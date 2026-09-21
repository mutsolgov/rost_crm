import hashlib
import json
from collections import Counter, defaultdict
from datetime import timezone

from sqlalchemy import false, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from .errors import APIError
from .models import (Attachment, CommandResult, Comment, Contract, Direction, Interaction,
                     InteractionEvent, License, Organization, OrganizationAccess,
                     OrganizationContact, Product, Program, ProgramProduct, User,
                     new_id, utcnow)
from .workflow import (STATES, SUBJECT_REQUIRED_STATES, TERMINAL_STATES,
                      WORKFLOW_REGISTRY, allowed_transitions, get_states,
                      get_transitions)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return aware(value).isoformat().replace("+00:00", "Z") if value else None


def permissions(user):
    defaults = {
        "manager": {"interactions.create", "interactions.transition", "interactions.comment",
                    "interactions.edit", "reports.read"},
        "supervisor": {"interactions.create", "interactions.transition", "interactions.comment",
                       "interactions.assign", "interactions.edit", "reports.read", "organizations.create",
                       "integrations.manage"},
        "administrator": {"workflow.manage", "users.manage", "organizations.create", "reports.read",
                          "integrations.manage"},
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


def attachment_dict(att):
    return {
        "id": att.id,
        "interaction_id": att.interaction_id,
        "visit_id": att.visit_id,
        "file_name": att.file_name,
        "file_size": att.file_size,
        "content_type": att.content_type,
        "checksum": att.checksum,
        "uploaded_by": att.uploaded_by,
        "created_at": iso(att.created_at),
    }


def interaction_dict(db, item, attachments=None, lookup=None):
    if lookup:
        org = lookup["orgs"].get(item.organization_id)
        owner = lookup["owners"].get(item.owner_id)
        program = lookup["progs"].get(item.program_id) if item.program_id else None
        product = lookup["prods"].get(item.product_id) if item.product_id else None
        direction = lookup["dirs"].get(program.direction_id) if program and program.direction_id else None
        contact = lookup["contacts"].get(item.contact_id) if item.contact_id else None
        contract = lookup["contracts"].get(item.contract_id) if item.contract_id else None
        license_ = lookup["licenses"].get(item.license_id) if item.license_id else None
    else:
        org = db.get(Organization, item.organization_id)
        owner = db.get(User, item.owner_id)
        program = db.get(Program, item.program_id) if item.program_id else None
        product = db.get(Product, item.product_id) if item.product_id else None
        direction = db.get(Direction, program.direction_id) if program else None
        contact = db.get(OrganizationContact, item.contact_id) if item.contact_id else None
        contract = db.get(Contract, item.contract_id) if item.contract_id else None
        license_ = db.get(License, item.license_id) if item.license_id else None
    if attachments is None:
        attachments = [
            attachment_dict(a)
            for a in db.scalars(
                select(Attachment).where(Attachment.interaction_id == item.id).order_by(Attachment.created_at)
            )
        ]
    return {
        "id": item.id, "title": item.title, "organization_id": item.organization_id,
        "organization_name": org.name, "program_id": item.program_id,
        "program_name": program.name if program else None, "product_id": item.product_id,
        "product_name": product.name if product else None,
        "direction_name": direction.name if direction else None,
        "contact_id": item.contact_id, "contact_name": contact.full_name if contact else None,
        "contract_id": item.contract_id, "contract_number": contract.number if contract else None,
        "license_id": item.license_id, "license_status": license_.transfer_status if license_ else None,
        "cycle_label": item.cycle_label, "owner_id": item.owner_id, "owner_name": owner.name,
        "state": item.state, "state_name": STATES[item.state]["name"],
        "workflow_version": item.workflow_version, "revision": item.revision,
        "created_at": iso(item.created_at), "updated_at": iso(item.updated_at), "closed_at": iso(item.closed_at),
        "attachments": attachments,
    }



def event_dict(event):
    payload = event.payload or {}
    result = {
        "id": event.id,
        "type": event.type,
        "effective_at": iso(event.effective_at),
        "received_at": iso(event.received_at),
        "sequence": event.sequence,
        "actor_name": event.actor_name,
        "payload": payload,
    }
    for key, val in payload.items():
        result[key] = val
    return result


def comment_dict(comment):
    return {
        "id": comment.id,
        "body": comment.body,
        "author_id": comment.author_id,
        "author_name": comment.author_name,
        "author": {"id": comment.author_id, "name": comment.author_name},
        "created_at": iso(comment.created_at),
        "visit_id": comment.visit_id,
    }


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
    attachments = [attachment_dict(a) for a in db.scalars(select(Attachment).where(
        Attachment.interaction_id == item.id).order_by(Attachment.created_at))]
    result = interaction_dict(db, item, attachments=attachments)
    result["allowed_transitions"] = (allowed_transitions(item.state, item.workflow_version or 1)
        if "interactions.transition" in permissions(user) else [])
    result["events"] = [event_dict(e) for e in db.scalars(select(InteractionEvent).where(
        InteractionEvent.interaction_id == item.id).order_by(InteractionEvent.sequence))]
    result["comments"] = [comment_dict(c) for c in db.scalars(select(Comment).where(
        Comment.interaction_id == item.id).order_by(Comment.created_at, Comment.id))]
    result["attachments"] = attachments
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
    if body.contact_id:
        c = db.get(OrganizationContact, body.contact_id)
        if not c or c.organization_id != body.organization_id:
            raise APIError("VALIDATION_ERROR", "Контакт не принадлежит организации взаимодействия.")
    if body.contract_id:
        c = db.get(Contract, body.contract_id)
        if not c or c.organization_id != body.organization_id:
            raise APIError("VALIDATION_ERROR", "Договор не принадлежит организации взаимодействия.")
    if body.license_id:
        lic = db.get(License, body.license_id)
        if not lic or lic.organization_id != body.organization_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не принадлежит организации взаимодействия.")
        if body.product_id and lic.product_id != body.product_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует выбранному ИТ-продукту.")
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
    transitions_map = get_transitions(item.workflow_version or 1)
    edge = transitions_map.get(body.transition_code)
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
    response = {**comment_dict(comment), "interaction_revision": item.revision, "revision": item.revision}
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


def update_interaction(db, user, interaction_id, body, key):
    item = scoped_interaction(db, user, interaction_id)
    require_permission(user, "interactions.edit")
    if item.closed_at:
        raise APIError("VALIDATION_ERROR", "Завершённое взаимодействие не подлежит изменению.")
    saved, replay = begin_command(db, user, f"update:{item.id}", key, body.model_dump())
    if replay is not None:
        return replay

    new_program_id = body.program_id if "program_id" in body.model_fields_set else item.program_id
    new_product_id = body.product_id if "product_id" in body.model_fields_set else item.product_id
    new_contact_id = body.contact_id if "contact_id" in body.model_fields_set else item.contact_id
    new_contract_id = body.contract_id if "contract_id" in body.model_fields_set else item.contract_id
    new_license_id = body.license_id if "license_id" in body.model_fields_set else item.license_id
    new_title = body.title if "title" in body.model_fields_set else item.title
    new_cycle_label = body.cycle_label if "cycle_label" in body.model_fields_set else item.cycle_label

    if item.state in SUBJECT_REQUIRED_STATES and (new_program_id is None or new_product_id is None):
        raise APIError("VALIDATION_ERROR", "На этом этапе нельзя сбросить ИТ-программу или ИТ-продукт.")

    validate_subject(db, new_program_id, new_product_id)

    if new_contact_id:
        c = db.get(OrganizationContact, new_contact_id)
        if not c or c.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Контакт не принадлежит организации взаимодействия.")
    if new_contract_id:
        c = db.get(Contract, new_contract_id)
        if not c or c.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Договор не принадлежит организации взаимодействия.")
    if new_license_id:
        lic = db.get(License, new_license_id)
        if not lic or lic.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не принадлежит организации взаимодействия.")
        if new_product_id and lic.product_id != new_product_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует выбранному ИТ-продукту.")

    changes = {}
    updates = {}
    field_pairs = [
        ("title", new_title),
        ("cycle_label", new_cycle_label),
        ("program_id", new_program_id),
        ("product_id", new_product_id),
        ("contact_id", new_contact_id),
        ("contract_id", new_contract_id),
        ("license_id", new_license_id),
    ]
    for field, new_val in field_pairs:
        old_val = getattr(item, field)
        if old_val != new_val:
            changes[field] = {"old": old_val, "new": new_val}
            updates[field] = new_val

    now = utcnow()
    cas(db, item, body.expected_revision, updated_at=now, **updates)
    append_event(db, item, user, "attributes_corrected", now, changes=changes)
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
    contacts = list(db.scalars(select(OrganizationContact).where(
        OrganizationContact.organization_id.in_(org_ids), OrganizationContact.active.is_(True)).order_by(OrganizationContact.full_name)))
    contracts = list(db.scalars(select(Contract).where(
        Contract.organization_id.in_(org_ids)).order_by(Contract.number)))
    licenses = list(db.scalars(select(License).where(
        License.organization_id.in_(org_ids)).order_by(License.created_at.desc())))
    return {
        "organizations": [{"id": o.id, "name": o.name, "type": o.type} for o in orgs],
        "programs": [{"id": p.id, "name": p.name, "direction_id": p.direction_id,
                      "direction_name": directions[p.direction_id].name}
                     for p in db.scalars(select(Program).order_by(Program.name))],
        "products": [{"id": p.id, "name": p.name, "vendor": p.vendor}
                     for p in db.scalars(select(Product).order_by(Product.name))],
        "owners": [{"id": o.id, "name": o.name} for o in owners],
        "directions": [{"id": d.id, "name": d.name} for d in directions.values()],
        "contacts": [{"id": c.id, "organization_id": c.organization_id, "full_name": c.full_name,
                      "position": c.position, "email": c.email, "phone": c.phone, "active": c.active}
                     for c in contacts],
        "contracts": [{"id": c.id, "organization_id": c.organization_id, "number": c.number,
                       "signed_on": iso(c.signed_on), "status": c.status, "created_at": iso(c.created_at)}
                      for c in contracts],
        "licenses": [{"id": l.id, "organization_id": l.organization_id, "product_id": l.product_id,
                      "contract_id": l.contract_id, "signed_on": iso(l.signed_on), "term_years": l.term_years,
                      "transfer_status": l.transfer_status, "created_at": iso(l.created_at)}
                     for l in licenses],
    }


def validate_filters(db, user, organization_ids=(), program_ids=(), product_ids=(), owner_ids=()):
    if organization_ids and not set(organization_ids) <= visible_organization_ids(db, user):
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
    items = list(db.scalars(query.order_by(Interaction.updated_at.desc(), Interaction.id).offset(
        (page - 1) * page_size).limit(page_size)))
    if page == 1 and len(items) < page_size:
        total = len(items)
    else:
        total = db.scalar(select(func.count()).select_from(query.subquery()))
    item_ids = [item.id for item in items]
    att_map = defaultdict(list)
    lookup = None
    if item_ids:
        for att in db.scalars(select(Attachment).where(Attachment.interaction_id.in_(item_ids)).order_by(Attachment.created_at)):
            att_map[att.interaction_id].append(attachment_dict(att))
        org_ids = {item.organization_id for item in items if item.organization_id}
        org_map = {o.id: o for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids)))} if org_ids else {}
        owner_ids = {item.owner_id for item in items if item.owner_id}
        owner_map = {u.id: u for u in db.scalars(select(User).where(User.id.in_(owner_ids)))} if owner_ids else {}
        prog_ids = {item.program_id for item in items if item.program_id}
        progs = list(db.scalars(select(Program).where(Program.id.in_(prog_ids)))) if prog_ids else []
        prog_map = {p.id: p for p in progs}
        dir_ids = {p.direction_id for p in progs if p.direction_id}
        dir_map = {d.id: d for d in db.scalars(select(Direction).where(Direction.id.in_(dir_ids)))} if dir_ids else {}
        prod_ids = {item.product_id for item in items if item.product_id}
        prod_map = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(prod_ids)))} if prod_ids else {}
        contact_ids = {item.contact_id for item in items if item.contact_id}
        contact_map = {c.id: c for c in db.scalars(select(OrganizationContact).where(OrganizationContact.id.in_(contact_ids)))} if contact_ids else {}
        contract_ids = {item.contract_id for item in items if item.contract_id}
        contract_map = {c.id: c for c in db.scalars(select(Contract).where(Contract.id.in_(contract_ids)))} if contract_ids else {}
        license_ids = {item.license_id for item in items if item.license_id}
        license_map = {l.id: l for l in db.scalars(select(License).where(License.id.in_(license_ids)))} if license_ids else {}
        lookup = {
            "orgs": org_map, "owners": owner_map, "progs": prog_map,
            "dirs": dir_map, "prods": prod_map, "contacts": contact_map,
            "contracts": contract_map, "licenses": license_map,
        }
    return {"items": [interaction_dict(db, item, attachments=att_map.get(item.id, []), lookup=lookup) for item in items], "total": total,
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
    events = list(db.scalars(select(InteractionEvent).where(InteractionEvent.interaction_id.in_(visible_ids),
        date_condition, InteractionEvent.received_at <= cutoff).order_by(
        InteractionEvent.effective_at, InteractionEvent.sequence, InteractionEvent.id)))
    latest, created = {}, set()
    for event in events:
        if event.type in ("created", "initial_state"):
            created.add(event.interaction_id)
        if event.payload.get("snapshot"):
            latest[event.interaction_id] = event.payload["snapshot"]
    rows, org_ids, state_counts = [], set(), Counter()
    filters = (("organization_id", body.organization_ids), ("program_id", body.program_ids),
               ("product_id", body.product_ids), ("owner_id", body.owner_ids))
    for interaction_id, data in sorted(latest.items()):
        if interaction_id not in created or any(values and data.get(field) not in values for field, values in filters):
            continue
        hist_owner = data.get("owner_id")
        if getattr(body, "historical_owner_id", None) and hist_owner != body.historical_owner_id:
            continue
        row = {"interaction_id": interaction_id, "historical_owner_id": hist_owner, **{key: data.get(key) for key in (
            "title", "organization_name", "program_name", "product_name", "state", "state_name", "owner_id", "owner_name")}}
        rows.append(row)
        if data.get("organization_id"):
            org_ids.add(data["organization_id"])
        state_counts[data["state"]] += 1
    counts_by_state = {code: state_counts.get(code, 0) for code in STATES}
    counts_by_historical_owner = dict(sorted(Counter(r.get("historical_owner_id") for r in rows if r.get("historical_owner_id")).items()))
    return {
        "report_type": "snapshot",
        "as_of": iso(body.as_of),
        "knowledge_cutoff": iso(cutoff),
        "as_of_inclusive": body.as_of_inclusive,
        "generated_at": iso(now),
        "total_interactions": len(rows),
        "interaction_ids": [r["interaction_id"] for r in rows],
        "counts_by_state": counts_by_state,
        "counts_by_historical_owner": counts_by_historical_owner,
        "rows": rows,
        "totals": {
            "interactions": len(rows),
            "organizations": len(org_ids),
            "counts_by_state": counts_by_state,
        },
    }


def activity(db, user, body):
    require_permission(user, "reports.read")
    validate_filters(db, user, body.organization_ids, body.program_ids, body.product_ids, body.owner_ids)
    now = utcnow()
    cutoff = aware(body.knowledge_cutoff or now)
    start, end = aware(body.from_date), aware(body.to_date)
    visible_ids = list(db.scalars(select(Interaction.id).where(scope_clause(user))))
    if len(visible_ids) > 5000:
        raise APIError("REPORT_LIMIT_EXCEEDED", "Первый выпуск ограничивает синхронный отчёт 5000 карточками.")

    all_events = list(db.scalars(
        select(InteractionEvent).where(
            InteractionEvent.interaction_id.in_(visible_ids),
            InteractionEvent.received_at <= cutoff,
        ).order_by(InteractionEvent.effective_at, InteractionEvent.sequence, InteractionEvent.id)
    ))

    assignments_by_interaction: dict[str, list[InteractionEvent]] = {}
    transitions: list[InteractionEvent] = []

    for ev in all_events:
        ev_eff = aware(ev.effective_at)
        if ev.type in ("assignment", "owner_changed", "created", "initial_state"):
            assignments_by_interaction.setdefault(ev.interaction_id, []).append(ev)
        if ev.type in ("transition", "state_changed") and start <= ev_eff < end:
            transitions.append(ev)

    def resolve_historical_owner(trans: InteractionEvent) -> str | None:
        trans_eff = aware(trans.effective_at)
        cands = [
            a for a in assignments_by_interaction.get(trans.interaction_id, [])
            if (aware(a.effective_at) < trans_eff or
                (aware(a.effective_at) == trans_eff and a.sequence <= trans.sequence))
        ]
        if not cands:
            return None
        latest = max(cands, key=lambda a: (aware(a.effective_at), a.sequence))
        payload = latest.payload or {}
        return payload.get("to_owner_id") or payload.get("owner_id") or (payload.get("snapshot") or {}).get("owner_id")

    filters = (("organization_id", body.organization_ids), ("program_id", body.program_ids),
               ("product_id", body.product_ids), ("owner_id", body.owner_ids))

    selected_rows = []
    transitions.sort(key=lambda t: (aware(t.effective_at), t.sequence, t.id))

    for trans in transitions:
        hist_owner = resolve_historical_owner(trans)
        if body.historical_owner_id and hist_owner != body.historical_owner_id:
            continue
        snap = (trans.payload or {}).get("snapshot") or {}
        if any(values and snap.get(field) not in values for field, values in filters):
            continue
        from_st = (trans.payload or {}).get("from_state")
        to_st = (trans.payload or {}).get("to_state")
        selected_rows.append({
            "event_id": trans.id,
            "interaction_id": trans.interaction_id,
            "from_state": from_st,
            "from_state_name": STATES.get(from_st, {}).get("name") if from_st else None,
            "to_state": to_st,
            "to_state_name": STATES.get(to_st, {}).get("name") if to_st else None,
            "historical_owner_id": hist_owner,
            "effective_at": iso(trans.effective_at),
        })

    event_ids = [r["event_id"] for r in selected_rows]
    interaction_ids = sorted({r["interaction_id"] for r in selected_rows})
    counts_by_interaction = dict(sorted(Counter(r["interaction_id"] for r in selected_rows).items()))
    counts_by_to_state = {code: sum(1 for r in selected_rows if r["to_state"] == code) for code in STATES}
    counts_by_historical_owner = dict(sorted(Counter(r["historical_owner_id"] for r in selected_rows if r.get("historical_owner_id")).items()))

    return {
        "report_type": "activity",
        "from_date": iso(start),
        "to_date": iso(end),
        "knowledge_cutoff": iso(cutoff),
        "generated_at": iso(now),
        "event_ids": event_ids,
        "interaction_ids": interaction_ids,
        "total_transitions": len(selected_rows),
        "total_interactions": len(interaction_ids),
        "counts_by_interaction": counts_by_interaction,
        "counts_by_to_state": counts_by_to_state,
        "counts_by_historical_owner": counts_by_historical_owner,
        "rows": selected_rows,
        "totals": {
            "transitions": len(selected_rows),
            "interactions": len(interaction_ids),
            "counts_by_to_state": counts_by_to_state,
        },
    }


def created_report(db, user, body):
    require_permission(user, "reports.read")
    validate_filters(db, user, body.organization_ids, body.program_ids, body.product_ids, body.owner_ids)
    now = utcnow()
    cutoff = aware(body.knowledge_cutoff or now)
    start, end = aware(body.from_date), aware(body.to_date)
    visible_ids = list(db.scalars(select(Interaction.id).where(scope_clause(user))))
    if len(visible_ids) > 5000:
        raise APIError("REPORT_LIMIT_EXCEEDED", "Первый выпуск ограничивает синхронный отчёт 5000 карточками.")

    events = list(db.scalars(
        select(InteractionEvent).where(
            InteractionEvent.interaction_id.in_(visible_ids),
            InteractionEvent.type.in_(["created", "initial_state"]),
            InteractionEvent.effective_at >= start,
            InteractionEvent.effective_at < end,
            InteractionEvent.received_at <= cutoff,
        ).order_by(InteractionEvent.effective_at, InteractionEvent.sequence, InteractionEvent.id)
    ))

    rows = []
    filters = (("organization_id", body.organization_ids), ("program_id", body.program_ids),
               ("product_id", body.product_ids), ("owner_id", body.owner_ids))
    for ev in events:
        snap = (ev.payload or {}).get("snapshot") or {}
        if any(values and snap.get(field) not in values for field, values in filters):
            continue
        rows.append({
            "interaction_id": ev.interaction_id,
            "title": snap.get("title"),
            "organization_id": snap.get("organization_id"),
            "organization_name": snap.get("organization_name"),
            "program_name": snap.get("program_name"),
            "product_name": snap.get("product_name"),
            "owner_id": snap.get("owner_id"),
            "owner_name": snap.get("owner_name"),
            "state": snap.get("state"),
            "state_name": snap.get("state_name"),
            "created_at": iso(ev.effective_at),
        })

    counts_by_organization = dict(sorted(Counter(r["organization_name"] for r in rows if r.get("organization_name")).items()))
    counts_by_owner = dict(sorted(Counter(r["owner_name"] for r in rows if r.get("owner_name")).items()))
    counts_by_state = {code: sum(1 for r in rows if r.get("state") == code) for code in STATES}

    return {
        "report_type": "created",
        "from_date": iso(start),
        "to_date": iso(end),
        "knowledge_cutoff": iso(cutoff),
        "generated_at": iso(now),
        "total_created": len(rows),
        "interaction_ids": [r["interaction_id"] for r in rows],
        "counts_by_organization": counts_by_organization,
        "counts_by_owner": counts_by_owner,
        "counts_by_state": counts_by_state,
        "rows": rows,
        "totals": {
            "created": len(rows),
            "counts_by_organization": counts_by_organization,
            "counts_by_owner": counts_by_owner,
        },
    }


def preview_workflow_migration(
    db,
    user,
    from_version: int,
    to_version: int,
    status_mapping: dict[str, str],
) -> dict:
    if user.role not in ("supervisor", "administrator"):
        raise APIError("FORBIDDEN", "Недостаточно прав для выполнения миграции процессов.", 403)

    if from_version not in WORKFLOW_REGISTRY or to_version not in WORKFLOW_REGISTRY:
        raise APIError("VALIDATION_ERROR", "Указана неизвестная версия workflow.", 422)

    if from_version == to_version:
        raise APIError("VALIDATION_ERROR", "Исходная и целевая версии workflow совпадают.", 422)

    from_states = get_states(from_version)
    to_states = get_states(to_version)
    from_terminal = {k for k, s in from_states.items() if s["kind"] == "terminal"}
    to_terminal = {k for k, s in to_states.items() if s["kind"] == "terminal"}

    for src, dst in status_mapping.items():
        if src not in from_states:
            raise APIError("VALIDATION_ERROR", f"Исходный статус '{src}' отсутствует в версии {from_version}.", 422)
        if dst not in to_states:
            raise APIError("VALIDATION_ERROR", f"Целевой статус '{dst}' отсутствует в версии {to_version}.", 422)
        if src in from_terminal and dst not in to_terminal:
            raise APIError(
                "VALIDATION_ERROR",
                f"Недопустимо сопоставлять терминальный статус '{src}' в активный статус '{dst}'.",
                422,
            )

    items = list(db.scalars(
        select(Interaction)
        .where(
            Interaction.workflow_version == from_version,
            Interaction.state.not_in(from_terminal),
        )
        .order_by(Interaction.id)
    ))

    status_distribution_before = dict(sorted(Counter(item.state for item in items).items()))
    status_distribution_after = dict(sorted(Counter(
        status_mapping[item.state] for item in items if item.state in status_mapping
    ).items()))

    active_statuses_present = set(status_distribution_before.keys())
    unmapped_statuses = sorted(list(active_statuses_present - set(status_mapping.keys())))

    target_to_sources: dict[str, list[str]] = {}
    for src, dst in status_mapping.items():
        target_to_sources.setdefault(dst, []).append(src)

    collisions = []
    warnings = []
    for target, sources in sorted(target_to_sources.items()):
        if len(sources) > 1:
            target_name = to_states[target]["name"] if target in to_states else target
            collisions.append({
                "target_status": target,
                "target_name": target_name,
                "source_statuses": sorted(sources),
            })
            warnings.append(f"Коллизия: статусы {sorted(sources)} объединены в '{target}'.")

    is_valid = len(unmapped_statuses) == 0
    if unmapped_statuses:
        warnings.append(f"Не все активные статусы сопоставлены: {unmapped_statuses}.")

    return {
        "from_version": from_version,
        "to_version": to_version,
        "affected_interactions_count": len(items),
        "status_distribution_before": status_distribution_before,
        "status_distribution_after": status_distribution_after,
        "unmapped_statuses": unmapped_statuses,
        "collisions": collisions,
        "warnings": warnings,
        "is_valid": is_valid,
    }


def commit_workflow_migration(
    db,
    user,
    from_version: int,
    to_version: int,
    status_mapping: dict[str, str],
    idempotency_key: str | None,
) -> dict:
    if not idempotency_key or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).")

    if user.role not in ("supervisor", "administrator"):
        raise APIError("FORBIDDEN", "Недостаточно прав для выполнения миграции процессов.", 403)

    payload = {
        "from_version": from_version,
        "to_version": to_version,
        "status_mapping": status_mapping,
    }
    operation = f"workflow_migration:{from_version}->{to_version}"
    saved, replay = begin_command(db, user, operation, idempotency_key, payload)
    if replay is not None:
        return replay

    if from_version not in WORKFLOW_REGISTRY or to_version not in WORKFLOW_REGISTRY:
        raise APIError("VALIDATION_ERROR", "Указана неизвестная версия workflow.", 422)

    if from_version == to_version:
        raise APIError("VALIDATION_ERROR", "Исходная и целевая версии workflow совпадают.", 422)

    from_states = get_states(from_version)
    to_states = get_states(to_version)
    from_terminal = {k for k, s in from_states.items() if s["kind"] == "terminal"}
    to_terminal = {k for k, s in to_states.items() if s["kind"] == "terminal"}

    for src, dst in status_mapping.items():
        if src not in from_states:
            raise APIError("VALIDATION_ERROR", f"Исходный статус '{src}' отсутствует в версии {from_version}.", 422)
        if dst not in to_states:
            raise APIError("VALIDATION_ERROR", f"Целевой статус '{dst}' отсутствует в версии {to_version}.", 422)
        if src in from_terminal and dst not in to_terminal:
            raise APIError(
                "VALIDATION_ERROR",
                f"Недопустимо сопоставлять терминальный статус '{src}' в активный статус '{dst}'.",
                422,
            )

    items = list(db.scalars(
        select(Interaction)
        .where(
            Interaction.workflow_version == from_version,
            Interaction.state.not_in(from_terminal),
        )
        .order_by(Interaction.id)
    ))

    for item in items:
        if item.state not in status_mapping:
            raise APIError("VALIDATION_ERROR", f"Статус '{item.state}' у карточки {item.id} не сопоставлен.", 422)

    now = utcnow()
    details = []
    status_distribution = {}

    for item in items:
        old_state = item.state
        old_revision = item.revision
        new_state = status_mapping[old_state]
        new_revision = old_revision + 1

        cas(
            db,
            item,
            old_revision,
            workflow_version=to_version,
            state=new_state,
            updated_at=now,
            closed_at=now if new_state in to_terminal else item.closed_at,
        )

        append_event(
            db,
            item,
            user,
            "workflow_migrated",
            now,
            from_version=from_version,
            to_version=to_version,
            from_state=old_state,
            to_state=new_state,
            previous_revision=old_revision,
            new_revision=new_revision,
        )

        status_distribution[new_state] = status_distribution.get(new_state, 0) + 1
        details.append({
            "interaction_id": item.id,
            "from_state": old_state,
            "to_state": new_state,
            "revision": new_revision,
        })

    response = {
        "status": "migrated",
        "from_version": from_version,
        "to_version": to_version,
        "migrated_count": len(items),
        "status_distribution": status_distribution,
        "details": details,
    }

    return finish_command(db, saved, response, None)


