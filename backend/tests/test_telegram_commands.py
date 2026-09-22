from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import DevinMode, Repository, Session as DBSession, SessionStatus, TriggerType
from app.services import telegram_bot
from app.services.telegram_bot import CommandScope, TelegramBotService

MAIN_CHAT = "1000"


def update(chat_id=MAIN_CHAT, topic_id=None, reply_to=None):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=int(chat_id)),
        effective_message=SimpleNamespace(
            message_thread_id=int(topic_id) if topic_id else None,
            reply_to_message=reply_to,
        ),
    )


def notification(devin_id=None, text="⚠️ Devin needs your input — abcdef00", link_in_entity=True):
    """A fake previously-sent bot message; the session link lives in a text_link entity like real ones."""
    entities = []
    if devin_id and link_in_entity:
        entities.append(SimpleNamespace(url=f"https://app.devin.ai/sessions/{devin_id}"))
    elif devin_id:
        text += f" https://app.devin.ai/sessions/{devin_id}"
    return SimpleNamespace(text=text, entities=entities)


def ctx(*args):
    return SimpleNamespace(args=list(args))


class Harness:
    def __init__(self, db_factory):
        self.db_factory = db_factory
        self.svc = TelegramBotService()
        self.svc.devin_client = MagicMock()
        self.svc.session_sync.devin_client = self.svc.devin_client
        self.svc.devin_client.get_session = AsyncMock(return_value={"status": "running", "status_detail": "working"})
        self.svc.devin_client.get_last_devin_message = AsyncMock(return_value=None)
        self.svc.devin_client.terminate_session = AsyncMock(return_value={})
        self.svc.devin_client.create_session = AsyncMock(return_value={"session_id": "cafebabe12345678"})
        self.svc.devin_client.get_consumption_analytics = AsyncMock(side_effect=RuntimeError("401"))
        self.replies = []

        async def capture(scope, text):
            self.replies.append((scope, text))

        self.svc._reply = capture
        self.svc.send_message_to_topic = AsyncMock(return_value={})

    def repo(self, path, chat_id=MAIN_CHAT, topic_id=None, enabled=True):
        with self.db_factory() as db:
            r = Repository(
                github_repo_path=path, telegram_chat_id=chat_id, telegram_topic_id=topic_id,
                devin_org_id="org", webhook_secret="s", enabled=enabled,
            )
            db.add(r)
            db.commit()
            return r

    def session(self, repository, devin_id, status=SessionStatus.RUNNING):
        with self.db_factory() as db:
            s = DBSession(
                devin_session_id=devin_id, repository_id=repository.id, trigger_type=TriggerType.ISSUE,
                status=status, prompt="p", devin_mode=DevinMode.NORMAL, created_at=datetime.utcnow(),
            )
            db.add(s)
            db.commit()
            return s

    def reload(self, s):
        with self.db_factory() as db:
            return db.get(DBSession, s.id)

    @property
    def text(self):
        return self.replies[-1][1]


@pytest.fixture
def h(db_factory, monkeypatch):
    monkeypatch.setattr(telegram_bot, "SessionLocal", db_factory)
    return Harness(db_factory)


# --- authorization / routing --------------------------------------------------

async def test_unknown_chat_is_rejected(h):
    h.repo("o/r")
    await h.svc.status_command(update(chat_id="9999"), ctx())
    assert len(h.replies) == 1 and "not authorized" in h.text


async def test_mapped_chat_is_allowed(h):
    h.repo("o/r", chat_id="2000")
    await h.svc.status_command(update(chat_id="2000"), ctx())
    assert "No active sessions" in h.text


async def test_reply_goes_to_originating_topic(h):
    h.repo("o/r", topic_id="77")
    await h.svc.status_command(update(topic_id="77"), ctx())
    assert h.replies[0][0] == CommandScope(chat_id=MAIN_CHAT, topic_id="77")


# --- /status -----------------------------------------------------------------

async def test_status_scoped_to_topic_repo(h):
    r1, r2 = h.repo("o/one", topic_id="11"), h.repo("o/two", topic_id="22")
    h.session(r1, "aaaaaaaa11111111")
    h.session(r2, "bbbbbbbb22222222")
    await h.svc.status_command(update(topic_id="11"), ctx())
    assert "o/one" in h.text and "o/two" not in h.text
    assert "running / working" in h.text


async def test_status_main_chat_sees_all_repos(h):
    r1, r2 = h.repo("o/one", topic_id="11"), h.repo("o/two", topic_id="22")
    h.session(r1, "aaaaaaaa11111111")
    h.session(r2, "bbbbbbbb22222222")
    await h.svc.status_command(update(), ctx())
    assert "o/one" in h.text and "o/two" in h.text


async def test_status_persists_final_status_from_devin(h):
    s = h.session(h.repo("o/r"), "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(return_value={"status": "finished"})
    await h.svc.status_command(update(), ctx())
    s = h.reload(s)
    assert s.status == SessionStatus.COMPLETED and s.completed_at is not None


async def test_status_survives_devin_error(h):
    h.session(h.repo("o/r"), "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(side_effect=RuntimeError("down"))
    await h.svc.status_command(update(), ctx())
    assert "aaaaaaaa" in h.text and "running" in h.text


# --- /cancel -----------------------------------------------------------------

async def test_cancel_requires_min_prefix(h):
    h.repo("o/r")
    await h.svc.cancel_command(update(), ctx("abc"))
    assert "too short" in h.text


async def test_cancel_ambiguous_prefix(h):
    r = h.repo("o/r")
    h.session(r, "abcdef0000000001")
    h.session(r, "abcdef0000000002")
    await h.svc.cancel_command(update(), ctx("abcdef"))
    assert "ambiguous" in h.text
    h.svc.devin_client.terminate_session.assert_not_called()


async def test_cancel_prefix_is_not_a_like_pattern(h):
    h.session(h.repo("o/r"), "abcdef0000000001")
    await h.svc.cancel_command(update(), ctx("%_%_%_"))
    assert "No session" in h.text
    h.svc.devin_client.terminate_session.assert_not_called()


async def test_cancel_already_finished(h):
    h.session(h.repo("o/r"), "abcdef0000000001", status=SessionStatus.COMPLETED)
    await h.svc.cancel_command(update(), ctx("abcdef00"))
    assert "already completed" in h.text
    h.svc.devin_client.terminate_session.assert_not_called()


async def test_cancel_terminates_and_marks_cancelled(h):
    s = h.session(h.repo("o/r"), "abcdef0000000001")
    await h.svc.cancel_command(update(), ctx("https://app.devin.ai/sessions/abcdef0000000001"))
    h.svc.devin_client.terminate_session.assert_awaited_once_with("abcdef0000000001")
    assert h.reload(s).status == SessionStatus.CANCELLED
    assert "Cancelled session" in h.text


async def test_cancel_devin_failure_leaves_row_running(h):
    s = h.session(h.repo("o/r"), "abcdef0000000001")
    h.svc.devin_client.terminate_session = AsyncMock(side_effect=RuntimeError("boom"))
    await h.svc.cancel_command(update(), ctx("abcdef00"))
    assert h.reload(s).status == SessionStatus.RUNNING
    assert "Failed to cancel" in h.text


async def test_cancel_cannot_reach_other_chats_sessions(h):
    h.session(h.repo("o/other", chat_id="2000"), "abcdef0000000001")
    h.repo("o/mine", chat_id="3000")
    await h.svc.cancel_command(update(chat_id="3000"), ctx("abcdef00"))
    assert "No session" in h.text


async def test_cancel_by_replying_to_notification(h):
    s = h.session(h.repo("o/r"), "abcdef0000000001")
    await h.svc.cancel_command(update(reply_to=notification("abcdef0000000001")), ctx())
    h.svc.devin_client.terminate_session.assert_awaited_once_with("abcdef0000000001")
    assert h.reload(s).status == SessionStatus.CANCELLED


async def test_cancel_without_arg_or_reply_shows_usage(h):
    h.repo("o/r")
    await h.svc.cancel_command(update(), ctx())
    assert "Usage" in h.text


# --- /done -------------------------------------------------------------------

async def test_done_by_replying_marks_completed_without_touching_devin(h):
    s = h.session(h.repo("o/r"), "abcdef0000000001")
    await h.svc.done_command(update(reply_to=notification("abcdef0000000001")), ctx())
    s = h.reload(s)
    assert s.status == SessionStatus.COMPLETED and s.completed_at is not None
    h.svc.devin_client.terminate_session.assert_not_called()
    assert "Marked session" in h.text


async def test_done_reads_link_from_plain_text_fallback(h):
    s = h.session(h.repo("o/r"), "abcdef0000000001")
    await h.svc.done_command(
        update(reply_to=notification("abcdef0000000001", link_in_entity=False)), ctx()
    )
    assert h.reload(s).status == SessionStatus.COMPLETED


async def test_done_with_explicit_id(h):
    s = h.session(h.repo("o/r"), "abcdef0000000001")
    await h.svc.done_command(update(), ctx("abcdef00"))
    assert h.reload(s).status == SessionStatus.COMPLETED


async def test_done_reply_without_session_link_shows_usage(h):
    h.session(h.repo("o/r"), "abcdef0000000001")
    await h.svc.done_command(update(reply_to=notification(None)), ctx())
    assert "Usage" in h.text


async def test_done_already_final(h):
    h.session(h.repo("o/r"), "abcdef0000000001", status=SessionStatus.CANCELLED)
    await h.svc.done_command(update(), ctx("abcdef00"))
    assert "already cancelled" in h.text


async def test_done_cannot_reach_other_chats_sessions(h):
    s = h.session(h.repo("o/other", chat_id="2000"), "abcdef0000000001")
    h.repo("o/mine", chat_id="3000")
    await h.svc.done_command(update(chat_id="3000", reply_to=notification("abcdef0000000001")), ctx())
    assert "No session" in h.text and h.reload(s).status == SessionStatus.RUNNING


# --- /create -----------------------------------------------------------------

async def test_create_defaults_to_topic_repo_and_parses_mode(h):
    h.repo("o/one", topic_id="11")
    h.repo("o/two", topic_id="22")
    await h.svc.create_command(update(topic_id="22"), ctx("--mode", "fast", "fix", "the", "bug"))
    kwargs = h.svc.devin_client.create_session.await_args.kwargs
    assert kwargs["repos"] == ["https://github.com/o/two"]
    assert kwargs["devin_mode"] == DevinMode.FAST
    assert kwargs["prompt"] == "fix the bug"
    with h.db_factory() as db:
        new = db.query(DBSession).one()
    assert new.trigger_type == TriggerType.MANUAL
    assert new.devin_session_id == "cafebabe12345678"
    assert new.devin_mode == DevinMode.FAST
    assert "Session created" in h.text


async def test_create_explicit_repo_default_mode(h):
    h.repo("o/one")
    h.repo("o/two")
    await h.svc.create_command(update(), ctx("o/two", "do", "stuff"))
    kwargs = h.svc.devin_client.create_session.await_args.kwargs
    assert kwargs["repos"] == ["https://github.com/o/two"]
    assert kwargs["devin_mode"] == DevinMode.NORMAL


async def test_create_requires_repo_when_ambiguous(h):
    h.repo("o/one")
    h.repo("o/two")
    await h.svc.create_command(update(), ctx("do", "stuff"))
    assert "Several repositories" in h.text
    h.svc.devin_client.create_session.assert_not_called()


async def test_create_rejects_unknown_mode(h):
    h.repo("o/r")
    await h.svc.create_command(update(), ctx("--mode", "turbo", "x"))
    assert "Unknown mode" in h.text
    h.svc.devin_client.create_session.assert_not_called()


async def test_create_usage_without_prompt(h):
    h.repo("o/r")
    await h.svc.create_command(update(), ctx())
    assert "Usage" in h.text


# --- /metrics ----------------------------------------------------------------

async def test_metrics_counts_and_degrades_without_analytics(h):
    r = h.repo("o/r")
    h.session(r, "a" * 16)
    h.session(r, "b" * 16, status=SessionStatus.COMPLETED)
    await h.svc.metrics_command(update(), ctx())
    assert "total 2" in h.text and "completed 1" in h.text and "success 50%" in h.text
    assert "Analytics API unavailable" in h.text


# --- /help -------------------------------------------------------------------

async def test_help_replies_in_topic_without_db(h):
    await h.svc.help_command(update(topic_id="5"), ctx())
    assert h.replies[0][0] == CommandScope(chat_id=MAIN_CHAT, topic_id="5")
    assert "/create [owner/repo]" in h.text and "<b>DevinBot Commands</b>" in h.text


async def test_help_and_usage_are_valid_telegram_html(h):
    """Static texts must only contain Telegram-supported tags (angle brackets escaped)."""
    import re
    await h.svc.help_command(update(), ctx())
    for text in (h.text, telegram_bot.CREATE_USAGE):
        tags = re.findall(r"<(/?)(\w+)", text)
        assert {name for _, name in tags} <= {"b", "i", "a", "code", "pre"}


async def test_status_final_transition_notifies_repo_topic(h):
    r = h.repo("o/r", topic_id="42")
    h.session(r, "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(return_value={"status": "suspended", "status_detail": "inactivity"})
    await h.svc.status_command(update(), ctx())
    h.svc.send_message_to_topic.assert_awaited_once()
    chat_id, topic_id, text = h.svc.send_message_to_topic.await_args.args
    assert (chat_id, topic_id) == (MAIN_CHAT, "42")
    assert "Session suspended / inactivity" in text and "running → suspended / inactivity" in text


async def test_status_waiting_for_user_alerts_repo_topic(h):
    r = h.repo("o/r", topic_id="42")
    h.session(r, "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(return_value={"status": "running", "status_detail": "waiting_for_user"})
    await h.svc.status_command(update(), ctx())
    chat_id, topic_id, text = h.svc.send_message_to_topic.await_args.args
    assert (chat_id, topic_id) == (MAIN_CHAT, "42")
    assert "Devin needs your input" in text and "running / waiting_for_user" in text


async def test_needs_input_alert_includes_devins_last_message(h):
    r = h.repo("o/r", topic_id="42")
    h.session(r, "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(return_value={"status": "running", "status_detail": "waiting_for_user"})
    h.svc.devin_client.get_last_devin_message = AsyncMock(return_value="Review posted on <PR>.\nMain concern: polling.")
    await h.svc.status_command(update(), ctx())
    text = h.svc.send_message_to_topic.await_args.args[2]
    assert "Devin says:" in text and "Review posted on &lt;PR&gt;.\nMain concern: polling." in text
    assert "https://app.devin.ai/sessions/aaaaaaaa11111111" in text
    assert "<b>Task:</b>" in text


async def test_completion_alert_also_includes_devins_last_message(h):
    r = h.repo("o/r", topic_id="42")
    h.session(r, "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(return_value={"status": "suspended", "status_detail": "inactivity"})
    h.svc.devin_client.get_last_devin_message = AsyncMock(return_value="Merged PR #7.")
    await h.svc.status_command(update(), ctx())
    text = h.svc.send_message_to_topic.await_args.args[2]
    assert "Session suspended / inactivity" in text and "Devin says:</b>\nMerged PR #7." in text


async def test_long_devin_message_is_truncated_for_telegram(h):
    r = h.repo("o/r", topic_id="42")
    h.session(r, "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(return_value={"status": "running", "status_detail": "waiting_for_user"})
    h.svc.devin_client.get_last_devin_message = AsyncMock(return_value="x" * 5000)
    await h.svc.status_command(update(), ctx())
    text = h.svc.send_message_to_topic.await_args.args[2]
    assert len(text) < 4096 and text.count("x") == 2999 and "…" in text


async def test_webhook_notification_shows_task_and_full_session_url(h):
    await h.svc.send_session_notification(
        MAIN_CHAT, None,
        {"status": "running", "repository_name": "o/r", "session_id": "aaaaaaaa11111111",
         "trigger_type": "issue", "title": "Issue #4: <JP> support", "url": "https://github.com/o/r/issues/4"},
    )
    text = h.svc.send_message_to_topic.await_args.args[2]
    assert '<a href="https://github.com/o/r/issues/4">Issue #4: &lt;JP&gt; support</a>' in text
    assert ">https://app.devin.ai/sessions/aaaaaaaa11111111</a>" in text


async def test_needs_input_alert_survives_message_fetch_failure(h):
    r = h.repo("o/r", topic_id="42")
    h.session(r, "aaaaaaaa11111111")
    h.svc.devin_client.get_session = AsyncMock(return_value={"status": "running", "status_detail": "waiting_for_user"})
    h.svc.devin_client.get_last_devin_message = AsyncMock(side_effect=RuntimeError("boom"))
    await h.svc.status_command(update(), ctx())
    text = h.svc.send_message_to_topic.await_args.args[2]
    assert "Devin needs your input" in text and "Devin says:" not in text
