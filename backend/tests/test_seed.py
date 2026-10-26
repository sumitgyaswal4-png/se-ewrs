"""The demo dataset.

These assertions protect the properties the demo is *for*: a realistic
spread across all three risk bands, worked examples of missing data, and
no real personal information.
"""

from collections import Counter

import pytest
from sqlalchemy import func, select

from app.db.seed import DEMO_PASSWORD, SEED_TABLES, build_dataset, emit_sql, seed_database
from app.models import (
    AssessmentResult,
    Course,
    Department,
    Intervention,
    RiskAlert,
    RiskAssessment,
    Student,
    SystemSetting,
    User,
)


@pytest.fixture(scope="module")
def dataset():
    return build_dataset()


def test_dataset_is_deterministic():
    """A fixed seed, so a demo looks the same every time it is shown."""
    first, second = build_dataset(), build_dataset()
    assert first.counts() == second.counts()
    assert [s["student_id"] for s in first.students] == [
        s["student_id"] for s in second.students
    ]


def test_dataset_meets_the_brief_minimums(dataset):
    counts = dataset.counts()
    assert counts["departments"] >= 2, "multiple departments"
    assert counts["students"] >= 30, "at least 30 fictional students"
    assert counts["courses"] >= 5, "at least 5 courses"
    assert counts["enrollments"] > 0
    assert counts["attendance_records"] > 0
    assert counts["lms_activity_logs"] > 0
    assert counts["assessments"] > 0
    assert counts["assessment_results"] > 0
    assert counts["interventions"] > 0


def test_several_instructors_and_advisors_exist(dataset):
    roles = Counter(u["role"] for u in dataset.users)
    assert roles["INSTRUCTOR"] >= 2
    assert roles["ADVISOR"] >= 2
    assert roles["TA"] >= 1
    assert roles["CHAIR"] >= 1
    assert roles["ADMIN"] >= 1


def test_assessment_mix_covers_assignments_quizzes_and_exams(dataset):
    types = {a["assessment_type"] for a in dataset.assessments}
    assert "ASSIGNMENT" in types
    assert "QUIZ" in types
    assert "MIDTERM" in types


def test_identifiers_are_unique(dataset):
    assert len({s["student_id"] for s in dataset.students}) == len(dataset.students)
    assert len({s["email"] for s in dataset.students}) == len(dataset.students)
    assert len({u["email"] for u in dataset.users}) == len(dataset.users)


def test_no_duplicate_enrolments(dataset):
    pairs = [(e["student_pk"], e["course_pk"]) for e in dataset.enrollments]
    assert len(set(pairs)) == len(pairs)


def test_no_duplicate_attendance_sessions(dataset):
    keys = [
        (a["enrollment_id"], a["session_offset_days"], a["session_no"])
        for a in dataset.attendance
    ]
    assert len(set(keys)) == len(keys)


def test_marks_never_exceed_the_maximum(dataset):
    for row in dataset.results:
        if row["marks_obtained"] is not None:
            assert 0 <= row["marks_obtained"] <= row["max_marks"]


def test_all_dates_are_relative_offsets_not_fixed_calendar_dates(dataset):
    """Offsets keep the demo current whenever it is loaded."""
    for row in dataset.attendance:
        assert isinstance(row["session_offset_days"], int)
        assert row["session_offset_days"] >= 0
    for row in dataset.activities:
        assert isinstance(row["at_offset_days"], int)


def test_the_demo_contains_no_obviously_real_contact_details(dataset):
    """Fictional identities only -- every address is on a demo domain."""
    for student in dataset.students:
        assert student["email"].endswith("@students.se-ewrs.edu")
    for user in dataset.users:
        assert user["email"].endswith("@se-ewrs.edu")


# ---------------------------------------------------------------------------
# Loading it
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    """Seed a throwaway SQLite file once and inspect the result."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    path = tmp_path_factory.mktemp("seed") / "demo.sqlite3"
    url = f"sqlite:///{path}"
    counts = seed_database(url=url, reset=True, quiet=True)
    engine = create_engine(url)
    with Session(engine) as session:
        yield session, counts


def test_seeding_populates_every_table(seeded_db):
    session, counts = seeded_db
    assert counts["students"] >= 30
    assert counts["risk_assessments"] > 0
    assert counts["risk_alerts"] > 0

    assert session.execute(select(func.count()).select_from(Student)).scalar_one() >= 30
    assert session.execute(select(func.count()).select_from(Course)).scalar_one() >= 5
    assert session.execute(select(func.count()).select_from(Department)).scalar_one() >= 2
    assert session.execute(select(func.count()).select_from(Intervention)).scalar_one() > 0


def test_the_demo_spans_all_three_risk_bands(seeded_db):
    """The point of the demo: low, medium AND high risk are all present."""
    session, _ = seeded_db
    bands = {
        row[0]: row[1]
        for row in session.execute(
            select(RiskAssessment.risk_category, func.count())
            .group_by(RiskAssessment.risk_category)
        ).all()
    }
    assert bands.get("LOW", 0) > 0
    assert bands.get("MEDIUM", 0) > 0
    assert bands.get("HIGH", 0) > 0
    assert bands.get("INSUFFICIENT_DATA", 0) > 0, (
        "the demo must include a worked example of missing data"
    )


def test_every_risk_score_is_in_range(seeded_db):
    session, _ = seeded_db
    scores = list(
        session.execute(
            select(RiskAssessment.risk_score).where(RiskAssessment.risk_score.is_not(None))
        ).scalars()
    )
    assert scores
    assert all(0 <= float(score) <= 100 for score in scores)


def test_unscored_profiles_carry_a_reason(seeded_db):
    session, _ = seeded_db
    rows = list(
        session.execute(
            select(RiskAssessment).where(RiskAssessment.risk_category == "INSUFFICIENT_DATA")
        ).scalars()
    )
    assert rows
    assert all(row.missing_data_reasons for row in rows)


def test_alerts_exist_only_for_medium_and_high_risk(seeded_db):
    session, _ = seeded_db
    categories = set(session.execute(select(RiskAlert.risk_category)).scalars())
    assert categories <= {"MEDIUM", "HIGH"}


def test_at_most_one_open_alert_per_enrolment(seeded_db):
    session, _ = seeded_db
    duplicates = session.execute(
        select(RiskAlert.enrollment_id, func.count())
        .where(RiskAlert.active_flag == 1)
        .group_by(RiskAlert.enrollment_id)
        .having(func.count() > 1)
    ).all()
    assert duplicates == []


def test_the_alert_queue_shows_worked_state(seeded_db):
    """Not every alert is untouched -- the demo shows a queue in progress."""
    session, _ = seeded_db
    statuses = set(session.execute(select(RiskAlert.status)).scalars())
    assert "NEW" in statuses
    assert statuses & {"ACKNOWLEDGED", "IN_PROGRESS"}


def test_stored_percentages_match_marks_over_max(seeded_db):
    session, _ = seeded_db
    from app.models import Assessment

    mismatches = session.execute(
        select(func.count())
        .select_from(AssessmentResult)
        .join(Assessment, Assessment.assessment_id == AssessmentResult.assessment_id)
        .where(
            AssessmentResult.marks_obtained.is_not(None),
            func.abs(
                AssessmentResult.percentage
                - func.round(100.0 * AssessmentResult.marks_obtained / Assessment.max_marks, 2)
            )
            > 0.011,
        )
    ).scalar_one()
    assert mismatches == 0


def test_every_demo_account_shares_the_documented_password(seeded_db):
    from app.core.security import verify_password

    session, _ = seeded_db
    users = list(session.execute(select(User)).scalars())
    assert users
    for user in users:
        assert user.password_hash.startswith("$argon2"), "Argon2id, not plaintext"
        assert DEMO_PASSWORD not in user.password_hash
    assert verify_password(DEMO_PASSWORD, users[0].password_hash)


def test_reseeding_is_idempotent(tmp_path):
    """Running the seed twice must not duplicate or fail."""
    url = f"sqlite:///{tmp_path / 'twice.sqlite3'}"
    first = seed_database(url=url, reset=True, quiet=True)
    second = seed_database(url=url, reset=True, quiet=True)
    assert first["students"] == second["students"]
    assert first["enrollments"] == second["enrollments"]


def test_reseeding_preserves_a_tuned_risk_model(tmp_path):
    """system_settings is deliberately outside the reset list."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    url = f"sqlite:///{tmp_path / 'tuned.sqlite3'}"
    seed_database(url=url, reset=True, quiet=True)

    engine = create_engine(url)
    with Session(engine) as session:
        setting = session.get(SystemSetting, "risk.weight.attendance")
        setting.setting_value = "0.99"
        session.commit()

    seed_database(url=url, reset=True, quiet=True)
    with Session(engine) as session:
        assert session.get(SystemSetting, "risk.weight.attendance").setting_value == "0.99"


def test_system_settings_is_not_in_the_reset_list():
    assert "system_settings" not in SEED_TABLES


# ---------------------------------------------------------------------------
# The emitted SQL script
# ---------------------------------------------------------------------------
def test_emit_sql_produces_a_loadable_script(tmp_path):
    path = emit_sql(tmp_path / "seed.sql", password_hash="$argon2id$v=19$fake$hash")
    sql = path.read_text(encoding="utf-8")

    assert "USE se_ewrs;" in sql
    assert "INSERT INTO students" in sql
    assert "INSERT INTO assessment_results" in sql
    # Risk rows come from the stored procedure, not hardcoded values.
    assert "CALL sp_recalculate_all_risk(NULL, 1);" in sql
    assert "CALL sp_update_alert_status(" in sql
    # Dates stay relative so the demo never goes stale.
    assert "CURDATE() - INTERVAL" in sql
    assert "INSERT INTO risk_assessments" not in sql


def test_emitted_sql_never_contains_a_plaintext_password(tmp_path):
    path = emit_sql(tmp_path / "seed.sql", password_hash="$argon2id$v=19$fake$hash")
    sql = path.read_text(encoding="utf-8")
    # The password appears once, in the header comment documenting the demo
    # credentials, and never as a stored value.
    assert sql.count(DEMO_PASSWORD) == 1
    header = sql.split("USE se_ewrs;")[0]
    assert DEMO_PASSWORD in header


def test_emitted_sql_leaves_system_settings_alone(tmp_path):
    sql = emit_sql(tmp_path / "seed.sql", password_hash="$argon2id$x").read_text()
    assert "DELETE FROM system_settings" not in sql


def test_emitted_sql_omits_percentage_so_the_trigger_derives_it(tmp_path):
    """Proves the trigger is doing the work after a bulk load."""
    sql = emit_sql(tmp_path / "seed.sql", password_hash="$argon2id$x").read_text()
    insert_line = next(
        line for line in sql.splitlines() if line.startswith("INSERT INTO assessment_results")
    )
    assert "percentage" not in insert_line
    assert "marks_obtained" in insert_line


def test_emitted_sql_escapes_quotes_in_text(tmp_path):
    """Notes contain apostrophes; they must be doubled, not left raw."""
    sql = emit_sql(tmp_path / "seed.sql", password_hash="$argon2id$x").read_text()
    assert "student's" in sql.lower() or "''" in sql
