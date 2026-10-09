"""Typed configuration with explicit mode-specific dotenv precedence."""

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

type AppEnvironment = Literal["development", "testing", "staging", "production"]
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Settings for application initialization; environment variables win over dotenv files."""

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore", env_file_encoding="utf-8")

    name: str = "Python Backend Foundation"
    environment: AppEnvironment = "development"
    log_level: LogLevel = "INFO"
    cors_origins: list[str] = Field(default_factory=list)


def load_settings() -> Settings:
    """Load env/.env, mode and local overrides (in that order)."""
    environment = os.environ.get("APP_ENV", "development")
    if environment not in ("development", "testing", "staging", "production"):
        raise ValueError(f"Unsupported APP_ENV: {environment!r}")

    # Local development starts from the project root; deployed wheels can rely on
    # actual process environment variables without an env/ directory.
    env_dir = Path.cwd() / "env"
    env_files = (
        env_dir / ".env",
        env_dir / f".env.{environment}",
        env_dir / ".env.local",
        env_dir / f".env.{environment}.local",
    )

    return Settings(environment=environment, _env_file=env_files)
