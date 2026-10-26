# SE-EWRS — API Reference

Base URL `http://localhost:8000/api` · Interactive docs at
[`/docs`](http://localhost:8000/docs) (Swagger UI) and
[`/redoc`](http://localhost:8000/redoc).

---

## 1. Authentication

Every endpoint except `POST /api/auth/login`, `GET /`, `GET /health` and
the docs requires a bearer token.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@se-ewrs.edu","password":"Demo@12345"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s http://localhost:8000/api/dashboard/summary -H "Authorization: Bearer $TOKEN"
```

In Swagger UI, click **Authorize** and paste the token once.

The token is a JWT signed with `SECRET_KEY` (HS256) carrying `sub`, `uid`,
`role`, `iat` and `exp`. It expires after `ACCESS_TOKEN_EXPIRE_MINUTES`
(default 480 = 8 hours). The role claim is checked against the database
row on every request, so a role change or de-activation takes effect
immediately rather than at expiry.

`password_hash` is never present in any response. A test asserts this
against the generated OpenAPI schema
(`tests/test_system.py::test_openapi_never_exposes_a_password_hash_field`).

---

## 2. Authorisation

Permissions are named, not role checks scattered through the routers.
`GET /api/auth/permissions` returns the caller's own set; the frontend
uses it to build its navigation, and every endpoint enforces it.

| Permission | ADMIN | INSTRUCTOR | TA | ADVISOR | CHAIR |
|---|:-:|:-:|:-:|:-:|:-:|
| `students:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `students:write` | ✓ | | | | |
| `courses:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `courses:write` | ✓ | | | | |
| `enrollments:write` | ✓ | ✓ | | | |
| `attendance:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `attendance:write` | ✓ | ✓ | ✓ | | |
| `activity:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `activity:write` | ✓ | | ✓ | | |
| `assessments:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `assessments:write` | ✓ | ✓ | | | |
| `results:write` | ✓ | ✓ | | | |
| `risk:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `risk:recalculate` | ✓ | ✓ | | | |
| `alerts:read` | ✓ | ✓ | | ✓ | ✓ |
| `alerts:write` | ✓ | ✓ | | ✓ | |
| `interventions:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `interventions:write` | ✓ | ✓ | ✓ | ✓ | |
| `reports:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `settings:read` / `settings:write` | ✓ | | | | |
| `users:read` / `users:write` | ✓ | | | | |
| `audit:read` | ✓ | | | | |

The Department Chair has **no write permission at all** — it is an
oversight role by design.

Source of truth: `backend/app/core/permissions.py`.
Enforcement is asserted for every (role, endpoint) pair in
`backend/tests/test_rbac.py`.

---

## 3. Conventions

### Error envelope

```json
{ "detail": "Human-readable explanation", "error_code": "conflict" }
```

Validation failures add a `problems` array naming the offending fields
(never their submitted values):

```json
{
  "detail": "Request validation failed",
  "error_code": "validation_error",
  "problems": [{ "field": "semester", "message": "Input should be less than or equal to 12" }]
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 400 | `app_error` | Generic client error |
| 401 | `unauthenticated` | Missing, invalid or expired token |
| 403 | `forbidden` | Authenticated, but the role lacks the permission |
| 404 | `not_found` | No such record |
| 409 | `conflict` / `integrity_error` | Duplicate, or a disallowed state transition |
| 422 | `validation_error` | Request body or query failed validation |
| 500 | `internal_error` / `database_error` | Logged in full server-side; the client gets a generic message |

### Pagination

List endpoints take `page` (≥1, default 1) and `page_size` (1–200,
default 20) and return:

```json
{ "items": [...], "total": 80, "page": 1, "page_size": 20, "pages": 4 }
```

### Dates

Dates are `YYYY-MM-DD`, timestamps are ISO-8601. Date-range filters are
inclusive at both ends.

---

## 4. Endpoints

### 4.1 Authentication — `/api/auth`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/login` | public | Sign in; returns token, user, permissions and `home_route` |
| GET | `/me` | any signed-in | The caller's profile |
| GET | `/permissions` | any signed-in | The caller's permission list |
| POST | `/change-password` | any signed-in | Change your own password |
| GET | `/users` | `users:read` | List staff (paginated; `search`, `role`, `dept_id`, `is_active`) |
| GET | `/users/assignable` | any signed-in | Instructors/advisors/admins an alert can be assigned to |
| POST | `/users` | `users:write` | Create a staff account |
| PUT | `/users/{user_id}` | `users:write` | Update a staff account |

<details><summary><code>POST /api/auth/login</code></summary>

```json
// request
{ "email": "admin@se-ewrs.edu", "password": "Demo@12345" }

// 200
{
  "access_token": "eyJhbGciOi…",
  "token_type": "bearer",
  "expires_in_minutes": 480,
  "user": { "user_id": 1, "full_name": "Anita Verma", "email": "admin@se-ewrs.edu",
            "role": "ADMIN", "dept_id": 1, "is_active": true },
  "permissions": ["alerts:read", "alerts:write", "..."],
  "home_route": "/dashboard"
}
```
An unknown email and a wrong password both return the identical 401
`"Incorrect email or password"`, so the endpoint cannot be used to
enumerate accounts. Both outcomes are written to `audit_logs`.
</details>

### 4.2 Reference data

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/enums` | any signed-in | Every ENUM value with a display label — the UI's dropdown source |
| GET | `/departments` | any signed-in | List departments |
| POST | `/departments` | `settings:write` | Create a department |
| GET | `/course-options` | `courses:read` | Lightweight course list for filters |
| GET | `/student-options` | `courses:read` | Lightweight student list for enrolment pickers |

### 4.3 Dashboard — `/api/dashboard`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/summary` | `reports:read` | Headline counters, risk counts, averages, alert and intervention totals |
| GET | `/recent-alerts` | `reports:read` | Most recent alerts, highest risk first (`limit`, `only_open`) |
| GET | `/performance-trend` | `reports:read` | Monthly assessment mean + attendance rate (`course_pk`, `months`) |

Every figure is aggregated in SQL. With an empty database the counters
return `0` and the averages return `null` — never a hardcoded value.

### 4.4 Students — `/api/students`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `students:read` | List with search, filters, sorting, pagination and a per-student summary |
| POST | `` | `students:write` | Add a student |
| GET | `/{student_pk}` | `students:read` | One student |
| GET | `/{student_pk}/profile` | `students:read` | Summary + a row per enrolled course |
| PUT | `/{student_pk}` | `students:write` | Update |
| PATCH | `/{student_pk}/deactivate` | `students:write` | Soft delete |
| PATCH | `/{student_pk}/reactivate` | `students:write` | Restore |

Filters: `search` (roll/name/email), `dept_id`, `semester`,
`enrollment_year`, `is_active`, `risk_category`.
Sorting: `sort_by` ∈ {`student_id`, `full_name`, `semester`,
`enrollment_year`, `created_at`}, `sort_dir` ∈ {`asc`, `desc`}. An
unrecognised `sort_by` is rejected with 422 — the value never reaches SQL.

### 4.5 Courses — `/api/courses`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `courses:read` | List with statistics (headcount, attendance, marks, high-risk count) |
| POST | `` | `courses:write` | Create |
| GET | `/{course_pk}` | `courses:read` | One course |
| PUT | `/{course_pk}` | `courses:write` | Update |
| GET | `/{course_pk}/roster` | `courses:read` | Enrolled students with their risk band |
| POST | `/{course_pk}/instructors` | `courses:write` | Assign an instructor |
| DELETE | `/{course_pk}/instructors/{user_id}` | `courses:write` | Unassign |

### 4.6 Enrolments — `/api/enrollments`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `courses:read` | List (`course_pk`, `student_pk`, `enrollment_status`) |
| POST | `` | `enrollments:write` | Enrol one student |
| POST | `/bulk` | `enrollments:write` | Enrol many; duplicates are **skipped**, not errors |
| PATCH | `/{enrollment_id}` | `enrollments:write` | Change status |

<details><summary>Duplicate handling</summary>

`POST /api/enrollments` on an existing pair → **409**
`"MTH2024001 is already enrolled in MTH201"`.

`POST /api/enrollments/bulk` reports them instead:
```json
{ "enrolled": [81, 82], "skipped_duplicates": [1], "detail": "Enrolled 2 student(s) in MTH210; skipped 1 already-enrolled student(s)" }
```
Backed by the `uq_enrollment_student_course` unique key.
</details>

### 4.7 Attendance — `/api/attendance`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `attendance:read` | Historical records (`course_pk`, `student_pk`, `enrollment_id`, `date_from`, `date_to`, `attendance_status`) |
| GET | `/summary` | `attendance:read` | Classes held and attended per enrolment |
| POST | `` | `attendance:write` | Record one entry — **idempotent** on (enrolment, date, session) |
| POST | `/bulk` | `attendance:write` | Mark a whole roster for one session |
| DELETE | `/{attendance_id}` | `attendance:write` | Delete a record |

`LATE` counts as attended; `EXCUSED` is excluded from the denominator.

### 4.8 LMS activity — `/api/activity`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `activity:read` | Event log (`course_pk`, `student_pk`, `activity_type`, `date_from`, `date_to`) |
| GET | `/summary` | `activity:read` | Login frequency, minutes and last-seen per enrolment |
| POST | `` | `activity:write` | Log one event |

### 4.9 Assessments — `/api/assessments` and `/api/assessment-results`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/assessments` | `assessments:read` | List (`course_pk`, `assessment_type`, `due_from`, `due_to`) |
| POST | `/assessments` | `assessments:write` | Create |
| GET | `/assessments/trends` | `assessments:read` | Monthly mean percentage |
| GET | `/assessments/{id}` | `assessments:read` | One assessment |
| PUT | `/assessments/{id}` | `assessments:write` | Update |
| GET | `/assessments/{id}/results` | `assessments:read` | Marks grid — **every enrolled student**, graded or not |
| GET | `/assessment-results` | `assessments:read` | Results history |
| POST | `/assessment-results` | `results:write` | Enter/correct one student's marks |
| POST | `/assessment-results/bulk` | `results:write` | Enter a whole grade sheet |

<details><summary>Marks validation</summary>

* `marks_obtained < 0` → 422
* `marks_obtained > max_marks` → 422
  `"Marks obtained (21.0) cannot exceed the maximum marks (20.00)"`
* `percentage` is **always derived server-side** — never accepted from the
  client — as `ROUND(100 × marks / max_marks, 2)`
* `marks_obtained: null` records a submission without a grade; the risk
  engine excludes it rather than counting it as zero
* `submission_status` is derived from `submitted_at` vs `due_at`
* Lowering `max_marks` below an already-recorded mark → 422
* Raising `max_marks` or changing `due_at` **re-derives** every stored
  percentage and submission status for that assessment
* In `/bulk`, every row is validated before anything is written
</details>

### 4.10 Risk analysis — `/api/risk-assessments`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `risk:read` | The risk table |
| POST | `/recalculate` | `risk:recalculate` | Recalculate and reconcile alerts |
| GET | `/{enrollment_id}` | `risk:read` | Full explanation of one score |
| GET | `/{enrollment_id}/history` | `risk:read` | Score history |

Filters: `search`, `course_pk`, `dept_id`, `semester`, `risk_category`,
`min_score`, `has_open_alert`. Sorting by `risk_score`, `student_id`,
`student_name`, `course_code`, `calculated_at`. Unscored rows always sort
last, whichever direction is requested.

<details><summary><code>POST /api/risk-assessments/recalculate</code></summary>

```json
// request — all three forms are valid
{}                      // every active enrolment
{ "course_pk": 1 }      // one course
{ "enrollment_id": 42 } // one enrolment

// 200
{ "enrollments_processed": 80, "alerts_opened": 3, "alerts_updated": 12,
  "alerts_auto_resolved": 1,
  "detail": "Recalculated 80 enrolment(s): 3 new alert(s), 1 auto-resolved." }
```
Passing both `course_pk` and `enrollment_id` → 422.
</details>

<details><summary><code>GET /api/risk-assessments/{enrollment_id}</code></summary>

Returns `row`, `components`, `engagement_breakdown`, `thresholds`,
`weights`, `history` and a `disclaimer`. Each component reports both its
nominal `weight` and the `effective_weight` actually applied, so the
re-normalisation is visible rather than implied:

```json
{
  "components": [
    { "name": "Attendance", "available": true, "risk_value": 66.67,
      "weight": 0.35, "effective_weight": 0.35, "contribution": 23.33,
      "observed_label": "33.33% attended (8/24 sessions)" },
    { "name": "Academic", "available": false, "risk_value": null,
      "weight": 0.40, "effective_weight": 0.0, "contribution": null,
      "unavailable_reason": "No graded assessment yet -- not counted as a zero" }
  ]
}
```
Works even before the first recalculation, computing live rather than 404ing.
</details>

### 4.11 Alerts — `/api/alerts`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `alerts:read` | The queue |
| GET | `/summary` | `alerts:read` | Counts by status and category |
| GET | `/{alert_id}` | `alerts:read` | Detail + status history + linked interventions + risk context |
| PATCH | `/{alert_id}` | `alerts:write` | Change status and/or assignee |

Filters: `search`, `alert_status`, `risk_category`, `course_pk`,
`dept_id`, `assigned_to`, `unassigned`, `only_open`, `date_from`,
`date_to`.

<details><summary><code>PATCH /api/alerts/{alert_id}</code></summary>

```json
{ "status": "ACKNOWLEDGED", "assigned_to": 8, "note": "Emailed the student." }
```
At least one of `status` / `assigned_to` is required. An illegal
transition → **409** with the allowed next states named. `RESOLVED` is
terminal. Alerts can only be assigned to `INSTRUCTOR`, `ADVISOR` or
`ADMIN` — anything else is 422. Each status change writes an
`alert_status_history` row in the same transaction.
</details>

### 4.12 Interventions — `/api/interventions`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `interventions:read` | History |
| POST | `` | `interventions:write` | Record an intervention |
| GET | `/{intervention_id}` | `interventions:read` | One record |
| PUT | `/{intervention_id}` | `interventions:write` | Update outcome / plan |

Filters include `follow_up_due=true`, which returns records whose
follow-up date has passed and which are not yet closed.

A supplied `alert_id` must belong to the **same enrolment** — checked by
the API and again by `trg_intervention_before_insert`.

### 4.13 Reports — `/api/reports`

All require `reports:read`.

| Path | Returns | Filters |
|---|---|---|
| `/risk-distribution` | Risk bands grouped by `category`, `semester`, `department` or `course` | `group_by`, `course_pk`, `dept_id`, `semester` |
| `/course-performance` | Mean marks, pass rate, attendance, high-risk count | `dept_id`, `semester` |
| `/course-attendance` | Sessions held/attended, mean rate, students below 75% | `dept_id`, `date_from`, `date_to` |
| `/submission-patterns` | On-time / late / missing per assessment | `course_pk`, `date_from`, `date_to` |
| `/high-risk-students` | Students at risk, with the courses listed | `dept_id`, `semester`, `min_courses` |
| `/department-risk` | Department-level KPIs | — |
| `/intervention-outcomes` | Effectiveness by intervention type | `date_from`, `date_to` |
| `/export` | **Any of the above as CSV** | `report=<name>` plus that report's filters |

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/api/reports/export?report=high-risk-students&dept_id=1' \
  -o high-risk.csv
```

### 4.14 Settings — `/api/settings`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `settings:read` | All settings |
| GET | `/risk-config` | `settings:read` | The resolved model configuration |
| PUT | `/{setting_key}` | `settings:write` | Update one setting |
| GET | `/audit/logs` | `audit:read` | Browse the audit trail |

Numeric settings are range-checked, and the medium threshold must stay
below the high threshold — crossing them is rejected with 422.

### 4.15 Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service banner |
| GET | `/health` | Liveness **and** real database connectivity |

```json
{ "status": "ok", "database": "connected", "dialect": "mysql" }
```

---

## 5. A complete worked flow

```bash
API=http://localhost:8000/api
TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"rohit.khanna@se-ewrs.edu","password":"Demo@12345"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

# 1. Who is on this course?
curl -s -H "$AUTH" $API/courses/1/roster | python3 -m json.tool

# 2. Mark today's session
curl -s -X POST $API/attendance/bulk -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "course_pk": 1, "session_date": "'"$(date +%F)"'", "session_no": 1,
  "rows": [{"enrollment_id": 1, "status": "ABSENT"},
           {"enrollment_id": 2, "status": "PRESENT"}]}'

# 3. Enter marks for an assessment
curl -s -X POST $API/assessment-results/bulk -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "assessment_id": 1,
  "rows": [{"enrollment_id": 1, "marks_obtained": 4},
           {"enrollment_id": 2, "marks_obtained": 18}]}'

# 4. Recalculate risk — this raises or refreshes alerts
curl -s -X POST $API/risk-assessments/recalculate -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{"course_pk": 1}'

# 5. Look at the queue
curl -s -H "$AUTH" "$API/alerts?only_open=true&risk_category=HIGH"

# 6. Acknowledge the first one
curl -s -X PATCH $API/alerts/1 -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"status":"ACKNOWLEDGED","note":"Emailed the student."}'

# 7. Record what was done about it
curl -s -X POST $API/interventions -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "enrollment_id": 1, "alert_id": 1, "intervention_type": "COUNSELING",
  "contact_date": "'"$(date +%F)"'",
  "notes": "Discussed the missed classes.",
  "action_plan": "Weekly check-in for a month.",
  "follow_up_date": "'"$(date -d '+7 days' +%F)"'"}'

# 8. Export the department report
curl -s -H "$AUTH" "$API/reports/export?report=department-risk" -o department-risk.csv
```
