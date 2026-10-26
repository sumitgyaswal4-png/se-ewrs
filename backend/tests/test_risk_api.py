"""Risk analysis endpoints: recalculation, the table and the explanation."""

from datetime import date, datetime, timedelta

from app.models import AssessmentResult, AttendanceRecord, LmsActivityLog


def give_data(db, enrollment_id=1, attended=8, total=10, marks=15, days_dormant=1, logins=12):
    """Attendance + marks + activity for one enrolment."""
    for index in range(total):
        db.add(
            AttendanceRecord(
                enrollment_id=enrollment_id,
                session_date=date.today() - timedelta(days=index + 1),
                session_no=1,
                status="PRESENT" if index < attended else "ABSENT",
            )
        )
    if marks is not None:
        db.add(
            AssessmentResult(
                assessment_id=1,
                enrollment_id=enrollment_id,
                marks_obtained=marks,
                percentage=round(100 * marks / 20, 2),
                submission_status="ON_TIME",
                submitted_at=datetime.now() - timedelta(days=12),
                graded_at=datetime.now() - timedelta(days=10),
            )
        )
    for index in range(logins):
        db.add(
            LmsActivityLog(
                enrollment_id=enrollment_id,
                activity_type="LOGIN",
                activity_at=datetime.now() - timedelta(days=days_dormant + index),
            )
        )
    db.commit()


def recalc(client, headers, **body):
    return client.post("/api/risk-assessments/recalculate", headers=headers, json=body)


def test_recalculate_one_enrolment(client, as_instructor, seeded, db):
    give_data(db)
    response = recalc(client, as_instructor, enrollment_id=1)
    assert response.status_code == 200
    assert response.json()["enrollments_processed"] == 1


def test_recalculate_every_active_enrolment(client, as_instructor, seeded, db):
    give_data(db, enrollment_id=1)
    give_data(db, enrollment_id=2)
    response = recalc(client, as_instructor)
    assert response.json()["enrollments_processed"] == 3  # three fixture enrolments


def test_recalculate_scoped_to_one_course(client, as_instructor, seeded, db):
    give_data(db)
    response = recalc(client, as_instructor, course_pk=seeded.course_b.course_pk)
    assert response.json()["enrollments_processed"] == 0


def test_dropped_enrolments_are_skipped(client, as_instructor, seeded, db):
    seeded.enrollments[0].status = "DROPPED"
    db.commit()
    assert recalc(client, as_instructor).json()["enrollments_processed"] == 2


def test_cannot_pass_both_scopes(client, as_instructor, seeded):
    response = recalc(client, as_instructor, enrollment_id=1, course_pk=1)
    assert response.status_code == 422
    assert "not both" in response.json()["detail"]


def test_recalculate_unknown_enrolment_is_404(client, as_instructor, seeded):
    assert recalc(client, as_instructor, enrollment_id=9999).status_code == 404


def test_recalculate_unknown_course_is_404(client, as_instructor, seeded):
    assert recalc(client, as_instructor, course_pk=9999).status_code == 404


# ---------------------------------------------------------------------------
# The risk table
# ---------------------------------------------------------------------------
def test_risk_table_reports_the_documented_figures(client, as_instructor, seeded, db):
    give_data(db, attended=8, total=10, marks=15)
    recalc(client, as_instructor, enrollment_id=1)

    rows = client.get("/api/risk-assessments?search=MTH2024001", headers=as_instructor).json()
    row = rows["items"][0]
    assert row["student_id"] == "MTH2024001"
    assert row["course_code"] == "MTH201"
    assert row["attendance_percentage"] == 80.0
    assert row["avg_assessment_percentage"] == 75.0
    assert row["sessions_held"] == 10
    assert row["sessions_attended"] == 8
    assert row["graded_assessments"] == 1
    assert row["data_completeness"] == "COMPLETE"
    # 0.35*20 + 0.40*25 + 0.25*engagement_risk
    assert row["attendance_risk"] == 20.0
    assert row["academic_risk"] == 25.0
    assert 0 <= row["risk_score"] <= 100
    assert row["risk_category"] in ("LOW", "MEDIUM", "HIGH")
    assert row["model_version"] == "rule-v1"


def test_risk_table_lists_unscored_enrolments_too(client, as_instructor, seeded):
    """An enrolment with no risk run yet must still appear, flagged."""
    rows = client.get("/api/risk-assessments", headers=as_instructor).json()
    assert rows["total"] == 3
    assert all(r["risk_category"] == "INSUFFICIENT_DATA" for r in rows["items"])
    assert all(r["risk_score"] is None for r in rows["items"])


def test_filter_the_risk_table(client, as_instructor, seeded, db):
    give_data(db, enrollment_id=1, attended=9, total=10, marks=18)   # healthy
    give_data(db, enrollment_id=2, attended=2, total=10, marks=4, days_dormant=25, logins=1)
    recalc(client, as_instructor)

    high = client.get("/api/risk-assessments?risk_category=HIGH", headers=as_instructor).json()
    assert high["total"] >= 1
    assert all(r["risk_category"] == "HIGH" for r in high["items"])

    above_50 = client.get("/api/risk-assessments?min_score=50", headers=as_instructor).json()
    assert all(r["risk_score"] >= 50 for r in above_50["items"])

    with_alerts = client.get(
        "/api/risk-assessments?has_open_alert=true", headers=as_instructor
    ).json()
    assert all(r["open_alert_id"] is not None for r in with_alerts["items"])

    by_course = client.get(
        f"/api/risk-assessments?course_pk={seeded.course_b.course_pk}", headers=as_instructor
    ).json()
    assert by_course["total"] == 0


def test_risk_table_sorts_highest_first_with_nulls_last(client, as_instructor, seeded, db):
    give_data(db, enrollment_id=1, attended=9, total=10, marks=18)
    give_data(db, enrollment_id=2, attended=2, total=10, marks=4, days_dormant=25, logins=1)
    recalc(client, as_instructor)

    rows = client.get(
        "/api/risk-assessments?sort_by=risk_score&sort_dir=desc", headers=as_instructor
    ).json()["items"]
    scored = [r["risk_score"] for r in rows if r["risk_score"] is not None]
    assert scored == sorted(scored, reverse=True)
    # the unscored third enrolment must be last, not first
    assert rows[-1]["risk_score"] is None


# ---------------------------------------------------------------------------
# The per-student explanation
# ---------------------------------------------------------------------------
def test_detail_explains_every_component(client, as_instructor, seeded, db):
    give_data(db, attended=8, total=10, marks=15)
    recalc(client, as_instructor, enrollment_id=1)

    detail = client.get("/api/risk-assessments/1", headers=as_instructor).json()
    assert detail["weights"] == {"attendance": 0.35, "academic": 0.40, "engagement": 0.25}
    assert detail["thresholds"]["medium"] == 30
    assert detail["thresholds"]["high"] == 60
    assert "early-warning indicator" in detail["disclaimer"]

    names = {c["name"]: c for c in detail["components"]}
    assert set(names) == {"Attendance", "Academic", "Engagement"}
    assert all(c["available"] for c in detail["components"])
    assert names["Attendance"]["risk_value"] == 20.0
    assert names["Academic"]["risk_value"] == 25.0
    # all three present, so each effective weight equals its nominal weight
    assert names["Attendance"]["effective_weight"] == 0.35
    assert names["Academic"]["effective_weight"] == 0.40
    assert names["Engagement"]["effective_weight"] == 0.25
    assert sum(c["effective_weight"] for c in detail["components"]) == 1.0

    breakdown = detail["engagement_breakdown"]
    assert "recency_penalty" in breakdown
    assert "login_frequency_penalty" in breakdown


def test_detail_shows_why_a_component_was_skipped(client, as_instructor, seeded, db):
    """No marks recorded: the academic component must be reported as
    unavailable with a reason, and its weight redistributed."""
    give_data(db, marks=None)
    recalc(client, as_instructor, enrollment_id=1)

    detail = client.get("/api/risk-assessments/1", headers=as_instructor).json()
    names = {c["name"]: c for c in detail["components"]}
    academic = names["Academic"]
    assert academic["available"] is False
    assert academic["risk_value"] is None
    assert academic["effective_weight"] == 0.0
    assert "not counted as a zero" in academic["unavailable_reason"]

    # the surviving weights renormalise to 1
    survivors = [c for c in detail["components"] if c["available"]]
    assert round(sum(c["effective_weight"] for c in survivors), 4) == 1.0
    assert detail["row"]["data_completeness"] == "PARTIAL"
    assert "Academic component skipped" in detail["row"]["missing_data_reasons"]


def test_detail_works_before_any_risk_run(client, as_instructor, seeded, db):
    """The page must explain a brand-new enrolment, not 404 on it."""
    give_data(db)
    detail = client.get("/api/risk-assessments/1", headers=as_instructor).json()
    assert detail["row"]["risk_id"] is None
    assert detail["row"]["risk_score"] is not None, "computed live"
    assert detail["components"]


def test_detail_of_unknown_enrolment_is_404(client, as_instructor, seeded):
    assert client.get("/api/risk-assessments/9999", headers=as_instructor).status_code == 404


def test_history_accumulates_one_point_per_run(client, as_instructor, seeded, db):
    give_data(db)
    for _ in range(3):
        recalc(client, as_instructor, enrollment_id=1)

    history = client.get("/api/risk-assessments/1/history", headers=as_instructor).json()
    assert len(history) == 3
    assert all(point["risk_score"] is not None for point in history)
    assert all("calculated_at" in point for point in history)


def test_history_is_chronological(client, as_instructor, seeded, db):
    give_data(db)
    recalc(client, as_instructor, enrollment_id=1)
    recalc(client, as_instructor, enrollment_id=1)
    history = client.get("/api/risk-assessments/1/history", headers=as_instructor).json()
    timestamps = [point["calculated_at"] for point in history]
    assert timestamps == sorted(timestamps)


def test_history_of_unknown_enrolment_is_404(client, as_instructor, seeded):
    assert client.get("/api/risk-assessments/9999/history", headers=as_instructor).status_code == 404


def test_the_table_reflects_only_the_latest_run(client, as_instructor, seeded, db):
    """The risk table reads the newest row per enrolment, not every row."""
    give_data(db, attended=2, total=10, marks=4, days_dormant=25, logins=1)
    recalc(client, as_instructor, enrollment_id=1)
    first = client.get("/api/risk-assessments?search=MTH2024001", headers=as_instructor).json()
    first_score = first["items"][0]["risk_score"]

    for record in db.query(AttendanceRecord).filter_by(enrollment_id=1).all():
        record.status = "PRESENT"
    db.commit()
    recalc(client, as_instructor, enrollment_id=1)

    second = client.get("/api/risk-assessments?search=MTH2024001", headers=as_instructor).json()
    assert second["total"] == 1, "one row per enrolment, not one per run"
    assert second["items"][0]["risk_score"] < first_score


def test_changing_a_weight_changes_the_next_score(client, as_admin, seeded, db):
    """The model reads its weights from system_settings at run time."""
    give_data(db, attended=5, total=10, marks=5)
    recalc(client, as_admin, enrollment_id=1)
    before = client.get("/api/risk-assessments/1", headers=as_admin).json()["row"]["risk_score"]

    client.put(
        "/api/settings/risk.weight.attendance", headers=as_admin, json={"setting_value": "0.10"}
    )
    client.put(
        "/api/settings/risk.weight.academic", headers=as_admin, json={"setting_value": "0.65"}
    )
    recalc(client, as_admin, enrollment_id=1)
    after = client.get("/api/risk-assessments/1", headers=as_admin).json()["row"]["risk_score"]
    assert after != before
