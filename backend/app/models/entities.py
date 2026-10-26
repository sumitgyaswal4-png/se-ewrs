"""ORM models -- a 1:1 mapping of ``database/schema.sql``.

The models are written so the same code runs on MySQL 8 (production and
the graded deliverable) and on SQLite (the pytest suite). SQLAlchemy
renders ``Enum`` as a native MySQL ``ENUM`` and as ``VARCHAR`` + ``CHECK``
on SQLite, and both engines support the STORED generated column used by
``risk_alerts.active_flag``.

Timestamp columns carry **both** a Python-side ``default=datetime.now``
and a SQL ``server_default=CURRENT_TIMESTAMP``. The Python default is what
the ORM actually uses, which keeps every timestamp in one timezone: MySQL
evaluates ``CURRENT_TIMESTAMP`` in the server's local zone but SQLite
always returns UTC, so relying on the server default alone would make an
``audit_logs.created_at`` disagree with a ``risk_alerts.acknowledged_at``
written by application code, and a filter built from a local date would
silently drop rows created that evening. The server default is kept so
direct SQL inserts -- ``seed.sql``, a manual ``INSERT`` during a viva --
still get a sensible value.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# --------------------------------------------------------------------------
# Enumerated domains. Kept as module-level tuples so the Pydantic schemas
# and the seed script import exactly the same vocabulary as the database.
# --------------------------------------------------------------------------
USER_ROLES = ("ADMIN", "INSTRUCTOR", "TA", "ADVISOR", "CHAIR")
COURSE_ROLES = ("PRIMARY", "CO_INSTRUCTOR", "TA")
ENROLLMENT_STATUSES = ("ACTIVE", "DROPPED", "COMPLETED")
ATTENDANCE_STATUSES = ("PRESENT", "ABSENT", "LATE", "EXCUSED")
ACTIVITY_TYPES = (
    "LOGIN",
    "RESOURCE_VIEW",
    "FORUM_POST",
    "VIDEO_WATCH",
    "QUIZ_ATTEMPT",
    "ASSIGNMENT_SUBMIT",
)
ASSESSMENT_TYPES = ("ASSIGNMENT", "QUIZ", "MIDTERM", "FINAL", "PROJECT", "LAB")
SUBMISSION_STATUSES = ("ON_TIME", "LATE", "MISSING")
RISK_CATEGORIES = ("LOW", "MEDIUM", "HIGH", "INSUFFICIENT_DATA")
ALERT_CATEGORIES = ("MEDIUM", "HIGH")
ALERT_STATUSES = ("NEW", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED")
COMPLETENESS = ("COMPLETE", "PARTIAL", "INSUFFICIENT")
INTERVENTION_TYPES = (
    "COUNSELING",
    "TUTORING_REFERRAL",
    "ASSIGNMENT_SUPPORT",
    "ATTENDANCE_FOLLOWUP",
    "ACADEMIC_ADVISING",
    "PARENT_CONTACT",
)
INTERVENTION_OUTCOMES = ("PENDING", "IMPROVED", "NO_CHANGE", "DECLINED", "ESCALATED")
RESOLUTION_STATUSES = ("OPEN", "IN_PROGRESS", "CLOSED")
SETTING_TYPES = ("INT", "FLOAT", "STRING", "BOOL")


def _enum(*values: str, name: str) -> Enum:
    return Enum(*values, name=name, validate_strings=True)


_ts = DateTime

#: MySQL gets BIGINT for the high-volume log tables, but SQLite only
#: treats a plain "INTEGER PRIMARY KEY" as a rowid alias -- a BIGINT
#: primary key there would never auto-increment. The variant keeps one
#: model definition working correctly on both engines.
_big_pk = BigInteger().with_variant(Integer, "sqlite")


class Department(Base):
    __tablename__ = "departments"

    dept_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dept_code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    dept_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    students: Mapped[List["Student"]] = relationship(back_populates="department")
    courses: Mapped[List["Course"]] = relationship(back_populates="department")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_dept", "dept_id"),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    #: Argon2id digest. Never serialised by any Pydantic response schema.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(_enum(*USER_ROLES, name="user_role"), nullable=False)
    dept_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.dept_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(_ts)
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    department: Mapped[Optional[Department]] = relationship()


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("semester BETWEEN 1 AND 12", name="ck_students_semester"),
        CheckConstraint("enrollment_year BETWEEN 2000 AND 2100", name="ck_students_year"),
        Index("ix_students_dept", "dept_id"),
        Index("ix_students_semester", "semester"),
        Index("ix_students_active", "is_active"),
        Index("ix_students_name", "full_name"),
    )

    student_pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    dept_id: Mapped[int] = mapped_column(
        ForeignKey("departments.dept_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    semester: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    enrollment_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    department: Mapped[Department] = relationship(back_populates="students")
    enrollments: Mapped[List["Enrollment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("course_code", "academic_term", name="uq_courses_code_term"),
        CheckConstraint("semester BETWEEN 1 AND 12", name="ck_courses_semester"),
        CheckConstraint("credits BETWEEN 1 AND 10", name="ck_courses_credits"),
        CheckConstraint("total_sessions >= 0", name="ck_courses_sessions"),
        Index("ix_courses_dept", "dept_id"),
        Index("ix_courses_semester", "semester"),
        Index("ix_courses_active", "is_active"),
    )

    course_pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    course_name: Mapped[str] = mapped_column(String(150), nullable=False)
    dept_id: Mapped[int] = mapped_column(
        ForeignKey("departments.dept_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    semester: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    credits: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3, server_default="3")
    academic_term: Mapped[str] = mapped_column(String(20), nullable=False)
    total_sessions: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    department: Mapped[Department] = relationship(back_populates="courses")
    instructors: Mapped[List["CourseInstructor"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    enrollments: Mapped[List["Enrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    assessments: Mapped[List["Assessment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class CourseInstructor(Base):
    """Resolves the many-to-many between ``courses`` and ``users``."""

    __tablename__ = "course_instructors"
    __table_args__ = (
        UniqueConstraint("course_pk", "user_id", name="uq_course_instructor"),
        Index("ix_ci_user", "user_id"),
    )

    course_instructor_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_pk: Mapped[int] = mapped_column(
        ForeignKey("courses.course_pk", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    role_in_course: Mapped[str] = mapped_column(
        _enum(*COURSE_ROLES, name="course_role"), nullable=False, default="PRIMARY"
    )
    assigned_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)

    course: Mapped[Course] = relationship(back_populates="instructors")
    user: Mapped[User] = relationship()


class Enrollment(Base):
    """The join table every engagement fact hangs off.

    ``uq_enrollment_student_course`` is what makes duplicate enrolment
    impossible, and routing attendance / activity / results through
    ``enrollment_id`` means such a record can never reference a student
    who is not enrolled in that course.
    """

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_pk", "course_pk", name="uq_enrollment_student_course"),
        Index("ix_enrollments_course", "course_pk"),
        Index("ix_enrollments_status", "status"),
    )

    enrollment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_pk: Mapped[int] = mapped_column(
        ForeignKey("students.student_pk", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    course_pk: Mapped[int] = mapped_column(
        ForeignKey("courses.course_pk", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    enrolled_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        _enum(*ENROLLMENT_STATUSES, name="enrollment_status"), nullable=False, default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    student: Mapped[Student] = relationship(back_populates="enrollments")
    course: Mapped[Course] = relationship(back_populates="enrollments")
    attendance: Mapped[List["AttendanceRecord"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )
    activities: Mapped[List["LmsActivityLog"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )
    results: Mapped[List["AssessmentResult"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "session_date", "session_no", name="uq_attendance_session"
        ),
        CheckConstraint("session_no >= 1", name="ck_attendance_session_no"),
        Index("ix_attendance_date", "session_date"),
        Index("ix_attendance_status", "status"),
        Index("ix_attendance_enrollment", "enrollment_id"),
    )

    attendance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.enrollment_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_no: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        _enum(*ATTENDANCE_STATUSES, name="attendance_status"), nullable=False
    )
    recorded_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    remarks: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)

    enrollment: Mapped[Enrollment] = relationship(back_populates="attendance")
    recorder: Mapped[Optional[User]] = relationship()


class LmsActivityLog(Base):
    __tablename__ = "lms_activity_logs"
    __table_args__ = (
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes >= 0", name="ck_lms_duration"
        ),
        Index("ix_lms_enrollment_time", "enrollment_id", "activity_at"),
        Index("ix_lms_activity_at", "activity_at"),
        Index("ix_lms_type", "activity_type"),
    )

    activity_id: Mapped[int] = mapped_column(
        _big_pk, primary_key=True, autoincrement=True
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.enrollment_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    activity_type: Mapped[str] = mapped_column(
        _enum(*ACTIVITY_TYPES, name="activity_type"), nullable=False
    )
    activity_at: Mapped[datetime] = mapped_column(_ts, nullable=False)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    resource_ref: Mapped[Optional[str]] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)

    enrollment: Mapped[Enrollment] = relationship(back_populates="activities")


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("course_pk", "title", name="uq_assessment_course_title"),
        CheckConstraint("max_marks > 0", name="ck_assess_max_marks"),
        CheckConstraint("weight_percent >= 0 AND weight_percent <= 100", name="ck_assess_weight"),
        Index("ix_assessments_due", "due_at"),
        Index("ix_assessments_type", "assessment_type"),
    )

    assessment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_pk: Mapped[int] = mapped_column(
        ForeignKey("courses.course_pk", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    assessment_type: Mapped[str] = mapped_column(
        _enum(*ASSESSMENT_TYPES, name="assessment_type"), nullable=False
    )
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    weight_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=0, server_default="0"
    )
    due_at: Mapped[datetime] = mapped_column(_ts, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    course: Mapped[Course] = relationship(back_populates="assessments")
    results: Mapped[List["AssessmentResult"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class AssessmentResult(Base):
    """One graded row per (assessment, enrolment).

    ``marks_obtained IS NULL`` means "nothing graded yet" -- the risk
    engine deliberately excludes those rows from the academic average
    rather than treating them as a zero.
    """

    __tablename__ = "assessment_results"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "enrollment_id", name="uq_result_assessment_enrollment"
        ),
        CheckConstraint(
            "marks_obtained IS NULL OR marks_obtained >= 0", name="ck_result_marks_nonneg"
        ),
        CheckConstraint("attempt_no >= 1", name="ck_result_attempt"),
        Index("ix_results_enrollment", "enrollment_id"),
        Index("ix_results_status", "submission_status"),
        Index("ix_results_submitted", "submitted_at"),
    )

    result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.assessment_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.enrollment_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    marks_obtained: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    #: Maintained by trg_ar_before_insert/update on MySQL and by
    #: ``services.assessment_service`` so SQLite behaves identically.
    percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(_ts)
    submission_status: Mapped[str] = mapped_column(
        _enum(*SUBMISSION_STATUSES, name="submission_status"),
        nullable=False,
        default="MISSING",
    )
    attempt_no: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    graded_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    graded_at: Mapped[Optional[datetime]] = mapped_column(_ts)
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    assessment: Mapped[Assessment] = relationship(back_populates="results")
    enrollment: Mapped[Enrollment] = relationship(back_populates="results")


class RiskAssessment(Base):
    """Append-only risk history: one row per enrolment per recalc run."""

    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint(
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)",
            name="ck_risk_score_range",
        ),
        Index("ix_risk_enrollment_time", "enrollment_id", "calculated_at"),
        Index("ix_risk_category", "risk_category"),
        Index("ix_risk_calculated", "calculated_at"),
        Index("ix_risk_score", "risk_score"),
    )

    risk_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.enrollment_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    calculated_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)

    attendance_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    avg_assessment_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    engagement_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    attendance_risk: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    academic_risk: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    engagement_risk: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    risk_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    risk_category: Mapped[str] = mapped_column(
        _enum(*RISK_CATEGORIES, name="risk_category"), nullable=False
    )
    data_completeness: Mapped[str] = mapped_column(
        _enum(*COMPLETENESS, name="data_completeness"), nullable=False
    )
    missing_data_reasons: Mapped[Optional[str]] = mapped_column(String(500))
    contributing_factors: Mapped[Optional[str]] = mapped_column(String(1000))

    sessions_held: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    sessions_attended: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    late_submissions: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    missing_submissions: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    graded_assessments: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    login_count_30d: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    days_since_last_activity: Mapped[Optional[int]] = mapped_column(SmallInteger)
    last_assessment_date: Mapped[Optional[date]] = mapped_column(Date)
    model_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="rule-v1", server_default="rule-v1"
    )

    enrollment: Mapped[Enrollment] = relationship()


class RiskAlert(Base):
    """Early-warning alert.

    ``active_flag`` is a STORED generated column that holds 1 while the
    alert is open and NULL once it is resolved. Repeated NULLs are
    allowed inside a UNIQUE key, so ``uq_alert_one_active_per_enrollment``
    permits at most one OPEN alert per enrolment while keeping unlimited
    resolved history. That is the database-level guard against duplicate
    active alerts -- the application does not have to police it.
    """

    __tablename__ = "risk_alerts"
    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "active_flag", name="uq_alert_one_active_per_enrollment"
        ),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_alert_score"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_category", "risk_category"),
        Index("ix_alerts_created", "created_at"),
        Index("ix_alerts_assignee", "assigned_to"),
    )

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.enrollment_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    risk_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("risk_assessments.risk_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    risk_category: Mapped[str] = mapped_column(
        _enum(*ALERT_CATEGORIES, name="alert_category"), nullable=False
    )
    triggering_factors: Mapped[Optional[str]] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(
        _enum(*ALERT_STATUSES, name="alert_status"), nullable=False, default="NEW"
    )
    assigned_to: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(_ts)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(_ts)
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )
    active_flag: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        Computed("(CASE WHEN status = 'RESOLVED' THEN NULL ELSE 1 END)", persisted=True),
    )

    enrollment: Mapped[Enrollment] = relationship()
    assignee: Mapped[Optional[User]] = relationship()
    history: Mapped[List["AlertStatusHistory"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AlertStatusHistory(Base):
    __tablename__ = "alert_status_history"
    __table_args__ = (Index("ix_ash_alert", "alert_id", "changed_at"),)

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("risk_alerts.alert_id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    old_status: Mapped[Optional[str]] = mapped_column(
        _enum(*ALERT_STATUSES, name="alert_status_old")
    )
    new_status: Mapped[str] = mapped_column(
        _enum(*ALERT_STATUSES, name="alert_status_new"), nullable=False
    )
    changed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    note: Mapped[Optional[str]] = mapped_column(String(500))
    changed_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)

    alert: Mapped[RiskAlert] = relationship(back_populates="history")
    user: Mapped[Optional[User]] = relationship()


class Intervention(Base):
    __tablename__ = "interventions"
    __table_args__ = (
        CheckConstraint(
            "follow_up_date IS NULL OR follow_up_date >= contact_date", name="ck_intv_followup"
        ),
        Index("ix_intv_enrollment", "enrollment_id"),
        Index("ix_intv_alert", "alert_id"),
        Index("ix_intv_advisor", "assigned_advisor_id"),
        Index("ix_intv_type", "intervention_type"),
        Index("ix_intv_outcome", "outcome"),
        Index("ix_intv_contact_date", "contact_date"),
    )

    intervention_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.enrollment_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    alert_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("risk_alerts.alert_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    intervention_type: Mapped[str] = mapped_column(
        _enum(*INTERVENTION_TYPES, name="intervention_type"), nullable=False
    )
    assigned_advisor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    contact_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    action_plan: Mapped[Optional[str]] = mapped_column(Text)
    follow_up_date: Mapped[Optional[date]] = mapped_column(Date)
    outcome: Mapped[str] = mapped_column(
        _enum(*INTERVENTION_OUTCOMES, name="intervention_outcome"),
        nullable=False,
        default="PENDING",
    )
    resolution_status: Mapped[str] = mapped_column(
        _enum(*RESOLUTION_STATUSES, name="resolution_status"), nullable=False, default="OPEN"
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )

    enrollment: Mapped[Enrollment] = relationship()
    alert: Mapped[Optional[RiskAlert]] = relationship()
    advisor: Mapped[Optional[User]] = relationship(foreign_keys=[assigned_advisor_id])


class SystemSetting(Base):
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    setting_value: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[str] = mapped_column(
        _enum(*SETTING_TYPES, name="setting_type"), nullable=False, default="STRING"
    )
    description: Mapped[Optional[str]] = mapped_column(String(255))
    updated_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        _ts, default=datetime.now, onupdate=datetime.now,
        server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_user", "user_id"),
        Index("ix_audit_action", "action"),
    )

    audit_id: Mapped[int] = mapped_column(
        _big_pk, primary_key=True, autoincrement=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", onupdate="CASCADE", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(60))
    old_values: Mapped[Optional[str]] = mapped_column(Text)
    new_values: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(_ts, default=datetime.now, server_default=func.now(), nullable=False)
