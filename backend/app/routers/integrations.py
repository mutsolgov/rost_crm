import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import Settings, get_settings, get_webhook_secret
from ..db import get_db
from ..errors import APIError
from ..integrations.service import (
    get_integrations_status,
    get_learning_metrics_summary,
    list_inbox_items,
    process_lms_learners_file,
    process_lms_payments_json,
    process_webhook,
    reconcile_application,
    sync_source,
)
from ..metrics import record_webhook
from ..models import User
from .common import _extract_uploaded_file

router = APIRouter()


@router.post("/api/v1/integrations/upload/json", tags=["integrations"])
async def upload_integrations_json_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in ("supervisor", "administrator", "admin"):
        raise APIError("FORBIDDEN", "Доступ к загрузке выгрузок LMS разрешен только ролям supervisor и administrator.", 403)
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        filename, file_bytes, _ = await _extract_uploaded_file(request)
        data = None
        for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1251"):
            try:
                data = json.loads(file_bytes.decode(enc))
                break
            except Exception:
                continue
        if data is None:
            raise APIError("VALIDATION_ERROR", "Невалидный JSON файл или неподдерживаемая кодировка.", 422)
    else:
        try:
            data = await request.json()
        except Exception as e:
            raise APIError("VALIDATION_ERROR", f"Невалидный JSON запрос: {e}", 422)
    return process_lms_payments_json(db, user, data)


@router.post("/api/v1/integrations/upload/learners", tags=["integrations"])
async def upload_integrations_learners_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in ("supervisor", "administrator", "admin"):
        raise APIError("FORBIDDEN", "Доступ к загрузке анкет слушателей разрешен только ролям supervisor и administrator.", 403)
    filename, file_bytes, _ = await _extract_uploaded_file(request)
    return process_lms_learners_file(db, user, file_bytes, filename=filename)


@router.get("/api/v1/integrations/status", tags=["integrations"])
def integrations_status_endpoint(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    config: Settings = Depends(get_settings),
):
    return get_integrations_status(db, user, config)


@router.post("/api/v1/integrations/sync/{source}", tags=["integrations"])
def integrations_sync_endpoint(
    source: str,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    config: Settings = Depends(get_settings),
):
    return sync_source(db, user, source, config, idempotency_key=idempotency_key)


@router.get("/api/v1/integrations/inbox", tags=["integrations"])
def integrations_inbox_endpoint(
    source: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    exclude_technical: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return list_inbox_items(
        db,
        user,
        source=source,
        status=status,
        page=page,
        page_size=page_size,
        exclude_technical=exclude_technical,
    )


@router.post("/api/v1/integrations/inbox/{id}/resolve", tags=["integrations"])
async def integrations_inbox_resolve_endpoint(
    id: str,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not idempotency_key or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise APIError("VALIDATION_ERROR", "Тело запроса должно быть JSON объектом.")
    action = body.get("action")
    if not action:
        raise APIError("VALIDATION_ERROR", "Поле 'action' обязательно ('link_existing', 'create_new', 'reject').")
    params = body.get("params")
    if not isinstance(params, dict):
        params = {}
    for k, v in body.items():
        if k not in ("action", "params") and k not in params:
            params[k] = v
    return reconcile_application(
        db, user, inbox_id=id, action=action, params=params, idempotency_key=idempotency_key
    )


@router.get("/api/v1/integrations/metrics", tags=["integrations"])
def integrations_metrics_endpoint(
    organization_id: str | None = Query(None),
    program_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return get_learning_metrics_summary(db, user, organization_id=organization_id, program_id=program_id)


@router.post("/api/v1/webhooks/{source}", tags=["webhooks"])
async def webhook_endpoint(
    source: str,
    request: Request,
    db: Session = Depends(get_db),
    config: Settings = Depends(get_settings),
):
    src = (source or "").strip().lower()
    if src not in {"lms", "website"}:
        record_webhook(src or "unknown", "invalid_source")
        raise APIError("VALIDATION_ERROR", f"Неподдерживаемый источник вебхука: '{source}'. Допустимые: 'lms', 'website'", status=400)

    secret = get_webhook_secret(src, config)
    body_bytes = await request.body()

    # Check authentication headers
    sig_header = request.headers.get("x-signature-sha256") or request.headers.get("x-hub-signature-256")
    secret_header = request.headers.get("x-webhook-secret")

    authenticated = False

    if secret_header:
        if hmac.compare_digest(secret_header.strip(), secret):
            authenticated = True

    if not authenticated and sig_header:
        cleaned_sig = sig_header.strip()
        if cleaned_sig.lower().startswith("sha256="):
            cleaned_sig = cleaned_sig[7:].strip()
        expected_hex = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(cleaned_sig.lower(), expected_hex.lower()):
            authenticated = True

    if not authenticated:
        record_webhook(src, "unauthorized")
        raise APIError("UNAUTHORIZED", "Invalid webhook signature or secret", status=401)

    if not body_bytes or not body_bytes.strip():
        record_webhook(src, "invalid_payload")
        raise APIError("VALIDATION_ERROR", "Empty webhook payload", status=400)

    try:
        payload_data = json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        record_webhook(src, "invalid_json")
        raise APIError("VALIDATION_ERROR", f"Invalid JSON payload: {exc}", status=400)

    try:
        result = process_webhook(db, src, payload_data)
        record_webhook(src, "processed")
        return result
    except Exception:
        record_webhook(src, "failed")
        raise
