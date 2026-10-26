"""Attendance, LMS activity and assessment schemas."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ACTIVITY_TYPES, ASSESSMENT_TYPES, ATTENDANCE_STATUSES


# --- attendance ------------------------------------------------------------
class AttendanceCreate(BaseModel):
    enrollment_id: int
    session_date: date
    session_no: int = Field(default=1, ge=1, le=1000)
    status: str
    remarks: Optional[str] = Field(default=None, max_length=255)

    @field_validator("status")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in ATTENDANCE_STATUSES:
            raise ValueError(f"status must be one of {', '.join(ATTENDANCE_STATUSES)}")
        return v

    @field_validator("session_date")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("session_date cannot be in the future")
        return v


class AttendanceBulkRow(BaseModel):
    enrollment_id: int
    status: str

    @field_validator("status")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in ATTENDANCE_STATUSES:
            raise ValueError(f"status must be one of {', '.join(ATTENDANCE_STATUSES)}")
        return v


class AttendanceBulkCreate(BaseModel):
    """Mark a whole class roster for one session in a single request."""

    course_pk: int
    session_date: date
    session_no: int = Field(default=1, ge=1, le=1000)
    rows: List[AttendanceBulkRow] = Field(min_length=1, max_length=500)

    @field_validator("session_date")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("session_date cannot be in the future")
        return v


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attendance_id: int
    enrollment_id: int
    session_date: date
    session_no: int
    status: str
    remarks: Optional[str] = None
    recorded_by: Optional[int] = None
    recorded_by_name: Optional[str] = None
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    course_code: Optional[str] = None
    created_at: Optional[datetime] = None


class AttendanceSummaryRow(BaseModel):
    """Totals of classes held and attended, per enrolment."""

    enrollment_id: int
    student_pk: int
    student_id: str
    student_name: str
    course_pk: int
    course_code: str
    sessions_held: int
    sessions_attended: int
    sessions_absent: int
    sessions_late: int
    sessions_excused: int
    attendance_percentage: Optional[float] = None
    last_session_date: Optional[date] = None


# --- LMS activity ----------------------------------------------------------
class ActivityCreate(BaseModel):
    enrollment_id: int
    activity_type: str
    activity_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    resource_ref: Optional[str] = Field(default=None, max_length=160)

    @field_validator("activity_type")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in ACTIVITY_TYPES:
            raise ValueError(f"activity_type must be one of {', '.join(ACTIVITY_TYPES)}")
        return v

    @model_validator(mode="after")
    def _not_future(self):
        if self.activity_at is not None and self.activity_at > datetime.now():
            raise ValueError("activity_at cannot be in the future")
        return self


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: int
    enrollment_id: int
    activity_type: str
    activity_at: datetime
    duration_minutes: Optional[int] = None
    resource_ref: Optional[str] = None
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    course_code: Optional[str] = None


class ActivitySummaryRow(BaseModel):
    """Login frequency and last-seen, per enrolment."""

    enrollment_id: int
    student_pk: int
    student_id: str
    student_name: str
    course_pk: int
    course_code: str
    total_activities: int
    login_count_30d: int
    login_count_total: int
    quiz_attempts: int
    submission_events: int
    total_minutes: int
    last_activity_at: Optional[datetime] = None
    days_since_last_activity: Optional[int] = None


# --- assessments -----------------------------------------------------------
class AssessmentCreate(BaseModel):
    course_pk: int
    title: str = Field(min_length=2, max_length=150)
    assessment_type: str
    max_marks: float = Field(gt=0, le=1000)
    weight_percent: float = Field(default=0, ge=0, le=100)
    due_at: datetime

    @field_validator("assessment_type")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in ASSESSMENT_TYPES:
            raise ValueError(f"assessment_type must be one of {', '.join(ASSESSMENT_TYPES)}")
        return v


class AssessmentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=150)
    assessment_type: Optional[str] = None
    max_marks: Optional[float] = Field(default=None, gt=0, le=1000)
    weight_percent: Optional[float] = Field(default=None, ge=0, le=100)
    due_at: Optional[datetime] = None

    @field_validator("assessment_type")
    @classmethod
    def _known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ASSESSMENT_TYPES:
            raise ValueError(f"assessment_type must be one of {', '.join(ASSESSMENT_TYPES)}")
        return v


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assessment_id: int
    course_pk: int
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    title: str
    assessment_type: str
    max_marks: float
    weight_percent: float
    due_at: datetime
    created_by: Optional[int] = None
    graded_count: int = 0
    expected_count: int = 0
    avg_percentage: Optional[float] = None


class ResultUpsert(BaseModel):
    """Enter or correct one student's marks.

    ``marks_obtained = None`` records a submission (or its absence)
    without a grade; the risk engine then excludes the row from the
    academic average rather than counting it as zero.
    """

    assessment_id: int
    enrollment_id: int
    marks_obtained: Optional[float] = Field(default=None, ge=0, le=1000)
    submitted_at: Optional[datetime] = None
    attempt_no: int = Field(default=1, ge=1, le=10)


class ResultBulkRow(BaseModel):
    enrollment_id: int
    marks_obtained: Optional[float] = Field(default=None, ge=0, le=1000)
    submitted_at: Optional[datetime] = None


class ResultBulkUpsert(BaseModel):
    assessment_id: int
    rows: List[ResultBulkRow] = Field(min_length=1, max_length=500)


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    result_id: int
    assessment_id: int
    enrollment_id: int
    marks_obtained: Optional[float] = None
    max_marks: Optional[float] = None
    percentage: Optional[float] = None
    submitted_at: Optional[datetime] = None
    submission_status: str
    attempt_no: int
    graded_by: Optional[int] = None
    graded_at: Optional[datetime] = None
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    assessment_title: Optional[str] = None
    assessment_type: Optional[str] = None
    course_code: Optional[str] = None
    due_at: Optional[datetime] = None


class PerformanceTrendPoint(BaseModel):
    period: str
    label: Optional[str] = None
    graded_results: int
    avg_percentage: Optional[float] = None
