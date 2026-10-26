"""Assessments, marks validation and the percentage calculation."""

from datetime import datetime, timedelta


def test_create_an_assessment(client, as_instructor, seeded):
    response = client.post(
        "/api/assessments",
        headers=as_instructor,
        json={
            "course_pk": 1,
            "title": "Mid-term Examination",
            "assessment_type": "MIDTERM",
            "max_marks": 50,
            "weight_percent": 25,
            "due_at": (datetime.now() + timedelta(days=7)).isoformat(),
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["max_marks"] == 50.0
    assert body["course_code"] == "MTH201"


def test_duplicate_title_in_the_same_course_is_rejected(client, as_instructor, seeded):
    payload = {
        "course_pk": 1,
        "title": "Assignment 1",  # already exists in the fixture
        "assessment_type": "ASSIGNMENT",
        "max_marks": 20,
        "due_at": datetime.now().isoformat(),
    }
    response = client.post("/api/assessments", headers=as_instructor, json=payload)
    assert response.status_code == 409


def test_same_title_in_a_different_course_is_allowed(client, as_instructor, seeded):
    response = client.post(
        "/api/assessments",
        headers=as_instructor,
        json={
            "course_pk": seeded.course_b.course_pk,
            "title": "Assignment 1",
            "assessment_type": "ASSIGNMENT",
            "max_marks": 20,
            "due_at": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 201


def test_zero_or_negative_max_marks_is_rejected(client, as_instructor, seeded):
    for bad in (0, -5):
        response = client.post(
            "/api/assessments",
            headers=as_instructor,
            json={
                "course_pk": 1,
                "title": f"Bad {bad}",
                "assessment_type": "QUIZ",
                "max_marks": bad,
                "due_at": datetime.now().isoformat(),
            },
        )
        assert response.status_code == 422


def test_unknown_assessment_type_is_rejected(client, as_instructor, seeded):
    response = client.post(
        "/api/assessments",
        headers=as_instructor,
        json={
            "course_pk": 1,
            "title": "Oral",
            "assessment_type": "VIVA",
            "max_marks": 10,
            "due_at": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Marks entry: validation and the derived percentage
# ---------------------------------------------------------------------------
def enter(client, headers, marks, enrollment_id=1, assessment_id=1, submitted_at=None):
    payload = {
        "assessment_id": assessment_id,
        "enrollment_id": enrollment_id,
        "marks_obtained": marks,
    }
    if submitted_at is not None:
        payload["submitted_at"] = submitted_at
    return client.post("/api/assessment-results", headers=headers, json=payload)


def test_percentage_is_derived_server_side(client, as_instructor, seeded):
    """max_marks is 20, so 15 marks must become exactly 75.00%."""
    response = enter(client, as_instructor, 15)
    assert response.status_code == 201
    body = response.json()
    assert body["marks_obtained"] == 15.0
    assert body["max_marks"] == 20.0
    assert body["percentage"] == 75.0


def test_percentage_rounds_half_up_to_two_decimals(client, as_instructor, seeded):
    # 7 / 20 = 35%, 13 / 20 = 65%, 1 / 20 = 5%
    assert enter(client, as_instructor, 7).json()["percentage"] == 35.0
    assert enter(client, as_instructor, 13).json()["percentage"] == 65.0
    assert enter(client, as_instructor, 1).json()["percentage"] == 5.0


def test_percentage_of_a_repeating_fraction(client, as_instructor, seeded, db):
    """1 of 3 marks -> 33.33 (half-up at two decimals)."""
    from app.models import Assessment

    db.add(
        Assessment(
            assessment_id=2,
            course_pk=1,
            title="Three-mark quiz",
            assessment_type="QUIZ",
            max_marks=3,
            due_at=datetime.now(),
        )
    )
    db.commit()
    response = enter(client, as_instructor, 1, assessment_id=2)
    assert response.json()["percentage"] == 33.33


def test_full_marks_is_one_hundred_percent(client, as_instructor, seeded):
    assert enter(client, as_instructor, 20).json()["percentage"] == 100.0


def test_zero_marks_is_zero_percent_and_is_distinct_from_ungraded(
    client, as_instructor, seeded
):
    zero = enter(client, as_instructor, 0)
    assert zero.json()["percentage"] == 0.0
    assert zero.json()["marks_obtained"] == 0.0

    ungraded = enter(client, as_instructor, None, enrollment_id=2)
    assert ungraded.json()["marks_obtained"] is None
    assert ungraded.json()["percentage"] is None


def test_negative_marks_are_rejected(client, as_instructor, seeded):
    response = enter(client, as_instructor, -1)
    assert response.status_code == 422


def test_marks_above_the_maximum_are_rejected(client, as_instructor, seeded):
    response = enter(client, as_instructor, 21)  # max_marks is 20
    assert response.status_code == 422
    assert "cannot exceed the maximum marks" in response.json()["detail"]


def test_marks_exactly_at_the_maximum_are_accepted(client, as_instructor, seeded):
    assert enter(client, as_instructor, 20).status_code == 201


def test_re_entering_marks_corrects_the_existing_row(client, as_instructor, seeded):
    first = enter(client, as_instructor, 10)
    second = enter(client, as_instructor, 18)
    assert first.json()["result_id"] == second.json()["result_id"]
    assert second.json()["percentage"] == 90.0
    listed = client.get("/api/assessment-results?assessment_id=1", headers=as_instructor)
    assert listed.json()["total"] == 1


def test_submission_status_is_derived_from_the_deadline(client, as_instructor, seeded):
    due = seeded.assessment.due_at

    on_time = enter(
        client, as_instructor, 15, enrollment_id=1,
        submitted_at=(due - timedelta(hours=2)).isoformat(),
    )
    assert on_time.json()["submission_status"] == "ON_TIME"

    late = enter(
        client, as_instructor, 15, enrollment_id=2,
        submitted_at=(due + timedelta(days=2)).isoformat(),
    )
    assert late.json()["submission_status"] == "LATE"

    missing = enter(client, as_instructor, None, enrollment_id=3)
    assert missing.json()["submission_status"] == "MISSING"


def test_result_for_an_enrolment_in_another_course_is_rejected(client, as_instructor, seeded, db):
    from datetime import date

    from app.models import Enrollment

    db.add(
        Enrollment(
            enrollment_id=50,
            student_pk=1,
            course_pk=seeded.course_b.course_pk,
            enrolled_on=date.today(),
            status="ACTIVE",
        )
    )
    db.commit()
    response = enter(client, as_instructor, 10, enrollment_id=50)
    assert response.status_code == 422
    assert "different course" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Bulk grade entry
# ---------------------------------------------------------------------------
def test_bulk_entry_grades_the_whole_class(client, as_instructor, seeded):
    response = client.post(
        "/api/assessment-results/bulk",
        headers=as_instructor,
        json={
            "assessment_id": 1,
            "rows": [
                {"enrollment_id": 1, "marks_obtained": 18},
                {"enrollment_id": 2, "marks_obtained": 12},
                {"enrollment_id": 3, "marks_obtained": 6},
            ],
        },
    )
    assert response.status_code == 200
    assert "3 result(s) added" in response.json()["detail"]

    results = client.get("/api/assessment-results?assessment_id=1", headers=as_instructor).json()
    percentages = sorted(r["percentage"] for r in results["items"])
    assert percentages == [30.0, 60.0, 90.0]


def test_one_bad_mark_rejects_the_whole_batch(client, as_instructor, seeded):
    """All-or-nothing: a half-saved grade sheet would be worse than none."""
    response = client.post(
        "/api/assessment-results/bulk",
        headers=as_instructor,
        json={
            "assessment_id": 1,
            "rows": [
                {"enrollment_id": 1, "marks_obtained": 18},
                {"enrollment_id": 2, "marks_obtained": 99},  # over max_marks
            ],
        },
    )
    assert response.status_code == 422
    listed = client.get("/api/assessment-results?assessment_id=1", headers=as_instructor)
    assert listed.json()["total"] == 0, "nothing should have been written"


def test_bulk_rejects_an_enrolment_outside_the_roster(client, as_instructor, seeded, db):
    from datetime import date

    from app.models import Enrollment

    db.add(
        Enrollment(
            enrollment_id=60, student_pk=2, course_pk=seeded.course_b.course_pk,
            enrolled_on=date.today(), status="ACTIVE",
        )
    )
    db.commit()
    response = client.post(
        "/api/assessment-results/bulk",
        headers=as_instructor,
        json={"assessment_id": 1, "rows": [{"enrollment_id": 60, "marks_obtained": 10}]},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The marks grid and history
# ---------------------------------------------------------------------------
def test_results_grid_returns_the_whole_roster_including_ungraded(
    client, as_instructor, seeded
):
    enter(client, as_instructor, 15, enrollment_id=1)
    grid = client.get("/api/assessments/1/results", headers=as_instructor).json()
    assert len(grid) == 3
    graded = [r for r in grid if r["marks_obtained"] is not None]
    pending = [r for r in grid if r["result_id"] == 0]
    assert len(graded) == 1
    assert len(pending) == 2
    assert all(r["max_marks"] == 20.0 for r in grid)


def test_lowering_max_marks_below_a_recorded_mark_is_blocked(client, as_instructor, seeded):
    enter(client, as_instructor, 18)
    response = client.put("/api/assessments/1", headers=as_instructor, json={"max_marks": 10})
    assert response.status_code == 422
    assert "already exceeds it" in response.json()["detail"]


def test_raising_max_marks_recomputes_stored_percentages(client, as_instructor, seeded):
    """The stored percentage must stay consistent with the new scale."""
    enter(client, as_instructor, 10)  # 10/20 = 50%
    client.put("/api/assessments/1", headers=as_instructor, json={"max_marks": 40})
    results = client.get("/api/assessment-results?assessment_id=1", headers=as_instructor).json()
    assert results["items"][0]["percentage"] == 25.0  # 10/40


def test_changing_the_deadline_re_derives_submission_status(client, as_instructor, seeded):
    due = seeded.assessment.due_at
    enter(client, as_instructor, 15, submitted_at=(due + timedelta(days=1)).isoformat())
    results = client.get("/api/assessment-results?assessment_id=1", headers=as_instructor).json()
    assert results["items"][0]["submission_status"] == "LATE"

    client.put(
        "/api/assessments/1",
        headers=as_instructor,
        json={"due_at": (due + timedelta(days=5)).isoformat()},
    )
    results = client.get("/api/assessment-results?assessment_id=1", headers=as_instructor).json()
    assert results["items"][0]["submission_status"] == "ON_TIME"


def test_performance_trend_groups_by_month(client, as_instructor, seeded):
    client.post(
        "/api/assessment-results/bulk",
        headers=as_instructor,
        json={
            "assessment_id": 1,
            "rows": [
                {"enrollment_id": 1, "marks_obtained": 20},
                {"enrollment_id": 2, "marks_obtained": 10},
            ],
        },
    )
    trend = client.get("/api/assessments/trends?course_pk=1", headers=as_instructor).json()
    assert len(trend) == 1
    assert trend[0]["graded_results"] == 2
    assert trend[0]["avg_percentage"] == 75.0  # mean of 100 and 50


def test_assessment_list_reports_graded_counts_and_mean(client, as_instructor, seeded):
    enter(client, as_instructor, 20, enrollment_id=1)
    enter(client, as_instructor, 10, enrollment_id=2)
    enter(client, as_instructor, None, enrollment_id=3)

    listed = client.get("/api/assessments?course_pk=1", headers=as_instructor).json()
    row = listed["items"][0]
    assert row["expected_count"] == 3
    assert row["graded_count"] == 2
    assert row["avg_percentage"] == 75.0


def test_unknown_assessment_is_404(client, as_instructor, seeded):
    assert client.get("/api/assessments/9999", headers=as_instructor).status_code == 404
    assert client.get("/api/assessments/9999/results", headers=as_instructor).status_code == 404
