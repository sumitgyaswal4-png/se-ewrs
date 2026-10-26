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
