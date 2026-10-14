from enum import Enum
import os
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentProfile(str, Enum):
    VPS = "vps"
    RENDER = "render"
    VERCEL = "vercel"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    API_ID: int = Field(default=0)
    API_HASH: str = Field(default="")
    BOT_TOKEN: str = Field(default="")
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///data/archive.db")
    ENCRYPTION_KEY: str = Field(default="")
    REDIS_URL: Optional[str] = Field(default=None)
    WEBHOOK_URL: Optional[str] = Field(default=None)
    WEBHOOK_SECRET: Optional[str] = Field(default=None)
    DEPLOYMENT_PROFILE: Optional[DeploymentProfile] = Field(default=None)

    MAX_CONCURRENT_JOBS: int = Field(default=5, ge=1, le=50)
    MAX_USER_CONCURRENT_JOBS: int = Field(default=2, ge=1, le=10)
    MAX_CONCURRENT_DOWNLOADS: int = Field(default=3, ge=1, le=10)
    MAX_CONCURRENT_UPLOADS: int = Field(default=3, ge=1, le=10)
    PROGRESS_UPDATE_INTERVAL: float = Field(default=3.0, ge=1.0, le=10.0)
    MAX_BATCH_SIZE: int = Field(default=100, ge=1, le=500)
    CHUNK_SIZE_KB: int = Field(default=512, ge=128, le=1024)
    TEMP_DIR: str = Field(default="temp_downloads")
    MIN_DISK_FREE_GB: float = Field(default=1.0)
    ENABLE_CRYPTG: bool = Field(default=True)
    LOG_LEVEL: str = Field(default="INFO")

    @field_validator("DATABASE_URL", mode="after")

    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if not v:
            return "sqlite+aiosqlite:///data/archive.db"
        clean = v.strip("'\"")
        if clean.startswith("postgres://"):
            clean = "postgresql://" + clean[len("postgres://"):]
        if clean.startswith("postgresql://") and not clean.startswith("postgresql+"):
            try:
                import psycopg  # noqa: F401
                clean = "postgresql+psycopg://" + clean[len("postgresql://"):]
            except ImportError:
                clean = "postgresql+asyncpg://" + clean[len("postgresql://"):]
                if "sslmode=" in clean:
                    clean = clean.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer")
        return clean

    @field_validator("ENCRYPTION_KEY", mode="after")
    @classmethod
    def validate_or_generate_key(cls, v: str) -> str:
        if not v or v.strip() == "":
            return Fernet.generate_key().decode()
        return v.strip()

    @property
    def effective_profile(self) -> DeploymentProfile:
        if self.DEPLOYMENT_PROFILE:
            return self.DEPLOYMENT_PROFILE
        if os.getenv("VERCEL") or os.getenv("NOW_REGION"):
            return DeploymentProfile.VERCEL
        if os.getenv("RENDER"):
            return DeploymentProfile.RENDER
        return DeploymentProfile.VPS

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.DATABASE_URL.lower()

    @property
    def temp_path(self) -> Path:
        p = Path(self.TEMP_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
