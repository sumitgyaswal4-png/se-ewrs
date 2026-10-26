"""Application configuration, loaded from the environment / .env file."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every value here can be overridden by an environment variable.

    Credentials and secrets are never hard-coded: see ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application ---------------------------------------------------
    app_name: str = "SE-EWRS API"
    app_version: str = "1.0.0"
    api_prefix: str = "/api"
    debug: bool = False

    # --- database ------------------------------------------------------
    # Set DATABASE_URL to override the assembled MySQL URL entirely
    # (the test-suite uses this to point at SQLite).
    database_url: Optional[str] = None
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "se_ewrs_app"
    db_password: str = ""
    db_name: str = "se_ewrs"
    db_echo: bool = False
    db_pool_size: int = 10
    db_pool_recycle: int = 1800

    # --- authentication -------------------------------------------------
    secret_key: str = Field(
        default="CHANGE-ME-IN-DOT-ENV-this-default-is-for-local-dev-only",
        min_length=16,
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours

    # --- CORS -----------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @computed_field
    @property
    def sqlalchemy_url(self) -> str:
        """Resolved SQLAlchemy connection URL."""
        if self.database_url:
            return self.database_url
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @computed_field
    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @computed_field
    @property
    def is_mysql(self) -> bool:
        return self.sqlalchemy_url.startswith("mysql")


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the .env file is parsed once per process."""
    return Settings()


settings = get_settings()
