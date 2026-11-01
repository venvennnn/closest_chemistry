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
    return {
        "status": "ready",
        "database": True,
        "gemini_configured": not bool(settings.missing_gemini()),
        "youcam_configured": not bool(settings.missing_youcam()),
        "auth_configured": bool(settings.supabase_url or settings.supabase_jwt_secret),
    }
