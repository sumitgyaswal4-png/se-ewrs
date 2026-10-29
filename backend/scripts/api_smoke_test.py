"""Smoke-test a running API over HTTP, against the demo data.

    python -m scripts.api_smoke_test http://127.0.0.1:8000 [--allow-writes]
        [--accounts FILE]

``--accounts`` names the private file scripts/init_remote_db.py writes,
whose "email  password" lines replace the published demo password on a
deployed database. Without it the seed's shared password is used.

Checks what the unit tests cannot, because they use SQLite and an
in-process client: the real server, on MySQL, through real HTTP.

1. every demo role can sign in, and no response carries a password hash;
2. every GET route answers each role exactly as ``ROLE_PERMISSIONS`` says
   (200/404 when granted, 403 when not), and 401 with no or a forged token;
3. a write the role lacks is refused;
4. failed sign-ins lock an account with a 429 and ``Retry-After``, the same
   for an email with no account, without locking anyone else; and a burst
   of concurrent guesses gets no further than sequential ones;
5. with ``--allow-writes`` only: a course renamed to a spreadsheet formula
   comes out of the CSV export escaped. The name is restored afterwards.
   Use this only on a disposable database.

Step 4 locks two demo accounts, and an unknown email, for 15 minutes.
Exits non-zero if anything is wrong.
"""

import argparse
import csv
import io
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

# Importing the app only to read its route table and permission map; the
# requests below all go over HTTP. These defaults just let it import.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "smoke-test-import-only-" + "x" * 16)

import httpx  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from app.api.deps import get_current_user, require_permissions  # noqa: E402
from app.core.permissions import permissions_for  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "Demo@12345"
ACCOUNTS = {
    "ADMIN": "admin@se-ewrs.edu",
    "INSTRUCTOR": "rohit.khanna@se-ewrs.edu",
    "TA": "tanvi.nair@se-ewrs.edu",
    "ADVISOR": "priya.menon@se-ewrs.edu",
    "CHAIR": "latika.rao@se-ewrs.edu",
}
#: Path parameters filled in for the route sweep.
FILL = {"setting_key": "risk.weight.attendance"}
QUERY = {"/api/reports/export": {"report": "risk-distribution"}}


def _guards(dependant, auth, perms):
    if dependant.call is get_current_user:
        auth.add(True)
    if isinstance(dependant.call, require_permissions):
        perms.update(dependant.call.permissions)
    for dep in dependant.dependencies:
        _guards(dep, auth, perms)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url")
    parser.add_argument("--allow-writes", action="store_true",
                        help="also run step 5, which renames and restores a course")
    parser.add_argument("--accounts", help="file of 'email  password' lines")
    args = parser.parse_args(argv)
    passwords = {}
    if args.accounts:
        for line in open(args.accounts):
            parts = line.split()
            if len(parts) == 2 and "@" in parts[0] and not line.startswith("#"):
                passwords[parts[0]] = parts[1]
    base = args.base_url.rstrip("/")
    http = httpx.Client(base_url=base, timeout=60)
    problems = []

    def check(ok, label):
        """Record a problem when ``ok`` is false; returns True if it was."""
        if not ok:
            problems.append(label)
        return not ok

    def login(email, password=None):
        password = password or passwords.get(email, PASSWORD)
        return http.post("/api/auth/login", json={"email": email, "password": password})

    # 1 -----------------------------------------------------------------
    tokens = {}
    for role, email in ACCOUNTS.items():
        response = login(email)
        if not check(response.status_code == 200, f"sign in as {role}: {response.status_code}"):
            tokens[role] = response.json()["access_token"]
            check(response.json()["user"]["role"] == role, f"{role} signed in with another role")
            check("password_hash" not in response.text, f"{role} sign-in returns a hash")
    if len(tokens) < len(ACCOUNTS):
        print("Could not sign in as every role; is the demo data loaded?")
        for problem in problems:
            print("  -", problem)
        return 1
    print(f"[1] signed in as all {len(tokens)} roles")

    # 2 -----------------------------------------------------------------
    pairs = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods:
            continue
        auth, perms = set(), set()
        _guards(route.dependant, auth, perms)
        if not auth:
            continue
        path = re.sub(r"\{(\w+)\}", lambda m: FILL.get(m.group(1), "1"), route.path)
        params = QUERY.get(route.path, {})
        for label, headers in (("no token", {}), ("forged token", {"Authorization": "Bearer x.y.z"})):
            status = http.get(path, params=params, headers=headers).status_code
            check(status == 401, f"{label} GET {path}: {status}")
        for role, token in tokens.items():
            expected = {200, 404} if perms <= permissions_for(role) else {403}
            status = http.get(path, params=params,
                              headers={"Authorization": f"Bearer {token}"}).status_code
            check(status in expected, f"{role} GET {path}: {status}, expected {sorted(expected)}")
            pairs += 1
    print(f"[2] {pairs} (role, GET route) pairs match the permission map; 401 without a valid token")

    # 3 -----------------------------------------------------------------
    status = http.put("/api/settings/alert.min_score", json={"setting_value": "31"},
                      headers={"Authorization": f"Bearer {tokens['CHAIR']}"}).status_code
    check(status == 403, f"CHAIR changing a setting: {status}")
    status = http.post("/api/students", json={},
                       headers={"Authorization": f"Bearer {tokens['TA']}"}).status_code
    check(status == 403, f"TA creating a student: {status}")
    print("[3] writes outside the role are refused")

    # 4 -----------------------------------------------------------------
    victim = "sneha.iyer@se-ewrs.edu"
    first = [login(victim, "wrong").status_code for _ in range(5)]
    check(first == [401] * 5, f"first five failures: {first}")
    blocked = login(victim)  # the right password, still refused
    check(blocked.status_code == 429, f"sixth attempt: {blocked.status_code}")
    retry_after = int(blocked.headers.get("Retry-After", "0"))
    check(1 <= retry_after <= 900, f"Retry-After: {retry_after}")
    ghost = "nobody-here@se-ewrs.edu"
    for _ in range(5):
        login(ghost, "wrong")
    check(login(ghost, "wrong").json() == blocked.json(), "an unknown email locks differently")
    check(login("arup.banerjee@se-ewrs.edu").status_code == 200, "another account was locked too")

    def guess(_):
        return httpx.post(f"{base}/api/auth/login", timeout=60,
                          json={"email": "meher.qureshi@se-ewrs.edu", "password": "wrong"}).status_code

    with ThreadPoolExecutor(max_workers=20) as pool:
        burst = list(pool.map(guess, range(20)))
    check(burst.count(401) == 5 and burst.count(429) == 15, f"concurrent burst: {sorted(burst)}")
    print(f"[4] lockout after 5 failures (Retry-After {retry_after}s); "
          f"20 concurrent guesses: {burst.count(401)} checked, {burst.count(429)} refused")

    # 5 -----------------------------------------------------------------
    if args.allow_writes:
        admin = {"Authorization": f"Bearer {tokens['ADMIN']}"}
        course = http.get("/api/courses/1", headers=admin).json()
        fields = ("course_code", "course_name", "dept_id", "semester", "credits",
                  "academic_term", "total_sessions")
        payload = {key: course[key] for key in fields if key in course}
        original = payload["course_name"]
        formula = '=HYPERLINK("http://evil.example","x")'
        try:
            payload["course_name"] = formula
            check(http.put("/api/courses/1", json=payload, headers=admin).status_code == 200,
                  "renaming the course")
            export = http.get("/api/reports/export", params={"report": "course-performance"},
                              headers=admin)
            cells = [cell for row in csv.reader(io.StringIO(export.text)) for cell in row]
            check("'" + formula in cells, "the formula is not escaped in the CSV")
            check(not any(cell.startswith(("=", "+", "@")) for cell in cells),
                  "a CSV cell still starts with a formula character")
        finally:
            payload["course_name"] = original
            check(http.put("/api/courses/1", json=payload, headers=admin).status_code == 200,
                  "restoring the course name")
        print("[5] the CSV export escaped a formula; the course name is restored")
    else:
        print("[5] skipped (pass --allow-writes on a disposable database)")

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print("  -", problem)
        return 1
    print("0 problems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
