-- =====================================================================
-- SE-EWRS : views.sql
-- Purpose : Analytical views used by the dashboard, the risk page and
--           every report endpoint. Run AFTER schema.sql.
--   mysql -u <user> -p se_ewrs < database/views.sql
-- ---------------------------------------------------------------------
-- Demonstrated concepts: inner/left joins, aggregate functions,
-- GROUP BY / HAVING, conditional aggregation, CTEs, window functions
-- and views built on top of other views.
-- =====================================================================

USE se_ewrs;

DROP VIEW IF EXISTS department_risk_summary;
DROP VIEW IF EXISTS student_risk_summary;
DROP VIEW IF EXISTS v_active_alerts;
DROP VIEW IF EXISTS v_intervention_outcomes;
DROP VIEW IF EXISTS v_submission_patterns;
DROP VIEW IF EXISTS course_performance_summary;
DROP VIEW IF EXISTS course_attendance_summary;
DROP VIEW IF EXISTS student_performance_view;
DROP VIEW IF EXISTS v_enrollment_activity;
DROP VIEW IF EXISTS v_enrollment_academics;
DROP VIEW IF EXISTS v_enrollment_attendance;
DROP VIEW IF EXISTS v_latest_risk;

-- ---------------------------------------------------------------------
-- v_enrollment_attendance
--   Attendance roll-up per enrolment. LATE still counts as attended
--   (the student was in the room); EXCUSED absences are removed from
--   the denominator so they cannot inflate attendance risk.
-- ---------------------------------------------------------------------
CREATE VIEW v_enrollment_attendance AS
SELECT
    e.enrollment_id,
    COUNT(a.attendance_id)                                   AS sessions_recorded,
    SUM(CASE WHEN a.status <> 'EXCUSED' THEN 1 ELSE 0 END)    AS sessions_held,
    SUM(CASE WHEN a.status IN ('PRESENT','LATE') THEN 1 ELSE 0 END)
                                                             AS sessions_attended,
    SUM(CASE WHEN a.status = 'ABSENT'  THEN 1 ELSE 0 END)     AS sessions_absent,
    SUM(CASE WHEN a.status = 'LATE'    THEN 1 ELSE 0 END)     AS sessions_late,
    SUM(CASE WHEN a.status = 'EXCUSED' THEN 1 ELSE 0 END)     AS sessions_excused,
    CASE
        WHEN SUM(CASE WHEN a.status <> 'EXCUSED' THEN 1 ELSE 0 END) = 0
            THEN NULL
        ELSE ROUND(
            100.0 * SUM(CASE WHEN a.status IN ('PRESENT','LATE') THEN 1 ELSE 0 END)
            / SUM(CASE WHEN a.status <> 'EXCUSED' THEN 1 ELSE 0 END), 2)
    END                                                      AS attendance_percentage,
    MAX(a.session_date)                                      AS last_session_date
FROM enrollments e
LEFT JOIN attendance_records a ON a.enrollment_id = e.enrollment_id
GROUP BY e.enrollment_id;

-- ---------------------------------------------------------------------
-- v_enrollment_academics
--   Academic roll-up per enrolment. Only graded rows (marks_obtained
--   IS NOT NULL) contribute to the average, so an ungraded assessment
--   never looks like a zero.
-- ---------------------------------------------------------------------
CREATE VIEW v_enrollment_academics AS
SELECT
    e.enrollment_id,
    COUNT(r.result_id)                                        AS results_recorded,
    SUM(CASE WHEN r.marks_obtained IS NOT NULL THEN 1 ELSE 0 END)
                                                              AS graded_assessments,
    ROUND(AVG(CASE WHEN r.marks_obtained IS NOT NULL
                   THEN r.percentage END), 2)                 AS avg_assessment_percentage,
    MIN(CASE WHEN r.marks_obtained IS NOT NULL
             THEN r.percentage END)                           AS min_assessment_percentage,
    MAX(CASE WHEN r.marks_obtained IS NOT NULL
             THEN r.percentage END)                           AS max_assessment_percentage,
    SUM(CASE WHEN r.submission_status = 'LATE'    THEN 1 ELSE 0 END)
                                                              AS late_submissions,
    SUM(CASE WHEN r.submission_status = 'MISSING' THEN 1 ELSE 0 END)
                                                              AS missing_submissions,
    SUM(CASE WHEN r.submission_status = 'ON_TIME' THEN 1 ELSE 0 END)
                                                              AS ontime_submissions,
    MAX(CASE WHEN r.marks_obtained IS NOT NULL
             THEN DATE(COALESCE(r.graded_at, r.submitted_at, r.created_at)) END)
                                                              AS last_assessment_date
FROM enrollments e
LEFT JOIN assessment_results r ON r.enrollment_id = e.enrollment_id
GROUP BY e.enrollment_id;

-- ---------------------------------------------------------------------
-- v_enrollment_activity
--   LMS engagement roll-up per enrolment, windowed on the last 30 days
--   for login frequency but unbounded for "last seen".
-- ---------------------------------------------------------------------
CREATE VIEW v_enrollment_activity AS
SELECT
    e.enrollment_id,
    COUNT(l.activity_id)                                      AS total_activities,
    SUM(CASE WHEN l.activity_type = 'LOGIN'
                  AND l.activity_at >= (CURRENT_DATE - INTERVAL 30 DAY)
             THEN 1 ELSE 0 END)                               AS login_count_30d,
    SUM(CASE WHEN l.activity_type = 'LOGIN' THEN 1 ELSE 0 END) AS login_count_total,
    SUM(CASE WHEN l.activity_type = 'QUIZ_ATTEMPT' THEN 1 ELSE 0 END)
                                                              AS quiz_attempts,
    SUM(CASE WHEN l.activity_type = 'ASSIGNMENT_SUBMIT' THEN 1 ELSE 0 END)
                                                              AS submission_events,
    COALESCE(SUM(l.duration_minutes), 0)                      AS total_minutes,
    MAX(l.activity_at)                                        AS last_activity_at,
    CASE WHEN MAX(l.activity_at) IS NULL THEN NULL
         ELSE DATEDIFF(CURRENT_DATE, DATE(MAX(l.activity_at))) END
                                                              AS days_since_last_activity
FROM enrollments e
LEFT JOIN lms_activity_logs l ON l.enrollment_id = e.enrollment_id
GROUP BY e.enrollment_id;

-- ---------------------------------------------------------------------
-- v_latest_risk
--   Most recent risk_assessments row per enrolment.
--   Uses a CTE + ROW_NUMBER() window function (MySQL 8 feature).
-- ---------------------------------------------------------------------
CREATE VIEW v_latest_risk AS
WITH ranked AS (
    SELECT ra.*,
           ROW_NUMBER() OVER (PARTITION BY ra.enrollment_id
                              ORDER BY ra.calculated_at DESC,
                                       ra.risk_id DESC) AS rn
    FROM risk_assessments ra
)
SELECT * FROM ranked WHERE rn = 1;

-- ---------------------------------------------------------------------
-- student_performance_view
--   One row per (student, course): the single source of truth for the
--   student profile page and for the risk recalculation procedure.
-- ---------------------------------------------------------------------
CREATE VIEW student_performance_view AS
SELECT
    e.enrollment_id,
    s.student_pk,
    s.student_id,
    s.full_name                 AS student_name,
    s.email                     AS student_email,
    s.semester                  AS student_semester,
    s.enrollment_year,
    s.is_active                 AS student_active,
    d.dept_id,
    d.dept_code,
    d.dept_name,
    c.course_pk,
    c.course_code,
    c.course_name,
    c.semester                  AS course_semester,
    c.academic_term,
    c.credits,
    e.status                    AS enrollment_status,
    e.enrolled_on,
    att.sessions_held,
    att.sessions_attended,
    att.sessions_absent,
    att.sessions_late,
    att.attendance_percentage,
    att.last_session_date,
    aca.graded_assessments,
    aca.avg_assessment_percentage,
    aca.min_assessment_percentage,
    aca.max_assessment_percentage,
    aca.ontime_submissions,
    aca.late_submissions,
    aca.missing_submissions,
    aca.last_assessment_date,
    act.login_count_30d,
    act.login_count_total,
    act.quiz_attempts,
    act.total_minutes,
    act.last_activity_at,
    act.days_since_last_activity
FROM enrollments e
JOIN students    s   ON s.student_pk = e.student_pk
JOIN departments d   ON d.dept_id    = s.dept_id
JOIN courses     c   ON c.course_pk  = e.course_pk
LEFT JOIN v_enrollment_attendance att ON att.enrollment_id = e.enrollment_id
LEFT JOIN v_enrollment_academics  aca ON aca.enrollment_id = e.enrollment_id
LEFT JOIN v_enrollment_activity   act ON act.enrollment_id = e.enrollment_id;

-- ---------------------------------------------------------------------
-- course_attendance_summary
--   Course-wise attendance report. GROUP BY + HAVING keeps courses that
--   actually have enrolments.
-- ---------------------------------------------------------------------
CREATE VIEW course_attendance_summary AS
SELECT
    c.course_pk,
    c.course_code,
    c.course_name,
    c.semester,
    c.academic_term,
    d.dept_code,
    d.dept_name,
    COUNT(DISTINCT e.enrollment_id)                      AS enrolled_students,
    COALESCE(SUM(att.sessions_held), 0)                  AS total_sessions_held,
    COALESCE(SUM(att.sessions_attended), 0)              AS total_sessions_attended,
    CASE WHEN COALESCE(SUM(att.sessions_held), 0) = 0 THEN NULL
         ELSE ROUND(100.0 * SUM(att.sessions_attended)
                    / SUM(att.sessions_held), 2) END     AS avg_attendance_percentage,
    SUM(CASE WHEN att.attendance_percentage < 75 THEN 1 ELSE 0 END)
                                                         AS students_below_75
FROM courses c
JOIN departments d ON d.dept_id = c.dept_id
LEFT JOIN enrollments e
       ON e.course_pk = c.course_pk AND e.status = 'ACTIVE'
LEFT JOIN v_enrollment_attendance att ON att.enrollment_id = e.enrollment_id
GROUP BY c.course_pk, c.course_code, c.course_name, c.semester,
         c.academic_term, d.dept_code, d.dept_name
HAVING COUNT(DISTINCT e.enrollment_id) > 0;

-- ---------------------------------------------------------------------
-- course_performance_summary
--   Course-wise average marks and pass rate (pass mark = 40%).
-- ---------------------------------------------------------------------
CREATE VIEW course_performance_summary AS
SELECT
    c.course_pk,
    c.course_code,
    c.course_name,
    c.semester,
    d.dept_code,
    COUNT(DISTINCT a.assessment_id)                      AS assessment_count,
    COUNT(r.result_id)                                   AS result_rows,
    SUM(CASE WHEN r.marks_obtained IS NOT NULL THEN 1 ELSE 0 END)
                                                         AS graded_rows,
    ROUND(AVG(r.percentage), 2)                          AS avg_percentage,
    ROUND(MIN(r.percentage), 2)                          AS min_percentage,
    ROUND(MAX(r.percentage), 2)                          AS max_percentage,
    ROUND(STDDEV_SAMP(r.percentage), 2)                  AS stddev_percentage,
    CASE WHEN SUM(CASE WHEN r.marks_obtained IS NOT NULL THEN 1 ELSE 0 END) = 0
         THEN NULL
         ELSE ROUND(100.0 * SUM(CASE WHEN r.percentage >= 40 THEN 1 ELSE 0 END)
              / SUM(CASE WHEN r.marks_obtained IS NOT NULL THEN 1 ELSE 0 END), 2)
    END                                                  AS pass_rate_percentage
FROM courses c
JOIN departments d ON d.dept_id = c.dept_id
LEFT JOIN assessments a ON a.course_pk = c.course_pk
LEFT JOIN assessment_results r
       ON r.assessment_id = a.assessment_id AND r.marks_obtained IS NOT NULL
GROUP BY c.course_pk, c.course_code, c.course_name, c.semester, d.dept_code;

-- ---------------------------------------------------------------------
-- v_submission_patterns
--   Assignment submission behaviour per assessment.
-- ---------------------------------------------------------------------
CREATE VIEW v_submission_patterns AS
SELECT
    a.assessment_id,
    a.title                                              AS assessment_title,
    a.assessment_type,
    a.due_at,
    a.max_marks,
    c.course_pk,
    c.course_code,
    c.course_name,
    d.dept_code,
    COUNT(r.result_id)                                   AS total_expected,
    SUM(CASE WHEN r.submission_status = 'ON_TIME' THEN 1 ELSE 0 END) AS on_time,
    SUM(CASE WHEN r.submission_status = 'LATE'    THEN 1 ELSE 0 END) AS late,
    SUM(CASE WHEN r.submission_status = 'MISSING' THEN 1 ELSE 0 END) AS missing,
    CASE WHEN COUNT(r.result_id) = 0 THEN NULL
         ELSE ROUND(100.0 * SUM(CASE WHEN r.submission_status = 'ON_TIME'
                                     THEN 1 ELSE 0 END)
                    / COUNT(r.result_id), 2) END         AS on_time_rate,
    ROUND(AVG(r.percentage), 2)                          AS avg_percentage
FROM assessments a
JOIN courses c     ON c.course_pk = a.course_pk
JOIN departments d ON d.dept_id   = c.dept_id
LEFT JOIN assessment_results r ON r.assessment_id = a.assessment_id
GROUP BY a.assessment_id, a.title, a.assessment_type, a.due_at, a.max_marks,
         c.course_pk, c.course_code, c.course_name, d.dept_code;

-- ---------------------------------------------------------------------
-- student_risk_summary
--   The heart of the risk-analysis page: latest risk score per
--   (student, course) joined to the human-readable context plus the
--   open-alert state.
-- ---------------------------------------------------------------------
CREATE VIEW student_risk_summary AS
SELECT
    spv.enrollment_id,
    spv.student_pk,
    spv.student_id,
    spv.student_name,
    spv.student_email,
    spv.student_semester,
    spv.dept_id,
    spv.dept_code,
    spv.dept_name,
    spv.course_pk,
    spv.course_code,
    spv.course_name,
    spv.academic_term,
    spv.enrollment_status,
    lr.risk_id,
    lr.risk_score,
    lr.risk_category,
    lr.data_completeness,
    lr.missing_data_reasons,
    lr.contributing_factors,
    lr.attendance_percentage,
    lr.avg_assessment_percentage,
    lr.engagement_score,
    lr.attendance_risk,
    lr.academic_risk,
    lr.engagement_risk,
    lr.late_submissions,
    lr.missing_submissions,
    lr.graded_assessments,
    lr.login_count_30d,
    lr.days_since_last_activity,
    lr.last_assessment_date,
    lr.calculated_at                                     AS risk_calculated_at,
    lr.model_version,
    al.alert_id                                          AS open_alert_id,
    al.status                                            AS open_alert_status,
    al.assigned_to                                       AS open_alert_assignee
FROM student_performance_view spv
LEFT JOIN v_latest_risk lr ON lr.enrollment_id = spv.enrollment_id
LEFT JOIN risk_alerts  al  ON al.enrollment_id = spv.enrollment_id
                          AND al.active_flag = 1;

-- ---------------------------------------------------------------------
-- department_risk_summary
--   Department-level KPIs for the Department Chair dashboard.
-- ---------------------------------------------------------------------
CREATE VIEW department_risk_summary AS
SELECT
    d.dept_id,
    d.dept_code,
    d.dept_name,
    COUNT(DISTINCT srs.student_pk)                       AS students_tracked,
    COUNT(srs.enrollment_id)                             AS enrollments_tracked,
    SUM(CASE WHEN srs.risk_category = 'HIGH'   THEN 1 ELSE 0 END) AS high_risk,
    SUM(CASE WHEN srs.risk_category = 'MEDIUM' THEN 1 ELSE 0 END) AS medium_risk,
    SUM(CASE WHEN srs.risk_category = 'LOW'    THEN 1 ELSE 0 END) AS low_risk,
    SUM(CASE WHEN srs.risk_category = 'INSUFFICIENT_DATA'
             THEN 1 ELSE 0 END)                          AS insufficient_data,
    -- An INSUFFICIENT_DATA row keeps the partial score of its one component;
    -- it is not an assessment, so the mean leaves it out.
    ROUND(AVG(CASE WHEN srs.risk_category IN ('LOW', 'MEDIUM', 'HIGH')
                   THEN srs.risk_score END), 2)          AS avg_risk_score,
    ROUND(AVG(srs.attendance_percentage), 2)             AS avg_attendance_percentage,
    ROUND(AVG(srs.avg_assessment_percentage), 2)         AS avg_assessment_percentage,
    SUM(CASE WHEN srs.open_alert_id IS NOT NULL THEN 1 ELSE 0 END)
                                                         AS open_alerts
FROM departments d
LEFT JOIN student_risk_summary srs ON srs.dept_id = d.dept_id
GROUP BY d.dept_id, d.dept_code, d.dept_name;

-- ---------------------------------------------------------------------
-- v_active_alerts
--   Open alerts enriched with student / course / assignee names so the
--   alerts table needs no further joins at query time.
-- ---------------------------------------------------------------------
CREATE VIEW v_active_alerts AS
SELECT
    al.alert_id,
    al.enrollment_id,
    al.risk_id,
    al.risk_score,
    al.risk_category,
    al.triggering_factors,
    al.status,
    al.assigned_to,
    u.full_name                 AS assignee_name,
    u.role                      AS assignee_role,
    al.acknowledged_at,
    al.resolved_at,
    al.created_at,
    al.updated_at,
    s.student_pk,
    s.student_id,
    s.full_name                 AS student_name,
    s.semester                  AS student_semester,
    d.dept_id,
    d.dept_code,
    c.course_pk,
    c.course_code,
    c.course_name,
    (SELECT COUNT(*) FROM interventions i WHERE i.alert_id = al.alert_id)
                                AS intervention_count
FROM risk_alerts al
JOIN enrollments e   ON e.enrollment_id = al.enrollment_id
JOIN students    s   ON s.student_pk    = e.student_pk
JOIN departments d   ON d.dept_id       = s.dept_id
JOIN courses     c   ON c.course_pk     = e.course_pk
LEFT JOIN users  u   ON u.user_id       = al.assigned_to;

-- ---------------------------------------------------------------------
-- v_intervention_outcomes
--   Intervention effectiveness report.
-- ---------------------------------------------------------------------
CREATE VIEW v_intervention_outcomes AS
SELECT
    i.intervention_id,
    i.intervention_type,
    i.outcome,
    i.resolution_status,
    i.contact_date,
    i.follow_up_date,
    i.notes,
    i.action_plan,
    i.alert_id,
    i.enrollment_id,
    adv.user_id                 AS advisor_id,
    adv.full_name               AS advisor_name,
    adv.role                    AS advisor_role,
    s.student_pk,
    s.student_id,
    s.full_name                 AS student_name,
    d.dept_code,
    c.course_pk,
    c.course_code,
    c.course_name,
    lr.risk_score               AS current_risk_score,
    lr.risk_category            AS current_risk_category
FROM interventions i
JOIN enrollments e   ON e.enrollment_id = i.enrollment_id
JOIN students    s   ON s.student_pk    = e.student_pk
JOIN departments d   ON d.dept_id       = s.dept_id
JOIN courses     c   ON c.course_pk     = e.course_pk
LEFT JOIN users  adv ON adv.user_id     = i.assigned_advisor_id
LEFT JOIN v_latest_risk lr ON lr.enrollment_id = i.enrollment_id;

SELECT 'views.sql applied successfully' AS status;
