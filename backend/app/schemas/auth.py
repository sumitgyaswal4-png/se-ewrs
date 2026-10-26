"""Authentication and user-account schemas.

No schema in this module exposes ``password_hash``; the only direction a
password travels is inbound.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import USER_ROLES


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    """Safe projection of a ``users`` row."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    email: EmailStr
    role: str
    dept_id: Optional[int] = None
    phone: Optional[str] = None
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserPublic
    permissions: List[str]
    #: Frontend landing route for this role, so redirection is decided
    #: server-side from the same role map that guards the endpoints.
    home_route: str


class PermissionsResponse(BaseModel):
    role: str
    permissions: List[str]


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str
    dept_id: Optional[int] = None
    phone: Optional[str] = Field(default=None, max_length=20)

    @field_validator("role")
    @classmethod
    def _role_known(cls, v: str) -> str:
        if v not in USER_ROLES:
            raise ValueError(f"role must be one of {', '.join(USER_ROLES)}")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    dept_id: Optional[int] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def _role_known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in USER_ROLES:
            raise ValueError(f"role must be one of {', '.join(USER_ROLES)}")
        return v


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
