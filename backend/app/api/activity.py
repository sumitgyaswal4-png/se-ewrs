"""LMS activity logging: logins, resource views, submissions, quiz attempts."""

from datetime import date, datetime, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import ValidationError
from app.core.permissions import P_ACTIVITY_READ, P_ACTIVITY_WRITE
from app.models import ACTIVITY_TYPES, Course, Enrollment, LmsActivityLog, Student
from app.schemas.common import Page
from app.schemas.engagement import ActivityCreate, ActivityOut, ActivitySummaryRow
from app.services import audit
from app.services.queries import activity_sq

router = APIRouter(dependencies=[Depends(require_permissions(P_ACTIVITY_READ))])


@router.get("", response_model=Page[ActivityOut], summary="LMS activity log")
def list_activity(
    db: DbSession,
    page: Pagination,
    course_pk: Annotated[Optional[int], Query()] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
    enrollment_id: Annotated[Optional[int], Query()] = None,
    activity_type: Annotated[Optional[str], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
) -> Page[ActivityOut]:
    stmt = (
        select(
            LmsActivityLog,
            Student.student_id,
            Student.full_name.label("student_name"),
            Course.course_code,
        )
        .join(Enrollment, Enrollment.enrollment_id == LmsActivityLog.enrollment_id)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
    )
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    if student_pk is not None:
        stmt = stmt.where(Enrollment.student_pk == student_pk)
    if enrollment_id is not None:
        stmt = stmt.where(LmsActivityLog.enrollment_id == enrollment_id)
    if activity_type:
        if activity_type not in ACTIVITY_TYPES:
            raise ValidationError(f"activity_type must be one of {', '.join(ACTIVITY_TYPES)}")
        stmt = stmt.where(LmsActivityLog.activity_type == activity_type)
    if date_from is not None:
        stmt = stmt.where(LmsActivityLog.activity_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(
            LmsActivityLog.activity_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(LmsActivityLog.activity_at.desc()).offset(page.offset).limit(page.limit)
    ).mappings()

    items = []
    for row in rows:
        out = ActivityOut.model_validate(row["LmsActivityLog"])
        out.student_id = row["student_id"]
        out.student_name = row["student_name"]
        out.course_code = row["course_code"]
        items.append(out)
    return Page.build(items, total, page.page, page.page_size)


@router.get(
    "/summary",
    response_model=List[ActivitySummaryRow],
    summary="Login frequency and last-activity date per enrolment",
)
def activity_summary(
    db: DbSession,
    course_pk: Annotated[Optional[int], Query()] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
) -> List[ActivitySummaryRow]:
    act = activity_sq()
    today = date.today()
    stmt = (
        select(
            Enrollment.enrollment_id,
            Student.student_pk,
            Student.student_id,
            Student.full_name.label("student_name"),
            Course.course_pk,
            Course.course_code,
            func.coalesce(act.c.total_activities, 0).label("total_activities"),
            func.coalesce(act.c.login_count_30d, 0).label("login_count_30d"),
            func.coalesce(act.c.login_count_total, 0).label("login_count_total"),
            func.coalesce(act.c.quiz_attempts, 0).label("quiz_attempts"),
            func.coalesce(act.c.submission_events, 0).label("submission_events"),
            func.coalesce(act.c.total_minutes, 0).label("total_minutes"),
            act.c.last_activity_at,
        )
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .outerjoin(act, act.c.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.status == "ACTIVE")
    )
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    if student_pk is not None:
        stmt = stmt.where(Enrollment.student_pk == student_pk)

    out: List[ActivitySummaryRow] = []
    for r in db.execute(stmt.order_by(Course.course_code, Student.student_id)).mappings():
        last = r["last_activity_at"]
        out.append(
            ActivitySummaryRow(
                enrollment_id=r["enrollment_id"],
                student_pk=r["student_pk"],
                student_id=r["student_id"],
                student_name=r["student_name"],
                course_pk=r["course_pk"],
                course_code=r["course_code"],
                total_activities=r["total_activities"],
                login_count_30d=r["login_count_30d"],
                login_count_total=r["login_count_total"],
                quiz_attempts=r["quiz_attempts"],
                submission_events=r["submission_events"],
                total_minutes=int(r["total_minutes"] or 0),
                last_activity_at=last,
                days_since_last_activity=(today - last.date()).days if last else None,
            )
        )
    return out


@router.post(
    "",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_ACTIVITY_WRITE))],
    summary="Log an LMS activity event",
)
def create_activity(payload: ActivityCreate, actor: CurrentUser, db: DbSession) -> ActivityOut:
    if db.get(Enrollment, payload.enrollment_id) is None:
        raise ValidationError(f"Enrolment {payload.enrollment_id} does not exist")

    entry = LmsActivityLog(
        enrollment_id=payload.enrollment_id,
        activity_type=payload.activity_type,
        activity_at=payload.activity_at or datetime.now(),
        duration_minutes=payload.duration_minutes,
        resource_ref=payload.resource_ref,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="lms_activity_logs",
        entity_id=entry.activity_id,
        user_id=actor.user_id,
        new_values={
            "enrollment_id": entry.enrollment_id,
            "activity_type": entry.activity_type,
            "activity_at": entry.activity_at,
        },
    )
    db.commit()

    row = db.execute(
        select(Student.student_id, Student.full_name, Course.course_code)
        .select_from(Enrollment)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .where(Enrollment.enrollment_id == entry.enrollment_id)
    ).one()
    out = ActivityOut.model_validate(entry)
    out.student_id, out.student_name, out.course_code = row
    return out
