from .admin import router as admin_router
from .auth import router as auth_router
from .catalogs import router as catalogs_router
from .health import router as health_router
from .integrations import router as integrations_router
from .interactions import router as interactions_router
from .reports import router as reports_router
from .workflow import router as workflow_router

__all__ = [
    "admin_router",
    "auth_router",
    "catalogs_router",
    "health_router",
    "integrations_router",
    "interactions_router",
    "reports_router",
    "workflow_router",
]

