"""Role-based access control, enforced server-side.

The table below is the contract: for each (role, endpoint) pair the API
must either allow the call or answer 403. These assertions are what make
the frontend's hidden buttons a convenience rather than the control.
"""

import pytest

from app.core.permissions import ROLE_PERMISSIONS, permissions_for

# (method, path, json body) -> set of roles that must be allowed
WRITE_ENDPOINTS = [
    (
        "POST",
        "/api/students",
        {
            "student_id": "RBAC001",
            "full_name": "RBAC Probe",
            "email": "rbac.probe@test.edu",
            "dept_id": 1,
            "semester": 3,
            "enrollment_year": 2024,
        },
        {"ADMIN"},
    ),
    (
        "POST",
        "/api/courses",
        {
            "course_code": "RBAC101",
            "course_name": "Access Control",
            "dept_id": 1,
            "semester": 3,
            "academic_term": "2025-ODD",
        },
        {"ADMIN"},
    ),
    (
        "POST",
        "/api/attendance",
        {"enrollment_id": 1, "session_date": "2025-01-10", "status": "PRESENT"},
        {"ADMIN", "INSTRUCTOR", "TA"},
    ),
    (
        "POST",
        "/api/activity",
        {"enrollment_id": 1, "activity_type": "LOGIN"},
        {"ADMIN", "TA"},
    ),
    (
        "POST",
        "/api/assessments",
        {
            "course_pk": 1,
            "title": "RBAC Quiz",
            "assessment_type": "QUIZ",
            "max_marks": 10,
            "due_at": "2025-02-01T17:00:00",
        },
        {"ADMIN", "INSTRUCTOR"},
    ),
    (
        "POST",
        "/api/assessment-results",
        {"assessment_id": 1, "enrollment_id": 1, "marks_obtained": 15},
        {"ADMIN", "INSTRUCTOR"},
    ),
    (
        "POST",
        "/api/risk-assessments/recalculate",
        {},
        {"ADMIN", "INSTRUCTOR"},
    ),
    (
        "POST",
        "/api/interventions",
        {
            "enrollment_id": 1,
            "intervention_type": "COUNSELING",
            "contact_date": "2025-01-15",
        },
        {"ADMIN", "INSTRUCTOR", "TA", "ADVISOR"},
    ),
    (
        "POST",
        "/api/auth/users",
        {
            "full_name": "RBAC New Staff",
            "email": "rbac.staff@test.edu",
            "password": "Password@123",
            "role": "TA",
        },
        {"ADMIN"},
    ),
    (
        "POST",
        "/api/enrollments",
        {"student_pk": 1, "course_pk": 2},
        {"ADMIN", "INSTRUCTOR"},
    ),
]

READ_ENDPOINTS = [
    "/api/students",
    "/api/courses",
    "/api/attendance",
    "/api/activity",
    "/api/assessments",
    "/api/risk-assessments",
    "/api/reports/risk-distribution",
    "/api/dashboard/summary",
]

ALL_ROLES = list(ROLE_PERMISSIONS)


def _headers(client, role):
    from tests.conftest import auth_headers

    return auth_headers(client, role)


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("path", READ_ENDPOINTS)
def test_every_role_can_read_the_core_pages(client, seeded, role, path):
    response = client.get(path, headers=_headers(client, role))
    assert response.status_code == 200, f"{role} GET {path} -> {response.text[:200]}"


@pytest.mark.parametrize(
    "method,path,body,allowed", WRITE_ENDPOINTS, ids=[e[1] for e in WRITE_ENDPOINTS]
)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_write_endpoints_match_the_permission_matrix(
    client, seeded, role, method, path, body, allowed
):
    headers = _headers(client, role)
    response = client.request(method, path, headers=headers, json=body)

    if role in allowed:
        assert response.status_code != 403, (
            f"{role} should be permitted to {method} {path} but got 403"
        )
    else:
        assert response.status_code == 403, (
            f"{role} must NOT be permitted to {method} {path}; got "
            f"{response.status_code} {response.text[:200]}"
        )
        assert response.json()["error_code"] == "forbidden"


def test_chair_has_no_write_permission_at_all():
    """The Department Chair is an oversight role: read-only by design."""
    granted = permissions_for("CHAIR")
    assert not [p for p in granted if p.endswith(":write")]
    assert "risk:recalculate" not in granted


def test_chair_cannot_change_an_alert(client, seeded, as_chair, db):
    from app.models import RiskAlert

    db.add(
        RiskAlert(
            alert_id=1,
            enrollment_id=1,
            risk_score=70,
            risk_category="HIGH",
            status="NEW",
        )
    )
    db.commit()
    response = client.patch(
        "/api/alerts/1", headers=as_chair, json={"status": "ACKNOWLEDGED"}
    )
    assert response.status_code == 403


def test_advisor_can_work_the_alert_queue(client, seeded, as_advisor, db):
    from app.models import RiskAlert

    db.add(
        RiskAlert(
            alert_id=1,
            enrollment_id=1,
            risk_score=70,
            risk_category="HIGH",
            status="NEW",
        )
    )
    db.commit()
    response = client.patch(
        "/api/alerts/1", headers=as_advisor, json={"status": "ACKNOWLEDGED"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACKNOWLEDGED"


def test_ta_cannot_enter_marks_but_can_record_attendance(client, seeded, as_ta):
    marks = client.post(
        "/api/assessment-results",
        headers=as_ta,
        json={"assessment_id": 1, "enrollment_id": 1, "marks_obtained": 15},
    )
    assert marks.status_code == 403

    attendance = client.post(
        "/api/attendance",
        headers=as_ta,
        json={"enrollment_id": 1, "session_date": "2025-01-10", "status": "PRESENT"},
    )
    assert attendance.status_code == 201


def test_unknown_role_is_granted_nothing():
    assert permissions_for("SOMETHING_ELSE") == frozenset()


def test_settings_are_administrator_only(client, seeded):
    for role in ("INSTRUCTOR", "TA", "ADVISOR", "CHAIR"):
        response = client.get("/api/settings", headers=_headers(client, role))
        assert response.status_code == 403, f"{role} should not read system settings"
    assert client.get("/api/settings", headers=_headers(client, "ADMIN")).status_code == 200
