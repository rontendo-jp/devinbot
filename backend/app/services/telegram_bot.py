import logging
from datetime import datetime, timedelta
from html import escape
from typing import Optional, Dict, Any, List
from telegram import Update, Bot, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.database import Session as DBSession, Repository, SessionStatus, TriggerType, DevinMode
from app.services.devin_client import DevinClient

logger = logging.getLogger(__name__)

DEVIN_SESSION_URL = "https://app.devin.ai/sessions/{}"

# Devin API status -> local status for sessions that are no longer running
FINAL_STATUS_MAP = {
    "finished": SessionStatus.COMPLETED,
    "completed": SessionStatus.COMPLETED,
    "terminated": SessionStatus.CANCELLED,
    "cancelled": SessionStatus.CANCELLED,
    "failed": SessionStatus.FAILED,
    "error": SessionStatus.FAILED,
}


class TelegramBotService:
    """Service for Telegram bot integration."""
    
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.main_chat_id = settings.telegram_chat_id
        self.bot = Bot(token=self.bot_token)
        self.application = None
        self.devin_client = DevinClient()
    
    async def start(self):
        """Start the Telegram bot application."""
        self.application = Application.builder().token(self.bot_token).build()
        
        # Register command handlers
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        self.application.add_handler(CommandHandler("create", self.create_command))
        self.application.add_handler(CommandHandler("metrics", self.metrics_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
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
        session_id = session_data.get("session_id", "unknown")
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
<b>Session ID:</b> {escape(str(session_id))}
<b>Trigger:</b> {escape(str(trigger_type))}
"""
        
        if status == "running":
            message += "\n💡 Devin is working on your request..."
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
    def _chat_repositories(self, db, chat_id: str) -> List[Repository]:
        """Repositories mapped to this chat; the main chat sees all of them."""
        query = db.query(Repository).filter(Repository.enabled == True)
        if chat_id != self.main_chat_id:
            query = query.filter(Repository.telegram_chat_id == chat_id)
        return query.order_by(Repository.github_repo_path).all()
    
    async def _authorized(self, update: Update) -> Optional[str]:
        """Return the chat id if this chat may control the bot, else reply and return None."""
        chat_id = str(update.effective_chat.id)
        if chat_id == self.main_chat_id:
            return chat_id
        with SessionLocal() as db:
            known = db.query(Repository).filter(Repository.telegram_chat_id == chat_id).first()
        if known:
            return chat_id
        logger.warning(f"Ignoring command from unauthorized chat {chat_id}")
        await self.send_message(chat_id, "⛔ This chat is not authorized to control DevinBot.")
        return None
    
    @staticmethod
    def _session_link(devin_session_id: Optional[str]) -> str:
        if not devin_session_id:
            return "<i>no Devin ID</i>"
        short = escape(devin_session_id[:8])
        return f'<a href="{DEVIN_SESSION_URL.format(escape(devin_session_id))}">{short}</a>'
    
    async def _refresh_session(self, db, session: DBSession) -> str:
        """Fetch live status from Devin, persist a final status if reached, return live status text."""
        if not session.devin_session_id:
            return session.status.value
        try:
            live = await self.devin_client.get_session(session.devin_session_id)
        except Exception as e:
            logger.warning(f"Could not refresh session {session.devin_session_id}: {e}")
            return session.status.value
        live_status = str(live.get("status") or session.status.value).lower()
        final = FINAL_STATUS_MAP.get(live_status)
        if final and session.status != final:
            session.status = final
            session.completed_at = datetime.utcnow()
            db.commit()
        detail = live.get("status_detail")
        return f"{live_status} ({detail})" if detail and detail != live_status else live_status
    
    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    async def status_command(self, update: Update, context: CallbackContext):
        """Handle /status: list active sessions with live status from Devin."""
        chat_id = await self._authorized(update)
        if not chat_id:
            return
        
        with SessionLocal() as db:
            repos = self._chat_repositories(db, chat_id)
            repo_ids = [r.id for r in repos]
            sessions = (
                db.query(DBSession)
                .filter(
                    DBSession.repository_id.in_(repo_ids),
                    DBSession.status.in_([SessionStatus.PENDING, SessionStatus.RUNNING]),
                )
                .order_by(DBSession.created_at.desc())
                .limit(10)
                .all()
            )
            
            if not sessions:
                await self.send_message(chat_id, "✅ No active sessions.")
                return
            
            lines = [f"🔄 <b>Active sessions ({len(sessions)})</b>", ""]
            for s in sessions:
                live_status = await self._refresh_session(db, s)
                age = datetime.utcnow() - s.created_at
                lines.append(
                    f"• {self._session_link(s.devin_session_id)} — <b>{escape(s.repository.github_repo_path)}</b>\n"
                    f"  {escape(s.trigger_type.value)} · {escape(live_status)} · {int(age.total_seconds() // 60)}m ago"
                )
            lines.append("")
            lines.append("Cancel with /cancel &lt;session_id&gt; (first 8 chars are enough)")
        
        await self.send_message(chat_id, "\n".join(lines))
    
    async def cancel_command(self, update: Update, context: CallbackContext):
        """Handle /cancel <session_id>: terminate a running Devin session."""
        chat_id = await self._authorized(update)
        if not chat_id:
            return
        
        if not context.args:
            await self.send_message(chat_id, "❌ Usage: /cancel &lt;session_id&gt;")
            return
        
        raw_id = context.args[0].strip().rstrip("/").split("/")[-1]
        if len(raw_id) < 6:
            await self.send_message(chat_id, "❌ Session ID too short — give at least 6 characters.")
            return
        
        with SessionLocal() as db:
            repo_ids = [r.id for r in self._chat_repositories(db, chat_id)]
            matches = (
                db.query(DBSession)
                .filter(
                    DBSession.repository_id.in_(repo_ids),
                    DBSession.devin_session_id.like(f"{raw_id}%"),
                )
                .all()
            )
            if not matches:
                await self.send_message(chat_id, f"❌ No session found matching <code>{escape(raw_id)}</code>.")
                return
            if len(matches) > 1:
                await self.send_message(chat_id, f"❌ <code>{escape(raw_id)}</code> is ambiguous — give more characters.")
                return
            
            session = matches[0]
            if session.status not in (SessionStatus.PENDING, SessionStatus.RUNNING):
                await self.send_message(
                    chat_id,
                    f"ℹ️ Session {self._session_link(session.devin_session_id)} is already {escape(session.status.value)}.",
                )
                return
            
            try:
                await self.devin_client.terminate_session(session.devin_session_id)
            except Exception as e:
                logger.error(f"Failed to terminate session {session.devin_session_id}: {e}")
                await self.send_message(chat_id, f"⚠️ Failed to cancel session: {escape(str(e))}")
                return
            
            session.status = SessionStatus.CANCELLED
            session.completed_at = datetime.utcnow()
            db.commit()
            
            await self.send_message(
                chat_id,
                f"🛑 Cancelled session {self._session_link(session.devin_session_id)} "
                f"(<b>{escape(session.repository.github_repo_path)}</b>).",
            )
    
    async def create_command(self, update: Update, context: CallbackContext):
        """Handle /create [owner/repo] <prompt>: start a new Devin session."""
        chat_id = await self._authorized(update)
        if not chat_id:
            return
        
        args = list(context.args or [])
        if not args:
            await self.send_message(chat_id, "❌ Usage: /create [owner/repo] &lt;prompt&gt;")
            return
        
        with SessionLocal() as db:
            repos = self._chat_repositories(db, chat_id)
            if not repos:
                await self.send_message(chat_id, "❌ No repositories are registered for this chat.")
                return
            
            repository = None
            if "/" in args[0]:
                repository = next((r for r in repos if r.github_repo_path.lower() == args[0].lower()), None)
                if not repository:
                    await self.send_message(chat_id, f"❌ Unknown repository <code>{escape(args[0])}</code>.")
                    return
                args = args[1:]
            elif len(repos) == 1:
                repository = repos[0]
            else:
                choices = "\n".join(f"• <code>{escape(r.github_repo_path)}</code>" for r in repos)
                await self.send_message(
                    chat_id,
                    f"❌ Several repositories are registered — specify one:\n{choices}\n\n"
                    "Usage: /create owner/repo &lt;prompt&gt;",
                )
                return
            
            prompt = " ".join(args).strip()
            if not prompt:
                await self.send_message(chat_id, "❌ Usage: /create [owner/repo] &lt;prompt&gt;")
                return
            
            try:
                response = await self.devin_client.create_session(
                    prompt=prompt,
                    repos=[f"https://github.com/{repository.github_repo_path}"],
                    devin_mode=DevinMode.NORMAL,
                    title=f"Telegram: {prompt[:60]}",
                    tags=["telegram"],
                )
            except Exception as e:
                logger.error(f"Failed to create session from Telegram: {e}")
                await self.send_message(chat_id, f"⚠️ Failed to create session: {escape(str(e))}")
                return
            
            devin_session_id = response.get("session_id")
            new_session = DBSession(
                devin_session_id=devin_session_id,
                repository_id=repository.id,
                trigger_type=TriggerType.MANUAL,
                trigger_context=None,
                status=SessionStatus.RUNNING,
                prompt=prompt,
                devin_mode=DevinMode.NORMAL,
            )
            db.add(new_session)
            db.commit()
            
            await self.send_message(
                chat_id,
                f"🚀 <b>Session created</b> for <b>{escape(repository.github_repo_path)}</b>\n"
                f"<b>ID:</b> {self._session_link(devin_session_id)}\n"
                f"<b>Prompt:</b> {escape(prompt)}",
            )
    
    async def metrics_command(self, update: Update, context: CallbackContext):
        """Handle /metrics: session counts for the last 24h / 7d plus ACU consumption."""
        chat_id = await self._authorized(update)
        if not chat_id:
            return
        
        now = datetime.utcnow()
        with SessionLocal() as db:
            repo_ids = [r.id for r in self._chat_repositories(db, chat_id)]
            
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
        await self.send_message(chat_id, message)
    
    async def help_command(self, update: Update, context: CallbackContext):
        """Handle /help command."""
        chat_id = update.effective_chat.id
        help_text = """
<b>DevinBot Commands</b>

/status - Show active sessions
/cancel &lt;session_id&gt; - Cancel a running session
/create [owner/repo] &lt;prompt&gt; - Create a new session
/metrics - Show current metrics
/help - Show this help message
"""
        await self.send_message(chat_id, help_text)