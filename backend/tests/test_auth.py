"""Authentication: sign-in, token handling and password hygiene."""

from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from tests.conftest import ROLE_EMAILS, TEST_PASSWORD


def test_login_returns_token_user_and_permissions(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "admin@test.edu"
    assert body["user"]["role"] == "ADMIN"
    assert "students:write" in body["permissions"]
    assert body["home_route"] == "/dashboard"


def test_login_is_case_insensitive_on_email(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "ADMIN@TEST.EDU", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200


def test_login_response_never_includes_the_password_hash(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD}
    )
    assert "password_hash" not in response.text
    assert "$argon2" not in response.text


def test_wrong_password_is_rejected_with_a_generic_message(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": "not-the-password"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_unknown_email_gives_the_same_message_as_a_wrong_password(client, seeded):
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@test.edu", "password": TEST_PASSWORD}
    )
    wrong = client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": "wrong"}
    )
    assert unknown.status_code == wrong.status_code == 401
    # Identical wording, so the endpoint cannot be used to enumerate accounts.
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_deactivated_account_cannot_sign_in(client, seeded, db):
    seeded.users["TA"].is_active = False
    db.commit()
    response = client.post(
        "/api/auth/login", json={"email": "ta@test.edu", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert "deactivated" in response.json()["detail"].lower()


def test_malformed_email_is_a_validation_error(client, seeded):
    response = client.post(
        "/api/auth/login", json={"email": "not-an-email", "password": TEST_PASSWORD}
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"


def test_protected_endpoint_requires_a_token(client, seeded):
    assert client.get("/api/students").status_code == 401
    assert client.get("/api/dashboard/summary").status_code == 401


def test_garbage_token_is_rejected(client, seeded):
    response = client.get(
        "/api/students", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert response.status_code == 401


def test_expired_token_is_rejected(client, seeded):
    token = create_access_token(
        subject="admin@test.edu", role="ADMIN", user_id=1, expires_minutes=-1
    )
    response = client.get("/api/students", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_token_signed_with_another_key_is_rejected(client, seeded):
    forged = jwt.encode(
        {"sub": "admin@test.edu", "uid": 1, "role": "ADMIN", "exp": 9999999999},
        "a-different-secret",
        algorithm="HS256",
    )
    response = client.get("/api/students", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_token_role_must_match_the_database_row(client, seeded):
    """A privilege downgrade takes effect immediately, not at expiry."""
    token = create_access_token(subject="ta@test.edu", role="ADMIN", user_id=3)
    response = client.get("/api/students", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_and_permissions_endpoints(client, as_instructor):
    me = client.get("/api/auth/me", headers=as_instructor)
    assert me.status_code == 200
    assert me.json()["role"] == "INSTRUCTOR"
    assert "password_hash" not in me.text

    perms = client.get("/api/auth/permissions", headers=as_instructor)
    assert perms.status_code == 200
    body = perms.json()
    assert body["role"] == "INSTRUCTOR"
    assert "results:write" in body["permissions"]
    assert "users:write" not in body["permissions"]


def test_change_password_then_sign_in_with_the_new_one(client, as_admin):
    response = client.post(
        "/api/auth/change-password",
        headers=as_admin,
        json={"current_password": TEST_PASSWORD, "new_password": "BrandNew@456"},
    )
    assert response.status_code == 200

    assert (
        client.post(
            "/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "admin@test.edu", "password": "BrandNew@456"}
        ).status_code
        == 200
    )


def test_change_password_requires_the_current_one(client, as_admin):
    response = client.post(
        "/api/auth/change-password",
        headers=as_admin,
        json={"current_password": "wrong", "new_password": "BrandNew@456"},
    )
    assert response.status_code == 401


def test_short_new_password_is_rejected(client, as_admin):
    response = client.post(
        "/api/auth/change-password",
        headers=as_admin,
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422


# --- hashing primitives ----------------------------------------------------
def test_argon2_hash_is_salted_and_verifiable():
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second, "identical passwords must not produce identical digests"
    assert first.startswith("$argon2")
    assert verify_password("same-password", first)
    assert not verify_password("other-password", first)


def test_verify_password_tolerates_a_corrupt_stored_hash():
    assert verify_password("anything", "not-a-valid-argon2-hash") is False


def test_user_list_never_serialises_a_hash(client, as_admin):
    response = client.get("/api/auth/users", headers=as_admin)
    assert response.status_code == 200
    assert response.json()["total"] == len(ROLE_EMAILS)
    assert "password_hash" not in response.text
    assert "$argon2" not in response.text
