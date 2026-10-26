"""Shared FastAPI dependencies: the current user and permission guards."""

from typing import Annotated, Optional

import jwt
from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, PermissionError_
from app.core.permissions import permissions_for
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)
    ] = None,
) -> User:
    """Resolve the bearer token to an active user row.

    The error messages here are intentionally uniform so a caller cannot
    distinguish "no such user" from "wrong signature".
    """
    if credentials is None or not credentials.credentials:
        raise AuthError("Authentication credentials were not supplied")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise AuthError("Access token has expired; please sign in again")
    except jwt.PyJWTError:
        raise AuthError("Invalid authentication token")

    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        raise AuthError("Invalid authentication token")

    user = db.execute(select(User).where(User.user_id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("User account is inactive or no longer exists")

    # A role change must take effect immediately, so trust the database
    # row rather than the (possibly stale) role claim inside the token.
    if payload.get("role") != user.role:
        raise AuthError("Token no longer matches the account; please sign in again")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class require_permissions:  # noqa: N801 - used as a dependency factory
    """Dependency enforcing that the caller holds every listed permission.

    Usage::

        @router.post("/", dependencies=[Depends(require_permissions(P_STUDENTS_WRITE))])
    """

    def __init__(self, *permissions: str):
        self.permissions = permissions

    def __call__(self, user: CurrentUser) -> User:
        granted = permissions_for(user.role)
        missing = [p for p in self.permissions if p not in granted]
        if missing:
            raise PermissionError_(
                f"Role {user.role} is not permitted to perform this action "
                f"(requires: {', '.join(missing)})"
            )
        return user


class PageParams:
    """Reusable pagination query parameters."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        page_size: int = Query(20, ge=1, le=200, description="Rows per page"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


Pagination = Annotated[PageParams, Depends(PageParams)]
