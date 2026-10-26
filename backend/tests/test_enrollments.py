"""Enrolment validation -- above all, duplicate prevention."""


def test_enrol_a_student(client, as_admin, seeded):
    response = client.post(
        "/api/enrollments",
        headers=as_admin,
        json={"student_pk": 1, "course_pk": seeded.course_b.course_pk},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["student_id"] == "MTH2024001"
    assert body["course_code"] == "MTH210"


def test_duplicate_enrolment_is_rejected_with_a_readable_message(client, as_admin, seeded):
    """Students 1-3 are already on MTH201 from the fixture."""
    response = client.post(
        "/api/enrollments", headers=as_admin, json={"student_pk": 1, "course_pk": 1}
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "conflict"
    assert "already enrolled" in response.json()["detail"]


def test_duplicate_is_blocked_even_across_two_requests(client, as_admin, seeded):
    course_pk = seeded.course_b.course_pk
    first = client.post(
        "/api/enrollments", headers=as_admin, json={"student_pk": 2, "course_pk": course_pk}
    )
    second = client.post(
        "/api/enrollments", headers=as_admin, json={"student_pk": 2, "course_pk": course_pk}
    )
    assert first.status_code == 201
    assert second.status_code == 409


def test_unknown_student_is_rejected(client, as_admin, seeded):
    response = client.post(
        "/api/enrollments", headers=as_admin, json={"student_pk": 9999, "course_pk": 1}
    )
    assert response.status_code == 422
    assert "Student 9999" in response.json()["detail"]


def test_unknown_course_is_rejected(client, as_admin, seeded):
    response = client.post(
        "/api/enrollments", headers=as_admin, json={"student_pk": 1, "course_pk": 9999}
    )
    assert response.status_code == 422


def test_inactive_student_cannot_be_enrolled(client, as_admin, seeded, db):
    seeded.students[0].is_active = False
    db.commit()
    response = client.post(
        "/api/enrollments",
        headers=as_admin,
        json={"student_pk": 1, "course_pk": seeded.course_b.course_pk},
    )
    assert response.status_code == 422
    assert "inactive" in response.json()["detail"]


def test_inactive_course_cannot_take_enrolments(client, as_admin, seeded, db):
    seeded.course_b.is_active = False
    db.commit()
    response = client.post(
        "/api/enrollments",
        headers=as_admin,
        json={"student_pk": 1, "course_pk": seeded.course_b.course_pk},
    )
    assert response.status_code == 422


def test_bulk_enrol_reports_duplicates_instead_of_failing(client, as_admin, seeded):
    """Students 1 and 2 are already on MTH201; 3 is too. Re-running the
    batch must skip all three rather than abort."""
    response = client.post(
        "/api/enrollments/bulk",
        headers=as_admin,
        json={"course_pk": 1, "student_pks": [1, 2, 3]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enrolled"] == []
    assert sorted(body["skipped_duplicates"]) == [1, 2, 3]


def test_bulk_enrol_mixes_new_and_duplicate_rows(client, as_admin, seeded):
    course_pk = seeded.course_b.course_pk
    client.post(
        "/api/enrollments", headers=as_admin, json={"student_pk": 1, "course_pk": course_pk}
    )
    response = client.post(
        "/api/enrollments/bulk",
        headers=as_admin,
        json={"course_pk": course_pk, "student_pks": [1, 2, 3]},
    )
    body = response.json()
    assert len(body["enrolled"]) == 2
    assert body["skipped_duplicates"] == [1]


def test_bulk_enrol_deduplicates_the_request_itself(client, as_admin, seeded):
    response = client.post(
        "/api/enrollments/bulk",
        headers=as_admin,
        json={"course_pk": seeded.course_b.course_pk, "student_pks": [1, 1, 1]},
    )
    assert response.status_code == 200
    assert len(response.json()["enrolled"]) == 1


def test_bulk_enrol_rejects_the_whole_batch_on_an_unknown_student(client, as_admin, seeded):
    response = client.post(
        "/api/enrollments/bulk",
        headers=as_admin,
        json={"course_pk": seeded.course_b.course_pk, "student_pks": [1, 9999]},
    )
    assert response.status_code == 422
    assert "9999" in response.json()["detail"]
    # nothing was written
    listed = client.get(
        f"/api/enrollments?course_pk={seeded.course_b.course_pk}", headers=as_admin
    )
    assert listed.json()["total"] == 0


def test_empty_bulk_request_is_rejected(client, as_admin, seeded):
    response = client.post(
        "/api/enrollments/bulk", headers=as_admin, json={"course_pk": 1, "student_pks": []}
    )
    assert response.status_code == 422


def test_change_an_enrolment_status(client, as_admin, seeded):
    response = client.patch("/api/enrollments/1", headers=as_admin, json={"status": "DROPPED"})
    assert response.status_code == 200
    assert response.json()["status"] == "DROPPED"


def test_invalid_status_is_rejected(client, as_admin, seeded):
    response = client.patch("/api/enrollments/1", headers=as_admin, json={"status": "PAUSED"})
    assert response.status_code == 422


def test_dropped_students_leave_the_active_roster(client, as_admin, seeded):
    client.patch("/api/enrollments/1", headers=as_admin, json={"status": "DROPPED"})
    roster = client.get("/api/courses/1/roster", headers=as_admin).json()
    assert len(roster) == 2


def test_list_and_filter_enrolments(client, as_admin, seeded):
    assert client.get("/api/enrollments", headers=as_admin).json()["total"] == 3
    assert client.get("/api/enrollments?course_pk=1", headers=as_admin).json()["total"] == 3
    assert client.get("/api/enrollments?student_pk=1", headers=as_admin).json()["total"] == 1
    assert (
        client.get("/api/enrollments?enrollment_status=DROPPED", headers=as_admin).json()["total"]
        == 0
    )
