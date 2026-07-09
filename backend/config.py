from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    app_name: str = "CycleBubble API"
    database_url: str = "sqlite:///./cyclebubble.db"
    jwt_secret: str = "dev-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 168  # 7 days
    cors_origins: List[str] = ["*"]

    class Config:
        env_prefix = "CB_"
        env_file = ".env"

settings = Settings()