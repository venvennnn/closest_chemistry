from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db


@dataclass
class Principal:
    owner_id: str
    email: str | None
    claims: dict[str, Any]


_jwks_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient | None:
    global _jwks_client
    settings = get_settings()
    if not settings.supabase_url:
        return None
    if _jwks_client is None:
        url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url)
    return _jwks_client


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    options = {"require": ["exp", "sub"], "verify_aud": True, "verify_iss": bool(settings.resolved_jwt_issuer)}
    issuer = settings.resolved_jwt_issuer or None
    audience = settings.supabase_jwt_audience
    try:
        client = _jwks()
        if client is not None:
            signing_key = client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "HS256"],
                audience=audience,
                issuer=issuer,
                options=options,
            )
        if not settings.supabase_jwt_secret:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Auth is not configured. Set SUPABASE_URL (JWKS) or SUPABASE_JWT_SECRET, "
                    "plus issuer and audience. The API will not trust browser-supplied owner IDs."
                ),
            )
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=audience,
            issuer=issuer,
            options=options,
        )
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired.") from exc
    except jwt.InvalidAudienceError as exc:
        raise HTTPException(status_code=401, detail="Token audience is invalid.") from exc
    except jwt.InvalidIssuerError as exc:
        raise HTTPException(status_code=401, detail="Token issuer is invalid.") from exc
    except jwt.InvalidSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token signature is invalid.") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token could not be verified.") from exc


def get_principal(request: Request) -> Principal:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    claims = decode_token(header.split(" ", 1)[1].strip())
    owner_id = claims.get("sub")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Token is missing sub.")
    return Principal(owner_id=str(owner_id), email=claims.get("email"), claims=claims)


def current_principal(principal: Principal = Depends(get_principal)) -> Principal:
    return principal


def db_session(session: Session = Depends(get_db)) -> Session:
    return session
