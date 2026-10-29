# SE-EWRS — DBMS Project Report Outline

A chapter-by-chapter skeleton for the written submission, with the file
or command that supplies the evidence for each section. Suggested length
is for a typical 40–60 page undergraduate DBMS report; adjust to your
department's template.

**Project:** Student Engagement & Early Warning Risk System (SE-EWRS)
**Department:** Mathematics
**Team:** Mohammad Adnan · Lucky Dhall · Raja · Sumit

---

## Front matter

- Title page (title, team, supervisor, department, session)
- Certificate / declaration
- Acknowledgements
- Abstract — 150–200 words: the problem, the approach, what was built, what works
- Table of contents, list of figures, list of tables

---

## Chapter 1 — Introduction (4–5 pages)

1.1 Background — LMS platforms collect engagement data that is rarely acted on
1.2 Problem statement — *use the brief's own wording*
1.3 Objectives
  - Design a normalised relational schema for student engagement data
  - Implement a transparent, configurable risk model
  - Generate early-warning alerts without duplicates
  - Track interventions against those alerts
  - Provide role-based access for five distinct user roles
1.4 Scope and limitations — what is in, what is out, and that the score is an indicator rather than a judgement
1.5 Report organisation

---

## Chapter 2 — Literature / existing systems (3–4 pages)

2.1 Early-warning systems in education — the general approach
2.2 What LMS platforms already provide, and the gap
2.3 Rule-based versus statistical risk models, and why a transparent rule-based model was chosen here
2.4 Summary of the gap this project addresses

---

## Chapter 3 — System analysis (4–5 pages)

3.1 Existing system and its shortcomings
3.2 Proposed system
3.3 Feasibility — technical, operational, economic
3.4 Requirements
  - Functional, grouped by the five roles → `docs/api_documentation.md` §2
  - Non-functional: security, performance, usability, data integrity
3.5 Hardware and software requirements

---

## Chapter 4 — System design (6–8 pages) — *the core DBMS chapter*

4.1 Architecture — three tiers: React SPA → FastAPI → MySQL 8
  > **Figure:** the architecture diagram from `README.md` §6

4.2 **ER diagram and relationships**
  > **Figure:** `docs/er_diagram.md` §1 (render the Mermaid diagram)
  > **Figure:** the simplified engagement spine, §2
  > **Table:** cardinality summary, §3

4.3 **Relational schema** — all 16 tables with columns, types and constraints
  > **Source:** `database/schema.sql`
  > **Table:** one row per table with its purpose

4.4 **Normalisation** — demonstrate 1NF → 2NF → 3NF
  > **Source:** `docs/er_diagram.md` §5
  > *Worth marks:* also discuss the two **deliberate** denormalisations
  > (`assessment_results.percentage`, the `risk_assessments` table) and
  > why each is justified. Examiners expect candidates to defend a
  > denormalisation, not pretend none exists.

4.5 **Constraints and keys**
  - Primary and foreign keys with their referential actions
  - Composite unique keys and what each one prevents
  - CHECK constraints
  - *Highlight:* `uq_alert_one_active_per_enrollment` with the
    `active_flag` generated column — this is the most interesting single
    design decision in the schema (`docs/er_diagram.md` §4.1)

4.6 **Indexing strategy** — `docs/er_diagram.md` §6, with the composite
  index rationale and the `EXPLAIN` output from Q15

4.7 Data dictionary — a table per entity (can go in an appendix)

---

## Chapter 5 — The risk model (5–6 pages) — *the distinctive chapter*

5.1 The formula and its three components
  > **Source:** `docs/database_design.md` §3

5.2 Each component defined
  - Attendance, including why LATE counts as attended and EXCUSED is excluded
  - Academic, including why ungraded work is excluded rather than zeroed
  - Engagement, with the four penalty rules tabulated

5.3 **Missing-data handling and weight re-normalisation**
  > **Table:** the worked comparison in `docs/database_design.md` §3.3 —
  > the same student scoring 47 (MEDIUM) if missing data is zeroed versus
  > 11.67 (LOW) when the component is dropped. This is the single best
  > table in the report: it shows a design decision with a measurable
  > consequence.

5.4 Banding, thresholds, and why they are configuration rather than code

5.5 Alert generation, refresh and auto-resolution; the status transition graph

5.6 **Keeping two implementations in step** — the SQL procedure and the
  Python service, and the three mechanisms that stop them drifting:
  one specification, half-up rounding on both sides, and integer
  cross-multiplication at the band boundaries
  > **Source:** `docs/database_design.md` §9

5.7 Ethical considerations — the score as an indicator, not a judgement
  > **Source:** `docs/user_guide.md` §15

---

## Chapter 6 — Implementation (8–10 pages)

6.1 Technology stack and why each piece was chosen

6.2 **Database implementation**
  - Schema creation → `database/schema.sql`
  - **Views** — all 12, with purpose and one sample output each
    > **Source:** `docs/database_design.md` §4
  - **Stored functions and procedures** — all 9, with signatures and a
    `CALL` example each → §5
  - **Triggers** — all 12, split into validation and audit, with a
    worked demonstration of the percentage trigger and the marks range
    check → §6
  - **Transactions** — where they are used and what each protects → §7
  > *Include actual screenshots of `CALL` statements and their output.*
  > *A trigger rejecting an invalid INSERT is a strong screenshot.*

6.3 **Analytical queries** — pick 6–8 from `database/analytics_queries.sql`
  and show the query, its output, and which SQL concept it demonstrates.
  Q5 (correlated subquery), Q6 (CTE + window function), Q11 (`LAG()`),
  Q13 (`GROUP BY … HAVING` + `GROUP_CONCAT`) are the strongest.

6.4 **Backend** — layering, the ORM models, Pydantic validation,
  JWT authentication, the permission map, centralised error handling

6.5 **Frontend** — routing, route guards, the data-fetching hook, the
  four UI states, the chart layer

6.6 Security — Argon2id hashing, JWT expiry, server-side authorisation,
  parameterised queries, audit logging, environment variables
  > **Source:** `README.md` §11

---

## Chapter 7 — Testing (4–5 pages)

7.1 Strategy — unit, integration, end-to-end

7.2 **Backend tests** — 526 tests, what each file covers
  > **Table:** test file → what it verifies → count
  > **Screenshot:** the `pytest` summary line

7.3 **Frontend tests** — 98 tests across formatting, components, charts,
  navigation, the data hook and the status-colour helper

7.4 **Selected test cases** — present 8–10 as a formal table
  (ID, description, input, expected, actual, pass/fail). Good candidates:
  - risk formula produces exactly 61.80 for the documented inputs
  - a profile with no data is `INSUFFICIENT_DATA`, never high risk
  - dropping the academic component lowers the score rather than raising it
  - the database refuses a second open alert for one enrolment
  - a resolved alert cannot be reopened
  - marks above the maximum are rejected
  - a chair receives 403 on every write endpoint
  - excused absences do not depress attendance

7.5 Coverage — 83% backend; note what is uncovered and why

7.6 Limitations found during testing

---

## Chapter 8 — Results (5–6 pages)

8.1 Demo dataset — 36 students, 6 courses, 80 enrolments, ~1,700
  attendance records, ~5,400 activity events, 380 results

8.2 **Screenshots** — all fifteen are captured and captioned in
  `docs/screenshots/` (see its `README.md`, which is written to be lifted
  into the report as the figure list). They were taken from the running
  application against the MySQL demo database, so the figures agree
  across images.

  | Fig. | File | Demonstrates |
  |---|---|---|
  | 1 | `01-login.png` | Login, with the demo accounts and role-based landing |
  | 2 | `02-dashboard-admin.png` | Live metrics and charts, every figure from SQL |
  | 3 | `03-students-filtered-high-risk.png` | Student list filtered to high risk (36 → 5) |
  | 4 | `04-student-profile.png` | One student across all their courses |
  | 5 | `05-attendance-marking.png` | Marking a whole session in one pass |
  | 6 | `06-marks-validation-rejected.png` | **999 marks out of 10 refused by the server** |
  | 7 | `07-risk-analysis-table.png` | The risk analysis table |
  | 8 | `08-risk-detail.png` | **The best single figure** — formula, weights, components and factors together |
  | 9 | `09-alerts-queue.png` | The early-warning alert queue |
  | 10 | `10-alert-detail-history.png` | An alert with its status history |
  | 11 | `11-interventions.png` | Intervention tracking |
  | 12 | `12-reports-csv-export.png` | Reports, just after a real CSV export |
  | 13 | `13-settings-risk-weights.png` | The configurable weights and thresholds |
  | 14 | `14-rbac-teaching-assistant.png` | The same app as a Teaching Assistant |
  | 15 | `15-rbac-department-chair.png` | The same app as a read-only Department Chair |

  Figure 6 is worth a paragraph rather than a caption. The entered value
  passes the HTML `max` attribute — that attribute only constrains the
  spinner — so the request reaches the API, which refuses it, and the
  database would refuse it again. Three layers, and the screenshot shows
  the one that actually matters.

  Figures 14 and 15 are the clearest evidence for Chapter 6's access
  control: the same build, the same URL, a different navigation tree.
  Say in the text that hiding the control is only the visible half, and
  that each endpoint behind it re-checks the permission server-side.

8.3 Observed risk distribution across the demo cohort, with a comment on
  whether it looks plausible

8.4 **Performance** — this section now has real material, which most
  student reports lack. Use `docs/database_design.md` §9:
  - The access-path bug found by stress-testing: reading one row from an
    aggregate view made MySQL materialise the whole view, costing 4,406 ms
    per call; reading the base tables with a predicate costs 33.5 ms. A
    full 6,000-enrolment recalculation went from a projected ~7 hours to
    82 seconds. **Show the `EXPLAIN` with `<derived3>` in it** — that is
    the evidence, and it is a genuinely instructive screenshot.
  - State that the output was proven byte-identical before and after, so
    it was an optimisation and not a behaviour change.
  - Index usage: the `EXPLAIN` showing `ix_lms_enrollment_time` as a
    covering range scan reading 26 rows of 270,000.
  - **The same bug in the application layer** (§9.3), which is the more
    interesting half because it cost a *page* rather than a batch job:
    endpoints that wanted one enrolment filtered the result of a
    whole-table aggregate, so opening one student's profile took 3.4 s
    and now takes 81 ms. Four endpoints, 21x to 57x. Make the point that
    the same mistake appeared independently in SQL and in Python,
    because it is a way of thinking about queries, not a typo.
  - State that both fixes were proven byte-identical before and after
    (80 enrolments for the procedure; 157 API responses for the
    endpoints), so they were optimisations and not behaviour changes.
  - **The paginated lists** (§9.4), which is the subtlest of the three:
    a list cannot restrict its aggregates to its page, because the page
    is not known until the query has run — but it does not need to,
    because nothing selects the page *by* those aggregates. Choosing the
    page first and aggregating only it gives 10× and 12×. The reasoning
    is the interesting part: the fix came from reading what each
    endpoint filters, sorts and counts on, not from tuning anything.

  - Say that the whole of section 8.4 is reproducible: one command,
    `./database/scale_test.sh`, rebuilds the benchmark database and
    reprints the timings. An examiner who asks "show me" can be shown.

8.5 **Concurrency** — the duplicate-alert guard under real contention:
  20 threads racing to open one alert (1 succeeded, 19 refused by the
  unique key), and 16 threads calling the recalculation procedure
  simultaneously on a high-risk student (all completed, exactly one
  alert). This is the evidence that the constraint, not the application
  code, is what makes duplicates impossible.

---

## Chapter 9 — Conclusion and future work (2–3 pages)

9.1 What was achieved, against the objectives in §1.3
9.2 What was learned
9.3 Limitations — rule-based model, no live LMS integration, single
  institution, and no incremental recalculation (a full run re-scores
  every enrolment rather than only those whose data changed)

9.4 Future work — incremental recalculation, statistical/ML scoring
  validated against real outcomes, live LMS integration, notifications,
  a student-facing view, and fairness auditing of the model across
  demographic groups

---

## Back matter

- References (IEEE or your department's style)
- **Appendix A** — full `schema.sql`
- **Appendix B** — views, procedures and triggers
- **Appendix C** — the analytical queries with output
- **Appendix D** — API endpoint table (`docs/api_documentation.md` §4)
- **Appendix E** — selected source listings

---

## Suggested division of work

Adjust to how you actually worked — but state it honestly, since vivas
tend to probe the parts a candidate did not write.

| Member | Primary area |
|---|---|
| Mohammad Adnan | Database design, schema, views, procedures, triggers (Ch. 4, 6.2) |
| Lucky Dhall | Risk model specification and both implementations (Ch. 5) |
| Raja | Backend API, authentication, role-based access (Ch. 6.4, 6.6) |
| Sumit | Frontend, charts, reports (Ch. 6.5, Ch. 8) |

Testing (Ch. 7) and documentation are shared.

---

## Viva preparation — questions to expect

**On the schema**
- Why does `attendance_records` reference `enrollment_id` rather than
  `student_pk` and `course_pk`? *(3NF: the pair is determined by the
  enrolment, not the attendance row — and it makes attendance for a
  non-enrolled student impossible.)*
- Your schema stores `percentage`, which is derived. Does that break 3NF?
  *(Yes, strictly — it is a deliberate, documented denormalisation for
  read performance and indexability, and a trigger guarantees it cannot
  drift from its inputs.)*
- How do you prevent two open alerts for the same student in one course?
  *(A STORED generated column that is NULL when resolved, inside a
  composite UNIQUE key — MySQL allows repeated NULLs, so only one open
  row can exist while resolved history is unlimited.)*

**On the risk model**
- What happens to a student with no marks yet? *(The academic component
  is dropped and the remaining weights re-normalise; with fewer than two
  components the result is INSUFFICIENT_DATA and no alert is raised.)*
- Why not treat missing marks as zero? *(Show the worked table from
  §5.3 — it turns a low-risk student into a medium-risk one.)*
- You have the model in SQL and in Python. How do you stop them
  disagreeing? *(One specification, half-up rounding on both sides, and
  integer cross-multiplication at the band boundaries instead of a float
  ratio.)*

**On performance**
- Your recalculation reads the base tables rather than the view you wrote
  for reporting. Why? *(Selecting one row from an aggregate view makes
  MySQL materialise the whole view first — `EXPLAIN` shows `<derived>`
  tables. It measured 4,406 ms per call at scale versus 33.5 ms against
  the base tables. A view is an abstraction, not an index.)*
- How do you know the optimisation did not change the results? *(Both
  versions were run against identical data and every field of all 80 rows
  matched, including the generated factor text.)*

**On triggers and procedures**
- Why is alert generation in a procedure rather than a trigger? *(A
  trigger on `risk_assessments` would fire per inserted row and could not
  easily see the open-alert state transactionally; keeping it in one
  procedure makes the raise/refresh/close decision a single atomic step —
  and avoids any recursion risk.)*
- Which triggers could recurse, and how did you avoid it? *(None: audit
  triggers only append to `audit_logs`, which has no triggers of its own;
  BEFORE triggers only modify `NEW`.)*

**On security**
- Why Argon2id rather than MD5 or SHA-256? *(Memory-hard and salted by
  design; a fast general-purpose hash is the wrong tool for passwords.)*
- Where is authorisation enforced? *(Server-side on every endpoint. The
  frontend hiding a button is a convenience, not a control — and
  `tests/test_rbac.py` asserts the 403 for every role/endpoint pair.)*
- How do you prevent SQL injection? *(All access is through SQLAlchemy
  with bound parameters; even the sortable-column name is validated
  against an allowlist rather than interpolated.)*
