"""Student management: CRUD, search, de-activation and the full profile."""

from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import P_STUDENTS_READ, P_STUDENTS_WRITE
from app.models import Department, Enrollment, Student
from app.schemas.academics import (
    StudentCourseRow,
    StudentCreate,
    StudentOut,
    StudentProfile,
    StudentSummary,
    StudentUpdate,
    StudentWithSummary,
)
from app.schemas.common import Message, Page
from app.services import audit
from app.services.queries import risk_summary_select, student_stats_sq

router = APIRouter(dependencies=[Depends(require_permissions(P_STUDENTS_READ))])

SORTABLE = {
    "student_id": Student.student_id,
    "full_name": Student.full_name,
    "semester": Student.semester,
    "enrollment_year": Student.enrollment_year,
    "created_at": Student.created_at,
}


def _category_for(score: Optional[float], high: int = 60, medium: int = 30) -> Optional[str]:
    if score is None:
        return None
    if score >= high:
        return "HIGH"
    if score >= medium:
        return "MEDIUM"
    return "LOW"


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)


@router.get("", response_model=Page[StudentWithSummary], summary="List and search students")
def list_students(
    db: DbSession,
    page: Pagination,
    search: Annotated[
        Optional[str], Query(max_length=120, description="Matches roll number, name or email")
    ] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    semester: Annotated[Optional[int], Query(ge=1, le=12)] = None,
    enrollment_year: Annotated[Optional[int], Query(ge=2000, le=2100)] = None,
    is_active: Annotated[Optional[bool], Query()] = None,
    risk_category: Annotated[
        Optional[Literal["LOW", "MEDIUM", "HIGH"]],
        Query(description="Keep students whose worst course risk is this band"),
    ] = None,
    sort_by: Annotated[str, Query()] = "student_id",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> Page[StudentWithSummary]:
    """Paginated, sortable, filterable student list with each student's
    academic and engagement summary aggregated in SQL."""
    if sort_by not in SORTABLE:
        raise ValidationError(f"sort_by must be one of {', '.join(SORTABLE)}")

    stats = student_stats_sq()
    stmt = (
        select(Student, Department.dept_code, Department.dept_name, stats)
        .join(Department, Department.dept_id == Student.dept_id)
        .outerjoin(stats, stats.c.student_pk == Student.student_pk)
    )

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Student.student_id.ilike(pattern),
                Student.full_name.ilike(pattern),
                Student.email.ilike(pattern),
            )
        )
    if dept_id is not None:
        stmt = stmt.where(Student.dept_id == dept_id)
    if semester is not None:
        stmt = stmt.where(Student.semester == semester)
    if enrollment_year is not None:
        stmt = stmt.where(Student.enrollment_year == enrollment_year)
    if is_active is not None:
        stmt = stmt.where(Student.is_active == is_active)
    if risk_category == "HIGH":
        stmt = stmt.where(stats.c.high_risk_courses > 0)
    elif risk_category == "MEDIUM":
        stmt = stmt.where(stats.c.medium_risk_courses > 0, stats.c.high_risk_courses == 0)
    elif risk_category == "LOW":
        stmt = stmt.where(
            func.coalesce(stats.c.high_risk_courses, 0) == 0,
            func.coalesce(stats.c.medium_risk_courses, 0) == 0,
            stats.c.enrolled_courses > 0,
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    column = SORTABLE[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    items: List[StudentWithSummary] = []
    for row in db.execute(stmt.offset(page.offset).limit(page.limit)).mappings():
        student: Student = row["Student"]
        highest = _as_float(row["highest_risk_score"])
        items.append(
            StudentWithSummary(
                **StudentOut.model_validate(student).model_dump(
                    exclude={"dept_code", "dept_name"}
                ),
                dept_code=row["dept_code"],
                dept_name=row["dept_name"],
                summary=StudentSummary(
                    enrolled_courses=row["enrolled_courses"] or 0,
                    attendance_percentage=_as_float(row["attendance_percentage"]),
                    avg_assessment_percentage=_as_float(row["avg_assessment_percentage"]),
                    highest_risk_score=highest,
                    highest_risk_category=_category_for(highest),
                    open_alerts=row["open_alerts"] or 0,
                    late_submissions=row["late_submissions"] or 0,
                    missing_submissions=row["missing_submissions"] or 0,
                    last_activity_at=row["last_activity_at"],
                ),
            )
        )
    return Page.build(items, total, page.page, page.page_size)


@router.post(
    "",
    response_model=StudentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_STUDENTS_WRITE))],
    summary="Add a student",
)
def create_student(payload: StudentCreate, actor: CurrentUser, db: DbSession) -> StudentOut:
    if not db.get(Department, payload.dept_id):
        raise ValidationError(f"Department {payload.dept_id} does not exist")
    clash = db.execute(
        select(Student.student_pk).where(
            or_(
                Student.student_id == payload.student_id,
                func.lower(Student.email) == payload.email.lower(),
            )
        )
    ).scalar_one_or_none()
    if clash:
        raise ConflictError(
            f"A student with roll number {payload.student_id} or email "
            f"{payload.email} already exists"
        )

    student = Student(
        student_id=payload.student_id,
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        dept_id=payload.dept_id,
        semester=payload.semester,
        enrollment_year=payload.enrollment_year,
        phone=payload.phone,
        is_active=True,
    )
    db.add(student)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="students",
        entity_id=student.student_pk,
        user_id=actor.user_id,
        new_values={
            "student_id": student.student_id,
            "full_name": student.full_name,
            "dept_id": student.dept_id,
            "semester": student.semester,
        },
    )
    db.commit()
    return _student_out(db, student)


@router.get("/{student_pk}", response_model=StudentOut, summary="Fetch one student")
def get_student(student_pk: int, db: DbSession) -> StudentOut:
    student = db.get(Student, student_pk)
    if student is None:
        raise NotFoundError(f"Student {student_pk} was not found")
    return _student_out(db, student)


@router.get(
    "/{student_pk}/profile",
    response_model=StudentProfile,
    summary="Full profile: summary plus a row per enrolled course",
)
def student_profile(student_pk: int, db: DbSession) -> StudentProfile:
    student = db.get(Student, student_pk)
    if student is None:
        raise NotFoundError(f"Student {student_pk} was not found")

    rows = db.execute(
        risk_summary_select().where(Enrollment.student_pk == student_pk).order_by(
            Enrollment.enrollment_id
        )
    ).mappings()

    courses: List[StudentCourseRow] = []
    att_values, aca_values = [], []
    late = missing = open_alerts = 0
    best_score: Optional[float] = None
    last_activity = None

    for row in rows:
        attendance = _as_float(row["attendance_percentage"]) or _as_float(
            row["live_attendance_percentage"]
        )
        assessment = _as_float(row["avg_assessment_percentage"]) or _as_float(
            row["live_assessment_percentage"]
        )
        score = _as_float(row["risk_score"])
        category = row["risk_category"]
        courses.append(
            StudentCourseRow(
                enrollment_id=row["enrollment_id"],
                course_pk=row["course_pk"],
                course_code=row["course_code"],
                course_name=row["course_name"],
                enrollment_status=row["enrollment_status"],
                sessions_held=row["sessions_held"] or 0,
                sessions_attended=row["sessions_attended"] or 0,
                attendance_percentage=attendance,
                graded_assessments=row["graded_assessments"] or 0,
                avg_assessment_percentage=assessment,
                late_submissions=row["late_submissions"] or 0,
                missing_submissions=row["missing_submissions"] or 0,
                risk_score=score,
                risk_category=category,
                last_activity_at=row["last_activity_at"],
            )
        )
        if attendance is not None:
            att_values.append(attendance)
        if assessment is not None:
            aca_values.append(assessment)
        late += row["late_submissions"] or 0
        missing += row["missing_submissions"] or 0
        if row["open_alert_id"] is not None:
            open_alerts += 1
        if score is not None and category in ("LOW", "MEDIUM", "HIGH"):
            best_score = score if best_score is None else max(best_score, score)
        if row["last_activity_at"] is not None:
            last_activity = (
                row["last_activity_at"]
                if last_activity is None
                else max(last_activity, row["last_activity_at"])
            )

    summary = StudentSummary(
        enrolled_courses=len(courses),
        attendance_percentage=round(sum(att_values) / len(att_values), 2) if att_values else None,
        avg_assessment_percentage=(
            round(sum(aca_values) / len(aca_values), 2) if aca_values else None
        ),
        highest_risk_score=best_score,
        highest_risk_category=_category_for(best_score),
        open_alerts=open_alerts,
        late_submissions=late,
        missing_submissions=missing,
        last_activity_at=last_activity,
    )
    return StudentProfile(student=_student_out(db, student), summary=summary, courses=courses)


@router.put(
    "/{student_pk}",
    response_model=StudentOut,
    dependencies=[Depends(require_permissions(P_STUDENTS_WRITE))],
    summary="Update a student",
)
def update_student(
    student_pk: int, payload: StudentUpdate, actor: CurrentUser, db: DbSession
) -> StudentOut:
    student = db.get(Student, student_pk)
    if student is None:
        raise NotFoundError(f"Student {student_pk} was not found")

    before = {
        "full_name": student.full_name,
        "email": student.email,
        "dept_id": student.dept_id,
        "semester": student.semester,
        "is_active": student.is_active,
    }
    data = payload.model_dump(exclude_unset=True)

    if data.get("email"):
        clash = db.execute(
            select(Student.student_pk).where(
                func.lower(Student.email) == data["email"].lower(),
                Student.student_pk != student_pk,
            )
        ).scalar_one_or_none()
        if clash:
            raise ConflictError(f"Email {data['email']} is already used by another student")
        data["email"] = data["email"].lower()
    if data.get("dept_id") is not None and not db.get(Department, data["dept_id"]):
        raise ValidationError(f"Department {data['dept_id']} does not exist")

    for key, value in data.items():
        setattr(student, key, value)

    audit.record(
        db,
        action="UPDATE",
        entity_type="students",
        entity_id=student.student_pk,
        user_id=actor.user_id,
        old_values=before,
        new_values=data,
    )
    db.commit()
    return _student_out(db, student)


@router.patch(
    "/{student_pk}/deactivate",
    response_model=Message,
    dependencies=[Depends(require_permissions(P_STUDENTS_WRITE))],
    summary="Deactivate a student record",
)
def deactivate_student(student_pk: int, actor: CurrentUser, db: DbSession) -> Message:
    """A soft delete.

    Student rows are never hard-deleted: attendance, grades, risk history
    and interventions all reference them, and that history is the point of
    the system. ``is_active = 0`` removes the student from active rosters
    and from the dashboard counters while preserving the audit trail.
    """
    student = db.get(Student, student_pk)
    if student is None:
        raise NotFoundError(f"Student {student_pk} was not found")
    if not student.is_active:
        return Message(detail=f"{student.student_id} is already inactive")

    student.is_active = False
    audit.record(
        db,
        action="DEACTIVATE",
        entity_type="students",
        entity_id=student.student_pk,
        user_id=actor.user_id,
        old_values={"is_active": True},
        new_values={"is_active": False},
    )
    db.commit()
    return Message(detail=f"{student.student_id} deactivated")


@router.patch(
    "/{student_pk}/reactivate",
    response_model=Message,
    dependencies=[Depends(require_permissions(P_STUDENTS_WRITE))],
    summary="Reactivate a student record",
)
def reactivate_student(student_pk: int, actor: CurrentUser, db: DbSession) -> Message:
    student = db.get(Student, student_pk)
    if student is None:
        raise NotFoundError(f"Student {student_pk} was not found")
    student.is_active = True
    audit.record(
        db,
        action="REACTIVATE",
        entity_type="students",
        entity_id=student.student_pk,
        user_id=actor.user_id,
        new_values={"is_active": True},
    )
    db.commit()
    return Message(detail=f"{student.student_id} reactivated")


def _student_out(db: DbSession, student: Student) -> StudentOut:
    dept = db.get(Department, student.dept_id)
    out = StudentOut.model_validate(student)
    if dept:
        out.dept_code = dept.dept_code
        out.dept_name = dept.dept_name
    return out
