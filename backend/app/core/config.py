from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Devin API
    devin_api_key: str = ""
    devin_org_id: str = ""
    
    # GitHub
    github_webhook_secret: str = ""
    github_token: str = ""
    
    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    # Database
    database_url: str = "postgresql://user:password@localhost/devinbot"
    
    # Application
    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    session_sync_interval_seconds: int = 120
    # suspended sessions are still polled (Devin can resume them) until they have sat
    # unchanged this long
    session_sync_suspended_hours: int = 24
    
    # CORS
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()