"""Intervention tracking and its link to risk alerts."""

from datetime import date, datetime, timedelta

from app.models import AttendanceRecord, LmsActivityLog, RiskAlert


def base(**overrides) -> dict:
    payload = {
        "enrollment_id": 1,
        "intervention_type": "COUNSELING",
        "contact_date": date.today().isoformat(),
        "notes": "Met the student to discuss the missed classes.",
        "action_plan": "Weekly check-in for the next month.",
    }
    payload.update(overrides)
    return payload


def test_record_an_intervention(client, as_advisor, seeded):
    response = client.post("/api/interventions", headers=as_advisor, json=base())
    assert response.status_code == 201
    body = response.json()
    assert body["intervention_type"] == "COUNSELING"
    assert body["outcome"] == "PENDING"
    assert body["resolution_status"] == "OPEN"
    assert body["student_id"] == "MTH2024001"
    assert body["course_code"] == "MTH201"


def test_the_recorder_becomes_the_advisor_by_default(client, as_advisor, seeded):
    response = client.post("/api/interventions", headers=as_advisor, json=base())
    assert response.json()["assigned_advisor_id"] == seeded.users["ADVISOR"].user_id
    assert response.json()["advisor_name"] == "Advisor User"


def test_an_explicit_advisor_is_respected(client, as_advisor, seeded):
    response = client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(assigned_advisor_id=seeded.users["INSTRUCTOR"].user_id),
    )
    assert response.json()["advisor_name"] == "Instructor User"


def test_a_chair_cannot_own_an_intervention(client, as_advisor, seeded):
    response = client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(assigned_advisor_id=seeded.users["CHAIR"].user_id),
    )
    assert response.status_code == 422
    assert "cannot own an intervention" in response.json()["detail"]


def test_every_intervention_type_is_accepted(client, as_advisor, seeded):
    types = [
        "COUNSELING",
        "TUTORING_REFERRAL",
        "ASSIGNMENT_SUPPORT",
        "ATTENDANCE_FOLLOWUP",
        "ACADEMIC_ADVISING",
        "PARENT_CONTACT",
    ]
    for index, i_type in enumerate(types):
        response = client.post(
            "/api/interventions",
            headers=as_advisor,
            json=base(intervention_type=i_type, enrollment_id=(index % 3) + 1),
        )
        assert response.status_code == 201, i_type


def test_unknown_intervention_type_is_rejected(client, as_advisor, seeded):
    response = client.post(
        "/api/interventions", headers=as_advisor, json=base(intervention_type="EXORCISM")
    )
    assert response.status_code == 422


def test_unknown_enrolment_is_rejected(client, as_advisor, seeded):
    response = client.post("/api/interventions", headers=as_advisor, json=base(enrollment_id=9999))
    assert response.status_code == 422


def test_follow_up_before_the_contact_date_is_rejected(client, as_advisor, seeded):
    response = client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(
            contact_date=date.today().isoformat(),
            follow_up_date=(date.today() - timedelta(days=3)).isoformat(),
        ),
    )
    assert response.status_code == 422


def test_follow_up_on_the_contact_date_is_allowed(client, as_advisor, seeded):
    today = date.today().isoformat()
    response = client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(contact_date=today, follow_up_date=today),
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Linking to alerts
# ---------------------------------------------------------------------------
def test_link_an_intervention_to_its_alert(client, as_advisor, seeded, db):
    db.add(
        RiskAlert(alert_id=1, enrollment_id=1, risk_score=72, risk_category="HIGH", status="NEW")
    )
    db.commit()

    response = client.post("/api/interventions", headers=as_advisor, json=base(alert_id=1))
    assert response.status_code == 201
    assert response.json()["alert_id"] == 1

    detail = client.get("/api/alerts/1", headers=as_advisor).json()
    assert len(detail["interventions"]) == 1
    assert detail["alert"]["intervention_count"] == 1


def test_an_alert_from_another_enrolment_is_refused(client, as_advisor, seeded, db):
    """A plain foreign key cannot express this, so it is checked
    explicitly -- and again by the trg_intervention_before_insert trigger
    on MySQL."""
    db.add(
        RiskAlert(alert_id=1, enrollment_id=2, risk_score=72, risk_category="HIGH", status="NEW")
    )
    db.commit()

    response = client.post(
        "/api/interventions", headers=as_advisor, json=base(enrollment_id=1, alert_id=1)
    )
    assert response.status_code == 422
    assert "different enrolment" in response.json()["detail"]


def test_an_unknown_alert_is_refused(client, as_advisor, seeded):
    response = client.post("/api/interventions", headers=as_advisor, json=base(alert_id=9999))
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Updating and history
# ---------------------------------------------------------------------------
def test_record_an_outcome(client, as_advisor, seeded):
    created = client.post("/api/interventions", headers=as_advisor, json=base())
    intervention_id = created.json()["intervention_id"]

    updated = client.put(
        f"/api/interventions/{intervention_id}",
        headers=as_advisor,
        json={
            "outcome": "IMPROVED",
            "resolution_status": "CLOSED",
            "notes": "Attendance recovered over three weeks.",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["outcome"] == "IMPROVED"
    assert body["resolution_status"] == "CLOSED"
    assert "recovered" in body["notes"]


def test_invalid_outcome_is_rejected(client, as_advisor, seeded):
    created = client.post("/api/interventions", headers=as_advisor, json=base())
    response = client.put(
        f"/api/interventions/{created.json()['intervention_id']}",
        headers=as_advisor,
        json={"outcome": "MAGIC"},
    )
    assert response.status_code == 422


def test_update_cannot_invert_the_dates(client, as_advisor, seeded):
    created = client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(contact_date=(date.today() - timedelta(days=5)).isoformat()),
    )
    response = client.put(
        f"/api/interventions/{created.json()['intervention_id']}",
        headers=as_advisor,
        json={"follow_up_date": (date.today() - timedelta(days=10)).isoformat()},
    )
    assert response.status_code == 422


def test_update_unknown_intervention_is_404(client, as_advisor, seeded):
    response = client.put("/api/interventions/9999", headers=as_advisor, json={"outcome": "IMPROVED"})
    assert response.status_code == 404


def test_history_is_kept_per_student(client, as_advisor, seeded):
    for index in range(3):
        client.post(
            "/api/interventions",
            headers=as_advisor,
            json=base(contact_date=(date.today() - timedelta(days=index * 7)).isoformat()),
        )
    listed = client.get("/api/interventions?student_pk=1", headers=as_advisor).json()
    assert listed["total"] == 3
    # newest first
    dates = [row["contact_date"] for row in listed["items"]]
    assert dates == sorted(dates, reverse=True)


def test_filter_interventions(client, as_advisor, seeded):
    client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(intervention_type="TUTORING_REFERRAL", enrollment_id=1),
    )
    client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(intervention_type="COUNSELING", enrollment_id=2),
    )

    assert client.get("/api/interventions", headers=as_advisor).json()["total"] == 2
    assert (
        client.get(
            "/api/interventions?intervention_type=COUNSELING", headers=as_advisor
        ).json()["total"]
        == 1
    )
    assert client.get("/api/interventions?course_pk=1", headers=as_advisor).json()["total"] == 2
    assert client.get("/api/interventions?student_pk=2", headers=as_advisor).json()["total"] == 1
    assert (
        client.get("/api/interventions?outcome=PENDING", headers=as_advisor).json()["total"] == 2
    )
    assert client.get("/api/interventions?search=MTH2024002", headers=as_advisor).json()["total"] == 1


def test_follow_up_due_filter_finds_overdue_records(client, as_advisor, seeded):
    client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(
            contact_date=(date.today() - timedelta(days=20)).isoformat(),
            follow_up_date=(date.today() - timedelta(days=5)).isoformat(),
        ),
    )
    client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(
            enrollment_id=2,
            contact_date=date.today().isoformat(),
            follow_up_date=(date.today() + timedelta(days=10)).isoformat(),
        ),
    )
    due = client.get("/api/interventions?follow_up_due=true", headers=as_advisor).json()
    assert due["total"] == 1


def test_closed_records_drop_out_of_the_follow_up_queue(client, as_advisor, seeded):
    created = client.post(
        "/api/interventions",
        headers=as_advisor,
        json=base(
            contact_date=(date.today() - timedelta(days=20)).isoformat(),
            follow_up_date=(date.today() - timedelta(days=5)).isoformat(),
        ),
    )
    assert client.get("/api/interventions?follow_up_due=true", headers=as_advisor).json()["total"] == 1
    client.put(
        f"/api/interventions/{created.json()['intervention_id']}",
        headers=as_advisor,
        json={"resolution_status": "CLOSED"},
    )
    assert client.get("/api/interventions?follow_up_due=true", headers=as_advisor).json()["total"] == 0


def test_the_record_carries_the_students_current_risk(client, as_instructor, as_advisor, seeded, db):
    for index in range(10):
        db.add(
            AttendanceRecord(
                enrollment_id=1,
                session_date=date.today() - timedelta(days=index + 1),
                session_no=1,
                status="ABSENT" if index > 2 else "PRESENT",
            )
        )
    db.add(
        LmsActivityLog(
            enrollment_id=1,
            activity_type="LOGIN",
            activity_at=datetime.now() - timedelta(days=25),
        )
    )
    db.commit()
    client.post("/api/risk-assessments/recalculate", headers=as_instructor, json={"enrollment_id": 1})

    created = client.post("/api/interventions", headers=as_advisor, json=base())
    body = client.get(
        f"/api/interventions/{created.json()['intervention_id']}", headers=as_advisor
    ).json()
    assert body["current_risk_score"] is not None
    assert body["current_risk_category"] in ("LOW", "MEDIUM", "HIGH", "INSUFFICIENT_DATA")


def test_unknown_intervention_is_404(client, as_advisor, seeded):
    assert client.get("/api/interventions/9999", headers=as_advisor).status_code == 404
