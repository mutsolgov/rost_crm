import hashlib
import json
import sys
from collections import Counter
from datetime import date, datetime

from sqlalchemy import false, select, update
from sqlalchemy.orm import Session

from ..errors import APIError
from ..models import (
    BackgroundJob,
    Direction,
    Interaction,
    InteractionEvent,
    Organization,
    Product,
    Program,
    ReportRow,
    ReportRun,
    TransactionalOutbox,
    User,
    new_id,
    utcnow,
)
from ..workflow import STATES
from .common import _json_safe, aware, iso
from .interactions import validate_filters
from .rbac import check_authz_epoch, get_authz_epoch, require_permission, scope_clause


def _resolve_direction_name(db: Session, program_id: str | None, cache: dict | None = None) -> str | None:
    if not program_id:
        return None
    if cache is not None and program_id in cache:
        return cache[program_id]
    prog = db.get(Program, program_id)
    dir_name = None
    if prog and prog.direction_id:
        dir_obj = db.get(Direction, prog.direction_id)
        if dir_obj:
            dir_name = dir_obj.name
    if cache is not None:
        cache[program_id] = dir_name
    return dir_name



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
    for evt in events:
        if evt.type in ("created", "initial_state"):
            created.add(evt.interaction_id)
        if evt.payload.get("snapshot"):
            latest[evt.interaction_id] = evt.payload["snapshot"]
    dir_cache: dict[str, str | None] = {}
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
            "title", "organization_name", "direction_name", "program_name", "product_name", "state", "state_name", "owner_id", "owner_name", "cycle_label")}}
        if not row.get("direction_name") and data.get("program_id"):
            row["direction_name"] = _resolve_direction_name(db, data.get("program_id"), dir_cache)
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

    dir_cache: dict[str, str | None] = {}
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

        prog_id = snap.get("program_id") or (inter.program_id if inter else None)
        prod_id = snap.get("product_id") or (inter.product_id if inter else None)

        program_name = snap.get("program_name")
        if not program_name and prog_id:
            prog_obj = db.get(Program, prog_id)
            program_name = prog_obj.name if prog_obj else None

        product_name = snap.get("product_name")
        if not product_name and prod_id:
            prod_obj = db.get(Product, prod_id)
            product_name = prod_obj.name if prod_obj else None

        direction_name = snap.get("direction_name") or _resolve_direction_name(db, prog_id, dir_cache)

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
            "direction_name": direction_name,
            "program_name": program_name,
            "product_name": product_name,
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

    dir_cache: dict[str, str | None] = {}
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

        prog_id = snap.get("program_id")
        if not prog_id:
            inter = db.get(Interaction, ev.interaction_id)
            prog_id = inter.program_id if inter else None
        direction_name = snap.get("direction_name") or _resolve_direction_name(db, prog_id, dir_cache)

        state_code = snap.get("state") or st
        state_name = snap.get("state_name") or (STATES.get(state_code, {}).get("name") if state_code else None)

        rows.append({
            "interaction_id": ev.interaction_id,
            "title": snap.get("title"),
            "organization_id": snap.get("organization_id"),
            "organization_name": snap.get("organization_name"),
            "program_name": snap.get("program_name"),
            "product_name": snap.get("product_name"),
            "direction_name": direction_name,
            "owner_id": snap.get("owner_id"),
            "owner_name": snap.get("owner_name"),
            "state": state_code,
            "state_name": state_name,
            "cycle_label": snap.get("cycle_label"),
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
            from ..schemas import SnapshotRequest

            params = dict(job.parameters or {})
            if "as_of" not in params or not params["as_of"]:
                params["as_of"] = utcnow().isoformat()
            req = SnapshotRequest(**params)

            # Resolve snapshot dynamically via services facade for monkeypatch compatibility
            services_mod = sys.modules.get("app.services")
            snapshot_fn = getattr(services_mod, "snapshot", snapshot) if services_mod is not None else snapshot
            report_result = snapshot_fn(db, requester, req)

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
