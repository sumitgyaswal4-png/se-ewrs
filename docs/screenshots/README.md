# Screenshots

Captured from the running application on **2026-10-27** against the MySQL 8
demo database, using the dataset `database/seed.sql` loads. Nothing here is
a mock-up: every figure in every image was produced by the backend from the
database, so the numbers agree across images (41 low, 26 medium, 9 high and
4 needing more data).

They are taken at a 1440 × 980 viewport and stored at 1× for the written
report, which is why the long pages are tall.

To re-take them after a change, load the demo data and run the app, then
capture again — the figures should match this set exactly, because the seed
writes dates as `CURDATE()` arithmetic rather than fixed dates.

One trap if you automate it: do not use a browser driver's *full page*
screenshot on a page that holds a chart. That mode re-lays-out the page
while it captures, Recharts' `ResponsiveContainer` re-measures, and the
chart lands squeezed into a sliver at the left of its card — even though
the live page is perfectly fine. Set the viewport to the page's full
height first, let it settle, then take an ordinary screenshot.

| # | File | What it shows |
|---|---|---|
| 1 | `01-login.png` | The login page, with the demo accounts listed and a **Use** button that fills the form. The password field never leaves the browser in plain form: it is sent once and exchanged for a JWT. |
| 2 | `02-dashboard-admin.png` | The administrator dashboard. Every tile and both charts are aggregated by SQL from the recorded data — no figure on this page is hard-coded. The risk-distribution bar carries a legend, direct counts and a matching table, so the bands never depend on colour alone. |
| 3 | `03-students-filtered-high-risk.png` | Student management with the **Risk band = High** filter applied, narrowing 36 students to the 5 who have a high-risk enrolment. Filtering happens in SQL with bound parameters, not in the browser. |
| 4 | `04-student-profile.png` | One student across all their courses: attendance and assessment meters, per-course risk bands, and the open alerts raised for them. |
| 5 | `05-attendance-marking.png` | Marking a whole session in one pass. The sheet refuses to open until a course is chosen, because a session belongs to one course's roster; re-marking a session that was already recorded corrects it rather than creating a duplicate. |
| 6 | `06-marks-validation-rejected.png` | **Validation rejecting an out-of-range mark.** A mark of 999 was entered against an assessment worth 10. The HTML input carries `max`, but that is not what stops it: the request was sent and the server refused it — *"Marks obtained (999.0) cannot exceed the maximum marks (10.00)"*. The same rule is enforced again in the database, so it holds for a direct SQL write too: a CHECK constraint rejects a negative mark, and a BEFORE INSERT/UPDATE trigger rejects one above the assessment's maximum — that half has to be a trigger, because the limit lives in another table and a CHECK cannot read one. Note also the **Missing** badge: an ungraded row is recorded as missing work, never silently scored zero. |
| 7 | `07-risk-analysis-table.png` | The risk analysis table: every enrolment with its score, band and components, sortable and filterable. |
| 8 | `08-risk-detail.png` | **The single most informative screenshot.** For one enrolment it shows the score, the band, the weights, the three component risks, the observed figures behind them, the contributing factors in words, the engagement penalty breakdown, and the history. The footer states that the score is an early-warning indicator and not a judgement about the student. |
| 9 | `09-alerts-queue.png` | The early-warning alert queue, filterable by status, band and course. |
| 10 | `10-alert-detail-history.png` | One alert with its **status history** — who changed it, when, and the note they left. The history is written by the API inside the same transaction as the status change, so the two cannot disagree. |
| 11 | `11-interventions.png` | Intervention tracking: what was tried for a student, by whom, and how it ended. |
| 12 | `12-reports-csv-export.png` | Reports and analytics, just after a real CSV export (the toast confirms the download). `example-risk-distribution-export.csv` beside this file is the exact file that download produced. Every chart on the page has the matching table next to it. |
| 13 | `13-settings-risk-weights.png` | The configurable risk model: the three weights, the band thresholds and the engagement penalties, all read from `system_settings` rather than compiled in. The page warns if the weights stop summing to 1.00. |
| 14 | `14-rbac-teaching-assistant.png` | The same application as a **Teaching Assistant** — no Alerts, no Staff accounts, no Settings, and the write actions the role lacks are absent rather than disabled. The TA lands on Attendance. |
| 15 | `15-rbac-department-chair.png` | The same application as a **Department Chair**, who lands on Reports and holds no write permission at all. Hiding the control is only the visible half: every endpoint behind it re-checks the permission server-side, so a hand-made request is refused too. |

## A note on colour

Risk bands use a fixed status palette (green / amber / red / grey) that is
never reused for anything else, and every band is accompanied by an icon, a
text label and a direct count. Two of the four band colours fall below a
3:1 contrast ratio against white, which is why colour is never the only
carrier of meaning and why each chart ships the same figures as a table.

The meters on the student and risk pages are coloured by the band the
figure's own component risk falls in, so a poor figure is never drawn in a
reassuring colour.
