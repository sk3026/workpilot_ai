import os
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class Settings(BaseSettings):
    GROQ_API_KEY: str
    DATABASE_URL: str = f"sqlite:///{os.path.join(BASE_DIR, 'data', 'workpilot.db')}"
    INBOX_DIR: str = os.path.join(BASE_DIR, "data", "mock_inbox")
    APPROVAL_THRESHOLD_AMOUNT: float = 10000.0
    PORT: int = int(os.getenv("PORT", 8000))
    CORS_ORIGINS: str = "*"

    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, "backend", ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()