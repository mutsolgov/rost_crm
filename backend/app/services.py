import hashlib
import json
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import false, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from .errors import APIError
from .models import (CommandResult, Comment, Direction, Interaction, InteractionEvent,
                     Organization, OrganizationAccess, Product, Program, ProgramProduct,
                     User, new_id, utcnow)
from .workflow import STATES, SUBJECT_REQUIRED_STATES, TERMINAL_STATES, TRANSITIONS, allowed_transitions


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return aware(value).isoformat().replace("+00:00", "Z") if value else None


def permissions(user):
    defaults = {
        "manager": {"interactions.create", "interactions.transition", "interactions.comment", "reports.read"},
        "supervisor": {"interactions.create", "interactions.transition", "interactions.comment",
                       "interactions.assign", "reports.read", "organizations.create"},
        "administrator": {"workflow.manage", "users.manage", "organizations.create", "reports.read"},
    }
    return sorted(defaults.get(user.role, set()) | set(user.permissions or []))


def require_permission(user, name):
    if name not in permissions(user):
        raise APIError("FORBIDDEN", "Недостаточно прав для этого действия.", 403)


def scope_clause(user):
    granted = select(OrganizationAccess.organization_id).where(
        OrganizationAccess.user_id == user.id, OrganizationAccess.read_all.is_(True))
    own = Interaction.owner_id == user.id if user.role == "manager" else false()
    team = ((Interaction.team_id == user.team_id) if user.role == "supervisor" and user.team_id
            else false())
    return or_(own, team, Interaction.organization_id.in_(granted))


def scoped_interaction(db, user, interaction_id):
    interaction = db.scalar(select(Interaction).where(Interaction.id == interaction_id, scope_clause(user)))
    if not interaction:
        raise APIError("NOT_FOUND", "Взаимодействие не найдено.", 404)
    return interaction


def visible_organization_ids(db, user):
    scoped = set(db.scalars(select(Interaction.organization_id).where(scope_clause(user))))
    granted = set(db.scalars(select(OrganizationAccess.organization_id).where(
        OrganizationAccess.user_id == user.id,
        or_(OrganizationAccess.can_create.is_(True), OrganizationAccess.read_all.is_(True)))))
    return scoped | granted


def validate_subject(db, program_id, product_id):
    if program_id is not None and not db.get(Program, program_id):
        raise APIError("VALIDATION_ERROR", "Неизвестная ИТ-программа.")
    if product_id is not None and not db.get(Product, product_id):
        raise APIError("VALIDATION_ERROR", "Неизвестный ИТ-продукт.")
    if program_id and product_id and not db.get(ProgramProduct, (program_id, product_id)):
        raise APIError("VALIDATION_ERROR", "Продукт не связан с выбранной программой.")


def allowed_owner(db, user, owner_id, *, creation=False):
    owner = db.get(User, owner_id)
    if not owner or not owner.active or owner.role != "manager":
        raise APIError("VALIDATION_ERROR", "Выберите активного менеджера.")
    if user.role == "manager":
        if not creation or owner.id != user.id:
            raise APIError("FORBIDDEN", "Менеджер может создать карточку только на себя.", 403)
    elif user.role == "supervisor":
        if not user.team_id or owner.team_id != user.team_id:
            raise APIError("FORBIDDEN", "Назначение разрешено только внутри своей команды.", 403)
    elif user.role == "administrator":
        require_permission(user, "interactions.assign")
    else:
        raise APIError("FORBIDDEN", "Назначение запрещено.", 403)
    return owner


def interaction_dict(db, item):
    org = db.get(Organization, item.organization_id)
    owner = db.get(User, item.owner_id)
    program = db.get(Program, item.program_id) if item.program_id else None
    product = db.get(Product, item.product_id) if item.product_id else None
    direction = db.get(Direction, program.direction_id) if program else None
    return {
        "id": item.id, "title": item.title, "organization_id": item.organization_id,
        "organization_name": org.name, "program_id": item.program_id,
        "program_name": program.name if program else None, "product_id": item.product_id,
        "product_name": product.name if product else None,
        "direction_name": direction.name if direction else None,
        "cycle_label": item.cycle_label, "owner_id": item.owner_id, "owner_name": owner.name,
        "state": item.state, "state_name": STATES[item.state]["name"],
        "workflow_version": item.workflow_version, "revision": item.revision,
        "created_at": iso(item.created_at), "updated_at": iso(item.updated_at), "closed_at": iso(item.closed_at),
    }


def event_dict(event):
    result = {"id": event.id, "type": event.type, "effective_at": iso(event.effective_at),
              "received_at": iso(event.received_at), "sequence": event.sequence, "actor_name": event.actor_name}
    for key in ("from_state", "to_state", "owner_id", "comment"):
        if key in event.payload:
            result[key] = event.payload[key]
    return result


def comment_dict(comment):
    return {"id": comment.id, "body": comment.body, "author_name": comment.author_name,
            "created_at": iso(comment.created_at), "visit_id": comment.visit_id}


def append_event(db, item, actor, kind, at, **extra):
    # Each event carries an immutable reporting snapshot. Names are not rejoined from mutable catalogs later.
    payload = {"snapshot": interaction_dict(db, item), "visit_id": item.visit_id, **extra}
    # Revision protects the current card; several event types may share a revision
    # (for example a comment after a transition), so history has its own sequence.
    last_sequence = db.scalar(select(func.max(InteractionEvent.sequence)).where(
        InteractionEvent.interaction_id == item.id)) or 0
    event = InteractionEvent(interaction_id=item.id, type=kind, effective_at=at, received_at=at,
                             sequence=last_sequence + 1, actor_id=actor.id, actor_name=actor.name, payload=payload)
    db.add(event)
    return event


def detail(db, user, interaction_id):
    item = scoped_interaction(db, user, interaction_id)
    result = interaction_dict(db, item)
    result["allowed_transitions"] = (allowed_transitions(item.state)
        if "interactions.transition" in permissions(user) else [])
    result["events"] = [event_dict(e) for e in db.scalars(select(InteractionEvent).where(
        InteractionEvent.interaction_id == item.id).order_by(InteractionEvent.sequence))]
    result["comments"] = [comment_dict(c) for c in db.scalars(select(Comment).where(
        Comment.interaction_id == item.id).order_by(Comment.created_at, Comment.id))]
    return result


def begin_command(db, user, operation, key, payload):
    if not key or not key.strip() or len(key) > 200:
        raise APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode()).hexdigest()
    criteria = (CommandResult.user_id == user.id, CommandResult.operation == operation, CommandResult.key == key)
    saved = db.scalar(select(CommandResult).where(*criteria))
    if not saved:
        saved = CommandResult(user_id=user.id, operation=operation, key=key, payload_hash=digest)
        db.add(saved)
        try:
            # The unique key reserves this command inside the same transaction as its business effect.
            db.flush()
            return saved, None
        except IntegrityError:
            db.rollback()
            saved = db.scalar(select(CommandResult).where(*criteria))
            if not saved:
                raise APIError("IDEMPOTENCY_CONFLICT", "Команда выполняется; повторите запрос.", 409)
    if saved.payload_hash != digest:
        raise APIError("IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другим содержимым.", 409)
    if saved.resource_id:
        scoped_interaction(db, user, saved.resource_id)
    if saved.response is None:
        raise APIError("IDEMPOTENCY_CONFLICT", "Команда ещё выполняется.", 409)
    return saved, saved.response


def finish_command(db, saved, response, resource_id):
    saved.response, saved.resource_id = response, resource_id
    db.commit()
    return response


def cas(db, item, expected_revision, **values):
    result = db.execute(update(Interaction).where(Interaction.id == item.id,
                       Interaction.revision == expected_revision).values(
                           revision=expected_revision + 1, **values),
                       execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        db.rollback()
        raise APIError("REVISION_CONFLICT", "Карточка изменена. Обновите данные.", 409)
    db.refresh(item)


def create_interaction(db, user, body, key):
    # Missing idempotency metadata is a request-shape error and should be
    # reported before business authorization is evaluated.
    if not key or not key.strip() or len(key) > 200:
        raise APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).")
    require_permission(user, "interactions.create")
    grant = db.get(OrganizationAccess, (user.id, body.organization_id))
    if not grant or not grant.can_create or not db.get(Organization, body.organization_id):
        raise APIError("NOT_FOUND", "Организация недоступна для создания взаимодействия.", 404)
    owner = allowed_owner(db, user, body.owner_id, creation=True)
    saved, replay = begin_command(db, user, "interactions.create", key, body.model_dump())
    if replay is not None:
        return replay
    validate_subject(db, body.program_id, body.product_id)
    now = utcnow()
    item = Interaction(**body.model_dump(), id=new_id(), team_id=owner.team_id, state="contact_search",
                       revision=1, workflow_version=1, created_at=now, updated_at=now, visit_id=new_id())
    db.add(item)
    db.flush()
    append_event(db, item, user, "created", now, to_state=item.state, owner_id=item.owner_id)
    return finish_command(db, saved, interaction_dict(db, item), item.id)


def transition(db, user, interaction_id, body, key):
    item = scoped_interaction(db, user, interaction_id)
    require_permission(user, "interactions.transition")
    saved, replay = begin_command(db, user, f"transition:{item.id}", key, body.model_dump())
    if replay is not None:
        return replay
    edge = TRANSITIONS.get(body.transition_code)
    if not edge or edge["from"] != item.state:
        raise APIError("TRANSITION_NOT_ALLOWED", "Переход недоступен из текущего этапа.", 409)
    if edge["comment_required"] and not (body.comment or "").strip():
        raise APIError("VALIDATION_ERROR", "Для возврата, цикла или отмены нужен комментарий.")
    if edge["to"] in SUBJECT_REQUIRED_STATES and (not item.program_id or not item.product_id):
        raise APIError("VALIDATION_ERROR", "Перед этим этапом укажите ИТ-программу и ИТ-продукт.")
    validate_subject(db, item.program_id, item.product_id)
    old_state, old_visit, now = item.state, item.visit_id, utcnow()
    cas(db, item, body.expected_revision, state=edge["to"], updated_at=now,
        closed_at=now if edge["to"] in TERMINAL_STATES else None, visit_id=new_id())
    append_event(db, item, user, "state_changed", now, from_state=old_state, to_state=item.state,
                 owner_id=item.owner_id, comment=body.comment, previous_visit_id=old_visit)
    return finish_command(db, saved, interaction_dict(db, item), item.id)


def add_comment(db, user, interaction_id, body, key):
    item = scoped_interaction(db, user, interaction_id)
    require_permission(user, "interactions.comment")
    saved, replay = begin_command(db, user, f"comment:{item.id}", key, body.model_dump())
    if replay is not None:
        return replay
    now = utcnow()
    cas(db, item, body.expected_revision, updated_at=now)
    comment = Comment(id=new_id(), interaction_id=item.id, author_id=user.id, author_name=user.name,
                      body=body.body, visit_id=item.visit_id, created_at=now)
    db.add(comment)
    append_event(db, item, user, "comment_added", now, comment=body.body, comment_id=comment.id)
    response = {**comment_dict(comment), "interaction_revision": item.revision}
    return finish_command(db, saved, response, item.id)


def assign(db, user, interaction_id, body, key):
    item = scoped_interaction(db, user, interaction_id)
    require_permission(user, "interactions.assign")
    saved, replay = begin_command(db, user, f"assignment:{item.id}", key, body.model_dump())
    if replay is not None:
        return replay
    if user.role == "supervisor" and item.team_id != user.team_id:
        raise APIError("FORBIDDEN", "Назначение разрешено только в своей команде.", 403)
    owner = allowed_owner(db, user, body.owner_id)
    if item.closed_at:
        raise APIError("VALIDATION_ERROR", "Ответственный завершённого цикла не меняется.")
    if owner.id == item.owner_id:
        raise APIError("VALIDATION_ERROR", "Этот сотрудник уже назначен ответственным.")
    old_owner, now = item.owner_id, utcnow()
    cas(db, item, body.expected_revision, owner_id=owner.id, updated_at=now)
    append_event(db, item, user, "owner_changed", now, owner_id=owner.id,
                 previous_owner_id=old_owner, comment=body.reason)
    return finish_command(db, saved, interaction_dict(db, item), item.id)


def catalogs(db, user):
    org_ids = visible_organization_ids(db, user)
    orgs = list(db.scalars(select(Organization).where(Organization.id.in_(org_ids)).order_by(Organization.name)))
    owner_ids = set(db.scalars(select(Interaction.owner_id).where(scope_clause(user))))
    owner_ids.add(user.id)
    if user.role == "supervisor":
        owner_ids.update(db.scalars(select(User.id).where(User.team_id == user.team_id, User.role == "manager")))
    owners = db.scalars(select(User).where(User.id.in_(owner_ids), User.active.is_(True)).order_by(User.name))
    directions = {d.id: d for d in db.scalars(select(Direction).order_by(Direction.name))}
    return {
        "organizations": [{"id": o.id, "name": o.name, "type": o.type} for o in orgs],
        "programs": [{"id": p.id, "name": p.name, "direction_id": p.direction_id,
                      "direction_name": directions[p.direction_id].name}
                     for p in db.scalars(select(Program).order_by(Program.name))],
        "products": [{"id": p.id, "name": p.name, "vendor": p.vendor}
                     for p in db.scalars(select(Product).order_by(Product.name))],
        "owners": [{"id": o.id, "name": o.name} for o in owners],
        "directions": [{"id": d.id, "name": d.name} for d in directions.values()],
    }


def validate_filters(db, user, organization_ids=(), program_ids=(), product_ids=(), owner_ids=()):
    if not set(organization_ids) <= visible_organization_ids(db, user):
        raise APIError("VALIDATION_ERROR", "Фильтр содержит недоступную организацию.")
    for ids, model in ((program_ids, Program), (product_ids, Product), (owner_ids, User)):
        if ids:
            existing = set(db.scalars(select(model.id).where(model.id.in_(ids))))
            if set(ids) != existing:
                raise APIError("VALIDATION_ERROR", "Фильтр содержит неизвестное значение.")


def list_interactions(db, user, q=None, organization_id=None, program_id=None, product_id=None,
                      owner_id=None, state=None, page=1, page_size=50):
    validate_filters(db, user, [organization_id] if organization_id else [], [program_id] if program_id else [],
                     [product_id] if product_id else [], [owner_id] if owner_id else [])
    if state and state not in STATES:
        raise APIError("VALIDATION_ERROR", "Неизвестный этап процесса.")
    query = select(Interaction).where(scope_clause(user))
    for field, value in (("organization_id", organization_id), ("program_id", program_id),
                         ("product_id", product_id), ("owner_id", owner_id), ("state", state)):
        if value:
            query = query.where(getattr(Interaction, field) == value)
    if q:
        # Escape SQL wildcard syntax so the search is literal, including user '%' and '_'.
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        orgs = select(Organization.id).where(Organization.name.ilike(pattern, escape="\\"))
        query = query.where(or_(Interaction.title.ilike(pattern, escape="\\"), Interaction.organization_id.in_(orgs)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Interaction.updated_at.desc(), Interaction.id).offset(
        (page - 1) * page_size).limit(page_size))
    return {"items": [interaction_dict(db, item) for item in items], "total": total,
            "page": page, "page_size": page_size}


def dashboard(db, user):
    items = list(db.scalars(select(Interaction).where(scope_clause(user))))
    counts = Counter(i.state for i in items)
    item_map = {i.id: i for i in items}
    events = db.scalars(select(InteractionEvent).where(InteractionEvent.interaction_id.in_(item_map)).order_by(
        InteractionEvent.effective_at.desc(), InteractionEvent.sequence.desc()).limit(8))
    return {"total_interactions": len(items), "total_organizations": len({i.organization_id for i in items}),
            "active_interactions": sum(i.state not in TERMINAL_STATES for i in items),
            "completed_interactions": counts["completed"],
            "counts_by_state": [{"code": code, "name": STATES[code]["name"], "count": counts[code]} for code in STATES],
            "recent_events": [{"interaction_id": e.interaction_id, "title": item_map[e.interaction_id].title,
                               "event_type": e.type, "actor_name": e.actor_name, "at": iso(e.effective_at)} for e in events],
            "unassigned_program_count": sum(i.program_id is None for i in items)}


def snapshot(db, user, body):
    require_permission(user, "reports.read")
    validate_filters(db, user, body.organization_ids, body.program_ids, body.product_ids, body.owner_ids)
    now = utcnow()
    cutoff = body.knowledge_cutoff or now
    visible_ids = list(db.scalars(select(Interaction.id).where(scope_clause(user))))
    if len(visible_ids) > 5000:
        raise APIError("REPORT_LIMIT_EXCEEDED", "Первый выпуск ограничивает синхронный отчёт 5000 карточками.")
    date_condition = (InteractionEvent.effective_at <= body.as_of if body.as_of_inclusive
                      else InteractionEvent.effective_at < body.as_of)
    # One ordered query freezes the selected event payloads for table and JSON export calculation.
    events = db.scalars(select(InteractionEvent).where(InteractionEvent.interaction_id.in_(visible_ids),
        date_condition, InteractionEvent.received_at <= cutoff).order_by(
        InteractionEvent.effective_at, InteractionEvent.sequence, InteractionEvent.id))
    latest, created = {}, set()
    for event in events:
        if event.type == "created":
            created.add(event.interaction_id)
        if event.payload.get("snapshot"):
            latest[event.interaction_id] = event.payload["snapshot"]
    rows, org_ids, state_counts = [], set(), Counter()
    filters = (("organization_id", body.organization_ids), ("program_id", body.program_ids),
               ("product_id", body.product_ids), ("owner_id", body.owner_ids))
    for interaction_id, data in sorted(latest.items()):
        if interaction_id not in created or any(values and data.get(field) not in values for field, values in filters):
            continue
        rows.append({"interaction_id": interaction_id, **{key: data.get(key) for key in (
            "title", "organization_name", "program_name", "product_name", "state", "state_name", "owner_id", "owner_name")}})
        org_ids.add(data["organization_id"])
        state_counts[data["state"]] += 1
    return {"report_type": "snapshot", "as_of": iso(body.as_of), "knowledge_cutoff": iso(cutoff),
            "as_of_inclusive": body.as_of_inclusive, "generated_at": iso(now), "rows": rows,
            "totals": {"interactions": len(rows), "organizations": len(org_ids), "counts_by_state": dict(state_counts)}}
