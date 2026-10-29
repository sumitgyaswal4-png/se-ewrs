"""Password hashing (Argon2id) and JWT issue / verification."""

import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

# Argon2id with the argon2-cffi defaults, which follow the current
# OWASP password-storage guidance.
_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """Return an Argon2id digest. The plaintext is never stored."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Constant-time-ish verification that swallows malformed hashes."""
    try:
        return _hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A digest no password matches, made with the same parameters as real ones."""
    return _hasher.hash(secrets.token_urlsafe(32))


def verify_dummy_password(plain_password: str) -> None:
    """Spend the time a real verification would, for a login with no account.

    Without this an unknown email returns about ten times faster than a
    wrong password, so response time alone reveals which emails exist.
    """
    verify_password(plain_password, _dummy_hash())


def needs_rehash(password_hash: str) -> bool:
    """True when the stored digest uses outdated Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def create_access_token(
    subject: str,
    role: str,
    user_id: int,
    expires_minutes: Optional[int] = None,
) -> str:
    """Issue a signed JWT carrying the user's id and role."""
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "uid": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expire_minutes)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT. Raises ``jwt.PyJWTError`` on failure."""
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "uid"]},
    )
