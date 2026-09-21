from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
                    metric.organization_id = org.id
                    metric.program_id = prog.id
                    metric.metric_code = metric_code
                    metric.value = val
                    metric.unit = unit
                    metric.as_of = as_of_dt
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
    if item.entity_type != "application":
        raise APIError("VALIDATION_ERROR", "Сверка поддерживается только для заявок ('application').")
    if item.status != "pending":
        raise APIError("VALIDATION_ERROR", f"Запись уже обработана (текущий статус: {item.status}).", 409)

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

        contact_id = params.get("contact_id")
        if contact_id:
            contact = db.get(OrganizationContact, contact_id)
            if not contact or contact.organization_id != org.id:
                raise APIError("VALIDATION_ERROR", "Указанный контакт не принадлежит данной организации.")
        else:
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

        should_create = params.get("create_interaction", True if "owner_id" in params else False)
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


def get_learning_metrics_summary(
    db: Session,
    user: User,
    organization_id: str | None = None,
    program_id: str | None = None,
) -> dict[str, Any]:
    require_permission(user, "reports.read")

    query = select(LearningMetric)

    if user.role == "manager":
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
    else:
        if organization_id:
            query = query.where(LearningMetric.organization_id == organization_id)

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
