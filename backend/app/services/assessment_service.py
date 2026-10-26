"""Assessment grading rules.

These two functions are the application-side twin of the
``trg_ar_before_insert`` / ``trg_ar_before_update`` triggers and of
``sp_upsert_assessment_result``. On MySQL the triggers are the real
guarantee -- they fire for any client, including a manual INSERT. The
functions here produce the identical values so that behaviour is the same
when the API writes the row and when the suite runs on SQLite.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.core.exceptions import ValidationError


def compute_percentage(
    marks_obtained: Optional[Decimal], max_marks: Decimal
) -> Optional[Decimal]:
    """``ROUND(100 * marks / max_marks, 2)``, or ``None`` when ungraded.

    Rounds half-up to match MySQL's ``ROUND()``, so a value written by
    the API and a value written by the trigger are byte-identical.
    """
    if marks_obtained is None:
        return None
    if max_marks is None or Decimal(max_marks) <= 0:
        raise ValidationError("The assessment's maximum marks must be greater than zero")
    pct = Decimal(100) * Decimal(marks_obtained) / Decimal(max_marks)
    return pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_marks(marks_obtained: Optional[float], max_marks: Decimal) -> Optional[Decimal]:
    """Reject negative marks and marks above the assessment maximum."""
    if marks_obtained is None:
        return None
    marks = Decimal(str(marks_obtained))
    if marks < 0:
        raise ValidationError("Marks obtained cannot be negative")
    if marks > Decimal(max_marks):
        raise ValidationError(
            f"Marks obtained ({marks}) cannot exceed the maximum marks ({max_marks})"
        )
    return marks


def derive_submission_status(
    submitted_at: Optional[datetime], due_at: datetime
) -> str:
    """``MISSING`` with no submission, else ``ON_TIME`` or ``LATE`` vs the deadline."""
    if submitted_at is None:
        return "MISSING"
    return "ON_TIME" if submitted_at <= due_at else "LATE"
