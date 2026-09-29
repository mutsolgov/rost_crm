import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import event, false, func, inspect, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .errors import APIError
from .models import (AccessPolicyState, Attachment, BackgroundJob, CommandResult, Comment, Contract, Delivery,
                     DeliveryItem, Direction, IntegrationInbox, Interaction, InteractionEvent, License, Organization,
                     OrganizationAccess, OrganizationContact, Product, Program, ProgramProduct, ReportRow,
                     ReportRun, StateVisit, TransactionalOutbox, User, new_id, utcnow)
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
                    "interactions.edit", "interactions.write", "reports.read"},
        "supervisor": {"interactions.create", "interactions.transition", "interactions.comment",
                       "interactions.assign", "interactions.edit", "interactions.write", "reports.read",
                       "organizations.create", "integrations.manage"},
        "administrator": {"workflow.manage", "workflow.global_migrate", "users.manage", "organizations.create", "reports.read",
                          "integrations.manage"},
    }
    return sorted(defaults.get(user.role, set()) | set(user.permissions or []))


def require_permission(user, name):
    if name not in permissions(user):
        raise APIError("FORBIDDEN", "Недостаточно прав для этого действия.", 403)


def get_authz_epoch(db: Session) -> int:
    st = None
    for obj in db.new:
        if isinstance(obj, AccessPolicyState):
            st = obj
            break
    if st is None:
        st = db.get(AccessPolicyState, 1)
    if st is None:
        st = AccessPolicyState(singleton_id=1, epoch=1, updated_at=utcnow())
        db.add(st)
        db.flush(objects=[st])
    return int(st.epoch)


def bump_authz_epoch(db: Session) -> int:
    now = utcnow()
    db.info["_in_bump_authz_epoch"] = True
    try:
        st_new = None
        for obj in db.new:
            if isinstance(obj, AccessPolicyState):
                st_new = obj
                break
        if st_new is not None:
            st_new.epoch += 1
            st_new.updated_at = now
            db.info["_authz_epoch_bumped"] = True
            db.flush(objects=[st_new])
            return int(st_new.epoch)

        db.flush()

        res = db.execute(
            update(AccessPolicyState)
            .where(AccessPolicyState.singleton_id == 1)
            .values(epoch=AccessPolicyState.epoch + 1, updated_at=now)
        )
        if res.rowcount == 0:
            state = AccessPolicyState(singleton_id=1, epoch=2, updated_at=now)
            db.add(state)
            db.info["_authz_epoch_bumped"] = True
            db.flush(objects=[state])
            return 2

        key = db.identity_key(AccessPolicyState, 1)
        state = db.identity_map.get(key)
        if state is not None:
            db.expire(state)
        db.info["_authz_epoch_bumped"] = True
        epoch = db.scalar(select(AccessPolicyState.epoch).where(AccessPolicyState.singleton_id == 1))
        return int(epoch)
    finally:
        db.info.pop("_in_bump_authz_epoch", None)


def check_authz_epoch(db: Session, request_authz_epoch: int) -> bool:
    return get_authz_epoch(db) == request_authz_epoch


def ensure_authz_epoch_valid(db: Session, request_authz_epoch: int) -> None:
    current = get_authz_epoch(db)
    if current != request_authz_epoch:
        raise APIError(
            "REPORT_SCOPE_CHANGED",
            f"Контекст прав доступа изменился (эпоха {request_authz_epoch} != {current}).",
            403,
        )


def set_organization_access(
    db: Session,
    user_id: str,
    organization_id: str,
    *,
    can_create: bool = False,
    read_all: bool = False,
) -> OrganizationAccess:
    grant = db.get(OrganizationAccess, (user_id, organization_id))
    if grant is None:
        grant = OrganizationAccess(
            user_id=user_id,
            organization_id=organization_id,
            can_create=can_create,
            read_all=read_all,
        )
        db.add(grant)
    else:
        grant.can_create = can_create
        grant.read_all = read_all
    db.flush()
    return grant


def revoke_organization_access(
    db: Session,
    user_id: str,
    organization_id: str,
) -> bool:
    grant = db.get(OrganizationAccess, (user_id, organization_id))
    if grant is not None:
        db.delete(grant)
        db.flush()
        return True
    return False


def update_user_access(
    db: Session,
    user_id: str,
    *,
    role: str | None = None,
    team_id: str | None = None,
    active: bool | None = None,
    permissions: list | None = None,
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise APIError("NOT_FOUND", "Пользователь не найден.", 404)
    if role is not None:
        user.role = role
    if team_id is not None:
        user.team_id = team_id
    if active is not None:
        user.active = active
    if permissions is not None:
        user.permissions = permissions
    db.flush()
    return user


@event.listens_for(Session, "after_transaction_end")
def _authz_epoch_on_transaction_end(session: Session, transaction):
    if transaction.parent is not None:
        return
    session.info.pop("_authz_epoch_bumped", None)
    session.info.pop("_in_bump_authz_epoch", None)


@event.listens_for(Session, "before_flush")
def _authz_epoch_before_flush(session: Session, flush_context, instances):
    if (
        session.info.get("_authz_epoch_bumped")
        or session.info.get("_in_bump_authz_epoch")
    ):
        return
    should_bump = False
    flushing_new_del = (
        (session.new | session.deleted)
        if instances is None
        else [obj for obj in instances if obj in session.new or obj in session.deleted]
    )
    for obj in flushing_new_del:
        if isinstance(obj, (OrganizationAccess, User)):
            should_bump = True
            break
    if not should_bump:
        flushing_dirty = (
            session.dirty
            if instances is None
            else [obj for obj in instances if obj in session.dirty]
        )
        for obj in flushing_dirty:
            if isinstance(obj, OrganizationAccess):
                insp = inspect(obj)
                for attr in ("can_create", "read_all"):
                    if attr in insp.attrs and insp.attrs[attr].history.has_changes():
                        should_bump = True
                        break
                if should_bump:
                    break
            elif isinstance(obj, User):
                insp = inspect(obj)
                for attr in ("role", "team_id", "active", "permissions"):
                    if attr in insp.attrs and insp.attrs[attr].history.has_changes():
                        should_bump = True
                        break
                if should_bump:
                    break
    if should_bump:
        now = utcnow()
        st = None
        for obj in session.new:
            if isinstance(obj, AccessPolicyState):
                st = obj
                break
        if st is not None:
            st.epoch += 1
            st.updated_at = now
        else:
            st = session.get(AccessPolicyState, 1)
            if st is None:
                st = AccessPolicyState(singleton_id=1, epoch=2, updated_at=now)
                session.add(st)
            else:
                st.epoch = AccessPolicyState.epoch + 1
                st.updated_at = now
        session.info["_authz_epoch_bumped"] = True



def scope_clause(user):
    granted = select(OrganizationAccess.organization_id).where(
        OrganizationAccess.user_id == user.id, OrganizationAccess.read_all.is_(True))
    own = Interaction.owner_id == user.id if user.role == "manager" else false()
    if user.role == "supervisor" and user.team_id:
        team_mgr_ids = select(User.id).where(User.team_id == user.team_id)
        team = or_(Interaction.team_id == user.team_id, Interaction.owner_id.in_(team_mgr_ids))
    else:
        team = false()
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
    owned = set()
    if user.role == "manager":
        owned = set(db.scalars(select(Organization.id).where(Organization.owner_id == user.id)))
    elif user.role == "supervisor" and user.team_id:
        owned = set(db.scalars(select(Organization.id).join(User, Organization.owner_id == User.id).where(User.team_id == user.team_id)))
        team_mgr_grants = set(db.scalars(
            select(OrganizationAccess.organization_id)
            .join(User, OrganizationAccess.user_id == User.id)
            .where(
                User.team_id == user.team_id,
                or_(OrganizationAccess.can_create.is_(True), OrganizationAccess.read_all.is_(True))
            )
        ))
        granted |= team_mgr_grants
    return scoped | granted | owned


def has_organization_access(db, user, org_id: str) -> bool:
    if user.role == "administrator":
        return True
    org = db.get(Organization, org_id)
    if org and org.owner_id == user.id:
        return True
    if org and user.role == "supervisor" and org.owner_id:
        org_owner = db.get(User, org.owner_id)
        if org_owner and org_owner.team_id and org_owner.team_id == user.team_id:
            return True
    grant = db.get(OrganizationAccess, (user.id, org_id))
    if grant and (grant.read_all or grant.can_create):
        return True
    return org_id in visible_organization_ids(db, user)


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


def delivery_item_dict(item: DeliveryItem) -> dict:
    return {
        "id": item.id,
        "delivery_id": item.delivery_id,
        "item_kind": item.item_kind,
        "title": item.title,
        "attachment_id": item.attachment_id,
        "license_id": item.license_id,
        "material_version": item.material_version,
        "created_at": iso(item.created_at),
    }


def delivery_dict(db: Session, delivery: Delivery) -> dict:
    items = list(db.scalars(
        select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id).order_by(DeliveryItem.created_at)
    ))
    recorded_by_user = db.get(User, delivery.recorded_by)
    contact = db.get(OrganizationContact, delivery.recipient_contact_id) if delivery.recipient_contact_id else None
    return {
        "id": delivery.id,
        "organization_id": delivery.organization_id,
        "interaction_id": delivery.interaction_id,
        "status": delivery.status,
        "channel": delivery.channel,
        "sent_at": iso(delivery.sent_at),
        "confirmed_at": iso(delivery.confirmed_at),
        "recipient_contact_id": delivery.recipient_contact_id,
        "recipient_contact_name": contact.full_name if contact else None,
        "recorded_by": delivery.recorded_by,
        "recorded_by_name": recorded_by_user.name if recorded_by_user else None,
        "comment": delivery.comment,
        "created_at": iso(delivery.created_at),
        "revision": delivery.revision,
        "items": [delivery_item_dict(it) for it in items],
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
        "product_vendor": product.vendor if product else None,
        "direction_name": direction.name if direction else None,
        "contact_id": item.contact_id, "contact_name": contact.full_name if contact else None,
        "contract_id": item.contract_id, "contract_number": contract.number if contract else None,
        "license_id": item.license_id, "license_status": license_.transfer_status if license_ else None,
        "license_term_years": license_.term_years if license_ else None,
        "license_signed_on": iso(license_.signed_on) if (license_ and license_.signed_on) else None,
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
    for obj in db.new:
        if isinstance(obj, InteractionEvent) and getattr(obj, "interaction_id", None) == item.id:
            if obj.sequence and obj.sequence > last_sequence:
                last_sequence = obj.sequence
    event = InteractionEvent(interaction_id=item.id, type=kind, effective_at=at, received_at=at,
                             sequence=last_sequence + 1, actor_id=actor.id, actor_name=actor.name, payload=payload)
    db.add(event)
    db.flush()
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
    result["deliveries"] = [delivery_dict(db, d) for d in db.scalars(select(Delivery).where(
        Delivery.interaction_id == item.id).order_by(Delivery.created_at.desc()))]
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
        if c.archived_at is not None:
            raise APIError("VALIDATION_ERROR", "Нельзя привязать архивный контакт к взаимодействию.")
    if body.contract_id:
        c = db.get(Contract, body.contract_id)
        if not c or c.organization_id != body.organization_id:
            raise APIError("VALIDATION_ERROR", "Договор не принадлежит организации взаимодействия.")
    if body.license_id:
        lic = db.get(License, body.license_id)
        if not lic or lic.organization_id != body.organization_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не принадлежит организации взаимодействия.")
        if lic and body.contract_id and lic.contract_id and lic.contract_id != body.contract_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует указанному договору.")
        if body.product_id and lic.product_id != body.product_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует выбранному ИТ-продукту.")
        if body.program_id and not db.get(ProgramProduct, (body.program_id, lic.product_id)):
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует выбранной ИТ-программе.")
    now = utcnow()
    item_data = body.model_dump()
    start_comment = item_data.pop("comment", None)
    init_visit_id = new_id()
    item = Interaction(**item_data, id=new_id(), team_id=owner.team_id, state="contact_search",
                       revision=1, workflow_version=1, created_at=now, updated_at=now, visit_id=init_visit_id)
    db.add(item)
    db.flush()
    db.add(StateVisit(id=init_visit_id, interaction_id=item.id, state=item.state, entered_at=now))
    append_event(db, item, user, "created", now, to_state=item.state, owner_id=item.owner_id)
    if start_comment and start_comment.strip():
        comm = Comment(
            id=new_id(),
            interaction_id=item.id,
            author_id=user.id,
            author_name=user.name,
            body=start_comment.strip(),
            visit_id=item.visit_id,
            created_at=now,
        )
        db.add(comm)
        append_event(db, item, user, "comment_added", now, comment=start_comment.strip(), comment_id=comm.id)
    return finish_command(db, saved, interaction_dict(db, item), item.id)


def _advance_state_visit(db, interaction_id, new_state, now):
    open_visits = db.scalars(
        select(StateVisit).where(
            StateVisit.interaction_id == interaction_id,
            StateVisit.exited_at.is_(None),
        ).order_by(StateVisit.entered_at.desc())
    ).all()
    for open_visit in open_visits:
        open_visit.exited_at = now
        if open_visit.entered_at:
            open_visit.duration_seconds = max(0.0, (aware(now) - aware(open_visit.entered_at)).total_seconds())

    new_visit = StateVisit(
        id=new_id(),
        interaction_id=interaction_id,
        state=new_state,
        entered_at=now,
    )
    db.add(new_visit)
    return new_visit


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
    new_visit = _advance_state_visit(db, item.id, edge["to"], now)
    cas(db, item, body.expected_revision, state=edge["to"], updated_at=now,
        closed_at=now if edge["to"] in TERMINAL_STATES else None, visit_id=new_visit.id)

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
    cas(db, item, body.expected_revision, owner_id=owner.id, team_id=owner.team_id, updated_at=now)
    append_event(db, item, user, "owner_changed", now, owner_id=owner.id,
                 previous_owner_id=old_owner, comment=body.reason)
    bump_authz_epoch(db)
    return finish_command(db, saved, interaction_dict(db, item), item.id)


def update_interaction(db, user, interaction_id, body, key):
    item = scoped_interaction(db, user, interaction_id)
    require_permission(user, "interactions.edit")
    if item.closed_at:
        raise APIError("VALIDATION_ERROR", "Завершённое взаимодействие не подлежит изменению.")
    saved, replay = begin_command(db, user, f"update:{item.id}", key, body.model_dump(exclude_unset=True))
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
        if c.archived_at is not None and new_contact_id != item.contact_id:
            raise APIError("VALIDATION_ERROR", "Нельзя привязать архивный контакт к взаимодействию.")
    if new_contract_id:
        c = db.get(Contract, new_contract_id)
        if not c or c.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Договор не принадлежит организации взаимодействия.")
    if new_license_id:
        lic = db.get(License, new_license_id)
        if not lic or lic.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не принадлежит организации взаимодействия.")
        if lic and new_contract_id and lic.contract_id and lic.contract_id != new_contract_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует указанному договору.")
        if new_product_id and lic.product_id != new_product_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует выбранному ИТ-продукту.")
        if new_program_id and not db.get(ProgramProduct, (new_program_id, lic.product_id)):
            raise APIError("VALIDATION_ERROR", "Лицензия не соответствует выбранной ИТ-программе.")

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


def get_interaction_deliveries(db: Session, user, interaction_id: str) -> list[dict]:
    item = scoped_interaction(db, user, interaction_id)
    deliveries = list(db.scalars(
        select(Delivery).where(Delivery.interaction_id == item.id).order_by(Delivery.created_at.desc())
    ))
    return [delivery_dict(db, d) for d in deliveries]


def create_delivery(db: Session, user, interaction_id: str, body, key: str | None = None) -> dict:
    item = scoped_interaction(db, user, interaction_id)
    user_perms = permissions(user)
    if (
        not ({"interactions.edit", "interactions.transition", "interactions.write"} & set(user_perms))
        and user.role not in ("administrator", "admin")
    ):
        raise APIError("FORBIDDEN", "Недостаточно прав для фиксации выдачи ПО.", 403)
    if item.closed_at:
        raise APIError("VALIDATION_ERROR", "Нельзя регистрировать поставку для закрытого взаимодействия.")

    payload_data = body.model_dump() if hasattr(body, "model_dump") else dict(body)
    saved, replay = None, None
    if key:
        saved, replay = begin_command(db, user, f"delivery:{item.id}", key, payload_data)
        if replay is not None:
            return replay

    if payload_data.get("license_id"):
        lic = db.get(License, payload_data["license_id"])
        if not lic or lic.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Лицензия не принадлежит организации взаимодействия.")
    if payload_data.get("recipient_contact_id"):
        cnt = db.get(OrganizationContact, payload_data["recipient_contact_id"])
        if not cnt or cnt.organization_id != item.organization_id:
            raise APIError("VALIDATION_ERROR", "Контакт не принадлежит организации взаимодействия.")

    now = utcnow()
    if payload_data.get("expected_revision") is not None:
        cas(db, item, payload_data["expected_revision"], updated_at=now)
    else:
        item.revision += 1
        item.updated_at = now

    deliv_id = new_id()
    deliv = Delivery(
        id=deliv_id,
        organization_id=item.organization_id,
        interaction_id=item.id,
        status="confirmed",
        channel=payload_data.get("channel") or "email",
        sent_at=now,
        confirmed_at=now,
        recipient_contact_id=payload_data.get("recipient_contact_id") or item.contact_id,
        recorded_by=user.id,
        comment=payload_data.get("comment"),
        created_at=now,
        revision=1,
    )
    db.add(deliv)

    deliv_item = DeliveryItem(
        id=new_id(),
        delivery_id=deliv_id,
        item_kind=payload_data.get("item_kind") or "license",
        title=payload_data["title"],
        license_id=payload_data.get("license_id") or item.license_id,
        material_version=payload_data.get("material_version"),
        created_at=now,
    )
    db.add(deliv_item)
    db.flush()

    append_event(
        db,
        item,
        user,
        "delivery_recorded",
        now,
        delivery_id=deliv.id,
        title=deliv_item.title,
        channel=deliv.channel,
        item_kind=deliv_item.item_kind,
        material_version=deliv_item.material_version,
        status=deliv.status,
    )

    result = delivery_dict(db, deliv)
    if key and saved:
        return finish_command(db, saved, result, item.id)
    db.commit()
    return result


def catalogs(db, user):
    org_ids = visible_organization_ids(db, user)
    orgs = list(db.scalars(select(Organization).where(Organization.id.in_(org_ids)).order_by(Organization.name)))
    owner_ids = set(db.scalars(select(Interaction.owner_id).where(scope_clause(user))))
    owner_ids.add(user.id)
    if user.role in ("administrator", "admin"):
        owner_ids.update(db.scalars(select(User.id).where(User.role == "manager", User.active.is_(True))))
    elif user.role == "supervisor" and user.team_id:
        owner_ids.update(db.scalars(select(User.id).where(User.team_id == user.team_id, User.role == "manager")))
    learner_ids = {"cherepanona-s", "max_crich", "grigorev355", "osipenko833484", "mp_ivanov"}
    valid_roles = ["manager", "supervisor", "administrator"]
    owners = db.scalars(
        select(User).where(
            User.id.in_(owner_ids),
            User.active.is_(True),
            User.role.in_(valid_roles),
            User.id.not_in(learner_ids),
        ).order_by(User.name)
    )
    directions = {d.id: d for d in db.scalars(select(Direction).order_by(Direction.name))}
    contacts = list(db.scalars(select(OrganizationContact).where(
        OrganizationContact.organization_id.in_(org_ids),
        OrganizationContact.active.is_(True),
        OrganizationContact.archived_at.is_(None),
    ).order_by(OrganizationContact.full_name)))
    contracts = list(db.scalars(select(Contract).where(
        Contract.organization_id.in_(org_ids)).order_by(Contract.number)))
    licenses = list(db.scalars(select(License).where(
        License.organization_id.in_(org_ids)).order_by(License.created_at.desc())))
    return {
        "organizations": [{"id": o.id, "name": o.name, "type": o.type, "owner_id": getattr(o, "owner_id", None)} for o in orgs],
        "programs": [{"id": p.id, "name": p.name, "direction_id": p.direction_id,
                      "direction_name": directions[p.direction_id].name}
                     for p in db.scalars(select(Program).order_by(Program.name))],
        "products": [{"id": p.id, "name": p.name, "vendor": p.vendor}
                     for p in db.scalars(select(Product).order_by(Product.name))],
        "owners": [{"id": o.id, "name": o.name, "role": o.role} for o in owners],
        "directions": [{"id": d.id, "name": d.name} for d in directions.values()],
        "contacts": [
            {
                "id": c.id,
                "organization_id": c.organization_id,
                "full_name": c.full_name,
                "position": c.position,
                "email": c.email,
                "phone": c.phone,
                "active": c.active,
                "notes": c.notes,
                "revision": c.revision,
                "created_at": iso(c.created_at),
                "updated_at": iso(c.updated_at),
                "archived_at": iso(c.archived_at),
            }
            for c in contacts
        ],
        "contracts": [{"id": c.id, "organization_id": c.organization_id, "number": c.number,
                       "signed_on": iso(c.signed_on), "status": c.status, "created_at": iso(c.created_at)}
                      for c in contracts],
        "licenses": [{"id": l.id, "organization_id": l.organization_id, "product_id": l.product_id,
                      "contract_id": l.contract_id, "signed_on": iso(l.signed_on), "term_years": l.term_years,
                      "transfer_status": l.transfer_status, "created_at": iso(l.created_at)}
                     for l in licenses],
    }


def validate_filters(db, user, organization_ids=(), program_ids=(), product_ids=(), owner_ids=(), direction_ids=(), state_ids=()):
    if organization_ids and not set(organization_ids) <= visible_organization_ids(db, user):
        raise APIError("VALIDATION_ERROR", "Фильтр содержит недоступную организацию.")
    for ids, model in ((program_ids, Program), (product_ids, Product), (owner_ids, User), (direction_ids, Direction)):
        if ids:
            existing = set(db.scalars(select(model.id).where(model.id.in_(ids))))
            if set(ids) != existing:
                raise APIError("VALIDATION_ERROR", "Фильтр содержит неизвестное значение.")
    if state_ids:
        if any(s not in STATES for s in state_ids):
            raise APIError("VALIDATION_ERROR", "Фильтр содержит неизвестный этап.")


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
    res = {
        "total_interactions": len(items), "total_organizations": len({i.organization_id for i in items}),
        "active_interactions": sum(i.state not in TERMINAL_STATES for i in items),
        "completed_interactions": counts["completed"],
        "counts_by_state": [{"code": code, "name": STATES[code]["name"], "count": counts[code]} for code in STATES],
        "recent_events": [{"interaction_id": e.interaction_id, "title": item_map[e.interaction_id].title,
                           "event_type": e.type, "actor_name": e.actor_name, "at": iso(e.effective_at)} for e in events],
        "unassigned_program_count": sum(i.program_id is None for i in items),
    }
    if user.role in ("administrator", "admin"):
        total_users = db.scalar(select(func.count(User.id))) or 0
        total_organizations_catalog = db.scalar(select(func.count(Organization.id))) or 0
        total_programs_catalog = db.scalar(select(func.count(Program.id))) or 0
        total_products_catalog = db.scalar(select(func.count(Product.id))) or 0
        total_inbox_pending = db.scalar(
            select(func.count(IntegrationInbox.id)).where(func.lower(IntegrationInbox.status) == "pending")
        ) or 0
        try:
            from .config import get_settings
            from .integrations.factory import get_adapter
            adapter = get_adapter("lms", get_settings())
            health = adapter.health_check()
            raw_status = health.get("status", "ok") if isinstance(health, dict) else "ok"
            lms_health_status = "healthy" if str(raw_status).strip().lower() in ("ok", "healthy") else str(raw_status).strip().lower()
        except Exception:
            lms_health_status = "error"

        res["system_stats"] = {
            "total_users": total_users,
            "total_organizations_catalog": total_organizations_catalog,
            "total_programs_catalog": total_programs_catalog,
            "total_products_catalog": total_products_catalog,
            "total_inbox_pending": total_inbox_pending,
            "lms_health_status": lms_health_status,
        }
    return res


def snapshot(db, user, body):
    require_permission(user, "reports.read")
    validate_filters(db, user, body.organization_ids, body.program_ids, body.product_ids, body.owner_ids, getattr(body, "direction_ids", ()), getattr(body, "state_ids", ()))
    now = utcnow()
    cutoff = body.knowledge_cutoff or now
    where_clauses = [scope_clause(user)]
    if body.organization_ids:
        where_clauses.append(Interaction.organization_id.in_(body.organization_ids))
    if body.program_ids:
        where_clauses.append(Interaction.program_id.in_(body.program_ids))
    if body.product_ids:
        where_clauses.append(Interaction.product_id.in_(body.product_ids))
    if body.owner_ids:
        where_clauses.append(Interaction.owner_id.in_(body.owner_ids))
    dir_prog_ids = None
    if getattr(body, "direction_ids", None):
        dir_prog_ids = set(db.scalars(select(Program.id).where(Program.direction_id.in_(body.direction_ids))))
        where_clauses.append(Interaction.program_id.in_(dir_prog_ids) if dir_prog_ids else false())

    visible_ids = list(db.scalars(select(Interaction.id).where(*where_clauses)))
    if len(visible_ids) > 5000:
        raise APIError("REPORT_LIMIT_EXCEEDED", "Первый выпуск ограничивает синхронный отчёт 5000 карточками.")
    date_condition = (InteractionEvent.effective_at <= body.as_of if body.as_of_inclusive
                      else InteractionEvent.effective_at < body.as_of)
    # One ordered query freezes the selected event payloads for table and JSON export calculation.
    events = list(db.scalars(select(InteractionEvent).where(InteractionEvent.interaction_id.in_(visible_ids),
        date_condition, InteractionEvent.received_at <= cutoff).order_by(
        InteractionEvent.effective_at, InteractionEvent.sequence, InteractionEvent.id))) if visible_ids else []
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
        if dir_prog_ids is not None and data.get("program_id") not in dir_prog_ids:
            continue
        if getattr(body, "state_ids", None) and data.get("state") not in body.state_ids:
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
    validate_filters(db, user, body.organization_ids, body.program_ids, body.product_ids, body.owner_ids, getattr(body, "direction_ids", ()), getattr(body, "state_ids", ()))
    now = utcnow()
    cutoff = aware(body.knowledge_cutoff or now)
    start, end = aware(body.from_date), aware(body.to_date)
    where_clauses = [scope_clause(user)]
    if body.organization_ids:
        where_clauses.append(Interaction.organization_id.in_(body.organization_ids))
    if body.program_ids:
        where_clauses.append(Interaction.program_id.in_(body.program_ids))
    if body.product_ids:
        where_clauses.append(Interaction.product_id.in_(body.product_ids))
    if body.owner_ids:
        where_clauses.append(Interaction.owner_id.in_(body.owner_ids))
    dir_prog_ids = None
    if getattr(body, "direction_ids", None):
        dir_prog_ids = set(db.scalars(select(Program.id).where(Program.direction_id.in_(body.direction_ids))))
        where_clauses.append(Interaction.program_id.in_(dir_prog_ids) if dir_prog_ids else false())

    visible_ids = list(db.scalars(select(Interaction.id).where(*where_clauses)))
    if len(visible_ids) > 5000:
        raise APIError("REPORT_LIMIT_EXCEEDED", "Первый выпуск ограничивает синхронный отчёт 5000 карточками.")

    all_events = list(db.scalars(
        select(InteractionEvent).where(
            InteractionEvent.interaction_id.in_(visible_ids),
            InteractionEvent.received_at <= cutoff,
        ).order_by(InteractionEvent.effective_at, InteractionEvent.sequence, InteractionEvent.id)
    )) if visible_ids else []

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
        if dir_prog_ids is not None and snap.get("program_id") and snap.get("program_id") not in dir_prog_ids:
            continue
        from_st = (trans.payload or {}).get("from_state")
        to_st = (trans.payload or {}).get("to_state")
        if getattr(body, "state_ids", None) and to_st not in body.state_ids:
            continue

        inter = db.get(Interaction, trans.interaction_id)
        title = (inter.title if inter else None) or (snap.get("title") or "")
        org_id = (inter.organization_id if inter else None) or snap.get("organization_id")
        org = db.get(Organization, org_id) if org_id else None
        org_name = (org.name if org else None) or snap.get("organization_name") or ""

        owner_user = db.get(User, hist_owner) if hist_owner else None
        owner_name = owner_user.name if owner_user else (hist_owner or "Не назначен")

        actor_user = db.get(User, trans.actor_id) if trans.actor_id else None
        actor_name = actor_user.name if actor_user else (trans.actor_id or "Система")

        selected_rows.append({
            "event_id": trans.id,
            "interaction_id": trans.interaction_id,
            "title": title,
            "organization_name": org_name,
            "from_state": from_st,
            "from_state_name": STATES.get(from_st, {}).get("name") if from_st else None,
            "to_state": to_st,
            "to_state_name": STATES.get(to_st, {}).get("name") if to_st else None,
            "transition_code": (trans.payload or {}).get("transition_code") or f"{from_st}_to_{to_st}",
            "historical_owner_id": hist_owner,
            "owner_at_event": hist_owner,
            "owner_at_event_name": owner_name,
            "actor_name": actor_name,
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
    validate_filters(db, user, body.organization_ids, body.program_ids, body.product_ids, body.owner_ids, getattr(body, "direction_ids", ()), getattr(body, "state_ids", ()))
    now = utcnow()
    cutoff = aware(body.knowledge_cutoff or now)
    start, end = aware(body.from_date), aware(body.to_date)
    where_clauses = [scope_clause(user)]
    if body.organization_ids:
        where_clauses.append(Interaction.organization_id.in_(body.organization_ids))
    if body.program_ids:
        where_clauses.append(Interaction.program_id.in_(body.program_ids))
    if body.product_ids:
        where_clauses.append(Interaction.product_id.in_(body.product_ids))
    if body.owner_ids:
        where_clauses.append(Interaction.owner_id.in_(body.owner_ids))
    dir_prog_ids = None
    if getattr(body, "direction_ids", None):
        dir_prog_ids = set(db.scalars(select(Program.id).where(Program.direction_id.in_(body.direction_ids))))
        where_clauses.append(Interaction.program_id.in_(dir_prog_ids) if dir_prog_ids else false())

    visible_ids = list(db.scalars(select(Interaction.id).where(*where_clauses)))
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
    )) if visible_ids else []

    rows = []
    filters = (("organization_id", body.organization_ids), ("program_id", body.program_ids),
               ("product_id", body.product_ids), ("owner_id", body.owner_ids))
    for ev in events:
        snap = (ev.payload or {}).get("snapshot") or {}
        if any(values and snap.get(field) not in values for field, values in filters):
            continue
        if dir_prog_ids is not None and snap.get("program_id") and snap.get("program_id") not in dir_prog_ids:
            continue
        st = snap.get("state") or (ev.payload or {}).get("to_state") or (ev.payload or {}).get("state")
        if getattr(body, "state_ids", None) and st not in body.state_ids:
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
            "interactions": len(rows),
            "organizations": len(counts_by_organization),
            "counts_by_state": counts_by_state,
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

    where_clauses = [
        Interaction.workflow_version == from_version,
        Interaction.state.not_in(from_terminal),
    ]
    has_global_migrate = "workflow.global_migrate" in permissions(user)
    if not has_global_migrate:
        where_clauses.append(scope_clause(user))

    items = list(db.scalars(
        select(Interaction)
        .where(*where_clauses)
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

    invalid_subject_cards = []
    for item in items:
        target_state = status_mapping.get(item.state)
        if target_state in SUBJECT_REQUIRED_STATES:
            if not item.program_id or not item.product_id:
                invalid_subject_cards.append(item.id)
            else:
                try:
                    validate_subject(db, item.program_id, item.product_id)
                except APIError:
                    invalid_subject_cards.append(item.id)

    if invalid_subject_cards:
        warnings.append(
            f"Карточки {invalid_subject_cards} не имеют обязательной привязки программы/продукта для целевых этапов."
        )

    is_valid = len(unmapped_statuses) == 0 and len(invalid_subject_cards) == 0
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
        "card_revisions": {item.id: item.revision for item in items},
    }


def commit_workflow_migration(
    db,
    user,
    from_version: int,
    to_version: int,
    status_mapping: dict[str, str],
    idempotency_key: str | None,
    expected_card_revisions: dict[str, int] | None = None,
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

    where_clauses = [
        Interaction.workflow_version == from_version,
        Interaction.state.not_in(from_terminal),
    ]
    has_global_migrate = "workflow.global_migrate" in permissions(user)
    if not has_global_migrate:
        where_clauses.append(scope_clause(user))

    items = list(db.scalars(
        select(Interaction)
        .where(*where_clauses)
        .order_by(Interaction.id)
    ))

    if expected_card_revisions is not None:
        for item in items:
            exp_rev = expected_card_revisions.get(item.id)
            if exp_rev is not None and item.revision != exp_rev:
                raise APIError(
                    "REVISION_CONFLICT",
                    f"Карточка {item.id} была изменена после формирования превью миграции.",
                    409,
                )

    for item in items:
        if item.state not in status_mapping:
            raise APIError("VALIDATION_ERROR", f"Статус '{item.state}' у карточки {item.id} не сопоставлен.", 422)

    invalid_card_ids = []
    invalid_target_states = set()
    for item in items:
        target_state = status_mapping[item.state]
        if target_state in SUBJECT_REQUIRED_STATES:
            if not item.program_id or not item.product_id:
                invalid_card_ids.append(item.id)
                invalid_target_states.add(target_state)
            else:
                try:
                    validate_subject(db, item.program_id, item.product_id)
                except APIError:
                    invalid_card_ids.append(item.id)
                    invalid_target_states.add(target_state)

    if invalid_card_ids:
        target_str = ", ".join(sorted(invalid_target_states))
        raise APIError(
            "VALIDATION_ERROR",
            f"Карточки {invalid_card_ids} не имеют обязательной привязки к программе/продукту для этапа {target_str}",
            422,
            details={"invalid_card_ids": invalid_card_ids},
        )

    now = utcnow()
    details = []
    status_distribution = {}

    for item in items:
        old_state = item.state
        old_revision = item.revision
        new_state = status_mapping[old_state]
        new_revision = old_revision + 1

        new_visit_id = item.visit_id
        if old_state != new_state:
            new_visit = _advance_state_visit(db, item.id, new_state, now)
            new_visit_id = new_visit.id

        cas(
            db,
            item,
            old_revision,
            workflow_version=to_version,
            state=new_state,
            updated_at=now,
            closed_at=now if new_state in to_terminal else item.closed_at,
            visit_id=new_visit_id,
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


def _json_safe(obj):
    return json.loads(json.dumps(obj, default=str, ensure_ascii=False))


def freeze_report_dataset(
    db: Session,
    user: User,
    report_type: str,
    parameters: dict,
    rows: list[dict],
    knowledge_cutoff: datetime | None = None,
) -> ReportRun:
    if not user or not getattr(user, "id", None):
        raise APIError("UNAUTHORIZED", "Пользователь не определен.", 401)
    if not report_type or not str(report_type).strip():
        raise APIError("VALIDATION_ERROR", "Тип отчета обязателен.", 422)
    clean_type = str(report_type).strip()
    if len(clean_type) > 50:
        raise APIError("VALIDATION_ERROR", "Тип отчета не может превышать 50 символов.", 422)

    param_dict = _json_safe(parameters) if parameters is not None else {}
    if not isinstance(param_dict, dict):
        param_dict = {"value": param_dict}

    raw_rows = list(rows) if rows is not None else []
    row_list = [
        _json_safe(r) if isinstance(r, dict) else {"value": _json_safe(r)}
        for r in raw_rows
    ]

    cutoff_aware = None
    if knowledge_cutoff is not None:
        if isinstance(knowledge_cutoff, str):
            cleaned_cutoff = knowledge_cutoff.strip()
            if cleaned_cutoff:
                try:
                    dt = datetime.fromisoformat(cleaned_cutoff.replace("Z", "+00:00"))
                except ValueError:
                    raise APIError("VALIDATION_ERROR", "Некорректный формат knowledge_cutoff.", 422)
                cutoff_aware = aware(dt)
        elif isinstance(knowledge_cutoff, datetime):
            cutoff_aware = aware(knowledge_cutoff)
        elif isinstance(knowledge_cutoff, date):
            cutoff_aware = aware(datetime.combine(knowledge_cutoff, datetime.min.time()))
        else:
            raise APIError("VALIDATION_ERROR", "Некорректный тип knowledge_cutoff.", 422)

    p_hash = hashlib.sha256(
        json.dumps(param_dict, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    d_hash = hashlib.sha256(
        json.dumps(row_list, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    run = ReportRun(
        id=new_id(),
        requested_by=user.id,
        report_type=clean_type,
        parameters=param_dict,
        parameters_hash=p_hash,
        knowledge_cutoff=cutoff_aware,
        row_count=len(row_list),
        dataset_checksum=d_hash,
        created_at=utcnow(),
    )
    db.add(run)
    db.flush()
    db.add_all([
        ReportRow(
            id=new_id(),
            report_run_id=run.id,
            ordinal=ordinal,
            row_data=row,
        )
        for ordinal, row in enumerate(row_list, start=1)
    ])
    db.flush()
    return run


def get_frozen_report_rows(db: Session, report_run_id: str) -> list[dict]:
    if report_run_id is None:
        raise APIError("NOT_FOUND", "Срез отчета не найден.", 404)
    clean_id = str(report_run_id).strip()
    if not clean_id:
        raise APIError("NOT_FOUND", "Срез отчета не найден.", 404)
    run = db.get(ReportRun, clean_id)
    if not run:
        raise APIError("NOT_FOUND", "Срез отчета не найден.", 404)
    rows = db.scalars(
        select(ReportRow)
        .where(ReportRow.report_run_id == clean_id)
        .order_by(ReportRow.ordinal.asc())
    ).all()
    return [r.row_data for r in rows]


def enqueue_background_job(db: Session, user: User, kind: str, parameters: dict | None = None) -> BackgroundJob:
    if not user or not getattr(user, "id", None) or not getattr(user, "active", True):
        raise APIError("UNAUTHORIZED", "Пользователь не определен.", 401)

    clean_kind = str(kind or "").strip()
    if not clean_kind:
        raise APIError("VALIDATION_ERROR", "Тип фоновой задачи не может быть пустым.", 422)

    if parameters is not None:
        if not isinstance(parameters, dict):
            raise APIError("VALIDATION_ERROR", "Параметры фоновой задачи должны быть словарем.", 422)
        param_dict = _json_safe(parameters)
    else:
        param_dict = {}

    current_epoch = get_authz_epoch(db)
    job = BackgroundJob(
        id=new_id(),
        kind=clean_kind,
        status="queued",
        progress=0,
        requester_id=user.id,
        authz_epoch=current_epoch,
        parameters=param_dict,
        result_id=None,
        error_message=None,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    outbox = TransactionalOutbox(
        id=new_id(),
        event_type=f"job_queued:{clean_kind}",
        payload={"job_id": job.id, "kind": clean_kind, "requester_id": user.id},
        status="pending",
        created_at=utcnow(),
    )
    db.add(job)
    db.add(outbox)
    db.commit()
    return job


def _mark_job_outbox_processed(db: Session, job_id: str) -> None:
    if not job_id:
        return
    now = utcnow()
    for outbox in db.scalars(
        select(TransactionalOutbox).where(TransactionalOutbox.status == "pending")
    ).all():
        if isinstance(outbox.payload, dict) and outbox.payload.get("job_id") == job_id:
            outbox.status = "processed"
            outbox.processed_at = now
            break


def process_background_job(db: Session, job_id: str) -> BackgroundJob:
    clean_id = str(job_id).strip() if job_id else ""
    if not clean_id:
        raise APIError("NOT_FOUND", "Фоновая задача не найдена.", 404)
    job = db.get(BackgroundJob, clean_id)
    if not job:
        raise APIError("NOT_FOUND", "Фоновая задача не найдена.", 404)

    if job.status in ("completed", "cancelled", "failed", "running"):
        return job

    # 1. Atomic CAS transition to running for concurrency safety
    now = utcnow()
    res = db.execute(
        update(BackgroundJob)
        .where(BackgroundJob.id == clean_id, BackgroundJob.status == "queued")
        .values(status="running", progress=10, updated_at=now)
    )
    db.commit()
    db.refresh(job)
    if res.rowcount == 0:
        return job

    # 2. Check requester active status (152-ФЗ)
    requester = db.get(User, job.requester_id)
    if not requester or not requester.active:
        job.status = "cancelled"
        job.error_message = "REQUESTER_INACTIVE"
        job.updated_at = utcnow()
        _mark_job_outbox_processed(db, job.id)
        db.commit()
        return job

    # 3. Check authz_epoch (152-ФЗ)
    if not check_authz_epoch(db, job.authz_epoch):
        job.status = "cancelled"
        job.error_message = "REPORT_SCOPE_CHANGED"
        job.updated_at = utcnow()
        _mark_job_outbox_processed(db, job.id)
        db.commit()
        return job

    # 4. Process report or background workload
    try:
        job.progress = 50
        job.updated_at = utcnow()
        db.commit()

        if job.kind in ("report_snapshot", "snapshot"):
            from .schemas import SnapshotRequest

            params = dict(job.parameters or {})
            if "as_of" not in params or not params["as_of"]:
                params["as_of"] = utcnow().isoformat()
            req = SnapshotRequest(**params)
            report_result = snapshot(db, requester, req)

            # Re-verify epoch before freezing to guarantee zero race condition
            if not check_authz_epoch(db, job.authz_epoch):
                job.status = "cancelled"
                job.error_message = "REPORT_SCOPE_CHANGED"
                job.updated_at = utcnow()
                _mark_job_outbox_processed(db, job.id)
                db.commit()
                return job

            rows = report_result.get("rows", [])
            cutoff = req.knowledge_cutoff

            report_run = freeze_report_dataset(
                db=db,
                user=requester,
                report_type="snapshot",
                parameters=params,
                rows=rows,
                knowledge_cutoff=cutoff,
            )
            job.result_id = report_run.id
        elif job.parameters and "rows" in job.parameters:
            report_run = freeze_report_dataset(
                db=db,
                user=requester,
                report_type=job.kind,
                parameters=job.parameters,
                rows=job.parameters.get("rows", []),
            )
            job.result_id = report_run.id
        else:
            job.result_id = new_id()

        _mark_job_outbox_processed(db, job.id)
        job.status = "completed"
        job.progress = 100
        job.error_message = None
        job.updated_at = utcnow()
        db.commit()
        return job
    except Exception as exc:
        db.rollback()
        job = db.get(BackgroundJob, clean_id)
        if job:
            job.status = "failed"
            job.error_message = getattr(exc, "message", None) or str(exc)
            job.updated_at = utcnow()
            _mark_job_outbox_processed(db, job.id)
            db.commit()
            return job
        raise


def get_background_job_scoped(db: Session, user: User, job_id: str) -> BackgroundJob:
    if not user or not getattr(user, "id", None) or not getattr(user, "active", True):
        raise APIError("UNAUTHORIZED", "Пользователь не определен.", 401)

    clean_id = str(job_id).strip() if job_id else ""
    if not clean_id:
        raise APIError("NOT_FOUND", "Фоновая задача не найдена.", 404)

    job = db.get(BackgroundJob, clean_id)
    if not job:
        raise APIError("NOT_FOUND", "Фоновая задача не найдена.", 404)

    # 1. Administrator sees all system jobs
    if user.role == "administrator":
        return job

    # 2. Requester sees their own jobs
    if job.requester_id == user.id:
        return job

    # 3. Supervisor sees own team jobs
    if user.role == "supervisor" and user.team_id:
        requester = db.get(User, job.requester_id)
        if requester and requester.team_id == user.team_id:
            return job

    # Any other user -> 404 Not Found (152-ФЗ invariant: do not reveal existence)
    raise APIError("NOT_FOUND", "Фоновая задача не найдена.", 404)



