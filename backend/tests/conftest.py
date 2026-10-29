"""Pytest fixtures.

The suite runs against an in-memory SQLite database so it needs no MySQL
server and leaves no state behind. Everything under test -- the ORM
models, the aggregate SQL in ``services/queries.py``, the risk engine and
every router -- is the same code that runs against MySQL 8; only the
engine differs. The MySQL-specific objects (views, procedures, triggers)
are exercised by ``database/*.sql`` against a real server, which the
README documents.
"""

import functools
import os
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Dict, Optional

# Must be set before any app module reads the settings.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-not-used-anywhere-else"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Assessment,
    Course,
    CourseInstructor,
    Department,
    Enrollment,
    Student,
    SystemSetting,
    User,
)

TEST_PASSWORD = "TestPass@123"


@functools.lru_cache(maxsize=1)
def _test_digest() -> str:
    """Argon2id is deliberately slow, so the fixture password is hashed
    once per test session rather than once per test."""
    return hash_password(TEST_PASSWORD)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return eng


@pytest.fixture
def db(engine) -> Session:
    """A clean schema for every test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _fresh_login_limiter():
    """Failed sign-ins are counted per process; start every test at zero."""
    from app.api.auth import login_limiter

    login_limiter.reset()
    yield
    login_limiter.reset()


@pytest.fixture
def client(db) -> TestClient:
    """TestClient wired to the same session the test holds."""

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = [
    ("risk.weight.attendance", "0.35", "FLOAT"),
    ("risk.weight.academic", "0.40", "FLOAT"),
    ("risk.weight.engagement", "0.25", "FLOAT"),
    ("risk.threshold.medium", "30", "INT"),
    ("risk.threshold.high", "60", "INT"),
    ("risk.min_sessions", "3", "INT"),
    ("risk.min_graded", "1", "INT"),
    ("risk.activity_window_days", "30", "INT"),
    ("engagement.target_logins_30d", "12", "INT"),
    ("alert.min_score", "30", "INT"),
    ("risk.model_version", "rule-v1", "STRING"),
]

ROLE_EMAILS = {
    "ADMIN": "admin@test.edu",
    "INSTRUCTOR": "instructor@test.edu",
    "TA": "ta@test.edu",
    "ADVISOR": "advisor@test.edu",
    "CHAIR": "chair@test.edu",
}


@pytest.fixture
def seeded(db) -> SimpleNamespace:
    """A small but complete fixture graph.

    One department, one user per role, two courses, three students and
    their enrolments, plus the default risk-model settings.
    """
    for key, value, value_type in DEFAULT_SETTINGS:
        db.add(SystemSetting(setting_key=key, setting_value=value, value_type=value_type))

    dept = Department(dept_id=1, dept_code="MATH", dept_name="Department of Mathematics")
    other_dept = Department(dept_id=2, dept_code="CSE", dept_name="Computer Science")
    db.add_all([dept, other_dept])

    digest = _test_digest()
    users: Dict[str, User] = {}
    for index, (role, email) in enumerate(ROLE_EMAILS.items(), start=1):
        user = User(
            user_id=index,
            full_name=f"{role.title()} User",
            email=email,
            password_hash=digest,
            role=role,
            dept_id=1,
            is_active=True,
        )
        users[role] = user
        db.add(user)

    course = Course(
        course_pk=1,
        course_code="MTH201",
        course_name="Linear Algebra",
        dept_id=1,
        semester=3,
        credits=4,
        academic_term="2025-ODD",
        total_sessions=20,
        is_active=True,
    )
    course_b = Course(
        course_pk=2,
        course_code="MTH210",
        course_name="Probability",
        dept_id=1,
        semester=3,
        credits=3,
        academic_term="2025-ODD",
        total_sessions=18,
        is_active=True,
    )
    db.add_all([course, course_b])
    db.flush()

    db.add(CourseInstructor(course_instructor_id=1, course_pk=1, user_id=2, role_in_course="PRIMARY"))

    students = []
    for index in range(1, 4):
        student = Student(
            student_pk=index,
            student_id=f"MTH2024{index:03d}",
            full_name=f"Student {index}",
            email=f"student{index}@test.edu",
            dept_id=1,
            semester=3,
            enrollment_year=2024,
            is_active=True,
        )
        students.append(student)
        db.add(student)
    db.flush()

    enrollments = []
    for index, student in enumerate(students, start=1):
        enrollment = Enrollment(
            enrollment_id=index,
            student_pk=student.student_pk,
            course_pk=1,
            enrolled_on=date.today() - timedelta(days=90),
            status="ACTIVE",
        )
        enrollments.append(enrollment)
        db.add(enrollment)
    db.flush()

    assessment = Assessment(
        assessment_id=1,
        course_pk=1,
        title="Assignment 1",
        assessment_type="ASSIGNMENT",
        max_marks=20,
        weight_percent=10,
        due_at=datetime.now() - timedelta(days=10),
        created_by=2,
    )
    db.add(assessment)
    db.commit()

    return SimpleNamespace(
        dept=dept,
        other_dept=other_dept,
        users=users,
        course=course,
        course_b=course_b,
        students=students,
        enrollments=enrollments,
        assessment=assessment,
    )


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------
def login(client: TestClient, email: str, password: str = TEST_PASSWORD) -> Optional[str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        return None
    return response.json()["access_token"]


def auth_headers(client: TestClient, role: str) -> Dict[str, str]:
    token = login(client, ROLE_EMAILS[role])
    assert token, f"could not sign in as {role}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def as_admin(client, seeded) -> Dict[str, str]:
    return auth_headers(client, "ADMIN")


@pytest.fixture
def as_instructor(client, seeded) -> Dict[str, str]:
    return auth_headers(client, "INSTRUCTOR")


@pytest.fixture
def as_ta(client, seeded) -> Dict[str, str]:
    return auth_headers(client, "TA")


@pytest.fixture
def as_advisor(client, seeded) -> Dict[str, str]:
    return auth_headers(client, "ADVISOR")


@pytest.fixture
def as_chair(client, seeded) -> Dict[str, str]:
    return auth_headers(client, "CHAIR")
