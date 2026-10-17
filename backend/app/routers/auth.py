from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import Settings
from ..db import get_db, runtime_settings
from ..models import User
from .common import _user_dict

router = APIRouter(tags=["auth"])


@router.get("/api/v1/config")
def public_config(
    db: Session = Depends(get_db),
    config: Settings = Depends(runtime_settings),
):
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


@router.get("/api/v1/me")
def me(
    user: User = Depends(current_user),
    config: Settings = Depends(runtime_settings),
):
    return _user_dict(user, config.auth_mode)
