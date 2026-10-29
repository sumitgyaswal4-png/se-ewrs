"""Authentication: sign-in, token handling and password hygiene."""

import jwt

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


def test_unknown_email_costs_the_same_argon2_work_as_a_wrong_password(
    client, seeded, monkeypatch
):
    """Skipping the hash for an unknown email made it ~10x faster to reject,
    so response time revealed which accounts exist. Count verifications
    rather than time them, which would be flaky."""
    from app.core import security

    calls = []
    real = security._hasher

    class CountingHasher:
        def __getattr__(self, name):
            return getattr(real, name)

        def verify(self, digest, password):
            calls.append(digest)
            return real.verify(digest, password)

    monkeypatch.setattr(security, "_hasher", CountingHasher())

    client.post("/api/auth/login", json={"email": "nobody@test.edu", "password": "wrong"})
    unknown_calls = len(calls)
    calls.clear()
    client.post("/api/auth/login", json={"email": "admin@test.edu", "password": "wrong"})

    assert unknown_calls == len(calls) == 1


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
        "a-different-secret-of-a-realistic-length-0123456789",
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


# ---------------------------------------------------------------------------
# Failed-login throttling
# ---------------------------------------------------------------------------
def _fail(client, email, times):
    for _ in range(times):
        response = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == 401


def test_repeated_failures_lock_the_account_even_for_the_right_password(client, seeded):
    _fail(client, "admin@test.edu", 5)

    blocked = client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD}
    )
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "too_many_requests"
    assert "Try again in 15 minutes" in blocked.json()["detail"]
    assert 1 <= int(blocked.headers["Retry-After"]) <= 900


def test_a_blocked_attempt_costs_no_hashing_and_writes_no_audit_row(
    client, seeded, as_admin, monkeypatch
):
    from app.core import security

    _fail(client, "ta@test.edu", 5)
    calls = []
    real_verify = security.verify_password
    monkeypatch.setattr(
        "app.api.auth.verify_password", lambda *a: calls.append(a) or real_verify(*a)
    )
    monkeypatch.setattr("app.api.auth.verify_dummy_password", lambda *a: calls.append(a))

    for _ in range(10):
        assert client.post(
            "/api/auth/login", json={"email": "ta@test.edu", "password": "wrong"}
        ).status_code == 429

    assert calls == []
    logs = client.get("/api/settings/audit/logs?action=LOGIN_FAILED", headers=as_admin).json()
    assert logs["total"] == 5


def test_a_lockout_does_not_reveal_whether_the_account_exists(client, seeded):
    _fail(client, "admin@test.edu", 5)
    _fail(client, "nobody@test.edu", 5)
    real = client.post("/api/auth/login", json={"email": "admin@test.edu", "password": "x"})
    fake = client.post("/api/auth/login", json={"email": "nobody@test.edu", "password": "x"})
    assert real.status_code == fake.status_code == 429
    assert real.json() == fake.json()


def test_the_account_key_ignores_case(client, seeded):
    _fail(client, "Admin@Test.edu", 5)
    assert client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD}
    ).status_code == 429


def test_one_locked_account_does_not_lock_the_others(client, seeded):
    _fail(client, "admin@test.edu", 5)
    other = client.post(
        "/api/auth/login", json={"email": "instructor@test.edu", "password": TEST_PASSWORD}
    )
    assert other.status_code == 200


def test_one_address_cannot_spray_guesses_across_accounts(client, seeded):
    """Four tries at each of five accounts stays under every per-account
    limit, but twenty failures from one address is the address limit."""
    for email in [f"user{n}@test.edu" for n in range(5)]:
        _fail(client, email, 4)
    fresh = client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD}
    )
    assert fresh.status_code == 429


def test_a_successful_sign_in_resets_the_account_count(client, seeded):
    _fail(client, "admin@test.edu", 4)
    ok = client.post("/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD})
    assert ok.status_code == 200
    _fail(client, "admin@test.edu", 4)  # would be the 8th failure without the reset
    assert client.post(
        "/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD}
    ).status_code == 200


def test_failures_age_out_of_the_window():
    from app.core.rate_limit import FailedLoginLimiter

    now = [1000.0]
    limiter = FailedLoginLimiter(3, 100, window_seconds=60, clock=lambda: now[0])
    for step in range(3):
        now[0] = 1000.0 + step * 10  # failures at t=1000, 1010, 1020
        limiter.record_failure("a@test.edu", "10.0.0.1")

    assert limiter.retry_after("a@test.edu", "10.0.0.1") == 40  # first ages out at 1060
    now[0] = 1059.0
    assert limiter.retry_after("a@test.edu", "10.0.0.1") == 1
    now[0] = 1060.0
    assert limiter.retry_after("a@test.edu", "10.0.0.1") is None
    assert limiter.retry_after("b@test.edu", "10.0.0.2") is None


def test_a_concurrent_burst_cannot_slip_past_the_limit():
    """Checking first and counting after Argon2 let all 20 of a burst through."""
    import threading
    import time

    from app.core.rate_limit import FailedLoginLimiter

    limiter = FailedLoginLimiter(5, 100, window_seconds=900)
    admitted = []
    start = threading.Barrier(20)

    def attempt():
        start.wait()
        if limiter.reserve("victim@test.edu", "10.0.0.9") is not None:
            admitted.append(1)
            time.sleep(0.05)  # stands in for the password check

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(admitted) == 5


def test_a_successful_sign_in_does_not_use_up_the_address_allowance(client, seeded):
    for email in [f"user{n}@test.edu" for n in range(19)]:
        _fail(client, email, 1)
    ok = client.post("/api/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD})
    assert ok.status_code == 200
    _fail(client, "user19@test.edu", 1)  # the 20th failure is still allowed
    assert client.post(
        "/api/auth/login", json={"email": "user20@test.edu", "password": "wrong"}
    ).status_code == 429


def test_the_right_password_on_a_deactivated_account_is_not_a_failure(client, seeded, db):
    seeded.users["TA"].is_active = False
    db.commit()
    for _ in range(7):
        response = client.post(
            "/api/auth/login", json={"email": "ta@test.edu", "password": TEST_PASSWORD}
        )
        assert response.status_code == 401
        assert "deactivated" in response.json()["detail"].lower()
