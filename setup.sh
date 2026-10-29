#!/usr/bin/env bash
# =====================================================================
# SE-EWRS one-shot local setup.
#
#   ./setup.sh            install dependencies only
#   ./setup.sh --db       also create the MySQL schema and demo data
#                         (asks first if se_ewrs already holds tables:
#                         loading it drops and recreates every one)
#
# The --db step needs a MySQL account that can create a database. Its
# password is asked for once and never stored. Set MYSQL_USER to use a
# different account, and MYSQL_PASSWORD to skip the prompt entirely
# (useful in a script; an empty value means "no password").
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MYSQL_USER="${MYSQL_USER:-root}"
LOAD_DB=false
case "${1:-}" in
  "")        ;;
  --db)      LOAD_DB=true ;;
  -h|--help) echo "usage: ./setup.sh [--db]"; exit 0 ;;
  *)         echo "unknown option: $1" >&2
             echo "usage: ./setup.sh [--db]" >&2
             exit 2 ;;
esac

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

say "Checking prerequisites"
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v npm >/dev/null     || { echo "npm (Node 18+) is required"; exit 1; }
python3 --version
node --version

say "Backend: virtual environment and dependencies"
cd "$ROOT/backend"
[[ -d .venv ]] || python3 -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt
echo "installed into backend/.venv"

if [[ ! -f "$ROOT/backend/.env" ]]; then
  say "Creating backend/.env from .env.example"
  cp "$ROOT/.env.example" "$ROOT/backend/.env"
  SECRET="$(./.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  # Replace the placeholder with a freshly generated key.
  python3 - "$ROOT/backend/.env" "$SECRET" <<'PY'
import sys, pathlib
path, secret = pathlib.Path(sys.argv[1]), sys.argv[2]
text = path.read_text()
text = text.replace("SECRET_KEY=generate-a-new-random-value-do-not-use-this-one",
                    f"SECRET_KEY={secret}")
path.write_text(text)
PY
  echo "backend/.env created with a generated SECRET_KEY."
  echo "Edit DB_USER and DB_PASSWORD before starting the backend."
else
  echo "backend/.env already exists; leaving it alone."
fi

say "Frontend: dependencies"
cd "$ROOT/frontend"
npm install --no-audit --no-fund
echo "installed into frontend/node_modules"

if $LOAD_DB; then
  say "Database: creating the schema and loading the demo data"
  command -v mysql >/dev/null || { echo "the mysql client is required for --db"; exit 1; }

  # Ask once, not once per script. The client reads MYSQL_PWD itself, so
  # the password never reaches a command line or the shell history.
  # Presetting MYSQL_PASSWORD skips the prompt, which is what makes this
  # step runnable unattended; an empty value is a valid answer for an
  # account that has no password, such as a local socket login.
  if [[ -z "${MYSQL_PASSWORD+set}" ]]; then
    read -rsp "MySQL password for ${MYSQL_USER} (empty if none): " MYSQL_PASSWORD
    echo
  fi
  export MYSQL_PWD="$MYSQL_PASSWORD"

  # schema.sql drops and recreates every table, so loading over an existing
  # se_ewrs destroys whatever it holds. Say exactly what would go, and go
  # ahead only on an explicit answer: typing the database name, or, with no
  # terminal to ask on, SE_EWRS_CONFIRM_RESET=se_ewrs. Nothing defaults to yes.
  existing_tables="$(mysql -u "$MYSQL_USER" -N -B -e \
    "SELECT COUNT(*) FROM information_schema.TABLES
      WHERE TABLE_SCHEMA = 'se_ewrs' AND TABLE_TYPE = 'BASE TABLE'")"
  if [[ "$existing_tables" -gt 0 ]]; then
    printf '\n\033[1;31mWARNING: database se_ewrs already exists with %s tables.\033[0m\n' "$existing_tables"
    echo "Continuing DROPS AND RECREATES every table; all data in them is lost:"
    mysql -u "$MYSQL_USER" -N -B -e \
      "SELECT CONCAT('    ', TABLE_NAME, ': ~', TABLE_ROWS, ' rows')
         FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'se_ewrs' AND TABLE_TYPE = 'BASE TABLE'
          AND TABLE_NAME IN ('students', 'enrollments', 'assessment_results',
                             'risk_alerts', 'interventions', 'users')
        ORDER BY TABLE_NAME"
    echo "(Row counts are InnoDB estimates. Back up first with:"
    echo "    mysqldump -u ${MYSQL_USER} -p se_ewrs > se_ewrs-backup.sql )"
    if [[ "${SE_EWRS_CONFIRM_RESET:-}" == "se_ewrs" ]]; then
      echo "SE_EWRS_CONFIRM_RESET=se_ewrs is set; continuing."
    elif [[ -t 0 ]]; then
      read -rp "Type the database name (se_ewrs) to destroy and reload it, anything else to stop: " answer
      if [[ "$answer" != "se_ewrs" ]]; then
        echo "Stopped. The database was not touched."
        exit 1
      fi
    else
      echo "Stopped: no terminal to confirm on. The database was not touched." >&2
      echo "Set SE_EWRS_CONFIRM_RESET=se_ewrs to reload it unattended." >&2
      exit 1
    fi
  fi

  cd "$ROOT"
  # Order matters: schema creates the database, and every script carries
  # its own USE statement, so no database name is needed here.
  for script in schema views procedures triggers; do
    echo "  applying database/${script}.sql"
    mysql -u "$MYSQL_USER" < "database/${script}.sql"
  done

  # seed.sql scores every enrolment through the stored procedure, which
  # returns one result set per enrolment: ~180 lines of tables. Keep them
  # in a log instead of the terminal. Errors still go to stderr, and a
  # failed load still stops the script.
  seed_log="$(mktemp "${TMPDIR:-/tmp}/se-ewrs-seed.XXXXXX.log")"
  echo "  applying database/seed.sql (full output: ${seed_log})"
  mysql -u "$MYSQL_USER" < database/seed.sql > "$seed_log"
  echo "  rows loaded:"
  # The header row of the seed's own count summary, and the counts under it.
  sed -n '/^students\t/{N;p}' "$seed_log" | sed 's/^/    /'

  # Confirm the load rather than just reporting that mysql exited 0.
  echo "  risk distribution after seeding:"
  mysql -u "$MYSQL_USER" -B se_ewrs -e \
    'SELECT risk_category, COUNT(*) AS enrolments
       FROM v_latest_risk GROUP BY risk_category ORDER BY risk_category' \
    | sed 's/^/    /'
  unset MYSQL_PWD
  echo "demo data loaded."
fi

say "Done"
cat <<'NEXT'
Next steps:

  1. If you have not loaded the database yet (schema.sql DROPS every table
     of an existing se_ewrs, so do not run it over data you want to keep):
         mysql -u root -p < database/schema.sql
         mysql -u root -p se_ewrs < database/views.sql
         mysql -u root -p se_ewrs < database/procedures.sql
         mysql -u root -p se_ewrs < database/triggers.sql
         mysql -u root -p se_ewrs < database/seed.sql

  2. Check DB_USER / DB_PASSWORD in backend/.env

  3. Start the backend:
         cd backend && ./.venv/bin/python -m uvicorn app.main:app --reload --port 8000

  4. Start the frontend, in a second terminal:
         cd frontend && npm run dev

  5. Open http://localhost:5173 and sign in with
         admin@se-ewrs.edu  /  Demo@12345
NEXT
