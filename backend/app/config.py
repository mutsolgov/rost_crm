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
    storage_dir: str = "storage"
    lms_integration_mode: str = "mock"
    website_integration_mode: str = "mock"
    lms_base_url: str = "https://rtkb.zion-lms.ru"
    website_base_url: str = "https://it-school.rt.ru"
    lms_api_token: str | None = None
    website_api_token: str | None = None
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_enabled: bool = False
    clamav_timeout: float = 10.0
    redis_url: str = "redis://redis:6379/0"
    background_worker_enabled: bool = False

    def validate(self):
        if self.auth_mode not in {"demo", "oidc"}:
            raise RuntimeError("AUTH_MODE must be oidc or demo")
        if self.auth_mode == "demo" and self.app_env != "development":
            raise RuntimeError("Demo authentication requires APP_ENV=development")
        if self.database_url.startswith("sqlite") and self.app_env not in {"development", "test"}:
            raise RuntimeError("SQLite is an explicit development/test fallback only")
        if self.lms_integration_mode not in {"mock", "live"}:
            raise RuntimeError("LMS_INTEGRATION_MODE must be mock or live")
        if self.website_integration_mode not in {"mock", "live"}:
            raise RuntimeError("WEBSITE_INTEGRATION_MODE must be mock or live")


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
    storage_dir = os.getenv("STORAGE_DIR", "storage")
    lms_integration_mode = os.getenv("LMS_INTEGRATION_MODE", "mock")
    website_integration_mode = os.getenv("WEBSITE_INTEGRATION_MODE", "mock")
    lms_base_url = os.getenv("LMS_BASE_URL", "https://rtkb.zion-lms.ru")
    website_base_url = os.getenv("WEBSITE_BASE_URL", "https://it-school.rt.ru")
    clamav_host = os.getenv("CLAMAV_HOST") or "clamav"
    try:
        clamav_port = int(os.getenv("CLAMAV_PORT", "3310"))
        if not (1 <= clamav_port <= 65535):
            clamav_port = 3310
    except ValueError:
        clamav_port = 3310
    clamav_enabled = os.getenv("CLAMAV_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    try:
        clamav_timeout = float(os.getenv("CLAMAV_TIMEOUT", "10.0"))
        if clamav_timeout <= 0:
            clamav_timeout = 10.0
    except ValueError:
        clamav_timeout = 10.0
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    background_worker_enabled = os.getenv("BACKGROUND_WORKER_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    return Settings(
        database_url=url,
        app_env=env,
        auth_mode=mode,
        oidc_issuer=issuer,
        oidc_audience=os.getenv("OIDC_AUDIENCE", "rtk-crm-api"),
        oidc_jwks_url=os.getenv("OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"),
        oidc_url=oidc_url,
        oidc_realm=realm,
        oidc_client_id=os.getenv("OIDC_CLIENT_ID", "rtk-crm-web"),
        storage_dir=storage_dir,
        lms_integration_mode=lms_integration_mode,
        website_integration_mode=website_integration_mode,
        lms_base_url=lms_base_url,
        website_base_url=website_base_url,
        lms_api_token=os.getenv("LMS_API_TOKEN"),
        website_api_token=os.getenv("WEBSITE_API_TOKEN"),
        clamav_host=clamav_host,
        clamav_port=clamav_port,
        clamav_enabled=clamav_enabled,
        clamav_timeout=clamav_timeout,
        redis_url=redis_url,
        background_worker_enabled=background_worker_enabled,
    )
