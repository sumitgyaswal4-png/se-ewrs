"""Risk assessment, alert and intervention schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import (
    ALERT_STATUSES,
    INTERVENTION_OUTCOMES,
    INTERVENTION_TYPES,
    RESOLUTION_STATUSES,
)


# --- risk ------------------------------------------------------------------
class RiskRow(BaseModel):
    """One row of the risk-analysis table."""

    # protected_namespaces is cleared so the model_version column name
    # (which mirrors risk_assessments.model_version) is allowed.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    enrollment_id: int
    risk_id: Optional[int] = None
    student_pk: int
    student_id: str
    student_name: str
    student_semester: Optional[int] = None
    dept_id: Optional[int] = None
    dept_code: Optional[str] = None
    course_pk: int
    course_code: str
    course_name: str

    risk_score: Optional[float] = None
    risk_category: str = "INSUFFICIENT_DATA"
    data_completeness: str = "INSUFFICIENT"
    missing_data_reasons: Optional[str] = None
    contributing_factors: Optional[str] = None

    attendance_percentage: Optional[float] = None
    avg_assessment_percentage: Optional[float] = None
    engagement_score: Optional[float] = None
    attendance_risk: Optional[float] = None
    academic_risk: Optional[float] = None
    engagement_risk: Optional[float] = None

    sessions_held: int = 0
    sessions_attended: int = 0
    late_submissions: int = 0
    missing_submissions: int = 0
    graded_assessments: int = 0
    login_count_30d: int = 0
    days_since_last_activity: Optional[int] = None
    last_assessment_date: Optional[date] = None
    last_activity_at: Optional[datetime] = None
    calculated_at: Optional[datetime] = None
    model_version: Optional[str] = None

    open_alert_id: Optional[int] = None
    open_alert_status: Optional[str] = None


class RiskComponent(BaseModel):
    """One weighted component, as shown in the risk breakdown chart."""

    name: str
    observed_value: Optional[float] = None
    observed_label: str
    risk_value: Optional[float] = None
    weight: float
    effective_weight: float
    contribution: Optional[float] = None
    available: bool
    unavailable_reason: Optional[str] = None


class RiskDetail(BaseModel):
    """Full explanation of a single enrolment's risk score."""

    row: RiskRow
    components: List[RiskComponent]
    engagement_breakdown: Dict[str, Any] = Field(default_factory=dict)
    thresholds: Dict[str, int]
    weights: Dict[str, float]
    history: List["RiskHistoryPoint"] = Field(default_factory=list)
    disclaimer: str = (
        "This score is an early-warning indicator intended to prompt a "
        "conversation. It is not a judgement about the student's ability."
    )


class RiskHistoryPoint(BaseModel):
    calculated_at: datetime
    risk_score: Optional[float] = None
    risk_category: str
    attendance_percentage: Optional[float] = None
    avg_assessment_percentage: Optional[float] = None
    engagement_score: Optional[float] = None


class RecalculateRequest(BaseModel):
    course_pk: Optional[int] = Field(
        default=None, description="Limit the run to one course; omit for all courses"
    )
    enrollment_id: Optional[int] = Field(
        default=None, description="Recalculate a single enrolment"
    )


class RecalculateResponse(BaseModel):
    enrollments_processed: int
    alerts_opened: int
    alerts_updated: int
    alerts_auto_resolved: int
    detail: str


# --- alerts ----------------------------------------------------------------
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: int
    enrollment_id: int
    risk_id: Optional[int] = None
    risk_score: float
    risk_category: str
    triggering_factors: Optional[str] = None
    status: str
    assigned_to: Optional[int] = None
    assignee_name: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    student_pk: int
    student_id: str
    student_name: str
    student_semester: Optional[int] = None
    dept_code: Optional[str] = None
    course_pk: int
    course_code: str
    course_name: str
    intervention_count: int = 0
    age_days: int = 0


class AlertStatusRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: int
    old_status: Optional[str] = None
    new_status: str
    changed_by: Optional[int] = None
    changed_by_name: Optional[str] = None
    note: Optional[str] = None
    changed_at: datetime


class AlertDetail(BaseModel):
    alert: AlertOut
    history: List[AlertStatusRow]
    interventions: List["InterventionOut"]
    risk: Optional[RiskRow] = None


class AlertPatch(BaseModel):
    """Change an alert's status and/or its assignee.

    Legal transitions are NEW -> ACKNOWLEDGED | IN_PROGRESS | RESOLVED,
    ACKNOWLEDGED -> IN_PROGRESS | RESOLVED, IN_PROGRESS -> RESOLVED.
    RESOLVED is terminal.
    """

    status: Optional[str] = None
    assigned_to: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def _known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALERT_STATUSES:
            raise ValueError(f"status must be one of {', '.join(ALERT_STATUSES)}")
        return v

    @model_validator(mode="after")
    def _something_to_do(self):
        if self.status is None and self.assigned_to is None:
            raise ValueError("Provide status, assigned_to, or both")
        return self


# --- interventions ---------------------------------------------------------
class InterventionCreate(BaseModel):
    enrollment_id: int
    alert_id: Optional[int] = None
    intervention_type: str
    assigned_advisor_id: Optional[int] = None
    contact_date: date
    notes: Optional[str] = Field(default=None, max_length=4000)
    action_plan: Optional[str] = Field(default=None, max_length=4000)
    follow_up_date: Optional[date] = None
    outcome: str = "PENDING"
    resolution_status: str = "OPEN"

    @field_validator("intervention_type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        if v not in INTERVENTION_TYPES:
            raise ValueError(
                f"intervention_type must be one of {', '.join(INTERVENTION_TYPES)}"
            )
        return v

    @field_validator("outcome")
    @classmethod
    def _outcome_known(cls, v: str) -> str:
        if v not in INTERVENTION_OUTCOMES:
            raise ValueError(f"outcome must be one of {', '.join(INTERVENTION_OUTCOMES)}")
        return v

    @field_validator("resolution_status")
    @classmethod
    def _res_known(cls, v: str) -> str:
        if v not in RESOLUTION_STATUSES:
            raise ValueError(
                f"resolution_status must be one of {', '.join(RESOLUTION_STATUSES)}"
            )
        return v

    @model_validator(mode="after")
    def _dates_sane(self):
        if self.follow_up_date is not None and self.follow_up_date < self.contact_date:
            raise ValueError("follow_up_date cannot be before contact_date")
        return self


class InterventionUpdate(BaseModel):
    intervention_type: Optional[str] = None
    assigned_advisor_id: Optional[int] = None
    contact_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    action_plan: Optional[str] = Field(default=None, max_length=4000)
    follow_up_date: Optional[date] = None
    outcome: Optional[str] = None
    resolution_status: Optional[str] = None

    @field_validator("intervention_type")
    @classmethod
    def _type_known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in INTERVENTION_TYPES:
            raise ValueError(
                f"intervention_type must be one of {', '.join(INTERVENTION_TYPES)}"
            )
        return v

    @field_validator("outcome")
    @classmethod
    def _outcome_known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in INTERVENTION_OUTCOMES:
            raise ValueError(f"outcome must be one of {', '.join(INTERVENTION_OUTCOMES)}")
        return v

    @field_validator("resolution_status")
    @classmethod
    def _res_known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in RESOLUTION_STATUSES:
            raise ValueError(
                f"resolution_status must be one of {', '.join(RESOLUTION_STATUSES)}"
            )
        return v


class InterventionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    intervention_id: int
    enrollment_id: int
    alert_id: Optional[int] = None
    intervention_type: str
    assigned_advisor_id: Optional[int] = None
    advisor_name: Optional[str] = None
    contact_date: date
    notes: Optional[str] = None
    action_plan: Optional[str] = None
    follow_up_date: Optional[date] = None
    outcome: str
    resolution_status: str
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    student_pk: Optional[int] = None
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    course_pk: Optional[int] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    current_risk_score: Optional[float] = None
    current_risk_category: Optional[str] = None


RiskDetail.model_rebuild()
AlertDetail.model_rebuild()
