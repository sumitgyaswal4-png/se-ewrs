"""Risk analysis: the scored table, the per-student explanation and recalculation."""

from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import P_RISK_READ, P_RISK_RECALC
from app.models import (
    Course,
    Enrollment,
    RiskAlert,
    RiskAssessment,
    Student,
)
from app.schemas.common import Page
from app.schemas.risk import (
    RecalculateRequest,
    RecalculateResponse,
    RiskComponent,
    RiskDetail,
    RiskHistoryPoint,
    RiskRow,
)
from app.services import audit, risk_engine
from app.services.queries import risk_summary_select

router = APIRouter(dependencies=[Depends(require_permissions(P_RISK_READ))])

CATEGORY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INSUFFICIENT_DATA": 3}


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)


def _row_from_mapping(row) -> RiskRow:
    return RiskRow(
        enrollment_id=row["enrollment_id"],
        risk_id=row["risk_id"],
        student_pk=row["student_pk"],
        student_id=row["student_id"],
        student_name=row["student_name"],
        student_semester=row["student_semester"],
        dept_id=row["dept_id"],
        dept_code=row["dept_code"],
        course_pk=row["course_pk"],
        course_code=row["course_code"],
        course_name=row["course_name"],
        risk_score=_as_float(row["risk_score"]),
        risk_category=row["risk_category"],
        data_completeness=row["data_completeness"],
        missing_data_reasons=row["missing_data_reasons"],
        contributing_factors=row["contributing_factors"],
        attendance_percentage=_as_float(row["attendance_percentage"])
        if row["attendance_percentage"] is not None
        else _as_float(row["live_attendance_percentage"]),
        avg_assessment_percentage=_as_float(row["avg_assessment_percentage"])
        if row["avg_assessment_percentage"] is not None
        else _as_float(row["live_assessment_percentage"]),
        engagement_score=_as_float(row["engagement_score"]),
        attendance_risk=_as_float(row["attendance_risk"]),
        academic_risk=_as_float(row["academic_risk"]),
        engagement_risk=_as_float(row["engagement_risk"]),
        sessions_held=row["sessions_held"] or 0,
        sessions_attended=row["sessions_attended"] or 0,
        late_submissions=row["late_submissions"] or 0,
        missing_submissions=row["missing_submissions"] or 0,
        graded_assessments=row["graded_assessments"] or 0,
        login_count_30d=row["login_count_30d"] or 0,
        days_since_last_activity=row["days_since_last_activity"],
        last_assessment_date=row["last_assessment_date"],
        last_activity_at=row["last_activity_at"],
        calculated_at=row["calculated_at"],
        model_version=row["model_version"],
        open_alert_id=row["open_alert_id"],
        open_alert_status=row["open_alert_status"],
    )


@router.get("", response_model=Page[RiskRow], summary="Risk-analysis table")
def list_risk(
    db: DbSession,
    page: Pagination,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    course_pk: Annotated[Optional[int], Query()] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    semester: Annotated[Optional[int], Query(ge=1, le=12)] = None,
    risk_category: Annotated[
        Optional[Literal["LOW", "MEDIUM", "HIGH", "INSUFFICIENT_DATA"]], Query()
    ] = None,
    min_score: Annotated[Optional[float], Query(ge=0, le=100)] = None,
    has_open_alert: Annotated[Optional[bool], Query()] = None,
    sort_by: Annotated[
        Literal["risk_score", "student_id", "student_name", "course_code", "calculated_at"],
        Query(),
    ] = "risk_score",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> Page[RiskRow]:
    """Latest risk score per (student, course) with the supporting figures."""
    stmt = risk_summary_select().where(Enrollment.status == "ACTIVE")

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Student.student_id.ilike(pattern),
                Student.full_name.ilike(pattern),
                Course.course_code.ilike(pattern),
            )
        )
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    if dept_id is not None:
        stmt = stmt.where(Student.dept_id == dept_id)
    if semester is not None:
        stmt = stmt.where(Student.semester == semester)

    subq = stmt.subquery("risk_rows")
    outer = select(subq)
    if risk_category:
        outer = outer.where(subq.c.risk_category == risk_category)
    if min_score is not None:
        outer = outer.where(subq.c.risk_score >= min_score)
    if has_open_alert is True:
        outer = outer.where(subq.c.open_alert_id.is_not(None))
    elif has_open_alert is False:
        outer = outer.where(subq.c.open_alert_id.is_(None))

    total = db.execute(select(func.count()).select_from(outer.subquery())).scalar_one()

    column = subq.c[sort_by]
    # NULL scores (unscored profiles) always sort last, whichever direction.
    order = [column.is_(None)]
    order.append(column.desc() if sort_dir == "desc" else column.asc())
    rows = db.execute(outer.order_by(*order).offset(page.offset).limit(page.limit)).mappings()

    return Page.build(
        [_row_from_mapping(r) for r in rows], total, page.page, page.page_size
    )


@router.post(
    "/recalculate",
    response_model=RecalculateResponse,
    dependencies=[Depends(require_permissions(P_RISK_RECALC))],
    summary="Recalculate risk scores and reconcile alerts",
)
def recalculate(
    payload: RecalculateRequest, actor: CurrentUser, db: DbSession
) -> RecalculateResponse:
    """Re-score enrolments and raise, refresh or auto-close their alerts.

    Scope is one enrolment, one course, or every active enrolment. The
    whole run is a single transaction.
    """
    if payload.enrollment_id is not None and payload.course_pk is not None:
        raise ValidationError("Provide either enrollment_id or course_pk, not both")

    before = _alert_snapshot(db)

    if payload.enrollment_id is not None:
        if db.get(Enrollment, payload.enrollment_id) is None:
            raise NotFoundError(f"Enrolment {payload.enrollment_id} was not found")
        risk_engine.recalculate_enrollment(db, payload.enrollment_id, actor.user_id)
        processed = 1
    else:
        if payload.course_pk is not None and db.get(Course, payload.course_pk) is None:
            raise NotFoundError(f"Course {payload.course_pk} was not found")
        processed = risk_engine.recalculate_all(db, payload.course_pk, actor.user_id)

    after = _alert_snapshot(db)
    opened = max(after["total"] - before["total"], 0)
    resolved = max(after["resolved"] - before["resolved"], 0)
    updated = max(after["open"] - (before["open"] + opened - resolved), 0)

    audit.record(
        db,
        action="RECALCULATE",
        entity_type="risk_assessments",
        entity_id=payload.course_pk or payload.enrollment_id or "ALL",
        user_id=actor.user_id,
        new_values={"enrollments_processed": processed},
        commit=True,
    )

    return RecalculateResponse(
        enrollments_processed=processed,
        alerts_opened=opened,
        alerts_updated=updated,
        alerts_auto_resolved=resolved,
        detail=(
            f"Recalculated {processed} enrolment(s): {opened} new alert(s), "
            f"{resolved} auto-resolved."
        ),
    )


@router.get(
    "/{enrollment_id}",
    response_model=RiskDetail,
    summary="Full risk explanation for one enrolment",
)
def risk_detail(enrollment_id: int, db: DbSession) -> RiskDetail:
    """Shows how the score was built, including which inputs were missing.

    When a component has no supporting data its weight is redistributed
    across the components that do -- ``effective_weight`` is the weight
    actually applied, and the two sets of numbers are both returned so
    the re-normalisation is visible rather than implied.
    """
    row = db.execute(
        risk_summary_select().where(Enrollment.enrollment_id == enrollment_id)
    ).mappings().one_or_none()
    if row is None:
        raise NotFoundError(f"Enrolment {enrollment_id} was not found")

    risk_row = _row_from_mapping(row)
    cfg = risk_engine.RiskConfig.from_db(db)

    # Recompute live so the breakdown always matches the current data,
    # even if the stored row predates the newest attendance entry.
    metrics = risk_engine.collect_metrics(db, enrollment_id, cfg)
    live = risk_engine.compute_risk(metrics, cfg)

    specs = [
        ("Attendance", cfg.weight_attendance, live.attendance_risk, live.attendance_percentage,
         "attendance" ),
        ("Academic", cfg.weight_academic, live.academic_risk, live.avg_assessment_percentage,
         "academic"),
        ("Engagement", cfg.weight_engagement, live.engagement_risk, live.engagement_score,
         "engagement"),
    ]
    available_weight = sum(w for _, w, risk, _, _ in specs if risk is not None)

    components: List[RiskComponent] = []
    for name, weight, risk_value, observed, key in specs:
        available = risk_value is not None
        effective = float(weight / available_weight) if available and available_weight else 0.0
        if key == "attendance":
            label = (
                f"{observed}% attended ({metrics.sessions_attended}/{metrics.sessions_held} sessions)"
                if available
                else f"{metrics.sessions_held} of {cfg.min_sessions} required sessions recorded"
            )
            reason = None if available else "Not enough attendance sessions recorded yet"
        elif key == "academic":
            label = (
                f"{observed}% average across {metrics.graded_assessments} graded assessment(s)"
                if available
                else f"{metrics.graded_assessments} graded assessment(s) on record"
            )
            reason = None if available else "No graded assessment yet -- not counted as a zero"
        else:
            label = (
                f"Engagement score {observed}/100"
                if available
                else "No LMS activity or assessment records"
            )
            reason = None if available else "No engagement signal available yet"

        components.append(
            RiskComponent(
                name=name,
                observed_value=float(observed) if observed is not None else None,
                observed_label=label,
                risk_value=float(risk_value) if available else None,
                weight=float(weight),
                effective_weight=round(effective, 4),
                contribution=round(float(risk_value) * effective, 2) if available else None,
                available=available,
                unavailable_reason=reason,
            )
        )

    history = [
        RiskHistoryPoint(
            calculated_at=h.calculated_at,
            risk_score=_as_float(h.risk_score),
            risk_category=h.risk_category,
            attendance_percentage=_as_float(h.attendance_percentage),
            avg_assessment_percentage=_as_float(h.avg_assessment_percentage),
            engagement_score=_as_float(h.engagement_score),
        )
        for h in db.execute(
            select(RiskAssessment)
            .where(RiskAssessment.enrollment_id == enrollment_id)
            .order_by(RiskAssessment.calculated_at)
            .limit(50)
        ).scalars()
    ]

    # Surface the live recomputation when no risk run has been stored yet.
    if risk_row.risk_id is None:
        risk_row.risk_score = _as_float(live.risk_score)
        risk_row.risk_category = live.risk_category
        risk_row.data_completeness = live.data_completeness
        risk_row.missing_data_reasons = live.missing_data_reasons
        risk_row.contributing_factors = live.contributing_factors
        risk_row.engagement_score = _as_float(live.engagement_score)
        risk_row.attendance_risk = _as_float(live.attendance_risk)
        risk_row.academic_risk = _as_float(live.academic_risk)
        risk_row.engagement_risk = _as_float(live.engagement_risk)
        risk_row.model_version = cfg.model_version

    return RiskDetail(
        row=risk_row,
        components=components,
        engagement_breakdown=live.engagement_breakdown,
        thresholds={
            "medium": cfg.threshold_medium,
            "high": cfg.threshold_high,
            "alert_min_score": cfg.alert_min_score,
        },
        weights={
            "attendance": float(cfg.weight_attendance),
            "academic": float(cfg.weight_academic),
            "engagement": float(cfg.weight_engagement),
        },
        history=history,
    )


@router.get(
    "/{enrollment_id}/history",
    response_model=List[RiskHistoryPoint],
    summary="Risk score history for one enrolment",
)
def risk_history(
    enrollment_id: int,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> List[RiskHistoryPoint]:
    if db.get(Enrollment, enrollment_id) is None:
        raise NotFoundError(f"Enrolment {enrollment_id} was not found")
    return [
        RiskHistoryPoint(
            calculated_at=h.calculated_at,
            risk_score=_as_float(h.risk_score),
            risk_category=h.risk_category,
            attendance_percentage=_as_float(h.attendance_percentage),
            avg_assessment_percentage=_as_float(h.avg_assessment_percentage),
            engagement_score=_as_float(h.engagement_score),
        )
        for h in db.execute(
            select(RiskAssessment)
            .where(RiskAssessment.enrollment_id == enrollment_id)
            .order_by(RiskAssessment.calculated_at.desc())
            .limit(limit)
        ).scalars()
    ][::-1]


def _alert_snapshot(db: DbSession) -> dict:
    total = db.execute(select(func.count()).select_from(RiskAlert)).scalar_one()
    resolved = db.execute(
        select(func.count()).select_from(RiskAlert).where(RiskAlert.status == "RESOLVED")
    ).scalar_one()
    return {"total": total, "resolved": resolved, "open": total - resolved}
