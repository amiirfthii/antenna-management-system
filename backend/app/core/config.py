#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

from pydantic_settings import BaseSettings
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "antenna_management.db"


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Antenna Management System"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True

    # Database (local web: SQLite by default)
    DATABASE_URL: Optional[str] = None
    USE_SQLITE: bool = True
    SQLITE_PATH: str = str(DEFAULT_SQLITE_PATH)

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # CORS (برای API calls از همان origin)
    BACKEND_CORS_ORIGINS: list = ["http://127.0.0.1:8000", "http://localhost:8000"]

    # File uploads
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB

    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_database_url(self) -> str:
        """Return database URL. Local web defaults to existing SQLite file."""
        if self.USE_SQLITE:
            sqlite_path = Path(self.SQLITE_PATH)
            if not sqlite_path.is_absolute():
                sqlite_path = PROJECT_ROOT / sqlite_path
            return f"sqlite:///{sqlite_path.as_posix()}"

        if self.DATABASE_URL:
            return self.DATABASE_URL

        raise ValueError("DATABASE_URL must be set when USE_SQLITE=False")


settings = Settings()
