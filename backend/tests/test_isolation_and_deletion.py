from fastapi.testclient import TestClient
import jwt

from app.database import get_db
from app.main import app
from app.models import Asset, Workspace
from app.services.workspace import get_or_create_workspace


def _token(sub: str) -> str:
    return jwt.encode(
        {
            "sub": sub,
            "aud": "authenticated",
            "iss": "http://localhost/auth/v1",
            "exp": 4102444800,
        },
        "test-secret-do-not-use-in-production",
        algorithm="HS256",
    )


def test_tenant_isolation_and_deletion(session):
    app.dependency_overrides[get_db] = lambda: session
    client = TestClient(app)
    a = _token("user-a")
    b = _token("user-b")

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

    denied = client.get(f"/v1/assets/{asset_id}/content", headers={"Authorization": f"Bearer {b}"})
    assert denied.status_code == 404

    workspace = client.get("/v1/workspace", headers={"Authorization": f"Bearer {a}"})
    assert workspace.status_code == 200
    assert workspace.json()["workspace_id"] == str(workspace_a.id)

    deleted = client.delete("/v1/workspace", headers={"Authorization": f"Bearer {a}"})
    assert deleted.status_code == 200
    assert session.query(Workspace).filter(Workspace.owner_id == "user-a").count() == 0
    assert session.query(Asset).filter(Asset.owner_id == "user-a").count() == 0
    app.dependency_overrides.clear()
