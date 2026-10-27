"""Reusable SQL aggregates behind the API.

Each builder here is the SQLAlchemy Core twin of a view in
``database/views.sql``, and the docstrings name the view it mirrors. The
statements are compiled and executed by the database -- the joins,
``GROUP BY``, ``HAVING``, conditional aggregation and window functions
all run server-side, and the API only ever receives the aggregated rows.

They are written in Core rather than as ``SELECT * FROM <view>`` for one
reason: the same statements then run unchanged on MySQL 8 (the graded
deployment) and on SQLite (the pytest suite), so the test-suite exercises
the real aggregation logic rather than a stub. The MySQL views remain the
database-side definition of record and are what ``analytics_queries.sql``
queries directly.

**The ``limit_to`` argument.** Every roll-up here groups a whole fact
table by ``enrollment_id``. A caller that wants one enrolment's figures
can filter the *result* of that aggregate, but MySQL will still group
the entire table first and throw almost all of it away -- the same trap
that made ``sp_recalculate_risk_for_enrollment`` 132x slower than it
needed to be, documented in ``docs/database_design.md`` section 9.
Passing ``limit_to`` instead pushes the enrolment predicate *inside* the
aggregate, so the index is used and the work is proportional to what the
caller asked for. It never changes which rows come back or what they
contain: restricting a ``GROUP BY enrollment_id`` to a set of
``enrollment_id``s can only remove groups the caller was going to
discard anyway.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import Select, and_, case, func, literal, null, select
from sqlalchemy.sql import Subquery

from app.models import (
    AssessmentResult,
    AttendanceRecord,
    Course,
    Department,
    Enrollment,
    LmsActivityLog,
    RiskAlert,
    RiskAssessment,
    Student,
    User,
)

ATTENDED = ("PRESENT", "LATE")


def _restrict(stmt, column, limit_to):
    """Push an ``enrollment_id`` predicate inside an aggregate.

    ``limit_to`` is anything ``IN`` accepts: a list of ids, or a SELECT.
    A SELECT is explicitly un-correlated, because these subqueries name
    the same tables as the statement they end up inside and SQLAlchemy
    would otherwise helpfully correlate them into something that means
    something else entirely.
    """
    if limit_to is None:
        return stmt
    if isinstance(limit_to, Select):
        limit_to = limit_to.correlate(None).scalar_subquery()
    return stmt.where(column.in_(limit_to))


def _pct(numerator, denominator):
    """``ROUND(100 * n / NULLIF(d, 0), 2)`` -- NULL instead of divide-by-zero."""
    return func.round(100.0 * numerator / func.nullif(denominator, 0), 2)


# ---------------------------------------------------------------------------
# Per-enrolment roll-ups
# ---------------------------------------------------------------------------
def attendance_sq(limit_to=None) -> Subquery:
    """Mirrors ``v_enrollment_attendance``.

    LATE counts as attended -- the student was present. EXCUSED absences
    are excluded from the denominator so an authorised absence cannot
    inflate a student's attendance risk.
    """
    held = func.sum(case((AttendanceRecord.status != "EXCUSED", 1), else_=0))
    attended = func.sum(case((AttendanceRecord.status.in_(ATTENDED), 1), else_=0))
    stmt = (
        select(
            AttendanceRecord.enrollment_id.label("enrollment_id"),
            func.count(AttendanceRecord.attendance_id).label("sessions_recorded"),
            held.label("sessions_held"),
            attended.label("sessions_attended"),
            func.sum(case((AttendanceRecord.status == "ABSENT", 1), else_=0)).label(
                "sessions_absent"
            ),
            func.sum(case((AttendanceRecord.status == "LATE", 1), else_=0)).label(
                "sessions_late"
            ),
            func.sum(case((AttendanceRecord.status == "EXCUSED", 1), else_=0)).label(
                "sessions_excused"
            ),
            _pct(attended, held).label("attendance_percentage"),
            func.max(AttendanceRecord.session_date).label("last_session_date"),
        )
        .group_by(AttendanceRecord.enrollment_id)
    )
    return _restrict(stmt, AttendanceRecord.enrollment_id, limit_to).subquery("att")


def academics_sq(limit_to=None) -> Subquery:
    """Mirrors ``v_enrollment_academics``.

    Only rows with ``marks_obtained IS NOT NULL`` feed the average, so an
    ungraded or un-submitted assessment is never counted as a zero.
    """
    graded_pct = case((AssessmentResult.marks_obtained.is_not(None), AssessmentResult.percentage))
    graded_flag = case((AssessmentResult.marks_obtained.is_not(None), 1), else_=0)
    stmt = (
        select(
            AssessmentResult.enrollment_id.label("enrollment_id"),
            func.count(AssessmentResult.result_id).label("results_recorded"),
            func.sum(graded_flag).label("graded_assessments"),
            func.round(func.avg(graded_pct), 2).label("avg_assessment_percentage"),
            func.min(graded_pct).label("min_assessment_percentage"),
            func.max(graded_pct).label("max_assessment_percentage"),
            func.sum(case((AssessmentResult.submission_status == "ON_TIME", 1), else_=0)).label(
                "ontime_submissions"
            ),
            func.sum(case((AssessmentResult.submission_status == "LATE", 1), else_=0)).label(
                "late_submissions"
            ),
            func.sum(case((AssessmentResult.submission_status == "MISSING", 1), else_=0)).label(
                "missing_submissions"
            ),
            # A DATETIME, not a DATE: SQLite's CAST(x AS DATE) returns a
            # numeric, so the truncation is left to the caller.
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
            ).label("last_assessment_at"),
        )
        .group_by(AssessmentResult.enrollment_id)
    )
    return _restrict(stmt, AssessmentResult.enrollment_id, limit_to).subquery("aca")


def activity_sq(window_days: int = 30, today: Optional[date] = None, limit_to=None) -> Subquery:
    """Mirrors ``v_enrollment_activity``.

    ``login_count_30d`` is windowed; ``last_activity_at`` is not, so a
    long-dormant student still reports when they were last seen.
    """
    ref = today or date.today()
    window_start = datetime.combine(ref - timedelta(days=window_days), datetime.min.time())
    is_login_in_window = and_(
        LmsActivityLog.activity_type == "LOGIN", LmsActivityLog.activity_at >= window_start
    )
    stmt = (
        select(
            LmsActivityLog.enrollment_id.label("enrollment_id"),
            func.count(LmsActivityLog.activity_id).label("total_activities"),
            func.sum(case((is_login_in_window, 1), else_=0)).label("login_count_30d"),
            func.sum(case((LmsActivityLog.activity_type == "LOGIN", 1), else_=0)).label(
                "login_count_total"
            ),
            func.sum(case((LmsActivityLog.activity_type == "QUIZ_ATTEMPT", 1), else_=0)).label(
                "quiz_attempts"
            ),
            func.sum(
                case((LmsActivityLog.activity_type == "ASSIGNMENT_SUBMIT", 1), else_=0)
            ).label("submission_events"),
            func.coalesce(func.sum(LmsActivityLog.duration_minutes), 0).label("total_minutes"),
            func.max(LmsActivityLog.activity_at).label("last_activity_at"),
        )
        .group_by(LmsActivityLog.enrollment_id)
    )
    return _restrict(stmt, LmsActivityLog.enrollment_id, limit_to).subquery("act")


def latest_risk_sq(limit_to=None) -> Subquery:
    """Mirrors ``v_latest_risk``.

    Uses ``ROW_NUMBER() OVER (PARTITION BY enrollment_id ORDER BY
    calculated_at DESC)`` to pick the newest row out of the append-only
    risk history, which is the same window function the SQL view uses.
    """
    rn = func.row_number().over(
        partition_by=RiskAssessment.enrollment_id,
        order_by=(RiskAssessment.calculated_at.desc(), RiskAssessment.risk_id.desc()),
    )
    inner = _restrict(
        select(RiskAssessment, rn.label("rn")), RiskAssessment.enrollment_id, limit_to
    )
    ranked = inner.subquery("ranked")
    return select(ranked).where(ranked.c.rn == 1).subquery("lr")


def open_alert_sq(limit_to=None) -> Subquery:
    """At most one open alert per enrolment -- guaranteed by the unique key."""
    stmt = (
        select(
            RiskAlert.enrollment_id.label("enrollment_id"),
            RiskAlert.alert_id.label("alert_id"),
            RiskAlert.status.label("status"),
            RiskAlert.assigned_to.label("assigned_to"),
        )
        .where(RiskAlert.active_flag == 1)
    )
    return _restrict(stmt, RiskAlert.enrollment_id, limit_to).subquery("oa")


# ---------------------------------------------------------------------------
# Composite selects
# ---------------------------------------------------------------------------
def performance_select(window_days: int = 30, limit_to=None) -> Select:
    """Mirrors ``student_performance_view``: one row per (student, course)."""
    att = attendance_sq(limit_to)
    aca = academics_sq(limit_to)
    act = activity_sq(window_days, limit_to=limit_to)
    return (
        select(
            Enrollment.enrollment_id,
            Enrollment.status.label("enrollment_status"),
            Enrollment.enrolled_on,
            Student.student_pk,
            Student.student_id,
            Student.full_name.label("student_name"),
            Student.email.label("student_email"),
            Student.semester.label("student_semester"),
            Student.enrollment_year,
            Student.is_active.label("student_active"),
            Department.dept_id,
            Department.dept_code,
            Department.dept_name,
            Course.course_pk,
            Course.course_code,
            Course.course_name,
            Course.semester.label("course_semester"),
            Course.academic_term,
            Course.credits,
            func.coalesce(att.c.sessions_held, 0).label("sessions_held"),
            func.coalesce(att.c.sessions_attended, 0).label("sessions_attended"),
            func.coalesce(att.c.sessions_absent, 0).label("sessions_absent"),
            func.coalesce(att.c.sessions_late, 0).label("sessions_late"),
            func.coalesce(att.c.sessions_excused, 0).label("sessions_excused"),
            att.c.attendance_percentage,
            att.c.last_session_date,
            func.coalesce(aca.c.results_recorded, 0).label("results_recorded"),
            func.coalesce(aca.c.graded_assessments, 0).label("graded_assessments"),
            aca.c.avg_assessment_percentage,
            aca.c.min_assessment_percentage,
            aca.c.max_assessment_percentage,
            func.coalesce(aca.c.ontime_submissions, 0).label("ontime_submissions"),
            func.coalesce(aca.c.late_submissions, 0).label("late_submissions"),
            func.coalesce(aca.c.missing_submissions, 0).label("missing_submissions"),
            aca.c.last_assessment_at,
            func.coalesce(act.c.total_activities, 0).label("total_activities"),
            func.coalesce(act.c.login_count_30d, 0).label("login_count_30d"),
            func.coalesce(act.c.login_count_total, 0).label("login_count_total"),
            func.coalesce(act.c.quiz_attempts, 0).label("quiz_attempts"),
            func.coalesce(act.c.submission_events, 0).label("submission_events"),
            func.coalesce(act.c.total_minutes, 0).label("total_minutes"),
            act.c.last_activity_at,
        )
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Department, Department.dept_id == Student.dept_id)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .outerjoin(att, att.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(aca, aca.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(act, act.c.enrollment_id == Enrollment.enrollment_id)
    )


def risk_summary_select(window_days: int = 30, limit_to=None, live: bool = True) -> Select:
    """Mirrors ``student_risk_summary``: performance + latest risk + alert.

    Pass ``limit_to`` when the caller already knows which enrolments it
    wants -- one enrolment, one student's, one course's. Without it the
    five aggregates below are each computed over the whole database and
    then filtered, which is correct but costs the same whether you asked
    for one row or all of them.

    ``live=False`` drops the three attendance/academics/activity joins
    and leaves their columns NULL. They are display-only: nothing filters,
    sorts or counts on them, and each is grouped by ``enrollment_id`` so
    the joins cannot change how many rows come back. A paginated caller
    can therefore select its page without them and fill those three
    columns in afterwards with :func:`live_figures_select`, which is the
    difference between aggregating the whole database and aggregating
    twenty enrolments.
    """
    att = attendance_sq(limit_to) if live else None
    aca = academics_sq(limit_to) if live else None
    act = activity_sq(window_days, limit_to=limit_to) if live else None
    lr, oa = latest_risk_sq(limit_to), open_alert_sq(limit_to)
    live_columns = (
        [
            att.c.attendance_percentage.label("live_attendance_percentage"),
            aca.c.avg_assessment_percentage.label("live_assessment_percentage"),
            act.c.last_activity_at,
        ]
        if live
        else [
            null().label("live_attendance_percentage"),
            null().label("live_assessment_percentage"),
            null().label("last_activity_at"),
        ]
    )
    stmt = (
        select(
            Enrollment.enrollment_id,
            Enrollment.status.label("enrollment_status"),
            Student.student_pk,
            Student.student_id,
            Student.full_name.label("student_name"),
            Student.email.label("student_email"),
            Student.semester.label("student_semester"),
            Student.is_active.label("student_active"),
            Department.dept_id,
            Department.dept_code,
            Department.dept_name,
            Course.course_pk,
            Course.course_code,
            Course.course_name,
            Course.academic_term,
            lr.c.risk_id,
            lr.c.risk_score,
            func.coalesce(lr.c.risk_category, literal("INSUFFICIENT_DATA")).label("risk_category"),
            func.coalesce(lr.c.data_completeness, literal("INSUFFICIENT")).label(
                "data_completeness"
            ),
            lr.c.missing_data_reasons,
            lr.c.contributing_factors,
            lr.c.attendance_percentage,
            lr.c.avg_assessment_percentage,
            lr.c.engagement_score,
            lr.c.attendance_risk,
            lr.c.academic_risk,
            lr.c.engagement_risk,
            func.coalesce(lr.c.sessions_held, 0).label("sessions_held"),
            func.coalesce(lr.c.sessions_attended, 0).label("sessions_attended"),
            func.coalesce(lr.c.late_submissions, 0).label("late_submissions"),
            func.coalesce(lr.c.missing_submissions, 0).label("missing_submissions"),
            func.coalesce(lr.c.graded_assessments, 0).label("graded_assessments"),
            func.coalesce(lr.c.login_count_30d, 0).label("login_count_30d"),
            lr.c.days_since_last_activity,
            lr.c.last_assessment_date,
            lr.c.calculated_at,
            lr.c.model_version,
            # live figures, used when no risk run has happened yet
            *live_columns,
            oa.c.alert_id.label("open_alert_id"),
            oa.c.status.label("open_alert_status"),
            oa.c.assigned_to.label("open_alert_assignee"),
        )
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Department, Department.dept_id == Student.dept_id)
        .join(Course, Course.course_pk == Enrollment.course_pk)
    )
    if live:
        stmt = (
            stmt.outerjoin(att, att.c.enrollment_id == Enrollment.enrollment_id)
            .outerjoin(aca, aca.c.enrollment_id == Enrollment.enrollment_id)
            .outerjoin(act, act.c.enrollment_id == Enrollment.enrollment_id)
        )
    return (
        stmt.outerjoin(lr, lr.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(oa, oa.c.enrollment_id == Enrollment.enrollment_id)
    )


def live_figures_select(enrollment_ids, window_days: int = 30) -> Select:
    """The three display-only figures, for a page's worth of enrolments.

    The companion to ``risk_summary_select(live=False)``: same three
    columns, same meaning, computed for twenty enrolments instead of
    every one in the database.
    """
    att = attendance_sq(enrollment_ids)
    aca = academics_sq(enrollment_ids)
    act = activity_sq(window_days, limit_to=enrollment_ids)
    return (
        select(
            Enrollment.enrollment_id,
            att.c.attendance_percentage.label("live_attendance_percentage"),
            aca.c.avg_assessment_percentage.label("live_assessment_percentage"),
            act.c.last_activity_at.label("last_activity_at"),
        )
        .select_from(Enrollment)
        .outerjoin(att, att.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(aca, aca.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(act, act.c.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.enrollment_id.in_(enrollment_ids))
    )


def alerts_select_full() -> Select:
    """Alerts joined to student, course and assignee -- mirrors ``v_active_alerts``."""
    from app.models import Intervention

    intv = (
        select(
            Intervention.alert_id.label("alert_id"),
            func.count(Intervention.intervention_id).label("intervention_count"),
        )
        .where(Intervention.alert_id.is_not(None))
        .group_by(Intervention.alert_id)
        .subquery("intv")
    )
    return (
        select(
            RiskAlert.alert_id,
            RiskAlert.enrollment_id,
            RiskAlert.risk_id,
            RiskAlert.risk_score,
            RiskAlert.risk_category,
            RiskAlert.triggering_factors,
            RiskAlert.status,
            RiskAlert.assigned_to,
            User.full_name.label("assignee_name"),
            RiskAlert.acknowledged_at,
            RiskAlert.resolved_at,
            RiskAlert.created_at,
            RiskAlert.updated_at,
            Student.student_pk,
            Student.student_id,
            Student.full_name.label("student_name"),
            Student.semester.label("student_semester"),
            Department.dept_code,
            Course.course_pk,
            Course.course_code,
            Course.course_name,
            func.coalesce(intv.c.intervention_count, 0).label("intervention_count"),
        )
        .join(Enrollment, Enrollment.enrollment_id == RiskAlert.enrollment_id)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Department, Department.dept_id == Student.dept_id)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .outerjoin(User, User.user_id == RiskAlert.assigned_to)
        .outerjoin(intv, intv.c.alert_id == RiskAlert.alert_id)
    )


def student_risk_counts_sq() -> Subquery:
    """The half of the student summary that the list filters and sorts on.

    Enrolment counts, the worst banded score and the open-alert count.
    All of it comes from ``enrollments`` joined to the latest risk row and
    the open alert -- no attendance, academics or activity aggregate is
    involved, so this stays cheap however much fact data exists.

    ``highest_risk_score`` deliberately ignores rows whose category is
    ``INSUFFICIENT_DATA`` so an unscored profile is never presented as if
    it had been assessed.
    """
    lr, oa = latest_risk_sq(), open_alert_sq()
    banded = lr.c.risk_category.in_(("LOW", "MEDIUM", "HIGH"))
    return (
        select(
            Enrollment.student_pk.label("student_pk"),
            func.count(func.distinct(Enrollment.enrollment_id)).label("enrolled_courses"),
            func.max(case((banded, lr.c.risk_score))).label("highest_risk_score"),
            func.sum(case((lr.c.risk_category == "HIGH", 1), else_=0)).label("high_risk_courses"),
            func.sum(case((lr.c.risk_category == "MEDIUM", 1), else_=0)).label(
                "medium_risk_courses"
            ),
            func.count(oa.c.alert_id).label("open_alerts"),
        )
        .select_from(Enrollment)
        .outerjoin(lr, lr.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(oa, oa.c.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.status == "ACTIVE")
        .group_by(Enrollment.student_pk)
        .subquery("scounts")
    )


def student_live_stats_select(student_pks, window_days: int = 30) -> Select:
    """The display-only half of the student summary, for one page.

    Averaged attendance and marks, submission counts and last-seen. These
    are shown but never filtered, sorted or counted on, so the list can
    select its page first and ask for these only for the students on it.

    Splitting the summary this way is safe because every join involved is
    at most one row per enrolment: dropping the three aggregates cannot
    change ``enrolled_courses``, the risk counts or ``open_alerts``, and
    adding them back for twenty students cannot change these five.
    """
    enrolments = select(Enrollment.enrollment_id).where(
        Enrollment.student_pk.in_(student_pks), Enrollment.status == "ACTIVE"
    )
    att = attendance_sq(enrolments)
    aca = academics_sq(enrolments)
    act = activity_sq(window_days, limit_to=enrolments)
    return (
        select(
            Enrollment.student_pk.label("student_pk"),
            func.round(func.avg(att.c.attendance_percentage), 2).label(
                "attendance_percentage"
            ),
            func.round(func.avg(aca.c.avg_assessment_percentage), 2).label(
                "avg_assessment_percentage"
            ),
            func.coalesce(func.sum(aca.c.late_submissions), 0).label("late_submissions"),
            func.coalesce(func.sum(aca.c.missing_submissions), 0).label(
                "missing_submissions"
            ),
            func.max(act.c.last_activity_at).label("last_activity_at"),
        )
        .select_from(Enrollment)
        .outerjoin(att, att.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(aca, aca.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(act, act.c.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.student_pk.in_(student_pks), Enrollment.status == "ACTIVE")
        .group_by(Enrollment.student_pk)
    )


def course_stats_sq(window_days: int = 30) -> Subquery:
    """Per-course roll-up: headcount, attendance, marks and risk counts.

    Mirrors ``course_attendance_summary`` joined to
    ``course_performance_summary``.
    """
    att, aca = attendance_sq(), academics_sq()
    lr = latest_risk_sq()
    return (
        select(
            Enrollment.course_pk.label("course_pk"),
            func.count(func.distinct(Enrollment.enrollment_id)).label("enrolled_count"),
            func.coalesce(func.sum(att.c.sessions_held), 0).label("total_sessions_held"),
            func.coalesce(func.sum(att.c.sessions_attended), 0).label("total_sessions_attended"),
            _pct(
                func.sum(att.c.sessions_attended), func.sum(att.c.sessions_held)
            ).label("avg_attendance_percentage"),
            func.round(func.avg(aca.c.avg_assessment_percentage), 2).label(
                "avg_assessment_percentage"
            ),
            func.sum(case((att.c.attendance_percentage < 75, 1), else_=0)).label(
                "students_below_75"
            ),
            func.sum(case((lr.c.risk_category == "HIGH", 1), else_=0)).label("high_risk_count"),
            func.sum(case((lr.c.risk_category == "MEDIUM", 1), else_=0)).label(
                "medium_risk_count"
            ),
            func.round(func.avg(lr.c.risk_score), 2).label("avg_risk_score"),
        )
        .select_from(Enrollment)
        .outerjoin(att, att.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(aca, aca.c.enrollment_id == Enrollment.enrollment_id)
        .outerjoin(lr, lr.c.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.status == "ACTIVE")
        .group_by(Enrollment.course_pk)
        .subquery("cstats")
    )
