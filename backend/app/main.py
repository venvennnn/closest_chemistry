from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.routers.api import router as api_router
from app.routers.health import router as health_router

settings = get_settings()

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


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
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
