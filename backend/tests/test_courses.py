"""Course catalogue, instructor assignment and rosters."""


def new_course(**overrides) -> dict:
    payload = {
        "course_code": "MTH305",
        "course_name": "Real Analysis",
        "dept_id": 1,
        "semester": 5,
        "credits": 4,
        "academic_term": "2025-ODD",
        "total_sessions": 22,
    }
    payload.update(overrides)
    return payload


def test_create_and_fetch_a_course(client, as_admin):
    created = client.post("/api/courses", headers=as_admin, json=new_course())
    assert created.status_code == 201
    body = created.json()
    assert body["course_code"] == "MTH305"
    assert body["dept_code"] == "MATH"
    assert body["enrolled_count"] == 0

    fetched = client.get(f"/api/courses/{body['course_pk']}", headers=as_admin)
    assert fetched.status_code == 200
    assert fetched.json()["course_name"] == "Real Analysis"


def test_course_code_is_upper_cased(client, as_admin):
    response = client.post("/api/courses", headers=as_admin, json=new_course(course_code="mth306"))
    assert response.json()["course_code"] == "MTH306"


def test_same_code_in_the_same_term_is_rejected(client, as_admin):
    assert client.post("/api/courses", headers=as_admin, json=new_course()).status_code == 201
    duplicate = client.post("/api/courses", headers=as_admin, json=new_course())
    assert duplicate.status_code == 409


def test_same_code_in_a_different_term_is_allowed(client, as_admin):
    """``uq_courses_code_term`` is composite, so a course can run again."""
    assert client.post("/api/courses", headers=as_admin, json=new_course()).status_code == 201
    next_year = client.post(
        "/api/courses", headers=as_admin, json=new_course(academic_term="2026-ODD")
    )
    assert next_year.status_code == 201


def test_unknown_department_is_rejected(client, as_admin):
    response = client.post("/api/courses", headers=as_admin, json=new_course(dept_id=99))
    assert response.status_code == 422


def test_credits_out_of_range_is_rejected(client, as_admin):
    assert client.post(
        "/api/courses", headers=as_admin, json=new_course(credits=0)
    ).status_code == 422
    assert client.post(
        "/api/courses", headers=as_admin, json=new_course(credits=11)
    ).status_code == 422


def test_create_with_instructors_attached(client, as_admin, seeded):
    response = client.post(
        "/api/courses",
        headers=as_admin,
        json=new_course(course_code="MTH307", instructor_ids=[2]),
    )
    assert response.status_code == 201
    instructors = response.json()["instructors"]
    assert len(instructors) == 1
    assert instructors[0]["user_id"] == 2
    assert instructors[0]["role_in_course"] == "PRIMARY"


def test_update_a_course(client, as_admin, seeded):
    response = client.put(
        f"/api/courses/{seeded.course.course_pk}",
        headers=as_admin,
        json={"course_name": "Linear Algebra II", "credits": 3},
    )
    assert response.status_code == 200
    assert response.json()["course_name"] == "Linear Algebra II"
    assert response.json()["credits"] == 3


def test_deactivating_a_course_hides_it_from_the_active_filter(client, as_admin, seeded):
    client.put(
        f"/api/courses/{seeded.course.course_pk}", headers=as_admin, json={"is_active": False}
    )
    active = client.get("/api/courses?is_active=true", headers=as_admin)
    assert all(c["course_pk"] != seeded.course.course_pk for c in active.json()["items"])


def test_assign_and_remove_an_instructor(client, as_admin, seeded):
    course_pk = seeded.course_b.course_pk
    assigned = client.post(
        f"/api/courses/{course_pk}/instructors",
        headers=as_admin,
        json={"user_id": 2, "role_in_course": "PRIMARY"},
    )
    assert assigned.status_code == 200
    assert len(client.get(f"/api/courses/{course_pk}", headers=as_admin).json()["instructors"]) == 1

    removed = client.delete(f"/api/courses/{course_pk}/instructors/2", headers=as_admin)
    assert removed.status_code == 200
    assert client.get(f"/api/courses/{course_pk}", headers=as_admin).json()["instructors"] == []


def test_assigning_the_same_instructor_twice_is_rejected(client, as_admin, seeded):
    course_pk = seeded.course_b.course_pk
    client.post(
        f"/api/courses/{course_pk}/instructors", headers=as_admin, json={"user_id": 2}
    )
    again = client.post(
        f"/api/courses/{course_pk}/instructors", headers=as_admin, json={"user_id": 2}
    )
    assert again.status_code == 409


def test_a_chair_cannot_be_assigned_to_teach(client, as_admin, seeded):
    """Only INSTRUCTOR, TA and ADMIN may hold a course assignment."""
    response = client.post(
        f"/api/courses/{seeded.course_b.course_pk}/instructors",
        headers=as_admin,
        json={"user_id": seeded.users["CHAIR"].user_id},
    )
    assert response.status_code == 422
    assert "cannot be assigned" in response.json()["detail"]


def test_removing_an_unassigned_instructor_is_404(client, as_admin, seeded):
    response = client.delete(
        f"/api/courses/{seeded.course_b.course_pk}/instructors/2", headers=as_admin
    )
    assert response.status_code == 404


def test_roster_lists_the_active_enrolments(client, as_admin, seeded):
    response = client.get(f"/api/courses/{seeded.course.course_pk}/roster", headers=as_admin)
    assert response.status_code == 200
    roster = response.json()
    assert len(roster) == 3
    assert {row["student_id"] for row in roster} == {
        "MTH2024001", "MTH2024002", "MTH2024003"
    }


def test_roster_of_unknown_course_is_404(client, as_admin):
    assert client.get("/api/courses/9999/roster", headers=as_admin).status_code == 404


def test_course_list_reports_the_enrolled_count(client, as_admin, seeded):
    response = client.get("/api/courses", headers=as_admin)
    by_code = {c["course_code"]: c for c in response.json()["items"]}
    assert by_code["MTH201"]["enrolled_count"] == 3
    assert by_code["MTH210"]["enrolled_count"] == 0


def test_search_and_filter_courses(client, as_admin):
    assert client.get("/api/courses?search=Linear", headers=as_admin).json()["total"] == 1
    assert client.get("/api/courses?semester=3", headers=as_admin).json()["total"] == 2
    assert client.get("/api/courses?dept_id=2", headers=as_admin).json()["total"] == 0
