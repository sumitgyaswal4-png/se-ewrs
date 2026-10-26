"""Intervention tracking: counselling, tutoring and follow-up records."""

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession, Pagination, require_permissions
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import P_INTERVENTIONS_READ, P_INTERVENTIONS_WRITE
from app.models import (
    Course,
    Enrollment,
    Intervention,
    RiskAlert,
    Student,
    User,
)
from app.schemas.common import Page
from app.schemas.risk import InterventionCreate, InterventionOut, InterventionUpdate
from app.services import audit
from app.services.queries import latest_risk_sq

router = APIRouter(dependencies=[Depends(require_permissions(P_INTERVENTIONS_READ))])

#: Roles that can be recorded as the owning advisor of an intervention.
ADVISOR_ROLES = ("ADVISOR", "INSTRUCTOR", "TA", "ADMIN")


def _as_float(value) -> Optional[float]:
    return None if value is None else float(value)


def _base_select():
    lr = latest_risk_sq()
    return (
        select(
            Intervention,
            User.full_name.label("advisor_name"),
            Student.student_pk,
            Student.student_id,
            Student.full_name.label("student_name"),
            Course.course_pk,
            Course.course_code,
            Course.course_name,
            lr.c.risk_score.label("current_risk_score"),
            lr.c.risk_category.label("current_risk_category"),
        )
        .join(Enrollment, Enrollment.enrollment_id == Intervention.enrollment_id)
        .join(Student, Student.student_pk == Enrollment.student_pk)
        .join(Course, Course.course_pk == Enrollment.course_pk)
        .outerjoin(User, User.user_id == Intervention.assigned_advisor_id)
        .outerjoin(lr, lr.c.enrollment_id == Intervention.enrollment_id)
    )


def _out(row) -> InterventionOut:
    out = InterventionOut.model_validate(row["Intervention"])
    out.advisor_name = row["advisor_name"]
    out.student_pk = row["student_pk"]
    out.student_id = row["student_id"]
    out.student_name = row["student_name"]
    out.course_pk = row["course_pk"]
    out.course_code = row["course_code"]
    out.course_name = row["course_name"]
    out.current_risk_score = _as_float(row["current_risk_score"])
    out.current_risk_category = row["current_risk_category"]
    return out


@router.get("", response_model=Page[InterventionOut], summary="Intervention history")
def list_interventions(
    db: DbSession,
    page: Pagination,
    search: Annotated[Optional[str], Query(max_length=120)] = None,
    student_pk: Annotated[Optional[int], Query()] = None,
    course_pk: Annotated[Optional[int], Query()] = None,
    enrollment_id: Annotated[Optional[int], Query()] = None,
    alert_id: Annotated[Optional[int], Query()] = None,
    intervention_type: Annotated[Optional[str], Query()] = None,
    outcome: Annotated[Optional[str], Query()] = None,
    resolution_status: Annotated[Optional[str], Query()] = None,
    advisor_id: Annotated[Optional[int], Query()] = None,
    date_from: Annotated[Optional[date], Query()] = None,
    date_to: Annotated[Optional[date], Query()] = None,
    follow_up_due: Annotated[
        Optional[bool], Query(description="Only records whose follow-up date has passed")
    ] = None,
) -> Page[InterventionOut]:
    stmt = _base_select()
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Student.student_id.ilike(pattern),
                Student.full_name.ilike(pattern),
                Course.course_code.ilike(pattern),
            )
        )
    if student_pk is not None:
        stmt = stmt.where(Enrollment.student_pk == student_pk)
    if course_pk is not None:
        stmt = stmt.where(Enrollment.course_pk == course_pk)
    if enrollment_id is not None:
        stmt = stmt.where(Intervention.enrollment_id == enrollment_id)
    if alert_id is not None:
        stmt = stmt.where(Intervention.alert_id == alert_id)
    if intervention_type:
        stmt = stmt.where(Intervention.intervention_type == intervention_type)
    if outcome:
        stmt = stmt.where(Intervention.outcome == outcome)
    if resolution_status:
        stmt = stmt.where(Intervention.resolution_status == resolution_status)
    if advisor_id is not None:
        stmt = stmt.where(Intervention.assigned_advisor_id == advisor_id)
    if date_from is not None:
        stmt = stmt.where(Intervention.contact_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Intervention.contact_date <= date_to)
    if follow_up_due is True:
        stmt = stmt.where(
            Intervention.follow_up_date.is_not(None),
            Intervention.follow_up_date <= date.today(),
            Intervention.resolution_status != "CLOSED",
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Intervention.contact_date.desc(), Intervention.intervention_id.desc())
        .offset(page.offset)
        .limit(page.limit)
    ).mappings()
    return Page.build([_out(r) for r in rows], total, page.page, page.page_size)


@router.post(
    "",
    response_model=InterventionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(P_INTERVENTIONS_WRITE))],
    summary="Record an intervention",
)
def create_intervention(
    payload: InterventionCreate, actor: CurrentUser, db: DbSession
) -> InterventionOut:
    """Links the record to its enrolment and, optionally, to a risk alert.

    An ``alert_id`` must belong to the *same* enrolment -- a plain foreign
    key cannot express that, so it is checked here and again by the
    ``trg_intervention_before_insert`` trigger on MySQL.
    """
    enrollment = db.get(Enrollment, payload.enrollment_id)
    if enrollment is None:
        raise ValidationError(f"Enrolment {payload.enrollment_id} does not exist")

    if payload.alert_id is not None:
        alert = db.get(RiskAlert, payload.alert_id)
        if alert is None:
            raise ValidationError(f"Alert {payload.alert_id} does not exist")
        if alert.enrollment_id != payload.enrollment_id:
            raise ValidationError(
                "That alert belongs to a different enrolment than the one supplied"
            )

    advisor_id = payload.assigned_advisor_id
    if advisor_id is not None:
        advisor = db.get(User, advisor_id)
        if advisor is None:
            raise ValidationError(f"User {advisor_id} does not exist")
        if advisor.role not in ADVISOR_ROLES:
            raise ValidationError(
                f"{advisor.full_name} has role {advisor.role} and cannot own an intervention"
            )
    else:
        # Default to whoever is recording it, which is almost always right.
        advisor_id = actor.user_id

    intervention = Intervention(
        enrollment_id=payload.enrollment_id,
        alert_id=payload.alert_id,
        intervention_type=payload.intervention_type,
        assigned_advisor_id=advisor_id,
        contact_date=payload.contact_date,
        notes=payload.notes,
        action_plan=payload.action_plan,
        follow_up_date=payload.follow_up_date,
        outcome=payload.outcome,
        resolution_status=payload.resolution_status,
        created_by=actor.user_id,
    )
    db.add(intervention)
    db.flush()
    audit.record(
        db,
        action="INSERT",
        entity_type="interventions",
        entity_id=intervention.intervention_id,
        user_id=actor.user_id,
        new_values={
            "enrollment_id": intervention.enrollment_id,
            "intervention_type": intervention.intervention_type,
            "alert_id": intervention.alert_id,
        },
    )
    db.commit()
    return _fetch_one(db, intervention.intervention_id)


@router.get("/{intervention_id}", response_model=InterventionOut, summary="Fetch one record")
def get_intervention(intervention_id: int, db: DbSession) -> InterventionOut:
    return _fetch_one(db, intervention_id)


@router.put(
    "/{intervention_id}",
    response_model=InterventionOut,
    dependencies=[Depends(require_permissions(P_INTERVENTIONS_WRITE))],
    summary="Update an intervention's outcome or plan",
)
def update_intervention(
    intervention_id: int, payload: InterventionUpdate, actor: CurrentUser, db: DbSession
) -> InterventionOut:
    intervention = db.get(Intervention, intervention_id)
    if intervention is None:
        raise NotFoundError(f"Intervention {intervention_id} was not found")

    data = payload.model_dump(exclude_unset=True)
    before = {
        "outcome": intervention.outcome,
        "resolution_status": intervention.resolution_status,
    }

    if data.get("assigned_advisor_id") is not None:
        advisor = db.get(User, data["assigned_advisor_id"])
        if advisor is None:
            raise ValidationError(f"User {data['assigned_advisor_id']} does not exist")
        if advisor.role not in ADVISOR_ROLES:
            raise ValidationError(
                f"{advisor.full_name} has role {advisor.role} and cannot own an intervention"
            )

    contact = data.get("contact_date", intervention.contact_date)
    follow_up = data.get("follow_up_date", intervention.follow_up_date)
    if follow_up is not None and contact is not None and follow_up < contact:
        raise ValidationError("follow_up_date cannot be before contact_date")

    for key, value in data.items():
        setattr(intervention, key, value)

    audit.record(
        db,
        action="UPDATE",
        entity_type="interventions",
        entity_id=intervention_id,
        user_id=actor.user_id,
        old_values=before,
        new_values=data,
    )
    db.commit()
    return _fetch_one(db, intervention_id)


def _fetch_one(db: DbSession, intervention_id: int) -> InterventionOut:
    row = db.execute(
        _base_select().where(Intervention.intervention_id == intervention_id)
    ).mappings().one_or_none()
    if row is None:
        raise NotFoundError(f"Intervention {intervention_id} was not found")
    return _out(row)
