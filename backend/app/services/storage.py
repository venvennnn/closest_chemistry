from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from app.config import get_settings


class StorageError(RuntimeError):
    pass


def _local_root() -> Path:
    settings = get_settings()
    path = Path(settings.local_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def put_bytes(owner_id: str, key: str, data: bytes, mime_type: str) -> str:
    settings = get_settings()
    storage_key = f"{owner_id}/{key}"
    if settings.supabase_url and settings.supabase_service_role_key:
        url = (
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
            f"{settings.supabase_storage_bucket}/{storage_key}"
        )
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
                "Content-Type": mime_type,
                "x-upsert": "true",
            },
            content=data,
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise StorageError(
                f"Supabase Storage rejected the upload ({response.status_code}). "
                "Confirm the private bucket exists and the service role can write."
            )
        return storage_key

    destination = _local_root() / storage_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return storage_key


def get_bytes(storage_key: str) -> bytes:
    settings = get_settings()
    if settings.supabase_url and settings.supabase_service_role_key:
        url = (
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
            f"{settings.supabase_storage_bucket}/{storage_key}"
        )
        response = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
            },
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise StorageError("Could not read object from private storage.")
        return response.content
    path = _local_root() / storage_key
    if not path.exists():
        raise StorageError("Local object missing.")
    return path.read_bytes()


def delete_prefix(owner_id: str) -> None:
    settings = get_settings()
    if settings.supabase_url and settings.supabase_service_role_key:
        url = (
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
            f"{settings.supabase_storage_bucket}"
        )
        httpx.request(
            "DELETE",
            url,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
            },
            json={"prefixes": [f"{owner_id}/"]},
            timeout=30.0,
        )
        return
    root = _local_root() / owner_id
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file():
                path.unlink()


def new_key(kind: str, suffix: str = "jpg") -> str:
    return f"{kind}/{uuid.uuid4()}.{suffix}"
