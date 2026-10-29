"""Dashboard and report accuracy.

Each assertion pins a figure that can be verified by hand from the
fixture rows, so a regression in the SQL shows up as a wrong number
rather than merely a different one.
"""

import csv
import io
from datetime import date, datetime, timedelta

import pytest

from app.models import AssessmentResult, AttendanceRecord, LmsActivityLog


def mark_attendance(db, enrollment_id, statuses):
    for index, status in enumerate(statuses):
        db.add(
            AttendanceRecord(
                enrollment_id=enrollment_id,
                session_date=date.today() - timedelta(days=index + 1),
                session_no=1,
                status=status,
            )
        )
    db.commit()


def grade(db, enrollment_id, marks, max_marks=20, status="ON_TIME"):
    db.add(
        AssessmentResult(
            assessment_id=1,
            enrollment_id=enrollment_id,
            marks_obtained=marks,
            percentage=None if marks is None else round(100 * marks / max_marks, 2),
            submission_status=status,
            submitted_at=datetime.now() - timedelta(days=12) if marks is not None else None,
            graded_at=datetime.now() - timedelta(days=10) if marks is not None else None,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def test_dashboard_counts_come_from_the_database(client, as_admin, seeded):
    summary = client.get("/api/dashboard/summary", headers=as_admin).json()
    assert summary["total_students"] == 3
    assert summary["total_courses"] == 2
    assert summary["total_enrollments"] == 3
    assert summary["total_departments"] == 2
    assert summary["generated_at"]


def test_dashboard_excludes_inactive_students_and_courses(client, as_admin, seeded, db):
    seeded.students[0].is_active = False
    seeded.course_b.is_active = False
    db.commit()
    summary = client.get("/api/dashboard/summary", headers=as_admin).json()
    assert summary["total_students"] == 2
    assert summary["total_courses"] == 1


def test_dashboard_averages_match_the_underlying_rows(client, as_admin, seeded, db):
    # enrolment 1: 3 of 4 present -> 75%;  enrolment 2: 2 of 4 -> 50%
    mark_attendance(db, 1, ["PRESENT", "PRESENT", "PRESENT", "ABSENT"])
    mark_attendance(db, 2, ["PRESENT", "PRESENT", "ABSENT", "ABSENT"])
    grade(db, 1, 20)  # 100%
    grade(db, 2, 10)  # 50%

    summary = client.get("/api/dashboard/summary", headers=as_admin).json()
    assert summary["avg_attendance_percentage"] == 62.5  # mean of 75 and 50
    assert summary["avg_assessment_percentage"] == 75.0  # mean of 100 and 50


def test_dashboard_averages_are_null_with_no_data(client, as_admin, seeded):
    summary = client.get("/api/dashboard/summary", headers=as_admin).json()
    assert summary["avg_attendance_percentage"] is None
    assert summary["avg_assessment_percentage"] is None


def test_dashboard_risk_counts_sum_to_the_enrolment_count(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["PRESENT"] * 9 + ["ABSENT"])
    grade(db, 1, 18)
    db.add(LmsActivityLog(enrollment_id=1, activity_type="LOGIN", activity_at=datetime.now()))
    db.commit()
    client.post("/api/risk-assessments/recalculate", headers=as_admin, json={})

    summary = client.get("/api/dashboard/summary", headers=as_admin).json()
    total = (
        summary["high_risk"]
        + summary["medium_risk"]
        + summary["low_risk"]
        + summary["insufficient_data"]
    )
    assert total == summary["total_enrollments"]
    assert summary["low_risk"] == 1
    assert summary["insufficient_data"] == 2

    distribution = {row["category"]: row["count"] for row in summary["risk_distribution"]}
    assert distribution["LOW"] == 1
    assert distribution["INSUFFICIENT_DATA"] == 2


def test_dashboard_counts_due_assessments_within_seven_days(client, as_admin, seeded, db):
    from app.models import Assessment

    db.add(
        Assessment(
            assessment_id=10, course_pk=1, title="Due soon", assessment_type="QUIZ",
            max_marks=10, due_at=datetime.now() + timedelta(days=3),
        )
    )
    db.add(
        Assessment(
            assessment_id=11, course_pk=1, title="Due later", assessment_type="QUIZ",
            max_marks=10, due_at=datetime.now() + timedelta(days=30),
        )
    )
    db.commit()
    summary = client.get("/api/dashboard/summary", headers=as_admin).json()
    assert summary["assessments_due_next_7_days"] == 1


def test_dashboard_alert_and_intervention_counters(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["ABSENT"] * 10)
    db.add(
        LmsActivityLog(
            enrollment_id=1, activity_type="LOGIN", activity_at=datetime.now() - timedelta(days=40)
        )
    )
    grade(db, 1, 2)
    db.commit()
    client.post("/api/risk-assessments/recalculate", headers=as_admin, json={"enrollment_id": 1})

    client.post(
        "/api/interventions",
        headers=as_admin,
        json={
            "enrollment_id": 1,
            "intervention_type": "COUNSELING",
            "contact_date": date.today().isoformat(),
        },
    )
    summary = client.get("/api/dashboard/summary", headers=as_admin).json()
    assert summary["open_alerts"] == 1
    assert summary["unresolved_high_risk_alerts"] == 1
    assert summary["open_interventions"] == 1


def test_recent_alerts_puts_high_risk_first(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["ABSENT"] * 10)
    grade(db, 1, 1)
    mark_attendance(db, 2, ["PRESENT"] * 6 + ["ABSENT"] * 4)
    grade(db, 2, 11)
    for enrollment_id in (1, 2):
        db.add(
            LmsActivityLog(
                enrollment_id=enrollment_id, activity_type="LOGIN",
                activity_at=datetime.now() - timedelta(days=20),
            )
        )
    db.commit()
    client.post("/api/risk-assessments/recalculate", headers=as_admin, json={})

    recent = client.get("/api/dashboard/recent-alerts", headers=as_admin).json()
    assert len(recent) >= 1
    assert recent[0]["risk_category"] == "HIGH"
    assert recent[0]["triggering_factors"]
    assert recent[0]["age_days"] == 0


def test_performance_trend_returns_a_point_per_month(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["PRESENT", "PRESENT", "ABSENT", "ABSENT"])
    grade(db, 1, 15)
    trend = client.get("/api/dashboard/performance-trend", headers=as_admin).json()
    assert len(trend) >= 1
    assert any(point["avg_percentage"] == 75.0 for point in trend)
    assert any(point["avg_attendance_percentage"] == 50.0 for point in trend)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def test_risk_distribution_by_category(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["PRESENT"] * 10)
    grade(db, 1, 19)
    db.add(LmsActivityLog(enrollment_id=1, activity_type="LOGIN", activity_at=datetime.now()))
    db.commit()
    client.post("/api/risk-assessments/recalculate", headers=as_admin, json={})

    rows = client.get("/api/reports/risk-distribution?group_by=category", headers=as_admin).json()
    by_key = {row["group_key"]: row for row in rows}
    assert by_key["LOW"]["total"] == 1
    assert by_key["LOW"]["low_risk"] == 1
    assert by_key["LOW"]["group_label"] == "Low risk (0-29)"
    assert by_key["INSUFFICIENT_DATA"]["total"] == 2


def test_risk_distribution_by_semester_and_department(client, as_admin, seeded):
    by_semester = client.get(
        "/api/reports/risk-distribution?group_by=semester", headers=as_admin
    ).json()
    assert len(by_semester) == 1
    assert by_semester[0]["group_label"] == "Semester 3"
    assert by_semester[0]["total"] == 3

    by_dept = client.get(
        "/api/reports/risk-distribution?group_by=department", headers=as_admin
    ).json()
    assert by_dept[0]["group_key"] == "MATH"
    assert by_dept[0]["total"] == 3


def test_risk_distribution_by_course(client, as_admin, seeded):
    rows = client.get("/api/reports/risk-distribution?group_by=course", headers=as_admin).json()
    assert len(rows) == 1
    assert rows[0]["group_key"] == "MTH201"


def test_invalid_group_by_is_rejected(client, as_admin, seeded):
    assert (
        client.get("/api/reports/risk-distribution?group_by=colour", headers=as_admin).status_code
        == 422
    )


def test_course_performance_figures(client, as_admin, seeded, db):
    grade(db, 1, 20)  # 100%
    grade(db, 2, 10)  # 50%
    grade(db, 3, 4)   # 20% -> below the 40% pass mark
    mark_attendance(db, 1, ["PRESENT", "PRESENT", "PRESENT", "ABSENT"])

    rows = client.get("/api/reports/course-performance", headers=as_admin).json()
    row = next(r for r in rows if r["course_code"] == "MTH201")
    assert row["enrolled_students"] == 3
    assert row["assessment_count"] == 1
    assert row["graded_results"] == 3
    assert row["avg_percentage"] == 56.67  # mean of 100, 50, 20
    assert row["pass_rate_percentage"] == 66.67  # 2 of 3 at or above 40%
    assert row["avg_attendance_percentage"] == 75.0


def test_course_performance_handles_a_course_with_no_data(client, as_admin, seeded):
    rows = client.get("/api/reports/course-performance", headers=as_admin).json()
    empty = next(r for r in rows if r["course_code"] == "MTH210")
    assert empty["graded_results"] == 0
    assert empty["avg_percentage"] is None
    assert empty["pass_rate_percentage"] is None


def test_course_attendance_report(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["PRESENT", "PRESENT", "PRESENT", "PRESENT"])  # 100%
    mark_attendance(db, 2, ["PRESENT", "ABSENT", "ABSENT", "ABSENT"])     # 25%

    rows = client.get("/api/reports/course-attendance", headers=as_admin).json()
    row = next(r for r in rows if r["course_code"] == "MTH201")
    assert row["enrolled_students"] == 3
    assert row["total_sessions_held"] == 8
    assert row["total_sessions_attended"] == 5
    assert row["avg_attendance_percentage"] == 62.5  # 5 of 8 overall
    assert row["students_below_75"] == 1


def test_course_attendance_respects_the_date_window(client, as_admin, seeded, db):
    db.add(
        AttendanceRecord(
            enrollment_id=1, session_date=date.today() - timedelta(days=60),
            session_no=1, status="ABSENT",
        )
    )
    db.add(
        AttendanceRecord(
            enrollment_id=1, session_date=date.today() - timedelta(days=1),
            session_no=1, status="PRESENT",
        )
    )
    db.commit()

    cutoff = (date.today() - timedelta(days=7)).isoformat()
    windowed = client.get(
        f"/api/reports/course-attendance?date_from={cutoff}", headers=as_admin
    ).json()
    row = next(r for r in windowed if r["course_code"] == "MTH201")
    assert row["total_sessions_held"] == 1
    assert row["avg_attendance_percentage"] == 100.0

    everything = client.get("/api/reports/course-attendance", headers=as_admin).json()
    row_all = next(r for r in everything if r["course_code"] == "MTH201")
    assert row_all["total_sessions_held"] == 2
    assert row_all["avg_attendance_percentage"] == 50.0


def test_submission_patterns_report(client, as_admin, seeded, db):
    grade(db, 1, 15, status="ON_TIME")
    grade(db, 2, 12, status="LATE")
    grade(db, 3, None, status="MISSING")

    rows = client.get("/api/reports/submission-patterns", headers=as_admin).json()
    row = next(r for r in rows if r["assessment_title"] == "Assignment 1")
    assert row["total_expected"] == 3
    assert row["on_time"] == 1
    assert row["late"] == 1
    assert row["missing"] == 1
    assert row["on_time_rate"] == 33.33
    assert row["avg_percentage"] == 67.5  # mean of 75 and 60; the missing row is excluded


def test_high_risk_students_report(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["ABSENT"] * 10)
    grade(db, 1, 2)
    db.add(
        LmsActivityLog(
            enrollment_id=1, activity_type="LOGIN", activity_at=datetime.now() - timedelta(days=35)
        )
    )
    db.commit()
    client.post("/api/risk-assessments/recalculate", headers=as_admin, json={})

    rows = client.get("/api/reports/high-risk-students", headers=as_admin).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["student_id"] == "MTH2024001"
    assert row["at_risk_courses"] == 1
    assert "MTH201" in row["courses"]
    assert row["max_risk_score"] >= 60
    assert row["open_alerts"] == 1


def test_high_risk_min_courses_filter(client, as_admin, seeded, db):
    mark_attendance(db, 1, ["ABSENT"] * 10)
    grade(db, 1, 2)
    db.commit()
    client.post("/api/risk-assessments/recalculate", headers=as_admin, json={})

    assert len(client.get("/api/reports/high-risk-students?min_courses=1", headers=as_admin).json()) == 1
    assert len(client.get("/api/reports/high-risk-students?min_courses=2", headers=as_admin).json()) == 0


def test_department_risk_report(client, as_admin, seeded):
    rows = client.get("/api/reports/department-risk", headers=as_admin).json()
    by_code = {row["dept_code"]: row for row in rows}
    assert by_code["MATH"]["enrollments_tracked"] == 3
    assert by_code["MATH"]["students_tracked"] == 3
    # A department with nothing in it still appears, with zeros.
    assert by_code["CSE"]["enrollments_tracked"] == 0
    assert by_code["CSE"]["avg_risk_score"] is None


def test_intervention_outcomes_report(client, as_advisor, seeded):
    for enrollment_id, outcome in ((1, "IMPROVED"), (2, "NO_CHANGE"), (3, "IMPROVED")):
        created = client.post(
            "/api/interventions",
            headers=as_advisor,
            json={
                "enrollment_id": enrollment_id,
                "intervention_type": "COUNSELING",
                "contact_date": date.today().isoformat(),
            },
        )
        client.put(
            f"/api/interventions/{created.json()['intervention_id']}",
            headers=as_advisor,
            json={"outcome": outcome},
        )

    rows = client.get("/api/reports/intervention-outcomes", headers=as_advisor).json()
    row = next(r for r in rows if r["intervention_type"] == "COUNSELING")
    assert row["total"] == 3
    assert row["improved"] == 2
    assert row["no_change"] == 1
    assert row["improvement_rate"] == 66.67


def test_intervention_outcomes_respects_the_date_filter(client, as_advisor, seeded):
    client.post(
        "/api/interventions",
        headers=as_advisor,
        json={
            "enrollment_id": 1,
            "intervention_type": "COUNSELING",
            "contact_date": (date.today() - timedelta(days=60)).isoformat(),
        },
    )
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    assert client.get(
        f"/api/reports/intervention-outcomes?date_from={cutoff}", headers=as_advisor
    ).json() == []
    assert len(client.get("/api/reports/intervention-outcomes", headers=as_advisor).json()) == 1


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
def test_csv_export_matches_the_json_rows(client, as_admin, seeded, db):
    grade(db, 1, 20)
    grade(db, 2, 10)

    json_rows = client.get("/api/reports/course-performance", headers=as_admin).json()
    response = client.get("/api/reports/export?report=course-performance", headers=as_admin)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert ".csv" in response.headers["content-disposition"]

    parsed = list(csv.DictReader(io.StringIO(response.text)))
    assert len(parsed) == len(json_rows)
    assert parsed[0]["course_code"] == json_rows[0]["course_code"]
    assert float(parsed[0]["avg_percentage"]) == json_rows[0]["avg_percentage"]


def test_every_report_exports(client, as_admin, seeded):
    reports = [
        "risk-distribution",
        "course-performance",
        "course-attendance",
        "submission-patterns",
        "high-risk-students",
        "department-risk",
        "intervention-outcomes",
    ]
    for report in reports:
        response = client.get(f"/api/reports/export?report={report}", headers=as_admin)
        assert response.status_code == 200, report
        assert response.text, report


def test_unknown_report_name_is_rejected(client, as_admin, seeded):
    response = client.get("/api/reports/export?report=everything", headers=as_admin)
    assert response.status_code == 422


def test_empty_export_says_so_rather_than_returning_a_bare_file(client, as_admin, seeded):
    response = client.get(
        "/api/reports/export?report=intervention-outcomes", headers=as_admin
    )
    assert response.status_code == 200
    assert "no rows matched" in response.text


def test_csv_export_cannot_smuggle_a_spreadsheet_formula(client, as_admin, seeded, db):
    """Names are typed by staff; a cell opening with = runs in Excel."""
    seeded.course.course_name = '=HYPERLINK("http://evil.example","open")'
    seeded.course_b.course_name = "@SUM(1+1)*cmd|' /C calc'!A0"
    seeded.dept.dept_code = "+MATH"
    db.commit()

    response = client.get("/api/reports/export?report=course-performance", headers=as_admin)
    cells = [cell for row in csv.reader(io.StringIO(response.text)) for cell in row]
    assert '\'=HYPERLINK("http://evil.example","open")' in cells
    assert "'@SUM(1+1)*cmd|' /C calc'!A0" in cells
    assert "'+MATH" in cells
    assert not any(cell.startswith(("=", "+", "-", "@", "\t", "\r")) for cell in cells)

    # Only the file is escaped: the JSON report still shows the real name.
    names = {r["course_name"] for r in client.get("/api/reports/course-performance", headers=as_admin).json()}
    assert '=HYPERLINK("http://evil.example","open")' in names


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_every_formula_trigger_is_neutralised(prefix):
    from app.api.reports import _csv_safe

    assert _csv_safe(f"{prefix}1+2") == f"'{prefix}1+2"


def test_safe_cells_and_numbers_are_left_alone():
    from app.api.reports import _csv_safe

    assert _csv_safe("Linear Algebra") == "Linear Algebra"
    assert _csv_safe("a=b") == "a=b"
    assert _csv_safe(-12.5) == -12.5
    assert _csv_safe(None) is None


def test_unscored_profiles_are_left_out_of_every_mean(client, as_admin, seeded, db):
    """An INSUFFICIENT_DATA row keeps the partial score of its one component.

    Averaging it in pulled the demo's MATH department from 28.51 to 27.88.
    Here one MEDIUM enrolment scores 40 and an unscored one carries 20, so
    every mean must read 40.0 (and would read 30.0 with the bug).
    """
    from app.models import Intervention, RiskAssessment

    db.add_all([
        RiskAssessment(enrollment_id=1, risk_score=40, risk_category="MEDIUM",
                       data_completeness="COMPLETE"),
        RiskAssessment(enrollment_id=2, risk_score=20, risk_category="INSUFFICIENT_DATA",
                       data_completeness="INSUFFICIENT"),
    ])
    for enrollment_id in (1, 2):
        db.add(Intervention(enrollment_id=enrollment_id, intervention_type="COUNSELING",
                            contact_date=date.today(), assigned_advisor_id=4))
    db.commit()

    def get(path):
        response = client.get(path, headers=as_admin)
        assert response.status_code == 200, response.text
        return response.json()

    department = next(r for r in get("/api/reports/department-risk") if r["dept_code"] == "MATH")
    assert department["avg_risk_score"] == 40.0

    by_semester = get("/api/reports/risk-distribution?group_by=semester")
    assert [r["avg_risk_score"] for r in by_semester] == [40.0]

    by_category = {r["group_key"]: r for r in get("/api/reports/risk-distribution?group_by=category")}
    assert by_category["INSUFFICIENT_DATA"]["avg_risk_score"] is None

    # No endpoint returns the per-course mean yet, so read the subquery itself.
    from sqlalchemy import select

    from app.services.queries import course_stats_sq

    stats = course_stats_sq()
    course_mean = db.execute(
        select(stats.c.avg_risk_score).where(stats.c.course_pk == 1)
    ).scalar_one()
    assert float(course_mean) == 40.0

    outcome = next(r for r in get("/api/reports/intervention-outcomes")
                   if r["intervention_type"] == "COUNSELING")
    assert outcome["avg_current_risk"] == 40.0
