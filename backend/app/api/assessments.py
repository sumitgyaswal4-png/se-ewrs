"""Assessment definitions and marks entry."""

from datetime import date, datetime, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import case, func, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import (
    P_ASSESSMENTS_READ,
    P_ASSESSMENTS_WRITE,
    P_RESULTS_WRITE,
)
from app.models import (
    Assessment,
    AssessmentResult,
    Course,
    Enrollment,
    Student,
)
from app.schemas.common import Message, Page
from app.schemas.engagement import (
    AssessmentCreate,
    AssessmentOut,
    AssessmentUpdate,
    PerformanceTrendPoint,
    ResultBulkUpsert,
    ResultOut,
    ResultUpsert,
)
from app.services import audit
from app.services.assessment_service import (
    compute_percentage,
    derive_submission_status,
    validate_marks,
)

router = APIRouter(dependencies=[Depends(require_permissions(P_ASSESSMENTS_READ))])
results_router = APIRouter(dependencies=[Depends(require_permissions(P_ASSESSMENTS_READ))])


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)


def _result_stats_sq():
    """Graded count and mean percentage per assessment."""
    return (
        select(
            AssessmentResult.assessment_id.label("assessment_id"),
            func.count(AssessmentResult.result_id).label("expected_count"),
            func.sum(
                case((AssessmentResult.marks_obtained.is_not(None), 1), else_=0)
            ).label("graded_count"),
            func.round(func.avg(AssessmentResult.percentage), 2).label("avg_percentage"),
        )
        .group_by(AssessmentResult.assessment_id)
        .subquery("rstats")
    )


@router.get("", response_model=Page[AssessmentOut], summary="List assessments")
def list_assessments(
    db: DbSession,
    page: Pagination,
    course_pk: Annotated[Optional[int], Query()] = None,
    assessment_type: Annotated[Optional[str], Query()] = None,
    due_from: Annotated[Optional[date], Query()] = None,
    due_to: Annotated[Optional[date], Query()] = None,
) -> Page[AssessmentOut]:
    stats = _result_stats_sq()
    stmt = (
        select(Assessment, Course.course_code, Course.course_name, stats)
        .join(Course, Course.course_pk == Assessment.course_pk)
        .outerjoin(stats, stats.c.assessment_id == Assessment.assessment_id)
    )
    if course_pk is not None:
        stmt = stmt.where(Assessment.course_pk == course_pk)
    if assessment_type:
        stmt = stmt.where(Assessment.assessment_type == assessment_type)
    if due_from is not None:
        stmt = stmt.where(Assessment.due_at >= datetime.combine(due_from, datetime.min.time()))
    if due_to is not None:
        stmt = stmt.where(
            Assessment.due_at < datetime.combine(due_to + timedelta(days=1), datetime.min.time())
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Assessment.due_at.desc()).offset(page.offset).limit(page.limit)
    ).mappings()
    return Page.build(
        [_assessment_out(r) for r in rows], total, page.page, page.page_size
    )


@router.get(
    "/trends",
    response_model=List[PerformanceTrendPoint],
    summary="Average score per month -- the performance trend chart",
)
def assessment_trends(
    db: DbSession,
    course_pk: Annotated[Optional[int], Query()] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
) -> List[PerformanceTrendPoint]:
    """Monthly mean of graded percentages, computed with GROUP BY in SQL."""
    period = func.strftime("%Y-%m", Assessment.due_at)
    if db.bind is not None and db.bind.dialect.name == "mysql":
        period = func.date_format(Assessment.due_at, "%Y-%m")

    stmt = (
        select(
            period.label("period"),
            func.count(AssessmentResult.result_id).label("graded_results"),
            func.round(func.avg(AssessmentResult.percentage), 2).label("avg_percentage"),
        )
        .select_from(Assessment)
        .join(AssessmentResult, AssessmentResult.assessment_id == Assessment.assessment_id)
        .where(AssessmentResult.marks_obtained.is_not(None))
    )
    if course_pk is not None:
        stmt = stmt.where(Assessment.course_pk == course_pk)
    if student_pk is not None:
        stmt = stmt.join(
            Enrollment, Enrollment.enrollment_id == AssessmentResult.enrollment_id
        ).where(Enrollment.student_pk == student_pk)

    rows = db.execute(stmt.group_by(period).order_by(period)).mappings()
    return [
        PerformanceTrendPoint(
            period=r["period"],
            label=r["period"],
            graded_results=r["graded_results"],
            avg_percentage=_as_float(r["avg_percentage"]),
        )
        for r in rows
    ]


@router.post(
    "",
    response_model=AssessmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_ASSESSMENTS_WRITE))],
    summary="Create an assignment, quiz or examination",
)
def create_assessment(
    payload: AssessmentCreate, actor: CurrentUser, db: DbSession
) -> AssessmentOut:
    course = db.get(Course, payload.course_pk)
    if course is None:
        raise ValidationError(f"Course {payload.course_pk} does not exist")

    clash = db.execute(
        select(Assessment.assessment_id).where(
            Assessment.course_pk == payload.course_pk, Assessment.title == payload.title
        )
    ).scalar_one_or_none()
    if clash:
        raise ConflictError(
            f"{course.course_code} already has an assessment titled '{payload.title}'"
        )

    assessment = Assessment(
        course_pk=payload.course_pk,
        title=payload.title.strip(),
        assessment_type=payload.assessment_type,
        max_marks=payload.max_marks,
        weight_percent=payload.weight_percent,
        due_at=payload.due_at,
        created_by=actor.user_id,
    )
    db.add(assessment)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="assessments",
        entity_id=assessment.assessment_id,
        user_id=actor.user_id,
        new_values={
            "course_pk": assessment.course_pk,
            "title": assessment.title,
            "max_marks": str(assessment.max_marks),
        },
    )
    db.commit()
    return get_assessment(assessment.assessment_id, db)


@router.get("/{assessment_id}", response_model=AssessmentOut, summary="Fetch one assessment")
def get_assessment(assessment_id: int, db: DbSession) -> AssessmentOut:
    stats = _result_stats_sq()
    row = db.execute(
        select(Assessment, Course.course_code, Course.course_name, stats)
        .join(Course, Course.course_pk == Assessment.course_pk)
        .outerjoin(stats, stats.c.assessment_id == Assessment.assessment_id)
        .where(Assessment.assessment_id == assessment_id)
    ).mappings().one_or_none()
    if row is None:
        raise NotFoundError(f"Assessment {assessment_id} was not found")
    return _assessment_out(row)


@router.put(
    "/{assessment_id}",
    response_model=AssessmentOut,
    dependencies=[Depends(require_permissions(P_ASSESSMENTS_WRITE))],
    summary="Update an assessment",
)
def update_assessment(
    assessment_id: int, payload: AssessmentUpdate, actor: CurrentUser, db: DbSession
) -> AssessmentOut:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFoundError(f"Assessment {assessment_id} was not found")

    data = payload.model_dump(exclude_unset=True)
    before = {
        "title": assessment.title,
        "max_marks": str(assessment.max_marks),
        "due_at": str(assessment.due_at),
    }

    if data.get("title") and data["title"] != assessment.title:
        clash = db.execute(
            select(Assessment.assessment_id).where(
                Assessment.course_pk == assessment.course_pk,
                Assessment.title == data["title"],
                Assessment.assessment_id != assessment_id,
            )
        ).scalar_one_or_none()
        if clash:
            raise ConflictError(f"Another assessment in this course is titled '{data['title']}'")

    new_max = data.get("max_marks")
    if new_max is not None:
        # Lowering the maximum below an already-recorded mark would make a
        # stored percentage impossible, so block it explicitly.
        highest = db.execute(
            select(func.max(AssessmentResult.marks_obtained)).where(
                AssessmentResult.assessment_id == assessment_id
            )
        ).scalar_one_or_none()
        if highest is not None and float(highest) > float(new_max):
            raise ValidationError(
                f"Cannot lower max_marks to {new_max}: a recorded mark of "
                f"{highest} already exceeds it"
            )

    for key, value in data.items():
        setattr(assessment, key, value)
    db.flush()

    # Re-derive every dependent value so the stored data stays consistent
    # with the new maximum / deadline.
    if new_max is not None or data.get("due_at") is not None:
        for result in db.execute(
            select(AssessmentResult).where(AssessmentResult.assessment_id == assessment_id)
        ).scalars():
            result.percentage = compute_percentage(result.marks_obtained, assessment.max_marks)
            result.submission_status = derive_submission_status(
                result.submitted_at, assessment.due_at
            )

    audit.record(
        db,
        action="UPDATE",
        entity_type="assessments",
        entity_id=assessment_id,
        user_id=actor.user_id,
        old_values=before,
        new_values=data,
    )
    db.commit()
    return get_assessment(assessment_id, db)


@router.get(
    "/{assessment_id}/results",
    response_model=List[ResultOut],
    summary="Marks grid for one assessment (every enrolled student)",
)
def assessment_results(assessment_id: int, db: DbSession) -> List[ResultOut]:
    """Returns one row per active enrolment, graded or not.

    Students with nothing recorded yet appear with ``result_id = 0`` and
    null marks, so the grade-entry screen can show the whole roster.
    """
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFoundError(f"Assessment {assessment_id} was not found")
    course = db.get(Course, assessment.course_pk)

    existing = {
        r.enrollment_id: r
        for r in db.execute(
            select(AssessmentResult).where(AssessmentResult.assessment_id == assessment_id)
        ).scalars()
    }

    roster = db.execute(
        select(Enrollment.enrollment_id, Student.student_id, Student.full_name)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .where(
            Enrollment.course_pk == assessment.course_pk, Enrollment.status == "ACTIVE"
        )
        .order_by(Student.student_id)
    ).all()

    out: List[ResultOut] = []
    for enrollment_id, student_id, student_name in roster:
        result = existing.get(enrollment_id)
        if result is not None:
            row = ResultOut.model_validate(result)
            row.marks_obtained = _as_float(result.marks_obtained)
            row.percentage = _as_float(result.percentage)
        else:
            row = ResultOut(
                result_id=0,
                assessment_id=assessment_id,
                enrollment_id=enrollment_id,
                submission_status="MISSING",
                attempt_no=1,
            )
        row.max_marks = float(assessment.max_marks)
        row.assessment_title = assessment.title
        row.assessment_type = assessment.assessment_type
        row.due_at = assessment.due_at
        row.course_code = course.course_code if course else None
        row.student_id = student_id
        row.student_name = student_name
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# /api/assessment-results
# ---------------------------------------------------------------------------
@results_router.get("", response_model=Page[ResultOut], summary="Assessment results history")
def list_results(
    db: DbSession,
    page: Pagination,
    course_pk: Annotated[Optional[int], Query()] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
    assessment_id: Annotated[Optional[int], Query()] = None,
    submission_status: Annotated[Optional[str], Query()] = None,
) -> Page[ResultOut]:
    stmt = (
        select(
            AssessmentResult,
            Assessment.title.label("assessment_title"),
            Assessment.assessment_type,
            Assessment.max_marks,
            Assessment.due_at,
            Course.course_code,
            Student.student_id,
            Student.full_name.label("student_name"),
        )
        .join(Assessment, Assessment.assessment_id == AssessmentResult.assessment_id)
        .join(Course, Course.course_pk == Assessment.course_pk)
        .join(Enrollment, Enrollment.enrollment_id == AssessmentResult.enrollment_id)
        .join(Student, Student.student_pk == Enrollment.student_pk)
    )
    if course_pk is not None:
        stmt = stmt.where(Assessment.course_pk == course_pk)
    if student_pk is not None:
        stmt = stmt.where(Enrollment.student_pk == student_pk)
    if assessment_id is not None:
        stmt = stmt.where(AssessmentResult.assessment_id == assessment_id)
    if submission_status:
        stmt = stmt.where(AssessmentResult.submission_status == submission_status)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Assessment.due_at.desc(), Student.student_id)
        .offset(page.offset)
        .limit(page.limit)
    ).mappings()

    items = []
    for r in rows:
        row = ResultOut.model_validate(r["AssessmentResult"])
        row.marks_obtained = _as_float(r["AssessmentResult"].marks_obtained)
        row.percentage = _as_float(r["AssessmentResult"].percentage)
        row.max_marks = _as_float(r["max_marks"])
        row.assessment_title = r["assessment_title"]
        row.assessment_type = r["assessment_type"]
        row.due_at = r["due_at"]
        row.course_code = r["course_code"]
        row.student_id = r["student_id"]
        row.student_name = r["student_name"]
        items.append(row)
    return Page.build(items, total, page.page, page.page_size)


@results_router.post(
    "",
    response_model=ResultOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_RESULTS_WRITE))],
    summary="Enter or correct one student's marks",
)
def upsert_result(payload: ResultUpsert, actor: CurrentUser, db: DbSession) -> ResultOut:
    """Percentage is derived server-side; marks are range-checked.

    The row is keyed on ``(assessment_id, enrollment_id)``, so submitting
    the same pair again corrects the existing grade instead of creating a
    second one.
    """
    assessment = db.get(Assessment, payload.assessment_id)
    if assessment is None:
        raise ValidationError(f"Assessment {payload.assessment_id} does not exist")
    enrollment = db.get(Enrollment, payload.enrollment_id)
    if enrollment is None:
        raise ValidationError(f"Enrolment {payload.enrollment_id} does not exist")
    if enrollment.course_pk != assessment.course_pk:
        raise ValidationError(
            "That enrolment belongs to a different course than the assessment"
        )

    marks = validate_marks(payload.marks_obtained, assessment.max_marks)
    percentage = compute_percentage(marks, assessment.max_marks)
    submission_status = derive_submission_status(payload.submitted_at, assessment.due_at)

    result = db.execute(
        select(AssessmentResult).where(
            AssessmentResult.assessment_id == payload.assessment_id,
            AssessmentResult.enrollment_id == payload.enrollment_id,
        )
    ).scalar_one_or_none()

    action = "UPDATE" if result else "INSERT"
    before = (
        {"marks_obtained": _as_float(result.marks_obtained), "percentage": _as_float(result.percentage)}
        if result
        else None
    )

    if result is None:
        result = AssessmentResult(
            assessment_id=payload.assessment_id, enrollment_id=payload.enrollment_id
        )
        db.add(result)

    result.marks_obtained = marks
    result.percentage = percentage
    result.submitted_at = payload.submitted_at
    result.submission_status = submission_status
    result.attempt_no = payload.attempt_no
    result.graded_by = actor.user_id if marks is not None else None
    result.graded_at = datetime.now() if marks is not None else None
    db.flush()

    audit.record(
        db,
        action=action,
        entity_type="assessment_results",
        entity_id=result.result_id,
        user_id=actor.user_id,
        old_values=before,
        new_values={"marks_obtained": _as_float(marks), "percentage": _as_float(percentage)},
    )
    db.commit()
    return _single_result_out(db, result)


@results_router.post(
    "/bulk",
    response_model=Message,
    dependencies=[Depends(require_permissions(P_RESULTS_WRITE))],
    summary="Enter marks for a whole class in one request",
)
def bulk_upsert_results(
    payload: ResultBulkUpsert, actor: CurrentUser, db: DbSession
) -> Message:
    """One transaction for the whole grade sheet.

    Every row is validated before anything is written, so an out-of-range
    mark rejects the batch rather than leaving half a grade sheet saved.
    """
    assessment = db.get(Assessment, payload.assessment_id)
    if assessment is None:
        raise ValidationError(f"Assessment {payload.assessment_id} does not exist")

    roster = set(
        db.execute(
            select(Enrollment.enrollment_id).where(
                Enrollment.course_pk == assessment.course_pk, Enrollment.status == "ACTIVE"
            )
        ).scalars()
    )
    foreign = [r.enrollment_id for r in payload.rows if r.enrollment_id not in roster]
    if foreign:
        raise ValidationError(
            "These enrolment ids are not on this course's active roster: "
            f"{', '.join(str(i) for i in foreign)}"
        )

    # Validate every mark up-front -- all or nothing.
    prepared = []
    for row in payload.rows:
        marks = validate_marks(row.marks_obtained, assessment.max_marks)
        prepared.append(
            (
                row.enrollment_id,
                marks,
                compute_percentage(marks, assessment.max_marks),
                row.submitted_at,
                derive_submission_status(row.submitted_at, assessment.due_at),
            )
        )

    existing = {
        r.enrollment_id: r
        for r in db.execute(
            select(AssessmentResult).where(
                AssessmentResult.assessment_id == payload.assessment_id
            )
        ).scalars()
    }

    inserted = updated = 0
    now = datetime.now()
    for enrollment_id, marks, percentage, submitted_at, submission_status in prepared:
        result = existing.get(enrollment_id)
        if result is None:
            result = AssessmentResult(
                assessment_id=payload.assessment_id, enrollment_id=enrollment_id
            )
            db.add(result)
            inserted += 1
        else:
            updated += 1
        result.marks_obtained = marks
        result.percentage = percentage
        result.submitted_at = submitted_at
        result.submission_status = submission_status
        result.graded_by = actor.user_id if marks is not None else None
        result.graded_at = now if marks is not None else None

    audit.record(
        db,
        action="BULK_UPSERT",
        entity_type="assessment_results",
        entity_id=payload.assessment_id,
        user_id=actor.user_id,
        new_values={"inserted": inserted, "updated": updated},
    )
    db.commit()
    return Message(detail=f"{inserted} result(s) added, {updated} updated")


def _assessment_out(row) -> AssessmentOut:
    assessment: Assessment = row["Assessment"]
    out = AssessmentOut.model_validate(assessment)
    out.max_marks = float(assessment.max_marks)
    out.weight_percent = float(assessment.weight_percent)
    out.course_code = row["course_code"]
    out.course_name = row["course_name"]
    out.graded_count = row["graded_count"] or 0
    out.expected_count = row["expected_count"] or 0
    out.avg_percentage = _as_float(row["avg_percentage"])
    return out


def _single_result_out(db: DbSession, result: AssessmentResult) -> ResultOut:
    row = db.execute(
        select(
            Assessment.title,
            Assessment.assessment_type,
            Assessment.max_marks,
            Assessment.due_at,
            Course.course_code,
            Student.student_id,
            Student.full_name,
        )
        .select_from(AssessmentResult)
        .join(Assessment, Assessment.assessment_id == AssessmentResult.assessment_id)
        .join(Course, Course.course_pk == Assessment.course_pk)
        .join(Enrollment, Enrollment.enrollment_id == AssessmentResult.enrollment_id)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .where(AssessmentResult.result_id == result.result_id)
    ).one()
    out = ResultOut.model_validate(result)
    out.marks_obtained = _as_float(result.marks_obtained)
    out.percentage = _as_float(result.percentage)
    (
        out.assessment_title,
        out.assessment_type,
        max_marks,
        out.due_at,
        out.course_code,
        out.student_id,
        out.student_name,
    ) = row
    out.max_marks = float(max_marks)
    return out
