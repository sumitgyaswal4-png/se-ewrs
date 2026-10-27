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
