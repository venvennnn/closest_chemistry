import io
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image

from app.database import get_db
from app.main import app
from app.services.workspace import get_or_create_workspace


def _png(size=(200, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(180, 120, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


def _override(session):
    def inner():
        try:
            yield session
        finally:
            pass

    return inner


def _client(session):
    app.dependency_overrides[get_db] = _override(session)
    return TestClient(app)


def test_outfit_and_purchase_uploads_after_consent(session):
    get_or_create_workspace(session, "local")
    client = _client(session)
    denied = client.post("/v1/assets", data={"kind": "outfit"}, files={"file": ("shirt.png", _png(), "image/png")})
    assert denied.status_code == 403
    consent = client.post(
        "/v1/consents",
        json={"granted": True, "kind": "external_image_processing", "policy_version": "2026-11-01"},
    )
    assert consent.status_code == 200, consent.text
    uploaded = client.post(
        "/v1/assets",
        data={"kind": "outfit"},
        files={"file": ("shirt.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["kind"] == "outfit"
    listed_photos = client.get("/v1/assets?kind=outfit")
    assert listed_photos.status_code == 200, listed_photos.text
    assert listed_photos.json()["items"][0]["id"] == uploaded.json()["id"]
    content = client.get(f"/v1/assets/{uploaded.json()['id']}/content")
    assert content.status_code == 200
    assert content.content[:8] == b"\x89PNG\r\n\x1a\n" or content.content[:3] == b"\xff\xd8"
    product = client.post(
        "/v1/products",
        data={
            "title": "Camel blazer",
            "price_major": "120",
            "currency": "USD",
            "category": "outerwear",
            "colour_family": "camel",
            "pattern_family": "solid",
        },
        files={"file": ("blazer.png", _png(), "image/png")},
    )
    assert product.status_code == 201, product.text
    listed = client.get("/v1/products")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["title"] == "Camel blazer"
    app.dependency_overrides.clear()


def test_extract_kick_completes_job_without_background_loop(session, monkeypatch):
    from app.config import get_settings
    from app.models import Job

    get_or_create_workspace(session, "local")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.worker.extract_garments",
        lambda _data, _mime: {
            "garments": [],
            "provider": "gemini",
            "model_id": "gemini-3.8-flash",
            "prompt_version": "garment-extract-v1",
        },
    )
    client = _client(session)
    consent = client.post(
        "/v1/consents",
        json={"granted": True, "kind": "external_image_processing", "policy_version": "2026-11-01"},
    )
    assert consent.status_code == 200, consent.text
    uploaded = client.post(
        "/v1/assets",
        data={"kind": "outfit"},
        files={"file": ("shirt.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    extracted = client.post(f"/v1/assets/{uploaded.json()['id']}/extract")
    assert extracted.status_code == 202, extracted.text
    assert extracted.json()["status"] == "succeeded"
    session.expire_all()
    stored = session.get(Job, UUID(extracted.json()["job_id"]))
    assert stored is not None
    assert stored.status == "succeeded"
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_readyz_reports_worker_flag(session):
    client = _client(session)
    response = client.get("/readyz")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["worker_running"] is False
    app.dependency_overrides.clear()


def test_malformed_multipart_is_not_a_generic_500(session):
    get_or_create_workspace(session, "local")
    client = _client(session)
    client.post(
        "/v1/consents",
        json={"granted": True, "kind": "external_image_processing", "policy_version": "2026-11-01"},
    )
    response = client.post(
        "/v1/assets",
        content=b"--nope",
        headers={"content-type": "multipart/form-data; boundary=abc"},
    )
    assert response.status_code in {400, 422}
    assert "Internal error" not in response.json()["detail"]
    app.dependency_overrides.clear()
