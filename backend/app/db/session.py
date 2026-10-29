"""Engine and session factory.

Sessions are handed to request handlers by the ``get_db`` dependency,
which guarantees a rollback on failure and a close in every case.
"""

import ssl
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def _tls_context(ca: str) -> ssl.SSLContext:
    """A context that verifies the server against ``ca`` and its host name.

    ``ca`` is the PEM text itself (as a hosting provider's secret setting
    holds it) or a path to a .pem file.
    """
    pem = ca if "-----BEGIN CERTIFICATE-----" in ca else Path(ca).read_text()
    context = ssl.create_default_context(cadata=pem)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _build_engine() -> Engine:
    url = settings.sqlalchemy_url

    if url.startswith("sqlite"):
        # In-memory SQLite needs one shared connection across threads so
        # the schema created at setup time is visible to the TestClient.
        connect_args = {"check_same_thread": False}
        kwargs = {"connect_args": connect_args, "echo": settings.db_echo}
        if ":memory:" in url or url.endswith("sqlite://"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_connection, _):
            # SQLite ignores FOREIGN KEY clauses unless this is switched
            # on per connection, which would silently weaken the tests.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    connect_args = {}
    if settings.db_ssl_ca:
        connect_args["ssl"] = _tls_context(settings.db_ssl_ca)

    return create_engine(
        url,
        connect_args=connect_args,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        pool_recycle=settings.db_pool_recycle,
        max_overflow=5,
    )


engine: Engine = _build_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
