from __future__ import annotations

import email
import email.policy
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from .auth import current_user
from .config import Settings, get_settings
from .db import get_db, get_engine
from .errors import APIError, install_error_handlers
from .files import attachment_dict, get_attachment_or_404, list_interaction_attachments, save_attachment
from .importer import commit_organizations_import, parse_tabular_file, preview_organizations_import
from .integrations.service import (
    get_integrations_status,
    get_learning_metrics_summary,
    list_inbox_items,
    reconcile_application,
    sync_source,
)
from .models import User
from .reports_export import export_report
from .schemas import (
    ActivityRequest,
    AssignmentCommand,
    CommentCommand,
    CreatedReportRequest,
    InteractionCreate,
    InteractionUpdate,
    SnapshotRequest,
    TransitionCommand,
    WorkflowMigrateRequest,
)
from .services import (
    activity,
    add_comment,
    assign,
    catalogs,
    commit_workflow_migration,
    create_interaction,
    created_report,
    dashboard,
    detail,
    list_interactions,
    preview_workflow_migration,
    scoped_interaction,
    snapshot,
    transition,
    update_interaction,
)
from .workflow import get_workflow as get_workflow_by_version



def _user_dict(user: User, auth_mode: str) -> dict:
    from .services import permissions

    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "team_id": user.team_id,
        "permissions": permissions(user),
        "auth_mode": auth_mode,
    }


async def _extract_uploaded_file(request: Request) -> tuple[str, bytes, str | None]:
    cl_header = request.headers.get("content-length")
    if cl_header:
        try:
            if int(cl_header) > 26_214_400:
                raise APIError("FILE_TOO_LARGE", "Размер файла превышает 25 МБ.", 413)
        except ValueError:
            pass

    body = await request.body()
    if len(body) > 26_214_400:
        raise APIError("FILE_TOO_LARGE", "Размер файла превышает 25 МБ.", 413)
    if not body:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Передан пустой файл.", 422)

    ct = request.headers.get("content-type", "")
    if "multipart/form-data" in ct:
        msg = email.message_from_bytes(f"Content-Type: {ct}\r\n\r\n".encode("latin1") + body, policy=email.policy.default)
        for part in msg.iter_parts():
            fn = part.get_filename()
            if fn:
                payload = part.get_payload(decode=True)
                return fn, payload or b"", part.get_content_type()
        for part in msg.iter_parts():
            if part.get_param("name", header="content-disposition") == "file":
                fn = part.get_filename() or "upload.bin"
                payload = part.get_payload(decode=True)
                return fn, payload or b"", part.get_content_type()
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Файл не найден в multipart форме.", 422)
    else:
        cd = request.headers.get("content-disposition", "")
        fn = None
        if "filename=" in cd:
            fn = cd.split("filename=")[-1].strip('"\'; ')
        fn = fn or request.headers.get("x-file-name") or request.query_params.get("filename") or "upload.bin"
        return fn, body, ct or None


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    config.validate()
    engine = get_engine(config.database_url)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="ИТ Школа · Партнёры API",
        version="0.1.0",
        description="API первого рабочего среза CRM взаимодействий с образовательными организациями.",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.engine = engine
    app.state.session_factory = factory
    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - readiness must not expose DB details
            raise APIError("NOT_READY", "База данных недоступна.", 503) from exc
        return {"status": "ok", "database": "ok"}

    @app.get("/api/v1/config", tags=["auth"])
    def public_config(db: Session = Depends(get_db)):
        result = {
            "auth_mode": config.auth_mode,
            "oidc": None,
            "demo_users": [],
        }
        if config.auth_mode == "oidc":
            result["oidc"] = {
                "url": config.oidc_url,
                "realm": config.oidc_realm,
                "client_id": config.oidc_client_id,
            }
        else:
            result["demo_users"] = [
                {"id": user.id, "name": user.name, "role": user.role}
                for user in db.scalars(select(User).where(User.active.is_(True)).order_by(User.name))
            ]
        return result

    @app.get("/api/v1/me", tags=["auth"])
    def me(user: User = Depends(current_user)):
        return _user_dict(user, config.auth_mode)

    @app.get("/api/v1/catalogs", tags=["reference"])
    def get_catalogs(db: Session = Depends(get_db), user: User = Depends(current_user)):
        return catalogs(db, user)

    @app.get("/api/v1/workflow", tags=["reference"])
    def get_workflow(version: int = Query(1, ge=1), user: User = Depends(current_user)):
        # Keep the public shape intentionally declarative; server-side transition checks use the same document.
        try:
            wf = get_workflow_by_version(version)
        except KeyError:
            raise APIError("NOT_FOUND", f"Версия workflow {version} не найдена.", 404)
        return {
            "schema_version": wf["schema_version"],
            "template_code": wf["template_code"],
            "version": wf["version"],
            "name": wf["name"],
            "initial_state": wf["initial_state"],
            "states": wf["states"],
            "transitions": wf["transitions"],
        }

    @app.post("/api/v1/workflow/migrate/preview", tags=["workflow"])
    def post_workflow_migrate_preview(
        body: WorkflowMigrateRequest,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return preview_workflow_migration(
            db, user, body.from_version, body.to_version, body.status_mapping
        )

    @app.post("/api/v1/workflow/migrate/commit", tags=["workflow"])
    def post_workflow_migrate_commit(
        body: WorkflowMigrateRequest,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return commit_workflow_migration(
            db, user, body.from_version, body.to_version, body.status_mapping, idempotency_key
        )

    @app.get("/api/v1/interactions", tags=["interactions"])
    def get_interactions(
        q: str | None = None,
        organization_id: str | None = None,
        program_id: str | None = None,
        product_id: str | None = None,
        owner_id: str | None = None,
        state: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=100),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return list_interactions(db, user, q, organization_id, program_id, product_id, owner_id, state, page, page_size)

    @app.get("/api/v1/interactions/{interaction_id}", tags=["interactions"])
    def get_interaction(interaction_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        return detail(db, user, interaction_id)

    @app.patch("/api/v1/interactions/{interaction_id}", tags=["interactions"])
    def patch_interaction(
        interaction_id: str,
        body: InteractionUpdate,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return update_interaction(db, user, interaction_id, body, idempotency_key)

    @app.post("/api/v1/interactions", status_code=201, tags=["interactions"])
    def post_interaction(
        body: InteractionCreate,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return create_interaction(db, user, body, idempotency_key)

    @app.post("/api/v1/interactions/{interaction_id}/transitions", tags=["interactions"])
    def post_transition(
        interaction_id: str,
        body: TransitionCommand,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return transition(db, user, interaction_id, body, idempotency_key)

    @app.post("/api/v1/interactions/{interaction_id}/comments", status_code=201, tags=["interactions"])
    def post_comment(
        interaction_id: str,
        body: CommentCommand,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return add_comment(db, user, interaction_id, body, idempotency_key)

    @app.post("/api/v1/interactions/{interaction_id}/assignments", tags=["interactions"])
    def post_assignment(
        interaction_id: str,
        body: AssignmentCommand,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return assign(db, user, interaction_id, body, idempotency_key)

    @app.get("/api/v1/dashboard", tags=["dashboard"])
    def get_dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
        return dashboard(db, user)

    @app.post("/api/v1/interactions/{interaction_id}/attachments", status_code=201, tags=["attachments"])
    async def upload_attachment(
        interaction_id: str,
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        scoped_interaction(db, user, interaction_id)
        filename, file_bytes, content_type = await _extract_uploaded_file(request)
        att = save_attachment(
            db,
            user,
            interaction_id,
            filename,
            file_bytes,
            storage_dir=config.storage_dir,
            content_type_header=content_type,
        )
        db.commit()
        return attachment_dict(att)

    @app.get("/api/v1/interactions/{interaction_id}/attachments", tags=["attachments"])
    def get_attachments(
        interaction_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        attachments = list_interaction_attachments(db, user, interaction_id)
        return [attachment_dict(a) for a in attachments]

    @app.get("/api/v1/interactions/{interaction_id}/attachments/{attachment_id}/download", tags=["attachments"])
    def download_attachment(
        interaction_id: str,
        attachment_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        att = get_attachment_or_404(db, user, interaction_id, attachment_id)
        return FileResponse(
            path=att.file_path,
            media_type=att.content_type,
            filename=att.file_name,
        )

    @app.post("/api/v1/reports/snapshot", tags=["reports"])
    def post_snapshot(body: SnapshotRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
        return snapshot(db, user, body)

    @app.post("/api/v1/reports/snapshot/export", tags=["reports"])
    def export_snapshot(
        body: SnapshotRequest,
        format: str = Query("json"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        result = snapshot(db, user, body)
        return export_report(result, "snapshot", format, user)

    @app.post("/api/v1/reports/activity", tags=["reports"])
    def post_activity(
        body: ActivityRequest,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return activity(db, user, body)

    @app.post("/api/v1/reports/activity/export", tags=["reports"])
    def export_activity(
        body: ActivityRequest,
        format: str = Query("json"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        result = activity(db, user, body)
        return export_report(result, "activity", format, user)

    @app.post("/api/v1/reports/created", tags=["reports"])
    def post_created_report(
        body: CreatedReportRequest,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return created_report(db, user, body)

    @app.post("/api/v1/reports/created/export", tags=["reports"])
    def export_created(
        body: CreatedReportRequest,
        format: str = Query("json"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        result = created_report(db, user, body)
        return export_report(result, "created", format, user)

    @app.post("/api/v1/imports/organizations/preview", tags=["imports"])
    async def import_organizations_preview(
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        filename, file_bytes, _ = await _extract_uploaded_file(request)
        return preview_organizations_import(db, user, file_bytes, filename)

    @app.post("/api/v1/imports/organizations/commit", tags=["imports"])
    async def import_organizations_commit(
        request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            filename, file_bytes, _ = await _extract_uploaded_file(request)
            parsed_rows = parse_tabular_file(file_bytes, filename)
            return commit_organizations_import(db, user, parsed_rows, idempotency_key)
        try:
            body = await request.json()
        except Exception:
            body = {}
        rows = body.get("rows", []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
        return commit_organizations_import(db, user, rows, idempotency_key)

    @app.get("/api/v1/integrations/status", tags=["integrations"])
    def integrations_status_endpoint(
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
        config: Settings = Depends(get_settings),
    ):
        return get_integrations_status(db, user, config)

    @app.post("/api/v1/integrations/sync/{source}", tags=["integrations"])
    def integrations_sync_endpoint(
        source: str,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
        config: Settings = Depends(get_settings),
    ):
        return sync_source(db, user, source, config, idempotency_key=idempotency_key)

    @app.get("/api/v1/integrations/inbox", tags=["integrations"])
    def integrations_inbox_endpoint(
        source: str | None = Query(None),
        status: str | None = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return list_inbox_items(db, user, source=source, status=status, page=page, page_size=page_size)

    @app.post("/api/v1/integrations/inbox/{id}/resolve", tags=["integrations"])
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

    @app.get("/api/v1/integrations/metrics", tags=["integrations"])
    def integrations_metrics_endpoint(
        organization_id: str | None = Query(None),
        program_id: str | None = Query(None),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return get_learning_metrics_summary(db, user, organization_id=organization_id, program_id=program_id)

    return app


app = create_app()
