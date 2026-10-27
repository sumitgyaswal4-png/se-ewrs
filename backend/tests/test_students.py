"""Student CRUD, search, filtering, de-activation and the profile view."""


def new_student(**overrides) -> dict:
    payload = {
        "student_id": "MTH2024900",
        "full_name": "Nadia Farooq",
        "email": "nadia.farooq@test.edu",
        "dept_id": 1,
        "semester": 3,
        "enrollment_year": 2024,
    }
    payload.update(overrides)
    return payload


def test_create_and_fetch_a_student(client, as_admin):
    created = client.post("/api/students", headers=as_admin, json=new_student())
    assert created.status_code == 201
    body = created.json()
    assert body["student_id"] == "MTH2024900"
    assert body["dept_code"] == "MATH"
    assert body["is_active"] is True

    fetched = client.get(f"/api/students/{body['student_pk']}", headers=as_admin)
    assert fetched.status_code == 200
    assert fetched.json()["full_name"] == "Nadia Farooq"


def test_roll_number_is_upper_cased_and_trimmed(client, as_admin):
    response = client.post(
        "/api/students", headers=as_admin, json=new_student(student_id="  mth2024901  ")
    )
    assert response.status_code == 201
    assert response.json()["student_id"] == "MTH2024901"


def test_duplicate_roll_number_is_rejected(client, as_admin):
    assert client.post("/api/students", headers=as_admin, json=new_student()).status_code == 201
    duplicate = client.post(
        "/api/students", headers=as_admin, json=new_student(email="other@test.edu")
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error_code"] == "conflict"


def test_duplicate_email_is_rejected(client, as_admin):
    assert client.post("/api/students", headers=as_admin, json=new_student()).status_code == 201
    duplicate = client.post(
        "/api/students", headers=as_admin, json=new_student(student_id="MTH2024902")
    )
    assert duplicate.status_code == 409


def test_unknown_department_is_rejected(client, as_admin):
    response = client.post("/api/students", headers=as_admin, json=new_student(dept_id=999))
    assert response.status_code == 422
    assert "Department 999" in response.json()["detail"]


def test_semester_out_of_range_is_rejected(client, as_admin):
    assert client.post(
        "/api/students", headers=as_admin, json=new_student(semester=0)
    ).status_code == 422
    assert client.post(
        "/api/students", headers=as_admin, json=new_student(semester=13)
    ).status_code == 422


def test_list_is_paginated(client, as_admin):
    response = client.get("/api/students?page=1&page_size=2", headers=as_admin)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["pages"] == 2
    assert body["page"] == 1

    page_two = client.get("/api/students?page=2&page_size=2", headers=as_admin)
    assert len(page_two.json()["items"]) == 1


def test_search_matches_roll_number_name_and_email(client, as_admin, seeded):
    by_roll = client.get("/api/students?search=MTH2024001", headers=as_admin)
    assert by_roll.json()["total"] == 1

    by_name = client.get("/api/students?search=Student 2", headers=as_admin)
    assert by_name.json()["total"] == 1

    by_email = client.get("/api/students?search=student3@test.edu", headers=as_admin)
    assert by_email.json()["total"] == 1

    no_match = client.get("/api/students?search=zzzz-nobody", headers=as_admin)
    assert no_match.json()["total"] == 0
    assert no_match.json()["items"] == []


def test_filter_by_department_and_semester(client, as_admin):
    assert client.get("/api/students?dept_id=1", headers=as_admin).json()["total"] == 3
    assert client.get("/api/students?dept_id=2", headers=as_admin).json()["total"] == 0
    assert client.get("/api/students?semester=3", headers=as_admin).json()["total"] == 3
    assert client.get("/api/students?semester=5", headers=as_admin).json()["total"] == 0


def test_sorting_is_applied(client, as_admin):
    ascending = client.get("/api/students?sort_by=student_id&sort_dir=asc", headers=as_admin)
    descending = client.get("/api/students?sort_by=student_id&sort_dir=desc", headers=as_admin)
    first_asc = ascending.json()["items"][0]["student_id"]
    first_desc = descending.json()["items"][0]["student_id"]
    assert first_asc == "MTH2024001"
    assert first_desc == "MTH2024003"


def test_unknown_sort_column_is_rejected(client, as_admin):
    response = client.get("/api/students?sort_by=; DROP TABLE students", headers=as_admin)
    assert response.status_code == 422
    assert "sort_by must be one of" in response.json()["detail"]


def test_update_a_student(client, as_admin, seeded):
    pk = seeded.students[0].student_pk
    response = client.put(
        f"/api/students/{pk}",
        headers=as_admin,
        json={"full_name": "Renamed Student", "semester": 5},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Renamed Student"
    assert response.json()["semester"] == 5


def test_update_cannot_take_another_students_email(client, as_admin, seeded):
    response = client.put(
        f"/api/students/{seeded.students[0].student_pk}",
        headers=as_admin,
        json={"email": "student2@test.edu"},
    )
    assert response.status_code == 409


def test_update_unknown_student_is_404(client, as_admin):
    response = client.put("/api/students/9999", headers=as_admin, json={"semester": 4})
    assert response.status_code == 404


def test_deactivate_is_a_soft_delete_that_keeps_the_record(client, as_admin, seeded):
    pk = seeded.students[0].student_pk
    response = client.patch(f"/api/students/{pk}/deactivate", headers=as_admin)
    assert response.status_code == 200

    # still retrievable -- history must survive
    fetched = client.get(f"/api/students/{pk}", headers=as_admin)
    assert fetched.status_code == 200
    assert fetched.json()["is_active"] is False

    assert client.get("/api/students?is_active=true", headers=as_admin).json()["total"] == 2
    assert client.get("/api/students?is_active=false", headers=as_admin).json()["total"] == 1


def test_deactivating_twice_is_harmless(client, as_admin, seeded):
    pk = seeded.students[0].student_pk
    client.patch(f"/api/students/{pk}/deactivate", headers=as_admin)
    second = client.patch(f"/api/students/{pk}/deactivate", headers=as_admin)
    assert second.status_code == 200
    assert "already inactive" in second.json()["detail"]


def test_reactivate_restores_the_student(client, as_admin, seeded):
    pk = seeded.students[0].student_pk
    client.patch(f"/api/students/{pk}/deactivate", headers=as_admin)
    client.patch(f"/api/students/{pk}/reactivate", headers=as_admin)
    assert client.get(f"/api/students/{pk}", headers=as_admin).json()["is_active"] is True


def test_profile_lists_each_enrolled_course(client, as_admin, seeded):
    pk = seeded.students[0].student_pk
    response = client.get(f"/api/students/{pk}/profile", headers=as_admin)
    assert response.status_code == 200
    body = response.json()
    assert body["student"]["student_pk"] == pk
    assert len(body["courses"]) == 1
    assert body["courses"][0]["course_code"] == "MTH201"
    assert body["summary"]["enrolled_courses"] == 1


def test_profile_of_unknown_student_is_404(client, as_admin):
    assert client.get("/api/students/9999/profile", headers=as_admin).status_code == 404


def test_list_includes_an_aggregated_summary_per_student(client, as_admin, seeded, db):
    from datetime import date, timedelta

    from app.models import AttendanceRecord

    for index in range(4):
        db.add(
            AttendanceRecord(
                enrollment_id=1,
                session_date=date.today() - timedelta(days=index),
                session_no=1,
                status="PRESENT" if index < 3 else "ABSENT",
            )
        )
    db.commit()

    response = client.get("/api/students?search=MTH2024001", headers=as_admin)
    summary = response.json()["items"][0]["summary"]
    assert summary["enrolled_courses"] == 1
    assert summary["attendance_percentage"] == 75.0


def test_profile_keeps_a_stored_zero_instead_of_falling_back_to_live(
    client, as_admin, seeded, db
):
    """A stored 0% must not be mistaken for "no stored value".

    The profile shows the snapshot the risk run recorded and falls back to
    a live figure only when there is no snapshot. 0.0 is a snapshot - and
    it belongs to exactly the student this system exists to catch - so it
    must survive. Guarding the fallback with `or` instead of an explicit
    None check silently replaced it with the live number, which also made
    the profile disagree with the risk detail page for the same enrolment.
    """
    from datetime import date, timedelta

    from app.models import AttendanceRecord, RiskAssessment

    enrollment = seeded.enrollments[0]

    # Live attendance is clearly non-zero: two sessions, both attended.
    for index in range(2):
        db.add(
            AttendanceRecord(
                enrollment_id=enrollment.enrollment_id,
                session_date=date.today() - timedelta(days=index + 1),
                session_no=index + 1,
                status="PRESENT",
                recorded_by=2,
            )
        )

    # The stored snapshot says 0% for both figures.
    db.add(
        RiskAssessment(
            enrollment_id=enrollment.enrollment_id,
            risk_score=100,
            risk_category="HIGH",
            data_completeness="COMPLETE",
            attendance_percentage=0,
            avg_assessment_percentage=0,
            engagement_score=0,
            attendance_risk=100,
            academic_risk=100,
            engagement_risk=100,
            model_version="rule-v1",
        )
    )
    db.commit()

    body = client.get(
        f"/api/students/{enrollment.student_pk}/profile", headers=as_admin
    ).json()
    row = next(
        course
        for course in body["courses"]
        if course["enrollment_id"] == enrollment.enrollment_id
    )

    assert row["attendance_percentage"] == 0.0, "stored 0% was replaced by the live figure"
    assert row["avg_assessment_percentage"] == 0.0
