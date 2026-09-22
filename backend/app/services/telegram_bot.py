import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from typing import Optional, Dict, Any, List
from telegram import Update, Bot, InlineKeyboardMarkup, Message
from telegram.ext import Application, CommandHandler, CallbackContext
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.database import Session as DBSession, Repository, SessionStatus, TriggerType, DevinMode
from app.services.devin_client import DevinClient
from app.services.session_sync import (
    ACTIVE_STATUSES,
    NEEDS_USER_DETAILS,
    SessionSyncService,
    session_status_text,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandScope:
    """Where a command came from: the chat and, for forum chats, the topic."""
    chat_id: str
    topic_id: Optional[str] = None


DEVIN_SESSION_URL = "https://app.devin.ai/sessions/{}"
DEVIN_SESSION_URL_RE = re.compile(r"https://app\.devin\.ai/sessions/([0-9a-f]{8,})")

REPLY_HINT = "Reply to this message with /done or /cancel to act on the session."

CREATE_USAGE = "❌ Usage: /create [owner/repo] [--mode normal|fast|lite|ultra|fusion] &lt;prompt&gt;"


class TelegramBotService:
    """Service for Telegram bot integration."""
    
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.main_chat_id = settings.telegram_chat_id
        self.bot = Bot(token=self.bot_token)
        self.application = None
        self.devin_client = DevinClient()
        self.session_sync = SessionSyncService(self.devin_client, notifier=self.notify_session_status_changed)
    
    async def start(self):
        """Start the Telegram bot application."""
        self.application = Application.builder().token(self.bot_token).build()
        
        # Register command handlers
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        self.application.add_handler(CommandHandler("done", self.done_command))
        self.application.add_handler(CommandHandler("create", self.create_command))
        self.application.add_handler(CommandHandler("metrics", self.metrics_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_error_handler(self.error_handler)
        
        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram bot started")
    
    async def stop(self):
        """Stop the Telegram bot application."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")
    
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> Dict[str, Any]:
        """
        Send a message to a Telegram chat.
        
        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Optional parse mode (Markdown, HTML)
            reply_markup: Optional inline keyboard markup
            
        Returns:
            Message data
        """
        try:
            message = await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return {"message_id": message.message_id, "chat_id": message.chat_id}
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            raise
    
    async def send_message_to_topic(
        self,
        chat_id: str,
        topic_id: Optional[str],
        text: str,
        parse_mode: Optional[str] = "HTML"
    ) -> Dict[str, Any]:
        """
        Send a message to a specific topic within a Telegram chat.
        
        Args:
            chat_id: Telegram chat ID
            topic_id: Optional topic ID
            text: Message text
            parse_mode: Optional parse mode
            
        Returns:
            Message data
        """
        try:
            if topic_id:
                message = await self.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    text=text,
                    parse_mode=parse_mode
                )
            else:
                message = await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
            return {"message_id": message.message_id, "chat_id": message.chat_id}
        except Exception as e:
            logger.error(f"Failed to send message to topic {topic_id} in chat {chat_id}: {e}")
            raise
    
    async def send_session_notification(
        self,
        chat_id: str,
        topic_id: Optional[str],
        session_data: Dict[str, Any]
    ):
        """
        Send a session status notification.
        
        Args:
            chat_id: Telegram chat ID
            topic_id: Optional topic ID
            session_data: Session data including status, repository, etc.
        """
        status = session_data.get("status", "unknown")
        repo_name = session_data.get("repository_name", "unknown")
        session_id = session_data.get("session_id")
        trigger_type = session_data.get("trigger_type", "manual")
        
        status_emoji = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🛑"
        }.get(status, "❓")
        
        message = f"""
{status_emoji} <b>Session {escape(str(status))}</b>

<b>Repository:</b> {escape(str(repo_name))}
<b>Session ID:</b> {self._session_link(session_id)}
<b>Trigger:</b> {escape(str(trigger_type))}
"""
        
        if status == "running":
            message += f"\n💡 Devin is working on your request...\n\n<i>{REPLY_HINT}</i>"
        elif status == "completed":
            message += "\n🎉 Task completed successfully!"
        elif status == "failed":
            error_msg = session_data.get("error_message", "Unknown error")
            message += f"\n⚠️ Error: {escape(str(error_msg))}"
        
        await self.send_message_to_topic(chat_id, topic_id, message)
    
    async def send_error_notification(
        self,
        chat_id: str,
        topic_id: Optional[str],
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Send an error notification.
        
        Args:
            chat_id: Telegram chat ID
            topic_id: Optional topic ID
            error_message: Error message
            context: Optional context information
        """
        message = f"🚨 <b>Error occurred</b>\n\n{escape(error_message)}"
        
        if context:
            message += "\n\n<b>Context:</b>"
            for key, value in context.items():
                message += f"\n• {escape(str(key))}: {escape(str(value))}"
        
        await self.send_message_to_topic(chat_id, topic_id, message)
    
    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _scope_of(update: Update) -> CommandScope:
        message = update.effective_message
        thread_id = message.message_thread_id if message else None
        return CommandScope(
            chat_id=str(update.effective_chat.id),
            topic_id=str(thread_id) if thread_id else None,
        )
    
    async def _reply(self, scope: CommandScope, text: str) -> None:
        """Reply in the topic the command came from (or the chat root)."""
        await self.send_message_to_topic(scope.chat_id, scope.topic_id, text)
    
    def _chat_repositories(self, db, scope: CommandScope) -> List[Repository]:
        """
        Repositories visible to a command.
        
        If the command was sent inside a topic mapped to a repository, only that
        repository is in scope. Otherwise the main chat sees every repository and
        any other chat sees the repositories mapped to it.
        """
        query = db.query(Repository).filter(Repository.enabled == True)
        if scope.topic_id:
            topic_repos = (
                query.filter(
                    Repository.telegram_chat_id == scope.chat_id,
                    Repository.telegram_topic_id == scope.topic_id,
                )
                .order_by(Repository.github_repo_path)
                .all()
            )
            if topic_repos:
                return topic_repos
        if scope.chat_id != self.main_chat_id:
            query = query.filter(Repository.telegram_chat_id == scope.chat_id)
        return query.order_by(Repository.github_repo_path).all()
    
    async def _authorized(self, update: Update) -> Optional[CommandScope]:
        """Return the command scope if this chat may control the bot, else reply and return None."""
        scope = self._scope_of(update)
        if scope.chat_id == self.main_chat_id:
            return scope
        with SessionLocal() as db:
            known = db.query(Repository).filter(Repository.telegram_chat_id == scope.chat_id).first()
        if known:
            return scope
        logger.warning(f"Ignoring command from unauthorized chat {scope.chat_id}")
        await self._reply(scope, "⛔ This chat is not authorized to control DevinBot.")
        return None
    
    async def error_handler(self, update: object, context: CallbackContext):
        """Report unexpected handler exceptions to the user instead of failing silently."""
        logger.error("Unhandled error in Telegram handler", exc_info=context.error)
        if isinstance(update, Update) and update.effective_chat:
            try:
                await self._reply(self._scope_of(update), "⚠️ Something went wrong, please try again.")
            except Exception as e:
                logger.error(f"Failed to report error to user: {e}")
    
    @staticmethod
    def _session_link(devin_session_id: Optional[str]) -> str:
        if not devin_session_id:
            return "<i>no Devin ID</i>"
        short = escape(devin_session_id[:8])
        return f'<a href="{DEVIN_SESSION_URL.format(escape(devin_session_id))}">{short}</a>'
    
    async def notify_session_status_changed(self, session: DBSession, previous: str) -> None:
        """Post to the repository's chat/topic whenever Devin's reported status changes."""
        repository = session.repository
        current = session_status_text(session)
        last_message = None
        if session.devin_status_detail in NEEDS_USER_DETAILS:
            emoji, headline = "⚠️", "Devin needs your input"
            last_message = await self._last_devin_message(session.devin_session_id)
        else:
            emoji = {
                SessionStatus.COMPLETED: "✅",
                SessionStatus.FAILED: "❌",
                SessionStatus.CANCELLED: "🛑",
            }.get(session.status, "🔄")
            headline = f"Session {current}"
        message = (
            f"{emoji} <b>{escape(headline)}</b> — {self._session_link(session.devin_session_id)}\n"
            f"<b>Repository:</b> {escape(repository.github_repo_path)}\n"
            f"<b>Trigger:</b> {escape(session.trigger_type.value)}\n"
            f"<b>Devin status:</b> {escape(previous)} → {escape(current)}"
        )
        if last_message:
            message += f"\n<b>Devin says:</b> <i>{escape(last_message)}</i>"
        if session.status in ACTIVE_STATUSES:
            message += f"\n\n<i>{REPLY_HINT}</i>"
        await self.send_message_to_topic(repository.telegram_chat_id, repository.telegram_topic_id, message)

    @staticmethod
    def _session_id_from_reply(message: Optional[Message]) -> Optional[str]:
        """Devin session ID referenced by the message a command replies to, if any."""
        replied = message.reply_to_message if message else None
        if not replied:
            return None
        for entity in replied.entities or ():
            if entity.url:
                match = DEVIN_SESSION_URL_RE.search(entity.url)
                if match:
                    return match.group(1)
        match = DEVIN_SESSION_URL_RE.search(replied.text or "")
        return match.group(1) if match else None

    async def _resolve_session(
        self, db, update: Update, scope: CommandScope, args: List[str], usage: str
    ) -> Optional[DBSession]:
        """Find the single session a command targets, from its argument or the replied-to notification."""
        if args:
            raw_id = args[0].strip().rstrip("/").split("/")[-1]
        else:
            raw_id = self._session_id_from_reply(update.effective_message) or ""
            if not raw_id:
                await self._reply(scope, usage)
                return None
        if len(raw_id) < 6:
            await self._reply(scope, "❌ Session ID too short — give at least 6 characters.")
            return None

        repo_ids = [r.id for r in self._chat_repositories(db, scope)]
        matches = (
            db.query(DBSession)
            .filter(
                DBSession.repository_id.in_(repo_ids),
                DBSession.devin_session_id.startswith(raw_id, autoescape=True),
            )
            .all()
        )
        if not matches:
            await self._reply(scope, f"❌ No session found matching <code>{escape(raw_id)}</code>.")
            return None
        if len(matches) > 1:
            await self._reply(scope, f"❌ <code>{escape(raw_id)}</code> is ambiguous — give more characters.")
            return None
        return matches[0]

    async def _last_devin_message(self, devin_session_id: str, limit: int = 400) -> Optional[str]:
        try:
            text = await self.devin_client.get_last_devin_message(devin_session_id)
        except Exception as e:
            logger.warning(f"Could not fetch last message of {devin_session_id}: {e}")
            return None
        if not text:
            return None
        text = " ".join(text.split())
        return text if len(text) <= limit else text[: limit - 1] + "…"
    
    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    async def status_command(self, update: Update, context: CallbackContext):
        """Handle /status: list active sessions with live status from Devin."""
        scope = await self._authorized(update)
        if not scope:
            return
        
        with SessionLocal() as db:
            repos = self._chat_repositories(db, scope)
            repo_ids = [r.id for r in repos]
            sessions = (
                db.query(DBSession)
                .filter(
                    DBSession.repository_id.in_(repo_ids),
                    DBSession.status.in_(ACTIVE_STATUSES),
                )
                .order_by(DBSession.created_at.desc())
                .limit(10)
                .all()
            )
            
            if not sessions:
                await self._reply(scope, "✅ No active sessions.")
                return
            
            lines = [f"🔄 <b>Active sessions ({len(sessions)})</b>", ""]
            statuses = await self.session_sync.refresh(db, sessions)
            for s, live_status in zip(sessions, statuses):
                age = datetime.utcnow() - s.created_at
                lines.append(
                    f"• {self._session_link(s.devin_session_id)} — <b>{escape(s.repository.github_repo_path)}</b>\n"
                    f"  {escape(s.trigger_type.value)} · {escape(live_status)} · {int(age.total_seconds() // 60)}m ago"
                )
            lines.append("")
            lines.append("Cancel with /cancel &lt;session_id&gt; (first 8 chars are enough)")
        
        await self._reply(scope, "\n".join(lines))
    
    async def cancel_command(self, update: Update, context: CallbackContext):
        """Handle /cancel [session_id] (or reply to a notification): terminate a running Devin session."""
        scope = await self._authorized(update)
        if not scope:
            return
        
        with SessionLocal() as db:
            session = await self._resolve_session(
                db, update, scope, list(context.args or []),
                "❌ Usage: /cancel &lt;session_id&gt; — or reply to a session notification with /cancel",
            )
            if not session:
                return
            if session.status not in (SessionStatus.PENDING, SessionStatus.RUNNING):
                await self._reply(
                    scope,
                    f"ℹ️ Session {self._session_link(session.devin_session_id)} is already {escape(session.status.value)}.",
                )
                return
            
            try:
                await self.devin_client.terminate_session(session.devin_session_id)
            except Exception as e:
                logger.error(f"Failed to terminate session {session.devin_session_id}: {e}")
                await self._reply(scope, f"⚠️ Failed to cancel session: {escape(str(e))}")
                return
            
            session.status = SessionStatus.CANCELLED
            session.completed_at = datetime.utcnow()
            db.commit()
            
            await self._reply(
                scope,
                f"🛑 Cancelled session {self._session_link(session.devin_session_id)} "
                f"(<b>{escape(session.repository.github_repo_path)}</b>).",
            )
    
    async def done_command(self, update: Update, context: CallbackContext):
        """Handle /done [session_id] (or reply to a notification): mark a session completed locally.

        Devin has no API to declare a session successful, so this only updates DevinBot's
        own record; the Devin session itself is left untouched (it will suspend on its own).
        """
        scope = await self._authorized(update)
        if not scope:
            return
        
        with SessionLocal() as db:
            session = await self._resolve_session(
                db, update, scope, list(context.args or []),
                "❌ Usage: /done &lt;session_id&gt; — or reply to a session notification with /done",
            )
            if not session:
                return
            if session.status not in ACTIVE_STATUSES:
                await self._reply(
                    scope,
                    f"ℹ️ Session {self._session_link(session.devin_session_id)} is already {escape(session.status.value)}.",
                )
                return
            
            session.status = SessionStatus.COMPLETED
            session.completed_at = datetime.utcnow()
            db.commit()
            
            await self._reply(
                scope,
                f"✅ Marked session {self._session_link(session.devin_session_id)} "
                f"(<b>{escape(session.repository.github_repo_path)}</b>) as completed. "
                f"Devin reports <code>{escape(session_status_text(session))}</code>; the session is left as is.",
            )
    
    async def create_command(self, update: Update, context: CallbackContext):
        """Handle /create [owner/repo] [--mode <mode>] <prompt>: start a new Devin session."""
        scope = await self._authorized(update)
        if not scope:
            return
        
        args = list(context.args or [])
        devin_mode = DevinMode.NORMAL
        if "--mode" in args:
            i = args.index("--mode")
            mode_value = args[i + 1].lower() if i + 1 < len(args) else ""
            try:
                devin_mode = DevinMode(mode_value)
            except ValueError:
                modes = ", ".join(m.value for m in DevinMode)
                await self._reply(scope, f"❌ Unknown mode <code>{escape(mode_value)}</code>. Choose one of: {modes}")
                return
            del args[i:i + 2]
        if not args:
            await self._reply(scope, CREATE_USAGE)
            return
        
        with SessionLocal() as db:
            repos = self._chat_repositories(db, scope)
            if not repos:
                await self._reply(scope, "❌ No repositories are registered for this chat.")
                return
            
            repository = None
            if "/" in args[0]:
                repository = next((r for r in repos if r.github_repo_path.lower() == args[0].lower()), None)
                if not repository:
                    await self._reply(scope, f"❌ Unknown repository <code>{escape(args[0])}</code>.")
                    return
                args = args[1:]
            elif len(repos) == 1:
                repository = repos[0]
            else:
                choices = "\n".join(f"• <code>{escape(r.github_repo_path)}</code>" for r in repos)
                await self._reply(
                    scope,
                    f"❌ Several repositories are registered — specify one:\n{choices}\n\n"
                    "Usage: /create owner/repo [--mode fast] &lt;prompt&gt;",
                )
                return
            
            prompt = " ".join(args).strip()
            if not prompt:
                await self._reply(scope, CREATE_USAGE)
                return
            
            try:
                response = await self.devin_client.create_session(
                    prompt=prompt,
                    repos=[f"https://github.com/{repository.github_repo_path}"],
                    devin_mode=devin_mode,
                    title=f"Telegram: {prompt[:60]}",
                    tags=["telegram"],
                )
            except Exception as e:
                logger.error(f"Failed to create session from Telegram: {e}")
                await self._reply(scope, f"⚠️ Failed to create session: {escape(str(e))}")
                return
            
            devin_session_id = response.get("session_id")
            new_session = DBSession(
                devin_session_id=devin_session_id,
                repository_id=repository.id,
                trigger_type=TriggerType.MANUAL,
                trigger_context=None,
                status=SessionStatus.RUNNING,
                prompt=prompt,
                devin_mode=devin_mode,
            )
            db.add(new_session)
            db.commit()
            
            await self._reply(
                scope,
                f"🚀 <b>Session created</b> for <b>{escape(repository.github_repo_path)}</b>\n"
                f"<b>ID:</b> {self._session_link(devin_session_id)} · <b>Mode:</b> {devin_mode.value}\n"
                f"<b>Prompt:</b> {escape(prompt)}",
            )
    
    async def metrics_command(self, update: Update, context: CallbackContext):
        """Handle /metrics: session counts for the last 24h / 7d plus ACU consumption."""
        scope = await self._authorized(update)
        if not scope:
            return
        
        now = datetime.utcnow()
        with SessionLocal() as db:
            repo_ids = [r.id for r in self._chat_repositories(db, scope)]
            
            def counts(since: datetime) -> Dict[str, int]:
                rows = (
                    db.query(DBSession.status)
                    .filter(DBSession.repository_id.in_(repo_ids), DBSession.created_at >= since)
                    .all()
                )
                result = {s.value: 0 for s in SessionStatus}
                for (status,) in rows:
                    result[status.value] += 1
                return result
            
            day = counts(now - timedelta(hours=24))
            week = counts(now - timedelta(days=7))
        
        def summarize(c: Dict[str, int]) -> str:
            total = sum(c.values())
            rate = (c["completed"] / total * 100) if total else 0.0
            return (
                f"total {total} · running {c['running']} · completed {c['completed']} · "
                f"failed {c['failed']} · cancelled {c['cancelled']} · success {rate:.0f}%"
            )
        
        cost_line = "n/a (Analytics API unavailable)"
        try:
            consumption = await self.devin_client.get_consumption_analytics(
                start_date=(now - timedelta(days=7)).strftime("%Y-%m-%d"),
                end_date=now.strftime("%Y-%m-%d"),
            )
            acus = sum(item.get("acus", 0) or 0 for item in consumption.get("data", []))
            cost_line = f"{acus:.2f} ACUs (7d)"
        except Exception as e:
            logger.warning(f"Analytics API unavailable for /metrics: {e}")
        
        message = (
            "📊 <b>Metrics</b>\n\n"
            f"<b>Last 24h:</b> {escape(summarize(day))}\n"
            f"<b>Last 7d:</b> {escape(summarize(week))}\n"
            f"<b>Cost:</b> {escape(cost_line)}"
        )
        await self._reply(scope, message)
    
    async def help_command(self, update: Update, context: CallbackContext):
        """Handle /help command."""
        scope = self._scope_of(update)
        help_text = """
<b>DevinBot Commands</b>

/status - Show active sessions
/cancel &lt;session_id&gt; - Cancel a running session
/done &lt;session_id&gt; - Mark a session as completed (when Devin is just waiting for you)
  Tip: reply to a session notification with /done or /cancel — no ID needed
/create [owner/repo] [--mode normal|fast|lite|ultra|fusion] &lt;prompt&gt; - Create a new session
/metrics - Show current metrics
/help - Show this help message
"""
        await self._reply(scope, help_text)