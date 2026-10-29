"""The rule-based early-warning risk model.

This module is the application-side twin of
``sp_recalculate_risk_for_enrollment`` in ``database/procedures.sql``.
Both implement the identical rule set, which is specified once in
``docs/database_design.md``:

    Risk Score = 0.35 x Attendance Risk
               + 0.40 x Academic Risk
               + 0.25 x Engagement Risk

    Attendance Risk = 100 - Attendance Percentage
    Academic Risk   = 100 - Average Assessment Percentage
    Engagement Risk = 100 - Engagement Score

Every component is on a 0-100 scale and the final score is clamped to
0-100 and rounded half-up to two decimals.

Missing data is NOT treated as poor performance. A component with no
supporting data is dropped and the remaining weights are re-normalised,
so a student with no graded work yet is not pushed towards "high risk"
by that absence. When fewer than two components are observable the
profile is reported as ``INSUFFICIENT_DATA`` with a human-readable
reason instead of being assigned a risk band.

The score is an early-warning indicator for starting a conversation --
not a judgement about a student.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AlertStatusHistory,
    AssessmentResult,
    AttendanceRecord,
    Enrollment,
    LmsActivityLog,
    RiskAlert,
    RiskAssessment,
    SystemSetting,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")

# Engagement recency bands: (inclusive upper bound in days, penalty).
RECENCY_BANDS: Tuple[Tuple[int, Decimal], ...] = (
    (3, Decimal("0")),
    (7, Decimal("10")),
    (14, Decimal("20")),
    (30, Decimal("35")),
)
RECENCY_PENALTY_BEYOND = Decimal("50")
RECENCY_PENALTY_NEVER = Decimal("50")

MISSING_PENALTY_MAX = Decimal("40")
LATE_PENALTY_MAX = Decimal("20")


def _q2(value: Decimal) -> Decimal:
    """Round half-up to 2 decimals -- matches MySQL ``ROUND(x, 2)``."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q0(value: Decimal) -> int:
    """Round half-up to an integer -- matches MySQL ``ROUND(x)``."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _clamp(value: Decimal, low: Decimal = ZERO, high: Decimal = HUNDRED) -> Decimal:
    return max(low, min(high, value))


def _dec(value) -> Optional[Decimal]:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RiskConfig:
    """Tunable model parameters, mirroring the ``system_settings`` rows."""

    weight_attendance: Decimal = Decimal("0.35")
    weight_academic: Decimal = Decimal("0.40")
    weight_engagement: Decimal = Decimal("0.25")
    threshold_medium: int = 30
    threshold_high: int = 60
    min_sessions: int = 3
    min_graded: int = 1
    activity_window_days: int = 30
    target_logins_30d: int = 12
    alert_min_score: int = 30
    model_version: str = "rule-v1"

    @classmethod
    def from_db(cls, db: Session) -> "RiskConfig":
        rows = {s.setting_key: s.setting_value for s in db.execute(select(SystemSetting)).scalars()}
        defaults = cls()

        def num(key: str, fallback: Decimal) -> Decimal:
            raw = rows.get(key)
            if raw is None:
                return fallback
            # fn_setting_num reads every setting as DECIMAL(10,4), rounding
            # half-up; doing the same here keeps 0.33335 from scoring
            # differently in the two implementations.
            try:
                return Decimal(str(raw)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            except (ArithmeticError, ValueError):
                return fallback

        def integer(key: str, fallback: int) -> int:
            # CAST(... AS SIGNED) rounds, so 30.5 is 31 in SQL; int() would truncate to 30.
            try:
                return _q0(num(key, Decimal(fallback)))
            except (ArithmeticError, ValueError):
                return fallback

        return cls(
            weight_attendance=num("risk.weight.attendance", defaults.weight_attendance),
            weight_academic=num("risk.weight.academic", defaults.weight_academic),
            weight_engagement=num("risk.weight.engagement", defaults.weight_engagement),
            threshold_medium=integer("risk.threshold.medium", defaults.threshold_medium),
            threshold_high=integer("risk.threshold.high", defaults.threshold_high),
            min_sessions=integer("risk.min_sessions", defaults.min_sessions),
            min_graded=integer("risk.min_graded", defaults.min_graded),
            activity_window_days=integer(
                "risk.activity_window_days", defaults.activity_window_days
            ),
            target_logins_30d=integer(
                "engagement.target_logins_30d", defaults.target_logins_30d
            ),
            alert_min_score=integer("alert.min_score", defaults.alert_min_score),
            model_version=str(rows.get("risk.model_version", defaults.model_version)),
        )


# ---------------------------------------------------------------------------
# Inputs and outputs
# ---------------------------------------------------------------------------
@dataclass
class EnrollmentMetrics:
    """Observed facts for one enrolment -- the model's only input."""

    enrollment_id: int = 0
    sessions_held: int = 0
    sessions_attended: int = 0
    attendance_percentage: Optional[Decimal] = None
    results_recorded: int = 0
    graded_assessments: int = 0
    avg_assessment_percentage: Optional[Decimal] = None
    ontime_submissions: int = 0
    late_submissions: int = 0
    missing_submissions: int = 0
    last_assessment_date: Optional[date] = None
    total_activities: int = 0
    login_count_30d: int = 0
    last_activity_at: Optional[datetime] = None
    days_since_last_activity: Optional[int] = None


@dataclass
class RiskResult:
    """The computed risk profile for one enrolment."""

    attendance_percentage: Optional[Decimal] = None
    avg_assessment_percentage: Optional[Decimal] = None
    engagement_score: Optional[Decimal] = None
    attendance_risk: Optional[Decimal] = None
    academic_risk: Optional[Decimal] = None
    engagement_risk: Optional[Decimal] = None
    risk_score: Optional[Decimal] = None
    risk_category: str = "INSUFFICIENT_DATA"
    data_completeness: str = "INSUFFICIENT"
    components_available: int = 0
    missing_data_reasons: Optional[str] = None
    contributing_factors: str = "No adverse factors detected"
    engagement_breakdown: dict = field(default_factory=dict)
    model_version: str = "rule-v1"


# ---------------------------------------------------------------------------
# Pure scoring functions (no database access -- directly unit-testable)
# ---------------------------------------------------------------------------
def compute_engagement_score(
    days_since_last_activity: Optional[int],
    login_count_30d: int,
    missing_submissions: int,
    late_submissions: int,
    results_recorded: int,
    target_logins: int = 12,
) -> Tuple[Decimal, dict]:
    """Engagement Score on 0-100 where 100 is fully engaged.

    ``engagement_score = clamp(100 - (recency + frequency + missing + late), 0, 100)``

    * **recency** -- days since the most recent LMS event:
      never active -> 50, <=3 -> 0, <=7 -> 10, <=14 -> 20, <=30 -> 35, >30 -> 50
    * **frequency** -- logins in the window against the target (default 12):
      >= target -> 0, >= 2/3 target -> 5, >= 1/3 target -> 12, >= 1 -> 20, 0 -> 30
    * **missing** -- ``40 * missing_submissions / results_recorded``
    * **late** -- ``20 * late_submissions / results_recorded``

    The frequency bands use integer cross-multiplication (``logins * 3 >=
    target * 2``) rather than a float ratio, so this function and the SQL
    function ``fn_engagement_score`` can never disagree at a boundary.
    """
    target = max(int(target_logins), 1)
    logins = max(int(login_count_30d), 0)

    # recency penalty
    if days_since_last_activity is None:
        recency = RECENCY_PENALTY_NEVER
    else:
        recency = RECENCY_PENALTY_BEYOND
        for upper, penalty in RECENCY_BANDS:
            if days_since_last_activity <= upper:
                recency = penalty
                break

    # login frequency penalty
    if logins >= target:
        frequency = Decimal("0")
    elif logins * 3 >= target * 2:
        frequency = Decimal("5")
    elif logins * 3 >= target:
        frequency = Decimal("12")
    elif logins >= 1:
        frequency = Decimal("20")
    else:
        frequency = Decimal("30")

    # submission-behaviour penalties
    if results_recorded > 0:
        total = Decimal(results_recorded)
        missing = MISSING_PENALTY_MAX * Decimal(max(missing_submissions, 0)) / total
        late = LATE_PENALTY_MAX * Decimal(max(late_submissions, 0)) / total
    else:
        missing = ZERO
        late = ZERO

    score = _q2(_clamp(HUNDRED - (recency + frequency + missing + late)))
    breakdown = {
        "recency_penalty": float(recency),
        "login_frequency_penalty": float(frequency),
        "missing_submission_penalty": float(_q2(missing)),
        "late_submission_penalty": float(_q2(late)),
        "engagement_score": float(score),
    }
    return score, breakdown


def _build_factors(metrics: EnrollmentMetrics, result: RiskResult, config: RiskConfig) -> str:
    """Human-readable reasons, highest-signal first. Mirrors the SQL."""
    factors: List[str] = []

    if result.attendance_risk is not None and metrics.attendance_percentage is not None:
        if metrics.attendance_percentage < 75:
            factors.append(f"Low attendance ({_q0(metrics.attendance_percentage)}%)")
    if result.academic_risk is not None and metrics.avg_assessment_percentage is not None:
        if metrics.avg_assessment_percentage < 50:
            factors.append(
                f"Weak assessment average ({_q0(metrics.avg_assessment_percentage)}%)"
            )
    if metrics.missing_submissions > 0:
        factors.append(f"{metrics.missing_submissions} missing submission(s)")
    if metrics.late_submissions > 0:
        factors.append(f"{metrics.late_submissions} late submission(s)")

    if metrics.days_since_last_activity is None and metrics.total_activities == 0:
        factors.append("No LMS activity on record")
    elif (
        metrics.days_since_last_activity is not None
        and metrics.days_since_last_activity > 14
    ):
        factors.append(f"No LMS activity for {metrics.days_since_last_activity} days")

    if metrics.total_activities > 0 and metrics.login_count_30d * 3 < config.target_logins_30d:
        factors.append(f"Low login frequency ({metrics.login_count_30d} in 30 days)")

    return "; ".join(factors) if factors else "No adverse factors detected"


def compute_risk(metrics: EnrollmentMetrics, config: Optional[RiskConfig] = None) -> RiskResult:
    """Turn observed metrics into a risk profile. Pure and deterministic."""
    cfg = config or RiskConfig()
    result = RiskResult(model_version=cfg.model_version)
    reasons: List[str] = []

    available_weight = ZERO
    weighted_sum = ZERO
    components = 0

    # --- component 1: attendance ------------------------------------------
    att_pct = _dec(metrics.attendance_percentage)
    result.attendance_percentage = att_pct
    if metrics.sessions_held >= cfg.min_sessions and att_pct is not None:
        result.attendance_risk = _q2(HUNDRED - att_pct)
        available_weight += cfg.weight_attendance
        weighted_sum += cfg.weight_attendance * result.attendance_risk
        components += 1
    else:
        reasons.append(
            f"Attendance component skipped: only {metrics.sessions_held} of "
            f"{cfg.min_sessions} required sessions recorded"
        )

    # --- component 2: academic --------------------------------------------
    aca_pct = _dec(metrics.avg_assessment_percentage)
    result.avg_assessment_percentage = aca_pct
    if metrics.graded_assessments >= cfg.min_graded and aca_pct is not None:
        result.academic_risk = _q2(HUNDRED - aca_pct)
        available_weight += cfg.weight_academic
        weighted_sum += cfg.weight_academic * result.academic_risk
        components += 1
    else:
        reasons.append(
            f"Academic component skipped: {metrics.graded_assessments} graded "
            f"assessment(s) on record"
        )

    # --- component 3: engagement ------------------------------------------
    if metrics.total_activities > 0 or metrics.results_recorded > 0:
        score, breakdown = compute_engagement_score(
            metrics.days_since_last_activity,
            metrics.login_count_30d,
            metrics.missing_submissions,
            metrics.late_submissions,
            metrics.results_recorded,
            cfg.target_logins_30d,
        )
        result.engagement_score = score
        result.engagement_breakdown = breakdown
        result.engagement_risk = _q2(HUNDRED - score)
        available_weight += cfg.weight_engagement
        weighted_sum += cfg.weight_engagement * result.engagement_risk
        components += 1
    else:
        reasons.append(
            "Engagement component skipped: no LMS activity or assessment records"
        )

    # --- weighted, re-normalised score ------------------------------------
    if available_weight > 0:
        result.risk_score = _q2(_clamp(weighted_sum / available_weight))

    result.components_available = components
    result.data_completeness = (
        "COMPLETE" if components >= 3 else "PARTIAL" if components == 2 else "INSUFFICIENT"
    )

    if result.risk_score is None or result.data_completeness == "INSUFFICIENT":
        result.risk_category = "INSUFFICIENT_DATA"
    elif result.risk_score >= cfg.threshold_high:
        result.risk_category = "HIGH"
    elif result.risk_score >= cfg.threshold_medium:
        result.risk_category = "MEDIUM"
    else:
        result.risk_category = "LOW"

    if reasons:
        result.missing_data_reasons = "; ".join(reasons)
    elif result.data_completeness != "COMPLETE":
        result.missing_data_reasons = "One or more risk components had no supporting data"

    result.contributing_factors = _build_factors(metrics, result, cfg)
    return result


# ---------------------------------------------------------------------------
# Metric collection -- mirrors v_enrollment_* in database/views.sql
# ---------------------------------------------------------------------------
def collect_metrics(
    db: Session, enrollment_id: int, config: Optional[RiskConfig] = None
) -> EnrollmentMetrics:
    """Aggregate the raw tables into the model's inputs for one enrolment."""
    cfg = config or RiskConfig()
    today = date.today()
    window_start = datetime.combine(today - timedelta(days=cfg.activity_window_days), datetime.min.time())
    metrics = EnrollmentMetrics(enrollment_id=enrollment_id)

    # attendance: LATE counts as attended, EXCUSED leaves the denominator
    att = db.execute(
        select(
            func.count(AttendanceRecord.attendance_id),
            func.sum(case((AttendanceRecord.status != "EXCUSED", 1), else_=0)),
            func.sum(case((AttendanceRecord.status.in_(("PRESENT", "LATE")), 1), else_=0)),
        ).where(AttendanceRecord.enrollment_id == enrollment_id)
    ).one()
    metrics.sessions_held = int(att[1] or 0)
    metrics.sessions_attended = int(att[2] or 0)
    if metrics.sessions_held > 0:
        metrics.attendance_percentage = _q2(
            HUNDRED * Decimal(metrics.sessions_attended) / Decimal(metrics.sessions_held)
        )

    # academics: only graded rows feed the average
    graded_pct = case((AssessmentResult.marks_obtained.is_not(None), AssessmentResult.percentage))
    aca = db.execute(
        select(
            func.count(AssessmentResult.result_id),
            func.sum(case((AssessmentResult.marks_obtained.is_not(None), 1), else_=0)),
            func.avg(graded_pct),
            func.sum(case((AssessmentResult.submission_status == "ON_TIME", 1), else_=0)),
            func.sum(case((AssessmentResult.submission_status == "LATE", 1), else_=0)),
            func.sum(case((AssessmentResult.submission_status == "MISSING", 1), else_=0)),
            # Kept as a DATETIME and converted in Python: SQLite's
            # CAST(x AS DATE) yields a numeric, not a date.
            func.max(
                case(
                    (
                        AssessmentResult.marks_obtained.is_not(None),
                        func.coalesce(
                            AssessmentResult.graded_at,
                            AssessmentResult.submitted_at,
                            AssessmentResult.created_at,
                        ),
                    )
                )
            ),
        ).where(AssessmentResult.enrollment_id == enrollment_id)
    ).one()
    metrics.results_recorded = int(aca[0] or 0)
    metrics.graded_assessments = int(aca[1] or 0)
    metrics.avg_assessment_percentage = _q2(_dec(aca[2])) if aca[2] is not None else None
    metrics.ontime_submissions = int(aca[3] or 0)
    metrics.late_submissions = int(aca[4] or 0)
    metrics.missing_submissions = int(aca[5] or 0)
    last_assess = aca[6]
    if isinstance(last_assess, datetime):
        last_assess = last_assess.date()
    elif isinstance(last_assess, str):
        last_assess = date.fromisoformat(last_assess[:10])
    metrics.last_assessment_date = last_assess

    # LMS activity
    act = db.execute(
        select(
            func.count(LmsActivityLog.activity_id),
            func.sum(
                case(
                    (
                        (LmsActivityLog.activity_type == "LOGIN")
                        & (LmsActivityLog.activity_at >= window_start),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.max(LmsActivityLog.activity_at),
        ).where(LmsActivityLog.enrollment_id == enrollment_id)
    ).one()
    metrics.total_activities = int(act[0] or 0)
    metrics.login_count_30d = int(act[1] or 0)
    last_at = act[2]
    if isinstance(last_at, str):
        last_at = datetime.fromisoformat(last_at)
    metrics.last_activity_at = last_at
    if last_at is not None:
        metrics.days_since_last_activity = (today - last_at.date()).days

    return metrics


# ---------------------------------------------------------------------------
# Persistence -- risk row + at most one open alert, in one transaction
# ---------------------------------------------------------------------------
def recalculate_enrollment(
    db: Session,
    enrollment_id: int,
    actor_user_id: Optional[int] = None,
    config: Optional[RiskConfig] = None,
    commit: bool = True,
) -> RiskAssessment:
    """Score one enrolment, store the history row and reconcile its alert.

    The risk row and any alert change are flushed together and committed
    once, so a risk assessment can never be persisted without the alert
    state that belongs to it.
    """
    cfg = config or RiskConfig.from_db(db)
    metrics = collect_metrics(db, enrollment_id, cfg)
    result = compute_risk(metrics, cfg)

    risk_row = RiskAssessment(
        enrollment_id=enrollment_id,
        calculated_at=datetime.now(),
        attendance_percentage=result.attendance_percentage,
        avg_assessment_percentage=result.avg_assessment_percentage,
        engagement_score=result.engagement_score,
        attendance_risk=result.attendance_risk,
        academic_risk=result.academic_risk,
        engagement_risk=result.engagement_risk,
        risk_score=result.risk_score,
        risk_category=result.risk_category,
        data_completeness=result.data_completeness,
        missing_data_reasons=result.missing_data_reasons,
        contributing_factors=result.contributing_factors,
        sessions_held=metrics.sessions_held,
        sessions_attended=metrics.sessions_attended,
        late_submissions=metrics.late_submissions,
        missing_submissions=metrics.missing_submissions,
        graded_assessments=metrics.graded_assessments,
        login_count_30d=metrics.login_count_30d,
        days_since_last_activity=metrics.days_since_last_activity,
        last_assessment_date=metrics.last_assessment_date,
        model_version=cfg.model_version,
    )
    db.add(risk_row)
    db.flush()

    _reconcile_alert(db, enrollment_id, risk_row, result, cfg, actor_user_id)

    if commit:
        db.commit()
    else:
        db.flush()
    return risk_row


def _reconcile_alert(
    db: Session,
    enrollment_id: int,
    risk_row: RiskAssessment,
    result: RiskResult,
    cfg: RiskConfig,
    actor_user_id: Optional[int],
) -> None:
    """Raise, refresh or auto-close the single open alert for an enrolment.

    * At or above the threshold with no open alert -> raise one (``NEW``).
    * At or above the threshold with an open alert -> refresh that alert's
      score and factors. It is never duplicated; the composite unique key
      ``(enrollment_id, active_flag)`` makes a duplicate impossible even
      under a race.
    * Below the threshold with an open alert still in ``NEW`` -> close it
      automatically. An alert a human has already acknowledged or started
      working is left alone for that human to close.
    """
    open_alert = db.execute(
        select(RiskAlert).where(
            RiskAlert.enrollment_id == enrollment_id, RiskAlert.active_flag == 1
        )
    ).scalar_one_or_none()

    should_alert = (
        result.risk_category in ("MEDIUM", "HIGH")
        and result.risk_score is not None
        and result.risk_score >= Decimal(cfg.alert_min_score)
    )

    if should_alert:
        if open_alert is None:
            alert = RiskAlert(
                enrollment_id=enrollment_id,
                risk_id=risk_row.risk_id,
                risk_score=result.risk_score,
                risk_category=result.risk_category,
                triggering_factors=result.contributing_factors,
                status="NEW",
            )
            db.add(alert)
            db.flush()
            db.add(
                AlertStatusHistory(
                    alert_id=alert.alert_id,
                    old_status=None,
                    new_status="NEW",
                    changed_by=actor_user_id,
                    note="Alert raised by risk recalculation",
                )
            )
        else:
            open_alert.risk_id = risk_row.risk_id
            open_alert.risk_score = result.risk_score
            open_alert.risk_category = result.risk_category
            open_alert.triggering_factors = result.contributing_factors
    elif open_alert is not None and open_alert.status == "NEW":
        open_alert.status = "RESOLVED"
        open_alert.resolved_at = datetime.now()
        open_alert.risk_id = risk_row.risk_id
        db.flush()
        db.add(
            AlertStatusHistory(
                alert_id=open_alert.alert_id,
                old_status="NEW",
                new_status="RESOLVED",
                changed_by=actor_user_id,
                note=(
                    "Auto-resolved: risk score fell to "
                    f"{result.risk_score if result.risk_score is not None else 'n/a'}"
                ),
            )
        )


def recalculate_all(
    db: Session,
    course_pk: Optional[int] = None,
    actor_user_id: Optional[int] = None,
) -> int:
    """Recalculate every ACTIVE enrolment, optionally limited to a course.

    Returns the number of enrolments processed. The whole run is one
    transaction: either every risk row lands or none does.
    """
    cfg = RiskConfig.from_db(db)
    stmt = select(Enrollment.enrollment_id).where(Enrollment.status == "ACTIVE")
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    ids = list(db.execute(stmt.order_by(Enrollment.enrollment_id)).scalars())

    for enrollment_id in ids:
        recalculate_enrollment(db, enrollment_id, actor_user_id, cfg, commit=False)

    db.commit()
    return len(ids)
