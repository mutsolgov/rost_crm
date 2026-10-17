import hashlib

import anyio.to_thread
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import get_settings
from ..db import get_db
from ..errors import APIError
from ..files import delete_attachment, get_attachment_or_404, list_interaction_attachments, save_attachment
from ..models import User
from ..schemas import (
    AssignmentCommand,
    CommentCommand,
    DeliveryCreate,
    InteractionCreate,
    InteractionUpdate,
    TransitionCommand,
)
from ..services import (
    add_comment,
    assign,
    attachment_dict,
    begin_command,
    cas,
    create_delivery,
    create_interaction,
    dashboard,
    detail,
    finish_command,
    get_interaction_deliveries,
    list_interactions,
    require_permission,
    scoped_interaction,
    transition,
    update_interaction,
)
from .common import _extract_uploaded_file_and_revision

router = APIRouter()


@router.get("/api/v1/interactions", tags=["interactions"])
def get_interactions(
    q: str | None = None,
    organization_id: str | None = None,
    direction_id: str | None = None,
    program_id: str | None = None,
    product_id: str | None = None,
    owner_id: str | None = None,
    state: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return list_interactions(
        db, user, q, organization_id, program_id, product_id, owner_id, state, page, page_size, direction_id=direction_id
    )


@router.get("/api/v1/interactions/{interaction_id}", tags=["interactions"])
def get_interaction(interaction_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return detail(db, user, interaction_id)


@router.patch("/api/v1/interactions/{interaction_id}", tags=["interactions"])
def patch_interaction(
    interaction_id: str,
    body: InteractionUpdate,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return update_interaction(db, user, interaction_id, body, idempotency_key)


@router.post("/api/v1/interactions", status_code=201, tags=["interactions"])
def post_interaction(
    body: InteractionCreate,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return create_interaction(db, user, body, idempotency_key)


@router.post("/api/v1/interactions/{interaction_id}/transitions", tags=["interactions"])
def post_transition(
    interaction_id: str,
    body: TransitionCommand,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return transition(db, user, interaction_id, body, idempotency_key)


@router.post("/api/v1/interactions/{interaction_id}/comments", status_code=201, tags=["interactions"])
def post_comment(
    interaction_id: str,
    body: CommentCommand,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return add_comment(db, user, interaction_id, body, idempotency_key)


@router.post("/api/v1/interactions/{interaction_id}/assignments", tags=["interactions"])
def post_assignment(
    interaction_id: str,
    body: AssignmentCommand,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return assign(db, user, interaction_id, body, idempotency_key)


@router.get("/api/v1/interactions/{interaction_id}/deliveries", tags=["deliveries"])
def get_deliveries_endpoint(
    interaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return get_interaction_deliveries(db, user, interaction_id)


@router.post("/api/v1/interactions/{interaction_id}/deliveries", status_code=201, tags=["deliveries"])
def post_delivery_endpoint(
    interaction_id: str,
    body: DeliveryCreate,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return create_delivery(db, user, interaction_id, body, idempotency_key)


@router.get("/api/v1/dashboard", tags=["dashboard"])
def get_dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return dashboard(db, user)


@router.post("/api/v1/interactions/{interaction_id}/attachments", status_code=201, tags=["attachments"])
async def upload_attachment(
    interaction_id: str,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    item = scoped_interaction(db, user, interaction_id)
    require_permission(user, "interactions.write")
    filename, file_bytes, content_type, exp_rev = await _extract_uploaded_file_and_revision(request)

    saved = None
    if idempotency_key is not None:
        payload_meta = {
            "filename": filename,
            "size": len(file_bytes),
            "checksum": hashlib.sha256(file_bytes).hexdigest(),
            "expected_revision": exp_rev,
        }
        saved, replay = begin_command(db, user, f"attachment:{item.id}", idempotency_key, payload_meta)
        if replay is not None:
            return replay

    if exp_rev is not None:
        cas(db, item, exp_rev)

    cfg = getattr(request.app.state, "settings", None) or get_settings()
    att = await anyio.to_thread.run_sync(
        lambda: save_attachment(
            db,
            user,
            interaction_id,
            filename,
            file_bytes,
            storage_dir=cfg.storage_dir,
            content_type_header=content_type,
            settings=cfg,
        )
    )
    result = attachment_dict(att)
    if saved is not None:
        return finish_command(db, saved, result, item.id)

    db.commit()
    return result


@router.get("/api/v1/interactions/{interaction_id}/attachments", tags=["attachments"])
def get_attachments(
    interaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    attachments = list_interaction_attachments(db, user, interaction_id)
    return [attachment_dict(a) for a in attachments]


@router.get("/api/v1/interactions/{interaction_id}/attachments/{attachment_id}/download", tags=["attachments"])
def download_attachment(
    interaction_id: str,
    attachment_id: str,
    disposition: str = Query("attachment", pattern="^(attachment|inline)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    att = get_attachment_or_404(db, user, interaction_id, attachment_id)
    return FileResponse(
        path=att.file_path,
        media_type=att.content_type,
        filename=att.file_name,
        content_disposition_type=disposition,
    )


@router.delete("/api/v1/interactions/{interaction_id}/attachments/{attachment_id}", tags=["attachments"])
def remove_attachment(
    interaction_id: str,
    attachment_id: str,
    request: Request,
    expected_revision: int | None = Query(None, ge=1),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    exp_rev = expected_revision
    if exp_rev is None:
        raw_rev = (
            request.query_params.get("expected-revision")
            or request.headers.get("expected_revision")
            or request.headers.get("expected-revision")
        )
        if raw_rev is not None and raw_rev != "":
            if not raw_rev.isdigit():
                raise APIError("VALIDATION_ERROR", "Параметр expected_revision должен быть целым числом.", 422)
            exp_rev = int(raw_rev)
            if exp_rev < 1:
                raise APIError("VALIDATION_ERROR", "Параметр expected_revision должен быть >= 1.", 422)

    saved = None
    if idempotency_key is not None:
        payload_meta = {
            "interaction_id": interaction_id,
            "attachment_id": attachment_id,
            "expected_revision": exp_rev,
        }
        saved, replay = begin_command(
            db,
            user,
            f"attachment_delete:{interaction_id}:{attachment_id}",
            idempotency_key,
            payload_meta,
        )
        if replay is not None:
            return replay

    result = delete_attachment(
        db,
        user,
        interaction_id=interaction_id,
        attachment_id=attachment_id,
        expected_revision=exp_rev,
    )

    if saved is not None:
        return finish_command(db, saved, result, interaction_id)

    db.commit()
    return result
