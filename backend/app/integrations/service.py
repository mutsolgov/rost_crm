from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..config import Settings, get_settings
from ..errors import APIError
from ..models import (
    IntegrationInbox,
    Interaction,
    LearningMetric,
    Organization,
    OrganizationAccess,
    OrganizationContact,
    Program,
    User,
    new_id,
    utcnow,
)
from ..services import (
    allowed_owner,
    append_event,
    aware,
    begin_command,
    finish_command,
    iso,
    require_permission,
    validate_subject,
    visible_organization_ids,
)
from .factory import get_adapter


def get_integrations_status(
    db: Session,
    user: User,
    config: Settings | None = None,
) -> dict[str, Any]:
    require_permission(user, "integrations.manage")

    cfg = config or get_settings()
    lms_adapter = get_adapter("lms", cfg)
    website_adapter = get_adapter("website", cfg)

    lms_health = lms_adapter.health_check()
    website_health = website_adapter.health_check()

    total_inbox = db.scalar(select(func.count(IntegrationInbox.id))) or 0
    total_pending = (
        db.scalar(select(func.count(IntegrationInbox.id)).where(IntegrationInbox.status == "pending"))
        or 0
    )
    total_processed = (
        db.scalar(select(func.count(IntegrationInbox.id)).where(IntegrationInbox.status == "processed"))
        or 0
    )
    total_quarantined = (
        db.scalar(select(func.count(IntegrationInbox.id)).where(IntegrationInbox.status == "quarantined"))
        or 0
    )
    total_rejected = (
        db.scalar(select(func.count(IntegrationInbox.id)).where(IntegrationInbox.status == "rejected"))
        or 0
    )
    total_metrics = db.scalar(select(func.count(LearningMetric.id))) or 0

    last_received = db.scalar(select(func.max(IntegrationInbox.received_at)))
    last_synced_at = iso(last_received) if last_received else None

    return {
        "adapters": [lms_health, website_health],
        "adapters_by_source": {
            "lms": lms_health,
            "website": website_health,
        },
        "total_inbox": total_inbox,
        "total_pending": total_pending,
        "total_processed": total_processed,
        "total_quarantined": total_quarantined,
        "total_rejected": total_rejected,
        "total_metrics": total_metrics,
        "last_synced_at": last_synced_at,
    }


def _is_revision_older(rev1: str, rev2: str) -> bool:
    try:
        return int(rev1) < int(rev2)
    except (ValueError, TypeError):
        return str(rev1) < str(rev2)


def sync_source(
    db: Session,
    user: User,
    source: str,
    config: Settings | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    require_permission(user, "integrations.manage")

    src = (source or "").strip().lower()
    if src not in {"lms", "website"}:
        raise APIError("VALIDATION_ERROR", f"Неизвестный источник интеграции: '{source}'. Допустимые: 'lms', 'website'")

    cfg = config or get_settings()

    saved = None
    if idempotency_key:
        saved, replay = begin_command(
            db,
            user,
            f"integrations.sync:{src}",
            idempotency_key,
            {"source": src},
        )
        if replay is not None:
            return replay

    adapter = get_adapter(src, cfg)
    envelopes = adapter.fetch_updates()

    if getattr(adapter, "last_error", None):
        err_item = IntegrationInbox(
            id=new_id(),
            source=src,
            entity_type="sync_error",
            external_id=f"sync_error_{uuid4().hex[:12]}",
            source_revision=str(int(utcnow().timestamp())),
            status="error",
            error_message=adapter.last_error,
            payload={"error": adapter.last_error, "base_url": getattr(adapter, "base_url", None)},
            received_at=utcnow(),
        )
        db.add(err_item)
        db.flush()
        res = {
            "status": "error",
            "source": src,
            "error_message": adapter.last_error,
            "received_count": 0,
            "processed_count": 0,
            "pending_count": 0,
            "skipped_count": 0,
            "quarantined_count": 0,
        }
        return finish_command(db, saved, res, None) if saved else res

    received_count = len(envelopes)
    processed_count = 0
    pending_count = 0
    skipped_count = 0
    quarantined_count = 0

    for env in envelopes:
        # Check duplicate by (source, entity_type, external_id, source_revision)
        existing = db.scalar(
            select(IntegrationInbox).where(
                IntegrationInbox.source == env.source,
                IntegrationInbox.entity_type == env.entity_type,
                IntegrationInbox.external_id == env.external_id,
                IntegrationInbox.source_revision == env.source_revision,
            )
        )
        if existing:
            skipped_count += 1
            continue

        item = IntegrationInbox(
            id=new_id(),
            source=env.source,
            entity_type=env.entity_type,
            external_id=env.external_id,
            source_revision=env.source_revision,
            payload=env.payload,
            status="pending",
            received_at=aware(env.received_at) if hasattr(env, "received_at") and env.received_at else utcnow(),
        )
        db.add(item)

        if env.entity_type == "learning_metric":
            org_id = env.payload.get("organization_id")
            prog_id = env.payload.get("program_id")
            org = db.get(Organization, org_id) if org_id else None
            if not org and env.payload.get("organization_name"):
                org = db.scalar(select(Organization).where(Organization.name == env.payload["organization_name"]))
            prog = db.get(Program, prog_id) if prog_id else None
            if not prog and env.payload.get("program_name"):
                prog = db.scalar(select(Program).where(Program.name == env.payload["program_name"]))

            if org and prog:
                as_of_val = env.payload.get("as_of")
                if isinstance(as_of_val, str):
                    try:
                        as_of_dt = aware(datetime.fromisoformat(as_of_val))
                    except Exception:
                        as_of_dt = utcnow()
                elif isinstance(as_of_val, datetime):
                    as_of_dt = aware(as_of_val)
                else:
                    as_of_dt = aware(env.effective_at) if hasattr(env, "effective_at") and env.effective_at else utcnow()

                metric_code = env.payload.get("metric_code", "")
                val = float(env.payload.get("value", 0.0))
                unit = str(env.payload.get("unit", ""))

                metric = db.scalar(
                    select(LearningMetric).where(
                        LearningMetric.source == env.source,
                        LearningMetric.external_id == env.external_id,
                    )
                )
                if metric:
                    applied_inboxes = list(
                        db.scalars(
                            select(IntegrationInbox)
                            .where(
                                IntegrationInbox.source == env.source,
                                IntegrationInbox.entity_type == "learning_metric",
                                IntegrationInbox.external_id == env.external_id,
                                IntegrationInbox.status == "processed",
                                IntegrationInbox.error_message.is_(None),
                                IntegrationInbox.id != item.id,
                            )
                        )
                    )
                    prev_inbox = None
                    for prev in applied_inboxes:
                        if prev_inbox is None or _is_revision_older(prev_inbox.source_revision, prev.source_revision):
                            prev_inbox = prev

                    if prev_inbox and _is_revision_older(env.source_revision, prev_inbox.source_revision):
                        item.status = "skipped"
                        item.matched_organization_id = org.id
                        item.processed_at = utcnow()
                        item.error_message = (
                            f"Skipped: envelope source_revision {env.source_revision} older than existing revision {prev_inbox.source_revision}"
                        )
                        skipped_count += 1
                        continue

                    res = db.execute(
                        update(LearningMetric)
                        .where(
                            LearningMetric.id == metric.id,
                            or_(
                                LearningMetric.last_applied_revision.is_(None),
                                LearningMetric.last_applied_revision == metric.last_applied_revision,
                            ),
                        )
                        .values(
                            organization_id=org.id,
                            program_id=prog.id,
                            metric_code=metric_code,
                            value=val,
                            unit=unit,
                            as_of=as_of_dt,
                            last_applied_revision=str(env.source_revision),
                        )
                    )
                    metric.last_applied_revision = str(env.source_revision)
                else:
                    metric = LearningMetric(
                        id=new_id(),
                        organization_id=org.id,
                        program_id=prog.id,
                        metric_code=metric_code,
                        value=val,
                        unit=unit,
                        as_of=as_of_dt,
                        source=env.source,
                        external_id=env.external_id,
                        last_applied_revision=str(env.source_revision),
                        created_at=utcnow(),
                    )
                    db.add(metric)
                item.status = "processed"
                item.matched_organization_id = org.id
                item.processed_at = utcnow()
                processed_count += 1
            else:
                item.status = "quarantined"
                item.error_message = f"Организация ({org_id}) или программа ({prog_id}) не найдена в системе"
                quarantined_count += 1

        elif env.entity_type == "application":
            org_name = (env.payload.get("organization_name") or "").strip()
            if org_name:
                matched_org = db.scalar(
                    select(Organization).where(func.lower(Organization.name) == org_name.lower())
                )
                if not matched_org:
                    matches = list(db.scalars(
                        select(Organization).where(Organization.name.ilike(f"%{org_name}%"))
                    ))
                    if len(matches) == 1:
                        matched_org = matches[0]
                    elif not matches:
                        all_orgs = list(db.scalars(select(Organization)))
                        sub_matches = [o for o in all_orgs if o.name.lower() in org_name.lower()]
                        if len(sub_matches) == 1:
                            matched_org = sub_matches[0]

                if matched_org:
                    item.matched_organization_id = matched_org.id
            item.status = "pending"
            pending_count += 1

    result = {
        "source": src,
        "received_count": received_count,
        "processed_count": processed_count,
        "pending_count": pending_count,
        "skipped_count": skipped_count,
        "quarantined_count": quarantined_count,
        "message": (
            f"Синхронизация '{src}' завершена: получено {received_count}, обработано {processed_count}, "
            f"ожидает сверки {pending_count}, пропущено дубликатов {skipped_count}."
        ),
    }

    if idempotency_key and saved:
        return finish_command(db, saved, result, None)
    db.commit()
    return result


def list_inbox_items(
    db: Session,
    user: User,
    source: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    require_permission(user, "integrations.manage")

    query = select(IntegrationInbox)
    if source:
        query = query.where(IntegrationInbox.source == source.strip().lower())
    if status:
        query = query.where(IntegrationInbox.status == status.strip().lower())

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    items = list(
        db.scalars(
            query.order_by(IntegrationInbox.received_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    )

    matched_org_ids = {item.matched_organization_id for item in items if item.matched_organization_id}
    orgs_map = (
        {o.id: o.name for o in db.scalars(select(Organization).where(Organization.id.in_(matched_org_ids)))}
        if matched_org_ids
        else {}
    )

    serialized = []
    for item in items:
        serialized.append({
            "id": item.id,
            "source": item.source,
            "entity_type": item.entity_type,
            "external_id": item.external_id,
            "source_revision": item.source_revision,
            "payload": item.payload,
            "status": item.status,
            "error_message": item.error_message,
            "matched_organization_id": item.matched_organization_id,
            "matched_organization_name": (
                orgs_map.get(item.matched_organization_id) if item.matched_organization_id else None
            ),
            "matched_interaction_id": item.matched_interaction_id,
            "received_at": iso(item.received_at),
            "processed_at": iso(item.processed_at),
        })

    return {
        "items": serialized,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def reconcile_application(
    db: Session,
    user: User,
    inbox_id: str,
    action: str,
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    require_permission(user, "integrations.manage")

    params = params or {}
    act = (action or "").strip().lower()
    if act not in {"link_existing", "create_new", "reject"}:
        raise APIError(
            "VALIDATION_ERROR",
            f"Неизвестное действие: '{action}'. Допустимые действия: 'link_existing', 'create_new', 'reject'",
        )

    saved = None
    if idempotency_key:
        saved, replay = begin_command(
            db,
            user,
            f"integrations.resolve:{inbox_id}",
            idempotency_key,
            {"inbox_id": inbox_id, "action": act, "params": params},
        )
        if replay is not None:
            return replay

    item = db.get(IntegrationInbox, inbox_id)
    if not item:
        raise APIError("NOT_FOUND", "Запись в очереди интеграции не найдена.", 404)
    if item.entity_type not in ("application", "learner"):
        raise APIError("VALIDATION_ERROR", "Сверка поддерживается только для заявок ('application') и слушателей ('learner').")

    res = db.execute(
        update(IntegrationInbox)
        .where(IntegrationInbox.id == inbox_id, IntegrationInbox.status == "pending")
        .values(status="processing")
    )
    if res.rowcount == 0:
        db.refresh(item)
        raise APIError(
            "VALIDATION_ERROR",
            f"Запись уже обработана (текущий статус: {item.status}) или выполняется другим оператором.",
            409,
        )

    item.status = "processing"

    now = utcnow()
    org: Organization | None = None
    contact: OrganizationContact | None = None
    interaction: Interaction | None = None

    if act == "reject":
        item.status = "rejected"
        item.error_message = params.get("reason") or "Отклонено оператором"
        item.processed_at = now

    elif act == "link_existing":
        org_id = params.get("organization_id") or item.matched_organization_id
        if not org_id:
            raise APIError("VALIDATION_ERROR", "Не указана организация для привязки заявки.")
        org = db.get(Organization, org_id)
        if not org:
            raise APIError("NOT_FOUND", "Организация для привязки не найдена.", 404)

        item.matched_organization_id = org.id

        interaction_id = params.get("interaction_id")
        if interaction_id:
            interaction = db.get(Interaction, interaction_id)
            if not interaction:
                raise APIError("NOT_FOUND", "Взаимодействие для привязки не найдено.", 404)
            item.matched_interaction_id = interaction.id

        contact_id = params.get("contact_id")
        if contact_id:
            contact = db.get(OrganizationContact, contact_id)
            if not contact or contact.organization_id != org.id:
                raise APIError("VALIDATION_ERROR", "Указанный контакт не принадлежит данной организации.")
        elif item.entity_type != "learner":
            rep_name = params.get("representative_name") or item.payload.get("representative_name")
            if rep_name:
                rep_pos = params.get("representative_position") or item.payload.get(
                    "representative_position", "Представитель вуза"
                )
                rep_email = params.get("representative_email") or item.payload.get("representative_email")
                rep_phone = params.get("representative_phone") or item.payload.get("representative_phone")
                contact = OrganizationContact(
                    id=new_id(),
                    organization_id=org.id,
                    full_name=rep_name,
                    position=rep_pos,
                    email=rep_email,
                    phone=rep_phone,
                    active=True,
                )
                db.add(contact)
                db.flush()

        should_create = params.get("create_interaction", True if "owner_id" in params and not interaction_id else False)
        if should_create:
            owner_id = params.get("owner_id")
            if not owner_id and user.role == "manager":
                owner_id = user.id
            if not owner_id:
                raise APIError("VALIDATION_ERROR", "Для создания взаимодействия укажите ответственного менеджера.")

            owner = allowed_owner(db, user, owner_id, creation=True)

            grant = db.get(OrganizationAccess, (owner.id, org.id))
            if not grant:
                db.add(OrganizationAccess(user_id=owner.id, organization_id=org.id, can_create=True, read_all=False))

            title = params.get("interaction_title") or f"Заявка: {org.name}"
            prog_id = params.get("program_id") or item.payload.get("program_id")
            prod_id = params.get("product_id")
            if prog_id or prod_id:
                validate_subject(db, prog_id, prod_id)

            cycle_label = params.get("cycle_label") or "2026/2027"

            interaction = Interaction(
                id=new_id(),
                title=title,
                organization_id=org.id,
                program_id=prog_id,
                product_id=prod_id,
                cycle_label=cycle_label,
                owner_id=owner.id,
                team_id=owner.team_id,
                contact_id=contact.id if contact else None,
                state="contact_search",
                revision=1,
                workflow_version=1,
                created_at=now,
                updated_at=now,
                visit_id=new_id(),
            )
            db.add(interaction)
            db.flush()
            append_event(db, interaction, user, "created", now, to_state=interaction.state, owner_id=interaction.owner_id)
            item.matched_interaction_id = interaction.id

        item.status = "processed"
        item.processed_at = now

    elif act == "create_new":
        org_name = (params.get("organization_name") or item.payload.get("organization_name") or "").strip()
        if not org_name:
            raise APIError("VALIDATION_ERROR", "Не указано название создаваемой организации.")
        org_type = params.get("organization_type", "university")

        org = Organization(id=new_id(), name=org_name, type=org_type)
        db.add(org)
        db.flush()

        db.add(OrganizationAccess(user_id=user.id, organization_id=org.id, can_create=True, read_all=True))
        item.matched_organization_id = org.id

        rep_name = (
            params.get("representative_name")
            or item.payload.get("representative_name")
            or "Представитель организации"
        )
        rep_pos = params.get("representative_position") or item.payload.get(
            "representative_position", "Представитель вуза"
        )
        rep_email = params.get("representative_email") or item.payload.get("representative_email")
        rep_phone = params.get("representative_phone") or item.payload.get("representative_phone")
        contact = OrganizationContact(
            id=new_id(),
            organization_id=org.id,
            full_name=rep_name,
            position=rep_pos,
            email=rep_email,
            phone=rep_phone,
            active=True,
        )
        db.add(contact)
        db.flush()

        should_create = params.get("create_interaction", True if "owner_id" in params else False)
        if should_create:
            owner_id = params.get("owner_id")
            if not owner_id and user.role == "manager":
                owner_id = user.id
            if not owner_id:
                raise APIError("VALIDATION_ERROR", "Для создания взаимодействия укажите ответственного менеджера.")

            owner = allowed_owner(db, user, owner_id, creation=True)

            if owner.id != user.id:
                grant = db.get(OrganizationAccess, (owner.id, org.id))
                if not grant:
                    db.add(OrganizationAccess(user_id=owner.id, organization_id=org.id, can_create=True, read_all=False))

            title = params.get("interaction_title") or f"Заявка: {org.name}"
            prog_id = params.get("program_id") or item.payload.get("program_id")
            prod_id = params.get("product_id")
            if prog_id or prod_id:
                validate_subject(db, prog_id, prod_id)

            cycle_label = params.get("cycle_label") or "2026/2027"

            interaction = Interaction(
                id=new_id(),
                title=title,
                organization_id=org.id,
                program_id=prog_id,
                product_id=prod_id,
                cycle_label=cycle_label,
                owner_id=owner.id,
                team_id=owner.team_id,
                contact_id=contact.id if contact else None,
                state="contact_search",
                revision=1,
                workflow_version=1,
                created_at=now,
                updated_at=now,
                visit_id=new_id(),
            )
            db.add(interaction)
            db.flush()
            append_event(db, interaction, user, "created", now, to_state=interaction.state, owner_id=interaction.owner_id)
            item.matched_interaction_id = interaction.id

        item.status = "processed"
        item.processed_at = now

    if item.payload:
        p = dict(item.payload)
        if item.matched_organization_id:
            p["matched_organization_id"] = item.matched_organization_id
        if item.matched_interaction_id:
            p["matched_interaction_id"] = item.matched_interaction_id
        item.payload = p
        flag_modified(item, "payload")

    result = {
        "id": item.id,
        "status": item.status,
        "action": act,
        "error_message": item.error_message,
        "matched_organization_id": item.matched_organization_id,
        "organization_id": org.id if org else item.matched_organization_id,
        "organization_name": org.name if org else None,
        "contact_id": contact.id if contact else None,
        "matched_interaction_id": item.matched_interaction_id,
        "interaction_id": item.matched_interaction_id,
        "processed_at": iso(item.processed_at),
    }

    if idempotency_key and saved:
        return finish_command(db, saved, result, None)
    db.commit()
    return result


resolve_inbox_item = reconcile_application


def get_learning_metrics_summary(
    db: Session,
    user: User,
    organization_id: str | None = None,
    program_id: str | None = None,
) -> dict[str, Any]:
    require_permission(user, "reports.read")

    query = select(LearningMetric)

    allowed_orgs = visible_organization_ids(db, user)
    if organization_id:
        if organization_id not in allowed_orgs:
            return {
                "total_cohorts": 0,
                "total_enrolled": 0,
                "total_completed": 0,
                "avg_attendance_rate": 0.0,
                "by_program": [],
                "by_organization": [],
                "metrics": [],
            }
        query = query.where(LearningMetric.organization_id == organization_id)
    else:
        query = query.where(LearningMetric.organization_id.in_(allowed_orgs))

    if program_id:
        query = query.where(LearningMetric.program_id == program_id)

    metrics_list = list(db.scalars(query.order_by(LearningMetric.as_of.desc())))

    org_ids = {m.organization_id for m in metrics_list}
    prog_ids = {m.program_id for m in metrics_list}
    orgs_map = (
        {o.id: o.name for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids)))}
        if org_ids
        else {}
    )
    progs_map = (
        {p.id: p.name for p in db.scalars(select(Program).where(Program.id.in_(prog_ids)))}
        if prog_ids
        else {}
    )

    total_cohorts = 0
    total_enrolled = 0
    total_completed = 0
    attendance_rates: list[float] = []

    by_program_map: dict[str, dict[str, Any]] = {}
    by_org_map: dict[str, dict[str, Any]] = {}
    serialized_metrics: list[dict[str, Any]] = []

    for m in metrics_list:
        org_name = orgs_map.get(m.organization_id, m.organization_id)
        prog_name = progs_map.get(m.program_id, m.program_id)

        if m.program_id not in by_program_map:
            by_program_map[m.program_id] = {
                "program_id": m.program_id,
                "program_name": prog_name,
                "active_cohorts": 0,
                "students_enrolled": 0,
                "students_completed": 0,
                "_attendance_rates": [],
            }
        if m.organization_id not in by_org_map:
            by_org_map[m.organization_id] = {
                "organization_id": m.organization_id,
                "organization_name": org_name,
                "active_cohorts": 0,
                "students_enrolled": 0,
                "students_completed": 0,
                "_attendance_rates": [],
            }

        prog_acc = by_program_map[m.program_id]
        org_acc = by_org_map[m.organization_id]

        if m.metric_code == "active_cohorts":
            val_int = int(round(m.value))
            total_cohorts += val_int
            prog_acc["active_cohorts"] += val_int
            org_acc["active_cohorts"] += val_int
        elif m.metric_code == "students_enrolled":
            val_int = int(round(m.value))
            total_enrolled += val_int
            prog_acc["students_enrolled"] += val_int
            org_acc["students_enrolled"] += val_int
        elif m.metric_code == "students_completed":
            val_int = int(round(m.value))
            total_completed += val_int
            prog_acc["students_completed"] += val_int
            org_acc["students_completed"] += val_int
        elif m.metric_code == "attendance_rate":
            attendance_rates.append(m.value)
            prog_acc["_attendance_rates"].append(m.value)
            org_acc["_attendance_rates"].append(m.value)

        serialized_metrics.append({
            "id": m.id,
            "organization_id": m.organization_id,
            "organization_name": org_name,
            "program_id": m.program_id,
            "program_name": prog_name,
            "metric_code": m.metric_code,
            "value": m.value,
            "unit": m.unit,
            "as_of": iso(m.as_of),
            "source": m.source,
            "external_id": m.external_id,
        })

    avg_attendance_rate = round(sum(attendance_rates) / len(attendance_rates), 1) if attendance_rates else 0.0

    by_program = []
    for p_data in by_program_map.values():
        rates = p_data.pop("_attendance_rates")
        p_data["avg_attendance_rate"] = round(sum(rates) / len(rates), 1) if rates else 0.0
        by_program.append(p_data)

    by_organization = []
    for o_data in by_org_map.values():
        rates = o_data.pop("_attendance_rates")
        o_data["avg_attendance_rate"] = round(sum(rates) / len(rates), 1) if rates else 0.0
        by_organization.append(o_data)

    return {
        "total_cohorts": total_cohorts,
        "total_enrolled": total_enrolled,
        "total_completed": total_completed,
        "avg_attendance_rate": avg_attendance_rate,
        "by_program": by_program,
        "by_organization": by_organization,
        "metrics": serialized_metrics,
    }


def process_lms_payments_json(
    db: Session,
    user: User,
    data: Any,
) -> dict[str, Any]:
    if user.role not in ("supervisor", "administrator", "admin"):
        raise APIError("FORBIDDEN", "Доступ к загрузке выгрузок LMS разрешен только ролям supervisor и administrator.", 403)

    raw_items = []
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        for k in ("records", "items", "orders", "данные", "rows"):
            if k in data and isinstance(data[k], list):
                raw_items = data[k]
                break
        if not raw_items:
            raw_items = [data]
    else:
        raise APIError("VALIDATION_ERROR", "Неверная структура данных JSON.", 422)

    total_records = len(raw_items)
    skipped_nulls = 0
    valid_items = []

    for item in raw_items:
        if item is None or not isinstance(item, dict):
            skipped_nulls += 1
            continue
        valid_items.append(item)

    processed_count = 0
    by_prog_items: dict[str, list[dict]] = {}
    existing_learners = list(
        db.scalars(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.entity_type == "learner",
            )
        )
    )

    for item in valid_items:
        raw_ext_id = (
            item.get("Номер заявки")
            if item.get("Номер заявки") is not None
            else (
                item.get("order_id")
                if item.get("order_id") is not None
                else (item.get("id") if item.get("id") is not None else item.get("external_id"))
            )
        )
        ext_id = str(raw_ext_id).strip() if raw_ext_id is not None and str(raw_ext_id).strip() else uuid4().hex
        course_name = str(item.get("Курс") or item.get("course") or item.get("program") or "").strip()
        raw_cohort = (
            item.get("Номер потока")
            if item.get("Номер потока") is not None
            else (item.get("cohort") if item.get("cohort") is not None else item.get("stream"))
        )
        cohort = str(raw_cohort).strip() if raw_cohort is not None and str(raw_cohort).strip() else "1"

        last_name = str(item.get("Фамилия") or item.get("last_name") or item.get("surname") or "").strip()
        first_name = str(item.get("Имя") or item.get("first_name") or "").strip()
        patronymic = str(item.get("Отчество") or item.get("patronymic") or item.get("middle_name") or "").strip()
        name_parts = [p for p in (last_name, first_name, patronymic) if p]
        full_name = " ".join(name_parts) or str(item.get("full_name") or item.get("name") or item.get("ФИО") or "").strip()
        phone = str(item.get("Телефон") or item.get("phone") or item.get("тел") or "").strip()
        email = str(item.get("Email") or item.get("email") or item.get("e-mail") or item.get("почта") or "").strip()

        is_item_paid = True
        for k in ("Статус оплаты", "Оплачено", "status", "payment_status", "статус"):
            if k in item:
                st = str(item[k]).strip().lower()
                if st not in ("оплачено", "оплачен", "paid", "success", "успешно", "да", "true", "1"):
                    is_item_paid = False
                break

        prog = None
        if course_name:
            prog = db.scalar(select(Program).where(func.lower(Program.name) == course_name.lower()))
            if not prog:
                prog = db.scalar(select(Program).where(func.lower(Program.name).contains(course_name.lower())))
            if not prog:
                prog = db.get(Program, course_name)
        if not prog:
            prog = db.scalar(select(Program))

        org = None
        org_name = str(item.get("Организация") or item.get("Вуз") or item.get("organization") or "").strip()
        if org_name:
            org = db.scalar(select(Organization).where(func.lower(Organization.name) == org_name.lower()))
        if not org and prog:
            org = db.scalar(select(Organization).join(Interaction).where(Interaction.program_id == prog.id))
        if not org:
            org = db.scalar(select(Organization))

        payload = {
            **item,
            "order_id": ext_id,
            "external_id": ext_id,
            "course": course_name,
            "cohort": cohort,
            "last_name": last_name,
            "first_name": first_name,
            "patronymic": patronymic,
            "representative_name": full_name or "—",
            "representative_email": email or None,
            "representative_phone": phone or None,
            "organization_name": org_name or (org.name if org else "—"),
            "program_name": prog.name if prog else (course_name or "Не указана"),
            "matched_program_id": prog.id if prog else None,
            "matched_program_name": prog.name if prog else None,
            "matched_organization_id": org.id if org else None,
            "matched_organization_name": org.name if org else None,
        }

        # Bidirectional enrichment with existing LMS learners
        for l_inbox in existing_learners:
            l_payload = l_inbox.payload or {}
            l_email = str(l_payload.get("email") or l_inbox.external_id or "").strip().lower()
            l_phone_digits = "".join(filter(str.isdigit, str(l_payload.get("phone") or "")))
            item_phone_digits = "".join(filter(str.isdigit, str(phone or "")))

            email_match = bool(email and l_email and email.lower() == l_email)
            phone_match = bool(item_phone_digits and l_phone_digits and len(item_phone_digits) >= 10 and len(l_phone_digits) >= 10 and item_phone_digits[-10:] == l_phone_digits[-10:])

            if email_match or phone_match:
                payload["linked_learner_id"] = l_inbox.external_id
                payload["linked_learner_email"] = l_email or email
                payload["has_questionnaire"] = True
                payload["questionnaire_status"] = "completed"
                for k in ("snils", "passport_series", "passport_number", "passport_issued_by", "passport_issued_date", "education", "diploma_university"):
                    if l_payload.get(k):
                        payload[k] = l_payload[k]

                l_payload_updated = dict(l_payload)
                l_payload_updated["linked_order_id"] = ext_id
                l_payload_updated["course_name"] = course_name
                l_payload_updated["cohort"] = cohort
                l_payload_updated["payment_status"] = "paid" if is_item_paid else "pending"
                if prog:
                    l_payload_updated["matched_program_id"] = prog.id
                if org and not l_inbox.matched_organization_id:
                    l_inbox.matched_organization_id = org.id
                l_inbox.payload = l_payload_updated
                flag_modified(l_inbox, "payload")
                break

        existing_inbox = db.scalar(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.entity_type == "lms_order",
                IntegrationInbox.external_id == ext_id,
                IntegrationInbox.source_revision == cohort,
            )
        )
        if not existing_inbox:
            inbox_rec = IntegrationInbox(
                id=new_id(),
                source="lms",
                entity_type="lms_order",
                external_id=ext_id,
                source_revision=cohort,
                payload=payload,
                status="pending",
                matched_organization_id=org.id if org else None,
                received_at=utcnow(),
            )
            db.add(inbox_rec)
        else:
            existing_inbox.payload = payload
            existing_inbox.status = "pending"
            if not existing_inbox.matched_organization_id and org:
                existing_inbox.matched_organization_id = org.id
            flag_modified(existing_inbox, "payload")

        processed_count += 1

        prog_key = prog.id if prog else "default"
        if prog_key not in by_prog_items:
            by_prog_items[prog_key] = []
        by_prog_items[prog_key].append(item)

    for prog_id, p_items in by_prog_items.items():
        prog = db.get(Program, prog_id) if prog_id != "default" else db.scalar(select(Program))
        if not prog:
            continue
        org = db.scalar(select(Organization).join(Interaction).where(Interaction.program_id == prog.id)) or db.scalar(select(Organization))
        if not org:
            continue

        num_apps = len(p_items)
        num_paid = 0
        for it in p_items:
            is_paid = True
            for k in ("Статус оплаты", "Оплачено", "status", "payment_status", "статус"):
                if k in it:
                    st = str(it[k]).strip().lower()
                    if st not in ("оплачено", "оплачен", "paid", "success", "успешно", "да", "true", "1"):
                        is_paid = False
                    break
            if is_paid:
                num_paid += 1

        conv_rate = round((num_paid / num_apps * 100), 1) if num_apps > 0 else 0.0

        app_metric = db.scalar(select(LearningMetric).where(LearningMetric.source == "lms", LearningMetric.external_id == f"lms-app-{prog.id}"))
        if not app_metric:
            app_metric = LearningMetric(
                id=new_id(),
                organization_id=org.id,
                program_id=prog.id,
                metric_code="applications_count",
                value=float(num_apps),
                unit="application",
                as_of=utcnow(),
                source="lms",
                external_id=f"lms-app-{prog.id}",
                created_at=utcnow(),
            )
            db.add(app_metric)
        else:
            app_metric.value = float(num_apps)
            app_metric.as_of = utcnow()

        pay_metric = db.scalar(select(LearningMetric).where(LearningMetric.source == "lms", LearningMetric.external_id == f"lms-pay-{prog.id}"))
        if not pay_metric:
            pay_metric = LearningMetric(
                id=new_id(),
                organization_id=org.id,
                program_id=prog.id,
                metric_code="payments_count",
                value=float(num_paid),
                unit="payment",
                as_of=utcnow(),
                source="lms",
                external_id=f"lms-pay-{prog.id}",
                created_at=utcnow(),
            )
            db.add(pay_metric)
        else:
            pay_metric.value = float(num_paid)
            pay_metric.as_of = utcnow()

        conv_metric = db.scalar(select(LearningMetric).where(LearningMetric.source == "lms", LearningMetric.external_id == f"lms-conv-{prog.id}"))
        if not conv_metric:
            conv_metric = LearningMetric(
                id=new_id(),
                organization_id=org.id,
                program_id=prog.id,
                metric_code="conversion_rate",
                value=float(conv_rate),
                unit="%",
                as_of=utcnow(),
                source="lms",
                external_id=f"lms-conv-{prog.id}",
                created_at=utcnow(),
            )
            db.add(conv_metric)
        else:
            conv_metric.value = float(conv_rate)
            conv_metric.as_of = utcnow()

        enr_metric = db.scalar(select(LearningMetric).where(LearningMetric.source == "lms", LearningMetric.external_id == f"lms-enr-{prog.id}"))
        if not enr_metric:
            enr_metric = LearningMetric(
                id=new_id(),
                organization_id=org.id,
                program_id=prog.id,
                metric_code="students_enrolled",
                value=float(num_apps),
                unit="student",
                as_of=utcnow(),
                source="lms",
                external_id=f"lms-enr-{prog.id}",
                created_at=utcnow(),
            )
            db.add(enr_metric)
        else:
            enr_metric.value = float(num_apps)
            enr_metric.as_of = utcnow()

    paid_count = 0
    total_paid_amount = 0.0
    for it in valid_items:
        is_paid = True
        for k in ("Статус оплаты", "Оплачено", "status", "payment_status", "статус"):
            if k in it:
                st = str(it[k]).strip().lower()
                if st not in ("оплачено", "оплачен", "paid", "success", "успешно", "да", "true", "1"):
                    is_paid = False
                break
        if is_paid:
            paid_count += 1
            amt = it.get("Сумма") or it.get("amount") or it.get("sum") or it.get("price") or 0
            m = re.search(r"(\d+(?:[\.,]\d+)?)", str(amt).replace(" ", "").strip())
            if m:
                try:
                    total_paid_amount += float(m.group(1).replace(",", "."))
                except (ValueError, TypeError):
                    pass

    db.commit()

    return {
        "status": "success",
        "total_records": total_records,
        "processed": processed_count,
        "processed_count": processed_count,
        "skipped_nulls": skipped_nulls,
        "paid_count": paid_count,
        "total_paid_amount": total_paid_amount,
        "message": "Файл оплат LMS успешно обработан",
    }


def _match_learner_header(h: str) -> str | None:
    norm = h.strip().lower()
    if "снилс" in norm:
        return "snils"
    if "серия" in norm and "паспорт" in norm:
        return "passport_series"
    if "номер" in norm and "паспорт" in norm:
        return "passport_number"
    if "кем выдан" in norm:
        return "passport_issued_by"
    if "код подразделен" in norm:
        return "passport_subdivision_code"
    if "дата выдачи" in norm and ("паспорт" in norm or "диплом" not in norm):
        return "passport_issued_date"
    if norm in ("пол", "gender"):
        return "gender"
    if "рождени" in norm:
        return "birth_date"
    if "регион" in norm and "регистрац" in norm:
        return "registration_region"
    if any(k in norm for k in ("населенный пункт", "город")) and "регистрац" in norm:
        return "registration_city"
    if "улиц" in norm:
        return "registration_street"
    if "дом" in norm:
        return "registration_house"
    if "квартир" in norm:
        return "registration_apartment"
    if "индекс" in norm:
        return "registration_postal_code"
    if "падеж" in norm:
        if "имя" in norm:
            return "first_name_dative"
        if "фамил" in norm:
            return "last_name_dative"
        if "отчеств" in norm:
            return "patronymic_dative"
    if "образовани" in norm:
        return "education"
    if "професси" in norm:
        return "profession"
    if "учебное заведение" in norm or ("вуз" in norm and "диплом" in norm):
        return "diploma_university"
    if "фамилия" in norm and "диплом" in norm:
        return "diploma_last_name"
    if "диплом" in norm:
        if "серия" in norm:
            return "diploma_series"
        if "регистрацион" in norm:
            return "diploma_reg_number"
        if "номер" in norm:
            return "diploma_number"
        if "дата" in norm:
            return "diploma_issue_date"
    if any(e in norm for e in ("email", "e-mail", "почт", "mail")):
        return "email"
    if any(p in norm for p in ("телефон", "phone", "тел")):
        return "phone"
    if "отчеств" in norm:
        return "patronymic"
    if "фамил" in norm:
        return "last_name"
    if "имя" in norm:
        return "first_name"
    return None


def process_lms_learners_file(
    db: Session,
    user: User,
    file_bytes: bytes,
    filename: str | None = None,
) -> dict[str, Any]:
    if user.role not in ("supervisor", "administrator", "admin"):
        raise APIError("FORBIDDEN", "Доступ к загрузке анкет слушателей разрешен только ролям supervisor и administrator.", 403)

    from ..importer import parse_csv_stdlib, parse_xlsx_stdlib
    fn_lower = (filename or "").lower()
    if fn_lower.endswith(".xlsx") or file_bytes.startswith(b"PK\x03\x04"):
        raw_rows = parse_xlsx_stdlib(file_bytes)
    else:
        raw_rows = parse_csv_stdlib(file_bytes)

    if not raw_rows or len(raw_rows) < 2:
        return {
            "status": "success",
            "total_records": 0,
            "created_count": 0,
            "updated_count": 0,
            "enriched_with_payments": 0,
            "message": "Файл пуст или содержит только заголовки",
        }

    header_row = raw_rows[0]
    col_map: dict[int, str] = {}
    for idx, h in enumerate(header_row):
        m = _match_learner_header(h)
        if m:
            col_map[idx] = m

    created_count = 0
    updated_count = 0
    enriched_with_payments = 0

    existing_orders = list(
        db.scalars(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.entity_type == "lms_order",
            )
        )
    )

    for row in raw_rows[1:]:
        row_dict: dict[str, str] = {}
        for idx, val in enumerate(row):
            if idx in col_map:
                row_dict[col_map[idx]] = str(val).strip()

        if not any(row_dict.values()):
            continue

        last_name = row_dict.get("last_name", "")
        first_name = row_dict.get("first_name", "")
        patronymic = row_dict.get("patronymic", "")
        name_parts = [p for p in (last_name, first_name, patronymic) if p]
        full_name = " ".join(name_parts)

        clean_email = str(row_dict.get("email") or "").strip().lower()
        phone_raw = str(row_dict.get("phone") or "").strip()
        phone_digits = "".join(filter(str.isdigit, phone_raw))

        external_id = clean_email or phone_digits or uuid4().hex

        addr_parts = [
            row_dict.get(k, "")
            for k in (
                "registration_postal_code",
                "registration_region",
                "registration_city",
                "registration_street",
                "registration_house",
                "registration_apartment",
            )
            if row_dict.get(k)
        ]
        reg_addr = ", ".join(addr_parts)

        payload = {
            "last_name": last_name,
            "first_name": first_name,
            "patronymic": patronymic,
            "full_name": full_name,
            "email": clean_email,
            "phone": phone_digits or phone_raw,
            "gender": row_dict.get("gender", ""),
            "birth_date": row_dict.get("birth_date", ""),
            "snils": row_dict.get("snils", ""),
            "passport_series": row_dict.get("passport_series", ""),
            "passport_number": row_dict.get("passport_number", ""),
            "passport_issued_by": row_dict.get("passport_issued_by", ""),
            "passport_issued_date": row_dict.get("passport_issued_date", ""),
            "passport_subdivision_code": row_dict.get("passport_subdivision_code", ""),
            "registration_region": row_dict.get("registration_region", ""),
            "registration_city": row_dict.get("registration_city", ""),
            "registration_street": row_dict.get("registration_street", ""),
            "registration_house": row_dict.get("registration_house", ""),
            "registration_apartment": row_dict.get("registration_apartment", ""),
            "registration_postal_code": row_dict.get("registration_postal_code", ""),
            "registration_address": reg_addr,
            "first_name_dative": row_dict.get("first_name_dative", ""),
            "last_name_dative": row_dict.get("last_name_dative", ""),
            "patronymic_dative": row_dict.get("patronymic_dative", ""),
            "education": row_dict.get("education", ""),
            "profession": row_dict.get("profession", ""),
            "diploma_university": row_dict.get("diploma_university", ""),
            "diploma_last_name": row_dict.get("diploma_last_name", ""),
            "diploma_number": row_dict.get("diploma_number", ""),
            "diploma_series": row_dict.get("diploma_series", ""),
            "diploma_reg_number": row_dict.get("diploma_reg_number", ""),
            "diploma_issue_date": row_dict.get("diploma_issue_date", ""),
            "representative_name": full_name or "—",
            "representative_email": clean_email or None,
            "representative_phone": phone_digits or phone_raw or None,
            "linked_order_id": None,
            "course_name": None,
            "cohort": "1",
            "payment_status": None,
        }

        matched_org_id = None
        for o_inbox in existing_orders:
            o_payload = o_inbox.payload or {}
            o_email = str(o_payload.get("Email") or o_payload.get("email") or o_payload.get("representative_email") or "").strip().lower()
            o_phone_raw = str(o_payload.get("Телефон") or o_payload.get("phone") or o_payload.get("representative_phone") or "")
            o_phone_digits = "".join(filter(str.isdigit, o_phone_raw))

            email_match = bool(clean_email and o_email and clean_email == o_email)
            phone_match = bool(phone_digits and o_phone_digits and len(phone_digits) >= 10 and len(o_phone_digits) >= 10 and phone_digits[-10:] == o_phone_digits[-10:])

            if email_match or phone_match:
                payload["linked_order_id"] = o_inbox.external_id or o_payload.get("order_id")
                payload["course_name"] = o_payload.get("course") or o_payload.get("course_name") or o_payload.get("program_name")
                payload["cohort"] = o_inbox.source_revision or o_payload.get("cohort") or "1"
                payload["payment_status"] = "paid"
                if o_inbox.matched_organization_id:
                    matched_org_id = o_inbox.matched_organization_id
                if o_payload.get("matched_program_id"):
                    payload["matched_program_id"] = o_payload.get("matched_program_id")

                o_payload_updated = dict(o_payload)
                o_payload_updated["linked_learner_id"] = external_id
                o_payload_updated["linked_learner_email"] = clean_email
                o_payload_updated["has_questionnaire"] = True
                o_payload_updated["questionnaire_status"] = "completed"
                for k in ("snils", "passport_series", "passport_number", "passport_issued_by", "passport_issued_date", "education", "diploma_university"):
                    if payload.get(k):
                        o_payload_updated[k] = payload[k]
                o_inbox.payload = o_payload_updated
                flag_modified(o_inbox, "payload")
                enriched_with_payments += 1
                break

        existing_inbox = db.scalar(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.entity_type == "learner",
                IntegrationInbox.external_id == external_id,
                IntegrationInbox.source_revision == "1",
            )
        )
        if not existing_inbox:
            inbox_rec = IntegrationInbox(
                id=new_id(),
                source="lms",
                entity_type="learner",
                external_id=external_id,
                source_revision="1",
                payload=payload,
                status="pending",
                matched_organization_id=matched_org_id,
                received_at=utcnow(),
            )
            db.add(inbox_rec)
            created_count += 1
        else:
            existing_inbox.payload = payload
            existing_inbox.status = "pending"
            if matched_org_id and not existing_inbox.matched_organization_id:
                existing_inbox.matched_organization_id = matched_org_id
            flag_modified(existing_inbox, "payload")
            updated_count += 1

    db.commit()
    return {
        "status": "success",
        "total_records": len(raw_rows) - 1,
        "created_count": created_count,
        "updated_count": updated_count,
        "enriched_with_payments": enriched_with_payments,
        "message": "Анкеты слушателей LMS успешно загружены в шлюз интеграций",
    }
