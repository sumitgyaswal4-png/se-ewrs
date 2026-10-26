#!/usr/bin/env bash
# =====================================================================
# SE-EWRS one-shot local setup.
#
#   ./setup.sh            install dependencies only
#   ./setup.sh --db       also create the MySQL schema and demo data
#
# The --db step needs a MySQL account that can create a database. You
# will be prompted for its password; nothing is stored.
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MYSQL_USER="${MYSQL_USER:-root}"
LOAD_DB=false
[[ "${1:-}" == "--db" ]] && LOAD_DB=true

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
  cd "$ROOT"
  for script in schema views procedures triggers seed; do
    echo "  applying database/${script}.sql"
    mysql -u "$MYSQL_USER" -p < "database/${script}.sql"
  done
  echo "demo data loaded."
fi

say "Done"
cat <<'NEXT'
Next steps:

  1. If you have not loaded the database yet:
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
