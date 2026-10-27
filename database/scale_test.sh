#!/usr/bin/env bash
# =====================================================================
# SE-EWRS -- build the synthetic benchmark database and time it.
#
#   ./database/scale_test.sh
#
# Creates `se_ewrs_scale` from the same schema, views, procedures and
# triggers as the real database, loads ~444,000 synthetic fact rows,
# recalculates risk for all 6,000 enrolments, and prints the timings.
# This reproduces the figures in docs/database_design.md section 9.
#
# It never touches `se_ewrs`. The guard below refuses to run if the
# target database name is changed to the demo one.
#
# Set MYSQL_USER to use a different account and MYSQL_PASSWORD to skip
# the prompt (an empty value means "no password").
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MYSQL_USER="${MYSQL_USER:-root}"
TARGET="se_ewrs_scale"

if [[ "$TARGET" == "se_ewrs" ]]; then
  echo "refusing to run against the demo database" >&2
  exit 2
fi

command -v mysql >/dev/null || { echo "the mysql client is required"; exit 1; }

if [[ -z "${MYSQL_PASSWORD+set}" ]]; then
  read -rsp "MySQL password for ${MYSQL_USER} (empty if none): " MYSQL_PASSWORD
  echo
fi
export MYSQL_PWD="$MYSQL_PASSWORD"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

say "Creating $TARGET from the project's own SQL"
# The scripts name se_ewrs explicitly, so point them at the benchmark
# database instead. \b keeps se_ewrs_scale from being rewritten twice.
for script in schema views procedures triggers; do
  echo "  applying database/${script}.sql"
  sed "s/\bse_ewrs\b/${TARGET}/g" "$ROOT/database/${script}.sql" \
    | mysql -u "$MYSQL_USER" > /dev/null
done

say "Generating ~444,000 synthetic fact rows"
time mysql -u "$MYSQL_USER" < "$ROOT/database/scale_test.sql"

say "Recalculating risk for every enrolment"
time mysql -u "$MYSQL_USER" -B "$TARGET" \
  -e "CALL sp_recalculate_all_risk(NULL, 1)" > /dev/null

say "Result"
mysql -u "$MYSQL_USER" -B "$TARGET" -e "
  SELECT (SELECT COUNT(*) FROM enrollments)        AS enrolments,
         (SELECT COUNT(*) FROM attendance_records) AS attendance,
         (SELECT COUNT(*) FROM lms_activity_logs)  AS activity,
         (SELECT COUNT(*) FROM assessment_results) AS results,
         (SELECT COUNT(*) FROM risk_alerts)        AS alerts;
  SELECT risk_category, COUNT(*) AS enrolments
    FROM v_latest_risk GROUP BY risk_category ORDER BY risk_category;"
unset MYSQL_PWD

cat <<'NEXT'

To time the API against it, point a backend at this database:

    cd backend
    DATABASE_URL="mysql+pymysql://root@localhost/se_ewrs_scale?charset=utf8mb4" \
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
    ./.venv/bin/python -m uvicorn app.main:app --port 8001

The generated staff accounts carry a placeholder hash and cannot sign
in. To get a usable login, set one with the application's own hasher:

    cd backend && ./.venv/bin/python -c "
    from app.core.security import hash_password
    print(hash_password('Demo@12345'))"

then UPDATE users SET password_hash='<that>', role='ADMIN',
email='admin@scale-demo.edu' WHERE user_id=1;

To remove the benchmark database:  DROP DATABASE se_ewrs_scale;
NEXT
