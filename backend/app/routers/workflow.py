from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..errors import APIError
from ..models import User, WorkflowVersion, utcnow
from ..schemas import WorkflowMigrateRequest, WorkflowVersionCreate
from ..services import commit_workflow_migration, iso, preview_workflow_migration
from ..workflow import get_workflow as get_workflow_by_version
from ..workflow import load_workflow_versions

router = APIRouter()


@router.get("/api/v1/workflow", tags=["reference"])
def get_workflow(version: int = Query(1, ge=1), user: User = Depends(current_user)):
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


@router.post("/api/v1/workflow/migrate/preview", tags=["workflow"])
def post_workflow_migrate_preview(
    body: WorkflowMigrateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return preview_workflow_migration(
        db, user, body.from_version, body.to_version, body.status_mapping
    )


@router.post("/api/v1/workflow/migrate/commit", tags=["workflow"])
def post_workflow_migrate_commit(
    body: WorkflowMigrateRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return commit_workflow_migration(
        db, user, body.from_version, body.to_version, body.status_mapping, idempotency_key, getattr(body, "expected_card_revisions", None)
    )


@router.get("/api/v1/workflow/versions", tags=["workflow"])
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


@router.post("/api/v1/workflow/versions", status_code=201, tags=["workflow"])
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


@router.post("/api/v1/workflow/versions/{version}/publish", tags=["workflow"])
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
    load_workflow_versions(db)
    return {
        "version": wv.version,
        "name": wv.name,
        "is_published": wv.is_published,
        "status": "published",
    }
