"""System settings and the audit-log viewer (administrator only)."""

from datetime import date, datetime, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import (
    P_AUDIT_READ,
    P_SETTINGS_READ,
    P_SETTINGS_WRITE,
)
from app.models import AuditLog, SystemSetting, User
from app.schemas.common import Page
from app.services import audit
from app.services.risk_engine import RiskConfig
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()


class SettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    setting_key: str
    setting_value: str
    value_type: str
    description: Optional[str] = None
    updated_at: Optional[datetime] = None


class SettingUpdate(BaseModel):
    setting_value: str = Field(min_length=1, max_length=255)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    old_values: Optional[str] = None
    new_values: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime


#: Keys whose value must parse as a number, with the accepted range.
NUMERIC_RANGES = {
    "risk.weight.attendance": (0.0, 1.0),
    "risk.weight.academic": (0.0, 1.0),
    "risk.weight.engagement": (0.0, 1.0),
    "risk.threshold.medium": (0.0, 100.0),
    "risk.threshold.high": (0.0, 100.0),
    "risk.min_sessions": (0.0, 200.0),
    "risk.min_graded": (0.0, 100.0),
    "risk.activity_window_days": (1.0, 365.0),
    "engagement.target_logins_30d": (1.0, 200.0),
    "alert.min_score": (0.0, 100.0),
}


@router.get(
    "",
    response_model=List[SettingOut],
    dependencies=[Depends(require_permissions(P_SETTINGS_READ))],
    summary="List system settings",
)
def list_settings(db: DbSession) -> List[SettingOut]:
    return [
        SettingOut.model_validate(s)
        for s in db.execute(select(SystemSetting).order_by(SystemSetting.setting_key)).scalars()
    ]


@router.get(
    "/risk-config",
    dependencies=[Depends(require_permissions(P_SETTINGS_READ))],
    summary="The resolved risk model configuration",
)
def risk_config(db: DbSession) -> dict:
    """What the scoring engine will actually use, after defaults."""
    cfg = RiskConfig.from_db(db)
    return {
        "weights": {
            "attendance": float(cfg.weight_attendance),
            "academic": float(cfg.weight_academic),
            "engagement": float(cfg.weight_engagement),
        },
        "thresholds": {"medium": cfg.threshold_medium, "high": cfg.threshold_high},
        "min_sessions": cfg.min_sessions,
        "min_graded": cfg.min_graded,
        "activity_window_days": cfg.activity_window_days,
        "target_logins_30d": cfg.target_logins_30d,
        "alert_min_score": cfg.alert_min_score,
        "model_version": cfg.model_version,
    }


@router.put(
    "/{setting_key}",
    response_model=SettingOut,
    dependencies=[Depends(require_permissions(P_SETTINGS_WRITE))],
    summary="Update one setting",
)
def update_setting(
    setting_key: str, payload: SettingUpdate, actor: CurrentUser, db: DbSession
) -> SettingOut:
    """Changing a risk weight or threshold re-shapes every future score,
    so the value is range-checked and the change is audited."""
    setting = db.get(SystemSetting, setting_key)
    if setting is None:
        raise NotFoundError(f"Setting '{setting_key}' was not found")

    if setting_key in NUMERIC_RANGES:
        low, high = NUMERIC_RANGES[setting_key]
        try:
            value = float(payload.setting_value)
        except ValueError:
            raise ValidationError(f"'{setting_key}' must be a number")
        if not low <= value <= high:
            raise ValidationError(f"'{setting_key}' must be between {low} and {high}")

    if setting_key == "risk.threshold.medium":
        high_threshold = db.get(SystemSetting, "risk.threshold.high")
        if high_threshold and float(payload.setting_value) >= float(high_threshold.setting_value):
            raise ValidationError(
                "The medium threshold must be below the high threshold "
                f"({high_threshold.setting_value})"
            )
    if setting_key == "risk.threshold.high":
        medium = db.get(SystemSetting, "risk.threshold.medium")
        if medium and float(payload.setting_value) <= float(medium.setting_value):
            raise ValidationError(
                f"The high threshold must be above the medium threshold "
                f"({medium.setting_value})"
            )

    before = setting.setting_value
    setting.setting_value = payload.setting_value
    setting.updated_by = actor.user_id
    audit.record(
        db,
        action="UPDATE",
        entity_type="system_settings",
        entity_id=setting_key,
        user_id=actor.user_id,
        old_values={"setting_value": before},
        new_values={"setting_value": payload.setting_value},
    )
    db.commit()
    return SettingOut.model_validate(setting)


@router.get(
    "/audit/logs",
    response_model=Page[AuditOut],
    dependencies=[Depends(require_permissions(P_AUDIT_READ))],
    summary="Browse the audit trail",
)
def audit_logs(
    db: DbSession,
    page: Pagination,
    action: Annotated[Optional[str], Query(max_length=40)] = None,
    entity_type: Annotated[Optional[str], Query(max_length=60)] = None,
    user_id: Annotated[Optional[int], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
) -> Page[AuditOut]:
    stmt = select(AuditLog, User.full_name).outerjoin(
        User, User.user_id == AuditLog.user_id
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(
            AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
        .offset(page.offset)
        .limit(page.limit)
    ).all()

    items = []
    for entry, user_name in rows:
        out = AuditOut.model_validate(entry)
        out.user_name = user_name
        items.append(out)
    return Page.build(items, total, page.page, page.page_size)
