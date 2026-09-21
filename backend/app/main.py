import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.session import init_db
from app.services.scheduler import TaskScheduler
from app.services.telegram_bot import TelegramBotService
from app.api.webhooks import github as github_webhook
from app.api.sessions import routes as session_routes
from app.api.metrics import routes as metrics_routes
from app.api.scheduled import routes as scheduled_routes
from app.api.repositories import routes as repository_routes
from app.api.websocket import routes as websocket_routes

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
# httpx logs full request URLs, which include the Telegram bot token
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global services
task_scheduler = None
telegram_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    logger.info("Starting DevinBot backend...")
    
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Initialize and start task scheduler
    global task_scheduler
    task_scheduler = TaskScheduler()
    task_scheduler.start()
    task_scheduler.load_scheduled_tasks()
    logger.info("Task scheduler started")
    
    # Initialize and start Telegram bot
    global telegram_service
    telegram_service = TelegramBotService()
    await telegram_service.start()
    logger.info("Telegram bot started")
    
    # Inject scheduler into scheduled routes
    scheduled_routes.set_task_scheduler(task_scheduler)
    
    yield
    
    # Shutdown
    logger.info("Shutting down DevinBot backend...")
    
    # Stop services
    if task_scheduler:
        task_scheduler.stop()
    if telegram_service:
        await telegram_service.stop()
    
    logger.info("DevinBot backend shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="DevinBot API",
    description="Custom backend for Devin API integration with GitHub webhooks, Telegram bot, and observability dashboard",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(github_webhook.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(session_routes.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(metrics_routes.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(scheduled_routes.router, prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])
app.include_router(repository_routes.router, prefix="/api/repositories", tags=["repositories"])
app.include_router(websocket_routes.router, prefix="/ws", tags=["websocket"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "DevinBot API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "services": {
            "scheduler": task_scheduler is not None,
            "telegram": telegram_service is not None
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )