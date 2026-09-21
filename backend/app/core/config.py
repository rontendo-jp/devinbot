from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Devin API
    devin_api_key: str
    devin_org_id: str
    
    # GitHub
    github_webhook_secret: str
    github_token: str
    
    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str
    
    # Database
    database_url: str = "postgresql://user:password@localhost/devinbot"
    
    # Application
    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    
    # CORS
    cors_origins: list = ["http://localhost:3000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()