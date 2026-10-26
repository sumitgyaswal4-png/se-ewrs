"""Student-to-course enrolment.

Duplicate enrolment is prevented at three levels: the composite unique
key ``uq_enrollment_student_course``, an explicit pre-check that returns
a readable 409, and the bulk endpoint which reports duplicates as
``skipped`` rather than failing the whole batch.
"""

from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import P_COURSES_READ, P_ENROLLMENTS_WRITE
from app.models import Course, Enrollment, Student
from app.schemas.academics import (
    BulkEnrollResult,
    EnrollmentBulkCreate,
    EnrollmentCreate,
    EnrollmentOut,
    EnrollmentUpdate,
)
from app.schemas.common import Page
from app.services import audit

router = APIRouter(dependencies=[Depends(require_permissions(P_COURSES_READ))])


def _enrollment_out(db: DbSession, enrollment: Enrollment) -> EnrollmentOut:
    row = db.execute(
        select(
            Student.student_id, Student.full_name, Course.course_code, Course.course_name
        )
        .select_from(Enrollment)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .where(Enrollment.enrollment_id == enrollment.enrollment_id)
    ).one()
    out = EnrollmentOut.model_validate(enrollment)
    out.student_id, out.student_name, out.course_code, out.course_name = row
    return out


@router.get("", response_model=Page[EnrollmentOut], summary="List enrolments")
def list_enrollments(
    db: DbSession,
    page: Pagination,
    course_pk: Annotated[Optional[int], Query()] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
    enrollment_status: Annotated[Optional[str], Query()] = None,
) -> Page[EnrollmentOut]:
    stmt = (
        select(
            Enrollment,
            Student.student_id,
            Student.full_name,
            Course.course_code,
            Course.course_name,
        )
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
    )
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    if student_pk is not None:
        stmt = stmt.where(Enrollment.student_pk == student_pk)
    if enrollment_status:
        stmt = stmt.where(Enrollment.status == enrollment_status)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Student.student_id, Course.course_code)
        .offset(page.offset)
        .limit(page.limit)
    ).all()

    items = []
    for enrollment, student_id, student_name, course_code, course_name in rows:
        out = EnrollmentOut.model_validate(enrollment)
        out.student_id, out.student_name = student_id, student_name
        out.course_code, out.course_name = course_code, course_name
        items.append(out)
    return Page.build(items, total, page.page, page.page_size)


@router.post(
    "",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_ENROLLMENTS_WRITE))],
    summary="Enrol a student in a course",
)
def create_enrollment(
    payload: EnrollmentCreate, actor: CurrentUser, db: DbSession
) -> EnrollmentOut:
    student = db.get(Student, payload.student_pk)
    if student is None:
        raise ValidationError(f"Student {payload.student_pk} does not exist")
    if not student.is_active:
        raise ValidationError(f"{student.student_id} is inactive and cannot be enrolled")

    course = db.get(Course, payload.course_pk)
    if course is None:
        raise ValidationError(f"Course {payload.course_pk} does not exist")
    if not course.is_active:
        raise ValidationError(f"{course.course_code} is inactive and cannot take enrolments")

    duplicate = db.execute(
        select(Enrollment.enrollment_id).where(
            Enrollment.student_pk == payload.student_pk,
            Enrollment.course_pk == payload.course_pk,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise ConflictError(
            f"{student.student_id} is already enrolled in {course.course_code}"
        )

    enrollment = Enrollment(
        student_pk=payload.student_pk,
        course_pk=payload.course_pk,
        enrolled_on=payload.enrolled_on or date.today(),
        status="ACTIVE",
    )
    db.add(enrollment)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="enrollments",
        entity_id=enrollment.enrollment_id,
        user_id=actor.user_id,
        new_values={"student_pk": payload.student_pk, "course_pk": payload.course_pk},
    )
    db.commit()
    return _enrollment_out(db, enrollment)


@router.post(
    "/bulk",
    response_model=BulkEnrollResult,
    dependencies=[Depends(require_permissions(P_ENROLLMENTS_WRITE))],
    summary="Enrol many students at once, skipping duplicates",
)
def bulk_enroll(
    payload: EnrollmentBulkCreate, actor: CurrentUser, db: DbSession
) -> BulkEnrollResult:
    """Enrol a list of students in one course inside a single transaction.

    Students already enrolled are reported under ``skipped_duplicates``
    instead of aborting the batch.
    """
    course = db.get(Course, payload.course_pk)
    if course is None:
        raise ValidationError(f"Course {payload.course_pk} does not exist")
    if not course.is_active:
        raise ValidationError(f"{course.course_code} is inactive and cannot take enrolments")

    requested = list(dict.fromkeys(payload.student_pks))
    valid = set(
        db.execute(
            select(Student.student_pk).where(
                Student.student_pk.in_(requested), Student.is_active.is_(True)
            )
        ).scalars()
    )
    unknown = [pk for pk in requested if pk not in valid]
    if unknown:
        raise ValidationError(
            f"These student ids do not exist or are inactive: "
            f"{', '.join(str(p) for p in unknown)}"
        )

    already = set(
        db.execute(
            select(Enrollment.student_pk).where(
                Enrollment.course_pk == payload.course_pk,
                Enrollment.student_pk.in_(requested),
            )
        ).scalars()
    )

    created: List[int] = []
    today = date.today()
    for student_pk in requested:
        if student_pk in already:
            continue
        enrollment = Enrollment(
            student_pk=student_pk,
            course_pk=payload.course_pk,
            enrolled_on=today,
            status="ACTIVE",
        )
        db.add(enrollment)
        db.flush()
        created.append(enrollment.enrollment_id)

    audit.record(
        db,
        action="BULK_INSERT",
        entity_type="enrollments",
        entity_id=payload.course_pk,
        user_id=actor.user_id,
        new_values={"created": len(created), "skipped": len(already)},
    )
    db.commit()
    return BulkEnrollResult(
        enrolled=created,
        skipped_duplicates=sorted(already),
        detail=(
            f"Enrolled {len(created)} student(s) in {course.course_code}; "
            f"skipped {len(already)} already-enrolled student(s)"
        ),
    )


@router.patch(
    "/{enrollment_id}",
    response_model=EnrollmentOut,
    dependencies=[Depends(require_permissions(P_ENROLLMENTS_WRITE))],
    summary="Change an enrolment's status",
)
def update_enrollment(
    enrollment_id: int, payload: EnrollmentUpdate, actor: CurrentUser, db: DbSession
) -> EnrollmentOut:
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError(f"Enrolment {enrollment_id} was not found")

    before = enrollment.status
    enrollment.status = payload.status
    audit.record(
        db,
        action="UPDATE",
        entity_type="enrollments",
        entity_id=enrollment_id,
        user_id=actor.user_id,
        old_values={"status": before},
        new_values={"status": payload.status},
    )
    db.commit()
    return _enrollment_out(db, enrollment)
