"""The risk model itself.

``compute_risk`` and ``compute_engagement_score`` are pure functions, so
these tests pin the arithmetic exactly -- including the behaviour that
matters most: missing data must never be scored as if it were a zero.
"""

from decimal import Decimal

import pytest

from app.services.risk_engine import (
    EnrollmentMetrics,
    RiskConfig,
    compute_engagement_score,
    compute_risk,
)


def metrics(**overrides) -> EnrollmentMetrics:
    """A fully-observed baseline that callers tweak one field at a time."""
    base = dict(
        sessions_held=20,
        sessions_attended=16,
        attendance_percentage=Decimal("80.00"),
        results_recorded=5,
        graded_assessments=5,
        avg_assessment_percentage=Decimal("70.00"),
        ontime_submissions=5,
        late_submissions=0,
        missing_submissions=0,
        total_activities=30,
        login_count_30d=12,
        days_since_last_activity=1,
    )
    base.update(overrides)
    return EnrollmentMetrics(**base)


# ---------------------------------------------------------------------------
# The documented formula
# ---------------------------------------------------------------------------
def test_formula_matches_the_documented_weights():
    """0.35 x attendance + 0.40 x academic + 0.25 x engagement."""
    result = compute_risk(
        metrics(attendance_percentage=Decimal("45"), avg_assessment_percentage=Decimal("38"),
                late_submissions=2, missing_submissions=1, login_count_30d=2,
                days_since_last_activity=21)
    )
    # engagement: recency(21d)=35, frequency(2 of 12)=20,
    #             missing 40*1/5=8, late 20*2/5=8  ->  score 29, risk 71
    assert result.engagement_score == Decimal("29.00")
    assert result.attendance_risk == Decimal("55.00")
    assert result.academic_risk == Decimal("62.00")
    assert result.engagement_risk == Decimal("71.00")
    expected = Decimal("0.35") * 55 + Decimal("0.40") * 62 + Decimal("0.25") * 71
    assert result.risk_score == expected.quantize(Decimal("0.01"))
    assert result.risk_score == Decimal("61.80")
    assert result.risk_category == "HIGH"
    assert result.data_completeness == "COMPLETE"


def test_perfect_student_scores_near_zero():
    result = compute_risk(
        metrics(attendance_percentage=Decimal("100"), sessions_attended=20,
                avg_assessment_percentage=Decimal("100"), login_count_30d=20,
                days_since_last_activity=0)
    )
    assert result.risk_score == Decimal("0.00")
    assert result.risk_category == "LOW"


def test_worst_case_student_scores_one_hundred():
    result = compute_risk(
        metrics(attendance_percentage=Decimal("0"), sessions_attended=0,
                avg_assessment_percentage=Decimal("0"), results_recorded=5,
                missing_submissions=5, late_submissions=0,
                login_count_30d=0, days_since_last_activity=None,
                total_activities=0)
    )
    assert result.risk_score == Decimal("100.00")
    assert result.risk_category == "HIGH"


def test_score_is_always_within_zero_and_one_hundred():
    for attendance in (0, 25, 50, 75, 100):
        for academic in (0, 25, 50, 75, 100):
            result = compute_risk(
                metrics(
                    attendance_percentage=Decimal(attendance),
                    avg_assessment_percentage=Decimal(academic),
                )
            )
            assert Decimal("0") <= result.risk_score <= Decimal("100")


def test_score_is_rounded_to_two_decimals():
    result = compute_risk(
        metrics(attendance_percentage=Decimal("63.33"), avg_assessment_percentage=Decimal("71.11"))
    )
    assert result.risk_score == result.risk_score.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Category banding
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "attendance,academic,expected_score,expected_band",
    [
        # The baseline fixture has flawless engagement (engagement risk 0),
        # so the whole score comes from the attendance and academic terms:
        #   0.35 * (100 - attendance) + 0.40 * (100 - academic)
        (95, 92, "4.95", "LOW"),
        (70, 60, "26.50", "LOW"),
        (60, 45, "36.00", "MEDIUM"),
        (40, 30, "49.00", "MEDIUM"),
        (20, 15, "62.00", "HIGH"),
        (5, 5, "71.25", "HIGH"),
    ],
)
def test_category_bands(attendance, academic, expected_score, expected_band):
    result = compute_risk(
        metrics(
            attendance_percentage=Decimal(attendance),
            avg_assessment_percentage=Decimal(academic),
        )
    )
    assert result.risk_score == Decimal(expected_score)
    assert result.risk_category == expected_band


def test_band_boundaries_are_inclusive_at_the_lower_edge():
    """A score of exactly 30 is MEDIUM and exactly 60 is HIGH."""
    config = RiskConfig()
    # Drive the score using only the attendance component so the target
    # value is exact: with one component the weight re-normalises to 1.
    low_edge = compute_risk(
        EnrollmentMetrics(
            sessions_held=10, sessions_attended=7, attendance_percentage=Decimal("70"),
            graded_assessments=1, avg_assessment_percentage=Decimal("70"),
            results_recorded=0, total_activities=0,
        ),
        config,
    )
    assert low_edge.risk_score == Decimal("30.00")
    assert low_edge.risk_category == "MEDIUM"

    high_edge = compute_risk(
        EnrollmentMetrics(
            sessions_held=10, sessions_attended=4, attendance_percentage=Decimal("40"),
            graded_assessments=1, avg_assessment_percentage=Decimal("40"),
            results_recorded=0, total_activities=0,
        ),
        config,
    )
    assert high_edge.risk_score == Decimal("60.00")
    assert high_edge.risk_category == "HIGH"


def test_just_below_a_boundary_stays_in_the_lower_band():
    result = compute_risk(
        EnrollmentMetrics(
            sessions_held=10, sessions_attended=7, attendance_percentage=Decimal("70.01"),
            graded_assessments=1, avg_assessment_percentage=Decimal("70.01"),
            results_recorded=0, total_activities=0,
        )
    )
    assert result.risk_score == Decimal("29.99")
    assert result.risk_category == "LOW"


# ---------------------------------------------------------------------------
# Missing-data handling -- the behaviour the brief calls out explicitly
# ---------------------------------------------------------------------------
def test_no_data_at_all_is_insufficient_not_high_risk():
    result = compute_risk(EnrollmentMetrics())
    assert result.risk_score is None
    assert result.risk_category == "INSUFFICIENT_DATA"
    assert result.data_completeness == "INSUFFICIENT"
    assert result.components_available == 0
    assert "Attendance component skipped" in result.missing_data_reasons
    assert "Academic component skipped" in result.missing_data_reasons
    assert "Engagement component skipped" in result.missing_data_reasons


def test_a_student_with_no_graded_work_is_not_punished_for_it():
    """Dropping the academic component must not raise the score.

    With attendance 80% and full engagement, adding a *missing* academic
    component would push the score up if missing data were treated as a
    zero. Re-normalising the weights keeps it where it belongs.
    """
    with_marks = compute_risk(metrics(avg_assessment_percentage=Decimal("100")))
    without_marks = compute_risk(metrics(graded_assessments=0, avg_assessment_percentage=None))

    assert without_marks.academic_risk is None
    assert without_marks.data_completeness == "PARTIAL"
    # attendance risk 20 (weight .35) + engagement risk 0 (weight .25)
    # renormalised over 0.60 -> 20 * 0.35 / 0.60 = 11.67
    assert without_marks.risk_score == Decimal("11.67")
    # and it must not exceed the all-zeros-academic hypothetical
    hypothetical_zero = compute_risk(metrics(avg_assessment_percentage=Decimal("0")))
    assert without_marks.risk_score < hypothetical_zero.risk_score
    assert with_marks.risk_score < without_marks.risk_score


def test_weights_are_renormalised_across_available_components():
    """Two components present -> their weights sum back to 1."""
    result = compute_risk(
        metrics(
            attendance_percentage=Decimal("50"),
            graded_assessments=0,
            avg_assessment_percentage=None,
            total_activities=0,
            results_recorded=0,
        )
    )
    # only attendance survives, so its weight becomes 1.0
    assert result.components_available == 1
    assert result.risk_score == Decimal("50.00")
    assert result.risk_category == "INSUFFICIENT_DATA", (
        "a single component is not enough to assign a risk band"
    )


def test_two_components_give_a_partial_but_usable_band():
    result = compute_risk(
        metrics(total_activities=0, results_recorded=0, late_submissions=0,
                missing_submissions=0, graded_assessments=5)
    )
    assert result.data_completeness == "PARTIAL"
    assert result.components_available == 2
    assert result.risk_category in ("LOW", "MEDIUM", "HIGH")


def test_too_few_attendance_sessions_skips_the_attendance_component():
    config = RiskConfig(min_sessions=5)
    result = compute_risk(
        metrics(sessions_held=2, sessions_attended=1, attendance_percentage=Decimal("50")),
        config,
    )
    assert result.attendance_risk is None
    assert "only 2 of 5 required sessions" in result.missing_data_reasons


def test_missing_data_reason_is_always_populated_when_incomplete():
    result = compute_risk(metrics(graded_assessments=0, avg_assessment_percentage=None))
    assert result.data_completeness != "COMPLETE"
    assert result.missing_data_reasons


def test_complete_profile_has_no_missing_data_reason():
    result = compute_risk(metrics())
    assert result.data_completeness == "COMPLETE"
    assert result.missing_data_reasons is None


# ---------------------------------------------------------------------------
# Engagement sub-model
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "days,expected_penalty",
    [(0, 0), (3, 0), (4, 10), (7, 10), (8, 20), (14, 20), (15, 35), (30, 35), (31, 50), (None, 50)],
)
def test_recency_bands(days, expected_penalty):
    score, breakdown = compute_engagement_score(days, 12, 0, 0, 0)
    assert breakdown["recency_penalty"] == expected_penalty
    assert score == Decimal(100 - expected_penalty)


@pytest.mark.parametrize(
    "logins,expected_penalty",
    [(12, 0), (20, 0), (8, 5), (11, 5), (4, 12), (7, 12), (1, 20), (3, 20), (0, 30)],
)
def test_login_frequency_bands_with_a_target_of_twelve(logins, expected_penalty):
    _, breakdown = compute_engagement_score(0, logins, 0, 0, 0, target_logins=12)
    assert breakdown["login_frequency_penalty"] == expected_penalty


def test_submission_penalties_scale_with_the_ratio():
    _, breakdown = compute_engagement_score(0, 12, missing_submissions=2,
                                            late_submissions=4, results_recorded=8)
    assert breakdown["missing_submission_penalty"] == 10.0  # 40 * 2/8
    assert breakdown["late_submission_penalty"] == 10.0  # 20 * 4/8


def test_submission_penalties_are_zero_when_nothing_is_expected():
    _, breakdown = compute_engagement_score(0, 12, 0, 0, results_recorded=0)
    assert breakdown["missing_submission_penalty"] == 0.0
    assert breakdown["late_submission_penalty"] == 0.0


def test_engagement_score_is_clamped_at_zero():
    score, _ = compute_engagement_score(None, 0, missing_submissions=10,
                                        late_submissions=10, results_recorded=10)
    # 50 + 30 + 40 + 20 = 140 of penalty, clamped
    assert score == Decimal("0.00")


def test_engagement_score_never_exceeds_one_hundred():
    score, _ = compute_engagement_score(0, 100, 0, 0, 5)
    assert score == Decimal("100.00")


def test_frequency_boundary_uses_exact_integer_arithmetic():
    """``logins * 3 >= target * 2`` -- no float comparison to drift.

    With target 12, 8 logins is exactly two-thirds and must land in the
    5-point band, not the 12-point one.
    """
    _, at_boundary = compute_engagement_score(0, 8, 0, 0, 0, target_logins=12)
    _, just_below = compute_engagement_score(0, 7, 0, 0, 0, target_logins=12)
    assert at_boundary["login_frequency_penalty"] == 5
    assert just_below["login_frequency_penalty"] == 12


# ---------------------------------------------------------------------------
# Contributing factors
# ---------------------------------------------------------------------------
def test_contributing_factors_name_the_real_problems():
    result = compute_risk(
        metrics(attendance_percentage=Decimal("52"), avg_assessment_percentage=Decimal("41"),
                late_submissions=3, missing_submissions=2, days_since_last_activity=20,
                login_count_30d=1)
    )
    factors = result.contributing_factors
    assert "Low attendance (52%)" in factors
    assert "Weak assessment average (41%)" in factors
    assert "2 missing submission(s)" in factors
    assert "3 late submission(s)" in factors
    assert "No LMS activity for 20 days" in factors


def test_healthy_profile_reports_no_adverse_factors():
    result = compute_risk(
        metrics(attendance_percentage=Decimal("96"), avg_assessment_percentage=Decimal("88"),
                login_count_30d=15, days_since_last_activity=0)
    )
    assert result.contributing_factors == "No adverse factors detected"


def test_configurable_thresholds_change_the_band_not_the_score():
    tight = RiskConfig(threshold_medium=10, threshold_high=20)
    loose = RiskConfig(threshold_medium=50, threshold_high=90)
    inputs = metrics(attendance_percentage=Decimal("70"), avg_assessment_percentage=Decimal("65"))

    tight_result = compute_risk(inputs, tight)
    loose_result = compute_risk(inputs, loose)
    assert tight_result.risk_score == loose_result.risk_score
    assert tight_result.risk_category == "HIGH"
    assert loose_result.risk_category == "LOW"
