from __future__ import annotations

import email
import email.message
import email.policy
import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from .auth import current_user
from .config import Settings, get_settings, get_webhook_secret
from .db import get_db, get_engine
from .errors import APIError, install_error_handlers
from .files import (
    attachment_dict,
    delete_attachment,
    get_attachment_or_404,
    list_interaction_attachments,
    save_attachment,
)
from .importer import commit_organizations_import, parse_tabular_file, preview_organizations_import
from .integrations.service import (
    get_integrations_status,
    get_learning_metrics_summary,
    list_inbox_items,
    process_lms_payments_json,
    process_lms_learners_file,
    process_webhook,
    reconcile_application,
    sync_source,
)
from .models import BackgroundJob, Organization, ReportRow, ReportRun, User, WorkflowVersion, new_id, utcnow
from .reports_export import export_report
from .schemas import (
    ActivityRequest,
    AssignmentCommand,
    CommentCommand,
    CreatedReportRequest,
    DeliveryCreate,
    InteractionCreate,
    InteractionUpdate,
    JobSnapshotRequest,
    OrganizationPatch,
    SnapshotRequest,
    TransitionCommand,
    WorkflowMigrateRequest,
    WorkflowVersionCreate,
)
from .services import (
    activity,
    add_comment,
    assign,
    begin_command,
    cas,
    catalogs,
    check_authz_epoch,
    commit_workflow_migration,
    create_delivery,
    create_interaction,
    created_report,
    dashboard,
    detail,
    enqueue_background_job,
    finish_command,
    get_background_job_scoped,
    get_frozen_report_rows,
    get_interaction_deliveries,
    iso,
    list_interactions,
    preview_workflow_migration,
    process_background_job,
    require_permission,
    scoped_interaction,
    set_organization_access,
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


async def _extract_uploaded_file_and_revision(
    request: Request,
) -> tuple[str, bytes, str | None, int | None]:
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

    exp_rev_raw: str | None = (
        request.query_params.get("expected_revision")
        or request.query_params.get("expected-revision")
        or request.headers.get("expected_revision")
        or request.headers.get("expected-revision")
        or request.headers.get("x-expected-revision")
    )

    ct = request.headers.get("content-type", "")
    if "multipart/form-data" in ct:
        msg = email.message_from_bytes(f"Content-Type: {ct}\r\n\r\n".encode("utf-8") + body, policy=email.policy.default)
        parts = list(msg.iter_parts())
        for part in parts:
            if part.get_param("name", header="content-disposition") in ("expected_revision", "expected-revision"):
                rev_payload = part.get_payload(decode=True) or part.get_payload()
                part_val = ""
                if isinstance(rev_payload, bytes):
                    part_val = rev_payload.decode("utf-8", errors="replace").strip()
                elif isinstance(rev_payload, str):
                    part_val = rev_payload.strip()
                if part_val:
                    exp_rev_raw = part_val

        file_part = None
        for part in parts:
            if part.get_param("name", header="content-disposition") in ("expected_revision", "expected-revision"):
                continue
            fn = part.get_filename()
            if fn:
                payload = part.get_payload(decode=True)
                file_part = (fn, payload or b"", part.get_content_type())
                break
        if not file_part:
            for part in parts:
                if part.get_param("name", header="content-disposition") == "file":
                    fn = part.get_filename() or "upload.bin"
                    payload = part.get_payload(decode=True)
                    file_part = (fn, payload or b"", part.get_content_type())
                    break
        if not file_part:
            raise APIError("FILE_TYPE_NOT_ALLOWED", "Файл не найден в multipart форме.", 422)
        fn, payload, content_type = file_part
    else:
        cd = request.headers.get("content-disposition", "")
        fn = None
        if cd:
            cd_msg = email.message.EmailMessage()
            cd_msg["content-disposition"] = cd
            fn = cd_msg.get_filename()
        fn = fn or request.headers.get("x-file-name") or request.query_params.get("filename") or "upload.bin"
        payload, content_type = body, ct or None

    exp_rev: int | None = None
    if exp_rev_raw is not None:
        val = str(exp_rev_raw).strip()
        if val != "":
            try:
                exp_rev = int(val)
            except (ValueError, TypeError):
                raise APIError("VALIDATION_ERROR", "Параметр expected_revision должен быть целым числом.", 422)
            if exp_rev < 1:
                raise APIError("VALIDATION_ERROR", "Параметр expected_revision должен быть >= 1.", 422)

    return fn, payload, content_type, exp_rev


async def _extract_uploaded_file(request: Request) -> tuple[str, bytes, str | None]:
    fn, payload, ct, _ = await _extract_uploaded_file_and_revision(request)
    return fn, payload, ct


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    config.validate()
    engine = get_engine(config.database_url)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import anyio
        import anyio.to_thread
        anyio.to_thread.current_default_thread_limiter().total_tokens = 120

        try:
            from .seed import ensure_schema_columns
            ensure_schema_columns(engine)
        except Exception:
            pass

        try:
            with factory() as init_db:
                from .workflow import load_workflow_versions
                load_workflow_versions(init_db)
        except Exception:
            pass


        worker_enabled = os.environ.get("BACKGROUND_WORKER_ENABLED", "false").lower() in ("true", "1", "yes")
        if worker_enabled:
            async def _worker_loop():
                while True:
                    try:
                        def _tick():
                            with factory() as db:
                                job = db.scalars(
                                    select(BackgroundJob).where(BackgroundJob.status == "queued").order_by(BackgroundJob.created_at.asc()).limit(1)
                                ).first()
                                if job:
                                    process_background_job(db, job.id)
                        await anyio.to_thread.run_sync(_tick)
                    except Exception:
                        pass
                    await anyio.sleep(1.0)

            async with anyio.create_task_group() as tg:
                tg.start_soon(_worker_loop)
                yield
                tg.cancel_scope.cancel()
        else:
            yield

    app = FastAPI(
        title="ИТ Школа Ростелекома — CRM API",
        version="1.0.0",
        description="""### CRM «ИТ Школа Ростелекома» — Сервисный API

API для управления взаимодействиями с образовательными организациями (вузами, колледжами) 
по внедрению отечественного программного обеспечения в рамках инициатив ПАО «Ростелеком».

#### Реализованные ключевые возможности:
- **Управление воронкой взаимодействий:** 15 этапов жизненного цикла (13 рабочих + 2 терминальных), оптимистический контроль версий CAS (`expected_revision`), устранение дедлока D02.
- **Интеграционные контуры:** забор данных по REST API и Webhook из LMS Zion (`/api/v1/metrics`, `/api/v1/deliveries`) и Веб-сайта Laravel (`/api/v1/applications`) с очередью сверки Reconciliation Inbox.
- **Аналитический модуль и отчёты:** темпоральные срезы (Snapshot на дату, Activity по переходам, Created по динамике) с экспортом в форматы XLSX, XLS, PDF, CSV, JSON.
- **Двухфазный импорт справочников:** Preview (Dry-Run) и Commit из файлов Excel без сторонних библиотек.
- **Безопасность:** 152-ФЗ Zero-Oracle сокрытие (HTTP 404), In-Memory JWT, побайтовая проверка magic bytes и ClamAV.

#### Перечень использованных библиотек и компонентов (ТЗ п. 6.2):
- **Backend:** Python 3.12+, FastAPI (MIT), Uvicorn (BSD-3), SQLAlchemy 2.0 (MIT), Alembic (MIT), psycopg 3 (LGPL-3), PyJWT (MIT), httpx (BSD-3), AnyIO (MIT).
- **Frontend:** React 19 (MIT), TypeScript (Apache-2.0), Vite (MIT), Ростелеком Gen2 Design Tokens (Atomaro).
- **Инфраструктура:** PostgreSQL 16 (PostgreSQL License), Keycloak 26 (Apache-2.0), Nginx 1.27 (2-clause BSD), ClamAV (GPL-2.0), Redis 7 (BSD-3).
""",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.engine = engine
    app.state.session_factory = factory
    install_error_handlers(app)

    repo_root = Path(__file__).resolve().parents[2]
    frontend_screenshots = repo_root / "frontend" / "public" / "docs" / "screenshots"
    docs_screenshots = repo_root / "docs" / "screenshots"
    screenshots_target = frontend_screenshots if frontend_screenshots.exists() else docs_screenshots
    if screenshots_target.exists():
        app.mount("/docs/screenshots", StaticFiles(directory=str(screenshots_target)), name="screenshots")

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

    @app.patch("/api/v1/organizations/{organization_id}", tags=["catalogs"])
    def patch_organization(
        organization_id: str,
        body: OrganizationPatch,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        from .services import permissions
        user_perms = permissions(user)
        if user.role not in ("supervisor", "administrator") and "organizations.create" not in user_perms and "interactions.assign" not in user_perms:
            raise APIError("FORBIDDEN", "Недостаточно прав для назначения ответственного за организацию.", 403)

        org = db.get(Organization, organization_id)
        if not org:
            raise APIError("NOT_FOUND", "Организация не найдена.", 404)

        if body.owner_id is not None:
            target = db.get(User, body.owner_id)
            if not target or not target.active or target.role != "manager":
                raise APIError("VALIDATION_ERROR", "Указанный ответственный должен быть активным менеджером.", 422)
            if user.role == "supervisor" and target.team_id != user.team_id:
                raise APIError("FORBIDDEN", "Руководитель может назначать только менеджеров своей команды.", 403)
            org.owner_id = target.id
            set_organization_access(db, target.id, org.id, can_create=True, read_all=True)
        else:
            org.owner_id = None

        db.commit()
        db.refresh(org)
        return {"id": org.id, "name": org.name, "type": org.type, "owner_id": org.owner_id}

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
            db, user, body.from_version, body.to_version, body.status_mapping, idempotency_key, getattr(body, "expected_card_revisions", None)
        )

    @app.get("/api/v1/workflow/versions", tags=["workflow"])
    def get_workflow_versions(
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        versions = list(db.scalars(select(WorkflowVersion).order_by(WorkflowVersion.version.asc())).all())
        return [
            {
                "version": v.version,
                "name": v.name,
                "description": v.description,
                "is_published": getattr(v, "is_published", False),
                "created_at": iso(v.created_at),
            }
            for v in versions
        ]

    @app.post("/api/v1/workflow/versions", status_code=201, tags=["workflow"])
    def create_workflow_version(
        body: WorkflowVersionCreate,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        if user.role != "administrator":
            raise APIError("FORBIDDEN", "Только администратор может создавать версии workflow.", 403)

        existing = db.scalars(select(WorkflowVersion).where(WorkflowVersion.version == body.version)).first()
        if existing:
            raise APIError("CONFLICT", f"Версия workflow {body.version} уже существует.", 409)

        wv = WorkflowVersion(
            version=body.version,
            name=body.name,
            description=body.description,
            definition=body.definition,
            is_published=False,
            created_at=utcnow(),
        )
        db.add(wv)
        db.commit()
        db.refresh(wv)
        return {
            "version": wv.version,
            "name": wv.name,
            "description": wv.description,
            "is_published": wv.is_published,
            "created_at": iso(wv.created_at),
        }

    @app.post("/api/v1/workflow/versions/{version}/publish", tags=["workflow"])
    def publish_workflow_version(
        version: int,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        if user.role != "administrator":
            raise APIError("FORBIDDEN", "Только администратор может публиковать версии workflow.", 403)

        wv = db.scalars(select(WorkflowVersion).where(WorkflowVersion.version == version)).first()
        if not wv:
            raise APIError("NOT_FOUND", f"Версия workflow {version} не найдена.", 404)

        wv.is_published = True
        db.commit()
        db.refresh(wv)
        from .workflow import load_workflow_versions
        load_workflow_versions(db)
        return {
            "version": wv.version,
            "name": wv.name,
            "is_published": wv.is_published,
            "status": "published",
        }

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

    @app.get("/api/v1/interactions/{interaction_id}/deliveries", tags=["deliveries"])
    def get_deliveries_endpoint(
        interaction_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return get_interaction_deliveries(db, user, interaction_id)

    @app.post("/api/v1/interactions/{interaction_id}/deliveries", status_code=201, tags=["deliveries"])
    def post_delivery_endpoint(
        interaction_id: str,
        body: DeliveryCreate,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        return create_delivery(db, user, interaction_id, body, idempotency_key)

    @app.get("/api/v1/dashboard", tags=["dashboard"])
    def get_dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
        return dashboard(db, user)

    @app.post("/api/v1/interactions/{interaction_id}/attachments", status_code=201, tags=["attachments"])
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

        cfg = getattr(request.app.state, "settings", config)
        import anyio.to_thread
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

    @app.delete("/api/v1/interactions/{interaction_id}/attachments/{attachment_id}", tags=["attachments"])
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
        return export_report(result, "snapshot", format, user, selected_columns=getattr(body, "selected_columns", None))

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
        return export_report(result, "activity", format, user, selected_columns=getattr(body, "selected_columns", None))

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
        return export_report(result, "created", format, user, selected_columns=getattr(body, "selected_columns", None))

    @app.post("/api/v1/jobs/reports/snapshot", status_code=202, tags=["jobs"])
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

    @app.get("/api/v1/jobs/{job_id}", tags=["jobs"])
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

    @app.get("/api/v1/jobs/{job_id}/download", tags=["jobs"])
    def download_job_report(
        job_id: str,
        format: str = Query("xlsx"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        require_permission(user, "reports.read")
        fmt = (format or "xlsx").lower()
        if fmt not in ("xlsx", "pdf", "json", "csv"):
            raise APIError("VALIDATION_ERROR", f"Неподдерживаемый формат экспорта '{format}'. Допустимы: xlsx, pdf, json, csv.", 422)

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

    @app.post("/api/v1/imports/organizations/preview", tags=["imports"])
    @app.post("/api/v1/imports/preview", tags=["imports"])
    @app.post("/api/v1/catalogs/organizations/import/preview", tags=["imports"])
    async def import_organizations_preview(
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        import_type = request.query_params.get("import_type") or request.query_params.get("type")
        filename, file_bytes, _ = await _extract_uploaded_file(request)
        return preview_organizations_import(db, user, file_bytes, filename=filename, import_type=import_type)

    @app.post("/api/v1/imports/organizations/commit", tags=["imports"])
    @app.post("/api/v1/imports/commit", tags=["imports"])
    @app.post("/api/v1/catalogs/organizations/import/commit", tags=["imports"])
    async def import_organizations_commit(
        request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        content_type = request.headers.get("content-type", "")
        import_type = request.query_params.get("import_type") or request.query_params.get("type")
        if "multipart/form-data" in content_type:
            filename, file_bytes, _ = await _extract_uploaded_file(request)
            parsed_rows = parse_tabular_file(file_bytes, filename=filename, import_type=import_type)
            return commit_organizations_import(db, user, parsed_rows, idempotency_key, import_type=import_type, filename=filename)
        try:
            body = await request.json()
        except Exception:
            body = {}
        rows = body.get("rows", []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
        if isinstance(body, dict) and not import_type:
            import_type = body.get("import_type") or body.get("type")
        filename = (body.get("filename") or body.get("source_name")) if isinstance(body, dict) else None
        import_id = body.get("import_id") if isinstance(body, dict) else None
        return commit_organizations_import(db, user, rows, idempotency_key, import_type=import_type, filename=filename, import_id=import_id)

    @app.post("/api/v1/integrations/upload/json", tags=["integrations"])
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

    @app.post("/api/v1/integrations/upload/learners", tags=["integrations"])
    async def upload_integrations_learners_endpoint(
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        if user.role not in ("supervisor", "administrator", "admin"):
            raise APIError("FORBIDDEN", "Доступ к загрузке анкет слушателей разрешен только ролям supervisor и administrator.", 403)
        filename, file_bytes, _ = await _extract_uploaded_file(request)
        return process_lms_learners_file(db, user, file_bytes, filename=filename)

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

    @app.post("/api/v1/webhooks/{source}", tags=["webhooks"])
    async def webhook_endpoint(
        source: str,
        request: Request,
        db: Session = Depends(get_db),
        config: Settings = Depends(get_settings),
    ):
        src = (source or "").strip().lower()
        if src not in {"lms", "website"}:
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
            raise APIError("UNAUTHORIZED", "Invalid webhook signature or secret", status=401)

        if not body_bytes or not body_bytes.strip():
            raise APIError("VALIDATION_ERROR", "Empty webhook payload", status=400)

        try:
            payload_data = json.loads(body_bytes.decode("utf-8"))
        except Exception as exc:
            raise APIError("VALIDATION_ERROR", f"Invalid JSON payload: {exc}", status=400)

        return process_webhook(db, src, payload_data)

    return app


app = create_app()
