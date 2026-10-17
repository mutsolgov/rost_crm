from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..errors import APIError
from ..models import ReportRun, User, utcnow
from ..reports_export import export_report
from ..schemas import ActivityRequest, CreatedReportRequest, JobSnapshotRequest, SnapshotRequest
from ..services import (
    activity,
    begin_command,
    check_authz_epoch,
    created_report,
    enqueue_background_job,
    finish_command,
    get_background_job_scoped,
    get_frozen_report_rows,
    iso,
    require_permission,
    snapshot,
)

router = APIRouter()


@router.post("/api/v1/reports/snapshot", tags=["reports"])
def post_snapshot(body: SnapshotRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return snapshot(db, user, body)


@router.post("/api/v1/reports/snapshot/export", tags=["reports"])
def export_snapshot(
    body: SnapshotRequest,
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    result = snapshot(db, user, body)
    return export_report(result, "snapshot", format, user, selected_columns=getattr(body, "selected_columns", None))


@router.post("/api/v1/reports/activity", tags=["reports"])
def post_activity(
    body: ActivityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return activity(db, user, body)


@router.post("/api/v1/reports/activity/export", tags=["reports"])
def export_activity(
    body: ActivityRequest,
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    result = activity(db, user, body)
    return export_report(result, "activity", format, user, selected_columns=getattr(body, "selected_columns", None))


@router.post("/api/v1/reports/created", tags=["reports"])
def post_created_report(
    body: CreatedReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return created_report(db, user, body)


@router.post("/api/v1/reports/created/export", tags=["reports"])
def export_created(
    body: CreatedReportRequest,
    format: str = Query("json"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    result = created_report(db, user, body)
    return export_report(result, "created", format, user, selected_columns=getattr(body, "selected_columns", None))


@router.post("/api/v1/jobs/reports/snapshot", status_code=202, tags=["jobs"])
def post_job_reports_snapshot(
    body: JobSnapshotRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_permission(user, "reports.read")
    raw_payload = body.model_dump(mode="json")

    saved = None
    if idempotency_key is not None:
        saved, replay = begin_command(db, user, "jobs.report_snapshot", idempotency_key, raw_payload)
        if replay is not None:
            job_id = replay.get("job_id")
            if job_id:
                response.headers["Location"] = f"/api/v1/jobs/{job_id}"
            return replay

    params = dict(raw_payload)
    if not params.get("as_of"):
        params["as_of"] = utcnow().isoformat()

    job = enqueue_background_job(db, user, kind="report_snapshot", parameters=params)
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    result = {"job_id": job.id, "status": job.status}
    if saved is not None:
        return finish_command(db, saved, result, None)
    return result


@router.get("/api/v1/jobs/{job_id}", tags=["jobs"])
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = get_background_job_scoped(db, user, job_id)
    return {
        "id": job.id,
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "result_id": job.result_id,
        "error_message": job.error_message,
        "authz_epoch": job.authz_epoch,
        "created_at": iso(job.created_at),
        "updated_at": iso(job.updated_at),
    }


@router.get("/api/v1/jobs/{job_id}/download", tags=["jobs"])
def download_job_report(
    job_id: str,
    format: str = Query("xlsx"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_permission(user, "reports.read")
    fmt = (format or "xlsx").lower()
    if fmt not in ("xlsx", "xls", "pdf", "json", "csv"):
        raise APIError("VALIDATION_ERROR", f"Неподдерживаемый формат экспорта '{format}'. Допустимы: xlsx, xls, pdf, json, csv.", 422)

    job = get_background_job_scoped(db, user, job_id)

    if not check_authz_epoch(db, job.authz_epoch):
        raise APIError("REPORT_SCOPE_CHANGED", "Область видимости пользователя изменилась.", 403)

    if job.status in ("queued", "running"):
        raise APIError("JOB_NOT_READY", "Отчет еще формируется.", 409)

    if job.status in ("failed", "cancelled"):
        raise APIError("JOB_FAILED", f"Формирование отчета завершилось с ошибкой: {job.error_message}", 400)

    if not job.result_id:
        raise APIError("NOT_FOUND", "Результат отчета не найден.", 404)

    run = db.get(ReportRun, job.result_id)
    if not run:
        raise APIError("NOT_FOUND", "Срез отчета не найден.", 404)

    rows = get_frozen_report_rows(db, job.result_id)
    params = dict(run.parameters or {})
    report_data = {
        "report_type": run.report_type,
        "type": run.report_type,
        "parameters": params,
        "generated_at": iso(run.created_at),
        "as_of": params.get("as_of", iso(run.created_at)),
        "from_date": params.get("from", ""),
        "to_date": params.get("to", ""),
        "knowledge_cutoff": iso(run.knowledge_cutoff) if run.knowledge_cutoff else "",
        "rows": rows,
        "total_interactions": len(rows),
        "total_transitions": len(rows),
        "total_created": len(rows),
    }
    selected_cols = params.get("selected_columns")
    return export_report(report_data, run.report_type, fmt, user, selected_columns=selected_cols)
