/** Labels and option lists shared across pages.
 *
 * The authoritative vocabulary is the database's own ENUMs, served by
 * `GET /api/enums`; these constants cover the handful of places that need
 * a label before that request resolves.
 */

export const RISK_LABELS = {
  LOW: 'Low risk',
  MEDIUM: 'Medium risk',
  HIGH: 'High risk',
  INSUFFICIENT_DATA: 'Needs more data',
}

export const RISK_RANGES = {
  LOW: '0-29',
  MEDIUM: '30-59',
  HIGH: '60-100',
  INSUFFICIENT_DATA: 'not scored',
}

export const ALERT_STATUS_LABELS = {
  NEW: 'New',
  ACKNOWLEDGED: 'Acknowledged',
  IN_PROGRESS: 'In progress',
  RESOLVED: 'Resolved',
}

/** Mirrors ALLOWED_TRANSITIONS in app/api/alerts.py. The server is the
 *  authority; this only decides which buttons to show. */
export const ALERT_TRANSITIONS = {
  NEW: ['ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED'],
  ACKNOWLEDGED: ['IN_PROGRESS', 'RESOLVED'],
  IN_PROGRESS: ['RESOLVED'],
  RESOLVED: [],
}

export const ATTENDANCE_STATUS_LABELS = {
  PRESENT: 'Present',
  ABSENT: 'Absent',
  LATE: 'Late',
  EXCUSED: 'Excused',
}

export const PAGE_SIZES = [10, 20, 50, 100]

export const SEMESTERS = Array.from({ length: 12 }, (_, index) => index + 1)
