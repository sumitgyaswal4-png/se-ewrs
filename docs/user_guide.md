# SE-EWRS — User Guide

Written for the people who will use the system: instructors, teaching
assistants, academic advisors, department chairs and the administrator.

---

## 1. What this system is for

Your LMS already records who logged in, who attended, who submitted late
and who scored what. SE-EWRS reads that data, combines it into a single
risk score per student per course, and raises an alert when a student
crosses a threshold — so you can reach them while there is still time to
help.

**The score is a prompt for a conversation, not a verdict.** It is built
from attendance, marks and engagement, which are proxies for how a
student is coping. They are not the student. Treat a high score as
"something is worth asking about here", never as a judgement.

---

## 2. Signing in

Go to the application (by default <http://localhost:5173>), enter your
institutional email and password, and you will land on the page that
matters most for your role.

| Role | Lands on | Can do |
|---|---|---|
| **Administrator** | Dashboard | Everything: students, courses, enrolments, staff accounts, system settings |
| **Instructor** | Dashboard | Their students, assessments and marks, risk scores, the alert queue, interventions |
| **Teaching Assistant** | Attendance | Record attendance and LMS activity, assist with interventions |
| **Academic Advisor** | Alerts | Work the alert queue, record counselling sessions, update outcomes |
| **Department Chair** | Reports | Read-only: department statistics, performance reports, risk summaries |

The menu only shows what your role can use. If you think something is
missing, it is almost certainly a permissions question for your
administrator.

**Signing out:** your name, top right → **Sign out**. Sessions expire
after 8 hours.

**Changing your password:** your name → **Account & password**.

---

## 3. The dashboard

Everything on this page is calculated from the live database.

**The top rows** are your headline counters: active students, courses,
enrolments and open alerts, then high-risk and medium-risk counts and the
average attendance and assessment figures.

**The red banner**, when it appears, counts unresolved high-risk alerts.
Click it to go straight to that filtered queue.

**Academic performance and attendance over time** plots the monthly mean
assessment percentage and attendance rate together. Both are percentages
on one axis, so you can read them against each other directly.

**Risk distribution** shows the share of enrolments in each band, with
counts and percentages beside the bar.

**Risk by department** breaks the same bands down per department.

**Recent risk alerts** lists the newest alerts, highest risk first, with
the factors that triggered each one.

**"Recalculate risk"** (instructors and administrators) re-scores every
active enrolment against the current data and raises, refreshes or
auto-closes alerts accordingly. Run it after a batch of marks or
attendance goes in.

---

## 4. Students

**Finding someone:** the search box matches roll number, name or email.
Filter by department, semester, risk band and active/inactive, and sort
by any underlined column heading.

Each row shows the student's enrolled course count, mean attendance,
mean assessment percentage and their **worst** risk band across all
courses.

**Adding a student** (administrator): **Add student**. The roll number
must be unique and cannot be changed afterwards — everything else can.

**The student profile** (click a name) shows the overall summary, an
engagement panel, their assessment trend, and one row per enrolled
course with attendance, marks, submissions and risk. **Risk detail** on
any row opens the full explanation for that course.

**Deactivating a student** is a soft delete. They leave active rosters
and dashboard counts, but their attendance, grades, risk history and
interventions are all kept — that history is the point of the system.
It can be undone.

---

## 5. Courses

The list shows each course with its teaching staff, headcount, mean
attendance, mean marks and how many of its students are at high risk.

* **Roster** — who is enrolled, with each student's current risk band.
* **Enrol** — tick students and add them in one go. Anyone already
  enrolled is skipped automatically; you cannot create a duplicate.
* **Staff** — assign an instructor or teaching assistant.
* **Edit** — change the name, credits, planned sessions or active status.

A course code may repeat across academic terms, but not within one.

---

## 6. Attendance

### Marking a session

1. Choose the **Course**.
2. **Mark a session**.
3. Set the date and session number. **All present** fills the roster in
   one click; then change just the exceptions.
4. **Save session**.

If you mark a session you have already recorded, it **corrects** the
existing entries rather than creating duplicates — so fixing a mistake is
simply marking it again.

### The four statuses

| Status | Effect on attendance percentage |
|---|---|
| **Present** | counts as attended |
| **Late** | counts as attended — the student was there |
| **Absent** | counts against |
| **Excused** | **removed from the calculation entirely** |

An authorised absence never depresses a student's attendance.

### Reviewing

**Totals** shows classes held and attended per student with the
percentage; anything below 75% is highlighted. **History** is the
record-by-record log, filterable by date range and status.

---

## 7. LMS activity

**Per student** shows login counts (last 30 days and total), quiz
attempts, submission events, minutes on task and when each student was
last seen. A student who has not appeared for more than two weeks is
highlighted.

**Event log** is the raw feed, filterable by course, event type and date.

Teaching assistants and administrators can add an event by hand with
**Log an event** — useful when importing from an LMS that has no direct
feed.

---

## 8. Assessments

### Creating one

**New assessment** → pick the course and type (assignment, quiz,
mid-term, final, project or lab), set the maximum marks, the weight
toward the final grade, and the deadline. The title must be unique
within the course.

The deadline matters: anything submitted after it is automatically
recorded as **Late**.

### Entering marks

**Enter marks** on any assessment opens the whole class at once. Type
the marks, optionally set the submission time, and **Save marks**.

* Percentages are calculated for you — you never type one.
* A mark below zero or above the maximum is **rejected**, and one bad
  mark rejects the entire sheet rather than saving half of it.
* **Leaving a mark blank records a submission without a grade.** This is
  not the same as zero: an ungraded item is excluded from the student's
  average rather than dragging it down.

### Reviewing

**Results** is the full marks history across courses. **Trends** plots
the monthly class average.

---

## 9. Risk analysis

### How the score is built

```
Risk Score = 0.35 × Attendance Risk
           + 0.40 × Academic Risk
           + 0.25 × Engagement Risk
```

Each part runs 0–100 where higher means more concerning:

* **Attendance Risk** = 100 − attendance %
* **Academic Risk** = 100 − average assessment %
* **Engagement Risk** = 100 − engagement score, where engagement starts
  at 100 and loses points for not logging in recently, logging in rarely,
  missing work and submitting late.

| Band | Score |
|---|---|
| **Low risk** | 0–29 |
| **Medium risk** | 30–59 |
| **High risk** | 60–100 |
| **Needs more data** | not scored |

### "Needs more data" is not a risk band

If fewer than two of the three components can be measured — no
attendance recorded yet, no graded work yet — the student is reported as
**Needs more data**, with the reason shown, and **no alert is raised**.

This is deliberate. A student three weeks into term with no marks yet is
not at risk; there is simply nothing to assess. The system will never
treat a missing measurement as a bad one.

When one component is missing but two remain, that component is dropped
and the others are re-weighted to compensate — so the score still means
"out of 100", just based on what is actually known.

### The detail page

Click any student in the risk table. You will see:

* the **score** and band;
* **How the score was built** — one bar per component, with both its
  normal weight and the weight actually applied;
* **Observed figures** — the raw attendance, marks and engagement;
* **Main contributing factors** in plain words, plus the engagement
  penalties broken out;
* **Risk score over time**, with the band thresholds marked.

If a component could not be measured, the page says which one and why.

---

## 10. Alerts

An alert is raised automatically when a student crosses the threshold
(by default a score of 30 or more). **There is never more than one open
alert per student per course** — if their risk changes, the existing
alert is updated rather than a second one appearing.

### Working the queue

| Status | Meaning |
|---|---|
| **New** | Raised; nobody has picked it up |
| **Acknowledged** | Someone has seen it and taken ownership |
| **In progress** | Contact has been made; something is happening |
| **Resolved** | Closed |

Allowed moves:

```
New → Acknowledged → In progress → Resolved
 │          └──────────────────────→ ┤
 └────────────────────────────────── ┘
```

You cannot move an alert backwards, and **Resolved is final**. If the
student's risk rises again later, a *fresh* alert is raised — which keeps
an honest record of how many separate episodes there were.

Open an alert to see the triggering factors, the full status history
(who changed what, when, and any note), and any interventions already
recorded. From there you can acknowledge it, assign it to an instructor
or advisor, and record an intervention against it.

**One thing to know:** if a student's risk falls below the threshold
while their alert is still **New**, the system closes it automatically.
Once *you* have acknowledged it, it stays open until you close it
yourself — the system will not take a decision out of your hands.

---

## 11. Interventions

An intervention records what was actually done about a student.

**Record an intervention** from the Interventions page, or directly from
an alert (which links the two together).

Fields: the type (counselling, tutoring referral, assignment support,
attendance follow-up, academic advising or guardian contact), the contact
date, your notes, the action plan, an optional follow-up date, the
outcome and the resolution status.

Come back and **Update** the record as things develop — set the outcome to
Improved, No change, Escalated or Student declined, and close it when
finished.

**Follow-up overdue** filters to records whose follow-up date has passed
and which are still open. That is your working list.

The **Intervention outcomes** report shows which types of intervention
are actually associated with improvement.

---

## 12. Reports

Seven reports, each with filters, a chart where one helps, the figures as
a table, and **Export CSV**.

| Report | Answers |
|---|---|
| **Risk distribution** | How is risk spread — by band, semester, department or course? |
| **Course performance** | Which courses have the lowest marks and pass rates? |
| **Course attendance** | Which courses have an attendance problem, and how many students are below 75%? |
| **Submission patterns** | Which assessments had the most late and missing work? |
| **At-risk students** | Who is at risk, and in how many courses at once? |
| **Department summary** | How do departments compare? |
| **Intervention outcomes** | Which interventions are followed by improvement? |

Every figure is calculated from the database when you ask for it.

---

## 13. Settings (administrator only)

The risk model is configuration, not code. You can retune it here without
a redeployment.

* **Weights** — attendance 0.35, academic 0.40, engagement 0.25 by default.
* **Bands and alerting** — where medium and high begin, and the score at
  which an alert is raised.
* **Data sufficiency** — how many attendance sessions and graded items a
  component needs before it counts. These are what stop a student with no
  data being labelled at risk; raising them makes the system more cautious.

Changes apply to the **next** recalculation. Scores already stored keep
the weights they were produced with, which is why each risk record notes
its own model version.

The **Audit trail** at the bottom records who changed what, including
sign-ins and failed sign-in attempts. Passwords are never recorded there.

---

## 14. Common questions

**A student looks high-risk but I know they are fine.**
Open their risk detail and read the contributing factors. Usually it is
stale data — attendance not recorded, or marks not entered. Enter the
missing data and recalculate.

**A student shows "Needs more data" and I expected a score.**
Not enough is recorded yet: fewer than three attendance sessions, or no
graded work. The page states exactly which component is missing.

**I entered marks but the risk score has not moved.**
Risk is recalculated on demand, not continuously. Press **Recalculate
risk** on the dashboard or the risk page.

**I resolved an alert and it came back.**
That is intended. Resolved is final, so when risk crosses the threshold
again a *new* alert is raised rather than the old one reopening.

**Can I delete a student?**
No — only deactivate. Their history is referenced by attendance, grades,
risk records and interventions, and deleting it would destroy the record
of what was done for them.

**Someone's attendance looks wrong.**
Check for Excused sessions: those are removed from the calculation
entirely, so 8 attended out of 10 recorded with 2 excused reads as 100%,
not 80%.

**I cannot see a page my colleague can.**
Page access follows your role. Your Account page lists exactly which
permissions you hold.

---

## 15. A note on using this responsibly

The risk score is built from proxies. Attendance drops for reasons that
have nothing to do with commitment — illness, caring responsibilities,
work, transport, a crisis at home. Engagement metrics measure clicks, not
understanding.

So: use a high score to start a conversation, and let the conversation —
not the number — tell you what is actually going on. A student flagged by
this system has not done anything wrong. They may need help, and that is
the whole point.

Do not share risk scores with students as if they were grades, and do not
use them in any decision the student cannot appeal to a human.
