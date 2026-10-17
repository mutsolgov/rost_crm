from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import APIError
from ..metrics import generate_metrics_response

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - readiness must not expose DB details
        raise APIError("NOT_READY", "База данных недоступна.", 503) from exc

    redis_status = "unavailable"
    try:
        from ..redis_client import get_redis_client

        client = get_redis_client()
        if client.ping():
            redis_status = "ok"
    except Exception:
        redis_status = "unavailable"

    return {"status": "ok", "database": "ok", "redis": redis_status}


@router.get("/metrics")
def prometheus_metrics():
    return generate_metrics_response()
