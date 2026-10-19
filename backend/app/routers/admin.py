from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..errors import APIError
from ..models import Organization, OrganizationAccess, User
from ..schemas import OrganizationAccessPut, UserPatch
from ..services import (
    bump_authz_epoch,
    permissions,
    revoke_organization_access,
    set_organization_access,
    update_user_access,
)

router = APIRouter(prefix="/api/v1/users", tags=["admin"])


def _check_admin(user: User):
    user_perms = permissions(user)
    if user.role != "administrator" and "users.manage" not in user_perms:
        raise APIError("FORBIDDEN", "Требуются права администратора или users.manage.", 403)


def _serialize_user(user: User, db: Session) -> dict:
    grants = db.scalars(
        select(OrganizationAccess).where(OrganizationAccess.user_id == user.id)
    ).all()
    org_ids = [g.organization_id for g in grants]
    org_map = {}
    if org_ids:
        org_map = {
            o.id: o.name
            for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids)))
        }

    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "team_id": user.team_id,
        "active": user.active,
        "email": user.email,
        "phone": user.phone,
        "permissions": sorted(permissions(user)),
        "organization_grants": [
            {
                "organization_id": g.organization_id,
                "organization_name": org_map.get(g.organization_id, g.organization_id),
                "can_create": g.can_create,
                "read_all": g.read_all,
            }
            for g in grants
        ],
    }


@router.get("", tags=["admin"])
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _check_admin(user)
    users = db.scalars(select(User).order_by(User.name.asc())).all()
    return [_serialize_user(u, db) for u in users]


@router.patch("/{user_id}", tags=["admin"])
def patch_user(
    user_id: str,
    body: UserPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _check_admin(user)
    target = db.get(User, user_id)
    if not target:
        raise APIError("NOT_FOUND", "Пользователь не найден.", 404)

    if target.id == user.id:
        if body.active is False:
            raise APIError("VALIDATION_ERROR", "Администратор не может заблокировать собственную учётную запись.", 422)
        if body.role is not None and body.role not in ("administrator", "admin"):
            raise APIError("VALIDATION_ERROR", "Администратор не может понизить собственную роль.", 422)

    if target.role in ("administrator", "admin") and (
        body.active is False
        or (body.role is not None and body.role not in ("administrator", "admin"))
    ):
        other_active_admins = db.scalar(
            select(func.count(User.id)).where(
                User.role.in_(("administrator", "admin")),
                User.active.is_(True),
                User.id != target.id,
            )
        ) or 0
        if other_active_admins == 0:
            raise APIError("VALIDATION_ERROR", "Нельзя заблокировать или лишить прав единственного активного администратора системы.", 422)

    update_user_access(
        db,
        user_id,
        role=body.role,
        team_id=body.team_id,
        active=body.active,
        permissions=body.permissions,
    )
    if body.name is not None:
        target.name = body.name
    if body.phone is not None:
        target.phone = body.phone
    if body.email is not None:
        target.email = body.email

    new_epoch = bump_authz_epoch(db)
    db.commit()
    db.refresh(target)

    res = _serialize_user(target, db)
    res["authz_epoch"] = new_epoch
    return res


@router.put("/{user_id}/organizations/{organization_id}", status_code=200, tags=["admin"])
def grant_organization_access(
    user_id: str,
    organization_id: str,
    body: OrganizationAccessPut,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _check_admin(user)
    target = db.get(User, user_id)
    if not target:
        raise APIError("NOT_FOUND", "Пользователь не найден.", 404)
    org = db.get(Organization, organization_id)
    if not org:
        raise APIError("NOT_FOUND", "Организация не найдена.", 404)

    grant = set_organization_access(
        db,
        user_id,
        organization_id,
        can_create=body.can_create,
        read_all=body.read_all,
    )
    new_epoch = bump_authz_epoch(db)
    db.commit()

    return {
        "user_id": user_id,
        "organization_id": organization_id,
        "organization_name": org.name,
        "can_create": grant.can_create,
        "read_all": grant.read_all,
        "authz_epoch": new_epoch,
    }


@router.delete("/{user_id}/organizations/{organization_id}", status_code=200, tags=["admin"])
def delete_organization_access(
    user_id: str,
    organization_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _check_admin(user)
    target = db.get(User, user_id)
    if not target:
        raise APIError("NOT_FOUND", "Пользователь не найден.", 404)
    org = db.get(Organization, organization_id)
    if not org:
        raise APIError("NOT_FOUND", "Организация не найдена.", 404)

    revoked = revoke_organization_access(db, user_id, organization_id)
    new_epoch = bump_authz_epoch(db)
    db.commit()

    return {
        "status": "ok",
        "deleted": revoked,
        "user_id": user_id,
        "organization_id": organization_id,
        "authz_epoch": new_epoch,
    }
