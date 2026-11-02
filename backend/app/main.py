from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, ProgrammingError
from starlette.formparsers import MultiPartException

from app import __version__
from app.config import get_settings
from app.routers.api import router as api_router
from app.routers.health import router as health_router
from app.services.storage import StorageError

settings = get_settings()
log = logging.getLogger("closest_chemistry")

app = FastAPI(title="Closest Chemistry", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Session-Id"],
)
app.include_router(health_router)
app.include_router(api_router)


@app.exception_handler(HTTPException)
async def http_exc(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exc(_: Request, exc: RequestValidationError):
    messages = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()) if part != "body")
        messages.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages) or "Request failed validation."})


@app.exception_handler(MultiPartException)
async def multipart_exc(_: Request, exc: MultiPartException):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc) or "Upload was not a valid multipart file. Attach a JPEG, PNG, or WebP image."},
    )


@app.exception_handler(StorageError)
async def storage_exc(_: Request, exc: StorageError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(OperationalError)
@app.exception_handler(ProgrammingError)
async def database_exc(_: Request, exc: OperationalError | ProgrammingError):
    log.exception("Database error")
    raw = str(getattr(exc, "orig", None) or exc).lower()
    if "no such table" in raw or "does not exist" in raw or "undefined table" in raw:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database tables are missing. Run `alembic upgrade head` on the API against DATABASE_URL."
            },
        )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is unreachable. Check DATABASE_URL and that Postgres is running."},
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal error. Identifiers and timings are logged; photos, tokens, and signed URLs are not."},
    )


@app.get("/")
def root() -> dict:
    return {
        "name": "Closest Chemistry",
        "tagline": "Discover what clicks in your closet.",
        "version": __version__,
        "docs": "/docs",
    }
