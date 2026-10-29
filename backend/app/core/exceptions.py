"""Domain exceptions plus the centralised FastAPI exception handlers.

Error responses always use the same envelope::

    {"detail": "...", "error_code": "..."}

Internal failures are logged in full but reported to the client as a
generic message, so stack traces and SQL never leak through the API.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("se_ewrs")


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "app_error"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ConflictError(AppError):
    """A unique constraint or business rule would be violated."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"


class AuthError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthenticated"


class PermissionError_(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"


class TooManyRequestsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "too_many_requests"

    def __init__(self, detail: str, retry_after: int):
        super().__init__(detail)
        self.retry_after = retry_after


def _envelope(status_code: int, detail: str, error_code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "error_code": error_code},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler to the application."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        response = _envelope(exc.status_code, exc.detail, exc.error_code)
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is not None:
            response.headers["Retry-After"] = str(retry_after)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        headers = getattr(exc, "headers", None) or None
        response = _envelope(exc.status_code, str(exc.detail), "http_error")
        if headers:
            for key, value in headers.items():
                response.headers[key] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError):
        # Report the field path and message, but not the submitted value.
        problems = [
            {
                "field": ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Request validation failed",
                "error_code": "validation_error",
                "problems": problems,
            },
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        logger.warning("Database integrity error: %s", exc.orig)
        return _envelope(
            status.HTTP_409_CONFLICT,
            "The operation conflicts with an existing record or a database "
            "constraint. Check for duplicates and valid references.",
            "integrity_error",
        )

    @app.exception_handler(SQLAlchemyError)
    async def _sqlalchemy(_: Request, exc: SQLAlchemyError):
        logger.exception("Unhandled database error", exc_info=exc)
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "A database error occurred while processing the request.",
            "database_error",
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled server error", exc_info=exc)
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "An internal server error occurred.",
            "internal_error",
        )
