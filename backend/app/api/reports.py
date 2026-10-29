"""Dashboard metrics and the report suite.

Every figure returned here is aggregated by the database from real rows.
Nothing in this module -- and nothing in the frontend -- carries a
hardcoded metric.
"""

import csv
import io
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select

from app.api.deps import CurrentUser, DbSession, require_permissions
from app.core.exceptions import ValidationError
from app.core.permissions import P_REPORTS_READ
from app.models import (
    Assessment,
    AssessmentResult,
    Course,
    Department,
    Enrollment,
    Intervention,
    RiskAlert,
    Student,
)
from app.schemas.reports import (
    AlertPreview,
    CourseAttendanceRow,
    CoursePerformanceRow,
    DashboardSummary,
    DepartmentRiskRow,
    HighRiskStudentRow,
    InterventionOutcomeRow,
    RiskCount,
    RiskDistributionRow,
    SubmissionPatternRow,
    TrendPoint,
)
from app.services.queries import (
    course_stats_sq,
    latest_risk_sq,
    risk_summary_select,
    scored_risk,
)

dashboard_router = APIRouter(dependencies=[Depends(require_permissions(P_REPORTS_READ))])
router = APIRouter(dependencies=[Depends(require_permissions(P_REPORTS_READ))])

CATEGORY_LABELS = {
    "LOW": "Low risk (0-29)",
    "MEDIUM": "Medium risk (30-59)",
    "HIGH": "High risk (60-100)",
    "INSUFFICIENT_DATA": "Needs more data",
}


def _f(value) -> Optional[float]:
    return None if value is None else float(value)


def _month_expr(db: DbSession, column):
    """Portable ``YYYY-MM`` truncation."""
    if db.bind is not None and db.bind.dialect.name == "mysql":
        return func.date_format(column, "%Y-%m")
    return func.strftime("%Y-%m", column)


# ===========================================================================
# /api/dashboard
# ===========================================================================
@dashboard_router.get(
    "/summary", response_model=DashboardSummary, summary="Dashboard headline metrics"
)
def dashboard_summary(db: DbSession) -> DashboardSummary:
    total_students = db.execute(
        select(func.count()).select_from(Student).where(Student.is_active.is_(True))
    ).scalar_one()
    total_courses = db.execute(
        select(func.count()).select_from(Course).where(Course.is_active.is_(True))
    ).scalar_one()
    total_enrollments = db.execute(
        select(func.count()).select_from(Enrollment).where(Enrollment.status == "ACTIVE")
    ).scalar_one()
    total_departments = db.execute(select(func.count()).select_from(Department)).scalar_one()

    # Risk counts and the attendance / assessment means come from the same
    # aggregated statement the risk page uses.
    summary = risk_summary_select().where(Enrollment.status == "ACTIVE").subquery("rs")
    counts = db.execute(
        select(
            func.sum(case((summary.c.risk_category == "HIGH", 1), else_=0)),
            func.sum(case((summary.c.risk_category == "MEDIUM", 1), else_=0)),
            func.sum(case((summary.c.risk_category == "LOW", 1), else_=0)),
            func.sum(case((summary.c.risk_category == "INSUFFICIENT_DATA", 1), else_=0)),
            func.round(func.avg(summary.c.live_attendance_percentage), 2),
            func.round(func.avg(summary.c.live_assessment_percentage), 2),
        ).select_from(summary)
    ).one()

    high, medium, low, insufficient = (int(c or 0) for c in counts[:4])
    avg_attendance, avg_assessment = _f(counts[4]), _f(counts[5])

    open_alerts = db.execute(
        select(func.count()).select_from(RiskAlert).where(RiskAlert.status != "RESOLVED")
    ).scalar_one()
    unresolved_high = db.execute(
        select(func.count())
        .select_from(RiskAlert)
        .where(RiskAlert.risk_category == "HIGH", RiskAlert.status != "RESOLVED")
    ).scalar_one()
    open_interventions = db.execute(
        select(func.count())
        .select_from(Intervention)
        .where(Intervention.resolution_status != "CLOSED")
    ).scalar_one()

    now = datetime.now()
    due_soon = db.execute(
        select(func.count())
        .select_from(Assessment)
        .where(Assessment.due_at >= now, Assessment.due_at <= now + timedelta(days=7))
    ).scalar_one()

    distribution = [
        RiskCount(category=key, label=CATEGORY_LABELS[key], count=value)
        for key, value in (
            ("HIGH", high),
            ("MEDIUM", medium),
            ("LOW", low),
            ("INSUFFICIENT_DATA", insufficient),
        )
    ]

    return DashboardSummary(
        total_students=total_students,
        total_courses=total_courses,
        total_enrollments=total_enrollments,
        total_departments=total_departments,
        high_risk=high,
        medium_risk=medium,
        low_risk=low,
        insufficient_data=insufficient,
        avg_attendance_percentage=avg_attendance,
        avg_assessment_percentage=avg_assessment,
        open_alerts=open_alerts,
        unresolved_high_risk_alerts=unresolved_high,
        open_interventions=open_interventions,
        assessments_due_next_7_days=due_soon,
        risk_distribution=distribution,
        generated_at=now,
    )


@dashboard_router.get(
    "/recent-alerts",
    response_model=List[AlertPreview],
    summary="Most recent alerts, highest risk first",
)
def recent_alerts(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 8,
    only_open: Annotated[bool, Query()] = True,
) -> List[AlertPreview]:
    stmt = (
        select(
            RiskAlert.alert_id,
            Student.student_id,
            Student.full_name.label("student_name"),
            Course.course_code,
            RiskAlert.risk_score,
            RiskAlert.risk_category,
            RiskAlert.status,
            RiskAlert.triggering_factors,
            RiskAlert.created_at,
        )
        .join(Enrollment, Enrollment.enrollment_id == RiskAlert.enrollment_id)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
    )
    if only_open:
        stmt = stmt.where(RiskAlert.status != "RESOLVED")

    today = date.today()
    return [
        AlertPreview(
            alert_id=r["alert_id"],
            student_id=r["student_id"],
            student_name=r["student_name"],
            course_code=r["course_code"],
            risk_score=float(r["risk_score"]),
            risk_category=r["risk_category"],
            status=r["status"],
            triggering_factors=r["triggering_factors"],
            created_at=r["created_at"],
            age_days=(today - r["created_at"].date()).days,
        )
        for r in db.execute(
            stmt.order_by(
                case((RiskAlert.risk_category == "HIGH", 0), else_=1),
                RiskAlert.created_at.desc(),
            ).limit(limit)
        ).mappings()
    ]


@dashboard_router.get(
    "/performance-trend",
    response_model=List[TrendPoint],
    summary="Monthly assessment average and attendance rate",
)
def performance_trend(
    db: DbSession,
    course_pk: Annotated[Optional[int], Query()] = None,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
) -> List[TrendPoint]:
    """Academic performance over time, grouped by month in SQL."""
    period = _month_expr(db, Assessment.due_at)
    cutoff = datetime.now() - timedelta(days=31 * months)

    stmt = (
        select(
            period.label("period"),
            func.count(AssessmentResult.result_id).label("graded_results"),
            func.round(func.avg(AssessmentResult.percentage), 2).label("avg_percentage"),
        )
        .select_from(Assessment)
        .join(AssessmentResult, AssessmentResult.assessment_id == Assessment.assessment_id)
        .where(AssessmentResult.marks_obtained.is_not(None), Assessment.due_at >= cutoff)
    )
    if course_pk is not None:
        stmt = stmt.where(Assessment.course_pk == course_pk)

    academic = {
        r["period"]: (r["graded_results"], _f(r["avg_percentage"]))
        for r in db.execute(stmt.group_by(period).order_by(period)).mappings()
    }

    # Attendance rate for the same periods.
    from app.models import AttendanceRecord

    att_period = _month_expr(db, AttendanceRecord.session_date)
    att_stmt = (
        select(
            att_period.label("period"),
            func.round(
                100.0
                * func.sum(case((AttendanceRecord.status.in_(("PRESENT", "LATE")), 1), else_=0))
                / func.nullif(
                    func.sum(case((AttendanceRecord.status != "EXCUSED", 1), else_=0)), 0
                ),
                2,
            ).label("attendance_rate"),
        )
        .select_from(AttendanceRecord)
        .join(Enrollment, Enrollment.enrollment_id == AttendanceRecord.enrollment_id)
        .where(AttendanceRecord.session_date >= cutoff.date())
    )
    if course_pk is not None:
        att_stmt = att_stmt.where(Enrollment.course_pk == course_pk)
    attendance = {
        r["period"]: _f(r["attendance_rate"])
        for r in db.execute(att_stmt.group_by(att_period).order_by(att_period)).mappings()
    }

    periods = sorted(set(academic) | set(attendance))
    return [
        TrendPoint(
            period=p,
            graded_results=academic.get(p, (0, None))[0],
            avg_percentage=academic.get(p, (0, None))[1],
            avg_attendance_percentage=attendance.get(p),
        )
        for p in periods
    ]


# ===========================================================================
# /api/reports
# ===========================================================================
def _risk_distribution_rows(
    db: DbSession,
    group_by: str,
    course_pk: Optional[int],
    dept_id: Optional[int],
    semester: Optional[int],
) -> List[RiskDistributionRow]:
    summary = risk_summary_select().where(Enrollment.status == "ACTIVE")
    if course_pk is not None:
        summary = summary.where(Enrollment.course_pk == course_pk)
    if dept_id is not None:
        summary = summary.where(Student.dept_id == dept_id)
    if semester is not None:
        summary = summary.where(Student.semester == semester)
    sq = summary.subquery("rs")

    group_columns = {
        "category": (sq.c.risk_category, sq.c.risk_category),
        "semester": (sq.c.student_semester, sq.c.student_semester),
        "department": (sq.c.dept_code, sq.c.dept_name),
        "course": (sq.c.course_code, sq.c.course_name),
    }
    if group_by not in group_columns:
        raise ValidationError(f"group_by must be one of {', '.join(group_columns)}")
    key_col, label_col = group_columns[group_by]

    rows = db.execute(
        select(
            key_col.label("group_key"),
            label_col.label("group_label"),
            func.sum(case((sq.c.risk_category == "LOW", 1), else_=0)).label("low_risk"),
            func.sum(case((sq.c.risk_category == "MEDIUM", 1), else_=0)).label("medium_risk"),
            func.sum(case((sq.c.risk_category == "HIGH", 1), else_=0)).label("high_risk"),
            func.sum(case((sq.c.risk_category == "INSUFFICIENT_DATA", 1), else_=0)).label(
                "insufficient_data"
            ),
            func.count().label("total"),
            func.round(func.avg(scored_risk(sq.c.risk_score, sq.c.risk_category)), 2).label(
                "avg_risk_score"
            ),
        )
        .select_from(sq)
        .group_by(key_col, label_col)
        .order_by(key_col)
    ).mappings()

    out = []
    for r in rows:
        key = r["group_key"]
        label = r["group_label"]
        if group_by == "category":
            label = CATEGORY_LABELS.get(str(key), str(key))
        elif group_by == "semester":
            label = f"Semester {key}"
        out.append(
            RiskDistributionRow(
                group_key=str(key),
                group_label=str(label),
                low_risk=r["low_risk"] or 0,
                medium_risk=r["medium_risk"] or 0,
                high_risk=r["high_risk"] or 0,
                insufficient_data=r["insufficient_data"] or 0,
                total=r["total"] or 0,
                avg_risk_score=_f(r["avg_risk_score"]),
            )
        )
    return out


@router.get(
    "/risk-distribution",
    response_model=List[RiskDistributionRow],
    summary="Risk distribution grouped by category, semester, department or course",
)
def risk_distribution(
    db: DbSession,
    group_by: Annotated[
        Literal["category", "semester", "department", "course"], Query()
    ] = "category",
    course_pk: Annotated[Optional[int], Query()] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    semester: Annotated[Optional[int], Query(ge=1, le=12)] = None,
) -> List[RiskDistributionRow]:
    return _risk_distribution_rows(db, group_by, course_pk, dept_id, semester)


def _course_performance_rows(
    db: DbSession, dept_id: Optional[int], semester: Optional[int]
) -> List[CoursePerformanceRow]:
    stats = course_stats_sq()
    graded = (
        select(
            Assessment.course_pk.label("course_pk"),
            func.count(func.distinct(Assessment.assessment_id)).label("assessment_count"),
            func.sum(case((AssessmentResult.marks_obtained.is_not(None), 1), else_=0)).label(
                "graded_results"
            ),
            func.round(func.avg(AssessmentResult.percentage), 2).label("avg_percentage"),
            func.round(
                100.0
                * func.sum(case((AssessmentResult.percentage >= 40, 1), else_=0))
                / func.nullif(
                    func.sum(case((AssessmentResult.marks_obtained.is_not(None), 1), else_=0)), 0
                ),
                2,
            ).label("pass_rate_percentage"),
        )
        .select_from(Assessment)
        .outerjoin(AssessmentResult, AssessmentResult.assessment_id == Assessment.assessment_id)
        .group_by(Assessment.course_pk)
        .subquery("graded")
    )

    stmt = (
        select(
            Course.course_pk,
            Course.course_code,
            Course.course_name,
            Course.semester,
            Department.dept_code,
            func.coalesce(stats.c.enrolled_count, 0).label("enrolled_students"),
            func.coalesce(graded.c.assessment_count, 0).label("assessment_count"),
            func.coalesce(graded.c.graded_results, 0).label("graded_results"),
            graded.c.avg_percentage,
            graded.c.pass_rate_percentage,
            stats.c.avg_attendance_percentage,
            func.coalesce(stats.c.high_risk_count, 0).label("high_risk_count"),
        )
        .join(Department, Department.dept_id == Course.dept_id)
        .outerjoin(stats, stats.c.course_pk == Course.course_pk)
        .outerjoin(graded, graded.c.course_pk == Course.course_pk)
        .where(Course.is_active.is_(True))
    )
    if dept_id is not None:
        stmt = stmt.where(Course.dept_id == dept_id)
    if semester is not None:
        stmt = stmt.where(Course.semester == semester)

    return [
        CoursePerformanceRow(
            course_pk=r["course_pk"],
            course_code=r["course_code"],
            course_name=r["course_name"],
            dept_code=r["dept_code"],
            semester=r["semester"],
            enrolled_students=r["enrolled_students"],
            assessment_count=r["assessment_count"],
            graded_results=r["graded_results"],
            avg_percentage=_f(r["avg_percentage"]),
            pass_rate_percentage=_f(r["pass_rate_percentage"]),
            avg_attendance_percentage=_f(r["avg_attendance_percentage"]),
            high_risk_count=r["high_risk_count"],
        )
        for r in db.execute(stmt.order_by(Course.course_code)).mappings()
    ]


@router.get(
    "/course-performance",
    response_model=List[CoursePerformanceRow],
    summary="Course-wise average marks, pass rate and attendance",
)
def course_performance(
    db: DbSession,
    dept_id: Annotated[Optional[int], Query()] = None,
    semester: Annotated[Optional[int], Query(ge=1, le=12)] = None,
) -> List[CoursePerformanceRow]:
    return _course_performance_rows(db, dept_id, semester)


def _course_attendance_rows(
    db: DbSession, dept_id: Optional[int], date_from: Optional[date], date_to: Optional[date]
) -> List[CourseAttendanceRow]:
    from app.models import AttendanceRecord

    attended = func.sum(case((AttendanceRecord.status.in_(("PRESENT", "LATE")), 1), else_=0))
    held = func.sum(case((AttendanceRecord.status != "EXCUSED", 1), else_=0))

    per_enrollment = select(
        AttendanceRecord.enrollment_id.label("enrollment_id"),
        held.label("sessions_held"),
        attended.label("sessions_attended"),
    )
    if date_from is not None:
        per_enrollment = per_enrollment.where(AttendanceRecord.session_date >= date_from)
    if date_to is not None:
        per_enrollment = per_enrollment.where(AttendanceRecord.session_date <= date_to)
    pe = per_enrollment.group_by(AttendanceRecord.enrollment_id).subquery("pe")

    stmt = (
        select(
            Course.course_pk,
            Course.course_code,
            Course.course_name,
            Department.dept_code,
            func.count(func.distinct(Enrollment.enrollment_id)).label("enrolled_students"),
            func.coalesce(func.sum(pe.c.sessions_held), 0).label("total_sessions_held"),
            func.coalesce(func.sum(pe.c.sessions_attended), 0).label("total_sessions_attended"),
            func.round(
                100.0 * func.sum(pe.c.sessions_attended) / func.nullif(func.sum(pe.c.sessions_held), 0),
                2,
            ).label("avg_attendance_percentage"),
            func.sum(
                case(
                    (
                        100.0 * pe.c.sessions_attended / func.nullif(pe.c.sessions_held, 0) < 75,
                        1,
                    ),
                    else_=0,
                )
            ).label("students_below_75"),
        )
        .select_from(Course)
        .join(Department, Department.dept_id == Course.dept_id)
        .outerjoin(
            Enrollment,
            (Enrollment.course_pk == Course.course_pk) & (Enrollment.status == "ACTIVE"),
        )
        .outerjoin(pe, pe.c.enrollment_id == Enrollment.enrollment_id)
        .where(Course.is_active.is_(True))
        .group_by(Course.course_pk, Course.course_code, Course.course_name, Department.dept_code)
        .having(func.count(func.distinct(Enrollment.enrollment_id)) > 0)
    )
    if dept_id is not None:
        stmt = stmt.where(Course.dept_id == dept_id)

    return [
        CourseAttendanceRow(
            course_pk=r["course_pk"],
            course_code=r["course_code"],
            course_name=r["course_name"],
            dept_code=r["dept_code"],
            enrolled_students=r["enrolled_students"],
            total_sessions_held=int(r["total_sessions_held"] or 0),
            total_sessions_attended=int(r["total_sessions_attended"] or 0),
            avg_attendance_percentage=_f(r["avg_attendance_percentage"]),
            students_below_75=int(r["students_below_75"] or 0),
        )
        for r in db.execute(stmt.order_by(Course.course_code)).mappings()
    ]


@router.get(
    "/course-attendance",
    response_model=List[CourseAttendanceRow],
    summary="Course-wise attendance, with a date window",
)
def course_attendance(
    db: DbSession,
    dept_id: Annotated[Optional[int], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
) -> List[CourseAttendanceRow]:
    return _course_attendance_rows(db, dept_id, date_from, date_to)


def _submission_rows(
    db: DbSession, course_pk: Optional[int], date_from: Optional[date], date_to: Optional[date]
) -> List[SubmissionPatternRow]:
    stmt = (
        select(
            Assessment.assessment_id,
            Assessment.title.label("assessment_title"),
            Assessment.assessment_type,
            Assessment.due_at,
            Course.course_code,
            func.count(AssessmentResult.result_id).label("total_expected"),
            func.sum(case((AssessmentResult.submission_status == "ON_TIME", 1), else_=0)).label(
                "on_time"
            ),
            func.sum(case((AssessmentResult.submission_status == "LATE", 1), else_=0)).label(
                "late"
            ),
            func.sum(case((AssessmentResult.submission_status == "MISSING", 1), else_=0)).label(
                "missing"
            ),
            func.round(
                100.0
                * func.sum(case((AssessmentResult.submission_status == "ON_TIME", 1), else_=0))
                / func.nullif(func.count(AssessmentResult.result_id), 0),
                2,
            ).label("on_time_rate"),
            func.round(func.avg(AssessmentResult.percentage), 2).label("avg_percentage"),
        )
        .select_from(Assessment)
        .join(Course, Course.course_pk == Assessment.course_pk)
        .outerjoin(AssessmentResult, AssessmentResult.assessment_id == Assessment.assessment_id)
        .group_by(
            Assessment.assessment_id,
            Assessment.title,
            Assessment.assessment_type,
            Assessment.due_at,
            Course.course_code,
        )
    )
    if course_pk is not None:
        stmt = stmt.where(Assessment.course_pk == course_pk)
    if date_from is not None:
        stmt = stmt.where(Assessment.due_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(
            Assessment.due_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )

    return [
        SubmissionPatternRow(
            assessment_id=r["assessment_id"],
            assessment_title=r["assessment_title"],
            assessment_type=r["assessment_type"],
            course_code=r["course_code"],
            due_at=r["due_at"],
            total_expected=r["total_expected"] or 0,
            on_time=r["on_time"] or 0,
            late=r["late"] or 0,
            missing=r["missing"] or 0,
            on_time_rate=_f(r["on_time_rate"]),
            avg_percentage=_f(r["avg_percentage"]),
        )
        for r in db.execute(stmt.order_by(Course.course_code, Assessment.due_at)).mappings()
    ]


@router.get(
    "/submission-patterns",
    response_model=List[SubmissionPatternRow],
    summary="On-time, late and missing submissions per assessment",
)
def submission_patterns(
    db: DbSession,
    course_pk: Annotated[Optional[int], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
) -> List[SubmissionPatternRow]:
    return _submission_rows(db, course_pk, date_from, date_to)


def _high_risk_rows(
    db: DbSession, dept_id: Optional[int], semester: Optional[int], min_courses: int
) -> List[HighRiskStudentRow]:
    """Students carrying risk in one or more courses.

    ``GROUP BY`` + ``HAVING COUNT(*) >= n`` with ``GROUP_CONCAT`` to list
    the affected course codes on one line.
    """
    sq = (
        risk_summary_select()
        .where(Enrollment.status == "ACTIVE")
        .subquery("rs")
    )
    # MySQL renders GROUP_CONCAT(x) with a default comma separator;
    # SQLite takes the separator as a second argument.
    if db.bind is not None and db.bind.dialect.name == "mysql":
        concat = func.group_concat(sq.c.course_code.distinct())
    else:
        concat = func.group_concat(sq.c.course_code, ", ")

    stmt = (
        select(
            sq.c.student_pk,
            sq.c.student_id,
            sq.c.student_name,
            sq.c.dept_code,
            sq.c.student_semester.label("semester"),
            func.count().label("at_risk_courses"),
            concat.label("courses"),
            func.round(func.avg(sq.c.risk_score), 2).label("avg_risk_score"),
            func.max(sq.c.risk_score).label("max_risk_score"),
            func.sum(case((sq.c.open_alert_id.is_not(None), 1), else_=0)).label("open_alerts"),
        )
        .select_from(sq)
        .where(sq.c.risk_category.in_(("MEDIUM", "HIGH")))
        .group_by(
            sq.c.student_pk, sq.c.student_id, sq.c.student_name, sq.c.dept_code,
            sq.c.student_semester,
        )
        .having(func.count() >= min_courses)
    )
    if dept_id is not None:
        stmt = stmt.where(sq.c.dept_id == dept_id)
    if semester is not None:
        stmt = stmt.where(sq.c.student_semester == semester)

    return [
        HighRiskStudentRow(
            student_pk=r["student_pk"],
            student_id=r["student_id"],
            student_name=r["student_name"],
            dept_code=r["dept_code"],
            semester=r["semester"],
            at_risk_courses=r["at_risk_courses"],
            courses=r["courses"] or "",
            avg_risk_score=_f(r["avg_risk_score"]),
            max_risk_score=_f(r["max_risk_score"]),
            open_alerts=r["open_alerts"] or 0,
        )
        for r in db.execute(
            stmt.order_by(func.max(sq.c.risk_score).desc())
        ).mappings()
    ]


@router.get(
    "/high-risk-students",
    response_model=List[HighRiskStudentRow],
    summary="At-risk students, optionally only those at risk in several courses",
)
def high_risk_students(
    db: DbSession,
    dept_id: Annotated[Optional[int], Query()] = None,
    semester: Annotated[Optional[int], Query(ge=1, le=12)] = None,
    min_courses: Annotated[int, Query(ge=1, le=10)] = 1,
) -> List[HighRiskStudentRow]:
    return _high_risk_rows(db, dept_id, semester, min_courses)


def _department_risk_rows(db: DbSession) -> List[DepartmentRiskRow]:
    sq = risk_summary_select().where(Enrollment.status == "ACTIVE").subquery("rs")
    stmt = (
        select(
            Department.dept_id,
            Department.dept_code,
            Department.dept_name,
            func.count(func.distinct(sq.c.student_pk)).label("students_tracked"),
            func.count(sq.c.enrollment_id).label("enrollments_tracked"),
            func.sum(case((sq.c.risk_category == "HIGH", 1), else_=0)).label("high_risk"),
            func.sum(case((sq.c.risk_category == "MEDIUM", 1), else_=0)).label("medium_risk"),
            func.sum(case((sq.c.risk_category == "LOW", 1), else_=0)).label("low_risk"),
            func.sum(case((sq.c.risk_category == "INSUFFICIENT_DATA", 1), else_=0)).label(
                "insufficient_data"
            ),
            func.round(func.avg(scored_risk(sq.c.risk_score, sq.c.risk_category)), 2).label(
                "avg_risk_score"
            ),
            func.round(func.avg(sq.c.live_attendance_percentage), 2).label(
                "avg_attendance_percentage"
            ),
            func.round(func.avg(sq.c.live_assessment_percentage), 2).label(
                "avg_assessment_percentage"
            ),
            func.sum(case((sq.c.open_alert_id.is_not(None), 1), else_=0)).label("open_alerts"),
        )
        .select_from(Department)
        .outerjoin(sq, sq.c.dept_id == Department.dept_id)
        .group_by(Department.dept_id, Department.dept_code, Department.dept_name)
        .order_by(Department.dept_code)
    )
    return [
        DepartmentRiskRow(
            dept_id=r["dept_id"],
            dept_code=r["dept_code"],
            dept_name=r["dept_name"],
            students_tracked=r["students_tracked"] or 0,
            enrollments_tracked=r["enrollments_tracked"] or 0,
            high_risk=r["high_risk"] or 0,
            medium_risk=r["medium_risk"] or 0,
            low_risk=r["low_risk"] or 0,
            insufficient_data=r["insufficient_data"] or 0,
            avg_risk_score=_f(r["avg_risk_score"]),
            avg_attendance_percentage=_f(r["avg_attendance_percentage"]),
            avg_assessment_percentage=_f(r["avg_assessment_percentage"]),
            open_alerts=r["open_alerts"] or 0,
        )
        for r in db.execute(stmt).mappings()
    ]


@router.get(
    "/department-risk",
    response_model=List[DepartmentRiskRow],
    summary="Department-level risk summary",
)
def department_risk(db: DbSession) -> List[DepartmentRiskRow]:
    return _department_risk_rows(db)


def _intervention_outcome_rows(
    db: DbSession, date_from: Optional[date], date_to: Optional[date]
) -> List[InterventionOutcomeRow]:
    lr = latest_risk_sq()
    stmt = (
        select(
            Intervention.intervention_type,
            func.count().label("total"),
            func.sum(case((Intervention.outcome == "IMPROVED", 1), else_=0)).label("improved"),
            func.sum(case((Intervention.outcome == "NO_CHANGE", 1), else_=0)).label("no_change"),
            func.sum(case((Intervention.outcome == "PENDING", 1), else_=0)).label("pending"),
            func.sum(case((Intervention.outcome == "ESCALATED", 1), else_=0)).label("escalated"),
            func.sum(case((Intervention.outcome == "DECLINED", 1), else_=0)).label("declined"),
            func.round(
                100.0 * func.sum(case((Intervention.outcome == "IMPROVED", 1), else_=0))
                / func.nullif(func.count(), 0),
                2,
            ).label("improvement_rate"),
            func.round(func.avg(scored_risk(lr.c.risk_score, lr.c.risk_category)), 2).label(
                "avg_current_risk"
            ),
        )
        .select_from(Intervention)
        .outerjoin(lr, lr.c.enrollment_id == Intervention.enrollment_id)
        .group_by(Intervention.intervention_type)
        .having(func.count() > 0)
    )
    if date_from is not None:
        stmt = stmt.where(Intervention.contact_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Intervention.contact_date <= date_to)

    return [
        InterventionOutcomeRow(
            intervention_type=r["intervention_type"],
            total=r["total"],
            improved=r["improved"] or 0,
            no_change=r["no_change"] or 0,
            pending=r["pending"] or 0,
            escalated=r["escalated"] or 0,
            declined=r["declined"] or 0,
            improvement_rate=_f(r["improvement_rate"]),
            avg_current_risk=_f(r["avg_current_risk"]),
        )
        for r in db.execute(stmt.order_by(Intervention.intervention_type)).mappings()
    ]


@router.get(
    "/intervention-outcomes",
    response_model=List[InterventionOutcomeRow],
    summary="Intervention effectiveness by type",
)
def intervention_outcomes(
    db: DbSession,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
) -> List[InterventionOutcomeRow]:
    return _intervention_outcome_rows(db, date_from, date_to)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
CSV_REPORTS = (
    "risk-distribution",
    "course-performance",
    "course-attendance",
    "submission-patterns",
    "high-risk-students",
    "department-risk",
    "intervention-outcomes",
)


#: A spreadsheet treats a cell starting with one of these as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> Any:
    """Keep text cells from being run as spreadsheet formulas.

    Names come from data staff typed in, so a student recorded as
    ``=HYPERLINK(...)`` would otherwise become a live link, or worse, for
    whoever opens the export. A leading apostrophe makes the cell plain
    text. Numbers are not strings here and pass through unchanged, so a
    negative figure still imports as a number.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


@router.get(
    "/export",
    summary="Download any report as CSV",
    response_class=StreamingResponse,
)
def export_csv(
    db: DbSession,
    _: CurrentUser,
    report: Annotated[str, Query(description=f"One of: {', '.join(CSV_REPORTS)}")],
    group_by: Annotated[
        Literal["category", "semester", "department", "course"], Query()
    ] = "category",
    course_pk: Annotated[Optional[int], Query()] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    semester: Annotated[Optional[int], Query(ge=1, le=12)] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
) -> StreamingResponse:
    """Streams the same rows the JSON endpoints return, as a CSV file."""
    if report not in CSV_REPORTS:
        raise ValidationError(f"report must be one of {', '.join(CSV_REPORTS)}")

    if report == "risk-distribution":
        rows: List[Any] = _risk_distribution_rows(db, group_by, course_pk, dept_id, semester)
    elif report == "course-performance":
        rows = _course_performance_rows(db, dept_id, semester)
    elif report == "course-attendance":
        rows = _course_attendance_rows(db, dept_id, date_from, date_to)
    elif report == "submission-patterns":
        rows = _submission_rows(db, course_pk, date_from, date_to)
    elif report == "high-risk-students":
        rows = _high_risk_rows(db, dept_id, semester, 1)
    elif report == "department-risk":
        rows = _department_risk_rows(db)
    else:
        rows = _intervention_outcome_rows(db, date_from, date_to)

    buffer = io.StringIO()
    if rows:
        records: List[Dict[str, Any]] = [
            {key: _csv_safe(value) for key, value in r.model_dump().items()} for r in rows
        ]
        writer = csv.DictWriter(buffer, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    else:
        buffer.write("no rows matched the selected filters\n")

    buffer.seek(0)
    filename = f"se-ewrs-{report}-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
