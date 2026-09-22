import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.repositories import routes
from app.core.config import settings
from app.db.session import get_db

TOKEN = "admin-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", TOKEN)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/repositories")

    def override_db():
        with db_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def create(client, **overrides):
    body = {"github_repo_path": "o/r", "telegram_chat_id": "1000", "webhook_secret": "whsec"}
    body.update(overrides)
    return client.post("/api/repositories/", json=body, headers=AUTH)


def test_list_is_public(client):
    assert client.get("/api/repositories/").status_code == 200


def test_create_requires_admin_token(client):
    r = client.post("/api/repositories/", json={"github_repo_path": "o/r", "telegram_chat_id": "1"})
    assert r.status_code == 401
    r = client.post(
        "/api/repositories/",
        json={"github_repo_path": "o/r", "telegram_chat_id": "1"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_create_uses_json_body_and_hides_secret(client):
    r = create(client)
    assert r.status_code == 200, r.text
    listed = client.get("/api/repositories/").json()["repositories"]
    assert listed[0]["github_repo_path"] == "o/r"
    assert "webhook_secret" not in listed[0]


def test_create_rejects_query_params(client):
    r = client.post("/api/repositories/?github_repo_path=o/r&telegram_chat_id=1", headers=AUTH)
    assert r.status_code == 422


def test_create_validates_repo_path(client):
    assert create(client, github_repo_path="not-a-path").status_code == 422


def test_update_and_delete_require_admin(client):
    repo_id = create(client).json()["id"]
    assert client.put(f"/api/repositories/{repo_id}", json={"telegram_chat_id": "-5"}).status_code == 401
    assert client.delete(f"/api/repositories/{repo_id}").status_code == 401

    r = client.put(f"/api/repositories/{repo_id}", json={"telegram_chat_id": "-5"}, headers=AUTH)
    assert r.status_code == 200
    assert client.get(f"/api/repositories/{repo_id}").json()["telegram_chat_id"] == "-5"
    assert client.delete(f"/api/repositories/{repo_id}", headers=AUTH).status_code == 200


def test_update_ignores_explicit_nulls(client):
    repo_id = create(client).json()["id"]
    r = client.put(
        f"/api/repositories/{repo_id}",
        json={"telegram_chat_id": None, "webhook_secret": None, "enabled": False},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    repo = client.get(f"/api/repositories/{repo_id}").json()
    assert repo["telegram_chat_id"] == "1000"
    assert repo["enabled"] is False


def test_admin_endpoints_disabled_without_token_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_token", "")
    assert create(client).status_code == 503
