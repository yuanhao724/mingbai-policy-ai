from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .. import db
from ..config import settings
from ..observability import metrics


router = APIRouter(prefix="/api", tags=["system"])


@router.get("/live")
def live() -> dict:
    return {"status": "live"}


@router.get("/ready")
def ready() -> dict:
    try:
        db.init_db(settings.db_path)
        with db.session(settings.db_path) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="database not ready") from exc
    return {"status": "ready"}


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    return metrics.render()
