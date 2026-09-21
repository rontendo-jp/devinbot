from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.models.database import DevinMode, Repository, Session as DBSession, SessionStatus, TriggerType
from app.services import session_sync
from app.services.session_sync import SessionSyncService


def seed(db_factory, *statuses):
    with db_factory() as db:
        repo = Repository(github_repo_path="o/r", telegram_chat_id="1000", telegram_topic_id="7",
                          devin_org_id="org", webhook_secret="s", enabled=True)
        db.add(repo)
        db.flush()
        rows = []
        for i, status in enumerate(statuses):
            s = DBSession(devin_session_id=f"sid{i:013d}", repository_id=repo.id, trigger_type=TriggerType.ISSUE,
                          status=status, prompt="p", devin_mode=DevinMode.NORMAL, created_at=datetime.utcnow())
            db.add(s)
            rows.append(s)
        db.commit()
        return [r.id for r in rows]


def make_service(statuses_by_id, notifier=None):
    client = MagicMock()

    async def get_session(sid):
        result = statuses_by_id[sid]
        if isinstance(result, Exception):
            raise result
        return result

    client.get_session = AsyncMock(side_effect=get_session)
    return SessionSyncService(client, notifier=notifier)


async def test_sync_all_maps_final_statuses_and_notifies(db_factory, monkeypatch):
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    ids = seed(db_factory, SessionStatus.RUNNING, SessionStatus.RUNNING, SessionStatus.RUNNING, SessionStatus.COMPLETED)
    notified = []

    async def notifier(session, text):
        notified.append((session.devin_session_id, session.status, text))

    svc = make_service({
        "sid0000000000000": {"status": "suspended", "status_detail": "inactivity"},
        "sid0000000000001": {"status": "working"},
        "sid0000000000002": {"status": "terminated"},
    }, notifier)

    changed = await svc.sync_all()

    assert changed == 2
    with db_factory() as db:
        rows = {r.devin_session_id: r for r in db.query(DBSession).all()}
    assert rows["sid0000000000000"].status == SessionStatus.COMPLETED
    assert rows["sid0000000000000"].completed_at is not None
    assert rows["sid0000000000001"].status == SessionStatus.RUNNING
    assert rows["sid0000000000002"].status == SessionStatus.CANCELLED
    assert sorted(n[0] for n in notified) == ["sid0000000000000", "sid0000000000002"]
    assert notified[0][2] in ("suspended (inactivity)", "terminated")
    # already-final row was not fetched
    assert svc.devin_client.get_session.await_count == 3


async def test_refresh_keeps_local_status_when_devin_unreachable(db_factory):
    seed(db_factory, SessionStatus.RUNNING)
    svc = make_service({"sid0000000000000": RuntimeError("timeout")})
    with db_factory() as db:
        rows = db.query(DBSession).all()
        texts = await svc.refresh(db, rows)
        assert texts == ["running"]
        assert rows[0].status == SessionStatus.RUNNING


async def test_blocked_is_reported_but_not_final(db_factory):
    seed(db_factory, SessionStatus.RUNNING)
    svc = make_service({"sid0000000000000": {"status": "blocked", "status_detail": "waiting for user"}})
    with db_factory() as db:
        rows = db.query(DBSession).all()
        texts = await svc.refresh(db, rows)
        assert texts == ["blocked (waiting for user)"]
        assert rows[0].status == SessionStatus.RUNNING


async def test_notifier_failure_does_not_break_sync(db_factory, monkeypatch):
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    seed(db_factory, SessionStatus.RUNNING)
    svc = make_service({"sid0000000000000": {"status": "finished"}}, notifier=AsyncMock(side_effect=RuntimeError("tg down")))
    assert await svc.sync_all() == 1
