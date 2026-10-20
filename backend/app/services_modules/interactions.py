from collections import Counter, defaultdict

from sqlalchemy import false, func, or_, select, update
from sqlalchemy.orm import Session

from ..errors import APIError
from ..models import (
    Attachment,
    Comment,
    Contract,
    Delivery,
    DeliveryItem,
    Direction,
    IntegrationInbox,
    Interaction,
    InteractionEvent,
    License,
    Organization,
    OrganizationAccess,
    OrganizationContact,
    Product,
    Program,
    ProgramProduct,
    StateVisit,
    User,
    new_id,
    utcnow,
)
from ..workflow import (
    STATES,
    SUBJECT_REQUIRED_STATES,
    TERMINAL_STATES,
    WORKFLOW_REGISTRY,
    allowed_transitions,
    get_states,
    get_transitions,
)
from .common import aware, iso
from .idempotency import begin_command, finish_command
from .rbac import (
    allowed_owner,
    bump_authz_epoch,
    permissions,
    require_permission,
    scope_clause,
    scoped_interaction,
    visible_organization_ids,
)


def validate_subject(db, program_id, product_id):
    if program_id is not None and not db.get(Program, program_id):
        raise APIError("VALIDATION_ERROR", "Неизвестная ИТ-программа.")
    if product_id is not None and not db.get(Product, product_id):
        raise APIError("VALIDATION_ERROR", "Неизвестный ИТ-продукт.")
    if program_id and product_id and not db.get(ProgramProduct, (program_id, product_id)):
        raise APIError("VALIDATION_ERROR", "Продукт не связан с выбранной программой.")


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
    if user.role != "administrator":
        require_permission(user, "interactions.create")
        grant = db.get(OrganizationAccess, (user.id, body.organization_id))
        if not grant or not grant.can_create or not db.get(Organization, body.organization_id):
            raise APIError("NOT_FOUND", "Организация недоступна для создания взаимодействия.", 404)
    else:
        if not db.get(Organization, body.organization_id):
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
    if user.role == "manager":
        valid_grants = set(db.scalars(
            select(OrganizationAccess.organization_id).where(OrganizationAccess.user_id == user.id)
        ))
        owned_orgs = set(db.scalars(
            select(Organization.id).where(Organization.owner_id == user.id)
        ))
        org_ids = org_ids & (valid_grants | owned_orgs)
    orgs = list(db.scalars(select(Organization).where(Organization.id.in_(org_ids)).order_by(Organization.name)))
    owner_ids = set(db.scalars(select(Interaction.owner_id).where(scope_clause(user))))
    owner_ids.add(user.id)
    if user.role in ("administrator", "admin"):
        owner_ids.update(db.scalars(select(User.id).where(User.role == "manager", User.active.is_(True))))
    elif user.role == "supervisor" and user.team_id:
        owner_ids.update(db.scalars(select(User.id).where(User.team_id == user.team_id, User.role == "manager")))
    valid_roles = ["manager", "supervisor", "administrator"]
    owners = db.scalars(
        select(User).where(
            User.id.in_(owner_ids),
            User.active.is_(True),
            User.role.in_(valid_roles),
        ).order_by(User.name)
    )
    directions = {d.id: d for d in db.scalars(select(Direction).order_by(Direction.name))}
    program_products = list(db.scalars(select(ProgramProduct)))
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
        "program_products": [{"program_id": pp.program_id, "product_id": pp.product_id} for pp in program_products],
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
                      owner_id=None, state=None, page=1, page_size=50, direction_id=None):
    validate_filters(db, user, [organization_id] if organization_id else [], [program_id] if program_id else [],
                     [product_id] if product_id else [], [owner_id] if owner_id else [],
                     direction_ids=[direction_id] if direction_id else [])
    if state and state not in STATES:
        raise APIError("VALIDATION_ERROR", "Неизвестный этап процесса.")
    query = select(Interaction).where(scope_clause(user))
    for field, value in (("organization_id", organization_id), ("program_id", program_id),
                         ("product_id", product_id), ("owner_id", owner_id), ("state", state)):
        if value:
            query = query.where(getattr(Interaction, field) == value)
    if direction_id:
        dir_prog_ids = set(db.scalars(select(Program.id).where(Program.direction_id == direction_id)))
        query = query.where(Interaction.program_id.in_(dir_prog_ids) if dir_prog_ids else false())
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
    state_rows = db.execute(
        select(Interaction.state, func.count(Interaction.id))
        .where(scope_clause(user))
        .group_by(Interaction.state)
    ).all()
    counts = {st: cnt for st, cnt in state_rows}
    total_interactions = sum(counts.values())
    total_organizations = db.scalar(
        select(func.count(func.distinct(Interaction.organization_id)))
        .where(scope_clause(user))
    ) or 0
    active_interactions = sum(cnt for st, cnt in counts.items() if st not in TERMINAL_STATES)
    completed_interactions = counts.get("completed", 0)
    unassigned_program_count = db.scalar(
        select(func.count(Interaction.id))
        .where(scope_clause(user), Interaction.program_id.is_(None))
    ) or 0

    event_rows = db.execute(
        select(
            InteractionEvent.interaction_id,
            Interaction.title,
            InteractionEvent.type,
            InteractionEvent.actor_name,
            InteractionEvent.effective_at,
        )
        .join(Interaction, Interaction.id == InteractionEvent.interaction_id)
        .where(scope_clause(user))
        .order_by(InteractionEvent.effective_at.desc(), InteractionEvent.sequence.desc())
        .limit(8)
    ).all()
    recent_events = [
        {
            "interaction_id": row[0],
            "title": row[1],
            "event_type": row[2],
            "actor_name": row[3],
            "at": iso(row[4]),
        }
        for row in event_rows
    ]
    res = {
        "total_interactions": total_interactions,
        "total_organizations": total_organizations,
        "active_interactions": active_interactions,
        "completed_interactions": completed_interactions,
        "counts_by_state": [{"code": code, "name": STATES[code]["name"], "count": counts.get(code, 0)} for code in STATES],
        "recent_events": recent_events,
        "unassigned_program_count": unassigned_program_count,
    }
    if user.role in ("administrator", "admin"):
        from ..config import get_settings
        from ..integrations.factory import get_adapter

        settings = get_settings()
        total_users = db.scalar(select(func.count(User.id))) or 0
        total_organizations_catalog = db.scalar(select(func.count(Organization.id))) or 0
        total_programs_catalog = db.scalar(select(func.count(Program.id))) or 0
        total_products_catalog = db.scalar(select(func.count(Product.id))) or 0
        total_contracts_catalog = db.scalar(select(func.count(Contract.id))) or 0
        total_inbox_pending = db.scalar(
            select(func.count(IntegrationInbox.id)).where(func.lower(IntegrationInbox.status) == "pending")
        ) or 0
        try:
            adapter = get_adapter("lms", settings)
            health = adapter.health_check()
            raw_status = health.get("status", "ok") if isinstance(health, dict) else "ok"
            lms_health_status = "healthy" if str(raw_status).strip().lower() in ("ok", "healthy") else str(raw_status).strip().lower()
        except Exception:
            lms_health_status = "error"

        try:
            w_adapter = get_adapter("website", settings)
            w_health = w_adapter.health_check()
            w_raw_status = w_health.get("status", "ok") if isinstance(w_health, dict) else "ok"
            website_health_status = "healthy" if str(w_raw_status).strip().lower() in ("ok", "healthy") else str(w_raw_status).strip().lower()
        except Exception:
            website_health_status = "error"

        recent_system_events = []
        event_rows = db.execute(
            select(
                InteractionEvent.id,
                InteractionEvent.type,
                Interaction.title,
                InteractionEvent.actor_name,
                InteractionEvent.received_at,
                InteractionEvent.payload,
            )
            .join(Interaction, Interaction.id == InteractionEvent.interaction_id)
            .order_by(InteractionEvent.received_at.desc(), InteractionEvent.sequence.desc())
            .limit(25)
        ).all()

        for row in event_rows:
            evt_id, evt_type, ix_title, actor_name, received_at, payload = row
            p_dict = payload if isinstance(payload, dict) else {}
            if evt_type == "created":
                title = f"Создано взаимодействие: {ix_title}"
            elif evt_type in ("transition", "state_changed"):
                to_st = p_dict.get("to_state", "")
                to_st_name = STATES.get(to_st, {}).get("name", to_st) if to_st else ""
                title = f"Переход на этап «{to_st_name}»: {ix_title}"
            elif evt_type in ("assignment", "owner_changed"):
                title = f"Назначен ответственный: {ix_title}"
            elif evt_type in ("comment", "comment_added"):
                title = f"Добавлен комментарий к: {ix_title}"
            elif evt_type == "attributes_corrected":
                title = f"Обновлены реквизиты карточки: {ix_title}"
            elif evt_type == "attachment_uploaded":
                fname = p_dict.get("file_name") or p_dict.get("filename", "")
                title = f"Загружен файл «{fname}»: {ix_title}" if fname else f"Загружен файл: {ix_title}"
            elif evt_type == "attachment_deleted":
                fname = p_dict.get("file_name") or p_dict.get("filename", "")
                title = f"Удалён файл «{fname}»: {ix_title}" if fname else f"Удалён файл: {ix_title}"
            elif evt_type == "delivery_recorded":
                dtitle = p_dict.get("title") or "Пакет ПО"
                title = f"Выдача ПО ({dtitle}): {ix_title}"
            elif evt_type == "workflow_migrated":
                fv = p_dict.get("from_version") or "?"
                tv = p_dict.get("to_version") or "?"
                title = f"Миграция процесса v{fv}→v{tv}: {ix_title}"
            else:
                title = f"Системная операция: {ix_title}"

            ts_iso = iso(received_at)
            recent_system_events.append({
                "id": str(evt_id),
                "type": evt_type,
                "event_type": evt_type,
                "title": title,
                "description": f"Пользователь: {actor_name or 'Система'}",
                "actor_name": actor_name,
                "received_at": ts_iso,
                "created_at": ts_iso,
                "timestamp": ts_iso,
            })

        res["system_stats"] = {
            "total_users": total_users,
            "total_organizations_catalog": total_organizations_catalog,
            "total_programs_catalog": total_programs_catalog,
            "total_products_catalog": total_products_catalog,
            "total_contracts_catalog": total_contracts_catalog,
            "total_inbox_pending": total_inbox_pending,
            "lms_health_status": lms_health_status,
            "website_health_status": website_health_status,
            "recent_system_events": recent_system_events,
        }
    return res


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
