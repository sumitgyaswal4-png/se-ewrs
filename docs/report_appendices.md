# SE-EWRS — Report appendices

Appendices A–E to `docs/report.md`. **This file is generated** by
`docs/build_appendices.py` from the files it reproduces; edit those,
not this. A test fails if the two disagree.

---

## Appendix A — Schema

The complete data definition: sixteen tables, their keys, `CHECK` constraints and indexes (Chapter 4).

### `database/schema.sql`

```sql
-- =====================================================================
-- SE-EWRS : Student Engagement & Early Warning Risk System
-- File    : schema.sql
-- Purpose : Normalised relational schema (3NF) for MySQL 8.0+
-- Course  : Database Management Systems -- Department of Mathematics
-- Team    : Mohammad Adnan, Lucky Dhall, Raja, Sumit
-- ---------------------------------------------------------------------
-- Run with:
--   mysql -u <user> -p < database/schema.sql
-- ---------------------------------------------------------------------
-- Requires MySQL 8.0.16+ (enforced CHECK constraints, STORED generated
-- columns, CTEs and window functions are all used by this project).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS se_ewrs
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE se_ewrs;

-- Drop in reverse dependency order so the script is re-runnable.
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS system_settings;
DROP TABLE IF EXISTS interventions;
DROP TABLE IF EXISTS alert_status_history;
DROP TABLE IF EXISTS risk_alerts;
DROP TABLE IF EXISTS risk_assessments;
DROP TABLE IF EXISTS assessment_results;
DROP TABLE IF EXISTS assessments;
DROP TABLE IF EXISTS lms_activity_logs;
DROP TABLE IF EXISTS attendance_records;
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS course_instructors;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS departments;
SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================================
-- 1. departments
--    Reference table. One department -> many users / students / courses.
-- =====================================================================
CREATE TABLE departments (
    dept_id     INT             NOT NULL AUTO_INCREMENT,
    dept_code   VARCHAR(10)     NOT NULL,
    dept_name   VARCHAR(120)    NOT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (dept_id),
    UNIQUE KEY uq_departments_code (dept_code),
    UNIQUE KEY uq_departments_name (dept_name)
) ENGINE = InnoDB;

-- =====================================================================
-- 2. users
--    All staff accounts. `role` drives role-based access control.
--    password_hash stores an Argon2id digest -- never a plaintext value.
-- =====================================================================
CREATE TABLE users (
    user_id         INT             NOT NULL AUTO_INCREMENT,
    full_name       VARCHAR(120)    NOT NULL,
    email           VARCHAR(160)    NOT NULL,
    password_hash   VARCHAR(255)    NOT NULL,
    role            ENUM('ADMIN','INSTRUCTOR','TA','ADVISOR','CHAIR')
                                    NOT NULL,
    dept_id         INT             NULL,
    phone           VARCHAR(20)     NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    last_login_at   DATETIME        NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email),
    KEY ix_users_role (role),
    KEY ix_users_dept (dept_id),
    CONSTRAINT fk_users_dept FOREIGN KEY (dept_id)
        REFERENCES departments (dept_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE = InnoDB;

-- =====================================================================
-- 3. students
--    student_pk  : surrogate key used by every child table.
--    student_id  : human-facing roll number (e.g. MTH2023001).
-- =====================================================================
CREATE TABLE students (
    student_pk      INT             NOT NULL AUTO_INCREMENT,
    student_id      VARCHAR(20)     NOT NULL,
    full_name       VARCHAR(120)    NOT NULL,
    email           VARCHAR(160)    NOT NULL,
    dept_id         INT             NOT NULL,
    semester        TINYINT         NOT NULL,
    enrollment_year SMALLINT        NOT NULL,
    phone           VARCHAR(20)     NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (student_pk),
    UNIQUE KEY uq_students_student_id (student_id),
    UNIQUE KEY uq_students_email (email),
    KEY ix_students_dept (dept_id),
    KEY ix_students_semester (semester),
    KEY ix_students_active (is_active),
    KEY ix_students_name (full_name),
    CONSTRAINT fk_students_dept FOREIGN KEY (dept_id)
        REFERENCES departments (dept_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT ck_students_semester
        CHECK (semester BETWEEN 1 AND 12),
    CONSTRAINT ck_students_year
        CHECK (enrollment_year BETWEEN 2000 AND 2100)
) ENGINE = InnoDB;

-- =====================================================================
-- 4. courses
-- =====================================================================
CREATE TABLE courses (
    course_pk       INT             NOT NULL AUTO_INCREMENT,
    course_code     VARCHAR(20)     NOT NULL,
    course_name     VARCHAR(150)    NOT NULL,
    dept_id         INT             NOT NULL,
    semester        TINYINT         NOT NULL,
    credits         TINYINT         NOT NULL DEFAULT 3,
    academic_term   VARCHAR(20)     NOT NULL,
    total_sessions  SMALLINT        NOT NULL DEFAULT 0,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (course_pk),
    UNIQUE KEY uq_courses_code_term (course_code, academic_term),
    KEY ix_courses_dept (dept_id),
    KEY ix_courses_semester (semester),
    KEY ix_courses_active (is_active),
    CONSTRAINT fk_courses_dept FOREIGN KEY (dept_id)
        REFERENCES departments (dept_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT ck_courses_semester CHECK (semester BETWEEN 1 AND 12),
    CONSTRAINT ck_courses_credits  CHECK (credits BETWEEN 1 AND 10),
    CONSTRAINT ck_courses_sessions CHECK (total_sessions >= 0)
) ENGINE = InnoDB;

-- =====================================================================
-- 5. course_instructors  (resolves the M:N between courses and users)
-- =====================================================================
CREATE TABLE course_instructors (
    course_instructor_id INT        NOT NULL AUTO_INCREMENT,
    course_pk       INT             NOT NULL,
    user_id         INT             NOT NULL,
    role_in_course  ENUM('PRIMARY','CO_INSTRUCTOR','TA')
                                    NOT NULL DEFAULT 'PRIMARY',
    assigned_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (course_instructor_id),
    UNIQUE KEY uq_course_instructor (course_pk, user_id),
    KEY ix_ci_user (user_id),
    CONSTRAINT fk_ci_course FOREIGN KEY (course_pk)
        REFERENCES courses (course_pk)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ci_user FOREIGN KEY (user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE = InnoDB;

-- =====================================================================
-- 6. enrollments  (resolves the M:N between students and courses)
--    The composite UNIQUE key is what prevents duplicate enrolment.
--    Every engagement fact below hangs off enrollment_id, which
--    guarantees a record can never exist for a non-enrolled student.
-- =====================================================================
CREATE TABLE enrollments (
    enrollment_id   INT             NOT NULL AUTO_INCREMENT,
    student_pk      INT             NOT NULL,
    course_pk       INT             NOT NULL,
    enrolled_on     DATE            NOT NULL,
    status          ENUM('ACTIVE','DROPPED','COMPLETED')
                                    NOT NULL DEFAULT 'ACTIVE',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (enrollment_id),
    UNIQUE KEY uq_enrollment_student_course (student_pk, course_pk),
    KEY ix_enrollments_course (course_pk),
    KEY ix_enrollments_status (status),
    CONSTRAINT fk_enroll_student FOREIGN KEY (student_pk)
        REFERENCES students (student_pk)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_enroll_course FOREIGN KEY (course_pk)
        REFERENCES courses (course_pk)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE = InnoDB;

-- =====================================================================
-- 7. attendance_records
--    One row per (enrollment, calendar session). The composite UNIQUE
--    key stops a student being marked twice for the same class session.
-- =====================================================================
CREATE TABLE attendance_records (
    attendance_id   INT             NOT NULL AUTO_INCREMENT,
    enrollment_id   INT             NOT NULL,
    session_date    DATE            NOT NULL,
    session_no      SMALLINT        NOT NULL DEFAULT 1,
    status          ENUM('PRESENT','ABSENT','LATE','EXCUSED')
                                    NOT NULL,
    recorded_by     INT             NULL,
    remarks         VARCHAR(255)    NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (attendance_id),
    UNIQUE KEY uq_attendance_session
        (enrollment_id, session_date, session_no),
    KEY ix_attendance_date (session_date),
    KEY ix_attendance_status (status),
    KEY ix_attendance_enrollment (enrollment_id),
    CONSTRAINT fk_att_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_att_recorder FOREIGN KEY (recorded_by)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT ck_attendance_session_no CHECK (session_no >= 1)
) ENGINE = InnoDB;

-- =====================================================================
-- 8. lms_activity_logs
--    Raw engagement telemetry: logins, resource views, submissions...
-- =====================================================================
CREATE TABLE lms_activity_logs (
    activity_id     BIGINT          NOT NULL AUTO_INCREMENT,
    enrollment_id   INT             NOT NULL,
    activity_type   ENUM('LOGIN','RESOURCE_VIEW','FORUM_POST',
                         'VIDEO_WATCH','QUIZ_ATTEMPT','ASSIGNMENT_SUBMIT')
                                    NOT NULL,
    activity_at     DATETIME        NOT NULL,
    duration_minutes INT            NULL,
    resource_ref    VARCHAR(160)    NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id),
    KEY ix_lms_enrollment_time (enrollment_id, activity_at),
    KEY ix_lms_activity_at (activity_at),
    KEY ix_lms_type (activity_type),
    CONSTRAINT fk_lms_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT ck_lms_duration
        CHECK (duration_minutes IS NULL OR duration_minutes >= 0)
) ENGINE = InnoDB;

-- =====================================================================
-- 9. assessments  (the graded item itself -- one per course)
-- =====================================================================
CREATE TABLE assessments (
    assessment_id   INT             NOT NULL AUTO_INCREMENT,
    course_pk       INT             NOT NULL,
    title           VARCHAR(150)    NOT NULL,
    assessment_type ENUM('ASSIGNMENT','QUIZ','MIDTERM','FINAL',
                         'PROJECT','LAB')
                                    NOT NULL,
    max_marks       DECIMAL(6,2)    NOT NULL,
    weight_percent  DECIMAL(5,2)    NOT NULL DEFAULT 0,
    due_at          DATETIME        NOT NULL,
    created_by      INT             NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (assessment_id),
    UNIQUE KEY uq_assessment_course_title (course_pk, title),
    KEY ix_assessments_due (due_at),
    KEY ix_assessments_type (assessment_type),
    CONSTRAINT fk_assess_course FOREIGN KEY (course_pk)
        REFERENCES courses (course_pk)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_assess_creator FOREIGN KEY (created_by)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT ck_assess_max_marks CHECK (max_marks > 0),
    CONSTRAINT ck_assess_weight
        CHECK (weight_percent >= 0 AND weight_percent <= 100)
) ENGINE = InnoDB;

-- =====================================================================
-- 10. assessment_results
--     marks_obtained IS NULL  => not graded / nothing submitted.
--     `percentage` is maintained by the trg_ar_* triggers so that the
--     database guarantees it matches marks_obtained / max_marks * 100
--     no matter which client wrote the row.
-- =====================================================================
CREATE TABLE assessment_results (
    result_id       INT             NOT NULL AUTO_INCREMENT,
    assessment_id   INT             NOT NULL,
    enrollment_id   INT             NOT NULL,
    marks_obtained  DECIMAL(6,2)    NULL,
    percentage      DECIMAL(5,2)    NULL,
    submitted_at    DATETIME        NULL,
    submission_status ENUM('ON_TIME','LATE','MISSING')
                                    NOT NULL DEFAULT 'MISSING',
    attempt_no      TINYINT         NOT NULL DEFAULT 1,
    graded_by       INT             NULL,
    graded_at       DATETIME        NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (result_id),
    UNIQUE KEY uq_result_assessment_enrollment
        (assessment_id, enrollment_id),
    KEY ix_results_enrollment (enrollment_id),
    KEY ix_results_status (submission_status),
    KEY ix_results_submitted (submitted_at),
    CONSTRAINT fk_result_assessment FOREIGN KEY (assessment_id)
        REFERENCES assessments (assessment_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_result_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_result_grader FOREIGN KEY (graded_by)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT ck_result_marks_nonneg
        CHECK (marks_obtained IS NULL OR marks_obtained >= 0),
    CONSTRAINT ck_result_attempt CHECK (attempt_no >= 1)
) ENGINE = InnoDB;

-- =====================================================================
-- 11. risk_assessments
--     Append-only history: one row per enrolment per recalculation run,
--     so risk can be trended over time.
-- =====================================================================
CREATE TABLE risk_assessments (
    risk_id         INT             NOT NULL AUTO_INCREMENT,
    enrollment_id   INT             NOT NULL,
    calculated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- raw observed inputs (NULL = not observable yet)
    attendance_percentage       DECIMAL(5,2) NULL,
    avg_assessment_percentage   DECIMAL(5,2) NULL,
    engagement_score            DECIMAL(5,2) NULL,

    -- derived 0-100 risk components
    attendance_risk DECIMAL(5,2)    NULL,
    academic_risk   DECIMAL(5,2)    NULL,
    engagement_risk DECIMAL(5,2)    NULL,

    risk_score      DECIMAL(5,2)    NULL,
    risk_category   ENUM('LOW','MEDIUM','HIGH','INSUFFICIENT_DATA')
                                    NOT NULL,
    data_completeness ENUM('COMPLETE','PARTIAL','INSUFFICIENT')
                                    NOT NULL,
    missing_data_reasons VARCHAR(500) NULL,
    contributing_factors VARCHAR(1000) NULL,

    -- supporting counters surfaced in the UI
    sessions_held       SMALLINT    NOT NULL DEFAULT 0,
    sessions_attended   SMALLINT    NOT NULL DEFAULT 0,
    late_submissions    SMALLINT    NOT NULL DEFAULT 0,
    missing_submissions SMALLINT    NOT NULL DEFAULT 0,
    graded_assessments  SMALLINT    NOT NULL DEFAULT 0,
    login_count_30d     SMALLINT    NOT NULL DEFAULT 0,
    days_since_last_activity SMALLINT NULL,
    last_assessment_date DATE       NULL,
    model_version   VARCHAR(20)     NOT NULL DEFAULT 'rule-v1',

    PRIMARY KEY (risk_id),
    KEY ix_risk_enrollment_time (enrollment_id, calculated_at),
    KEY ix_risk_category (risk_category),
    KEY ix_risk_calculated (calculated_at),
    KEY ix_risk_score (risk_score),
    CONSTRAINT fk_risk_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT ck_risk_score_range
        CHECK (risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100))
) ENGINE = InnoDB;

-- =====================================================================
-- 12. risk_alerts
--     active_flag is a STORED generated column that is 1 while the alert
--     is open and NULL once resolved. Because MySQL permits repeated
--     NULLs inside a UNIQUE key, the composite key below allows at most
--     ONE open alert per enrolment while keeping full resolved history.
--     This is the database-level guard against duplicate active alerts.
-- =====================================================================
CREATE TABLE risk_alerts (
    alert_id        INT             NOT NULL AUTO_INCREMENT,
    enrollment_id   INT             NOT NULL,
    risk_id         INT             NULL,
    risk_score      DECIMAL(5,2)    NOT NULL,
    risk_category   ENUM('MEDIUM','HIGH')   NOT NULL,
    triggering_factors VARCHAR(1000) NULL,
    status          ENUM('NEW','ACKNOWLEDGED','IN_PROGRESS','RESOLVED')
                                    NOT NULL DEFAULT 'NEW',
    assigned_to     INT             NULL,
    acknowledged_at DATETIME        NULL,
    resolved_at     DATETIME        NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    active_flag     TINYINT(1)      GENERATED ALWAYS AS
                        (CASE WHEN status = 'RESOLVED' THEN NULL ELSE 1 END)
                        STORED,
    PRIMARY KEY (alert_id),
    UNIQUE KEY uq_alert_one_active_per_enrollment
        (enrollment_id, active_flag),
    KEY ix_alerts_status (status),
    KEY ix_alerts_category (risk_category),
    KEY ix_alerts_created (created_at),
    KEY ix_alerts_assignee (assigned_to),
    CONSTRAINT fk_alert_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_alert_risk FOREIGN KEY (risk_id)
        REFERENCES risk_assessments (risk_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_alert_assignee FOREIGN KEY (assigned_to)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT ck_alert_score
        CHECK (risk_score >= 0 AND risk_score <= 100)
) ENGINE = InnoDB;

-- =====================================================================
-- 13. alert_status_history
--     Immutable trail of every alert status transition.
-- =====================================================================
CREATE TABLE alert_status_history (
    history_id      INT             NOT NULL AUTO_INCREMENT,
    alert_id        INT             NOT NULL,
    old_status      ENUM('NEW','ACKNOWLEDGED','IN_PROGRESS','RESOLVED') NULL,
    new_status      ENUM('NEW','ACKNOWLEDGED','IN_PROGRESS','RESOLVED')
                                    NOT NULL,
    changed_by      INT             NULL,
    note            VARCHAR(500)    NULL,
    changed_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (history_id),
    KEY ix_ash_alert (alert_id, changed_at),
    CONSTRAINT fk_ash_alert FOREIGN KEY (alert_id)
        REFERENCES risk_alerts (alert_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ash_user FOREIGN KEY (changed_by)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE = InnoDB;

-- =====================================================================
-- 14. interventions
-- =====================================================================
CREATE TABLE interventions (
    intervention_id INT             NOT NULL AUTO_INCREMENT,
    enrollment_id   INT             NOT NULL,
    alert_id        INT             NULL,
    intervention_type ENUM('COUNSELING','TUTORING_REFERRAL',
                           'ASSIGNMENT_SUPPORT','ATTENDANCE_FOLLOWUP',
                           'ACADEMIC_ADVISING','PARENT_CONTACT')
                                    NOT NULL,
    assigned_advisor_id INT         NULL,
    contact_date    DATE            NOT NULL,
    notes           TEXT            NULL,
    action_plan     TEXT            NULL,
    follow_up_date  DATE            NULL,
    outcome         ENUM('PENDING','IMPROVED','NO_CHANGE',
                         'DECLINED','ESCALATED')
                                    NOT NULL DEFAULT 'PENDING',
    resolution_status ENUM('OPEN','IN_PROGRESS','CLOSED')
                                    NOT NULL DEFAULT 'OPEN',
    created_by      INT             NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (intervention_id),
    KEY ix_intv_enrollment (enrollment_id),
    KEY ix_intv_alert (alert_id),
    KEY ix_intv_advisor (assigned_advisor_id),
    KEY ix_intv_type (intervention_type),
    KEY ix_intv_outcome (outcome),
    KEY ix_intv_contact_date (contact_date),
    CONSTRAINT fk_intv_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_intv_alert FOREIGN KEY (alert_id)
        REFERENCES risk_alerts (alert_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_intv_advisor FOREIGN KEY (assigned_advisor_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_intv_creator FOREIGN KEY (created_by)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT ck_intv_followup
        CHECK (follow_up_date IS NULL OR follow_up_date >= contact_date)
) ENGINE = InnoDB;

-- =====================================================================
-- 15. system_settings
--     Key/value configuration -- risk weights and thresholds live here
--     so the scoring model is tunable without a code change.
-- =====================================================================
CREATE TABLE system_settings (
    setting_key     VARCHAR(80)     NOT NULL,
    setting_value   VARCHAR(255)     NOT NULL,
    value_type      ENUM('INT','FLOAT','STRING','BOOL')
                                    NOT NULL DEFAULT 'STRING',
    description     VARCHAR(255)    NULL,
    updated_by      INT             NULL,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (setting_key),
    CONSTRAINT fk_settings_user FOREIGN KEY (updated_by)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE = InnoDB;

-- =====================================================================
-- 16. audit_logs
--     Written both by application code and by the AFTER-triggers in
--     triggers.sql. entity_id is VARCHAR so heterogeneous keys fit.
-- =====================================================================
CREATE TABLE audit_logs (
    audit_id        BIGINT          NOT NULL AUTO_INCREMENT,
    user_id         INT             NULL,
    action          VARCHAR(40)     NOT NULL,
    entity_type     VARCHAR(60)     NOT NULL,
    entity_id       VARCHAR(60)     NULL,
    old_values      TEXT            NULL,
    new_values      TEXT            NULL,
    ip_address      VARCHAR(45)     NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY ix_audit_entity (entity_type, entity_id),
    KEY ix_audit_created (created_at),
    KEY ix_audit_user (user_id),
    KEY ix_audit_action (action),
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE = InnoDB;

-- =====================================================================
-- Default configuration for the rule-based risk model.
-- =====================================================================
INSERT INTO system_settings
    (setting_key, setting_value, value_type, description)
VALUES
    ('risk.weight.attendance', '0.35', 'FLOAT',
     'Weight of the attendance component in the risk score'),
    ('risk.weight.academic',   '0.40', 'FLOAT',
     'Weight of the academic component in the risk score'),
    ('risk.weight.engagement', '0.25', 'FLOAT',
     'Weight of the engagement component in the risk score'),
    ('risk.threshold.medium',  '30',   'INT',
     'Lowest risk score classified as MEDIUM risk'),
    ('risk.threshold.high',    '60',   'INT',
     'Lowest risk score classified as HIGH risk'),
    ('risk.min_sessions',      '3',    'INT',
     'Attendance sessions required before the attendance component counts'),
    ('risk.min_graded',        '1',    'INT',
     'Graded assessments required before the academic component counts'),
    ('risk.activity_window_days', '30', 'INT',
     'Look-back window in days for LMS login frequency'),
    ('alert.min_score',        '30',   'INT',
     'Risk score at or above which an early-warning alert is raised'),
    ('engagement.target_logins_30d', '12', 'INT',
     'Login count in the window that earns a full engagement score'),
    ('risk.model_version',     'rule-v1', 'STRING',
     'Identifier of the active scoring model');

SELECT 'schema.sql applied successfully' AS status;
```

---

## Appendix B — Views, procedures and triggers

The twelve views, three stored functions, six stored procedures and twelve triggers (Chapters 5 and 6.2). `procedures.sql` holds the SQL implementation of the risk model that §5.6 compares with the Python one in Appendix E.

### `database/views.sql`

```sql
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
```

### `database/procedures.sql`

```sql
-- =====================================================================
-- SE-EWRS : procedures.sql
-- Purpose : Stored functions and procedures. The risk model lives here
--           as well as in app/services/risk_engine.py -- both follow the
--           identical rule set documented in docs/database_design.md so
--           a recalculation run from SQL and from the API agree.
--   mysql -u <user> -p se_ewrs < database/procedures.sql
-- =====================================================================

USE se_ewrs;

DROP PROCEDURE IF EXISTS sp_recalculate_risk_for_enrollment;
DROP PROCEDURE IF EXISTS sp_recalculate_all_risk;
DROP PROCEDURE IF EXISTS sp_enroll_student;
DROP PROCEDURE IF EXISTS sp_record_attendance;
DROP PROCEDURE IF EXISTS sp_upsert_assessment_result;
DROP PROCEDURE IF EXISTS sp_update_alert_status;
DROP FUNCTION  IF EXISTS fn_setting_num;
DROP FUNCTION  IF EXISTS fn_engagement_score;
DROP FUNCTION  IF EXISTS fn_risk_category;

DELIMITER $$

-- ---------------------------------------------------------------------
-- fn_setting_num(key, default)
--   Reads a numeric value out of system_settings, falling back to the
--   supplied default when the key is absent. Keeps the scoring model
--   configurable without scattering magic numbers through the code.
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_setting_num(p_key VARCHAR(80), p_default DECIMAL(10,4))
RETURNS DECIMAL(10,4)
READS SQL DATA
BEGIN
    DECLARE v_val DECIMAL(10,4);
    SELECT CAST(setting_value AS DECIMAL(10,4)) INTO v_val
      FROM system_settings WHERE setting_key = p_key LIMIT 1;
    RETURN COALESCE(v_val, p_default);
END$$

-- ---------------------------------------------------------------------
-- fn_engagement_score(...)  -> 0..100, higher is better
--
-- Documented rule set (identical in risk_engine.py):
--   engagement_score = clamp(100 - (recency + frequency + missing + late), 0, 100)
--
--   recency penalty, from days since the last LMS event
--       never active -> 50 | <=3 -> 0 | <=7 -> 10 | <=14 -> 20
--       <=30 -> 35 | >30 -> 50
--   frequency penalty, logins in the window vs the target (default 12)
--       logins >= target        -> 0
--       logins*3 >= target*2    -> 5
--       logins*3 >= target      -> 12
--       logins >= 1             -> 20
--       logins  = 0             -> 30
--   missing penalty = 40 * missing_submissions / expected_results
--   late    penalty = 20 * late_submissions    / expected_results
--       (both 0 when no assessment rows exist for the enrolment)
--
-- Integer cross-multiplication is used for the frequency bands so the
-- SQL and Python implementations cannot diverge on a float comparison.
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_engagement_score(
    p_days_since  INT,
    p_logins      INT,
    p_target      INT,
    p_missing     INT,
    p_late        INT,
    p_results     INT
)
RETURNS DECIMAL(5,2)
DETERMINISTIC
BEGIN
    DECLARE v_recency   DECIMAL(6,3) DEFAULT 0;
    DECLARE v_frequency DECIMAL(6,3) DEFAULT 0;
    DECLARE v_missing   DECIMAL(6,3) DEFAULT 0;
    DECLARE v_late      DECIMAL(6,3) DEFAULT 0;
    DECLARE v_score     DECIMAL(8,4);

    SET p_logins  = COALESCE(p_logins, 0);
    SET p_missing = COALESCE(p_missing, 0);
    SET p_late    = COALESCE(p_late, 0);
    SET p_results = COALESCE(p_results, 0);
    SET p_target  = GREATEST(COALESCE(p_target, 12), 1);

    -- recency
    IF p_days_since IS NULL      THEN SET v_recency = 50;
    ELSEIF p_days_since <= 3     THEN SET v_recency = 0;
    ELSEIF p_days_since <= 7     THEN SET v_recency = 10;
    ELSEIF p_days_since <= 14    THEN SET v_recency = 20;
    ELSEIF p_days_since <= 30    THEN SET v_recency = 35;
    ELSE                              SET v_recency = 50;
    END IF;

    -- login frequency
    IF p_logins >= p_target                 THEN SET v_frequency = 0;
    ELSEIF p_logins * 3 >= p_target * 2     THEN SET v_frequency = 5;
    ELSEIF p_logins * 3 >= p_target         THEN SET v_frequency = 12;
    ELSEIF p_logins >= 1                    THEN SET v_frequency = 20;
    ELSE                                         SET v_frequency = 30;
    END IF;

    -- submission behaviour
    IF p_results > 0 THEN
        SET v_missing = 40.0 * p_missing / p_results;
        SET v_late    = 20.0 * p_late    / p_results;
    END IF;

    SET v_score = 100 - (v_recency + v_frequency + v_missing + v_late);
    RETURN ROUND(LEAST(GREATEST(v_score, 0), 100), 2);
END$$

-- ---------------------------------------------------------------------
-- fn_risk_category(score, completeness, medium_threshold, high_threshold)
--   A profile with fewer than two observable components is never
--   labelled at-risk -- it is reported as INSUFFICIENT_DATA instead.
-- ---------------------------------------------------------------------
CREATE FUNCTION fn_risk_category(
    p_score        DECIMAL(5,2),
    p_completeness VARCHAR(20),
    p_medium       INT,
    p_high         INT
)
RETURNS VARCHAR(20)
DETERMINISTIC
BEGIN
    IF p_score IS NULL OR p_completeness = 'INSUFFICIENT' THEN
        RETURN 'INSUFFICIENT_DATA';
    ELSEIF p_score >= p_high   THEN RETURN 'HIGH';
    ELSEIF p_score >= p_medium THEN RETURN 'MEDIUM';
    ELSE RETURN 'LOW';
    END IF;
END$$

-- ---------------------------------------------------------------------
-- sp_recalculate_risk_for_enrollment(enrollment_id, actor_user_id)
--
--   1. Pulls the observed inputs straight from the base tables, using
--      the per-enrolment indexes (see the note on the SELECTs below).
--   2. Derives the three 0-100 risk components, skipping any component
--      with no supporting data.
--   3. Re-normalises the weights across the available components so a
--      missing input never behaves like a zero score.
--   4. Appends a row to risk_assessments (full history is kept).
--   5. Raises OR updates exactly one open alert, inside a transaction.
--
--   Everything after step 3 runs in a single transaction so that a risk
--   row and its alert can never be written apart from each other.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_recalculate_risk_for_enrollment(
    IN p_enrollment_id INT,
    IN p_actor_user_id INT
)
MODIFIES SQL DATA
BEGIN
    DECLARE v_exists            INT DEFAULT 0;
    DECLARE v_att_pct           DECIMAL(5,2);
    DECLARE v_aca_pct           DECIMAL(5,2);
    DECLARE v_eng_score         DECIMAL(5,2);
    DECLARE v_att_risk          DECIMAL(5,2) DEFAULT NULL;
    DECLARE v_aca_risk          DECIMAL(5,2) DEFAULT NULL;
    DECLARE v_eng_risk          DECIMAL(5,2) DEFAULT NULL;

    DECLARE v_sessions_held     INT DEFAULT 0;
    DECLARE v_sessions_attended INT DEFAULT 0;
    DECLARE v_graded            INT DEFAULT 0;
    DECLARE v_results           INT DEFAULT 0;
    DECLARE v_late              INT DEFAULT 0;
    DECLARE v_missing           INT DEFAULT 0;
    DECLARE v_logins30          INT DEFAULT 0;
    DECLARE v_activities        INT DEFAULT 0;
    DECLARE v_days_since        INT DEFAULT NULL;
    DECLARE v_last_assess       DATE DEFAULT NULL;

    DECLARE v_w_att  DECIMAL(10,4);
    DECLARE v_w_aca  DECIMAL(10,4);
    DECLARE v_w_eng  DECIMAL(10,4);
    DECLARE v_med    INT;
    DECLARE v_high   INT;
    DECLARE v_min_sessions INT;
    DECLARE v_min_graded   INT;
    DECLARE v_target_logins INT;
    DECLARE v_window_days   INT;
    DECLARE v_alert_min     INT;
    DECLARE v_model  VARCHAR(20);

    DECLARE v_avail_weight  DECIMAL(10,4) DEFAULT 0;
    DECLARE v_weighted_sum  DECIMAL(14,6) DEFAULT 0;
    DECLARE v_components    INT DEFAULT 0;
    DECLARE v_score         DECIMAL(5,2) DEFAULT NULL;
    DECLARE v_completeness  VARCHAR(20);
    DECLARE v_category      VARCHAR(20);
    DECLARE v_reasons       VARCHAR(500) DEFAULT NULL;
    DECLARE v_factors       VARCHAR(1000) DEFAULT NULL;
    DECLARE v_risk_id       INT;
    DECLARE v_alert_id      INT DEFAULT NULL;
    DECLARE v_alert_status  VARCHAR(20) DEFAULT NULL;

    SELECT COUNT(*) INTO v_exists
      FROM enrollments WHERE enrollment_id = p_enrollment_id;
    IF v_exists = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_recalculate_risk_for_enrollment: unknown enrollment_id';
    END IF;

    -- configuration -------------------------------------------------
    SET v_w_att          = fn_setting_num('risk.weight.attendance', 0.35);
    SET v_w_aca          = fn_setting_num('risk.weight.academic',   0.40);
    SET v_w_eng          = fn_setting_num('risk.weight.engagement', 0.25);
    SET v_med            = CAST(fn_setting_num('risk.threshold.medium', 30) AS SIGNED);
    SET v_high           = CAST(fn_setting_num('risk.threshold.high',   60) AS SIGNED);
    SET v_min_sessions   = CAST(fn_setting_num('risk.min_sessions', 3) AS SIGNED);
    SET v_min_graded     = CAST(fn_setting_num('risk.min_graded',   1) AS SIGNED);
    SET v_target_logins  = CAST(fn_setting_num('engagement.target_logins_30d', 12) AS SIGNED);
    SET v_window_days    = CAST(fn_setting_num('risk.activity_window_days', 30) AS SIGNED);
    SET v_alert_min      = CAST(fn_setting_num('alert.min_score',  30) AS SIGNED);
    SET v_model = COALESCE((SELECT setting_value FROM system_settings
                            WHERE setting_key = 'risk.model_version'), 'rule-v1');

    -- observed inputs ------------------------------------------------
    -- These read the BASE TABLES with an enrollment_id predicate rather
    -- than selecting a single row out of student_performance_view.
    --
    -- The view is the right thing for reporting, but it is the wrong
    -- thing here: MySQL materialises each of its three aggregate
    -- sub-views in full before filtering, so a per-enrolment lookup
    -- aggregates the entire dataset every time. Measured on 6,000
    -- enrolments over ~450,000 fact rows that cost 4.4 seconds PER CALL
    -- (about 7 hours for a full run). Reading the base tables directly
    -- uses ix_attendance_enrollment, ix_results_enrollment and
    -- ix_lms_enrollment_time, and the same run takes seconds.
    --
    -- The arithmetic is deliberately identical to v_enrollment_attendance,
    -- v_enrollment_academics and v_enrollment_activity; only the access
    -- path differs.

    -- attendance: LATE counts as attended, EXCUSED leaves the denominator
    SELECT COALESCE(SUM(status <> 'EXCUSED'), 0),
           COALESCE(SUM(status IN ('PRESENT','LATE')), 0)
      INTO v_sessions_held, v_sessions_attended
      FROM attendance_records
     WHERE enrollment_id = p_enrollment_id;

    SET v_att_pct = CASE WHEN v_sessions_held = 0 THEN NULL
                         ELSE ROUND(100.0 * v_sessions_attended / v_sessions_held, 2) END;

    -- academics: only graded rows feed the average
    SELECT COUNT(*),
           COALESCE(SUM(marks_obtained IS NOT NULL), 0),
           ROUND(AVG(CASE WHEN marks_obtained IS NOT NULL THEN percentage END), 2),
           COALESCE(SUM(submission_status = 'LATE'), 0),
           COALESCE(SUM(submission_status = 'MISSING'), 0),
           MAX(CASE WHEN marks_obtained IS NOT NULL
                    THEN DATE(COALESCE(graded_at, submitted_at, created_at)) END)
      INTO v_results, v_graded, v_aca_pct, v_late, v_missing, v_last_assess
      FROM assessment_results
     WHERE enrollment_id = p_enrollment_id;

    -- LMS activity: logins inside the configured window, plus last-seen
    SELECT COUNT(*),
           COALESCE(SUM(activity_type = 'LOGIN'
                        AND activity_at >= (CURRENT_DATE - INTERVAL v_window_days DAY)), 0),
           CASE WHEN MAX(activity_at) IS NULL THEN NULL
                ELSE DATEDIFF(CURRENT_DATE, DATE(MAX(activity_at))) END
      INTO v_activities, v_logins30, v_days_since
      FROM lms_activity_logs
     WHERE enrollment_id = p_enrollment_id;

    -- component 1: attendance ---------------------------------------
    IF v_sessions_held >= v_min_sessions AND v_att_pct IS NOT NULL THEN
        SET v_att_risk = ROUND(100 - v_att_pct, 2);
        SET v_avail_weight = v_avail_weight + v_w_att;
        SET v_weighted_sum = v_weighted_sum + v_w_att * v_att_risk;
        SET v_components = v_components + 1;
    ELSE
        SET v_reasons = CONCAT_WS('; ', v_reasons,
            CONCAT('Attendance component skipped: only ', v_sessions_held,
                   ' of ', v_min_sessions, ' required sessions recorded'));
    END IF;

    -- component 2: academic -----------------------------------------
    IF v_graded >= v_min_graded AND v_aca_pct IS NOT NULL THEN
        SET v_aca_risk = ROUND(100 - v_aca_pct, 2);
        SET v_avail_weight = v_avail_weight + v_w_aca;
        SET v_weighted_sum = v_weighted_sum + v_w_aca * v_aca_risk;
        SET v_components = v_components + 1;
    ELSE
        SET v_reasons = CONCAT_WS('; ', v_reasons,
            CONCAT('Academic component skipped: ', v_graded,
                   ' graded assessment(s) on record'));
    END IF;

    -- component 3: engagement ---------------------------------------
    IF v_activities > 0 OR v_results > 0 THEN
        SET v_eng_score = fn_engagement_score(v_days_since, v_logins30,
                              v_target_logins, v_missing, v_late, v_results);
        SET v_eng_risk = ROUND(100 - v_eng_score, 2);
        SET v_avail_weight = v_avail_weight + v_w_eng;
        SET v_weighted_sum = v_weighted_sum + v_w_eng * v_eng_risk;
        SET v_components = v_components + 1;
    ELSE
        SET v_reasons = CONCAT_WS('; ', v_reasons,
            'Engagement component skipped: no LMS activity or assessment records');
    END IF;

    -- weighted, re-normalised score ---------------------------------
    IF v_avail_weight > 0 THEN
        SET v_score = ROUND(LEAST(GREATEST(v_weighted_sum / v_avail_weight, 0), 100), 2);
    END IF;

    SET v_completeness = CASE
        WHEN v_components >= 3 THEN 'COMPLETE'
        WHEN v_components = 2  THEN 'PARTIAL'
        ELSE 'INSUFFICIENT' END;

    SET v_category = fn_risk_category(v_score, v_completeness, v_med, v_high);

    IF v_completeness <> 'COMPLETE' AND v_reasons IS NULL THEN
        SET v_reasons = 'One or more risk components had no supporting data';
    END IF;

    -- human-readable contributing factors ---------------------------
    IF v_att_risk IS NOT NULL AND v_att_pct < 75 THEN
        SET v_factors = CONCAT_WS('; ', v_factors,
            CONCAT('Low attendance (', CAST(ROUND(v_att_pct) AS SIGNED), '%)'));
    END IF;
    IF v_aca_risk IS NOT NULL AND v_aca_pct < 50 THEN
        SET v_factors = CONCAT_WS('; ', v_factors,
            CONCAT('Weak assessment average (', CAST(ROUND(v_aca_pct) AS SIGNED), '%)'));
    END IF;
    IF v_missing > 0 THEN
        SET v_factors = CONCAT_WS('; ', v_factors,
            CONCAT(v_missing, ' missing submission(s)'));
    END IF;
    IF v_late > 0 THEN
        SET v_factors = CONCAT_WS('; ', v_factors,
            CONCAT(v_late, ' late submission(s)'));
    END IF;
    IF v_days_since IS NULL AND v_activities = 0 THEN
        SET v_factors = CONCAT_WS('; ', v_factors, 'No LMS activity on record');
    ELSEIF v_days_since > 14 THEN
        SET v_factors = CONCAT_WS('; ', v_factors,
            CONCAT('No LMS activity for ', v_days_since, ' days'));
    END IF;
    IF v_activities > 0 AND v_logins30 * 3 < v_target_logins THEN
        SET v_factors = CONCAT_WS('; ', v_factors,
            CONCAT('Low login frequency (', v_logins30, ' in 30 days)'));
    END IF;
    IF v_factors IS NULL THEN
        SET v_factors = 'No adverse factors detected';
    END IF;

    -- persist, transactionally --------------------------------------
    START TRANSACTION;

    INSERT INTO risk_assessments (
        enrollment_id, calculated_at,
        attendance_percentage, avg_assessment_percentage, engagement_score,
        attendance_risk, academic_risk, engagement_risk,
        risk_score, risk_category, data_completeness,
        missing_data_reasons, contributing_factors,
        sessions_held, sessions_attended, late_submissions,
        missing_submissions, graded_assessments, login_count_30d,
        days_since_last_activity, last_assessment_date, model_version
    ) VALUES (
        p_enrollment_id, NOW(),
        v_att_pct, v_aca_pct, v_eng_score,
        v_att_risk, v_aca_risk, v_eng_risk,
        v_score, v_category, v_completeness,
        v_reasons, v_factors,
        v_sessions_held, v_sessions_attended, v_late,
        v_missing, v_graded, v_logins30,
        v_days_since, v_last_assess, v_model
    );
    SET v_risk_id = LAST_INSERT_ID();

    SELECT alert_id, status INTO v_alert_id, v_alert_status
      FROM risk_alerts
     WHERE enrollment_id = p_enrollment_id AND active_flag = 1
     LIMIT 1;

    IF v_category IN ('MEDIUM','HIGH') AND v_score >= v_alert_min THEN
        IF v_alert_id IS NULL THEN
            -- no open alert: raise one
            INSERT INTO risk_alerts (enrollment_id, risk_id, risk_score,
                                     risk_category, triggering_factors, status)
            VALUES (p_enrollment_id, v_risk_id, v_score,
                    v_category, v_factors, 'NEW');
            INSERT INTO alert_status_history (alert_id, old_status, new_status,
                                              changed_by, note)
            VALUES (LAST_INSERT_ID(), NULL, 'NEW', p_actor_user_id,
                    'Alert raised by risk recalculation');
        ELSE
            -- refresh the existing open alert instead of duplicating it
            UPDATE risk_alerts
               SET risk_id = v_risk_id,
                   risk_score = v_score,
                   risk_category = v_category,
                   triggering_factors = v_factors
             WHERE alert_id = v_alert_id;
        END IF;
    ELSEIF v_alert_id IS NOT NULL AND v_alert_status = 'NEW' THEN
        -- Risk dropped below the alert threshold and nobody has picked
        -- the alert up yet, so close it automatically. Alerts that a
        -- human already acknowledged are left for that human to close.
        UPDATE risk_alerts
           SET status = 'RESOLVED', resolved_at = NOW(), risk_id = v_risk_id
         WHERE alert_id = v_alert_id;
        INSERT INTO alert_status_history (alert_id, old_status, new_status,
                                          changed_by, note)
        VALUES (v_alert_id, 'NEW', 'RESOLVED', p_actor_user_id,
                CONCAT('Auto-resolved: risk score fell to ',
                       COALESCE(CAST(v_score AS CHAR), 'n/a')));
    END IF;

    COMMIT;

    SELECT v_risk_id AS risk_id, v_score AS risk_score,
           v_category AS risk_category, v_completeness AS data_completeness;
END$$

-- ---------------------------------------------------------------------
-- sp_recalculate_all_risk(course_pk, actor_user_id)
--   Cursor loop over every ACTIVE enrolment, optionally narrowed to one
--   course (pass NULL for all). Returns the number of rows produced.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_recalculate_all_risk(
    IN p_course_pk     INT,
    IN p_actor_user_id INT
)
MODIFIES SQL DATA
BEGIN
    DECLARE v_done INT DEFAULT 0;
    DECLARE v_eid  INT;
    DECLARE v_count INT DEFAULT 0;
    DECLARE cur CURSOR FOR
        SELECT enrollment_id FROM enrollments
         WHERE status = 'ACTIVE'
           AND (p_course_pk IS NULL OR course_pk = p_course_pk)
         ORDER BY enrollment_id;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = 1;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO v_eid;
        IF v_done = 1 THEN LEAVE read_loop; END IF;
        CALL sp_recalculate_risk_for_enrollment(v_eid, p_actor_user_id);
        SET v_count = v_count + 1;
    END LOOP;
    CLOSE cur;

    INSERT INTO audit_logs (user_id, action, entity_type, entity_id, new_values)
    VALUES (p_actor_user_id, 'RECALCULATE', 'risk_assessments',
            COALESCE(CAST(p_course_pk AS CHAR), 'ALL'),
            CONCAT('{"enrollments_processed":', v_count, '}'));

    SELECT v_count AS enrollments_processed;
END$$

-- ---------------------------------------------------------------------
-- sp_enroll_student(student_pk, course_pk, actor)
--   Transactional enrolment with an explicit duplicate check on top of
--   the uq_enrollment_student_course unique key, so the caller gets a
--   readable error rather than a raw constraint violation.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_enroll_student(
    IN p_student_pk    INT,
    IN p_course_pk     INT,
    IN p_actor_user_id INT
)
MODIFIES SQL DATA
BEGIN
    DECLARE v_n INT DEFAULT 0;
    DECLARE v_enrollment_id INT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT COUNT(*) INTO v_n FROM students
     WHERE student_pk = p_student_pk AND is_active = 1;
    IF v_n = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_enroll_student: student not found or inactive';
    END IF;

    SELECT COUNT(*) INTO v_n FROM courses
     WHERE course_pk = p_course_pk AND is_active = 1;
    IF v_n = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_enroll_student: course not found or inactive';
    END IF;

    SELECT COUNT(*) INTO v_n FROM enrollments
     WHERE student_pk = p_student_pk AND course_pk = p_course_pk;
    IF v_n > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_enroll_student: student is already enrolled in this course';
    END IF;

    INSERT INTO enrollments (student_pk, course_pk, enrolled_on, status)
    VALUES (p_student_pk, p_course_pk, CURRENT_DATE, 'ACTIVE');
    SET v_enrollment_id = LAST_INSERT_ID();

    COMMIT;
    SELECT v_enrollment_id AS enrollment_id;
END$$

-- ---------------------------------------------------------------------
-- sp_record_attendance(enrollment_id, session_date, session_no, status,
--                      recorded_by, remarks)
--   Idempotent upsert: re-recording the same session corrects the old
--   row instead of failing on uq_attendance_session.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_record_attendance(
    IN p_enrollment_id INT,
    IN p_session_date  DATE,
    IN p_session_no    SMALLINT,
    IN p_status        VARCHAR(10),
    IN p_recorded_by   INT,
    IN p_remarks       VARCHAR(255)
)
MODIFIES SQL DATA
BEGIN
    IF p_status NOT IN ('PRESENT','ABSENT','LATE','EXCUSED') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_record_attendance: invalid status';
    END IF;

    INSERT INTO attendance_records
        (enrollment_id, session_date, session_no, status, recorded_by, remarks)
    VALUES
        (p_enrollment_id, p_session_date, COALESCE(p_session_no, 1),
         p_status, p_recorded_by, p_remarks)
    ON DUPLICATE KEY UPDATE
        status      = VALUES(status),
        recorded_by = VALUES(recorded_by),
        remarks     = VALUES(remarks);

    SELECT attendance_id FROM attendance_records
     WHERE enrollment_id = p_enrollment_id
       AND session_date  = p_session_date
       AND session_no    = COALESCE(p_session_no, 1);
END$$

-- ---------------------------------------------------------------------
-- sp_upsert_assessment_result(...)
--   Validates marks against the parent assessment's max_marks, derives
--   the submission status from submitted_at vs due_at, and upserts.
--   `percentage` is left to the trg_ar_* triggers.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_upsert_assessment_result(
    IN p_assessment_id INT,
    IN p_enrollment_id INT,
    IN p_marks         DECIMAL(6,2),
    IN p_submitted_at  DATETIME,
    IN p_graded_by     INT
)
MODIFIES SQL DATA
BEGIN
    DECLARE v_max  DECIMAL(6,2);
    DECLARE v_due  DATETIME;
    DECLARE v_status VARCHAR(10);

    SELECT max_marks, due_at INTO v_max, v_due
      FROM assessments WHERE assessment_id = p_assessment_id;

    IF v_max IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_upsert_assessment_result: unknown assessment_id';
    END IF;
    IF p_marks IS NOT NULL AND (p_marks < 0 OR p_marks > v_max) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_upsert_assessment_result: marks outside 0..max_marks';
    END IF;

    SET v_status = CASE
        WHEN p_submitted_at IS NULL           THEN 'MISSING'
        WHEN p_submitted_at <= v_due          THEN 'ON_TIME'
        ELSE 'LATE' END;

    INSERT INTO assessment_results
        (assessment_id, enrollment_id, marks_obtained, submitted_at,
         submission_status, graded_by, graded_at)
    VALUES
        (p_assessment_id, p_enrollment_id, p_marks, p_submitted_at,
         v_status, p_graded_by,
         CASE WHEN p_marks IS NULL THEN NULL ELSE NOW() END)
    ON DUPLICATE KEY UPDATE
        marks_obtained    = VALUES(marks_obtained),
        submitted_at      = VALUES(submitted_at),
        submission_status = VALUES(submission_status),
        graded_by         = VALUES(graded_by),
        graded_at         = VALUES(graded_at);

    SELECT result_id, percentage, submission_status
      FROM assessment_results
     WHERE assessment_id = p_assessment_id AND enrollment_id = p_enrollment_id;
END$$

-- ---------------------------------------------------------------------
-- sp_update_alert_status(alert_id, new_status, user_id, note)
--   Enforces the legal status transitions and writes the history row in
--   the same transaction, so an alert's status and its audit trail stay
--   consistent.
--   Legal graph: NEW -> ACKNOWLEDGED|IN_PROGRESS|RESOLVED
--                ACKNOWLEDGED -> IN_PROGRESS|RESOLVED
--                IN_PROGRESS  -> RESOLVED
--                RESOLVED     -> (terminal)
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_update_alert_status(
    IN p_alert_id   INT,
    IN p_new_status VARCHAR(20),
    IN p_user_id    INT,
    IN p_note       VARCHAR(500)
)
MODIFIES SQL DATA
BEGIN
    DECLARE v_old VARCHAR(20);
    DECLARE v_ok  INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT status INTO v_old FROM risk_alerts
     WHERE alert_id = p_alert_id FOR UPDATE;

    IF v_old IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_update_alert_status: unknown alert_id';
    END IF;

    SET v_ok = CASE
        WHEN v_old = 'NEW'
             AND p_new_status IN ('ACKNOWLEDGED','IN_PROGRESS','RESOLVED') THEN 1
        WHEN v_old = 'ACKNOWLEDGED'
             AND p_new_status IN ('IN_PROGRESS','RESOLVED') THEN 1
        WHEN v_old = 'IN_PROGRESS'
             AND p_new_status = 'RESOLVED' THEN 1
        ELSE 0 END;

    IF v_ok = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_update_alert_status: illegal status transition';
    END IF;

    UPDATE risk_alerts
       SET status = p_new_status,
           acknowledged_at = CASE
               WHEN p_new_status = 'ACKNOWLEDGED' AND acknowledged_at IS NULL
               THEN NOW() ELSE acknowledged_at END,
           resolved_at = CASE
               WHEN p_new_status = 'RESOLVED' THEN NOW() ELSE resolved_at END
     WHERE alert_id = p_alert_id;

    INSERT INTO alert_status_history
        (alert_id, old_status, new_status, changed_by, note)
    VALUES (p_alert_id, v_old, p_new_status, p_user_id, p_note);

    COMMIT;
    SELECT p_alert_id AS alert_id, v_old AS old_status,
           p_new_status AS new_status;
END$$

DELIMITER ;

SELECT 'procedures.sql applied successfully' AS status;
```

### `database/triggers.sql`

```sql
-- =====================================================================
-- SE-EWRS : triggers.sql
-- Purpose : Database-side validation and audit logging.
--   mysql -u <user> -p se_ewrs < database/triggers.sql
-- ---------------------------------------------------------------------
-- Design rules followed here:
--   * No trigger writes to the table it is attached to, and no trigger
--     calls a procedure that writes back to that table, so there is no
--     recursion and MySQL's single-trigger-per-event model is respected.
--   * Alert generation is NOT done in a trigger. It lives only in
--     sp_recalculate_risk_for_enrollment / the Python risk engine, which
--     is what keeps duplicate alerts impossible.
--   * Audit triggers never copy password_hash into audit_logs.
-- =====================================================================

USE se_ewrs;

DROP TRIGGER IF EXISTS trg_ar_before_insert;
DROP TRIGGER IF EXISTS trg_ar_before_update;
DROP TRIGGER IF EXISTS trg_assess_before_insert;
DROP TRIGGER IF EXISTS trg_assess_before_update;
DROP TRIGGER IF EXISTS trg_intervention_before_insert;
DROP TRIGGER IF EXISTS trg_students_after_insert;
DROP TRIGGER IF EXISTS trg_students_after_update;
DROP TRIGGER IF EXISTS trg_courses_after_update;
DROP TRIGGER IF EXISTS trg_users_after_update;
DROP TRIGGER IF EXISTS trg_enrollments_after_insert;
DROP TRIGGER IF EXISTS trg_alerts_after_update;
DROP TRIGGER IF EXISTS trg_settings_after_update;

DELIMITER $$

-- ---------------------------------------------------------------------
-- trg_ar_before_insert / trg_ar_before_update   (table: assessment_results)
-- Purpose : the database -- not the client -- owns the `percentage`
--           column and the marks range check. Whether a row arrives via
--           the API, the seed script or a manual INSERT, percentage is
--           always ROUND(marks / max_marks * 100, 2) and marks can never
--           be negative or exceed the assessment's maximum.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_ar_before_insert
BEFORE INSERT ON assessment_results
FOR EACH ROW
BEGIN
    DECLARE v_max DECIMAL(6,2);
    SELECT max_marks INTO v_max FROM assessments
     WHERE assessment_id = NEW.assessment_id;

    IF v_max IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessment_results: parent assessment does not exist';
    END IF;
    IF NEW.marks_obtained IS NOT NULL AND NEW.marks_obtained < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessment_results: marks_obtained cannot be negative';
    END IF;
    IF NEW.marks_obtained IS NOT NULL AND NEW.marks_obtained > v_max THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessment_results: marks_obtained exceeds max_marks';
    END IF;

    SET NEW.percentage = CASE
        WHEN NEW.marks_obtained IS NULL THEN NULL
        ELSE ROUND(100.0 * NEW.marks_obtained / v_max, 2) END;
END$$

CREATE TRIGGER trg_ar_before_update
BEFORE UPDATE ON assessment_results
FOR EACH ROW
BEGIN
    DECLARE v_max DECIMAL(6,2);
    SELECT max_marks INTO v_max FROM assessments
     WHERE assessment_id = NEW.assessment_id;

    IF v_max IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessment_results: parent assessment does not exist';
    END IF;
    IF NEW.marks_obtained IS NOT NULL AND NEW.marks_obtained < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessment_results: marks_obtained cannot be negative';
    END IF;
    IF NEW.marks_obtained IS NOT NULL AND NEW.marks_obtained > v_max THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessment_results: marks_obtained exceeds max_marks';
    END IF;

    SET NEW.percentage = CASE
        WHEN NEW.marks_obtained IS NULL THEN NULL
        ELSE ROUND(100.0 * NEW.marks_obtained / v_max, 2) END;
END$$

-- ---------------------------------------------------------------------
-- trg_assess_before_insert / trg_assess_before_update  (assessments)
-- Purpose : guard the grading scale itself. A zero or negative maximum
--           would make every percentage undefined, and a due date set
--           before the course even exists is almost always a typo.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_assess_before_insert
BEFORE INSERT ON assessments
FOR EACH ROW
BEGIN
    IF NEW.max_marks <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessments: max_marks must be greater than zero';
    END IF;
    IF NEW.weight_percent < 0 OR NEW.weight_percent > 100 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessments: weight_percent must be between 0 and 100';
    END IF;
END$$

CREATE TRIGGER trg_assess_before_update
BEFORE UPDATE ON assessments
FOR EACH ROW
BEGIN
    IF NEW.max_marks <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'assessments: max_marks must be greater than zero';
    END IF;
END$$

-- ---------------------------------------------------------------------
-- trg_intervention_before_insert  (table: interventions)
-- Purpose : cross-row referential validation that a plain foreign key
--           cannot express -- if an intervention cites a risk alert,
--           that alert must belong to the SAME enrolment. Without this
--           it is possible to attach Student A's intervention to
--           Student B's alert while both FKs still validate.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_intervention_before_insert
BEFORE INSERT ON interventions
FOR EACH ROW
BEGIN
    DECLARE v_alert_enrollment INT;
    IF NEW.alert_id IS NOT NULL THEN
        SELECT enrollment_id INTO v_alert_enrollment
          FROM risk_alerts WHERE alert_id = NEW.alert_id;
        IF v_alert_enrollment IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'interventions: alert_id does not exist';
        END IF;
        IF v_alert_enrollment <> NEW.enrollment_id THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'interventions: alert_id belongs to a different enrollment';
        END IF;
    END IF;
END$$

-- =====================================================================
-- AUDIT TRIGGERS
-- Every trigger below appends to audit_logs only. audit_logs itself has
-- no triggers, which is what prevents recursion.
-- =====================================================================

-- trg_students_after_insert : records student creation.
CREATE TRIGGER trg_students_after_insert
AFTER INSERT ON students
FOR EACH ROW
BEGIN
    INSERT INTO audit_logs (action, entity_type, entity_id, new_values)
    VALUES ('INSERT', 'students', NEW.student_pk,
            JSON_OBJECT('student_id', NEW.student_id,
                        'full_name',  NEW.full_name,
                        'email',      NEW.email,
                        'dept_id',    NEW.dept_id,
                        'semester',   NEW.semester,
                        'is_active',  NEW.is_active));
END$$

-- trg_students_after_update : records edits and de-activations. The IF
-- keeps no-op UPDATE statements out of the audit trail.
CREATE TRIGGER trg_students_after_update
AFTER UPDATE ON students
FOR EACH ROW
BEGIN
    IF NOT (OLD.full_name <=> NEW.full_name)
       OR NOT (OLD.email     <=> NEW.email)
       OR NOT (OLD.dept_id   <=> NEW.dept_id)
       OR NOT (OLD.semester  <=> NEW.semester)
       OR NOT (OLD.is_active <=> NEW.is_active) THEN
        INSERT INTO audit_logs (action, entity_type, entity_id,
                                old_values, new_values)
        VALUES ('UPDATE', 'students', NEW.student_pk,
                JSON_OBJECT('full_name', OLD.full_name, 'email', OLD.email,
                            'dept_id', OLD.dept_id, 'semester', OLD.semester,
                            'is_active', OLD.is_active),
                JSON_OBJECT('full_name', NEW.full_name, 'email', NEW.email,
                            'dept_id', NEW.dept_id, 'semester', NEW.semester,
                            'is_active', NEW.is_active));
    END IF;
END$$

-- trg_courses_after_update : course catalogue changes.
CREATE TRIGGER trg_courses_after_update
AFTER UPDATE ON courses
FOR EACH ROW
BEGIN
    IF NOT (OLD.course_name   <=> NEW.course_name)
       OR NOT (OLD.semester   <=> NEW.semester)
       OR NOT (OLD.credits    <=> NEW.credits)
       OR NOT (OLD.is_active  <=> NEW.is_active) THEN
        INSERT INTO audit_logs (action, entity_type, entity_id,
                                old_values, new_values)
        VALUES ('UPDATE', 'courses', NEW.course_pk,
                JSON_OBJECT('course_name', OLD.course_name,
                            'semester', OLD.semester, 'credits', OLD.credits,
                            'is_active', OLD.is_active),
                JSON_OBJECT('course_name', NEW.course_name,
                            'semester', NEW.semester, 'credits', NEW.credits,
                            'is_active', NEW.is_active));
    END IF;
END$$

-- trg_users_after_update : privilege and account-state changes only.
-- password_hash is deliberately never written to the audit trail.
CREATE TRIGGER trg_users_after_update
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    IF NOT (OLD.role <=> NEW.role)
       OR NOT (OLD.is_active <=> NEW.is_active)
       OR NOT (OLD.dept_id   <=> NEW.dept_id) THEN
        INSERT INTO audit_logs (action, entity_type, entity_id,
                                old_values, new_values)
        VALUES ('UPDATE', 'users', NEW.user_id,
                JSON_OBJECT('role', OLD.role, 'is_active', OLD.is_active,
                            'dept_id', OLD.dept_id),
                JSON_OBJECT('role', NEW.role, 'is_active', NEW.is_active,
                            'dept_id', NEW.dept_id));
    END IF;
END$$

-- trg_enrollments_after_insert : who was added to which course, when.
CREATE TRIGGER trg_enrollments_after_insert
AFTER INSERT ON enrollments
FOR EACH ROW
BEGIN
    INSERT INTO audit_logs (action, entity_type, entity_id, new_values)
    VALUES ('INSERT', 'enrollments', NEW.enrollment_id,
            JSON_OBJECT('student_pk', NEW.student_pk,
                        'course_pk',  NEW.course_pk,
                        'status',     NEW.status));
END$$

-- trg_alerts_after_update : the compliance-relevant trail of who moved
-- an early-warning alert from one state to another.
CREATE TRIGGER trg_alerts_after_update
AFTER UPDATE ON risk_alerts
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status)
       OR NOT (OLD.assigned_to <=> NEW.assigned_to) THEN
        INSERT INTO audit_logs (action, entity_type, entity_id,
                                old_values, new_values)
        VALUES ('UPDATE', 'risk_alerts', NEW.alert_id,
                JSON_OBJECT('status', OLD.status,
                            'assigned_to', OLD.assigned_to),
                JSON_OBJECT('status', NEW.status,
                            'assigned_to', NEW.assigned_to,
                            'risk_score', NEW.risk_score));
    END IF;
END$$

-- trg_settings_after_update : changing a risk weight changes every score
-- the system produces, so it is audited.
CREATE TRIGGER trg_settings_after_update
AFTER UPDATE ON system_settings
FOR EACH ROW
BEGIN
    IF NOT (OLD.setting_value <=> NEW.setting_value) THEN
        INSERT INTO audit_logs (user_id, action, entity_type, entity_id,
                                old_values, new_values)
        VALUES (NEW.updated_by, 'UPDATE', 'system_settings', NEW.setting_key,
                JSON_OBJECT('setting_value', OLD.setting_value),
                JSON_OBJECT('setting_value', NEW.setting_value));
    END IF;
END$$

DELIMITER ;

SELECT 'triggers.sql applied successfully' AS status;
```

---

## Appendix C — Analytical queries with output

The fifteen queries of `database/analytics_queries.sql` (§6.3), each followed by the output it produced against the MySQL 8 demonstration database. The seed writes dates as offsets from `CURDATE()`, so a fresh load reproduces these figures. Result sets longer than 20 rows are cut, with the number of rows left out stated beneath.

### C.1 Dashboard headline counters

*Concepts:* scalar subqueries, conditional aggregation over a view.

```sql
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
```

Output:

```text
+----------------+---------------+-------------------+-----------+-------------+----------+-------------------+----------------+----------------+
| total_students | total_courses | total_enrollments | high_risk | medium_risk | low_risk | insufficient_data | avg_attendance | avg_assessment |
+----------------+---------------+-------------------+-----------+-------------+----------+-------------------+----------------+----------------+
|             36 |             6 |                80 |         9 |          26 |       41 |                 4 |          82.29 |          59.09 |
+----------------+---------------+-------------------+-----------+-------------+----------+-------------------+----------------+----------------+
```

### C.2 Enrolments grouped by risk category, worst first

*Concepts:* join across 4 tables via a view, ORDER BY on a derived col. An INSUFFICIENT_DATA row stores a partial score, not an assessment, so its statistics are NULL here and it is left out of every mean below.

```sql
SELECT risk_category,
       COUNT(*)                        AS enrollments,
       ROUND(AVG(CASE WHEN risk_category IN ('LOW', 'MEDIUM', 'HIGH') THEN risk_score END), 2) AS avg_score,
       ROUND(MIN(CASE WHEN risk_category IN ('LOW', 'MEDIUM', 'HIGH') THEN risk_score END), 2) AS min_score,
       ROUND(MAX(CASE WHEN risk_category IN ('LOW', 'MEDIUM', 'HIGH') THEN risk_score END), 2) AS max_score
FROM student_risk_summary
GROUP BY risk_category
ORDER BY FIELD(risk_category, 'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_DATA');
```

Output:

```text
+-------------------+-------------+-----------+-----------+-----------+
| risk_category     | enrollments | avg_score | min_score | max_score |
+-------------------+-------------+-----------+-----------+-----------+
| HIGH              |           9 |     69.91 |     62.52 |     77.80 |
| MEDIUM            |          26 |     41.42 |     31.72 |     59.62 |
| LOW               |          41 |     11.44 |      2.72 |     24.06 |
| INSUFFICIENT_DATA |           4 |      NULL |      NULL |      NULL |
+-------------------+-------------+-----------+-----------+-----------+
```

### C.3 Course-wise attendance, only courses averaging under 80%

*Concepts:* GROUP BY + HAVING on an aggregate.

```sql
SELECT course_code, course_name, enrolled_students,
       total_sessions_held, total_sessions_attended,
       avg_attendance_percentage
FROM course_attendance_summary
WHERE avg_attendance_percentage IS NOT NULL
HAVING avg_attendance_percentage < 80
ORDER BY avg_attendance_percentage ASC;
```

Output:

```text
+-------------+--------------------------------+-------------------+---------------------+-------------------------+---------------------------+
| course_code | course_name                    | enrolled_students | total_sessions_held | total_sessions_attended | avg_attendance_percentage |
+-------------+--------------------------------+-------------------+---------------------+-------------------------+---------------------------+
| STA301      | Statistical Inference          |                12 |                 215 |                     165 |                     76.74 |
| CSE202      | Data Structures and Algorithms |                13 |                 303 |                     242 |                     79.87 |
+-------------+--------------------------------+-------------------+---------------------+-------------------------+---------------------------+
```

### C.4 Course-wise average marks with the department roll-up

*Concepts:* multi-table join, aggregate functions, STDDEV.

```sql
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
```

Output:

```text
+-------------+--------------------------------+-----------+-------------+----------------+----------------+--------+-----------+
| course_code | course_name                    | dept_code | assessments | graded_results | avg_percentage | spread | pass_rate |
+-------------+--------------------------------+-----------+-------------+----------------+----------------+--------+-----------+
| STA301      | Statistical Inference          | STAT      |           5 |             45 |          57.14 |  26.01 |     68.89 |
| MTH305      | Real Analysis                  | MATH      |           5 |             74 |          58.32 |  22.29 |     78.38 |
| CSE202      | Data Structures and Algorithms | CSE       |           5 |             60 |          59.06 |  19.82 |     80.00 |
| MTH210      | Probability and Statistics     | MATH      |           5 |             76 |          62.45 |  21.58 |     85.53 |
| MTH201      | Linear Algebra                 | MATH      |           5 |             59 |          64.18 |  23.29 |     81.36 |
| MTH401      | Numerical Methods              | MATH      |           5 |             25 |          78.94 |  10.99 |    100.00 |
+-------------+--------------------------------+-----------+-------------+----------------+----------------+--------+-----------+
```

### C.5 Students performing below their own course average

*Concepts:* correlated subquery in the WHERE clause.

```sql
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
```

Output:

```text
+------------+-----------------+-------------+-------------+------------+
| student_id | student_name    | course_code | student_avg | course_avg |
+------------+-----------------+-------------+-------------+------------+
| MTH2024008 | Aisha Menon     | CSE202      |       20.18 |      57.50 |
| MTH2024023 | Omar Joshi      | CSE202      |       37.96 |      57.50 |
| MTH2024009 | Raghav Rao      | CSE202      |       39.77 |      57.50 |
| MTH2024001 | Raghav Trivedi  | CSE202      |       44.19 |      57.50 |
| MTH2024014 | Rohan Dutta     | CSE202      |       45.97 |      57.50 |
| MTH2024019 | Veer Agarwal    | CSE202      |       51.97 |      57.50 |
| MTH2024023 | Omar Joshi      | MTH201      |       18.75 |      59.85 |
| MTH2024008 | Aisha Menon     | MTH201      |       20.70 |      59.85 |
| PHY2024002 | Arjun Agarwal   | MTH201      |       31.66 |      59.85 |
| MTH2024001 | Raghav Trivedi  | MTH201      |       41.21 |      59.85 |
| MTH2024019 | Veer Agarwal    | MTH201      |       45.82 |      59.85 |
| MTH2024018 | Rohan Patel     | MTH201      |       57.70 |      59.85 |
| PHY2024002 | Arjun Agarwal   | MTH210      |       14.65 |      60.70 |
| MTH2024008 | Aisha Menon     | MTH210      |       29.17 |      60.70 |
| MTH2024001 | Raghav Trivedi  | MTH210      |       42.92 |      60.70 |
| MTH2024014 | Rohan Dutta     | MTH210      |       45.41 |      60.70 |
| MTH2024018 | Rohan Patel     | MTH210      |       47.04 |      60.70 |
| MTH2024009 | Raghav Rao      | MTH210      |       47.62 |      60.70 |
| CSE2024006 | Harsh Mehta     | MTH210      |       51.00 |      60.70 |
| MTH2024019 | Veer Agarwal    | MTH210      |       55.52 |      60.70 |
+------------+-----------------+-------------+-------------+------------+
(15 further rows omitted; 35 in total)
```

### C.6 High-risk students by department, with the department share

*Concepts:* CTE + window function (SUM OVER) for the percentage.

```sql
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
```

Output:

```text
+-----------+------------------------------------------------+-------------+-----------+---------------+------------------------+
| dept_code | dept_name                                      | enrollments | high_risk | high_risk_pct | share_of_all_high_risk |
+-----------+------------------------------------------------+-------------+-----------+---------------+------------------------+
| MATH      | Department of Mathematics                      |          54 |         6 |         11.11 |                  66.67 |
| STAT      | Department of Statistics                       |          10 |         3 |         30.00 |                  33.33 |
| CSE       | Department of Computer Science and Engineering |          12 |         0 |          0.00 |                   0.00 |
| PHY       | Department of Physics                          |           4 |         0 |          0.00 |                   0.00 |
+-----------+------------------------------------------------+-------------+-----------+---------------+------------------------+
```

### C.7 Risk distribution by semester

*Concepts:* pivot via conditional aggregation.

```sql
SELECT student_semester                      AS semester,
       COUNT(*)                              AS enrollments,
       SUM(risk_category = 'LOW')            AS low_risk,
       SUM(risk_category = 'MEDIUM')         AS medium_risk,
       SUM(risk_category = 'HIGH')           AS high_risk,
       SUM(risk_category = 'INSUFFICIENT_DATA') AS insufficient_data,
       ROUND(AVG(CASE WHEN risk_category IN ('LOW', 'MEDIUM', 'HIGH')
                      THEN risk_score END), 2) AS avg_risk_score
FROM student_risk_summary
GROUP BY student_semester
ORDER BY student_semester;
```

Output:

```text
+----------+-------------+----------+-------------+-----------+-------------------+----------------+
| semester | enrollments | low_risk | medium_risk | high_risk | insufficient_data | avg_risk_score |
+----------+-------------+----------+-------------+-----------+-------------------+----------------+
|        3 |          44 |       23 |          17 |         4 |                 0 |          28.56 |
|        5 |          24 |        8 |           9 |         5 |                 2 |          36.44 |
|        7 |          12 |       10 |           0 |         0 |                 2 |          11.66 |
+----------+-------------+----------+-------------+-----------+-------------------+----------------+
```

### C.8 Assignment submission patterns per assessment

*Concepts:* LEFT JOIN so assessments with zero submissions still show.

```sql
SELECT course_code, assessment_title, assessment_type, due_at,
       total_expected, on_time, late, missing, on_time_rate, avg_percentage
FROM v_submission_patterns
ORDER BY course_code, due_at;
```

Output:

```text
+-------------+-----------------------------+-----------------+---------------------+----------------+---------+------+---------+--------------+----------------+
| course_code | assessment_title            | assessment_type | due_at              | total_expected | on_time | late | missing | on_time_rate | avg_percentage |
+-------------+-----------------------------+-----------------+---------------------+----------------+---------+------+---------+--------------+----------------+
| CSE202      | CSE202 Assignment 1         | ASSIGNMENT      | 2026-08-28 17:00:00 |             13 |       9 |    4 |       0 |        69.23 |          57.21 |
| CSE202      | CSE202 Quiz 1               | QUIZ            | 2026-09-11 17:00:00 |             13 |       8 |    4 |       1 |        61.54 |          57.03 |
| CSE202      | CSE202 Assignment 2         | ASSIGNMENT      | 2026-09-25 17:00:00 |             13 |       8 |    3 |       2 |        61.54 |          64.71 |
| CSE202      | CSE202 Mid-term Examination | MIDTERM         | 2026-10-08 17:00:00 |             13 |       9 |    4 |       0 |        69.23 |          54.63 |
| CSE202      | CSE202 Quiz 2               | QUIZ            | 2026-10-22 17:00:00 |             13 |       8 |    3 |       2 |        61.54 |          63.07 |
| MTH201      | MTH201 Assignment 1         | ASSIGNMENT      | 2026-08-28 17:00:00 |             14 |       8 |    3 |       3 |        57.14 |          63.20 |
| MTH201      | MTH201 Quiz 1               | QUIZ            | 2026-09-11 17:00:00 |             14 |       9 |    4 |       1 |        64.29 |          60.42 |
| MTH201      | MTH201 Assignment 2         | ASSIGNMENT      | 2026-09-25 17:00:00 |             14 |      10 |    2 |       2 |        71.43 |          65.95 |
| MTH201      | MTH201 Mid-term Examination | MIDTERM         | 2026-10-08 17:00:00 |             14 |       8 |    4 |       2 |        57.14 |          65.67 |
| MTH201      | MTH201 Quiz 2               | QUIZ            | 2026-10-22 17:00:00 |             14 |       8 |    3 |       3 |        57.14 |          66.05 |
| MTH210      | MTH210 Assignment 1         | ASSIGNMENT      | 2026-08-28 17:00:00 |             17 |       8 |    6 |       3 |        47.06 |          59.81 |
| MTH210      | MTH210 Quiz 1               | QUIZ            | 2026-09-11 17:00:00 |             17 |       8 |    6 |       3 |        47.06 |          62.33 |
| MTH210      | MTH210 Assignment 2         | ASSIGNMENT      | 2026-09-25 17:00:00 |             17 |      11 |    5 |       1 |        64.71 |          64.70 |
| MTH210      | MTH210 Mid-term Examination | MIDTERM         | 2026-10-08 17:00:00 |             17 |      10 |    6 |       1 |        58.82 |          60.36 |
| MTH210      | MTH210 Quiz 2               | QUIZ            | 2026-10-22 17:00:00 |             17 |      12 |    4 |       1 |        70.59 |          64.71 |
| MTH305      | MTH305 Assignment 1         | ASSIGNMENT      | 2026-08-28 17:00:00 |             16 |      13 |    3 |       0 |        81.25 |          54.91 |
| MTH305      | MTH305 Quiz 1               | QUIZ            | 2026-09-11 17:00:00 |             16 |       9 |    6 |       1 |        56.25 |          56.82 |
| MTH305      | MTH305 Assignment 2         | ASSIGNMENT      | 2026-09-25 17:00:00 |             16 |      10 |    4 |       2 |        62.50 |          61.56 |
| MTH305      | MTH305 Mid-term Examination | MIDTERM         | 2026-10-08 17:00:00 |             16 |      11 |    4 |       1 |        68.75 |          56.33 |
| MTH305      | MTH305 Quiz 2               | QUIZ            | 2026-10-22 17:00:00 |             16 |      10 |    4 |       2 |        62.50 |          62.72 |
+-------------+-----------------------------+-----------------+---------------------+----------------+---------+------+---------+--------------+----------------+
(10 further rows omitted; 30 in total)
```

### C.9 Academic performance trend — average score per course per month

*Concepts:* date truncation, GROUP BY on an expression.

```sql
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
```

Output:

```text
+---------+-------------+----------------+----------------+
| period  | course_code | graded_results | avg_percentage |
+---------+-------------+----------------+----------------+
| 2026-08 | CSE202      |             13 |          57.21 |
| 2026-08 | MTH201      |             11 |          63.20 |
| 2026-08 | MTH210      |             14 |          59.81 |
| 2026-08 | MTH305      |             16 |          54.91 |
| 2026-08 | MTH401      |              5 |          78.98 |
| 2026-08 | STA301      |              9 |          59.42 |
| 2026-09 | CSE202      |             23 |          60.70 |
| 2026-09 | MTH201      |             25 |          63.07 |
| 2026-09 | MTH210      |             30 |          63.59 |
| 2026-09 | MTH305      |             29 |          59.11 |
| 2026-09 | MTH401      |             10 |          77.41 |
| 2026-09 | STA301      |             18 |          55.24 |
| 2026-10 | CSE202      |             24 |          58.50 |
| 2026-10 | MTH201      |             23 |          65.85 |
| 2026-10 | MTH210      |             32 |          62.53 |
| 2026-10 | MTH305      |             29 |          59.41 |
| 2026-10 | MTH401      |             10 |          80.45 |
| 2026-10 | STA301      |             18 |          57.91 |
+---------+-------------+----------------+----------------+
```

### C.10 Intervention effectiveness by type

*Concepts:* aggregate over a view, HAVING to drop thin samples.

```sql
SELECT intervention_type,
       COUNT(*)                            AS total,
       SUM(outcome = 'IMPROVED')           AS improved,
       SUM(outcome = 'NO_CHANGE')          AS no_change,
       SUM(outcome = 'PENDING')            AS pending,
       SUM(outcome = 'ESCALATED')          AS escalated,
       SUM(outcome = 'DECLINED')           AS declined,
       ROUND(100.0 * SUM(outcome = 'IMPROVED') / COUNT(*), 2) AS improvement_rate,
       ROUND(AVG(CASE WHEN current_risk_category IN ('LOW', 'MEDIUM', 'HIGH')
                      THEN current_risk_score END), 2) AS avg_current_risk
FROM v_intervention_outcomes
GROUP BY intervention_type
HAVING COUNT(*) > 0
ORDER BY improvement_rate DESC;
```

Output:

```text
+---------------------+-------+----------+-----------+---------+-----------+----------+------------------+------------------+
| intervention_type   | total | improved | no_change | pending | escalated | declined | improvement_rate | avg_current_risk |
+---------------------+-------+----------+-----------+---------+-----------+----------+------------------+------------------+
| ATTENDANCE_FOLLOWUP |     2 |        1 |         1 |       0 |         0 |        0 |            50.00 |            59.86 |
| TUTORING_REFERRAL   |     2 |        1 |         0 |       1 |         0 |        0 |            50.00 |            59.48 |
| ACADEMIC_ADVISING   |     2 |        1 |         0 |       0 |         1 |        0 |            50.00 |            65.18 |
| COUNSELING          |     3 |        1 |         0 |       1 |         0 |        1 |            33.33 |            67.69 |
| ASSIGNMENT_SUPPORT  |     2 |        0 |         0 |       2 |         0 |        0 |             0.00 |            75.48 |
| PARENT_CONTACT      |     1 |        0 |         1 |       0 |         0 |        0 |             0.00 |            67.73 |
+---------------------+-------+----------+-----------+---------+-----------+----------+------------------+------------------+
```

### C.11 Risk trend over time — each enrolment's change between its two most recent risk calculations

*Concepts:* CTE + LAG() window function.

```sql
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
```

Output:

```text
Empty set
```

*Why it is empty:* The seed runs one risk calculation per enrolment, so no enrolment has a previous score to compare with. One more run of `sp_recalculate_all_risk` and all 80 active enrolments return a row.

### C.12 Unresolved high-risk alerts older than 7 days — the escalation queue the dashboard highlights

*Concepts:* date arithmetic, join to the assignee, IS NULL handling.

```sql
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
```

Output:

```text
Empty set
```

*Why it is empty:* Every alert in the demonstration data is raised when the seed's risk calculation runs, so none is yet older than seven days. The query is the escalation view an operating system would see after a week.

### C.13 Students at risk in more than one course simultaneously

*Concepts:* GROUP BY + HAVING COUNT(*) > 1, GROUP_CONCAT.

```sql
SELECT student_id, student_name, dept_code,
       COUNT(*)                                   AS at_risk_courses,
       GROUP_CONCAT(course_code ORDER BY course_code SEPARATOR ', ') AS courses,
       ROUND(AVG(risk_score), 2)                  AS avg_risk_score
FROM student_risk_summary
WHERE risk_category IN ('MEDIUM', 'HIGH')
GROUP BY student_pk, student_id, student_name, dept_code
HAVING COUNT(*) > 1
ORDER BY at_risk_courses DESC, avg_risk_score DESC;
```

Output:

```text
+------------+----------------+-----------+-----------------+------------------------+----------------+
| student_id | student_name   | dept_code | at_risk_courses | courses                | avg_risk_score |
+------------+----------------+-----------+-----------------+------------------------+----------------+
| MTH2024008 | Aisha Menon    | MATH      |               3 | CSE202, MTH201, MTH210 |          66.55 |
| MTH2024001 | Raghav Trivedi | MATH      |               3 | CSE202, MTH201, MTH210 |          42.39 |
| MTH2024019 | Veer Agarwal   | MATH      |               3 | CSE202, MTH201, MTH210 |          40.60 |
| MTH2023024 | Pooja Shetty   | MATH      |               2 | MTH305, STA301         |          70.66 |
| MTH2024023 | Omar Joshi     | MATH      |               2 | CSE202, MTH201         |          70.49 |
| STA2023003 | Sara Ghosh     | STAT      |               2 | MTH305, STA301         |          69.44 |
| STA2023004 | Veer Kapoor    | STAT      |               2 | MTH305, STA301         |          60.48 |
| PHY2024002 | Arjun Agarwal  | PHY       |               2 | MTH201, MTH210         |          58.55 |
| MTH2023020 | Raghav Sheikh  | MATH      |               2 | MTH305, STA301         |          42.50 |
| MTH2024009 | Raghav Rao     | MATH      |               2 | CSE202, MTH210         |          40.78 |
| CSE2023001 | Meera Kapoor   | CSE       |               2 | MTH305, STA301         |          40.78 |
| MTH2024018 | Rohan Patel    | MATH      |               2 | MTH201, MTH210         |          36.24 |
| CSE2024006 | Harsh Mehta    | CSE       |               2 | CSE202, MTH210         |          36.17 |
| MTH2023002 | Juhi Ansari    | MATH      |               2 | MTH305, STA301         |          34.74 |
| MTH2023015 | Rohan Bose     | MATH      |               2 | MTH305, STA301         |          34.38 |
| MTH2024014 | Rohan Dutta    | MATH      |               2 | CSE202, MTH210         |          33.59 |
+------------+----------------+-----------+-----------------+------------------------+----------------+
```

### C.14 Engagement cliff — enrolments with no LMS event in 14+ days

*Concepts:* LEFT JOIN + aggregate in a derived table, NULL semantics.

```sql
SELECT spv.student_id, spv.student_name, spv.course_code,
       spv.last_activity_at, spv.days_since_last_activity,
       spv.login_count_30d, spv.attendance_percentage
FROM student_performance_view spv
WHERE spv.days_since_last_activity IS NULL
   OR spv.days_since_last_activity >= 14
ORDER BY spv.days_since_last_activity IS NULL DESC,
         spv.days_since_last_activity DESC;
```

Output:

```text
+------------+--------------+-------------+---------------------+--------------------------+-----------------+-----------------------+
| student_id | student_name | course_code | last_activity_at    | days_since_last_activity | login_count_30d | attendance_percentage |
+------------+--------------+-------------+---------------------+--------------------------+-----------------+-----------------------+
| MTH2023024 | Pooja Shetty | MTH305      | 2026-09-20 21:23:00 |                       39 |               0 |                 57.14 |
| MTH2024023 | Omar Joshi   | CSE202      | 2026-09-23 19:30:00 |                       36 |               0 |                 33.33 |
| STA2023003 | Sara Ghosh   | STA301      | 2026-10-02 19:30:00 |                       27 |               1 |                 40.00 |
| MTH2024008 | Aisha Menon  | MTH201      | 2026-10-05 19:30:00 |                       24 |               1 |                 33.33 |
| STA2023003 | Sara Ghosh   | MTH305      | 2026-10-08 19:30:00 |                       21 |               3 |                 60.00 |
| STA2023004 | Veer Kapoor  | STA301      | 2026-10-08 19:30:00 |                       21 |               1 |                 40.00 |
+------------+--------------+-------------+---------------------+--------------------------+-----------------+-----------------------+
```

### C.15 Index usage proof — run EXPLAIN on the hottest filter to show the composite index on (enrollment_id, activity_at) being used

```sql
EXPLAIN SELECT COUNT(*) FROM lms_activity_logs
 WHERE enrollment_id = 1
   AND activity_at >= (CURRENT_DATE - INTERVAL 30 DAY);
```

Output:

```text
+----+-------------+-------------------+------------+-------+-------------------------------------------+------------------------+---------+------+------+----------+--------------------------+
| id | select_type | table             | partitions | type  | possible_keys                             | key                    | key_len | ref  | rows | filtered | Extra                    |
+----+-------------+-------------------+------------+-------+-------------------------------------------+------------------------+---------+------+------+----------+--------------------------+
|  1 | SIMPLE      | lms_activity_logs | NULL       | range | ix_lms_enrollment_time,ix_lms_activity_at | ix_lms_enrollment_time | 9       | NULL |   26 |   100.00 | Using where; Using index |
+----+-------------+-------------------+------------+-------+-------------------------------------------+------------------------+---------+------+------+----------+--------------------------+
```

---

## Appendix D — API endpoints

Section 4 of `docs/api_documentation.md`. `backend/tests/test_api_docs.py` checks every row against the routes the application actually serves.

### D.1 Authentication — `/api/auth`

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
`"Incorrect email or password"`, and both cost one Argon2 verification
(an unknown email is checked against a dummy digest), so neither the
message nor the response time can be used to enumerate accounts. Both outcomes are written to `audit_logs`.

After 5 failed attempts for one email, or 20 from one client address, within 15 minutes, the endpoint returns **429** `too_many_requests` with a `Retry-After` header (seconds) until the oldest failure leaves the window. The same applies to an email with no account, so a 429 does not reveal whether it exists. A successful sign-in clears that email's count.
</details>

### D.2 Reference data

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/enums` | any signed-in | Every ENUM value with a display label — the UI's dropdown source |
| GET | `/departments` | any signed-in | List departments |
| POST | `/departments` | `settings:write` | Create a department |
| GET | `/course-options` | `courses:read` | Lightweight course list for filters |
| GET | `/student-options` | `courses:read` | Lightweight student list for enrolment pickers |

### D.3 Dashboard — `/api/dashboard`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/summary` | `reports:read` | Headline counters, risk counts, averages, alert and intervention totals |
| GET | `/recent-alerts` | `reports:read` | Most recent alerts, highest risk first (`limit`, `only_open`) |
| GET | `/performance-trend` | `reports:read` | Monthly assessment mean + attendance rate (`course_pk`, `months`) |

Every figure is aggregated in SQL. With an empty database the counters
return `0` and the averages return `null` — never a hardcoded value.

### D.4 Students — `/api/students`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `students:read` | List with search, filters, sorting, pagination and a per-student summary |
| POST | `` | `students:write` | Add a student |
| GET | `/{student_pk}` | `students:read` | One student |
| GET | `/{student_pk}/profile` | `students:read` | Summary, a row per enrolled course, and the configured band thresholds |
| PUT | `/{student_pk}` | `students:write` | Update |
| PATCH | `/{student_pk}/deactivate` | `students:write` | Soft delete |
| PATCH | `/{student_pk}/reactivate` | `students:write` | Restore |

Filters: `search` (roll/name/email), `dept_id`, `semester`,
`enrollment_year`, `is_active`, `risk_category`.
Sorting: `sort_by` ∈ {`student_id`, `full_name`, `semester`,
`enrollment_year`, `created_at`}, `sort_dir` ∈ {`asc`, `desc`}. An
unrecognised `sort_by` is rejected with 422 — the value never reaches SQL.

### D.5 Courses — `/api/courses`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `courses:read` | List with statistics (headcount, attendance, marks, high-risk count) |
| POST | `` | `courses:write` | Create |
| GET | `/{course_pk}` | `courses:read` | One course |
| PUT | `/{course_pk}` | `courses:write` | Update |
| GET | `/{course_pk}/roster` | `courses:read` | Enrolled students with their risk band |
| POST | `/{course_pk}/instructors` | `courses:write` | Assign an instructor |
| DELETE | `/{course_pk}/instructors/{user_id}` | `courses:write` | Unassign |

### D.6 Enrolments — `/api/enrollments`

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

### D.7 Attendance — `/api/attendance`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `attendance:read` | Historical records (`course_pk`, `student_pk`, `enrollment_id`, `date_from`, `date_to`, `attendance_status`) |
| GET | `/summary` | `attendance:read` | Classes held and attended per enrolment |
| POST | `` | `attendance:write` | Record one entry — **idempotent** on (enrolment, date, session) |
| POST | `/bulk` | `attendance:write` | Mark a whole roster for one session |
| DELETE | `/{attendance_id}` | `attendance:write` | Delete a record |

`LATE` counts as attended; `EXCUSED` is excluded from the denominator.

### D.8 LMS activity — `/api/activity`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `activity:read` | Event log (`course_pk`, `student_pk`, `activity_type`, `date_from`, `date_to`) |
| GET | `/summary` | `activity:read` | Login frequency, minutes and last-seen per enrolment |
| POST | `` | `activity:write` | Log one event |

### D.9 Assessments — `/api/assessments` and `/api/assessment-results`

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

### D.10 Risk analysis — `/api/risk-assessments`

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

### D.11 Alerts — `/api/alerts`

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

### D.12 Interventions — `/api/interventions`

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

### D.13 Reports — `/api/reports`

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

### D.14 Settings — `/api/settings`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `` | `settings:read` | All settings |
| GET | `/risk-config` | `settings:read` | The resolved model configuration |
| PUT | `/{setting_key}` | `settings:write` | Update one setting |
| GET | `/audit/logs` | `audit:read` | Browse the audit trail |

Numeric settings are range-checked, and the medium threshold must stay
below the high threshold — crossing them is rejected with 422.

### D.15 Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service banner |
| GET | `/health` | Liveness **and** real database connectivity |

```json
{ "status": "ok", "database": "connected", "dialect": "mysql" }
```

---

---

## Appendix E — Selected source listings

The functions at the centre of Chapter 5: the Python risk model, the alert reconciliation that keeps one open alert per enrolment, and the server-side permission check behind every protected endpoint.

### `backend/app/services/risk_engine.py` — `compute_engagement_score`, `compute_risk`, `_reconcile_alert`

```python
def compute_engagement_score(
    days_since_last_activity: Optional[int],
    login_count_30d: int,
    missing_submissions: int,
    late_submissions: int,
    results_recorded: int,
    target_logins: int = 12,
) -> Tuple[Decimal, dict]:
    """Engagement Score on 0-100 where 100 is fully engaged.

    ``engagement_score = clamp(100 - (recency + frequency + missing + late), 0, 100)``

    * **recency** -- days since the most recent LMS event:
      never active -> 50, <=3 -> 0, <=7 -> 10, <=14 -> 20, <=30 -> 35, >30 -> 50
    * **frequency** -- logins in the window against the target (default 12):
      >= target -> 0, >= 2/3 target -> 5, >= 1/3 target -> 12, >= 1 -> 20, 0 -> 30
    * **missing** -- ``40 * missing_submissions / results_recorded``
    * **late** -- ``20 * late_submissions / results_recorded``

    The frequency bands use integer cross-multiplication (``logins * 3 >=
    target * 2``) rather than a float ratio, so this function and the SQL
    function ``fn_engagement_score`` can never disagree at a boundary.
    """
    target = max(int(target_logins), 1)
    logins = max(int(login_count_30d), 0)

    # recency penalty
    if days_since_last_activity is None:
        recency = RECENCY_PENALTY_NEVER
    else:
        recency = RECENCY_PENALTY_BEYOND
        for upper, penalty in RECENCY_BANDS:
            if days_since_last_activity <= upper:
                recency = penalty
                break

    # login frequency penalty
    if logins >= target:
        frequency = Decimal("0")
    elif logins * 3 >= target * 2:
        frequency = Decimal("5")
    elif logins * 3 >= target:
        frequency = Decimal("12")
    elif logins >= 1:
        frequency = Decimal("20")
    else:
        frequency = Decimal("30")

    # submission-behaviour penalties
    if results_recorded > 0:
        total = Decimal(results_recorded)
        missing = MISSING_PENALTY_MAX * Decimal(max(missing_submissions, 0)) / total
        late = LATE_PENALTY_MAX * Decimal(max(late_submissions, 0)) / total
    else:
        missing = ZERO
        late = ZERO

    score = _q2(_clamp(HUNDRED - (recency + frequency + missing + late)))
    breakdown = {
        "recency_penalty": float(recency),
        "login_frequency_penalty": float(frequency),
        "missing_submission_penalty": float(_q2(missing)),
        "late_submission_penalty": float(_q2(late)),
        "engagement_score": float(score),
    }
    return score, breakdown


def compute_risk(metrics: EnrollmentMetrics, config: Optional[RiskConfig] = None) -> RiskResult:
    """Turn observed metrics into a risk profile. Pure and deterministic."""
    cfg = config or RiskConfig()
    result = RiskResult(model_version=cfg.model_version)
    reasons: List[str] = []

    available_weight = ZERO
    weighted_sum = ZERO
    components = 0

    # --- component 1: attendance ------------------------------------------
    att_pct = _dec(metrics.attendance_percentage)
    result.attendance_percentage = att_pct
    if metrics.sessions_held >= cfg.min_sessions and att_pct is not None:
        result.attendance_risk = _q2(HUNDRED - att_pct)
        available_weight += cfg.weight_attendance
        weighted_sum += cfg.weight_attendance * result.attendance_risk
        components += 1
    else:
        reasons.append(
            f"Attendance component skipped: only {metrics.sessions_held} of "
            f"{cfg.min_sessions} required sessions recorded"
        )

    # --- component 2: academic --------------------------------------------
    aca_pct = _dec(metrics.avg_assessment_percentage)
    result.avg_assessment_percentage = aca_pct
    if metrics.graded_assessments >= cfg.min_graded and aca_pct is not None:
        result.academic_risk = _q2(HUNDRED - aca_pct)
        available_weight += cfg.weight_academic
        weighted_sum += cfg.weight_academic * result.academic_risk
        components += 1
    else:
        reasons.append(
            f"Academic component skipped: {metrics.graded_assessments} graded "
            f"assessment(s) on record"
        )

    # --- component 3: engagement ------------------------------------------
    if metrics.total_activities > 0 or metrics.results_recorded > 0:
        score, breakdown = compute_engagement_score(
            metrics.days_since_last_activity,
            metrics.login_count_30d,
            metrics.missing_submissions,
            metrics.late_submissions,
            metrics.results_recorded,
            cfg.target_logins_30d,
        )
        result.engagement_score = score
        result.engagement_breakdown = breakdown
        result.engagement_risk = _q2(HUNDRED - score)
        available_weight += cfg.weight_engagement
        weighted_sum += cfg.weight_engagement * result.engagement_risk
        components += 1
    else:
        reasons.append(
            "Engagement component skipped: no LMS activity or assessment records"
        )

    # --- weighted, re-normalised score ------------------------------------
    if available_weight > 0:
        result.risk_score = _q2(_clamp(weighted_sum / available_weight))

    result.components_available = components
    result.data_completeness = (
        "COMPLETE" if components >= 3 else "PARTIAL" if components == 2 else "INSUFFICIENT"
    )

    if result.risk_score is None or result.data_completeness == "INSUFFICIENT":
        result.risk_category = "INSUFFICIENT_DATA"
    elif result.risk_score >= cfg.threshold_high:
        result.risk_category = "HIGH"
    elif result.risk_score >= cfg.threshold_medium:
        result.risk_category = "MEDIUM"
    else:
        result.risk_category = "LOW"

    if reasons:
        result.missing_data_reasons = "; ".join(reasons)
    elif result.data_completeness != "COMPLETE":
        result.missing_data_reasons = "One or more risk components had no supporting data"

    result.contributing_factors = _build_factors(metrics, result, cfg)
    return result


def _reconcile_alert(
    db: Session,
    enrollment_id: int,
    risk_row: RiskAssessment,
    result: RiskResult,
    cfg: RiskConfig,
    actor_user_id: Optional[int],
) -> None:
    """Raise, refresh or auto-close the single open alert for an enrolment.

    * At or above the threshold with no open alert -> raise one (``NEW``).
    * At or above the threshold with an open alert -> refresh that alert's
      score and factors. It is never duplicated; the composite unique key
      ``(enrollment_id, active_flag)`` makes a duplicate impossible even
      under a race.
    * Below the threshold with an open alert still in ``NEW`` -> close it
      automatically. An alert a human has already acknowledged or started
      working is left alone for that human to close.
    """
    open_alert = db.execute(
        select(RiskAlert).where(
            RiskAlert.enrollment_id == enrollment_id, RiskAlert.active_flag == 1
        )
    ).scalar_one_or_none()

    should_alert = (
        result.risk_category in ("MEDIUM", "HIGH")
        and result.risk_score is not None
        and result.risk_score >= Decimal(cfg.alert_min_score)
    )

    if should_alert:
        if open_alert is None:
            alert = RiskAlert(
                enrollment_id=enrollment_id,
                risk_id=risk_row.risk_id,
                risk_score=result.risk_score,
                risk_category=result.risk_category,
                triggering_factors=result.contributing_factors,
                status="NEW",
            )
            db.add(alert)
            db.flush()
            db.add(
                AlertStatusHistory(
                    alert_id=alert.alert_id,
                    old_status=None,
                    new_status="NEW",
                    changed_by=actor_user_id,
                    note="Alert raised by risk recalculation",
                )
            )
        else:
            open_alert.risk_id = risk_row.risk_id
            open_alert.risk_score = result.risk_score
            open_alert.risk_category = result.risk_category
            open_alert.triggering_factors = result.contributing_factors
    elif open_alert is not None and open_alert.status == "NEW":
        open_alert.status = "RESOLVED"
        open_alert.resolved_at = datetime.now()
        open_alert.risk_id = risk_row.risk_id
        db.flush()
        db.add(
            AlertStatusHistory(
                alert_id=open_alert.alert_id,
                old_status="NEW",
                new_status="RESOLVED",
                changed_by=actor_user_id,
                note=(
                    "Auto-resolved: risk score fell to "
                    f"{result.risk_score if result.risk_score is not None else 'n/a'}"
                ),
            )
        )
```

### `backend/app/api/deps.py` — `get_current_user`, `require_permissions`

```python
def get_current_user(
    db: DbSession,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)
    ] = None,
) -> User:
    """Resolve the bearer token to an active user row.

    The error messages here are intentionally uniform so a caller cannot
    distinguish "no such user" from "wrong signature".
    """
    if credentials is None or not credentials.credentials:
        raise AuthError("Authentication credentials were not supplied")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise AuthError("Access token has expired; please sign in again")
    except jwt.PyJWTError:
        raise AuthError("Invalid authentication token")

    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        raise AuthError("Invalid authentication token")

    user = db.execute(select(User).where(User.user_id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("User account is inactive or no longer exists")

    # A role change must take effect immediately, so trust the database
    # row rather than the (possibly stale) role claim inside the token.
    if payload.get("role") != user.role:
        raise AuthError("Token no longer matches the account; please sign in again")

    return user


class require_permissions:  # noqa: N801 - used as a dependency factory
    """Dependency enforcing that the caller holds every listed permission.

    Usage::

        @router.post("/", dependencies=[Depends(require_permissions(P_STUDENTS_WRITE))])
    """

    def __init__(self, *permissions: str):
        self.permissions = permissions

    def __call__(self, user: CurrentUser) -> User:
        granted = permissions_for(user.role)
        missing = [p for p in self.permissions if p not in granted]
        if missing:
            raise PermissionError_(
                f"Role {user.role} is not permitted to perform this action "
                f"(requires: {', '.join(missing)})"
            )
        return user
```
