"""Course catalogue, instructor assignment and class rosters."""

from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import P_COURSES_READ, P_COURSES_WRITE
from app.models import Course, CourseInstructor, Department, Enrollment, Student, User
from app.schemas.academics import (
    CourseCreate,
    CourseOut,
    CourseUpdate,
    InstructorAssign,
    InstructorRef,
)
from app.schemas.common import Message, Page
from app.services import audit
from app.services.queries import course_stats_sq, risk_summary_select

router = APIRouter(dependencies=[Depends(require_permissions(P_COURSES_READ))])

SORTABLE = {
    "course_code": Course.course_code,
    "course_name": Course.course_name,
    "semester": Course.semester,
    "credits": Course.credits,
}

#: Only these roles may be attached to a course.
TEACHING_ROLES = ("INSTRUCTOR", "TA", "ADMIN")


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)


def _course_out(row, instructors: List[InstructorRef]) -> CourseOut:
    """Build the response explicitly.

    ``CourseOut.instructors`` holds flattened ``InstructorRef`` rows while
    ``Course.instructors`` is the raw association relationship, so
    ``model_validate`` on the ORM object would try to coerce the wrong
    shape. Mapping the fields by hand keeps the two apart.
    """
    course: Course = row["Course"]
    return CourseOut(
        course_pk=course.course_pk,
        course_code=course.course_code,
        course_name=course.course_name,
        dept_id=course.dept_id,
        dept_code=row["dept_code"],
        semester=course.semester,
        credits=course.credits,
        academic_term=course.academic_term,
        total_sessions=course.total_sessions,
        is_active=course.is_active,
        enrolled_count=row["enrolled_count"] or 0,
        avg_attendance_percentage=_as_float(row["avg_attendance_percentage"]),
        avg_assessment_percentage=_as_float(row["avg_assessment_percentage"]),
        high_risk_count=row["high_risk_count"] or 0,
        instructors=instructors,
    )


def _instructors_for(db: DbSession, course_pks: List[int]) -> dict:
    if not course_pks:
        return {}
    rows = db.execute(
        select(CourseInstructor.course_pk, User, CourseInstructor.role_in_course)
        .join(User, User.user_id == CourseInstructor.user_id)
        .where(CourseInstructor.course_pk.in_(course_pks))
        .order_by(CourseInstructor.role_in_course, User.full_name)
    ).all()
    grouped: dict = {pk: [] for pk in course_pks}
    for course_pk, user, role_in_course in rows:
        grouped[course_pk].append(
            InstructorRef(
                user_id=user.user_id,
                full_name=user.full_name,
                role=user.role,
                role_in_course=role_in_course,
            )
        )
    return grouped


@router.get("", response_model=Page[CourseOut], summary="List courses with their statistics")
def list_courses(
    db: DbSession,
    page: Pagination,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    dept_id: Annotated[Optional[int], Query()] = None,
    semester: Annotated[Optional[int], Query(ge=1, le=12)] = None,
    academic_term: Annotated[Optional[str], Query(max_length=20)] = None,
    is_active: Annotated[Optional[bool], Query()] = None,
    sort_by: Annotated[str, Query()] = "course_code",
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> Page[CourseOut]:
    if sort_by not in SORTABLE:
        raise ValidationError(f"sort_by must be one of {', '.join(SORTABLE)}")

    stats = course_stats_sq()
    stmt = (
        select(Course, Department.dept_code, stats)
        .join(Department, Department.dept_id == Course.dept_id)
        .outerjoin(stats, stats.c.course_pk == Course.course_pk)
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Course.course_code.ilike(pattern), Course.course_name.ilike(pattern))
        )
    if dept_id is not None:
        stmt = stmt.where(Course.dept_id == dept_id)
    if semester is not None:
        stmt = stmt.where(Course.semester == semester)
    if academic_term:
        stmt = stmt.where(Course.academic_term == academic_term)
    if is_active is not None:
        stmt = stmt.where(Course.is_active == is_active)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    column = SORTABLE[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    rows = list(db.execute(stmt.offset(page.offset).limit(page.limit)).mappings())
    instructors = _instructors_for(db, [r["Course"].course_pk for r in rows])

    items = [
        _course_out(r, instructors.get(r["Course"].course_pk, [])) for r in rows
    ]
    return Page.build(items, total, page.page, page.page_size)


@router.post(
    "",
    response_model=CourseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_COURSES_WRITE))],
    summary="Create a course",
)
def create_course(payload: CourseCreate, actor: CurrentUser, db: DbSession) -> CourseOut:
    if not db.get(Department, payload.dept_id):
        raise ValidationError(f"Department {payload.dept_id} does not exist")
    clash = db.execute(
        select(Course.course_pk).where(
            Course.course_code == payload.course_code,
            Course.academic_term == payload.academic_term,
        )
    ).scalar_one_or_none()
    if clash:
        raise ConflictError(
            f"Course {payload.course_code} already exists for term {payload.academic_term}"
        )

    course = Course(
        course_code=payload.course_code,
        course_name=payload.course_name.strip(),
        dept_id=payload.dept_id,
        semester=payload.semester,
        credits=payload.credits,
        academic_term=payload.academic_term,
        total_sessions=payload.total_sessions,
        is_active=True,
    )
    db.add(course)
    db.flush()

    for user_id in dict.fromkeys(payload.instructor_ids):
        _attach_instructor(db, course.course_pk, user_id, "PRIMARY")

    audit.record(
        db,
        action="INSERT",
        entity_type="courses",
        entity_id=course.course_pk,
        user_id=actor.user_id,
        new_values={
            "course_code": course.course_code,
            "academic_term": course.academic_term,
            "dept_id": course.dept_id,
        },
    )
    db.commit()
    return get_course(course.course_pk, db)


@router.get("/{course_pk}", response_model=CourseOut, summary="Fetch one course")
def get_course(course_pk: int, db: DbSession) -> CourseOut:
    stats = course_stats_sq()
    row = db.execute(
        select(Course, Department.dept_code, stats)
        .join(Department, Department.dept_id == Course.dept_id)
        .outerjoin(stats, stats.c.course_pk == Course.course_pk)
        .where(Course.course_pk == course_pk)
    ).mappings().one_or_none()
    if row is None:
        raise NotFoundError(f"Course {course_pk} was not found")

    return _course_out(row, _instructors_for(db, [course_pk]).get(course_pk, []))


@router.put(
    "/{course_pk}",
    response_model=CourseOut,
    dependencies=[Depends(require_permissions(P_COURSES_WRITE))],
    summary="Update a course",
)
def update_course(
    course_pk: int, payload: CourseUpdate, actor: CurrentUser, db: DbSession
) -> CourseOut:
    course = db.get(Course, course_pk)
    if course is None:
        raise NotFoundError(f"Course {course_pk} was not found")

    before = {
        "course_name": course.course_name,
        "semester": course.semester,
        "credits": course.credits,
        "is_active": course.is_active,
    }
    data = payload.model_dump(exclude_unset=True)
    if data.get("dept_id") is not None and not db.get(Department, data["dept_id"]):
        raise ValidationError(f"Department {data['dept_id']} does not exist")
    if data.get("academic_term"):
        clash = db.execute(
            select(Course.course_pk).where(
                Course.course_code == course.course_code,
                Course.academic_term == data["academic_term"],
                Course.course_pk != course_pk,
            )
        ).scalar_one_or_none()
        if clash:
            raise ConflictError(
                f"Course {course.course_code} already exists for term "
                f"{data['academic_term']}"
            )

    for key, value in data.items():
        setattr(course, key, value)

    audit.record(
        db,
        action="UPDATE",
        entity_type="courses",
        entity_id=course.course_pk,
        user_id=actor.user_id,
        old_values=before,
        new_values=data,
    )
    db.commit()
    return get_course(course_pk, db)


@router.get(
    "/{course_pk}/roster",
    summary="Enrolled students for a course, with their current risk band",
)
def course_roster(course_pk: int, db: DbSession) -> List[dict]:
    """The roster used by the attendance and grade-entry screens."""
    if db.get(Course, course_pk) is None:
        raise NotFoundError(f"Course {course_pk} was not found")

    rows = db.execute(
        risk_summary_select()
        .where(Enrollment.course_pk == course_pk, Enrollment.status == "ACTIVE")
        .order_by(Student.student_id)
    ).mappings()
    return [
        {
            "enrollment_id": r["enrollment_id"],
            "student_pk": r["student_pk"],
            "student_id": r["student_id"],
            "student_name": r["student_name"],
            "semester": r["student_semester"],
            "attendance_percentage": _as_float(r["live_attendance_percentage"]),
            "avg_assessment_percentage": _as_float(r["live_assessment_percentage"]),
            "risk_score": _as_float(r["risk_score"]),
            "risk_category": r["risk_category"],
        }
        for r in rows
    ]


@router.post(
    "/{course_pk}/instructors",
    response_model=Message,
    dependencies=[Depends(require_permissions(P_COURSES_WRITE))],
    summary="Assign an instructor to a course",
)
def assign_instructor(
    course_pk: int, payload: InstructorAssign, actor: CurrentUser, db: DbSession
) -> Message:
    if db.get(Course, course_pk) is None:
        raise NotFoundError(f"Course {course_pk} was not found")
    _attach_instructor(db, course_pk, payload.user_id, payload.role_in_course)
    audit.record(
        db,
        action="INSERT",
        entity_type="course_instructors",
        entity_id=f"{course_pk}:{payload.user_id}",
        user_id=actor.user_id,
        new_values={"course_pk": course_pk, "user_id": payload.user_id},
    )
    db.commit()
    return Message(detail="Instructor assigned")


@router.delete(
    "/{course_pk}/instructors/{user_id}",
    response_model=Message,
    dependencies=[Depends(require_permissions(P_COURSES_WRITE))],
    summary="Remove an instructor from a course",
)
def unassign_instructor(
    course_pk: int, user_id: int, actor: CurrentUser, db: DbSession
) -> Message:
    link = db.execute(
        select(CourseInstructor).where(
            CourseInstructor.course_pk == course_pk, CourseInstructor.user_id == user_id
        )
    ).scalar_one_or_none()
    if link is None:
        raise NotFoundError("That instructor is not assigned to this course")
    db.delete(link)
    audit.record(
        db,
        action="DELETE",
        entity_type="course_instructors",
        entity_id=f"{course_pk}:{user_id}",
        user_id=actor.user_id,
        old_values={"course_pk": course_pk, "user_id": user_id},
    )
    db.commit()
    return Message(detail="Instructor removed")


def _attach_instructor(db: DbSession, course_pk: int, user_id: int, role_in_course: str) -> None:
    """Validate and insert one course_instructors row."""
    user = db.get(User, user_id)
    if user is None:
        raise ValidationError(f"User {user_id} does not exist")
    if user.role not in TEACHING_ROLES:
        raise ValidationError(
            f"{user.full_name} has role {user.role} and cannot be assigned to a course "
            f"(allowed: {', '.join(TEACHING_ROLES)})"
        )
    exists = db.execute(
        select(CourseInstructor.course_instructor_id).where(
            CourseInstructor.course_pk == course_pk, CourseInstructor.user_id == user_id
        )
    ).scalar_one_or_none()
    if exists:
        raise ConflictError(f"{user.full_name} is already assigned to this course")
    db.add(
        CourseInstructor(
            course_pk=course_pk, user_id=user_id, role_in_course=role_in_course
        )
    )
