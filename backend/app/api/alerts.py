"""Early-warning alerts: the queue, the detail view and status transitions."""

from datetime import date, datetime, timedelta
from typing import Annotated, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import P_ALERTS_READ, P_ALERTS_WRITE
from app.models import (
    AlertStatusHistory,
    Course,
    Enrollment,
    Intervention,
    RiskAlert,
    Student,
    User,
)
from app.schemas.common import Page
from app.schemas.risk import (
    AlertDetail,
    AlertOut,
    AlertPatch,
    AlertStatusRow,
    InterventionOut,
)
from app.services import audit
from app.services.queries import alerts_select_full, risk_summary_select

router = APIRouter(dependencies=[Depends(require_permissions(P_ALERTS_READ))])

#: The legal status graph. RESOLVED is terminal, which is what stops an
#: alert being silently re-opened after it has been closed.
ALLOWED_TRANSITIONS: Dict[str, tuple] = {
    "NEW": ("ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED"),
    "ACKNOWLEDGED": ("IN_PROGRESS", "RESOLVED"),
    "IN_PROGRESS": ("RESOLVED",),
    "RESOLVED": (),
}

#: Roles that may own an alert.
ASSIGNABLE_ROLES = ("INSTRUCTOR", "ADVISOR", "ADMIN")


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)


def _alert_out(row, today: Optional[date] = None) -> AlertOut:
    ref = today or date.today()
    created = row["created_at"]
    out = AlertOut(
        alert_id=row["alert_id"],
        enrollment_id=row["enrollment_id"],
        risk_id=row["risk_id"],
        risk_score=float(row["risk_score"]),
        risk_category=row["risk_category"],
        triggering_factors=row["triggering_factors"],
        status=row["status"],
        assigned_to=row["assigned_to"],
        assignee_name=row["assignee_name"],
        acknowledged_at=row["acknowledged_at"],
        resolved_at=row["resolved_at"],
        created_at=created,
        updated_at=row["updated_at"],
        student_pk=row["student_pk"],
        student_id=row["student_id"],
        student_name=row["student_name"],
        student_semester=row["student_semester"],
        dept_code=row["dept_code"],
        course_pk=row["course_pk"],
        course_code=row["course_code"],
        course_name=row["course_name"],
        intervention_count=row["intervention_count"] or 0,
    )
    out.age_days = (ref - created.date()).days if isinstance(created, datetime) else 0
    return out


@router.get("", response_model=Page[AlertOut], summary="Alert queue")
def list_alerts(
    db: DbSession,
    page: Pagination,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    alert_status: Annotated[
        Optional[Literal["NEW", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED"]], Query()
    ] = None,
    risk_category: Annotated[Optional[Literal["MEDIUM", "HIGH"]], Query()] = None,
    course_pk: Annotated[Optional[int], Query()] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    assigned_to: Annotated[Optional[int], Query()] = None,
    unassigned: Annotated[Optional[bool], Query()] = None,
    only_open: Annotated[bool, Query(description="Hide resolved alerts")] = False,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
    sort_by: Annotated[
        Literal["created_at", "risk_score", "student_id", "status"], Query()
    ] = "created_at",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> Page[AlertOut]:
    stmt = alerts_select_full()

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Student.student_id.ilike(pattern),
                Student.full_name.ilike(pattern),
                Course.course_code.ilike(pattern),
            )
        )
    if alert_status:
        stmt = stmt.where(RiskAlert.status == alert_status)
    if only_open:
        stmt = stmt.where(RiskAlert.status != "RESOLVED")
    if risk_category:
        stmt = stmt.where(RiskAlert.risk_category == risk_category)
    if course_pk is not None:
        stmt = stmt.where(Course.course_pk == course_pk)
    if dept_id is not None:
        stmt = stmt.where(Student.dept_id == dept_id)
    if assigned_to is not None:
        stmt = stmt.where(RiskAlert.assigned_to == assigned_to)
    if unassigned is True:
        stmt = stmt.where(RiskAlert.assigned_to.is_(None))
    if date_from is not None:
        stmt = stmt.where(RiskAlert.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(
            RiskAlert.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    sort_columns = {
        "created_at": RiskAlert.created_at,
        "risk_score": RiskAlert.risk_score,
        "student_id": Student.student_id,
        "status": RiskAlert.status,
    }
    column = sort_columns[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    today = date.today()
    rows = db.execute(stmt.offset(page.offset).limit(page.limit)).mappings()
    return Page.build(
        [_alert_out(r, today) for r in rows], total, page.page, page.page_size
    )


@router.get(
    "/summary",
    summary="Alert counts by status and category, plus the escalation queue",
)
def alerts_summary(db: DbSession) -> dict:
    """Counts computed with GROUP BY, used by the dashboard banner."""
    by_status = {
        row[0]: row[1]
        for row in db.execute(
            select(RiskAlert.status, func.count()).group_by(RiskAlert.status)
        ).all()
    }
    by_category = {
        row[0]: row[1]
        for row in db.execute(
            select(RiskAlert.risk_category, func.count())
            .where(RiskAlert.status != "RESOLVED")
            .group_by(RiskAlert.risk_category)
        ).all()
    }
    unresolved_high = db.execute(
        select(func.count())
        .select_from(RiskAlert)
        .where(RiskAlert.risk_category == "HIGH", RiskAlert.status != "RESOLVED")
    ).scalar_one()
    unassigned = db.execute(
        select(func.count())
        .select_from(RiskAlert)
        .where(RiskAlert.assigned_to.is_(None), RiskAlert.status != "RESOLVED")
    ).scalar_one()
    return {
        "by_status": by_status,
        "open_by_category": by_category,
        "unresolved_high_risk": unresolved_high,
        "unassigned_open": unassigned,
        "total": sum(by_status.values()),
    }


@router.get("/{alert_id}", response_model=AlertDetail, summary="Alert detail")
def get_alert(alert_id: int, db: DbSession) -> AlertDetail:
    row = db.execute(
        alerts_select_full().where(RiskAlert.alert_id == alert_id)
    ).mappings().one_or_none()
    if row is None:
        raise NotFoundError(f"Alert {alert_id} was not found")
    alert = _alert_out(row)

    history = [
        AlertStatusRow(
            history_id=h.history_id,
            old_status=h.old_status,
            new_status=h.new_status,
            changed_by=h.changed_by,
            changed_by_name=name,
            note=h.note,
            changed_at=h.changed_at,
        )
        for h, name in db.execute(
            select(AlertStatusHistory, User.full_name)
            .outerjoin(User, User.user_id == AlertStatusHistory.changed_by)
            .where(AlertStatusHistory.alert_id == alert_id)
            .order_by(AlertStatusHistory.changed_at.desc())
        ).all()
    ]

    interventions = [
        _intervention_out(i, advisor_name)
        for i, advisor_name in db.execute(
            select(Intervention, User.full_name)
            .outerjoin(User, User.user_id == Intervention.assigned_advisor_id)
            .where(Intervention.alert_id == alert_id)
            .order_by(Intervention.contact_date.desc())
        ).all()
    ]

    risk_row = None
    summary = db.execute(
        risk_summary_select().where(Enrollment.enrollment_id == alert.enrollment_id)
    ).mappings().one_or_none()
    if summary is not None:
        from app.api.risk import _row_from_mapping

        risk_row = _row_from_mapping(summary)

    return AlertDetail(
        alert=alert, history=history, interventions=interventions, risk=risk_row
    )


@router.patch(
    "/{alert_id}",
    response_model=AlertOut,
    dependencies=[Depends(require_permissions(P_ALERTS_WRITE))],
    summary="Acknowledge, progress, resolve or reassign an alert",
)
def patch_alert(
    alert_id: int, payload: AlertPatch, actor: CurrentUser, db: DbSession
) -> AlertOut:
    """Status changes are validated against the legal transition graph and
    written together with their history row in one transaction.

    This mirrors ``sp_update_alert_status``. RESOLVED is terminal, so a
    closed alert cannot be reopened -- a fresh alert is raised instead if
    the student's risk rises again.
    """
    alert = db.get(RiskAlert, alert_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} was not found")

    old_status = alert.status
    changed: List[str] = []

    if payload.assigned_to is not None:
        assignee = db.get(User, payload.assigned_to)
        if assignee is None:
            raise ValidationError(f"User {payload.assigned_to} does not exist")
        if not assignee.is_active:
            raise ValidationError(f"{assignee.full_name} is not an active user")
        if assignee.role not in ASSIGNABLE_ROLES:
            raise ValidationError(
                f"{assignee.full_name} has role {assignee.role}; alerts can only be "
                f"assigned to {', '.join(ASSIGNABLE_ROLES)}"
            )
        alert.assigned_to = payload.assigned_to
        changed.append(f"assigned to {assignee.full_name}")

    if payload.status is not None and payload.status != old_status:
        if payload.status not in ALLOWED_TRANSITIONS[old_status]:
            allowed = ALLOWED_TRANSITIONS[old_status]
            raise ConflictError(
                f"Cannot move an alert from {old_status} to {payload.status}. "
                + (
                    f"Allowed next states: {', '.join(allowed)}."
                    if allowed
                    else "A resolved alert is final; a new alert is raised if risk rises again."
                )
            )
        alert.status = payload.status
        now = datetime.now()
        if payload.status == "ACKNOWLEDGED" and alert.acknowledged_at is None:
            alert.acknowledged_at = now
        if payload.status == "RESOLVED":
            alert.resolved_at = now
        db.flush()
        db.add(
            AlertStatusHistory(
                alert_id=alert_id,
                old_status=old_status,
                new_status=payload.status,
                changed_by=actor.user_id,
                note=payload.note,
            )
        )
        changed.append(f"{old_status} -> {payload.status}")

    if not changed:
        raise ValidationError("Nothing to change: the alert is already in that state")

    audit.record(
        db,
        action="UPDATE",
        entity_type="risk_alerts",
        entity_id=alert_id,
        user_id=actor.user_id,
        old_values={"status": old_status},
        new_values={
            "status": alert.status,
            "assigned_to": alert.assigned_to,
            "changes": "; ".join(changed),
        },
    )
    db.commit()

    row = db.execute(
        alerts_select_full().where(RiskAlert.alert_id == alert_id)
    ).mappings().one()
    return _alert_out(row)


def _intervention_out(intervention: Intervention, advisor_name: Optional[str]) -> InterventionOut:
    out = InterventionOut.model_validate(intervention)
    out.advisor_name = advisor_name
    return out
