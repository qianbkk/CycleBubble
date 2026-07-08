"""CycleBubble 后端配置"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库（本地用 SQLite，Render 也用 SQLite 临时存储）
    database_url: str = "sqlite:///./cyclebubble.db"

    # JWT
    jwt_secret: str = os.getenv("CB_JWT_SECRET", "cyclebubble-secret-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 168  # 7 天

    # DeepSeek API
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # CORS — 允许所有来源（Demo 阶段）
    cors_origins: list[str] = ["*"]

    class Config:
        env_prefix = "CB_"


settings = Settings()
