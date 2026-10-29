# SE-EWRS — Student Engagement & Early Warning Risk System

A database-driven early-warning system for higher education. It
aggregates attendance, LMS engagement and assessment data, scores every
student–course enrolment with a transparent rule-based risk model, raises
early-warning alerts when a student crosses a threshold, and tracks the
interventions staff record against them.

**Database Management Systems course project · Department of Mathematics**
Mohammad Adnan · Lucky Dhall · Raja · Sumit

---

## Contents

1. [Problem statement](#1-problem-statement)
2. [Objectives and scope](#2-objectives-and-scope)
3. [Features](#3-features)
4. [User roles](#4-user-roles)
5. [Technology stack](#5-technology-stack)
6. [System architecture](#6-system-architecture)
7. [Database design](#7-database-design)
8. [Risk-scoring methodology](#8-risk-scoring-methodology)
9. [Important SQL](#9-important-sql)
10. [API overview](#10-api-overview)
11. [Security](#11-security)
12. [Installation](#12-installation)
13. [Running the application](#13-running-the-application)
14. [Demo accounts](#14-demo-accounts)
15. [Testing](#15-testing)
16. [Project structure](#16-project-structure)
17. [Troubleshooting](#17-troubleshooting)
18. [What is verified, and what is not](#18-what-is-verified-and-what-is-not)

---

## 1. Problem statement

Learning Management Systems already collect a great deal of data about
students — login frequency, attendance, assignment submission times,
assessment scores. That data is rarely used to identify students who are
struggling *before* their results deteriorate. By the time a failed
mid-term makes the problem visible, the useful window for support has
usually closed.

SE-EWRS turns that already-collected data into an early-warning signal:
it analyses engagement and academic performance, calculates a risk score,
identifies at-risk students, raises alerts, and gives instructors and
advisors somewhere to record what they did about it.

---

## 2. Objectives and scope

**Objectives**

- Design a normalised relational schema (3NF) for student engagement data
- Implement a transparent, configurable risk model whose output can always be explained
- Generate early-warning alerts automatically, without duplicates
- Track interventions and link them to the alerts that prompted them
- Enforce role-based access for five distinct staff roles, server-side
- Produce database-driven reports and analytics

**In scope** — staff-facing web application; attendance, LMS activity and
assessment capture; risk scoring; alert lifecycle; intervention tracking;
reporting with CSV export; audit logging.

**Out of scope** — live LMS integration (activity is entered through the
API or the seed script), a student-facing view, email/SMS notification,
and statistical or machine-learning scoring. The risk model here is
deliberately rule-based so that every score can be explained to the
student it describes.

---

## 3. Features

| Area | What it does |
|---|---|
| **Dashboard** | Headline counters, risk distribution, performance and attendance trends, risk by department, recent alerts. Every figure aggregated in SQL. |
| **Students** | CRUD with search, filters, sorting and pagination; per-student academic and engagement summary; full profile with a row per enrolled course; soft delete. |
| **Courses** | Catalogue with statistics, instructor assignment, class roster, single and bulk enrolment with duplicate prevention. |
| **Attendance** | Mark a whole session in one pass, idempotent re-marking, running totals, historical log. `LATE` counts as attended; `EXCUSED` is excluded from the calculation. |
| **LMS activity** | Login frequency, time on task, last-seen tracking, raw event log. |
| **Assessments** | Assignments, quizzes and examinations; class-wide marks entry with validation; server-derived percentages; performance trends. |
| **Risk analysis** | Score per enrolment with the full breakdown, contributing factors, weight re-normalisation when data is missing, and score history. |
| **Alerts** | Automatic generation, guaranteed single open alert per enrolment, validated status transitions, assignment, full status history. |
| **Interventions** | Six intervention types, action plans, follow-up dates, outcomes; linked to alerts; overdue follow-up queue. |
| **Reports** | Seven database-driven reports with filters, charts, tables and CSV export. |
| **Settings** | The risk model's weights, thresholds and data-sufficiency rules are configuration, editable without a redeployment. |
| **Audit** | Application events plus row-level changes captured by database triggers. |

---

## 4. User roles

| Role | Lands on | Can do |
|---|---|---|
| **Administrator** | Dashboard | Everything, including staff accounts and system settings |
| **Instructor** | Dashboard | Assessments and marks, attendance, risk recalculation, alert queue, interventions |
| **Teaching Assistant** | Attendance | Record attendance and LMS activity; assist with interventions. No grading. |
| **Academic Advisor** | Alerts | Work the alert queue, record counselling, update outcomes |
| **Department Chair** | Reports | Read-only oversight: statistics, reports, risk summaries. **No write permission at all.** |

Authorisation is expressed as named permissions and enforced on every
endpoint. The frontend hides what a role cannot use, but that is a
convenience — the server refusing the call is the actual control, and
`backend/tests/test_rbac.py` asserts it for every (role, endpoint) pair.

Full matrix: [`docs/api_documentation.md` §2](docs/api_documentation.md).

---

## 5. Technology stack

| Layer | Technology | Version |
|---|---|---|
| Frontend | React + Vite | 18.3.1 / 5.4.11 |
| Styling | Tailwind CSS | 3.4.17 |
| Charts | Recharts | 2.15.0 |
| Routing | React Router | 6.28.1 |
| HTTP | Axios | 1.7.9 |
| Backend | FastAPI | 0.115.5 |
| ORM | SQLAlchemy | 2.0.36 |
| Driver | PyMySQL | 1.1.1 |
| Validation | Pydantic | 2.9.2 |
| Auth | PyJWT + argon2-cffi | 2.9.0 / 23.1.0 |
| Database | MySQL | 8.0.16+ |
| Testing | pytest / Vitest | 8.3.4 / 2.1.8 |

MySQL **8.0.16 or newer** is required: the schema uses enforced `CHECK`
constraints, `STORED` generated columns, CTEs and window functions.

---

## 6. System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser — React 18 SPA (Vite)                                  │
│                                                                 │
│  pages/ ── layouts/ ── components/ ── charts/                   │
│      │                                                          │
│  hooks/useAuth  ·  hooks/useApi  ·  services/endpoints          │
└───────────────────────────┬─────────────────────────────────────┘
                            │  JSON over HTTP, Bearer JWT
                            │  (dev: proxied by Vite, so no CORS hop)
┌───────────────────────────▼─────────────────────────────────────┐
│  FastAPI                                                        │
│                                                                 │
│  api/        routers, dependencies, permission guards           │
│  schemas/    Pydantic request/response validation               │
│  services/   risk_engine · queries · audit · assessment rules   │
│  models/     SQLAlchemy ORM (mirrors schema.sql)                │
│  core/       config · security (Argon2id, JWT) · permissions    │
└───────────────────────────┬─────────────────────────────────────┘
                            │  SQLAlchemy / PyMySQL, pooled
┌───────────────────────────▼─────────────────────────────────────┐
│  MySQL 8                                                        │
│                                                                 │
│  16 tables  ·  12 views  ·  6 procedures  ·  3 functions        │
│  12 triggers  ·  composite indexes  ·  generated columns        │
└─────────────────────────────────────────────────────────────────┘
```

**Request flow** — a request carries a JWT; `get_current_user` resolves it
against the live `users` row (so a role change takes effect immediately);
`require_permissions` checks the named permission; the router validates
the body with Pydantic, calls a service, and the service issues SQL
through SQLAlchemy. Errors are normalised by centralised handlers into a
single envelope.

---

## 7. Database design

16 tables in third normal form.

| # | Table | Purpose |
|---|---|---|
| 1 | `departments` | Reference table for students, courses and staff |
| 2 | `users` | Staff accounts; `role` drives access control |
| 3 | `students` | Student records; soft-deleted, never removed |
| 4 | `courses` | Course catalogue, unique per code + academic term |
| 5 | `course_instructors` | M:N between courses and staff |
| 6 | `enrollments` | M:N between students and courses — **the spine** |
| 7 | `attendance_records` | One row per enrolment per class session |
| 8 | `lms_activity_logs` | Raw engagement telemetry |
| 9 | `assessments` | Assignments, quizzes, examinations |
| 10 | `assessment_results` | Marks; `percentage` maintained by trigger |
| 11 | `risk_assessments` | Append-only risk history |
| 12 | `risk_alerts` | Early-warning alerts; one open per enrolment |
| 13 | `alert_status_history` | Immutable trail of status transitions |
| 14 | `interventions` | Counselling, tutoring and follow-up records |
| 15 | `system_settings` | The risk model's tunable parameters |
| 16 | `audit_logs` | Written by the application and by triggers |

### The one structural decision worth knowing

**Every engagement fact references `enrollment_id`, never a
`(student_pk, course_pk)` pair.** An enrolment *is* a validated
student–course pair, so routing attendance, activity, results, risk and
interventions through it makes a record for a non-enrolled student
structurally impossible — and avoids a transitive dependency on every
fact table.

### ER diagram

The full Mermaid ER diagram, the cardinality summary, the normalisation
analysis (including two **deliberate** denormalisations and why each is
justified) and the indexing strategy are in
**[`docs/er_diagram.md`](docs/er_diagram.md)**.

### How duplicate alerts are made impossible

```sql
active_flag TINYINT GENERATED ALWAYS AS
    (CASE WHEN status = 'RESOLVED' THEN NULL ELSE 1 END) STORED,
UNIQUE KEY uq_alert_one_active_per_enrollment (enrollment_id, active_flag)
```

MySQL permits repeated `NULL`s inside a `UNIQUE` key. While an alert is
open `active_flag = 1`, so `(enrollment_id, 1)` can occur only once —
**one open alert per enrolment, maximum**. Once resolved it becomes
`NULL` and leaves the uniqueness check, so resolved history is unlimited.
This is enforced by the storage engine, not by application code.

---

## 8. Risk-scoring methodology

```
Risk Score = 0.35 × Attendance Risk
           + 0.40 × Academic Risk
           + 0.25 × Engagement Risk
```

Each component is on a 0–100 scale where higher means more at risk:

```
Attendance Risk = 100 − Attendance Percentage
Academic Risk   = 100 − Average Assessment Percentage
Engagement Risk = 100 − Engagement Score
```

The result is clamped to 0–100 and rounded half-up to two decimals.

| Band | Score |
|---|---|
| Low | 0–29 |
| Medium | 30–59 |
| High | 60–100 |
| **Needs more data** | not banded |

**Engagement Score** starts at 100 and loses points for inactivity
(recency), infrequent logins, missing submissions and late submissions.
The full penalty table is in
[`docs/database_design.md` §3.2](docs/database_design.md).

### Missing data is not evidence of poor performance

This is the part that matters most. A component with no supporting data
is **dropped**, and the remaining weights are **re-normalised**:

```
risk = Σ(wᵢ × riskᵢ for available i) / Σ(wᵢ for available i)
```

Consider a student with 80% attendance, perfect engagement, and no graded
work yet — three weeks into term:

| | if missing data were zeroed | **what this system does** |
|---|---|---|
| attendance risk 20 × 0.35 | 7.00 | 7.00 |
| academic risk **100** × 0.40 | 40.00 | *component excluded* |
| engagement risk 0 × 0.25 | 0.00 | 0.00 |
| available weight | 1.00 | 0.60 |
| **score** | **47.00 → MEDIUM RISK** | **11.67 → LOW RISK** |

Treating the absence of a grade as a zero would flag a perfectly engaged
student as at risk purely for being early in the term.

When fewer than two components are observable the profile is reported as
**`INSUFFICIENT_DATA`** with the reason attached, **no risk band is
assigned, and no alert is raised**.

### The score is an indicator, not a judgement

Attendance and engagement are proxies. Attendance drops for reasons that
have nothing to do with commitment — illness, caring responsibilities,
work, transport, a crisis at home. A high score means *something here is
worth asking about*, and the conversation, not the number, should
determine what happens next. The API returns this disclaimer with every
risk detail response, and the UI shows it.

### Two implementations, kept in step

The model exists twice by design: `sp_recalculate_risk_for_enrollment`
in SQL, and `app/services/risk_engine.py` in Python. They are kept in
agreement by one written specification, half-up rounding on both sides
(Python's built-in `round()` is banker's rounding, so the engine uses
`Decimal.quantize(..., ROUND_HALF_UP)`), and integer cross-multiplication
at the band boundaries instead of a float ratio.

---

## 9. Important SQL

### Views (12)

`v_enrollment_attendance` · `v_enrollment_academics` ·
`v_enrollment_activity` · `v_latest_risk` · `student_performance_view` ·
`course_attendance_summary` · `course_performance_summary` ·
`v_submission_patterns` · `student_risk_summary` ·
`department_risk_summary` · `v_active_alerts` · `v_intervention_outcomes`

```sql
-- Latest risk per enrolment, via a CTE and a window function
CREATE VIEW v_latest_risk AS
WITH ranked AS (
    SELECT ra.*,
           ROW_NUMBER() OVER (PARTITION BY ra.enrollment_id
                              ORDER BY ra.calculated_at DESC,
                                       ra.risk_id DESC) AS rn
    FROM risk_assessments ra
)
SELECT * FROM ranked WHERE rn = 1;
```

### Stored routines (9)

| Routine | Purpose |
|---|---|
| `fn_setting_num` | Read a tunable parameter with a fallback |
| `fn_engagement_score` | The engagement sub-model |
| `fn_risk_category` | Band a score, honouring data completeness |
| `sp_recalculate_risk_for_enrollment` | Score one enrolment and reconcile its alert, transactionally |
| `sp_recalculate_all_risk` | Cursor loop over every active enrolment |
| `sp_enroll_student` | Transactional enrolment with duplicate guard |
| `sp_record_attendance` | Idempotent attendance upsert |
| `sp_upsert_assessment_result` | Validated marks upsert |
| `sp_update_alert_status` | Validated status transition + history row |

```sql
CALL sp_recalculate_all_risk(NULL, 1);
CALL sp_update_alert_status(1, 'ACKNOWLEDGED', 8, 'Emailed the student.');
```

### Triggers (12)

Validation: `trg_ar_before_insert` / `trg_ar_before_update` own the
`percentage` column and the marks range check; `trg_assess_before_*`
guard the grading scale; `trg_intervention_before_insert` enforces a
cross-row rule a foreign key cannot express.

Audit: seven `AFTER` triggers append to `audit_logs`. They never copy
`password_hash`, and they use the null-safe `<=>` operator so a change to
or from `NULL` is detected. No trigger writes to its own table and
`audit_logs` has none, so there is no recursion. **Alert generation is
deliberately not in a trigger** — it lives in one procedure so the
raise/refresh/close decision stays a single atomic step.

### Analytical queries

`database/analytics_queries.sql` holds 15 documented, read-only queries
demonstrating joins, aggregates, `GROUP BY … HAVING`, scalar and
correlated subqueries, CTEs, window functions (`ROW_NUMBER`, `LAG`,
`SUM OVER`), `GROUP_CONCAT`, and an `EXPLAIN` showing the composite index
in use.

```bash
mysql -u root -p se_ewrs < database/analytics_queries.sql
```

Full reference with purpose and a runnable example for every view,
routine and trigger:
**[`docs/database_design.md`](docs/database_design.md)**.

---

## 10. API overview

62 routes. Interactive documentation at
**<http://localhost:8000/docs>**.

```
POST   /api/auth/login                       GET    /api/dashboard/summary
GET    /api/auth/me                          GET    /api/dashboard/recent-alerts
GET    /api/auth/permissions                 GET    /api/dashboard/performance-trend

GET    /api/students                         GET    /api/courses
POST   /api/students                         POST   /api/courses
GET    /api/students/{id}                    GET    /api/courses/{id}
GET    /api/students/{id}/profile            PUT    /api/courses/{id}
PUT    /api/students/{id}                    GET    /api/courses/{id}/roster
PATCH  /api/students/{id}/deactivate         POST   /api/courses/{id}/instructors

POST   /api/enrollments                      POST   /api/attendance
POST   /api/enrollments/bulk                 POST   /api/attendance/bulk
                                             GET    /api/attendance/summary
POST   /api/assessments                      GET    /api/activity/summary
POST   /api/assessment-results               POST   /api/activity
POST   /api/assessment-results/bulk

GET    /api/risk-assessments                 GET    /api/alerts
POST   /api/risk-assessments/recalculate     GET    /api/alerts/{id}
GET    /api/risk-assessments/{id}            PATCH  /api/alerts/{id}

POST   /api/interventions                    GET    /api/reports/risk-distribution
PUT    /api/interventions/{id}               GET    /api/reports/course-performance
                                             GET    /api/reports/export?report=…
GET    /api/settings                         GET    /api/settings/audit/logs
```

Full reference with request/response examples:
**[`docs/api_documentation.md`](docs/api_documentation.md)**.

---

## 11. Security

| Measure | Implementation |
|---|---|
| **Password hashing** | Argon2id (`argon2-cffi` defaults, per OWASP guidance). Salted per password; digests are transparently upgraded on sign-in if the parameters change. |
| **No hash exposure** | `password_hash` appears in no response schema — asserted against the generated OpenAPI document by a test. |
| **JWT with expiry** | HS256, 8-hour default. The role claim is re-checked against the database row on every request, so a role change or de-activation takes effect immediately. |
| **Server-side authorisation** | Named permissions on every endpoint. Asserted for every (role, endpoint) pair in `test_rbac.py`. |
| **No account enumeration** | An unknown email and a wrong password return the identical 401 and cost the same Argon2 verification, so neither the message nor the response time reveals whether an account exists. Both are audited. |
| **Login throttling** | 5 failed sign-ins for one email, or 20 from one client address, within 15 minutes, and further attempts get a 429 with `Retry-After` until the oldest failure ages out. Each attempt is counted before its password is checked, so a burst of parallel requests cannot exceed the limit; a correct password hands its slot back. A blocked attempt does no database or Argon2 work and writes no audit row. Counts are per process (one uvicorn worker); behind a reverse proxy, run uvicorn with `--proxy-headers`. Tunable with `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_ADDRESS` and `LOGIN_FAILURE_WINDOW_SECONDS`. |
| **CSV exports** | Any text cell starting with `=`, `+`, `-`, `@`, tab or CR is prefixed with `'`, so a name entered as a spreadsheet formula opens as plain text. |
| **SQL injection** | All access through SQLAlchemy with bound parameters. Even sortable column names are validated against an allowlist rather than interpolated — `test_system.py` fires an injection payload at the search endpoint and asserts it is treated as a literal string. |
| **Input validation** | Pydantic on every request body and query parameter, with database `CHECK` constraints behind it. |
| **Safe errors** | Internal failures are logged in full server-side; the client receives a generic message. Validation errors name the field but never echo the submitted value. |
| **Audit logging** | Application events plus trigger-captured row changes. Passwords are redacted by the audit helper and never written by a trigger. |
| **Secrets** | Environment variables only. `.env` is git-ignored; `.env.example` ships placeholders. `setup.sh` generates a fresh `SECRET_KEY`. There is no built-in fallback key: the backend refuses to start if `SECRET_KEY` is missing, shorter than 32 characters or still the placeholder. Only with `DEBUG=true` and no key does it generate a temporary one for that process. |
| **FK validation** | Enforced by MySQL; `PRAGMA foreign_keys=ON` is set per connection on SQLite so the test-suite enforces them too. |

**Before any real deployment:** generate a new `SECRET_KEY`, change every
demo password, create a MySQL user with only the privileges it needs
rather than using `root`, and serve over HTTPS.

---

## 12. Installation

### Prerequisites

| | Version | Check |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| MySQL | 8.0.16+ | `mysql --version` |

### Quick start

```bash
cd se-ewrs
./setup.sh          # dependencies only
./setup.sh --db     # …and create the schema and demo data
```

> **`--db` replaces an existing `se_ewrs` database.** `schema.sql` drops and
> recreates every table. If `se_ewrs` already holds tables, `setup.sh` lists
> what would be lost and continues only when you type the database name. With
> no terminal to ask on, it stops unless `SE_EWRS_CONFIRM_RESET=se_ewrs` is set.
> Back up first with `mysqldump -u root -p se_ewrs > se_ewrs-backup.sql`.

### Manual setup

**1 — Create the database and load everything**

Run the five scripts **in this order**; they are not independent.
`schema.sql` **drops every table** of an existing `se_ewrs`, so run it only
on a database whose contents you do not need.

```bash
mysql -u root -p < database/schema.sql        # creates the se_ewrs database
mysql -u root -p se_ewrs < database/views.sql
mysql -u root -p se_ewrs < database/procedures.sql
mysql -u root -p se_ewrs < database/triggers.sql
mysql -u root -p se_ewrs < database/seed.sql  # demo data; calls the procedure
```

Before that, `seed.sql` prints one small result table per enrolment as
the stored procedure scores it (about 180 lines). Redirect the output,
`… < database/seed.sql > seed.log`, to keep the terminal clear; errors
still appear, and `./setup.sh --db` does this for you.

`seed.sql` finishes by printing a row count and the risk distribution, so
you can confirm it worked:

```
students  courses  enrollments  attendance_rows  activity_rows  result_rows  risk_rows  alerts  interventions
      36        6           80             1694           5414          380         80      35             12
```

**2 — Create a database user** (recommended — do not run the app as `root`)

```sql
CREATE USER 'se_ewrs_app'@'localhost' IDENTIFIED BY 'a-strong-password';
GRANT SELECT, INSERT, UPDATE, DELETE ON se_ewrs.* TO 'se_ewrs_app'@'localhost';
GRANT EXECUTE ON se_ewrs.* TO 'se_ewrs_app'@'localhost';
FLUSH PRIVILEGES;
```

**3 — Configure the backend**

```bash
cp .env.example backend/.env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
# then edit DB_USER and DB_PASSWORD in backend/.env
```

**4 — Install dependencies**

```bash
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt

cd ../frontend
npm install
```

---

## 13. Running the application

Two terminals.

**Backend** — <http://localhost:8000>

```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Confirm it reached the database:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"connected","dialect":"mysql"}
```

**Frontend** — <http://localhost:5173>

```bash
cd frontend
npm run dev
```

Vite proxies `/api` to the backend, so there is no CORS round-trip in
development and the production build can sit behind the same reverse
proxy unchanged.

### Resetting the demo data

```bash
# From SQL — re-runnable, clears only the demo-owned tables
mysql -u root -p se_ewrs < database/seed.sql

# Or through the application, which also re-runs the risk engine
cd backend && ./.venv/bin/python -m app.db.seed --reset
```

The reset prompts for the database name before deleting anything, and
touches **only** the demo-owned tables. `system_settings` is deliberately
excluded, so a retuned risk model survives a reseed.

To regenerate `database/seed.sql` after changing the dataset:

```bash
cd backend && ./.venv/bin/python -m app.db.seed --emit-sql ../database/seed.sql
```

---

## 14. Demo accounts

Loaded by `database/seed.sql`. **Every account uses the password
`Demo@12345`.** These are fictional identities for demonstration; change
them before any real use.

| Role | Email | Lands on |
|---|---|---|
| Administrator | `admin@se-ewrs.edu` | Dashboard |
| Instructor | `rohit.khanna@se-ewrs.edu` | Dashboard |
| Instructor | `sneha.iyer@se-ewrs.edu` | Dashboard |
| Teaching Assistant | `tanvi.nair@se-ewrs.edu` | Attendance |
| Academic Advisor | `priya.menon@se-ewrs.edu` | Alerts |
| Academic Advisor | `deepak.sharma@se-ewrs.edu` | Alerts |
| Department Chair | `latika.rao@se-ewrs.edu` | Reports |

In development (`npm run dev`) the login page lists these with a **Use**
button that fills the form. A production build (`npm run build`) leaves
the list and the password out entirely, because those accounts should
not exist on a real deployment; build with `VITE_SHOW_DEMO_ACCOUNTS=true`
for a deliberate demo site.

**The demo data contains** 4 departments, 11 staff, 36 students, 6
courses, 80 enrolments, ~1,700 attendance records, ~5,400 LMS events, 30
assessments and 380 results — producing a realistic spread of **41 low**,
**26 medium** and **9 high** risk enrolments, plus **4 deliberately
unscored** profiles that demonstrate the missing-data handling.

All identities are invented. No real student record or personal data is
included. Dates are written as `CURDATE()` arithmetic rather than fixed
dates, so the demo stays current whenever it is loaded.

---

## 15. Testing

### Backend — 526 tests, 93% coverage

```bash
cd backend
./.venv/bin/python -m pytest                              # all
./.venv/bin/python -m pytest --cov=app --cov-report=term-missing
./.venv/bin/python -m pytest tests/test_risk_engine.py -v # one file
```

The suite runs against in-memory SQLite, so it needs no MySQL server and
leaves nothing behind. The ORM models, the aggregate SQL, the risk engine
and every router under test are the same code that runs against MySQL.

| File | Tests | Covers |
|---|---|---|
| `test_auth.py` | 31 | Sign-in, tokens, expiry, forged signatures, hashing, no hash exposure, failed-login throttling |
| `test_rbac.py` | 96 | Every (role, endpoint) pair against the permission matrix |
| `test_risk_engine.py` | 48 | The formula, bands, clamping, rounding, engagement rules, **missing-data handling** |
| `test_students.py` | 21 | CRUD, search, filters, sorting, soft delete, profile |
| `test_courses.py` | 17 | CRUD, instructor assignment, roster, term uniqueness |
| `test_enrollments.py` | 16 | Duplicate prevention, bulk skip, status changes |
| `test_attendance.py` | 16 | Recording, idempotency, **percentage calculation**, excused handling |
| `test_assessments.py` | 26 | Marks validation, **percentage derivation**, bulk atomicity |
| `test_risk_api.py` | 20 | Recalculation, the table, the explanation, weight re-normalisation |
| `test_alerts.py` | 30 | Generation, **duplicate prevention at the constraint**, transitions, auto-resolution |
| `test_interventions.py` | 22 | Recording, alert linkage, date validation, follow-up queue |
| `test_reports.py` | 36 | Report accuracy against hand-computed figures, CSV export and its formula escaping |
| `test_system.py` | 36 | Health, settings validation, audit trail, error envelopes, SQL-injection payload, startup `SECRET_KEY` checks, database URL encoding |
| `test_seed.py` | 27 | Demo dataset properties, risk spread, reseed idempotency |
| `test_api_docs.py` | 76 | Every served endpoint is documented; every documented permission matches what is enforced |
| `test_report_docs.py` | 8 | The written report: appendices match the files they copy; figures, tables, citations and contents are numbered, listed and resolve |

**`test_api_docs.py` checks the documentation itself.** It reads the
routes off the running app and the tables out of
[`docs/api_documentation.md`](docs/api_documentation.md), then asserts
that every served endpoint has a row and that no row claims a stricter
permission than the code enforces. A permission column that overstates
the rule reads like a security guarantee while being fiction, so it is
tested rather than trusted. Both failure modes were confirmed by
deliberately introducing them: an undocumented endpoint and a row
claiming `attendance:write` where `attendance:read` is enforced were
each caught.

### Frontend — 98 tests

```bash
cd frontend
npm test          # run once
npm run test:watch
```

Covers formatting helpers (including that missing data renders as an em
dash, never `0%`), the risk badge (icon and label always present, so
colour is never the only cue), the data table's four states and
server-side sorting, chart rendering, role-based navigation, the
data-fetching hook's state machine, the API error handling (a 401 signs
the user out, a 429 does not), the login page and its demo panel, the meter colouring
(a poor figure must never be drawn in a reassuring colour) and the trend
chart (a legend must never name a line the chart cannot draw).

---

## 16. Project structure

```
se-ewrs/
├── backend/
│   ├── app/
│   │   ├── api/          routers, dependencies, permission guards
│   │   ├── core/         config, security, permissions, exceptions
│   │   ├── db/           engine, session, base, seed generator
│   │   ├── models/       SQLAlchemy ORM (mirrors schema.sql)
│   │   ├── schemas/      Pydantic request/response models
│   │   ├── services/     risk_engine, queries, audit, assessment rules
│   │   └── main.py       application entry point
│   ├── tests/            526 tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   shared UI, including charts/
│   │   ├── layouts/      app shell and navigation
│   │   ├── pages/        17 routed pages
│   │   ├── services/     axios client and endpoint map
│   │   ├── hooks/        useAuth, useApi, useToast
│   │   ├── utils/        formatting, chart tokens, constants
│   │   └── App.jsx       routing and guards
│   ├── package.json
│   └── vite.config.js
├── database/
│   ├── schema.sql            16 tables, keys, constraints, indexes
│   ├── views.sql             12 analytical views
│   ├── procedures.sql        3 functions + 6 procedures
│   ├── triggers.sql          12 triggers
│   ├── seed.sql              demo data (generated)
│   ├── analytics_queries.sql 15 documented queries
│   ├── scale_test.sql        synthetic benchmark dataset (170× the demo)
│   └── scale_test.sh         builds and times it, in its own database
├── docs/
│   ├── er_diagram.md         ER diagram, cardinality, normalisation, indexes
│   ├── database_design.md    design decisions, risk spec, full SQL reference
│   ├── api_documentation.md  endpoint reference with examples
│   ├── user_guide.md         guide for the five staff roles
│   ├── report.md             the full written report: front matter, nine chapters, references
│   ├── report_appendices.md  Appendices A–E (generated — do not edit by hand)
│   ├── build_appendices.py   regenerates the appendices; --capture re-runs the queries
│   ├── analytics_output/     captured MySQL output of the 15 queries, for Appendix C
│   ├── figures/              rendered ER diagrams for the report, and their renderer
│   ├── report_outline.md     chapter skeleton for the written submission
│   └── screenshots/          15 captioned screenshots of the running app
├── .env.example
├── .gitignore
├── setup.sh
└── README.md
```

---

## 17. Troubleshooting

<details><summary><b>Backend: <code>Access denied for user …</code></b></summary>

The credentials in `backend/.env` do not match MySQL. Verify them:

```bash
mysql -u se_ewrs_app -p se_ewrs -e "SELECT 1;"
```

If that fails, re-create the user (§12 step 2). Note that `DB_PASSWORD`
containing `#` or `$` may need quoting in `.env`.
</details>

<details><summary><b>Backend: <code>Can't connect to MySQL server</code></b></summary>

MySQL is not running.

```bash
sudo systemctl status mysql     # Linux
brew services list              # macOS
sudo systemctl start mysql
```

Then confirm the API can reach it: `curl http://localhost:8000/health`
reports `"database": "unavailable"` when it cannot.
</details>

<details><summary><b>Backend: <code>cryptography package is required</code></b></summary>

MySQL 8 defaults to `caching_sha2_password`, which PyMySQL needs
`cryptography` for. It is in `requirements.txt`; reinstall:

```bash
cd backend && ./.venv/bin/python -m pip install -r requirements.txt
```
</details>

<details><summary><b><code>schema.sql</code> fails on CHECK or GENERATED</b></summary>

Your MySQL is older than 8.0.16. Check with `mysql --version`. Earlier
versions parse `CHECK` constraints but silently ignore them, and do not
support `STORED` generated columns — which the duplicate-alert guard
depends on. Upgrade to 8.0.16+.
</details>

<details><summary><b><code>views.sql</code> fails with "table doesn't exist"</b></summary>

The scripts must run in order. Re-run from the start:
`schema → views → procedures → triggers → seed`.
</details>

<details><summary><b><code>seed.sql</code> fails on <code>CALL sp_recalculate_all_risk</code></b></summary>

`procedures.sql` was not loaded, or was loaded into the wrong database.
Confirm:

```sql
USE se_ewrs;
SHOW PROCEDURE STATUS WHERE Db = 'se_ewrs';
```

You should see six procedures. If not, re-run `procedures.sql`.
</details>

<details><summary><b>Frontend: "Could not reach the API"</b></summary>

The backend is not running on port 8000. Start it, then check
<http://localhost:8000/health>. If the backend is on a different port,
set `VITE_API_TARGET` before `npm run dev`:

```bash
VITE_API_TARGET=http://127.0.0.1:9000 npm run dev
```
</details>

<details><summary><b>Dashboard shows zeros and the charts are empty</b></summary>

Either no data is loaded, or no risk run has happened. Load `seed.sql`,
or press **Recalculate risk** on the dashboard — risk is calculated on
demand, not continuously.
</details>

<details><summary><b>Everyone shows "Needs more data"</b></summary>

Expected before the first recalculation. Press **Recalculate risk**. If
it persists, those enrolments genuinely lack data: fewer than
`risk.min_sessions` attendance records and no graded assessments. The
risk detail page names the missing component.
</details>

<details><summary><b>Sign-in returns 401 with the correct demo password</b></summary>

The seed may not have loaded, or loaded into another database. Check:

```sql
SELECT email, role, LEFT(password_hash, 9) FROM se_ewrs.users;
```

The hash should start with `$argon2id`. If the table is empty, re-run
`seed.sql`.
</details>

<details><summary><b>You cannot get MySQL credentials on your machine</b></summary>

If `mysql -u root` is denied and you cannot get the password or sudo
rights, you do not need them: `mysqld` runs as an ordinary user against
its own data directory, so you can start a completely private MySQL that
does not touch the system one.

```bash
DIR=~/se-ewrs-mysql
mkdir -p "$DIR/data" "$DIR/tmp"

# One-off: create the data directory with a passwordless root
mysqld --initialize-insecure --datadir="$DIR/data" \
       --tmpdir="$DIR/tmp" --log-error="$DIR/init.log"

# Start it on a spare port, in the background
mysqld --datadir="$DIR/data" --tmpdir="$DIR/tmp" \
       --port=3307 --socket=/tmp/sewrs.sock --mysqlx=0 \
       --log-error="$DIR/server.log" &

# Load the project
mysql --socket=/tmp/sewrs.sock -u root < database/schema.sql
mysql --socket=/tmp/sewrs.sock -u root se_ewrs < database/views.sql
mysql --socket=/tmp/sewrs.sock -u root se_ewrs < database/procedures.sql
mysql --socket=/tmp/sewrs.sock -u root se_ewrs < database/triggers.sql
mysql --socket=/tmp/sewrs.sock -u root se_ewrs < database/seed.sql
```

Point the backend at it in `backend/.env`:

```
DATABASE_URL=mysql+pymysql://root@localhost/se_ewrs?unix_socket=/tmp/sewrs.sock&charset=utf8mb4
```

Stop it with `mysqladmin --socket=/tmp/sewrs.sock -u root shutdown`.

Two things to watch: the Unix socket path has a hard **107-character
limit**, so keep it short — a long path fails with *"The socket file path
is too long"*. And this instance has a passwordless root, so it is for
local development only.
</details>

<details><summary><b>Tests fail with an import error</b></summary>

Run them from the `backend/` directory using the virtual environment's
interpreter:

```bash
cd backend && ./.venv/bin/python -m pytest
```
</details>

---

## 18. What is verified, and what is not

Stated plainly, because a claim in a README is worth nothing without it.

### Verified by running it

**Against real MySQL 8.0.46** (default `sql_mode`, which includes
`ONLY_FULL_GROUP_BY` — the strictest setting, and the one most `GROUP BY`
queries fail under):

- All five scripts load with **zero errors**, in the documented order,
  each printing its success line. `seed.sql` loads in about 9 seconds.
- The objects they create: **16 tables, 12 views, 6 procedures, 3
  functions, 12 triggers, 27 foreign keys, 14 CHECK constraints, 12
  unique keys, 77 indexes**.
- All 12 views return rows.
- All 15 queries in `analytics_queries.sql` run cleanly.
- `EXPLAIN` confirms the composite index is used: the risk engine's
  hottest predicate picks `ix_lms_enrollment_time` as a covering range
  scan touching 26 rows out of 5,414.

**The constraints and triggers actually fire:**

| Check | Result |
|---|---|
| Second open alert for one enrolment | `ERROR 1062 Duplicate entry '4-1' for key 'uq_alert_one_active_per_enrollment'` |
| Two resolved alerts + one open, same enrolment | accepted — 3 rows, 1 open (repeated NULLs behave as designed) |
| `INSERT` marks without supplying `percentage` | trigger derives `15.00/20.00 → 75.00` |
| Marks above `max_marks` | `ERROR 1644 assessment_results: marks_obtained exceeds max_marks` |
| Negative marks | `ERROR 1644 … cannot be negative` |
| Intervention citing another enrolment's alert | `ERROR 1644 … belongs to a different enrollment` |
| Duplicate enrolment via `sp_enroll_student` | `ERROR 1644 … already enrolled in this course` |
| Illegal alert transition via `sp_update_alert_status` | `ERROR 1644 … illegal status transition` |
| `sp_record_attendance` run twice for one session | 1 row, corrected — not duplicated |
| Audit triggers on a student update | both old and new values recorded |
| A no-op `UPDATE` | writes **no** audit row |
| Any password or hash in `audit_logs` | **0 rows** |

**The two risk implementations agree.** The stored procedure scored all
80 enrolments, then the Python engine scored the same MySQL rows: **zero
mismatches** on score, band and completeness flag. `fn_engagement_score(21,
2, 12, 1, 2, 5)` returns `29.00` in SQL — the same value the Python test
asserts. Both produce the identical distribution: **9 high, 26 medium, 41
low, 4 unscored**.

**The application on MySQL:**

- The backend starts against MySQL and reports `{"dialect": "mysql"}`
- Full end-to-end over HTTP: sign-in for all five roles, role-based
  redirection, dashboard figures, risk table and detail, alert
  transitions, duplicate prevention, marks validation, all seven reports,
  CSV export, and RBAC returning 403 where it should
- Every one of the 17 pages rendered in real Chrome against the
  MySQL-backed API with **no console errors, page errors or failed
  requests**, and no horizontal overflow at 390px

**`setup.sh --db`, run end to end** against a clean MySQL: it installs
both dependency sets, generates `backend/.env` with a fresh 64-character
`SECRET_KEY`, applies all five SQL scripts in order and prints the
resulting risk distribution — which came back as the documented **41 low,
26 medium, 9 high, 4 needing more data**. The script re-runs safely: the
schema drops its tables in reverse dependency order and the seed clears
them first.

**Rebuilt from nothing**, to check that the repository is actually
self-sufficient: a brand-new empty MySQL instance, then `setup.sh --db`
and nothing else. It reproduced **all 80 risk scores to the last
decimal** — enrolment 28 at 77.80, enrolment 34 at 2.72, enrolment 74 at
68.10, and so on for every row — along with the same 35 alerts and the
same 41/26/9/4 distribution. Two things follow: the seed is genuinely
deterministic despite writing its dates as `CURDATE()` arithmetic, and
the five SQL scripts need nothing that is not in this repository. The
application was then driven through **every page as all five roles — 51
page loads — with no console errors, page errors or failed requests**.

**Independently of the database:**

- 526 backend tests pass (93% coverage); 98 frontend tests pass
- The production build succeeds

**Under concurrency** (real threads against real MySQL, released from a
barrier so they fire at the same instant):

| Race | Result |
|---|---|
| 20 threads insert an open alert for one enrolment | **1 succeeded, 19 refused** by the unique key; exactly 1 open alert |
| 16 threads `CALL sp_recalculate_risk_for_enrollment` on a HIGH-risk student | all 16 completed, **exactly 1 alert**, no deadlocks |
| 12 threads enrol the same student in the same course | **1 enrolled, 11 refused** |

The second is the realistic one: two staff pressing **Recalculate** at
the same moment. The constraint holds, and a full run over the 6,000
enrolments that `./database/scale_test.sh` generates raises **1,748
alerts with zero enrolments holding two**.

**At scale** — a synthetic dataset 170× the demo (2,000 students, 6,000
enrolments, ~450,000 fact rows). This is where stress-testing earned its
keep: it exposed a **132× performance bug** in the recalculation
procedure, which read its inputs from a view and so aggregated the whole
dataset on every call.

| | before | after |
|---|---|---|
| one enrolment | 4,406 ms | **33.5 ms** |
| all 6,000 | ~7 hours (projected) | **82 seconds** |

The fix reads the base tables with an `enrollment_id` predicate instead.
Output is **byte-identical** — both versions scored the same 80 demo
enrolments and every field matched, including the generated
contributing-factors text. Details in
[`docs/database_design.md` §9](docs/database_design.md).

**The same bug was in the application layer**, and cost a page rather
than a batch job: the endpoints that want one enrolment's figures
filtered the *result* of a whole-table aggregate instead of restricting
the aggregate. Opening one student's profile took 3.4 s. The roll-ups in
`services/queries.py` now take an optional `limit_to` that pushes the
enrolment predicate inside the aggregate:

| Endpoint | Before | After | |
|---|---|---|---|
| `GET /api/students/{pk}/profile` | 3,377 ms | **81 ms** | 42× |
| `GET /api/risk-assessments/{id}` | 3,725 ms | **79 ms** | 47× |
| `GET /api/courses/{pk}/roster` | 3,381 ms | **160 ms** | 21× |
| `GET /api/alerts/{id}` | 3,496 ms | **61 ms** | 57× |

Verified the same way: **157 responses** — every risk detail, student
profile, course roster and alert in the demo database — captured before
and after and compared byte for byte. Identical. And where `limit_to` is
not passed, the compiled SQL is unchanged, so nothing else moved.

**The two paginated lists** were the last slow reads, at 7.7–7.9 s. A
list cannot restrict its aggregates to its page, because the page is not
known until the query has run — but it does not need to, because nothing
selects the page *by* those aggregates. Each endpoint now chooses its
page without them and computes them for the twenty rows that came back:

| Endpoint | Before | After | |
|---|---|---|---|
| `GET /api/students` | 7,661 ms | **643 ms** | 12× |
| `GET /api/risk-assessments` | 7,852 ms | **777 ms** | 10× |

Checked across **77 responses** — five sort columns in both directions
over multiple pages, every risk band, eight filter combinations and two
deliberately empty results — captured before and after. Identical.

Every composite read in the API is now below a second on the
6,000-enrolment dataset.

### Not verified

- MySQL was verified on **8.0.46 on Linux**. Other 8.0.x patch releases
  and other platforms should behave identically but were not tried.
- The scale figures come from a synthetic dataset, not from real data
  at that size. `./database/scale_test.sh` regenerates it and reprints
  the timings; it builds `se_ewrs_scale` and never touches `se_ewrs`.

## Licence

Academic coursework, submitted for assessment. Not licensed for
production use without review.
# se-ewrs
