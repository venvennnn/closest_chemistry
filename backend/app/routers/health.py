from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "closest-chemistry"}


@router.get("/readyz")
def readyz(session: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    session.execute(text("SELECT 1"))
    from app.worker import WORKER_STATE

    youcam_missing = settings.missing_youcam()
    return {
        "status": "ready",
        "database": True,
        "gemini_configured": not bool(settings.missing_gemini()),
        "youcam_configured": youcam_missing is None,
        "youcam_missing": youcam_missing,
        "auth_configured": True,
        "auth_mode": settings.auth_mode,
        "worker_running": bool(WORKER_STATE.get("alive")),
    }
