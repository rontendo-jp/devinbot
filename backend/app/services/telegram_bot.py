import logging
from html import escape
from typing import Optional, Dict, Any
from telegram import Update, Bot, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext
from app.core.config import settings
import asyncio

logger = logging.getLogger(__name__)


class TelegramBotService:
    """Service for Telegram bot integration."""
    
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.main_chat_id = settings.telegram_chat_id
        self.bot = Bot(token=self.bot_token)
        self.application = None
    
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
    
    # Command handlers (to be implemented with actual business logic)
    async def status_command(self, update: Update, context: CallbackContext):
        """Handle /status command."""
        chat_id = update.effective_chat.id
        # This will be connected to the actual session management logic
        await self.send_message(chat_id, "🔄 Fetching session status...")
    
    async def cancel_command(self, update: Update, context: CallbackContext):
        """Handle /cancel command."""
        chat_id = update.effective_chat.id
        args = context.args
        
        if not args:
            await self.send_message(chat_id, "❌ Usage: /cancel &lt;session_id&gt;")
            return
        
        session_id = args[0]
        # This will be connected to the actual session cancellation logic
        await self.send_message(chat_id, f"🛑 Cancelling session {escape(session_id)}...")
    
    async def create_command(self, update: Update, context: CallbackContext):
        """Handle /create command."""
        chat_id = update.effective_chat.id
        args = context.args
        
        if not args:
            await self.send_message(chat_id, "❌ Usage: /create &lt;prompt&gt;")
            return
        
        prompt = " ".join(args)
        # This will be connected to the actual session creation logic
        await self.send_message(chat_id, f"🚀 Creating session with prompt: {escape(prompt)}")
    
    async def metrics_command(self, update: Update, context: CallbackContext):
        """Handle /metrics command."""
        chat_id = update.effective_chat.id
        # This will be connected to the actual metrics logic
        await self.send_message(chat_id, "📊 Fetching metrics...")
    
    async def help_command(self, update: Update, context: CallbackContext):
        """Handle /help command."""
        chat_id = update.effective_chat.id
        help_text = """
<b>DevinBot Commands</b>

/status - Show active sessions
/cancel &lt;session_id&gt; - Cancel a running session
/create &lt;prompt&gt; - Create a new session
/metrics - Show current metrics
/help - Show this help message
"""
        await self.send_message(chat_id, help_text)