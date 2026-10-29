"""Application configuration, loaded from the environment / .env file."""

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

#: HS256 wants at least 256 bits; token_urlsafe(48) gives 64 characters.
MIN_SECRET_KEY_LENGTH = 32
#: Fragments of the placeholder values that have shipped in this repository.
_PLACEHOLDER_MARKERS = ("change-me", "generate-a-new-random-value", "do-not-use-this-one")


class Settings(BaseSettings):
    """Every value here can be overridden by an environment variable.

    Credentials and secrets are never hard-coded: see ``.env.example``.
    """

    model_config = SettingsConfigDict(
        # backend/.env, wherever the server is started from. A relative path
        # would be read from the working directory, and starting uvicorn from
        # the repository root would then miss every setting in the file.
        env_file=Path(__file__).resolve().parents[2] / ".env",
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
    # TLS to a remote MySQL: the CA certificate that signed the server's,
    # given as the PEM text itself or as a path to a .pem file. When set,
    # the connection is encrypted and both the certificate and the host
    # name are verified. Managed services (Aiven, for one) require it.
    db_ssl_ca: Optional[str] = None

    # --- authentication -------------------------------------------------
    # No default: a key written in the source is public, and anyone who has
    # read it can mint an admin token. See _require_a_real_secret_key.
    secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours
    # Failed sign-ins allowed per window before further attempts get a 429
    # (see app/core/rate_limit.py). Successes are never counted.
    login_max_failures_per_account: int = 5
    login_max_failures_per_address: int = 20
    login_failure_window_seconds: int = 900  # 15 minutes
    # How many reverse proxies stand in front of the app. 0 (direct, and
    # local development): the caller is the socket's peer. 1 (one hosting
    # proxy, as on Render): the caller is the right-most X-Forwarded-For
    # entry, the one that proxy added itself. Entries further left are
    # whatever the client chose to send, so they are never trusted.
    trusted_proxy_hops: int = 0

    # --- CORS -----------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @model_validator(mode="after")
    def _require_a_real_secret_key(self) -> "Settings":
        """Refuse to start without a private signing key.

        With DEBUG=true and no key, a random one is made for this process
        only: nothing public signs tokens, and they stop working on restart.
        """
        key = (self.secret_key or "").strip()
        if not key and self.debug:
            logging.getLogger("se_ewrs").warning(
                "SECRET_KEY is not set; DEBUG is on, so a temporary key was "
                "generated. Tokens will not survive a restart."
            )
            self.secret_key = secrets.token_urlsafe(48)
            return self
        if not key:
            raise ValueError(
                "SECRET_KEY is not set. Put one in backend/.env; generate it with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if any(marker in key.lower() for marker in _PLACEHOLDER_MARKERS):
            raise ValueError(
                "SECRET_KEY is still the placeholder from .env.example; replace it "
                "with a generated value"
            )
        if len(key) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters"
            )
        return self

    @computed_field
    @property
    def sqlalchemy_url(self) -> str:
        """Resolved SQLAlchemy connection URL.

        Built with ``URL.create`` so each part is percent-encoded: a password
        holding ``@``, ``:``, ``/`` or ``#`` would otherwise be read as part of
        the host or path and connect somewhere else, or not at all.
        """
        if self.database_url:
            return self.database_url
        return URL.create(
            "mysql+pymysql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

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
