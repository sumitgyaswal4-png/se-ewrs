"""Dashboard and report payloads."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RiskCount(BaseModel):
    category: str
    label: str
    count: int


class DashboardSummary(BaseModel):
    """Every figure here is aggregated in SQL -- nothing is hardcoded."""

    total_students: int
    total_courses: int
    total_enrollments: int
    total_departments: int
    high_risk: int
    medium_risk: int
    low_risk: int
    insufficient_data: int
    avg_attendance_percentage: Optional[float] = None
    avg_assessment_percentage: Optional[float] = None
    open_alerts: int
    unresolved_high_risk_alerts: int
    open_interventions: int
    assessments_due_next_7_days: int
    risk_distribution: List[RiskCount] = Field(default_factory=list)
    generated_at: datetime


class AlertPreview(BaseModel):
    alert_id: int
    student_id: str
    student_name: str
    course_code: str
    risk_score: float
    risk_category: str
    status: str
    triggering_factors: Optional[str] = None
    created_at: datetime
    age_days: int


class TrendPoint(BaseModel):
    period: str
    avg_percentage: Optional[float] = None
    graded_results: int = 0
    avg_attendance_percentage: Optional[float] = None


class RiskDistributionRow(BaseModel):
    group_key: str
    group_label: str
    low_risk: int = 0
    medium_risk: int = 0
    high_risk: int = 0
    insufficient_data: int = 0
    total: int = 0
    avg_risk_score: Optional[float] = None


class CoursePerformanceRow(BaseModel):
    course_pk: int
    course_code: str
    course_name: str
    dept_code: Optional[str] = None
    semester: int
    enrolled_students: int = 0
    assessment_count: int = 0
    graded_results: int = 0
    avg_percentage: Optional[float] = None
    pass_rate_percentage: Optional[float] = None
    avg_attendance_percentage: Optional[float] = None
    high_risk_count: int = 0


class CourseAttendanceRow(BaseModel):
    course_pk: int
    course_code: str
    course_name: str
    dept_code: Optional[str] = None
    enrolled_students: int
    total_sessions_held: int
    total_sessions_attended: int
    avg_attendance_percentage: Optional[float] = None
    students_below_75: int = 0


class SubmissionPatternRow(BaseModel):
    assessment_id: int
    assessment_title: str
    assessment_type: str
    course_code: str
    due_at: datetime
    total_expected: int
    on_time: int
    late: int
    missing: int
    on_time_rate: Optional[float] = None
    avg_percentage: Optional[float] = None


class DepartmentRiskRow(BaseModel):
    dept_id: int
    dept_code: str
    dept_name: str
    students_tracked: int = 0
    enrollments_tracked: int = 0
    high_risk: int = 0
    medium_risk: int = 0
    low_risk: int = 0
    insufficient_data: int = 0
    avg_risk_score: Optional[float] = None
    avg_attendance_percentage: Optional[float] = None
    avg_assessment_percentage: Optional[float] = None
    open_alerts: int = 0


class InterventionOutcomeRow(BaseModel):
    intervention_type: str
    total: int
    improved: int = 0
    no_change: int = 0
    pending: int = 0
    escalated: int = 0
    declined: int = 0
    improvement_rate: Optional[float] = None
    avg_current_risk: Optional[float] = None


class HighRiskStudentRow(BaseModel):
    student_pk: int
    student_id: str
    student_name: str
    dept_code: Optional[str] = None
    semester: int
    at_risk_courses: int
    courses: str
    avg_risk_score: Optional[float] = None
    max_risk_score: Optional[float] = None
    open_alerts: int = 0


class ReportFilters(BaseModel):
    """Echoed back with each report so the UI can show what was applied."""

    date_from: Optional[date] = None
    date_to: Optional[date] = None
    course_pk: Optional[int] = None
    dept_id: Optional[int] = None
    semester: Optional[int] = None
