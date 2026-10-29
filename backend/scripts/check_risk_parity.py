"""Check that the stored procedure and the Python engine score identically.

Every enrolment's stored risk row was written by
``sp_recalculate_risk_for_enrollment`` (the seed ends with
``CALL sp_recalculate_all_risk``). This recomputes each one with the
Python engine and compares every stored field. It only reads.

    cd backend
    ./.venv/bin/python -m scripts.check_risk_parity

Run it against MySQL loaded with the demo data; the test suite's SQLite
database has no stored procedures, so it cannot make this comparison.
"""

import sys
from decimal import Decimal

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.risk_engine import RiskConfig, collect_metrics, compute_risk

FIELDS = [
    "attendance_percentage", "avg_assessment_percentage", "engagement_score",
    "attendance_risk", "academic_risk", "engagement_risk", "risk_score",
    "risk_category", "data_completeness", "missing_data_reasons",
    "contributing_factors", "sessions_held", "sessions_attended",
    "late_submissions", "missing_submissions", "graded_assessments",
    "login_count_30d", "days_since_last_activity", "last_assessment_date",
    "model_version",
]


def main() -> int:
    db = SessionLocal()
    config = RiskConfig.from_db(db)
    rows = db.execute(text(
        "SELECT ra.* FROM risk_assessments ra JOIN v_latest_risk v ON v.risk_id = ra.risk_id"
    )).mappings().all()
    if not rows:
        # Nothing compared is not the same as nothing wrong.
        print("No scored enrolments to compare: load database/seed.sql first.")
        return 1
    mismatches = []
    for row in rows:
        metrics = collect_metrics(db, row["enrollment_id"], config)
        result = compute_risk(metrics, config)
        for name in FIELDS:
            python = getattr(result, name) if hasattr(result, name) else getattr(metrics, name)
            stored = row[name]
            if isinstance(stored, Decimal) and python is not None:
                python = Decimal(python).quantize(stored)
            if python != stored:
                mismatches.append((row["enrollment_id"], name, stored, python))
    print(f"{len(rows)} enrolments × {len(FIELDS)} fields = "
          f"{len(rows) * len(FIELDS)} comparisons, {len(mismatches)} mismatches")
    for enrollment_id, name, stored, python in mismatches[:20]:
        print(f"  enrolment {enrollment_id}: {name} SQL={stored!r} Python={python!r}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
