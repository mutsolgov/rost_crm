from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import anyio
import anyio.to_thread
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings, get_settings
from .db import get_engine
from .errors import install_error_handlers
from .metrics import (
    dec_active_background_jobs,
    inc_active_background_jobs,
    record_http_request,
    resolve_endpoint,
)
from .models import BackgroundJob, utcnow
from .routers import (
    admin_router,
    auth_router,
    catalogs_router,
    health_router,
    integrations_router,
    interactions_router,
    reports_router,
    workflow_router,
)
from .routers.common import (
    _extract_uploaded_file,
    _extract_uploaded_file_and_revision,
    _user_dict,
)
from .services import process_background_job

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    config.validate()
    engine = get_engine(config.database_url)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        anyio.to_thread.current_default_thread_limiter().total_tokens = 120

        try:
            from .seed import ensure_schema_columns
            ensure_schema_columns(engine)
        except Exception as exc:
            logger.exception("Failed to ensure schema columns: %s", exc)

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
                        def _fetch_batch() -> list[str]:
                            with factory() as db:
                                return list(
                                    db.scalars(
                                        select(BackgroundJob.id)
                                        .where(BackgroundJob.status == "queued")
                                        .order_by(BackgroundJob.created_at.asc())
                                        .limit(10)
                                    )
                                )

                        job_ids = await anyio.to_thread.run_sync(_fetch_batch)
                        if job_ids:
                            async def _run_job(job_id: str):
                                def _execute():
                                    with factory() as db:
                                        inc_active_background_jobs()
                                        try:
                                            process_background_job(db, job_id)
                                        except Exception as exc:
                                            logger.exception("Background worker error on job %s: %s", job_id, exc)
                                            try:
                                                db.rollback()
                                                failed_job = db.get(BackgroundJob, job_id)
                                                if failed_job and failed_job.status not in ("completed", "cancelled"):
                                                    failed_job.status = "failed"
                                                    failed_job.error_message = str(exc)
                                                    failed_job.updated_at = utcnow()
                                                    db.commit()
                                            except Exception:
                                                db.rollback()
                                        finally:
                                            dec_active_background_jobs()

                                await anyio.to_thread.run_sync(_execute)

                            async with anyio.create_task_group() as job_tg:
                                for jid in job_ids:
                                    job_tg.start_soon(_run_job, jid)

                        await anyio.sleep(1.0 if not job_ids else 0.1)
                    except anyio.get_cancelled_exc_class():
                        logger.info("Background worker loop cancelled, exiting gracefully.")
                        raise
                    except Exception as exc:
                        logger.exception("Background worker error: %s", exc)
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
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration = time.perf_counter() - start_time
            endpoint = resolve_endpoint(request)
            record_http_request(request.method, endpoint, 500, duration)
            raise

        duration = time.perf_counter() - start_time
        endpoint = resolve_endpoint(request)
        record_http_request(request.method, endpoint, status_code, duration)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    # Modular routers registration
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(interactions_router)
    app.include_router(workflow_router)
    app.include_router(reports_router)
    app.include_router(catalogs_router)
    app.include_router(integrations_router)

    # Populate app.routes with router routes for introspection/test compatibility
    for r in list(app.routes):
        if hasattr(r, "original_router"):
            for sub_r in r.original_router.routes:
                if sub_r not in app.routes:
                    app.routes.append(sub_r)

    return app


try:
    app = create_app()
except RuntimeError:
    if os.getenv("APP_ENV") == "production":
        raise
    try:
        app = create_app(Settings(app_env="development", auth_mode="demo"))
    except Exception:
        app = None

__all__ = [
    "app",
    "create_app",
    "_user_dict",
    "_extract_uploaded_file",
    "_extract_uploaded_file_and_revision",
]
