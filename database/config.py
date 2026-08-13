import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # Application Profile
    APP_ENV: str = "development"
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"

    # Relational DB (MySQL)
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str = ""
    MYSQL_NAME: str = ""
    SECRET_KEY: str = "yoursecretkey"

    @property
    def DATABASE_URL(self) -> str:
        import urllib.parse
        encoded_password = urllib.parse.quote_plus(self.MYSQL_PASSWORD)
        return f"mysql+asyncmy://{self.MYSQL_USER}:{encoded_password}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_NAME}"

    @property
    def BASE_DATABASE_URL(self) -> str:
        import urllib.parse
        encoded_password = urllib.parse.quote_plus(self.MYSQL_PASSWORD)
        return f"mysql+asyncmy://{self.MYSQL_USER}:{encoded_password}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/"

    # Cache & Message Broker
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # Vector Store (Chroma)
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    VECTOR_COLLECTION_NAME: str = "unit_test_knowledge"

    # SQLite Fallback
    USE_SQLITE_FALLBACK: bool = True
    SQLITE_DB_FILE: str = "database/utgc_agent.db"

    @property
    def SQLITE_DATABASE_URL(self) -> str:
        return f"sqlite+aiosqlite:///{self.SQLITE_DB_FILE}"

    # LLM Providers
    MODE: str = "Cloud"
    MISTRAL_API_KEY: str = ""
    MODEL_NAME: str = "mistral-small:24b"
    MISTRAL_LOCAL_URL: str = ""
    MISTRAL_LOCAL_MODEL: str = "mistral:latest"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
