"""Attendance recording and review."""

from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import P_ATTENDANCE_READ, P_ATTENDANCE_WRITE
from app.models import AttendanceRecord, Course, Enrollment, Student, User
from app.schemas.common import Message, Page
from app.schemas.engagement import (
    AttendanceBulkCreate,
    AttendanceCreate,
    AttendanceOut,
    AttendanceSummaryRow,
)
from app.services import audit
from app.services.queries import attendance_sq

router = APIRouter(dependencies=[Depends(require_permissions(P_ATTENDANCE_READ))])


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)


@router.get("", response_model=Page[AttendanceOut], summary="Historical attendance records")
def list_attendance(
    db: DbSession,
    page: Pagination,
    course_pk: Annotated[Optional[int], Query()] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
    enrollment_id: Annotated[Optional[int], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
    attendance_status: Annotated[Optional[str], Query()] = None,
) -> Page[AttendanceOut]:
    recorder = User.__table__.alias("recorder")
    stmt = (
        select(
            AttendanceRecord,
            Student.student_id,
            Student.full_name.label("student_name"),
            Course.course_code,
            recorder.c.full_name.label("recorded_by_name"),
        )
        .join(Enrollment, Enrollment.enrollment_id == AttendanceRecord.enrollment_id)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .outerjoin(recorder, recorder.c.user_id == AttendanceRecord.recorded_by)
    )
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    if student_pk is not None:
        stmt = stmt.where(Enrollment.student_pk == student_pk)
    if enrollment_id is not None:
        stmt = stmt.where(AttendanceRecord.enrollment_id == enrollment_id)
    if date_from is not None:
        stmt = stmt.where(AttendanceRecord.session_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(AttendanceRecord.session_date <= date_to)
    if attendance_status:
        stmt = stmt.where(AttendanceRecord.status == attendance_status)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(
            AttendanceRecord.session_date.desc(), AttendanceRecord.session_no.desc()
        )
        .offset(page.offset)
        .limit(page.limit)
    ).mappings()

    items = []
    for row in rows:
        out = AttendanceOut.model_validate(row["AttendanceRecord"])
        out.student_id = row["student_id"]
        out.student_name = row["student_name"]
        out.course_code = row["course_code"]
        out.recorded_by_name = row["recorded_by_name"]
        items.append(out)
    return Page.build(items, total, page.page, page.page_size)


@router.get(
    "/summary",
    response_model=List[AttendanceSummaryRow],
    summary="Classes held and attended, per enrolled student",
)
def attendance_summary(
    db: DbSession,
    course_pk: Annotated[Optional[int], Query()] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
) -> List[AttendanceSummaryRow]:
    att = attendance_sq()
    stmt = (
        select(
            Enrollment.enrollment_id,
            Student.student_pk,
            Student.student_id,
            Student.full_name.label("student_name"),
            Course.course_pk,
            Course.course_code,
            func.coalesce(att.c.sessions_held, 0).label("sessions_held"),
            func.coalesce(att.c.sessions_attended, 0).label("sessions_attended"),
            func.coalesce(att.c.sessions_absent, 0).label("sessions_absent"),
            func.coalesce(att.c.sessions_late, 0).label("sessions_late"),
            func.coalesce(att.c.sessions_excused, 0).label("sessions_excused"),
            att.c.attendance_percentage,
            att.c.last_session_date,
        )
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .outerjoin(att, att.c.enrollment_id == Enrollment.enrollment_id)
        .where(Enrollment.status == "ACTIVE")
    )
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    if student_pk is not None:
        stmt = stmt.where(Enrollment.student_pk == student_pk)

    return [
        AttendanceSummaryRow(
            enrollment_id=r["enrollment_id"],
            student_pk=r["student_pk"],
            student_id=r["student_id"],
            student_name=r["student_name"],
            course_pk=r["course_pk"],
            course_code=r["course_code"],
            sessions_held=r["sessions_held"],
            sessions_attended=r["sessions_attended"],
            sessions_absent=r["sessions_absent"],
            sessions_late=r["sessions_late"],
            sessions_excused=r["sessions_excused"],
            attendance_percentage=_as_float(r["attendance_percentage"]),
            last_session_date=r["last_session_date"],
        )
        for r in db.execute(stmt.order_by(Course.course_code, Student.student_id)).mappings()
    ]


@router.post(
    "",
    response_model=AttendanceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_ATTENDANCE_WRITE))],
    summary="Record (or correct) one attendance entry",
)
def record_attendance(
    payload: AttendanceCreate, actor: CurrentUser, db: DbSession
) -> AttendanceOut:
    """Idempotent on ``(enrollment, session_date, session_no)``.

    Re-submitting the same session corrects the existing row rather than
    violating ``uq_attendance_session`` -- the same behaviour as the
    ``sp_record_attendance`` stored procedure.
    """
    if db.get(Enrollment, payload.enrollment_id) is None:
        raise ValidationError(f"Enrolment {payload.enrollment_id} does not exist")

    existing = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.enrollment_id == payload.enrollment_id,
            AttendanceRecord.session_date == payload.session_date,
            AttendanceRecord.session_no == payload.session_no,
        )
    ).scalar_one_or_none()

    if existing is not None:
        before = existing.status
        existing.status = payload.status
        existing.remarks = payload.remarks
        existing.recorded_by = actor.user_id
        audit.record(
            db,
            action="UPDATE",
            entity_type="attendance_records",
            entity_id=existing.attendance_id,
            user_id=actor.user_id,
            old_values={"status": before},
            new_values={"status": payload.status},
        )
        db.commit()
        return _attendance_out(db, existing)

    record = AttendanceRecord(
        enrollment_id=payload.enrollment_id,
        session_date=payload.session_date,
        session_no=payload.session_no,
        status=payload.status,
        remarks=payload.remarks,
        recorded_by=actor.user_id,
    )
    db.add(record)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="attendance_records",
        entity_id=record.attendance_id,
        user_id=actor.user_id,
        new_values={
            "enrollment_id": record.enrollment_id,
            "session_date": record.session_date,
            "status": record.status,
        },
    )
    db.commit()
    return _attendance_out(db, record)


@router.post(
    "/bulk",
    response_model=Message,
    dependencies=[Depends(require_permissions(P_ATTENDANCE_WRITE))],
    summary="Mark a whole class roster for one session",
)
def bulk_attendance(
    payload: AttendanceBulkCreate, actor: CurrentUser, db: DbSession
) -> Message:
    """Record attendance for an entire session in one transaction.

    Every row is validated against the course's own roster first, so an
    enrolment from a different course cannot be slipped into the batch.
    """
    if db.get(Course, payload.course_pk) is None:
        raise ValidationError(f"Course {payload.course_pk} does not exist")

    roster = set(
        db.execute(
            select(Enrollment.enrollment_id).where(
                Enrollment.course_pk == payload.course_pk, Enrollment.status == "ACTIVE"
            )
        ).scalars()
    )
    foreign = [r.enrollment_id for r in payload.rows if r.enrollment_id not in roster]
    if foreign:
        raise ValidationError(
            "These enrolment ids are not on this course's active roster: "
            f"{', '.join(str(i) for i in foreign)}"
        )

    existing = {
        rec.enrollment_id: rec
        for rec in db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.enrollment_id.in_([r.enrollment_id for r in payload.rows]),
                AttendanceRecord.session_date == payload.session_date,
                AttendanceRecord.session_no == payload.session_no,
            )
        ).scalars()
    }

    inserted = updated = 0
    for row in payload.rows:
        record = existing.get(row.enrollment_id)
        if record is not None:
            if record.status != row.status:
                record.status = row.status
                record.recorded_by = actor.user_id
                updated += 1
        else:
            db.add(
                AttendanceRecord(
                    enrollment_id=row.enrollment_id,
                    session_date=payload.session_date,
                    session_no=payload.session_no,
                    status=row.status,
                    recorded_by=actor.user_id,
                )
            )
            inserted += 1

    audit.record(
        db,
        action="BULK_UPSERT",
        entity_type="attendance_records",
        entity_id=f"course:{payload.course_pk}:{payload.session_date}",
        user_id=actor.user_id,
        new_values={"inserted": inserted, "updated": updated},
    )
    db.commit()
    return Message(
        detail=(
            f"Session {payload.session_date} (#{payload.session_no}): "
            f"{inserted} record(s) added, {updated} corrected"
        )
    )


@router.delete(
    "/{attendance_id}",
    response_model=Message,
    dependencies=[Depends(require_permissions(P_ATTENDANCE_WRITE))],
    summary="Delete an attendance record",
)
def delete_attendance(attendance_id: int, actor: CurrentUser, db: DbSession) -> Message:
    record = db.get(AttendanceRecord, attendance_id)
    if record is None:
        raise NotFoundError(f"Attendance record {attendance_id} was not found")
    snapshot = {
        "enrollment_id": record.enrollment_id,
        "session_date": record.session_date,
        "status": record.status,
    }
    db.delete(record)
    audit.record(
        db,
        action="DELETE",
        entity_type="attendance_records",
        entity_id=attendance_id,
        user_id=actor.user_id,
        old_values=snapshot,
    )
    db.commit()
    return Message(detail="Attendance record deleted")


def _attendance_out(db: DbSession, record: AttendanceRecord) -> AttendanceOut:
    row = db.execute(
        select(Student.student_id, Student.full_name, Course.course_code)
        .select_from(Enrollment)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .where(Enrollment.enrollment_id == record.enrollment_id)
    ).one()
    out = AttendanceOut.model_validate(record)
    out.student_id, out.student_name, out.course_code = row
    if record.recorded_by:
        user = db.get(User, record.recorded_by)
        out.recorded_by_name = user.full_name if user else None
    return out
