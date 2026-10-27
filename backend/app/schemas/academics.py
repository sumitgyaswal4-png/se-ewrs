"""Department, student, course and enrolment schemas."""

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import COURSE_ROLES, ENROLLMENT_STATUSES


# --- departments -----------------------------------------------------------
class DepartmentCreate(BaseModel):
    dept_code: str = Field(min_length=2, max_length=10)
    dept_name: str = Field(min_length=3, max_length=120)


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dept_id: int
    dept_code: str
    dept_name: str


# --- students --------------------------------------------------------------
class StudentCreate(BaseModel):
    student_id: str = Field(min_length=3, max_length=20, description="Roll number")
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    dept_id: int
    semester: int = Field(ge=1, le=12)
    enrollment_year: int = Field(ge=2000, le=2100)
    phone: Optional[str] = Field(default=None, max_length=20)

    @field_validator("student_id")
    @classmethod
    def _strip_upper(cls, v: str) -> str:
        return v.strip().upper()


class StudentUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    dept_id: Optional[int] = None
    semester: Optional[int] = Field(default=None, ge=1, le=12)
    enrollment_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    phone: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_pk: int
    student_id: str
    full_name: str
    email: EmailStr
    dept_id: int
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None
    semester: int
    enrollment_year: int
    phone: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None


class StudentSummary(BaseModel):
    """Academic + engagement roll-up shown on the student list and profile."""

    enrolled_courses: int = 0
    attendance_percentage: Optional[float] = None
    avg_assessment_percentage: Optional[float] = None
    highest_risk_score: Optional[float] = None
    highest_risk_category: Optional[str] = None
    open_alerts: int = 0
    late_submissions: int = 0
    missing_submissions: int = 0
    last_activity_at: Optional[datetime] = None


class StudentWithSummary(StudentOut):
    summary: StudentSummary


class StudentCourseRow(BaseModel):
    """One (student, course) row on the student profile page."""

    enrollment_id: int
    course_pk: int
    course_code: str
    course_name: str
    enrollment_status: str
    sessions_held: int = 0
    sessions_attended: int = 0
    attendance_percentage: Optional[float] = None
    graded_assessments: int = 0
    avg_assessment_percentage: Optional[float] = None
    late_submissions: int = 0
    missing_submissions: int = 0
    risk_score: Optional[float] = None
    risk_category: Optional[str] = None
    last_activity_at: Optional[datetime] = None


class StudentProfile(BaseModel):
    student: StudentOut
    summary: StudentSummary
    courses: List[StudentCourseRow]
    #: The configured band edges, so the client colours the summary
    #: meters with the same thresholds the risk model is using rather
    #: than a hard-coded copy of them.
    thresholds: Dict[str, int]


# --- courses ---------------------------------------------------------------
class CourseCreate(BaseModel):
    course_code: str = Field(min_length=2, max_length=20)
    course_name: str = Field(min_length=3, max_length=150)
    dept_id: int
    semester: int = Field(ge=1, le=12)
    credits: int = Field(default=3, ge=1, le=10)
    academic_term: str = Field(min_length=4, max_length=20, examples=["2025-ODD"])
    total_sessions: int = Field(default=0, ge=0, le=500)
    instructor_ids: List[int] = Field(
        default_factory=list, description="Users to assign as instructors"
    )

    @field_validator("course_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class CourseUpdate(BaseModel):
    course_name: Optional[str] = Field(default=None, min_length=3, max_length=150)
    dept_id: Optional[int] = None
    semester: Optional[int] = Field(default=None, ge=1, le=12)
    credits: Optional[int] = Field(default=None, ge=1, le=10)
    academic_term: Optional[str] = Field(default=None, min_length=4, max_length=20)
    total_sessions: Optional[int] = Field(default=None, ge=0, le=500)
    is_active: Optional[bool] = None


class InstructorRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    role: str
    role_in_course: str


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_pk: int
    course_code: str
    course_name: str
    dept_id: int
    dept_code: Optional[str] = None
    semester: int
    credits: int
    academic_term: str
    total_sessions: int
    is_active: bool
    enrolled_count: int = 0
    instructors: List[InstructorRef] = Field(default_factory=list)
    avg_attendance_percentage: Optional[float] = None
    avg_assessment_percentage: Optional[float] = None
    high_risk_count: int = 0


class InstructorAssign(BaseModel):
    user_id: int
    role_in_course: str = "PRIMARY"

    @field_validator("role_in_course")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in COURSE_ROLES:
            raise ValueError(f"role_in_course must be one of {', '.join(COURSE_ROLES)}")
        return v


# --- enrolments ------------------------------------------------------------
class EnrollmentCreate(BaseModel):
    student_pk: int
    course_pk: int
    enrolled_on: Optional[date] = None


class EnrollmentBulkCreate(BaseModel):
    course_pk: int
    student_pks: List[int] = Field(min_length=1, max_length=500)


class EnrollmentUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in ENROLLMENT_STATUSES:
            raise ValueError(f"status must be one of {', '.join(ENROLLMENT_STATUSES)}")
        return v


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enrollment_id: int
    student_pk: int
    course_pk: int
    enrolled_on: date
    status: str
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None


class BulkEnrollResult(BaseModel):
    enrolled: List[int] = Field(default_factory=list, description="New enrollment_ids")
    skipped_duplicates: List[int] = Field(
        default_factory=list, description="student_pks already enrolled"
    )
    detail: str
