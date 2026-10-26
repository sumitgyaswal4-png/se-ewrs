"""Alert generation, duplicate prevention and status transitions."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AttendanceRecord, LmsActivityLog, RiskAlert


def make_at_risk(db, enrollment_id=1, attendance_ratio=0.3):
    """Give an enrolment enough bad data to cross the alert threshold."""
    sessions = 10
    attended = int(sessions * attendance_ratio)
    for index in range(sessions):
        db.add(
            AttendanceRecord(
                enrollment_id=enrollment_id,
                session_date=date.today() - timedelta(days=index + 1),
                session_no=1,
                status="PRESENT" if index < attended else "ABSENT",
            )
        )
    db.add(
        LmsActivityLog(
            enrollment_id=enrollment_id,
            activity_type="LOGIN",
            activity_at=datetime.now() - timedelta(days=30),
        )
    )
    db.commit()


def recalc(client, headers, **body):
    return client.post("/api/risk-assessments/recalculate", headers=headers, json=body)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def test_recalculation_raises_an_alert_for_an_at_risk_student(
    client, as_instructor, seeded, db
):
    make_at_risk(db)
    response = recalc(client, as_instructor, enrollment_id=1)
    assert response.status_code == 200
    assert response.json()["alerts_opened"] == 1

    alerts = client.get("/api/alerts", headers=as_instructor).json()
    assert alerts["total"] == 1
    alert = alerts["items"][0]
    assert alert["status"] == "NEW"
    assert alert["risk_category"] in ("MEDIUM", "HIGH")
    assert alert["student_id"] == "MTH2024001"
    assert alert["course_code"] == "MTH201"
    assert alert["triggering_factors"]


def test_a_healthy_student_gets_no_alert(client, as_instructor, seeded, db):
    make_at_risk(db, attendance_ratio=1.0)
    recalc(client, as_instructor, enrollment_id=1)
    assert client.get("/api/alerts", headers=as_instructor).json()["total"] == 0


def test_an_unscored_profile_never_raises_an_alert(client, as_instructor, seeded):
    """INSUFFICIENT_DATA must not be treated as at-risk."""
    response = recalc(client, as_instructor, enrollment_id=1)
    assert response.status_code == 200
    assert response.json()["alerts_opened"] == 0

    risk = client.get("/api/risk-assessments/1", headers=as_instructor).json()
    assert risk["row"]["risk_category"] == "INSUFFICIENT_DATA"
    assert client.get("/api/alerts", headers=as_instructor).json()["total"] == 0


def test_repeated_recalculation_refreshes_instead_of_duplicating(
    client, as_instructor, seeded, db
):
    """The composite unique key ``(enrollment_id, active_flag)`` allows at
    most one open alert per enrolment, so re-running must update it."""
    make_at_risk(db)
    recalc(client, as_instructor, enrollment_id=1)
    first = client.get("/api/alerts", headers=as_instructor).json()
    assert first["total"] == 1
    alert_id = first["items"][0]["alert_id"]

    for _ in range(4):
        recalc(client, as_instructor, enrollment_id=1)

    after = client.get("/api/alerts", headers=as_instructor).json()
    assert after["total"] == 1, "no duplicate alerts"
    assert after["items"][0]["alert_id"] == alert_id


def test_the_database_itself_refuses_a_second_open_alert(db, seeded):
    """Belt and braces: the unique key, not just the application code."""
    from sqlalchemy.exc import IntegrityError

    db.add(RiskAlert(enrollment_id=1, risk_score=70, risk_category="HIGH", status="NEW"))
    db.commit()
    db.add(
        RiskAlert(enrollment_id=1, risk_score=80, risk_category="HIGH", status="ACKNOWLEDGED")
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_resolved_alert_does_not_block_a_new_one(db, seeded):
    """``active_flag`` is NULL once resolved, and repeated NULLs are
    allowed inside a UNIQUE key -- so history is unlimited."""
    resolved = RiskAlert(
        enrollment_id=1, risk_score=70, risk_category="HIGH", status="RESOLVED",
        resolved_at=datetime.now(),
    )
    db.add(resolved)
    db.commit()

    second_resolved = RiskAlert(
        enrollment_id=1, risk_score=65, risk_category="HIGH", status="RESOLVED",
        resolved_at=datetime.now(),
    )
    db.add(second_resolved)
    db.commit()

    fresh = RiskAlert(enrollment_id=1, risk_score=75, risk_category="HIGH", status="NEW")
    db.add(fresh)
    db.commit()

    rows = list(db.execute(select(RiskAlert).where(RiskAlert.enrollment_id == 1)).scalars())
    assert len(rows) == 3
    assert sum(1 for r in rows if r.active_flag == 1) == 1


def test_improvement_auto_resolves_an_untouched_alert(client, as_instructor, seeded, db):
    make_at_risk(db)
    recalc(client, as_instructor, enrollment_id=1)
    assert client.get("/api/alerts?only_open=true", headers=as_instructor).json()["total"] == 1

    # the student turns things around
    for record in db.execute(
        select(AttendanceRecord).where(AttendanceRecord.enrollment_id == 1)
    ).scalars():
        record.status = "PRESENT"
    db.add(
        LmsActivityLog(
            enrollment_id=1, activity_type="LOGIN", activity_at=datetime.now()
        )
    )
    db.commit()

    response = recalc(client, as_instructor, enrollment_id=1)
    assert response.json()["alerts_auto_resolved"] == 1
    assert client.get("/api/alerts?only_open=true", headers=as_instructor).json()["total"] == 0


def test_an_acknowledged_alert_is_never_auto_resolved(client, as_advisor, as_instructor, seeded, db):
    """Once a human owns the alert, closing it is their decision."""
    make_at_risk(db)
    recalc(client, as_instructor, enrollment_id=1)
    alert_id = client.get("/api/alerts", headers=as_instructor).json()["items"][0]["alert_id"]
    client.patch(f"/api/alerts/{alert_id}", headers=as_advisor, json={"status": "ACKNOWLEDGED"})

    for record in db.execute(
        select(AttendanceRecord).where(AttendanceRecord.enrollment_id == 1)
    ).scalars():
        record.status = "PRESENT"
    db.commit()

    response = recalc(client, as_instructor, enrollment_id=1)
    assert response.json()["alerts_auto_resolved"] == 0
    still_open = client.get("/api/alerts?only_open=true", headers=as_instructor).json()
    assert still_open["total"] == 1
    assert still_open["items"][0]["status"] == "ACKNOWLEDGED"


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------
@pytest.fixture
def open_alert(client, as_instructor, seeded, db):
    make_at_risk(db)
    recalc(client, as_instructor, enrollment_id=1)
    return client.get("/api/alerts", headers=as_instructor).json()["items"][0]["alert_id"]


@pytest.mark.parametrize(
    "path",
    [
        ["ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED"],
        ["ACKNOWLEDGED", "RESOLVED"],
        ["IN_PROGRESS", "RESOLVED"],
        ["RESOLVED"],
    ],
)
def test_legal_transition_paths(client, as_advisor, open_alert, path):
    for status in path:
        response = client.patch(
            f"/api/alerts/{open_alert}", headers=as_advisor, json={"status": status}
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status


@pytest.mark.parametrize(
    "first,illegal",
    [
        ("IN_PROGRESS", "ACKNOWLEDGED"),  # cannot go backwards
        ("RESOLVED", "NEW"),              # resolved is terminal
        ("RESOLVED", "IN_PROGRESS"),
        ("ACKNOWLEDGED", "NEW"),
    ],
)
def test_illegal_transitions_are_refused(client, as_advisor, open_alert, first, illegal):
    client.patch(f"/api/alerts/{open_alert}", headers=as_advisor, json={"status": first})
    response = client.patch(
        f"/api/alerts/{open_alert}", headers=as_advisor, json={"status": illegal}
    )
    assert response.status_code == 409
    assert "Cannot move an alert" in response.json()["detail"]


def test_acknowledging_stamps_the_timestamp(client, as_advisor, open_alert):
    response = client.patch(
        f"/api/alerts/{open_alert}", headers=as_advisor, json={"status": "ACKNOWLEDGED"}
    )
    assert response.json()["acknowledged_at"] is not None


def test_resolving_stamps_the_timestamp(client, as_advisor, open_alert):
    response = client.patch(
        f"/api/alerts/{open_alert}", headers=as_advisor, json={"status": "RESOLVED"}
    )
    assert response.json()["resolved_at"] is not None


def test_every_status_change_is_recorded_in_history(client, as_advisor, open_alert, db):
    client.patch(f"/api/alerts/{open_alert}", headers=as_advisor,
                 json={"status": "ACKNOWLEDGED", "note": "Emailed the student"})
    client.patch(f"/api/alerts/{open_alert}", headers=as_advisor, json={"status": "IN_PROGRESS"})

    detail = client.get(f"/api/alerts/{open_alert}", headers=as_advisor).json()
    history = detail["history"]
    # NEW (raised) + 2 transitions
    assert len(history) == 3
    transitions = {(h["old_status"], h["new_status"]) for h in history}
    assert (None, "NEW") in transitions
    assert ("NEW", "ACKNOWLEDGED") in transitions
    assert ("ACKNOWLEDGED", "IN_PROGRESS") in transitions
    note = next(h["note"] for h in history if h["new_status"] == "ACKNOWLEDGED")
    assert note == "Emailed the student"
    assert all(
        h["changed_by_name"] == "Advisor User"
        for h in history
        if h["new_status"] != "NEW"
    )


def test_assign_an_alert_to_an_advisor(client, as_advisor, open_alert, seeded):
    response = client.patch(
        f"/api/alerts/{open_alert}",
        headers=as_advisor,
        json={"assigned_to": seeded.users["ADVISOR"].user_id},
    )
    assert response.status_code == 200
    assert response.json()["assignee_name"] == "Advisor User"


def test_an_alert_cannot_be_assigned_to_a_chair_or_ta(client, as_advisor, open_alert, seeded):
    for role in ("CHAIR", "TA"):
        response = client.patch(
            f"/api/alerts/{open_alert}",
            headers=as_advisor,
            json={"assigned_to": seeded.users[role].user_id},
        )
        assert response.status_code == 422
        assert "can only be assigned to" in response.json()["detail"]


def test_assigning_to_an_unknown_user_is_rejected(client, as_advisor, open_alert):
    response = client.patch(
        f"/api/alerts/{open_alert}", headers=as_advisor, json={"assigned_to": 9999}
    )
    assert response.status_code == 422


def test_status_and_assignee_can_change_together(client, as_advisor, open_alert, seeded):
    response = client.patch(
        f"/api/alerts/{open_alert}",
        headers=as_advisor,
        json={"status": "IN_PROGRESS", "assigned_to": seeded.users["ADVISOR"].user_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"
    assert response.json()["assigned_to"] == seeded.users["ADVISOR"].user_id


def test_an_empty_patch_is_rejected(client, as_advisor, open_alert):
    assert client.patch(f"/api/alerts/{open_alert}", headers=as_advisor, json={}).status_code == 422


def test_patching_an_unknown_alert_is_404(client, as_advisor, seeded):
    response = client.patch("/api/alerts/9999", headers=as_advisor, json={"status": "RESOLVED"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Filtering and the summary
# ---------------------------------------------------------------------------
def test_filter_the_alert_queue(client, as_instructor, as_advisor, seeded, db):
    make_at_risk(db, enrollment_id=1)
    make_at_risk(db, enrollment_id=2, attendance_ratio=0.65)
    recalc(client, as_instructor)

    everything = client.get("/api/alerts", headers=as_instructor).json()
    assert everything["total"] == 2

    by_status = client.get("/api/alerts?alert_status=NEW", headers=as_instructor)
    assert by_status.json()["total"] == 2

    by_course = client.get("/api/alerts?course_pk=1", headers=as_instructor)
    assert by_course.json()["total"] == 2

    by_other_course = client.get(
        f"/api/alerts?course_pk={seeded.course_b.course_pk}", headers=as_instructor
    )
    assert by_other_course.json()["total"] == 0

    unassigned = client.get("/api/alerts?unassigned=true", headers=as_instructor)
    assert unassigned.json()["total"] == 2

    by_search = client.get("/api/alerts?search=MTH2024001", headers=as_instructor)
    assert by_search.json()["total"] == 1


def test_filter_by_date_window(client, as_instructor, seeded, db):
    make_at_risk(db)
    recalc(client, as_instructor, enrollment_id=1)

    today = date.today().isoformat()
    assert client.get(f"/api/alerts?date_from={today}", headers=as_instructor).json()["total"] == 1
    future = (date.today() + timedelta(days=1)).isoformat()
    assert client.get(f"/api/alerts?date_from={future}", headers=as_instructor).json()["total"] == 0


def test_alert_summary_counts(client, as_instructor, as_advisor, seeded, db):
    make_at_risk(db, enrollment_id=1)
    make_at_risk(db, enrollment_id=2)
    recalc(client, as_instructor)

    summary = client.get("/api/alerts/summary", headers=as_instructor).json()
    assert summary["total"] == 2
    assert summary["by_status"]["NEW"] == 2
    assert summary["unassigned_open"] == 2
    assert summary["unresolved_high_risk"] == summary["open_by_category"].get("HIGH", 0)


def test_alert_detail_includes_the_risk_context(client, as_instructor, open_alert):
    detail = client.get(f"/api/alerts/{open_alert}", headers=as_instructor).json()
    assert detail["alert"]["alert_id"] == open_alert
    assert detail["risk"] is not None
    assert detail["risk"]["enrollment_id"] == 1
    assert detail["risk"]["contributing_factors"]
    assert detail["interventions"] == []


def test_unknown_alert_detail_is_404(client, as_instructor, seeded):
    assert client.get("/api/alerts/9999", headers=as_instructor).status_code == 404
