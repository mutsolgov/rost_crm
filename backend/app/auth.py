from functools import lru_cache

import jwt
from fastapi import Depends, Header
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, runtime_settings
from .errors import APIError
from .models import User


@lru_cache
def jwks_client(url):
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300, timeout=5)


def current_user(db: Session = Depends(get_db), authorization: str | None = Header(None),
                 x_demo_user: str | None = Header(None), config=Depends(runtime_settings)) -> User:
    if config.auth_mode == "demo":
        if not x_demo_user:
            raise APIError("UNAUTHENTICATED", "Выберите демонстрационного пользователя.", 401)
        user = db.get(User, x_demo_user)
    else:
        if not authorization or not authorization.startswith("Bearer "):
            raise APIError("UNAUTHENTICATED", "Необходим вход через Keycloak.", 401)
        token = authorization[7:].strip()
        try:
            key = jwks_client(config.oidc_jwks_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], issuer=config.oidc_issuer,
                                audience=config.oidc_audience,
                                options={"require": ["exp", "iss", "aud", "sub"]})
        except PyJWKClientConnectionError:
            raise APIError("IDENTITY_PROVIDER_UNAVAILABLE", "Сервис авторизации временно недоступен.", 503)
        except (jwt.PyJWTError, ValueError, TypeError):
            raise APIError("UNAUTHENTICATED", "Сеанс недействителен или истёк.", 401)
        user = db.scalar(select(User).where(User.keycloak_subject == claims["sub"]))
        roles = set(claims.get("realm_access", {}).get("roles", []))
        roles.update(claims.get("resource_access", {}).get(config.oidc_client_id, {}).get("roles", []))
        if user and user.role not in roles:
            raise APIError("FORBIDDEN", "Роль учётной записи не разрешена в CRM.", 403)
    if not user or not user.active:
        raise APIError("UNAUTHENTICATED", "Учётная запись CRM недоступна.", 401)
    return user
