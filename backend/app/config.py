import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql+psycopg://rtk:rtk@localhost:5432/rtk_crm"
    app_env: str = "production"
    auth_mode: str = "oidc"
    oidc_issuer: str = "http://localhost:8080/realms/rtk-crm"
    oidc_audience: str = "rtk-crm-api"
    oidc_jwks_url: str = "http://localhost:8080/realms/rtk-crm/protocol/openid-connect/certs"
    oidc_url: str = "http://localhost:8080"
    oidc_realm: str = "rtk-crm"
    oidc_client_id: str = "rtk-crm-web"

    def validate(self):
        if self.auth_mode not in {"demo", "oidc"}:
            raise RuntimeError("AUTH_MODE must be oidc or demo")
        if self.auth_mode == "demo" and self.app_env != "development":
            raise RuntimeError("Demo authentication requires APP_ENV=development")
        if self.database_url.startswith("sqlite") and self.app_env not in {"development", "test"}:
            raise RuntimeError("SQLite is an explicit development/test fallback only")


@lru_cache
def get_settings() -> Settings:
    env = os.getenv("APP_ENV", "production")
    mode = os.getenv("AUTH_MODE", "oidc")
    if mode not in {"demo", "oidc"}:
        raise RuntimeError("AUTH_MODE must be oidc or demo")
    if mode == "demo" and env != "development":
        raise RuntimeError("Demo authentication requires APP_ENV=development")
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://rtk:rtk@localhost:5432/rtk_crm")
    if url.startswith("sqlite") and env not in {"development", "test"}:
        raise RuntimeError("SQLite is an explicit development/test fallback only")
    oidc_url = os.getenv("OIDC_URL", "http://localhost:8080").rstrip("/")
    realm = os.getenv("OIDC_REALM", "rtk-crm")
    issuer = os.getenv("OIDC_ISSUER", f"{oidc_url}/realms/{realm}").rstrip("/")
    return Settings(url, env, mode, issuer, os.getenv("OIDC_AUDIENCE", "rtk-crm-api"),
                    os.getenv("OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"),
                    oidc_url, realm, os.getenv("OIDC_CLIENT_ID", "rtk-crm-web"))
