import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str
    DATABASE_URL: str = "sqlite:///../../data/workpilot.db"
    INBOX_DIR: str = "../../data/mock_inbox"
    APPROVAL_THRESHOLD_AMOUNT: float = 10000.0

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()