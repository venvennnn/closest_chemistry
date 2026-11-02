from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Asset, Workspace
from app.services.workspace import get_or_create_workspace


def _override(session):
    def inner():
        try:
            yield session
        finally:
            pass

    return inner


def test_tenant_isolation_and_deletion(session):
    app.dependency_overrides[get_db] = _override(session)
    client = TestClient(app)

    workspace_a = get_or_create_workspace(session, "user-a")
    session.add(
        Asset(
            owner_id="user-a",
            workspace_id=workspace_a.id,
            kind="outfit",
            storage_key="user-a/x.jpg",
            content_sha256="abc",
            mime_type="image/jpeg",
            byte_size=10,
            width=100,
            height=100,
        )
    )
    session.commit()
    asset_id = session.query(Asset).first().id

    denied = client.get(f"/v1/assets/{asset_id}/content", headers={"X-Session-Id": "user-b"})
    assert denied.status_code == 404

    workspace = client.get("/v1/workspace", headers={"X-Session-Id": "user-a"})
    assert workspace.status_code == 200
    assert workspace.json()["workspace_id"] == str(workspace_a.id)

    deleted = client.delete("/v1/workspace", headers={"X-Session-Id": "user-a"})
    assert deleted.status_code == 200
    assert session.query(Workspace).filter(Workspace.owner_id == "user-a").count() == 0
    assert session.query(Asset).filter(Asset.owner_id == "user-a").count() == 0
    app.dependency_overrides.clear()


def test_delete_workspace_clears_consent_uploads_and_garments(session):
    import io

    from PIL import Image

    get_or_create_workspace(session, "local")
    app.dependency_overrides[get_db] = _override(session)
    client = TestClient(app)
    buffer = io.BytesIO()
    Image.new("RGB", (200, 200), color=(80, 40, 20)).save(buffer, format="PNG")
    png = buffer.getvalue()
    consent = client.post(
        "/v1/consents",
        json={"granted": True, "kind": "external_image_processing", "policy_version": "2026-11-01"},
    )
    assert consent.status_code == 200, consent.text
    uploaded = client.post(
        "/v1/assets",
        data={"kind": "outfit"},
        files={"file": ("shirt.png", png, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    tryon = client.post(
        "/v1/assets",
        data={"kind": "tryon_source"},
        files={"file": ("person.png", png, "image/png")},
    )
    assert tryon.status_code == 201, tryon.text
    deleted = client.delete("/v1/workspace")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    empty = client.get("/v1/workspace")
    assert empty.status_code == 200
    assert empty.json()["consent"] is None
    assert empty.json()["has_tryon_photo"] is False
    assert empty.json()["counts"]["garments"] == 0
    listed = client.get("/v1/assets")
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    app.dependency_overrides.clear()


def test_tryon_upload_replaces_previous_source(session):
    import io

    from PIL import Image

    get_or_create_workspace(session, "local")
    app.dependency_overrides[get_db] = _override(session)
    client = TestClient(app)
    buffer = io.BytesIO()
    Image.new("RGB", (200, 200), color=(10, 10, 10)).save(buffer, format="PNG")
    png = buffer.getvalue()
    client.post(
        "/v1/consents",
        json={"granted": True, "kind": "external_image_processing", "policy_version": "2026-11-01"},
    )
    first = client.post(
        "/v1/assets",
        data={"kind": "tryon_source"},
        files={"file": ("one.png", png, "image/png")},
    )
    second = client.post(
        "/v1/assets",
        data={"kind": "tryon_source"},
        files={"file": ("two.png", png, "image/png")},
    )
    assert first.status_code == 201 and second.status_code == 201
    listed = client.get("/v1/assets?kind=tryon_source")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == second.json()["id"]
    workspace = client.get("/v1/workspace")
    assert workspace.json()["has_tryon_photo"] is True
    app.dependency_overrides.clear()


def test_default_request_uses_single_local_session(session):
    app.dependency_overrides[get_db] = _override(session)
    created = get_or_create_workspace(session, "local")
    client = TestClient(app)
    first = client.get("/v1/workspace")
    second = client.get("/v1/workspace")
    assert first.status_code == 200
    assert first.json()["workspace_id"] == str(created.id)
    assert first.json()["workspace_id"] == second.json()["workspace_id"]
    app.dependency_overrides.clear()
