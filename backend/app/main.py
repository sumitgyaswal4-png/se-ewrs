"""SE-EWRS FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload --port 8000

Interactive API documentation is served at ``/docs`` (Swagger UI) and
``/redoc``.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.session import engine

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("se_ewrs")

DESCRIPTION = """
**Student Engagement & Early Warning Risk System (SE-EWRS)**

A database-driven early-warning system: it aggregates attendance, LMS
engagement and assessment data, scores each enrolment with a transparent
rule-based risk model, raises early-warning alerts and tracks the
interventions staff record against them.

*Database Management Systems course project -- Department of Mathematics.
Team: Mohammad Adnan, Lucky Dhall, Raja, Sumit.*

### Authentication
Call `POST /api/auth/login` with an email and password, then send the
returned token as `Authorization: Bearer <token>` on every other request.
Click **Authorize** in Swagger UI to do this for the whole page.

### Authorisation
Each endpoint requires named permissions which are derived from the
caller's role. `GET /api/auth/permissions` returns the caller's own set.

### A note on the risk score
The score is an early-warning indicator meant to prompt a conversation,
not a judgement about a student. Profiles without enough data are
reported as `INSUFFICIENT_DATA` with the reason attached, rather than
being scored as if the missing data were a zero.
"""

@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "%s %s starting; database dialect=%s",
        settings.app_name,
        settings.app_version,
        engine.dialect.name,
    )
    yield
    logger.info("%s shutting down", settings.app_name)


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version=settings.app_version,
    description=DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "SE-EWRS project team"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["Health"], summary="Service banner")
def root() -> dict:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
    }


@app.get("/health", tags=["Health"], summary="Liveness and database connectivity")
def health() -> dict:
    """Reports whether the API can actually reach its database."""
    database = "unknown"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "connected"
    except Exception as exc:  # noqa: BLE001 - surfaced as a status string
        logger.error("Database health check failed: %s", exc)
        database = "unavailable"

    return {
        "status": "ok" if database == "connected" else "degraded",
        "database": database,
        "dialect": engine.dialect.name,
        # The deployed commit, which Render sets; lets a deploy pipeline
        # confirm the new code is the code answering. None when unset.
        "commit": os.environ.get("RENDER_GIT_COMMIT"),
    }

