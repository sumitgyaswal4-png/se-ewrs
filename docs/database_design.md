# SE-EWRS — Database Design

Design decisions, the risk model specification, and a reference for every
view, stored routine and trigger in `database/`.

---

## 1. Load order

The scripts are not independent — views depend on tables, procedures call
functions, and `seed.sql` calls a procedure. Run them in this order:

```
schema.sql  →  views.sql  →  procedures.sql  →  triggers.sql  →  seed.sql
```

`analytics_queries.sql` is read-only and can be run at any time afterwards.

---

## 2. Design decisions and their justification

### 2.1 Every engagement fact hangs off `enrollments`

`attendance_records`, `lms_activity_logs`, `assessment_results`,
`risk_assessments`, `risk_alerts` and `interventions` all reference
`enrollment_id` — never `student_pk` and `course_pk` as a pair.

* **Integrity.** An enrolment *is* a (student, course) pair that has been
  validated once. Referencing it makes attendance for a non-enrolled
  student structurally impossible. The alternative needs a composite
  foreign key to `enrollments(student_pk, course_pk)` on every fact table
  and still duplicates the pair on thousands of rows.
* **Normalisation.** Storing `student_pk` on `attendance_records` would be
  a transitive dependency: it is determined by `enrollment_id`, not by
  `attendance_id`.
* **Cost.** One extra join to reach the student's name. Every report here
  already joins `students` for the name anyway, so it is free in practice.

### 2.2 Surrogate keys everywhere, natural keys as UNIQUE

`students.student_pk` is an `AUTO_INCREMENT` integer; the roll number
`student_id` is a `UNIQUE` column. Roll numbers get reissued, corrected and
reformatted; an integer never changes and keeps child-table rows narrow.
The same pattern applies to `courses` (`course_pk` vs `course_code`).

### 2.3 Soft delete for students and courses

Neither is ever hard-deleted. Attendance, grades, risk history and
interventions all reference them, and that history is the point of the
system — deleting a student would erase the record of an intervention that
worked. `is_active = 0` removes them from rosters, dashboard counters and
risk recalculation while preserving everything.

### 2.4 `risk_assessments` is append-only

Each recalculation inserts a row rather than updating one. A risk score is
a statement about a point in time; overwriting it would make the trend
chart impossible and would mean a score acted on in week 4 could never be
explained afterwards. The latest row per enrolment is selected with
`ROW_NUMBER() OVER (PARTITION BY enrollment_id ORDER BY calculated_at DESC)`
in `v_latest_risk`.

Each row snapshots its own inputs (`sessions_held`, `login_count_30d`, …)
and its `model_version`, so an old score can be reproduced with the data
and weights that produced it even after the weights change.

### 2.5 Risk weights live in `system_settings`, not in code

The model is configuration. `risk.weight.*`, `risk.threshold.*`,
`risk.min_sessions`, `risk.min_graded` and `alert.min_score` are all read
at calculation time by both `sp_recalculate_risk_for_enrollment` and
`RiskConfig.from_db()`. Retuning the model is an UPDATE, not a deployment,
and `trg_settings_after_update` records who changed what.

### 2.6 At most one open alert per enrolment — enforced by the schema

See `er_diagram.md` §4.1. The `active_flag` generated column plus a
composite UNIQUE key makes a duplicate open alert impossible at the
storage layer.

---

## 3. The risk model — full specification

> **This section is the single specification.** `database/procedures.sql`
> and `backend/app/services/risk_engine.py` are two implementations of it
> and must agree.

### 3.1 The formula

```
Risk Score = 0.35 × Attendance Risk
           + 0.40 × Academic Risk
           + 0.25 × Engagement Risk
```

Each component is on a 0–100 scale where **higher means more at risk**:

```
Attendance Risk = 100 − Attendance Percentage
Academic Risk   = 100 − Average Assessment Percentage
Engagement Risk = 100 − Engagement Score
```

The result is clamped to 0–100 and rounded **half-up** to two decimals.

### 3.2 The three inputs

**Attendance Percentage**

```
attendance % = 100 × sessions_attended / sessions_held
```

* `PRESENT` and `LATE` both count as *attended* — the student was in the room.
* `EXCUSED` is removed from **both** numerator and denominator, so an
  authorised absence cannot depress a student's attendance.
* Requires at least `risk.min_sessions` (default **3**) recorded sessions.

**Average Assessment Percentage**

```
average % = AVG(percentage) WHERE marks_obtained IS NOT NULL
```

Only *graded* rows contribute. A row with `marks_obtained IS NULL` — not
submitted, or submitted but not yet marked — is excluded, never counted as
a zero. Requires at least `risk.min_graded` (default **1**) graded item.

**Engagement Score** (0–100, higher is better)

```
engagement = clamp(100 − (recency + frequency + missing + late), 0, 100)
```

| Penalty | Rule |
|---|---|
| **recency** — days since the last LMS event | never active → 50 · ≤3 → 0 · ≤7 → 10 · ≤14 → 20 · ≤30 → 35 · >30 → 50 |
| **frequency** — logins in the window vs the target (default 12) | `logins ≥ target` → 0 · `logins×3 ≥ target×2` → 5 · `logins×3 ≥ target` → 12 · `logins ≥ 1` → 20 · `0` → 30 |
| **missing** | `40 × missing_submissions / results_recorded` |
| **late** | `20 × late_submissions / results_recorded` |

The frequency bands use **integer cross-multiplication** rather than a
float ratio. With a target of 12, exactly 8 logins is two-thirds; written
as `logins / target >= 0.667` the SQL and Python implementations could
disagree at that boundary on a floating-point rounding. `logins * 3 >=
target * 2` is exact in both.

The engagement component is skipped entirely when an enrolment has
**no** LMS rows *and* **no** assessment rows — there is simply no signal.

### 3.3 Missing data — the part that matters

A component with no supporting data is **dropped**, and the remaining
weights are **re-normalised**:

```
risk = Σ(wᵢ × riskᵢ for available i) / Σ(wᵢ for available i)
```

Worked example — a student with 80% attendance, perfect engagement, and no
graded work yet:

| | treated as zero (**wrong**) | component dropped (**this system**) |
|---|---|---|
| attendance risk 20 × 0.35 | 7.00 | 7.00 |
| academic risk **100** × 0.40 | 40.00 | — excluded |
| engagement risk 0 × 0.25 | 0.00 | 0.00 |
| available weight | 1.00 | 0.60 |
| **score** | **47.00 → MEDIUM RISK** | **11.67 → LOW RISK** |

Treating the absence of a grade as a zero would flag a perfectly engaged
student as at risk purely for being early in the term.

**Data completeness and the band**

| Components available | `data_completeness` | `risk_category` |
|---|---|---|
| 3 | `COMPLETE` | banded by score |
| 2 | `PARTIAL` | banded by score |
| 0 or 1 | `INSUFFICIENT` | **`INSUFFICIENT_DATA`** — no band assigned |

With fewer than two observable components the score is still computed and
stored, but **no risk band is assigned** and **no alert is raised**. The
UI shows the reason instead of a band.

### 3.4 Bands and alerting

| Band | Score | Setting |
|---|---|---|
| Low | 0–29 | — |
| Medium | 30–59 | `risk.threshold.medium` = 30 |
| High | 60–100 | `risk.threshold.high` = 60 |
| Needs more data | not banded | — |

An alert is raised when `risk_category ∈ {MEDIUM, HIGH}` **and**
`risk_score ≥ alert.min_score` (default 30).

| Situation | What happens |
|---|---|
| At/above threshold, no open alert | **raise** a new alert with status `NEW` |
| At/above threshold, open alert exists | **refresh** that alert's score and factors — never duplicate it |
| Below threshold, open alert still `NEW` | **auto-resolve** it (nobody had picked it up) |
| Below threshold, alert `ACKNOWLEDGED`/`IN_PROGRESS` | **leave it alone** — a human owns it and closes it |

### 3.5 Alert status transitions

```
NEW ──→ ACKNOWLEDGED ──→ IN_PROGRESS ──→ RESOLVED
 │            │                             ▲
 │            └─────────────────────────────┤
 └──────────────────────────────────────────┘
```

`RESOLVED` is terminal. A resolved alert is never reopened; if the
student's risk rises again a *fresh* alert is raised, which keeps the
history honest about how many separate episodes there were.

Enforced in `sp_update_alert_status` and in `PATCH /api/alerts/{id}`.

---

## 4. Views reference

All in `database/views.sql`.

### 4.1 Building blocks

| View | Purpose | Concepts shown |
|---|---|---|
| `v_enrollment_attendance` | Attendance roll-up per enrolment: sessions held/attended/absent/late/excused and the percentage. | `LEFT JOIN`, conditional aggregation (`SUM(CASE …)`), `GROUP BY`, divide-by-zero guard |
| `v_enrollment_academics` | Academic roll-up: graded count, mean/min/max percentage, on-time/late/missing counts, last assessment date. | conditional aggregation, `AVG` over a filtered `CASE` |
| `v_enrollment_activity` | LMS roll-up: total events, logins in the last 30 days, quiz attempts, minutes, last-seen and days since. | date arithmetic (`INTERVAL`, `DATEDIFF`) |
| `v_latest_risk` | The newest `risk_assessments` row per enrolment. | **CTE + `ROW_NUMBER()` window function** |

**Run:**
```sql
SELECT * FROM v_enrollment_attendance WHERE enrollment_id = 1;
SELECT * FROM v_latest_risk ORDER BY risk_score DESC LIMIT 10;
```

### 4.2 Composite views

| View | Purpose | Concepts shown |
|---|---|---|
| `student_performance_view` | **One row per (student, course)** — the single source of truth for the student profile and the risk procedure. Joins students, departments, courses and all three roll-ups. | 4-table join + 3 `LEFT JOIN`s onto views |
| `course_attendance_summary` | Course-wise attendance with a "students below 75%" counter. | `GROUP BY` + **`HAVING`** (drops courses with no enrolments) |
| `course_performance_summary` | Course-wise mean/min/max/stddev marks and pass rate. | `AVG`, `STDDEV_SAMP`, `NULLIF` guard |
| `v_submission_patterns` | On-time/late/missing counts per assessment. | `LEFT JOIN` so assessments with zero submissions still appear |
| `student_risk_summary` | The risk page's source: latest risk + student/course context + open-alert state. | view built **on another view**, plus a conditional join on `active_flag` |
| `department_risk_summary` | Department KPIs for the Chair. | aggregation over a view |
| `v_active_alerts` | Alerts enriched with student/course/assignee names and an intervention count. | **correlated scalar subquery** in the SELECT list |
| `v_intervention_outcomes` | Interventions with advisor, student, course and current risk. | multi-table join + `LEFT JOIN` to `v_latest_risk` |

**Run:**
```sql
SELECT student_id, student_name, course_code, risk_score, risk_category
  FROM student_risk_summary
 WHERE risk_category = 'HIGH'
 ORDER BY risk_score DESC;

SELECT * FROM department_risk_summary;
```

---

## 5. Stored functions and procedures

All in `database/procedures.sql`.

### `fn_setting_num(key, default)` → DECIMAL
Reads a numeric value from `system_settings`, falling back to a default
when the key is absent. Keeps the model configurable without scattering
magic numbers.
```sql
SELECT fn_setting_num('risk.weight.academic', 0.40);
```

### `fn_engagement_score(days_since, logins, target, missing, late, results)` → DECIMAL
The engagement sub-model of §3.2, as a `DETERMINISTIC` function.
```sql
-- dormant 21 days, 2 logins, 1 missing and 2 late of 5 → 29.00
SELECT fn_engagement_score(21, 2, 12, 1, 2, 5);
```

### `fn_risk_category(score, completeness, medium, high)` → VARCHAR
Bands a score, returning `INSUFFICIENT_DATA` whenever completeness is
`INSUFFICIENT` regardless of the number.
```sql
SELECT fn_risk_category(61.80, 'COMPLETE', 30, 60);     -- HIGH
SELECT fn_risk_category(61.80, 'INSUFFICIENT', 30, 60); -- INSUFFICIENT_DATA
```

### `sp_recalculate_risk_for_enrollment(enrollment_id, actor_user_id)`
The core routine. Reads `student_performance_view`, derives the three
components, re-normalises the weights, inserts a `risk_assessments` row
and reconciles the alert — **the insert and the alert change are one
transaction**, so a risk row can never be written without its alert state.
```sql
CALL sp_recalculate_risk_for_enrollment(1, 1);
```

### `sp_recalculate_all_risk(course_pk, actor_user_id)`
Cursor loop over every `ACTIVE` enrolment, optionally one course. Writes
an `audit_logs` row and returns the count.
```sql
CALL sp_recalculate_all_risk(NULL, 1);  -- every course
CALL sp_recalculate_all_risk(1, 1);     -- course 1 only
```

### `sp_enroll_student(student_pk, course_pk, actor_user_id)`
Transactional enrolment with `EXIT HANDLER FOR SQLEXCEPTION … ROLLBACK;
RESIGNAL`. Checks the student and course exist and are active, and that
the pair is not already enrolled, so the caller gets a readable message
instead of a raw constraint violation.
```sql
CALL sp_enroll_student(5, 2, 1);
```

### `sp_record_attendance(enrollment_id, session_date, session_no, status, recorded_by, remarks)`
Idempotent upsert via `ON DUPLICATE KEY UPDATE` — re-recording a session
corrects it rather than failing on `uq_attendance_session`.
```sql
CALL sp_record_attendance(1, CURDATE(), 1, 'PRESENT', 2, NULL);
```

### `sp_upsert_assessment_result(assessment_id, enrollment_id, marks, submitted_at, graded_by)`
Validates marks against the parent's `max_marks`, derives
`submission_status` from `submitted_at` vs `due_at`, and upserts.
`percentage` is left to the trigger.
```sql
CALL sp_upsert_assessment_result(1, 1, 15.0, NOW(), 2);
```

### `sp_update_alert_status(alert_id, new_status, user_id, note)`
Enforces the §3.5 transition graph, uses `SELECT … FOR UPDATE` to lock the
row, and writes the `alert_status_history` entry in the same transaction.
```sql
CALL sp_update_alert_status(1, 'ACKNOWLEDGED', 8, 'Emailed the student.');
```

---

## 6. Triggers reference

All in `database/triggers.sql`.

**Design rules followed:** no trigger writes to the table it is attached
to; no trigger calls a procedure that writes back to that table; audit
triggers only ever append to `audit_logs`, which itself has no triggers.
There is therefore **no recursion**. Alert generation is deliberately
**not** in a trigger — it lives only in the procedure and the Python
engine, which is what keeps duplicate alerts impossible.

### Validation triggers

| Trigger | Table | Purpose |
|---|---|---|
| `trg_ar_before_insert` / `trg_ar_before_update` | `assessment_results` | The **database** owns `percentage`. Rejects negative marks and marks above the parent's `max_marks`, then sets `percentage = ROUND(100 × marks / max_marks, 2)`. Fires for any client — API, `seed.sql`, or a manual INSERT during a viva. |
| `trg_assess_before_insert` / `trg_assess_before_update` | `assessments` | Rejects `max_marks <= 0` (which would make every percentage undefined) and a `weight_percent` outside 0–100. |
| `trg_intervention_before_insert` | `interventions` | Cross-row referential check a foreign key cannot express: a cited `alert_id` must belong to the **same enrolment**. |

**Demonstrate:**
```sql
-- percentage is derived, not supplied
INSERT INTO assessment_results (assessment_id, enrollment_id, marks_obtained, submission_status)
VALUES (1, 1, 15.00, 'ON_TIME');
SELECT marks_obtained, percentage FROM assessment_results
 WHERE assessment_id = 1 AND enrollment_id = 1;     -- 15.00 → 75.00

-- and the range check bites
INSERT INTO assessment_results (assessment_id, enrollment_id, marks_obtained, submission_status)
VALUES (1, 2, 999, 'ON_TIME');
-- ERROR 1644: assessment_results: marks_obtained exceeds max_marks
```

### Audit triggers

| Trigger | Table | Records |
|---|---|---|
| `trg_students_after_insert` | `students` | creation |
| `trg_students_after_update` | `students` | edits and de-activations — guarded by an `IF` so a no-op UPDATE writes nothing |
| `trg_courses_after_update` | `courses` | catalogue changes |
| `trg_users_after_update` | `users` | **role, is_active and department only** — `password_hash` is never copied into the audit trail |
| `trg_enrollments_after_insert` | `enrollments` | who was added to which course |
| `trg_alerts_after_update` | `risk_alerts` | status and assignee changes |
| `trg_settings_after_update` | `system_settings` | a weight change reshapes every future score, so it is audited |

All use the null-safe comparison operator `<=>` so that a change to or
from `NULL` is detected correctly — `OLD.dept_id <> NEW.dept_id` would be
`NULL` (falsy) when either side is NULL and the change would go unrecorded.

**Demonstrate:**
```sql
UPDATE students SET is_active = 0 WHERE student_pk = 1;
SELECT action, entity_type, entity_id, old_values, new_values
  FROM audit_logs WHERE entity_type = 'students' ORDER BY audit_id DESC LIMIT 1;
```

---

## 7. Transactions

| Operation | Why it must be atomic |
|---|---|
| `sp_recalculate_risk_for_enrollment` | The risk row and the alert it raises/refreshes/closes must land together, or the alert queue disagrees with the scores. |
| `sp_recalculate_all_risk` | The whole run is one transaction in the Python engine (`recalculate_all` commits once), so a partial recalculation cannot leave half the cohort scored against old data. |
| `sp_enroll_student` | Validation and insert, with `ROLLBACK; RESIGNAL` on any exception. |
| `sp_update_alert_status` | Status change + history row. A status change with no history entry would break the audit trail. |
| `POST /api/attendance/bulk` | A whole session's roster, or none of it. |
| `POST /api/assessment-results/bulk` | **Every mark is validated before anything is written** — one out-of-range mark rejects the batch rather than leaving half a grade sheet saved. |
| `POST /api/enrollments/bulk` | One transaction; duplicates are reported as `skipped`, not failures. |

---

## 8. SQL feature checklist

| Required concept | Where to find it |
|---|---|
| Normalised schema (3NF) | `schema.sql`; justified in `er_diagram.md` §5 |
| Primary keys | every table |
| Foreign keys | 25 constraints with explicit `ON UPDATE` / `ON DELETE` |
| Unique constraints | `uq_enrollment_student_course`, `uq_attendance_session`, `uq_result_assessment_enrollment`, `uq_alert_one_active_per_enrollment`, `uq_courses_code_term`, `uq_assessment_course_title`, `uq_course_instructor` |
| CHECK constraints | semester, year, credits, marks, weights, score range, follow-up date |
| Indexes | §6 of `er_diagram.md`; `EXPLAIN` demo in Q15 |
| Joins (inner / left / self-contained) | every view; Q4, Q11, Q13 |
| Aggregate functions | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `STDDEV_SAMP`, `GROUP_CONCAT` |
| `GROUP BY` … `HAVING` | `course_attendance_summary`, Q3, Q4, Q10, Q13 |
| Subqueries | Q1 (scalar), Q5 (correlated), `v_active_alerts` (scalar in SELECT) |
| Common Table Expressions | `v_latest_risk`, Q6, Q11 |
| Window functions | `ROW_NUMBER()` in `v_latest_risk`; `SUM() OVER ()` in Q6; `LAG()` in Q11 |
| Views | 12 views, §4 |
| Stored functions | 3, §5 |
| Stored procedures | 6, §5 |
| Triggers | 12, §6 |
| Transactions | §7 |
| Generated columns | `risk_alerts.active_flag` (STORED) |
| Cursors | `sp_recalculate_all_risk` |
| Error signalling | `SIGNAL SQLSTATE '45000'` throughout |
| Exception handling | `DECLARE EXIT HANDLER FOR SQLEXCEPTION` in `sp_enroll_student`, `sp_update_alert_status` |

---

## 9. Performance

Measured on MySQL 8.0.46 against a synthetic dataset **170x the demo**:
2,000 students, 40 courses, 6,000 enrolments, 144,000 attendance records,
270,000 LMS events and 30,000 assessment results (~450,000 fact rows).

### 9.1 The access-path bug this testing found

`sp_recalculate_risk_for_enrollment` originally read its inputs from
`student_performance_view`:

```sql
SELECT ... INTO ... FROM student_performance_view spv
 WHERE spv.enrollment_id = p_enrollment_id;
```

That looks efficient -- one row, filtered by primary key. It is not.
`EXPLAIN` shows `<derived3>`, `<derived4>`, `<derived5>`: MySQL
**materialises each of the three aggregate sub-views in full** and only
then applies the predicate. Every call therefore aggregated all 450,000
fact rows to retrieve one row.

| | per call | 6,000 enrolments |
|---|---|---|
| reading `student_performance_view` | 4,406 ms | ~7 hours (projected) |
| reading the base tables with a predicate | **33.5 ms** | **82 seconds** |

A **132x** improvement, and the output is byte-identical: both versions
were run against the same data and every field of all 80 demo rows
matched, including the generated `contributing_factors` text.

The fix is the three targeted `SELECT`s now in the procedure. They use
`ix_attendance_enrollment`, `ix_results_enrollment` and
`ix_lms_enrollment_time`, and they reproduce the view's arithmetic
exactly -- only the access path differs.

**The general lesson**, and the reason this is worth a paragraph in the
report: *a view is an abstraction, not an index.* Selecting one row from
an aggregate view is not the same as aggregating one row. The Python
engine never had this problem because `collect_metrics()` always queried
base tables with a predicate; only the SQL side went through the view.

### 9.2 Measured timings after the fix

| Operation | Demo (80 enrolments) | Scale (6,000 enrolments) |
|---|---|---|
| Load `seed.sql` | 9 s | -- |
| `sp_recalculate_all_risk` (whole cohort) | 1.1 s | 82 s |
| `sp_recalculate_risk_for_enrollment` (one) | <5 ms | 33 ms |
| Alert queue (`v_active_alerts`) | instant | 158 ms |
| Submission patterns report | instant | 746 ms |
| Course performance report | instant | 1,115 ms |

Index usage is as designed. The risk engine's hottest predicate uses the
composite index as a covering range scan:

```
EXPLAIN SELECT COUNT(*) FROM lms_activity_logs
 WHERE enrollment_id = 1 AND activity_at >= (CURRENT_DATE - INTERVAL 30 DAY);

type: range   key: ix_lms_enrollment_time   rows: 26   Extra: Using index
```

26 rows examined out of 270,000.

### 9.3 The same bug in the application layer

The access-path bug of section 9.1 was not only in SQL. Every roll-up in
`services/queries.py` groups a whole fact table by `enrollment_id`, and
the endpoints that wanted *one* enrolment filtered the result of that
aggregate rather than restricting the aggregate itself. MySQL therefore
grouped all 144,000 attendance rows, all 270,000 activity rows and all
30,000 results in order to return a single student's figures.

Opening one student's profile on the 6,000-enrolment dataset took 3.4
seconds. Not a scale concern -- a page.

The fix is the one section 9.1 applies in SQL: push the predicate inside
the aggregate. Each roll-up now takes an optional `limit_to`, and the
four endpoints that already know which enrolments they want pass it:

| Endpoint | Before | After | |
|---|---|---|---|
| `GET /api/students/{pk}/profile` | 3,377 ms | **81 ms** | 42x |
| `GET /api/risk-assessments/{id}` | 3,725 ms | **79 ms** | 47x |
| `GET /api/courses/{pk}/roster` | 3,381 ms | **160 ms** | 21x |
| `GET /api/alerts/{id}` | 3,496 ms | **61 ms** | 57x |

Restricting a `GROUP BY enrollment_id` to a set of `enrollment_id`s can
only remove groups the caller was going to discard, so the change cannot
alter a result. That argument was checked rather than trusted: every
risk detail, every student profile, every course roster and every alert
in the demo database -- **157 responses** -- were captured before and
after and compared. They are identical byte for byte.

### 9.4 What is still slow: the paginated lists

`GET /api/students` and `GET /api/risk-assessments` were **not** fixed
and still take 8-9 s on the 6,000-enrolment dataset.

They are a harder problem than the single-entity reads, and honestly so.
A list computes aggregates for the whole filtered set in order to return
one page of 20, but it cannot simply restrict them to the page: the page
is not known until the query has run, and `student_stats_sq` genuinely
aggregates the live figures rather than merely displaying them. The fix
is to select the page's keys first and aggregate only those -- two round
trips instead of one -- which is a different and larger change.

Measured on the 6,000-enrolment dataset:

| Component | Time |
|---|---|
| group enrolments by student | 44 ms |
| aggregate attendance (144k rows) | 792 ms |
| aggregate LMS activity (270k rows) | 229 ms |
| latest-risk window function | 227 ms |
| **the five joined together** | **5,711 ms** |

The parts cost ~1.3 s; composed they cost 5.7 s, because MySQL
materialises each derived table and then joins them with auto-generated
keys. At the demo's scale, and at a realistic single-department scale of
a few hundred enrolments, both endpoints are effectively instant; the
limitation appears only above a few thousand.

Leaving it is a deliberate choice, and the same one as before: the
project does not need it, and an unverified optimisation is worse than a
documented limitation. The difference from section 9.3 is that there the
equivalence argument was provable and was proved.

## 10. Keeping SQL and Python in step

Two implementations of §3 exist, by design:

| | Implementation | Used by |
|---|---|---|
| **Database** | `sp_recalculate_risk_for_enrollment` | `CALL` from SQL, `seed.sql`, a DBA, the viva demo |
| **Application** | `app/services/risk_engine.py` | the REST API |

They are kept in step by:

1. **One specification** — §3 of this document.
2. **Identical rounding.** Both round half-up. MySQL's `ROUND()` is
   half-up; Python's built-in `round()` is banker's rounding, so the
   engine uses `Decimal.quantize(…, ROUND_HALF_UP)` rather than `round()`.
3. **Exact band boundaries.** Integer cross-multiplication for the login
   frequency bands (§3.2), so neither side can drift on a float.
4. **Shared configuration.** Both read the same `system_settings` rows.
5. **Tests.** `backend/tests/test_risk_engine.py` pins the arithmetic,
   the bands, the clamping and the missing-data behaviour against the
   worked numbers in §3.

If you change the model, change §3 first, then both implementations, then
the tests.
