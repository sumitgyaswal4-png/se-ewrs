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
