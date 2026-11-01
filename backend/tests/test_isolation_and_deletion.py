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
