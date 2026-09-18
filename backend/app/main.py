from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from .auth import current_user
from .config import Settings, get_settings
from .db import get_db, get_engine
from .errors import APIError, install_error_handlers
from .models import User
from .schemas import AssignmentCommand, CommentCommand, InteractionCreate, SnapshotRequest, TransitionCommand
from .services import (
    add_comment,
    assign,
    catalogs,
    create_interaction,
    dashboard,
    detail,
    interaction_dict,
    list_interactions,
    snapshot,
    transition,
)
from .workflow import WORKFLOW


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
    def get_workflow(user: User = Depends(current_user)):
        # Keep the public shape intentionally declarative; server-side transition checks use the same document.
        return {
            "schema_version": WORKFLOW["schema_version"],
            "template_code": WORKFLOW["template_code"],
            "version": WORKFLOW["version"],
            "name": WORKFLOW["name"],
            "initial_state": WORKFLOW["initial_state"],
            "states": WORKFLOW["states"],
            "transitions": WORKFLOW["transitions"],
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

    @app.post("/api/v1/reports/snapshot", tags=["reports"])
    def post_snapshot(body: SnapshotRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
        return snapshot(db, user, body)

    @app.post("/api/v1/reports/snapshot/export", tags=["reports"])
    def export_snapshot(body: SnapshotRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
        result = snapshot(db, user, body)
        response = JSONResponse(result)
        response.headers["Content-Disposition"] = 'attachment; filename="rtk-snapshot.json"'
        response.headers["X-Report-Format"] = "json"
        return response

    return app


app = create_app()
