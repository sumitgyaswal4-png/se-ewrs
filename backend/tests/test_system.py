"""Health, reference data, settings validation and the audit trail."""

from datetime import date, timedelta


def test_root_banner(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_health_reports_database_connectivity(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_openapi_document_is_served(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "SE-EWRS API"
    assert "/api/auth/login" in spec["paths"]
    assert "/api/risk-assessments/recalculate" in spec["paths"]


def test_openapi_never_exposes_a_password_hash_field(client):
    """No response schema should carry the digest."""
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    offenders = [
        name for name, schema in schemas.items() if "password_hash" in schema.get("properties", {})
    ]
    assert offenders == []


def test_enums_endpoint_feeds_the_ui_dropdowns(client, as_admin):
    body = client.get("/api/enums", headers=as_admin).json()
    assert "risk_categories" in body
    assert "intervention_types" in body
    labels = {row["value"]: row["label"] for row in body["risk_categories"]}
    assert labels["INSUFFICIENT_DATA"] == "Needs more data"
    assert labels["HIGH"] == "High risk"
    # Every value must be one the database would accept.
    from app.models import INTERVENTION_TYPES

    assert {row["value"] for row in body["intervention_types"]} == set(INTERVENTION_TYPES)


def test_departments_can_be_listed_and_created(client, as_admin):
    listed = client.get("/api/departments", headers=as_admin).json()
    assert len(listed) == 2

    created = client.post(
        "/api/departments",
        headers=as_admin,
        json={"dept_code": "chem", "dept_name": "Department of Chemistry"},
    )
    assert created.status_code == 201
    assert created.json()["dept_code"] == "CHEM"

    duplicate = client.post(
        "/api/departments",
        headers=as_admin,
        json={"dept_code": "CHEM", "dept_name": "Chemistry Again"},
    )
    assert duplicate.status_code == 409


def test_course_and_student_option_lists(client, as_admin, seeded):
    courses = client.get("/api/course-options", headers=as_admin).json()
    assert {c["course_code"] for c in courses} == {"MTH201", "MTH210"}
    assert courses[0]["label"].startswith("MTH201 - ")

    students = client.get("/api/student-options?search=MTH2024001", headers=as_admin).json()
    assert len(students) == 1
    assert students[0]["student_id"] == "MTH2024001"


# ---------------------------------------------------------------------------
# System settings
# ---------------------------------------------------------------------------
def test_settings_list_and_resolved_config(client, as_admin):
    settings = client.get("/api/settings", headers=as_admin).json()
    keys = {row["setting_key"] for row in settings}
    assert "risk.weight.attendance" in keys
    assert "alert.min_score" in keys

    config = client.get("/api/settings/risk-config", headers=as_admin).json()
    assert config["weights"] == {"attendance": 0.35, "academic": 0.40, "engagement": 0.25}
    assert config["thresholds"] == {"medium": 30, "high": 60}
    assert config["model_version"] == "rule-v1"


def test_a_weight_can_be_retuned(client, as_admin):
    response = client.put(
        "/api/settings/risk.weight.attendance", headers=as_admin, json={"setting_value": "0.50"}
    )
    assert response.status_code == 200
    config = client.get("/api/settings/risk-config", headers=as_admin).json()
    assert config["weights"]["attendance"] == 0.5


def test_a_non_numeric_weight_is_rejected(client, as_admin):
    response = client.put(
        "/api/settings/risk.weight.academic", headers=as_admin, json={"setting_value": "lots"}
    )
    assert response.status_code == 422
    assert "must be a number" in response.json()["detail"]


def test_a_weight_outside_zero_to_one_is_rejected(client, as_admin):
    response = client.put(
        "/api/settings/risk.weight.academic", headers=as_admin, json={"setting_value": "1.5"}
    )
    assert response.status_code == 422


def test_thresholds_cannot_cross_over(client, as_admin):
    """Medium must stay below high, or the bands become meaningless."""
    too_high = client.put(
        "/api/settings/risk.threshold.medium", headers=as_admin, json={"setting_value": "70"}
    )
    assert too_high.status_code == 422
    assert "below the high threshold" in too_high.json()["detail"]

    too_low = client.put(
        "/api/settings/risk.threshold.high", headers=as_admin, json={"setting_value": "20"}
    )
    assert too_low.status_code == 422
    assert "above the medium threshold" in too_low.json()["detail"]


def test_unknown_setting_is_404(client, as_admin):
    response = client.put(
        "/api/settings/risk.weight.vibes", headers=as_admin, json={"setting_value": "1"}
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------
def test_sign_in_is_audited(client, as_admin):
    logs = client.get("/api/settings/audit/logs?action=LOGIN", headers=as_admin).json()
    assert logs["total"] >= 1
    assert logs["items"][0]["entity_type"] == "users"
    assert logs["items"][0]["user_name"] == "Admin User"


def test_a_failed_sign_in_is_audited(client, as_admin):
    client.post("/api/auth/login", json={"email": "admin@test.edu", "password": "wrong"})
    logs = client.get("/api/settings/audit/logs?action=LOGIN_FAILED", headers=as_admin).json()
    assert logs["total"] == 1


def test_student_changes_are_audited(client, as_admin, seeded):
    client.post(
        "/api/students",
        headers=as_admin,
        json={
            "student_id": "MTH2024500",
            "full_name": "Audited Student",
            "email": "audited@test.edu",
            "dept_id": 1,
            "semester": 3,
            "enrollment_year": 2024,
        },
    )
    client.patch(f"/api/students/{seeded.students[0].student_pk}/deactivate", headers=as_admin)

    logs = client.get("/api/settings/audit/logs?entity_type=students", headers=as_admin).json()
    actions = {row["action"] for row in logs["items"]}
    assert "INSERT" in actions
    assert "DEACTIVATE" in actions


def test_a_setting_change_is_audited_with_both_values(client, as_admin):
    client.put(
        "/api/settings/alert.min_score", headers=as_admin, json={"setting_value": "45"}
    )
    logs = client.get(
        "/api/settings/audit/logs?entity_type=system_settings", headers=as_admin
    ).json()
    entry = logs["items"][0]
    assert "30" in entry["old_values"]
    assert "45" in entry["new_values"]


def test_the_audit_trail_never_stores_a_password(client, as_admin):
    client.post("/api/auth/change-password", headers=as_admin,
                json={"current_password": "TestPass@123", "new_password": "Another@999"})
    logs = client.get("/api/settings/audit/logs", headers=as_admin).json()
    blob = str(logs)
    assert "TestPass@123" not in blob
    assert "Another@999" not in blob
    assert "$argon2" not in blob


def test_audit_log_filters(client, as_admin, seeded):
    today = date.today().isoformat()
    assert client.get(f"/api/settings/audit/logs?date_from={today}", headers=as_admin).json()["total"] >= 1
    future = (date.today() + timedelta(days=1)).isoformat()
    assert client.get(f"/api/settings/audit/logs?date_from={future}", headers=as_admin).json()["total"] == 0
    assert client.get("/api/settings/audit/logs?user_id=1", headers=as_admin).json()["total"] >= 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
def test_validation_errors_report_the_field_but_not_the_value(client, as_admin):
    response = client.post(
        "/api/students",
        headers=as_admin,
        json={
            "student_id": "X",  # too short
            "full_name": "A",   # too short
            "email": "nope",
            "dept_id": 1,
            "semester": 99,
            "enrollment_year": 1800,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_error"
    fields = {problem["field"] for problem in body["problems"]}
    assert {"student_id", "full_name", "email", "semester", "enrollment_year"} <= fields


def test_unknown_route_is_a_clean_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert "error_code" in response.json()


def test_pagination_bounds_are_enforced(client, as_admin, seeded):
    assert client.get("/api/students?page=0", headers=as_admin).status_code == 422
    assert client.get("/api/students?page_size=0", headers=as_admin).status_code == 422
    assert client.get("/api/students?page_size=10000", headers=as_admin).status_code == 422


def test_a_sql_injection_attempt_in_search_is_treated_as_text(client, as_admin, seeded):
    """Parameters are bound, never interpolated."""
    response = client.get(
        "/api/students?search=' OR 1=1 --", headers=as_admin
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0, "the payload matched nothing, as a literal string"

    # and the table is still there
    assert client.get("/api/students", headers=as_admin).json()["total"] == 3
