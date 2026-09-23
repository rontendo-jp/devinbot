from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.metrics import routes
from app.db.session import get_db
from app.models.database import Repository, Session as DBSession, SessionStatus, TriggerType

EMPTY_COST = {"total_acus": 0, "acus_by_product": {}, "granularity": "daily", "data_points": 0, "daily": []}


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(routes, "get_cost_consumption", AsyncMock(return_value=EMPTY_COST))
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/metrics")

    def override_db():
        with db_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db

    with db_factory() as db:
        repo = Repository(github_repo_path="o/r", telegram_chat_id="1", devin_org_id="org", webhook_secret="s")
        db.add(repo)
        db.flush()
        for days_ago in (0, 2, 10):
            db.add(
                DBSession(
                    devin_session_id=f"devin-{days_ago}",
                    repository_id=repo.id,
                    trigger_type=TriggerType.MANUAL,
                    status=SessionStatus.COMPLETED,
                    prompt="p",
                    created_at=datetime.utcnow() - timedelta(days=days_ago, minutes=1),
                )
            )
        db.commit()
    return TestClient(app)


def test_preset_range_still_works(client):
    r = client.get("/api/metrics/", params={"time_range": "7d"})
    assert r.status_code == 200
    assert r.json()["session_metrics"]["total_sessions"] == 2


def test_custom_range_bounds_both_ends(client):
    now = datetime.utcnow()
    r = client.get(
        "/api/metrics/",
        params={
            "time_range": "custom",
            "time_from": (now - timedelta(days=3)).isoformat(),
            "time_to": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["time_range"] == "custom"
    assert body["session_metrics"]["total_sessions"] == 1


def test_custom_range_defaults_to_last_five_minutes(client):
    r = client.get("/api/metrics/", params={"time_range": "custom"})
    assert r.status_code == 200
    period = r.json()["time_period"]
    start, end = datetime.fromisoformat(period["start"]), datetime.fromisoformat(period["end"])
    assert end - start == timedelta(minutes=5)
    assert r.json()["session_metrics"]["total_sessions"] == 1


def test_custom_range_accepts_timezone_aware_iso(client):
    r = client.get(
        "/api/metrics/",
        params={"time_range": "custom", "time_from": "2026-01-01T00:00:00Z", "time_to": "2026-01-01T01:00:00+00:00"},
    )
    assert r.status_code == 200
    assert r.json()["time_period"]["start"] == "2026-01-01T00:00:00"


def test_preset_range_rejects_explicit_bounds(client):
    r = client.get("/api/metrics/", params={"time_range": "7d", "time_to": "2026-01-01T00:00:00"})
    assert r.status_code == 400


def test_custom_range_rejects_from_after_to(client):
    r = client.get(
        "/api/metrics/",
        params={"time_range": "custom", "time_from": "2026-01-02T00:00:00", "time_to": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 400
