"""Reference data the frontend needs to populate forms and filters."""

from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_permissions
from app.core.exceptions import ConflictError
from app.core.permissions import P_COURSES_READ, P_SETTINGS_WRITE
from app.models import (
    ACTIVITY_TYPES,
    ALERT_STATUSES,
    ASSESSMENT_TYPES,
    ATTENDANCE_STATUSES,
    COURSE_ROLES,
    ENROLLMENT_STATUSES,
    INTERVENTION_OUTCOMES,
    INTERVENTION_TYPES,
    RESOLUTION_STATUSES,
    RISK_CATEGORIES,
    SUBMISSION_STATUSES,
    USER_ROLES,
    Course,
    Department,
    Student,
)
from app.schemas.academics import DepartmentCreate, DepartmentOut
from app.services import audit

router = APIRouter()

#: Human-readable labels for every enumerated domain, so the UI never has
#: to hardcode the database vocabulary.
ENUM_LABELS: Dict[str, Dict[str, str]] = {
    "user_roles": {
        "ADMIN": "Administrator",
        "INSTRUCTOR": "Instructor",
        "TA": "Teaching Assistant",
        "ADVISOR": "Academic Advisor",
        "CHAIR": "Department Chair",
    },
    "course_roles": {
        "PRIMARY": "Primary instructor",
        "CO_INSTRUCTOR": "Co-instructor",
        "TA": "Teaching assistant",
    },
    "enrollment_statuses": {
        "ACTIVE": "Active",
        "DROPPED": "Dropped",
        "COMPLETED": "Completed",
    },
    "attendance_statuses": {
        "PRESENT": "Present",
        "ABSENT": "Absent",
        "LATE": "Late",
        "EXCUSED": "Excused",
    },
    "activity_types": {
        "LOGIN": "LMS login",
        "RESOURCE_VIEW": "Resource viewed",
        "FORUM_POST": "Forum post",
        "VIDEO_WATCH": "Video watched",
        "QUIZ_ATTEMPT": "Quiz attempt",
        "ASSIGNMENT_SUBMIT": "Assignment submitted",
    },
    "assessment_types": {
        "ASSIGNMENT": "Assignment",
        "QUIZ": "Quiz",
        "MIDTERM": "Mid-term examination",
        "FINAL": "Final examination",
        "PROJECT": "Project",
        "LAB": "Lab work",
    },
    "submission_statuses": {"ON_TIME": "On time", "LATE": "Late", "MISSING": "Missing"},
    "risk_categories": {
        "LOW": "Low risk",
        "MEDIUM": "Medium risk",
        "HIGH": "High risk",
        "INSUFFICIENT_DATA": "Needs more data",
    },
    "alert_statuses": {
        "NEW": "New",
        "ACKNOWLEDGED": "Acknowledged",
        "IN_PROGRESS": "In progress",
        "RESOLVED": "Resolved",
    },
    "intervention_types": {
        "COUNSELING": "Counselling",
        "TUTORING_REFERRAL": "Tutoring referral",
        "ASSIGNMENT_SUPPORT": "Assignment support",
        "ATTENDANCE_FOLLOWUP": "Attendance follow-up",
        "ACADEMIC_ADVISING": "Academic advising",
        "PARENT_CONTACT": "Guardian contact",
    },
    "intervention_outcomes": {
        "PENDING": "Pending",
        "IMPROVED": "Improved",
        "NO_CHANGE": "No change",
        "DECLINED": "Student declined",
        "ESCALATED": "Escalated",
    },
    "resolution_statuses": {"OPEN": "Open", "IN_PROGRESS": "In progress", "CLOSED": "Closed"},
}

_VOCABULARY = {
    "user_roles": USER_ROLES,
    "course_roles": COURSE_ROLES,
    "enrollment_statuses": ENROLLMENT_STATUSES,
    "attendance_statuses": ATTENDANCE_STATUSES,
    "activity_types": ACTIVITY_TYPES,
    "assessment_types": ASSESSMENT_TYPES,
    "submission_statuses": SUBMISSION_STATUSES,
    "risk_categories": RISK_CATEGORIES,
    "alert_statuses": ALERT_STATUSES,
    "intervention_types": INTERVENTION_TYPES,
    "intervention_outcomes": INTERVENTION_OUTCOMES,
    "resolution_statuses": RESOLUTION_STATUSES,
}


@router.get("/enums", summary="Every enumerated value with its display label")
def enums(_: CurrentUser) -> Dict[str, List[Dict[str, str]]]:
    """Single source of truth for dropdown options.

    The values come from the ORM's enum tuples, which mirror the MySQL
    ``ENUM`` columns, so the UI cannot offer a value the database would
    reject.
    """
    return {
        group: [
            {"value": value, "label": ENUM_LABELS.get(group, {}).get(value, value)}
            for value in values
        ]
        for group, values in _VOCABULARY.items()
    }


@router.get("/departments", response_model=List[DepartmentOut], summary="List departments")
def list_departments(db: DbSession, _: CurrentUser) -> List[DepartmentOut]:
    return [
        DepartmentOut.model_validate(d)
        for d in db.execute(select(Department).order_by(Department.dept_code)).scalars()
    ]


@router.post(
    "/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_SETTINGS_WRITE))],
    summary="Create a department",
)
def create_department(
    payload: DepartmentCreate, actor: CurrentUser, db: DbSession
) -> DepartmentOut:
    clash = db.execute(
        select(Department.dept_id).where(
            (Department.dept_code == payload.dept_code.upper())
            | (Department.dept_name == payload.dept_name)
        )
    ).scalar_one_or_none()
    if clash:
        raise ConflictError("A department with that code or name already exists")

    department = Department(
        dept_code=payload.dept_code.upper().strip(), dept_name=payload.dept_name.strip()
    )
    db.add(department)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="departments",
        entity_id=department.dept_id,
        user_id=actor.user_id,
        new_values={"dept_code": department.dept_code, "dept_name": department.dept_name},
    )
    db.commit()
    return DepartmentOut.model_validate(department)


@router.get(
    "/course-options",
    dependencies=[Depends(require_permissions(P_COURSES_READ))],
    summary="Lightweight course list for filter dropdowns",
)
def course_options(
    db: DbSession,
    only_active: Annotated[bool, Query()] = True,
) -> List[Dict[str, object]]:
    stmt = select(Course.course_pk, Course.course_code, Course.course_name, Course.semester)
    if only_active:
        stmt = stmt.where(Course.is_active.is_(True))
    return [
        {
            "course_pk": r[0],
            "course_code": r[1],
            "course_name": r[2],
            "semester": r[3],
            "label": f"{r[1]} - {r[2]}",
        }
        for r in db.execute(stmt.order_by(Course.course_code)).all()
    ]


@router.get(
    "/student-options",
    dependencies=[Depends(require_permissions(P_COURSES_READ))],
    summary="Lightweight student list for enrolment pickers",
)
def student_options(
    db: DbSession,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> List[Dict[str, object]]:
    stmt = select(
        Student.student_pk, Student.student_id, Student.full_name, Student.semester
    ).where(Student.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            (Student.student_id.ilike(pattern)) | (Student.full_name.ilike(pattern))
        )
    if dept_id is not None:
        stmt = stmt.where(Student.dept_id == dept_id)
    return [
        {
            "student_pk": r[0],
            "student_id": r[1],
            "full_name": r[2],
            "semester": r[3],
            "label": f"{r[1]} - {r[2]}",
        }
        for r in db.execute(stmt.order_by(Student.student_id).limit(limit)).all()
    ]
