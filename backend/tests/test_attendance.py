"""Attendance recording and the attendance-percentage calculation."""

from datetime import date, timedelta


def mark(client, headers, enrollment_id, days_ago, status, session_no=1):
    return client.post(
        "/api/attendance",
        headers=headers,
        json={
            "enrollment_id": enrollment_id,
            "session_date": (date.today() - timedelta(days=days_ago)).isoformat(),
            "session_no": session_no,
            "status": status,
        },
    )


def test_record_attendance(client, as_instructor, seeded):
    response = mark(client, as_instructor, 1, 1, "PRESENT")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PRESENT"
    assert body["student_id"] == "MTH2024001"
    assert body["course_code"] == "MTH201"
    assert body["recorded_by_name"] == "Instructor User"


def test_re_recording_the_same_session_corrects_it_rather_than_duplicating(
    client, as_instructor, seeded
):
    """``uq_attendance_session`` makes a second row impossible, so the
    endpoint is an idempotent upsert."""
    first = mark(client, as_instructor, 1, 1, "ABSENT")
    second = mark(client, as_instructor, 1, 1, "PRESENT")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["attendance_id"] == second.json()["attendance_id"]
    assert second.json()["status"] == "PRESENT"

    listed = client.get("/api/attendance?enrollment_id=1", headers=as_instructor)
    assert listed.json()["total"] == 1


def test_two_sessions_on_the_same_day_are_distinct(client, as_instructor, seeded):
    mark(client, as_instructor, 1, 1, "PRESENT", session_no=1)
    mark(client, as_instructor, 1, 1, "ABSENT", session_no=2)
    assert client.get("/api/attendance?enrollment_id=1", headers=as_instructor).json()["total"] == 2


def test_future_session_date_is_rejected(client, as_instructor, seeded):
    response = client.post(
        "/api/attendance",
        headers=as_instructor,
        json={
            "enrollment_id": 1,
            "session_date": (date.today() + timedelta(days=1)).isoformat(),
            "status": "PRESENT",
        },
    )
    assert response.status_code == 422
    assert "future" in response.text


def test_invalid_status_is_rejected(client, as_instructor, seeded):
    response = client.post(
        "/api/attendance",
        headers=as_instructor,
        json={
            "enrollment_id": 1,
            "session_date": date.today().isoformat(),
            "status": "MAYBE",
        },
    )
    assert response.status_code == 422


def test_unknown_enrolment_is_rejected(client, as_instructor, seeded):
    response = mark(client, as_instructor, 9999, 1, "PRESENT")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The percentage calculation
# ---------------------------------------------------------------------------
def test_attendance_percentage_counts_present_and_late_as_attended(
    client, as_instructor, seeded
):
    for day, status in enumerate(["PRESENT", "PRESENT", "LATE", "ABSENT"], start=1):
        mark(client, as_instructor, 1, day, status)

    summary = client.get("/api/attendance/summary?course_pk=1", headers=as_instructor).json()
    row = next(r for r in summary if r["enrollment_id"] == 1)
    assert row["sessions_held"] == 4
    assert row["sessions_attended"] == 3  # LATE counts as attended
    assert row["sessions_late"] == 1
    assert row["sessions_absent"] == 1
    assert row["attendance_percentage"] == 75.0


def test_excused_absences_leave_the_denominator(client, as_instructor, seeded):
    """An authorised absence must not depress attendance."""
    for day, status in enumerate(["PRESENT", "PRESENT", "PRESENT", "EXCUSED"], start=1):
        mark(client, as_instructor, 1, day, status)

    summary = client.get("/api/attendance/summary?course_pk=1", headers=as_instructor).json()
    row = next(r for r in summary if r["enrollment_id"] == 1)
    assert row["sessions_excused"] == 1
    assert row["sessions_held"] == 3, "the excused session is excluded from the total"
    assert row["attendance_percentage"] == 100.0


def test_percentage_is_null_when_nothing_has_been_recorded(client, as_instructor, seeded):
    summary = client.get("/api/attendance/summary?course_pk=1", headers=as_instructor).json()
    row = next(r for r in summary if r["enrollment_id"] == 1)
    assert row["sessions_held"] == 0
    assert row["attendance_percentage"] is None, "no data must not read as 0%"


def test_all_absent_is_zero_percent(client, as_instructor, seeded):
    for day in range(1, 4):
        mark(client, as_instructor, 1, day, "ABSENT")
    summary = client.get("/api/attendance/summary?course_pk=1", headers=as_instructor).json()
    row = next(r for r in summary if r["enrollment_id"] == 1)
    assert row["attendance_percentage"] == 0.0


def test_percentage_is_rounded_to_two_decimals(client, as_instructor, seeded):
    # 2 of 3 -> 66.666... -> 66.67
    for day, status in enumerate(["PRESENT", "PRESENT", "ABSENT"], start=1):
        mark(client, as_instructor, 1, day, status)
    summary = client.get("/api/attendance/summary?course_pk=1", headers=as_instructor).json()
    row = next(r for r in summary if r["enrollment_id"] == 1)
    assert row["attendance_percentage"] == 66.67


# ---------------------------------------------------------------------------
# Bulk roster marking
# ---------------------------------------------------------------------------
def test_bulk_marks_a_whole_session(client, as_ta, seeded):
    response = client.post(
        "/api/attendance/bulk",
        headers=as_ta,
        json={
            "course_pk": 1,
            "session_date": date.today().isoformat(),
            "session_no": 1,
            "rows": [
                {"enrollment_id": 1, "status": "PRESENT"},
                {"enrollment_id": 2, "status": "ABSENT"},
                {"enrollment_id": 3, "status": "LATE"},
            ],
        },
    )
    assert response.status_code == 200
    assert "3 record(s) added" in response.json()["detail"]
    assert client.get("/api/attendance?course_pk=1", headers=as_ta).json()["total"] == 3


def test_bulk_rerun_corrects_rather_than_duplicates(client, as_ta, seeded):
    payload = {
        "course_pk": 1,
        "session_date": date.today().isoformat(),
        "session_no": 1,
        "rows": [{"enrollment_id": 1, "status": "ABSENT"}],
    }
    client.post("/api/attendance/bulk", headers=as_ta, json=payload)
    payload["rows"] = [{"enrollment_id": 1, "status": "PRESENT"}]
    second = client.post("/api/attendance/bulk", headers=as_ta, json=payload)
    assert "1 corrected" in second.json()["detail"]
    assert client.get("/api/attendance?course_pk=1", headers=as_ta).json()["total"] == 1


def test_bulk_rejects_an_enrolment_from_another_course(client, as_ta, seeded, db):
    """A roster check stops data being written against the wrong course."""
    from app.models import Enrollment

    db.add(
        Enrollment(
            enrollment_id=99,
            student_pk=1,
            course_pk=seeded.course_b.course_pk,
            enrolled_on=date.today(),
            status="ACTIVE",
        )
    )
    db.commit()

    response = client.post(
        "/api/attendance/bulk",
        headers=as_ta,
        json={
            "course_pk": 1,
            "session_date": date.today().isoformat(),
            "rows": [{"enrollment_id": 99, "status": "PRESENT"}],
        },
    )
    assert response.status_code == 422
    assert "not on this course's active roster" in response.json()["detail"]


def test_delete_an_attendance_record(client, as_instructor, seeded):
    created = mark(client, as_instructor, 1, 1, "PRESENT")
    attendance_id = created.json()["attendance_id"]
    assert client.delete(f"/api/attendance/{attendance_id}", headers=as_instructor).status_code == 200
    assert client.get("/api/attendance?enrollment_id=1", headers=as_instructor).json()["total"] == 0


def test_filter_attendance_by_date_window_and_status(client, as_instructor, seeded):
    mark(client, as_instructor, 1, 10, "ABSENT")
    mark(client, as_instructor, 1, 2, "PRESENT")

    recent = (date.today() - timedelta(days=5)).isoformat()
    assert (
        client.get(f"/api/attendance?date_from={recent}", headers=as_instructor).json()["total"] == 1
    )
    assert (
        client.get("/api/attendance?attendance_status=ABSENT", headers=as_instructor).json()["total"]
        == 1
    )
