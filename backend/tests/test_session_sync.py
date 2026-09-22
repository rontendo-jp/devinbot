from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import DevinMode, Repository, Session as DBSession, SessionStatus, TriggerType
from app.services import session_sync
from app.services.session_sync import SessionSyncService, summary_status_of


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


def make_service(statuses_by_id, notifier=None, messages_by_id=None):
    client = MagicMock()
    messages_by_id = messages_by_id or {}

    async def get_session(sid):
        result = statuses_by_id[sid]
        if isinstance(result, Exception):
            raise result
        return result

    async def get_last_devin_message(sid):
        result = messages_by_id.get(sid)
        if isinstance(result, Exception):
            raise result
        return result

    client.get_session = AsyncMock(side_effect=get_session)
    client.get_last_devin_message = AsyncMock(side_effect=get_last_devin_message)
    return SessionSyncService(client, notifier=notifier)


async def test_refresh_stores_last_devin_message(db_factory):
    seed(db_factory, SessionStatus.RUNNING, SessionStatus.RUNNING)
    messages = {"sid0000000000000": "Opened https://github.com/o/r/pull/1", "sid0000000000001": RuntimeError("boom")}
    svc = make_service({"sid0000000000000": {"status": "running", "status_detail": "working"},
                        "sid0000000000001": {"status": "running", "status_detail": "working"}}, messages_by_id=messages)
    with db_factory() as db:
        rows = db.query(DBSession).order_by(DBSession.devin_session_id).all()
        await svc.refresh(db, rows)
        db.commit()
    with db_factory() as db:
        rows = {r.devin_session_id: r for r in db.query(DBSession).all()}
    assert rows["sid0000000000000"].last_devin_message == "Opened https://github.com/o/r/pull/1"
    assert rows["sid0000000000001"].last_devin_message is None

    # message updates are persisted even when the status pair is unchanged
    messages["sid0000000000000"] = "PR merged"
    with db_factory() as db:
        rows = db.query(DBSession).order_by(DBSession.devin_session_id).all()
        await svc.refresh(db, rows)
    with db_factory() as db:
        assert db.query(DBSession).filter_by(devin_session_id="sid0000000000000").one().last_devin_message == "PR merged"


@pytest.mark.parametrize("live,expected", [
    ({"status": "running", "status_detail": "working"}, SessionStatus.RUNNING),
    ({"status": "running", "status_detail": "waiting_for_user"}, SessionStatus.RUNNING),
    ({"status": "running", "status_detail": "waiting_for_approval"}, SessionStatus.RUNNING),
    ({"status": "running", "status_detail": "finished"}, SessionStatus.COMPLETED),
    ({"status": "new"}, SessionStatus.RUNNING),
    ({"status": "claimed"}, SessionStatus.RUNNING),
    ({"status": "resuming"}, SessionStatus.RUNNING),
    ({"status": "exit"}, SessionStatus.COMPLETED),
    ({"status": "error"}, SessionStatus.FAILED),
    ({"status": "suspended", "status_detail": "inactivity"}, SessionStatus.COMPLETED),
    ({"status": "suspended", "status_detail": "user_request"}, SessionStatus.COMPLETED),
    ({"status": "suspended", "status_detail": "out_of_credits"}, SessionStatus.FAILED),
    ({"status": "suspended", "status_detail": "error"}, SessionStatus.FAILED),
])
def test_summary_status_follows_documented_enum(live, expected):
    assert summary_status_of(live) == expected


async def test_sync_all_stores_raw_status_and_notifies_on_change(db_factory, monkeypatch):
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    seed(db_factory, SessionStatus.RUNNING, SessionStatus.RUNNING, SessionStatus.RUNNING, SessionStatus.COMPLETED)
    notified = []

    async def notifier(session, previous):
        notified.append((session.devin_session_id, session.status, session.devin_status, session.devin_status_detail, previous))

    svc = make_service({
        "sid0000000000000": {"status": "suspended", "status_detail": "inactivity"},
        "sid0000000000001": {"status": "running", "status_detail": "waiting_for_user"},
        "sid0000000000002": {"status": "exit"},
    }, notifier)

    changed = await svc.sync_all()

    assert changed == 3
    with db_factory() as db:
        rows = {r.devin_session_id: r for r in db.query(DBSession).all()}
    assert rows["sid0000000000000"].status == SessionStatus.COMPLETED
    assert rows["sid0000000000000"].completed_at is not None
    assert (rows["sid0000000000000"].devin_status, rows["sid0000000000000"].devin_status_detail) == ("suspended", "inactivity")
    assert rows["sid0000000000001"].status == SessionStatus.RUNNING
    assert (rows["sid0000000000001"].devin_status, rows["sid0000000000001"].devin_status_detail) == ("running", "waiting_for_user")
    assert rows["sid0000000000002"].status == SessionStatus.COMPLETED
    assert rows["sid0000000000002"].devin_status_detail is None
    assert sorted(n[0] for n in notified) == ["sid0000000000000", "sid0000000000001", "sid0000000000002"]
    assert all(n[4] == "running" for n in notified)  # previous text was the local summary
    # already-final row was not fetched
    assert svc.devin_client.get_session.await_count == 3

    # second pass: nothing changed, nothing notified
    notified.clear()
    assert await svc.sync_all() == 0
    assert notified == []


async def test_refresh_keeps_local_status_when_devin_unreachable(db_factory):
    seed(db_factory, SessionStatus.RUNNING)
    svc = make_service({"sid0000000000000": RuntimeError("timeout")})
    with db_factory() as db:
        rows = db.query(DBSession).all()
        texts = await svc.refresh(db, rows)
        assert texts == ["running"]
        assert rows[0].status == SessionStatus.RUNNING


async def test_waiting_for_user_is_reported_as_is_and_stays_active(db_factory):
    seed(db_factory, SessionStatus.RUNNING)
    svc = make_service({"sid0000000000000": {"status": "running", "status_detail": "waiting_for_user"}})
    with db_factory() as db:
        rows = db.query(DBSession).all()
        texts = await svc.refresh(db, rows)
        assert texts == ["running / waiting_for_user"]
        assert rows[0].status == SessionStatus.RUNNING
        assert rows[0].completed_at is None


async def test_notifier_failure_does_not_break_sync(db_factory, monkeypatch):
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    seed(db_factory, SessionStatus.RUNNING)
    svc = make_service({"sid0000000000000": {"status": "exit"}}, notifier=AsyncMock(side_effect=RuntimeError("tg down")))
    assert await svc.sync_all() == 1
    with db_factory() as db:
        assert db.query(DBSession).one().status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_intermediate_raw_changes_are_stored_but_not_notified(db_factory, monkeypatch):
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    seed(db_factory, SessionStatus.RUNNING)
    notifier = AsyncMock()
    live = {"sid0000000000000": {"status": "new"}}
    svc = make_service(live, notifier=notifier)

    for payload in ({"status": "new"}, {"status": "claimed"}, {"status": "running", "status_detail": "working"}):
        live["sid0000000000000"] = payload
        await svc.sync_all()
    notifier.assert_not_awaited()
    with db_factory() as db:
        row = db.query(DBSession).one()
        assert (row.devin_status, row.devin_status_detail) == ("running", "working")

    live["sid0000000000000"] = {"status": "running", "status_detail": "waiting_for_user"}
    await svc.sync_all()
    live["sid0000000000000"] = {"status": "running", "status_detail": "working"}
    await svc.sync_all()
    live["sid0000000000000"] = {"status": "running", "status_detail": "finished"}
    await svc.sync_all()
    assert [c.args[1] for c in notifier.await_args_list] == [
        "running / working",            # -> waiting_for_user (needs input)
        "running / waiting_for_user",   # -> working (input received)
        "running / working",            # -> finished (coarse status changed)
    ]


@pytest.mark.asyncio
async def test_suspended_sessions_keep_being_polled(db_factory, monkeypatch):
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    seed(db_factory, SessionStatus.RUNNING)
    notifier = AsyncMock()
    live = {"sid0000000000000": {"status": "suspended", "status_detail": "inactivity"}}
    svc = make_service(live, notifier=notifier)
    await svc.sync_all()
    with db_factory() as db:
        assert db.query(DBSession).one().status == SessionStatus.COMPLETED

    live["sid0000000000000"] = {"status": "running", "status_detail": "waiting_for_user"}
    assert await svc.sync_all() == 1
    with db_factory() as db:
        row = db.query(DBSession).one()
        assert row.status == SessionStatus.RUNNING
        assert row.devin_status_detail == "waiting_for_user"
        assert row.completed_at is None
    assert notifier.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_refreshes_notify_once(db_factory, monkeypatch):
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    seed(db_factory, SessionStatus.RUNNING)
    notifier = AsyncMock()
    svc = make_service({"sid0000000000000": {"status": "exit"}}, notifier=notifier)
    import asyncio
    await asyncio.gather(svc.sync_all(), svc.sync_all())
    assert notifier.await_count == 1


@pytest.mark.asyncio
async def test_stale_suspended_sessions_are_not_polled(db_factory, monkeypatch):
    from datetime import timedelta
    monkeypatch.setattr(session_sync, "SessionLocal", db_factory)
    seed(db_factory, SessionStatus.COMPLETED, SessionStatus.COMPLETED)
    with db_factory() as db:
        fresh, stale = db.query(DBSession).order_by(DBSession.devin_session_id).all()
        for row, age in ((fresh, timedelta(hours=1)), (stale, timedelta(days=3))):
            row.devin_status, row.devin_status_detail = "suspended", "inactivity"
            row.updated_at = datetime.utcnow() - age
        db.commit()
    svc = make_service({"sid0000000000000": {"status": "running", "status_detail": "working"}})
    assert await svc.sync_all() == 1
    svc.devin_client.get_session.assert_awaited_once_with("sid0000000000000")
