-- =====================================================================
-- SE-EWRS : analytics_queries.sql
-- Purpose : Stand-alone analytical queries. These are the queries used
--           by the /api/reports/* endpoints, written out here so they
--           can be run and explained directly in the viva / report.
--           This file only READS -- it is safe to run at any time.
--   mysql -u <user> -p se_ewrs < database/analytics_queries.sql
-- =====================================================================

USE se_ewrs;

-- ---------------------------------------------------------------------
-- Q1. Dashboard headline counters.
-- Concepts: scalar subqueries, conditional aggregation over a view.
-- ---------------------------------------------------------------------
SELECT 'Q1: dashboard summary' AS query_label;
SELECT
    (SELECT COUNT(*) FROM students WHERE is_active = 1)        AS total_students,
    (SELECT COUNT(*) FROM courses  WHERE is_active = 1)        AS total_courses,
    (SELECT COUNT(*) FROM enrollments WHERE status = 'ACTIVE') AS total_enrollments,
    SUM(risk_category = 'HIGH')                                AS high_risk,
    SUM(risk_category = 'MEDIUM')                              AS medium_risk,
    SUM(risk_category = 'LOW')                                 AS low_risk,
    SUM(risk_category = 'INSUFFICIENT_DATA')                   AS insufficient_data,
    ROUND(AVG(attendance_percentage), 2)                       AS avg_attendance,
    ROUND(AVG(avg_assessment_percentage), 2)                   AS avg_assessment
FROM student_risk_summary;

-- ---------------------------------------------------------------------
-- Q2. Students grouped by risk category, worst first.
-- Concepts: join across 4 tables via a view, ORDER BY on a derived col.
-- ---------------------------------------------------------------------
SELECT 'Q2: students by risk category' AS query_label;
SELECT risk_category,
       COUNT(*)                        AS students,
       ROUND(AVG(risk_score), 2)       AS avg_score,
       ROUND(MIN(risk_score), 2)       AS min_score,
       ROUND(MAX(risk_score), 2)       AS max_score
FROM student_risk_summary
GROUP BY risk_category
ORDER BY FIELD(risk_category, 'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_DATA');

-- ---------------------------------------------------------------------
-- Q3. Course-wise attendance, only courses averaging under 80%.
-- Concepts: GROUP BY + HAVING on an aggregate.
-- ---------------------------------------------------------------------
SELECT 'Q3: courses averaging under 80% attendance' AS query_label;
SELECT course_code, course_name, enrolled_students,
       total_sessions_held, total_sessions_attended,
       avg_attendance_percentage
FROM course_attendance_summary
WHERE avg_attendance_percentage IS NOT NULL
HAVING avg_attendance_percentage < 80
ORDER BY avg_attendance_percentage ASC;

-- ---------------------------------------------------------------------
-- Q4. Course-wise average marks with the department roll-up.
-- Concepts: multi-table join, aggregate functions, STDDEV.
-- ---------------------------------------------------------------------
SELECT 'Q4: course performance' AS query_label;
SELECT c.course_code, c.course_name, d.dept_code,
       COUNT(DISTINCT a.assessment_id)  AS assessments,
       COUNT(r.result_id)               AS graded_results,
       ROUND(AVG(r.percentage), 2)      AS avg_percentage,
       ROUND(STDDEV_SAMP(r.percentage), 2) AS spread,
       ROUND(100.0 * SUM(r.percentage >= 40) / NULLIF(COUNT(r.result_id), 0), 2)
                                        AS pass_rate
FROM courses c
JOIN departments d        ON d.dept_id = c.dept_id
JOIN assessments a        ON a.course_pk = c.course_pk
JOIN assessment_results r ON r.assessment_id = a.assessment_id
                         AND r.marks_obtained IS NOT NULL
GROUP BY c.course_pk, c.course_code, c.course_name, d.dept_code
HAVING COUNT(r.result_id) > 0
ORDER BY avg_percentage ASC;

-- ---------------------------------------------------------------------
-- Q5. Students performing below their own course average.
-- Concepts: correlated subquery in the WHERE clause.
-- ---------------------------------------------------------------------
SELECT 'Q5: students below their course average' AS query_label;
SELECT spv.student_id, spv.student_name, spv.course_code,
       spv.avg_assessment_percentage AS student_avg,
       (SELECT ROUND(AVG(x.avg_assessment_percentage), 2)
          FROM student_performance_view x
         WHERE x.course_pk = spv.course_pk) AS course_avg
FROM student_performance_view spv
WHERE spv.avg_assessment_percentage IS NOT NULL
  AND spv.avg_assessment_percentage <
      (SELECT AVG(x.avg_assessment_percentage)
         FROM student_performance_view x
        WHERE x.course_pk = spv.course_pk)
ORDER BY spv.course_code, spv.avg_assessment_percentage ASC;

-- ---------------------------------------------------------------------
-- Q6. High-risk students by department, with the department share.
-- Concepts: CTE + window function (SUM OVER) for the percentage.
-- ---------------------------------------------------------------------
SELECT 'Q6: high-risk students by department' AS query_label;
WITH per_dept AS (
    SELECT dept_code, dept_name,
           COUNT(*)                                AS enrollments,
           SUM(risk_category = 'HIGH')             AS high_risk
    FROM student_risk_summary
    GROUP BY dept_code, dept_name
)
SELECT dept_code, dept_name, enrollments, high_risk,
       ROUND(100.0 * high_risk / NULLIF(enrollments, 0), 2) AS high_risk_pct,
       ROUND(100.0 * high_risk / NULLIF(SUM(high_risk) OVER (), 0), 2)
                                                            AS share_of_all_high_risk
FROM per_dept
ORDER BY high_risk DESC;

-- ---------------------------------------------------------------------
-- Q7. Risk distribution by semester.
-- Concepts: pivot via conditional aggregation.
-- ---------------------------------------------------------------------
SELECT 'Q7: risk distribution by semester' AS query_label;
SELECT student_semester                      AS semester,
       COUNT(*)                              AS enrollments,
       SUM(risk_category = 'LOW')            AS low_risk,
       SUM(risk_category = 'MEDIUM')         AS medium_risk,
       SUM(risk_category = 'HIGH')           AS high_risk,
       SUM(risk_category = 'INSUFFICIENT_DATA') AS insufficient_data,
       ROUND(AVG(risk_score), 2)             AS avg_risk_score
FROM student_risk_summary
GROUP BY student_semester
ORDER BY student_semester;

-- ---------------------------------------------------------------------
-- Q8. Assignment submission patterns per assessment.
-- Concepts: LEFT JOIN so assessments with zero submissions still show.
-- ---------------------------------------------------------------------
SELECT 'Q8: submission patterns' AS query_label;
SELECT course_code, assessment_title, assessment_type, due_at,
       total_expected, on_time, late, missing, on_time_rate, avg_percentage
FROM v_submission_patterns
ORDER BY course_code, due_at;

-- ---------------------------------------------------------------------
-- Q9. Academic performance trend -- average score per course per month.
-- Concepts: date truncation, GROUP BY on an expression.
-- ---------------------------------------------------------------------
SELECT 'Q9: monthly performance trend' AS query_label;
SELECT DATE_FORMAT(a.due_at, '%Y-%m')   AS period,
       c.course_code,
       COUNT(r.result_id)               AS graded_results,
       ROUND(AVG(r.percentage), 2)      AS avg_percentage
FROM assessments a
JOIN courses c            ON c.course_pk = a.course_pk
JOIN assessment_results r ON r.assessment_id = a.assessment_id
                         AND r.marks_obtained IS NOT NULL
GROUP BY period, c.course_pk, c.course_code
ORDER BY period, c.course_code;

-- ---------------------------------------------------------------------
-- Q10. Intervention effectiveness by type.
-- Concepts: aggregate over a view, HAVING to drop thin samples.
-- ---------------------------------------------------------------------
SELECT 'Q10: intervention outcomes' AS query_label;
SELECT intervention_type,
       COUNT(*)                            AS total,
       SUM(outcome = 'IMPROVED')           AS improved,
       SUM(outcome = 'NO_CHANGE')          AS no_change,
       SUM(outcome = 'PENDING')            AS pending,
       SUM(outcome = 'ESCALATED')          AS escalated,
       SUM(outcome = 'DECLINED')           AS declined,
       ROUND(100.0 * SUM(outcome = 'IMPROVED') / COUNT(*), 2) AS improvement_rate,
       ROUND(AVG(current_risk_score), 2)   AS avg_current_risk
FROM v_intervention_outcomes
GROUP BY intervention_type
HAVING COUNT(*) > 0
ORDER BY improvement_rate DESC;

-- ---------------------------------------------------------------------
-- Q11. Risk trend over time -- each enrolment's change between its two
--      most recent risk calculations.
-- Concepts: CTE + LAG() window function.
-- ---------------------------------------------------------------------
SELECT 'Q11: risk movement since previous calculation' AS query_label;
WITH seq AS (
    SELECT ra.enrollment_id, ra.calculated_at, ra.risk_score, ra.risk_category,
           LAG(ra.risk_score) OVER (PARTITION BY ra.enrollment_id
                                    ORDER BY ra.calculated_at) AS prev_score,
           ROW_NUMBER() OVER (PARTITION BY ra.enrollment_id
                              ORDER BY ra.calculated_at DESC)  AS rn
    FROM risk_assessments ra
)
SELECT s.student_id, s.full_name AS student_name, c.course_code,
       seq.prev_score, seq.risk_score AS current_score,
       ROUND(seq.risk_score - seq.prev_score, 2) AS delta,
       seq.risk_category
FROM seq
JOIN enrollments e ON e.enrollment_id = seq.enrollment_id
JOIN students    s ON s.student_pk    = e.student_pk
JOIN courses     c ON c.course_pk     = e.course_pk
WHERE seq.rn = 1 AND seq.prev_score IS NOT NULL
ORDER BY delta DESC;

-- ---------------------------------------------------------------------
-- Q12. Unresolved high-risk alerts older than 7 days -- the escalation
--      queue the dashboard highlights.
-- Concepts: date arithmetic, join to the assignee, IS NULL handling.
-- ---------------------------------------------------------------------
SELECT 'Q12: ageing unresolved high-risk alerts' AS query_label;
SELECT alert_id, student_id, student_name, course_code,
       risk_score, status,
       COALESCE(assignee_name, '(unassigned)') AS assignee,
       created_at,
       DATEDIFF(CURRENT_DATE, DATE(created_at)) AS age_days
FROM v_active_alerts
WHERE risk_category = 'HIGH'
  AND status <> 'RESOLVED'
  AND created_at < (NOW() - INTERVAL 7 DAY)
ORDER BY age_days DESC, risk_score DESC;

-- ---------------------------------------------------------------------
-- Q13. Students at risk in more than one course simultaneously.
-- Concepts: GROUP BY + HAVING COUNT(*) > 1, GROUP_CONCAT.
-- ---------------------------------------------------------------------
SELECT 'Q13: students at risk in multiple courses' AS query_label;
SELECT student_id, student_name, dept_code,
       COUNT(*)                                   AS at_risk_courses,
       GROUP_CONCAT(course_code ORDER BY course_code SEPARATOR ', ') AS courses,
       ROUND(AVG(risk_score), 2)                  AS avg_risk_score
FROM student_risk_summary
WHERE risk_category IN ('MEDIUM', 'HIGH')
GROUP BY student_pk, student_id, student_name, dept_code
HAVING COUNT(*) > 1
ORDER BY at_risk_courses DESC, avg_risk_score DESC;

-- ---------------------------------------------------------------------
-- Q14. Engagement cliff -- enrolments with no LMS event in 14+ days.
-- Concepts: LEFT JOIN + aggregate in a derived table, NULL semantics.
-- ---------------------------------------------------------------------
SELECT 'Q14: disengaged enrolments' AS query_label;
SELECT spv.student_id, spv.student_name, spv.course_code,
       spv.last_activity_at, spv.days_since_last_activity,
       spv.login_count_30d, spv.attendance_percentage
FROM student_performance_view spv
WHERE spv.days_since_last_activity IS NULL
   OR spv.days_since_last_activity >= 14
ORDER BY spv.days_since_last_activity IS NULL DESC,
         spv.days_since_last_activity DESC;

-- ---------------------------------------------------------------------
-- Q15. Index usage proof -- run EXPLAIN on the hottest filter to show
--      the composite index on (enrollment_id, activity_at) being used.
-- ---------------------------------------------------------------------
SELECT 'Q15: EXPLAIN for the LMS activity window scan' AS query_label;
EXPLAIN SELECT COUNT(*) FROM lms_activity_logs
 WHERE enrollment_id = 1
   AND activity_at >= (CURRENT_DATE - INTERVAL 30 DAY);
