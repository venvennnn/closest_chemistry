from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SINGLE_OWNER_ID = "local"


@dataclass
class Principal:
    owner_id: str
    email: str | None
    claims: dict[str, Any]


def _safe_session(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if SESSION_RE.fullmatch(trimmed):
        return trimmed
    raise HTTPException(status_code=400, detail="Session id is invalid.")


def get_principal(request: Request) -> Principal:
    """Anonymous single-user session. No sign-in.

    Default production mode is one shared closet (`local`). Tests may send
    `X-Session-Id` so isolation checks still run.
    """
    settings = get_settings()
    header = _safe_session(request.headers.get("x-session-id"))
    cookie = _safe_session(request.cookies.get("cc_session"))
    allow_override = settings.auth_mode == "session" or settings.environment == "test"
    if allow_override and (header or cookie):
        owner_id = header or cookie or settings.single_owner_id
        return Principal(owner_id=owner_id, email=None, claims={"mode": "session"})
    return Principal(owner_id=settings.single_owner_id, email=None, claims={"mode": "single"})


def current_principal(principal: Principal = Depends(get_principal)) -> Principal:
    return principal


def db_session(session: Session = Depends(get_db)) -> Session:
    return session
