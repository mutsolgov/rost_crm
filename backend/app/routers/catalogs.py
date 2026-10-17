from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..errors import APIError
from ..importer import (
    commit_organizations_import,
    parse_tabular_file,
    preview_organizations_import,
)
from ..models import Organization, User
from ..schemas import OrganizationPatch
from ..services import catalogs, permissions, set_organization_access
from .common import _extract_uploaded_file

router = APIRouter()


@router.get("/api/v1/catalogs", tags=["reference"])
def get_catalogs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return catalogs(db, user)


@router.patch("/api/v1/organizations/{organization_id}", tags=["catalogs"])
def patch_organization(
    organization_id: str,
    body: OrganizationPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
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


@router.post("/api/v1/imports/organizations/preview", tags=["imports"])
@router.post("/api/v1/imports/preview", tags=["imports"])
@router.post("/api/v1/catalogs/organizations/import/preview", tags=["imports"])
async def import_organizations_preview(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    import_type = request.query_params.get("import_type") or request.query_params.get("type")
    filename, file_bytes, _ = await _extract_uploaded_file(request)
    return preview_organizations_import(db, user, file_bytes, filename=filename, import_type=import_type)


@router.post("/api/v1/imports/organizations/commit", tags=["imports"])
@router.post("/api/v1/imports/commit", tags=["imports"])
@router.post("/api/v1/catalogs/organizations/import/commit", tags=["imports"])
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
