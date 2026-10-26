"""Authentication and user administration."""

from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.config import settings
from app.core.exceptions import AuthError, ConflictError, NotFoundError, ValidationError
from app.core.permissions import P_USERS_READ, P_USERS_WRITE, permissions_for
from app.core.security import create_access_token, hash_password, needs_rehash, verify_password
from app.models import USER_ROLES, Department, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordChange,
    PermissionsResponse,
    UserCreate,
    UserPublic,
    UserUpdate,
)
from app.schemas.common import Message, Page
from app.services import audit

router = APIRouter()

#: Landing route per role. The server decides this from the same role map
#: that guards the endpoints, so redirection cannot drift from the RBAC.
HOME_ROUTES = {
    "ADMIN": "/dashboard",
    "INSTRUCTOR": "/dashboard",
    "TA": "/attendance",
    "ADVISOR": "/alerts",
    "CHAIR": "/reports",
}


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/login", response_model=LoginResponse, summary="Sign in and receive a JWT")
def login(payload: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    """Verify credentials and issue a signed, expiring access token.

    The same message is returned for an unknown email and a wrong
    password, so the endpoint cannot be used to enumerate accounts.
    """
    user = db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    ).scalar_one_or_none()

    generic = "Incorrect email or password"
    if user is None or not verify_password(payload.password, user.password_hash):
        audit.record(
            db,
            action="LOGIN_FAILED",
            entity_type="users",
            entity_id=payload.email,
            ip_address=_client_ip(request),
            commit=True,
        )
        raise AuthError(generic)

    if not user.is_active:
        raise AuthError("This account has been deactivated. Contact an administrator.")

    # Transparently upgrade the digest if Argon2's parameters have moved on.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    user.last_login_at = datetime.now()
    audit.record(
        db,
        action="LOGIN",
        entity_type="users",
        entity_id=user.user_id,
        user_id=user.user_id,
        ip_address=_client_ip(request),
    )
    db.commit()

    token = create_access_token(subject=user.email, role=user.role, user_id=user.user_id)
    return LoginResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        user=UserPublic.model_validate(user),
        permissions=sorted(permissions_for(user.role)),
        home_route=HOME_ROUTES.get(user.role, "/dashboard"),
    )


@router.get("/me", response_model=UserPublic, summary="Current signed-in user")
def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.get(
    "/permissions",
    response_model=PermissionsResponse,
    summary="Permissions granted to the caller's role",
)
def my_permissions(user: CurrentUser) -> PermissionsResponse:
    """The frontend reads this to build its navigation and hide actions.

    It is a convenience only -- every endpoint enforces the same map.
    """
    return PermissionsResponse(role=user.role, permissions=sorted(permissions_for(user.role)))


@router.post("/change-password", response_model=Message, summary="Change your own password")
def change_password(payload: PasswordChange, user: CurrentUser, db: DbSession) -> Message:
    if not verify_password(payload.current_password, user.password_hash):
        raise AuthError("Current password is incorrect")
    if payload.new_password == payload.current_password:
        raise ValidationError("The new password must differ from the current one")

    user.password_hash = hash_password(payload.new_password)
    audit.record(
        db,
        action="PASSWORD_CHANGE",
        entity_type="users",
        entity_id=user.user_id,
        user_id=user.user_id,
    )
    db.commit()
    return Message(detail="Password updated")


# ---------------------------------------------------------------------------
# User administration
# ---------------------------------------------------------------------------
@router.get(
    "/users",
    response_model=Page[UserPublic],
    dependencies=[Depends(require_permissions(P_USERS_READ))],
    summary="List staff accounts",
)
def list_users(
    db: DbSession,
    page: Pagination,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    role: Annotated[Optional[str], Query()] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    is_active: Annotated[Optional[bool], Query()] = None,
) -> Page[UserPublic]:
    stmt = select(User)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    if role:
        if role not in USER_ROLES:
            raise ValidationError(f"role must be one of {', '.join(USER_ROLES)}")
        stmt = stmt.where(User.role == role)
    if dept_id is not None:
        stmt = stmt.where(User.dept_id == dept_id)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(User.full_name).offset(page.offset).limit(page.limit)
    ).scalars()
    return Page.build(
        [UserPublic.model_validate(u) for u in rows], total, page.page, page.page_size
    )


@router.get(
    "/users/assignable",
    response_model=List[UserPublic],
    summary="Users an alert can be assigned to",
)
def assignable_users(db: DbSession, _: CurrentUser) -> List[UserPublic]:
    """Instructors and advisors -- the roles allowed to own an alert."""
    rows = db.execute(
        select(User)
        .where(User.is_active.is_(True), User.role.in_(("INSTRUCTOR", "ADVISOR", "ADMIN")))
        .order_by(User.full_name)
    ).scalars()
    return [UserPublic.model_validate(u) for u in rows]


@router.post(
    "/users",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_USERS_WRITE))],
    summary="Create a staff account",
)
def create_user(payload: UserCreate, actor: CurrentUser, db: DbSession) -> UserPublic:
    existing = db.execute(
        select(User.user_id).where(func.lower(User.email) == payload.email.lower())
    ).scalar_one_or_none()
    if existing:
        raise ConflictError(f"A user with email {payload.email} already exists")
    if payload.dept_id is not None:
        if not db.get(Department, payload.dept_id):
            raise ValidationError(f"Department {payload.dept_id} does not exist")

    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        dept_id=payload.dept_id,
        phone=payload.phone,
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="users",
        entity_id=user.user_id,
        user_id=actor.user_id,
        new_values={"email": user.email, "role": user.role, "dept_id": user.dept_id},
    )
    db.commit()
    return UserPublic.model_validate(user)


@router.put(
    "/users/{user_id}",
    response_model=UserPublic,
    dependencies=[Depends(require_permissions(P_USERS_WRITE))],
    summary="Update a staff account",
)
def update_user(
    user_id: int, payload: UserUpdate, actor: CurrentUser, db: DbSession
) -> UserPublic:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} was not found")

    if user.user_id == actor.user_id and payload.is_active is False:
        raise ValidationError("You cannot deactivate your own account")

    before = {"role": user.role, "is_active": user.is_active, "dept_id": user.dept_id}
    data = payload.model_dump(exclude_unset=True)

    if "email" in data and data["email"]:
        clash = db.execute(
            select(User.user_id).where(
                func.lower(User.email) == data["email"].lower(), User.user_id != user_id
            )
        ).scalar_one_or_none()
        if clash:
            raise ConflictError(f"A user with email {data['email']} already exists")
        data["email"] = data["email"].lower()
    if data.get("dept_id") is not None and not db.get(Department, data["dept_id"]):
        raise ValidationError(f"Department {data['dept_id']} does not exist")

    for key, value in data.items():
        setattr(user, key, value)

    audit.record(
        db,
        action="UPDATE",
        entity_type="users",
        entity_id=user.user_id,
        user_id=actor.user_id,
        old_values=before,
        new_values={"role": user.role, "is_active": user.is_active, "dept_id": user.dept_id},
    )
    db.commit()
    return UserPublic.model_validate(user)
