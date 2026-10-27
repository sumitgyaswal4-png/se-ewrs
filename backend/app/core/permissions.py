"""Role-based access control.

Authorisation is expressed as named permissions rather than as role
checks scattered through the routers. ``ROLE_PERMISSIONS`` is the single
source of truth: the API enforces it server-side, and the frontend reads
the same map from ``GET /api/auth/permissions`` to decide which pages and
buttons to render. A client that hides a button it should not have is a
convenience -- the server refusing the call is the actual control.
"""

from typing import Dict, FrozenSet

# --- permission vocabulary -------------------------------------------------
P_USERS_READ = "users:read"
P_USERS_WRITE = "users:write"
P_STUDENTS_READ = "students:read"
P_STUDENTS_WRITE = "students:write"
P_COURSES_READ = "courses:read"
P_COURSES_WRITE = "courses:write"
P_ENROLLMENTS_WRITE = "enrollments:write"
P_ATTENDANCE_READ = "attendance:read"
P_ATTENDANCE_WRITE = "attendance:write"
P_ACTIVITY_READ = "activity:read"
P_ACTIVITY_WRITE = "activity:write"
P_ASSESSMENTS_READ = "assessments:read"
P_ASSESSMENTS_WRITE = "assessments:write"
P_RESULTS_WRITE = "results:write"
P_RISK_READ = "risk:read"
P_RISK_RECALC = "risk:recalculate"
P_ALERTS_READ = "alerts:read"
P_ALERTS_WRITE = "alerts:write"
P_INTERVENTIONS_READ = "interventions:read"
P_INTERVENTIONS_WRITE = "interventions:write"
P_REPORTS_READ = "reports:read"
P_SETTINGS_READ = "settings:read"
P_SETTINGS_WRITE = "settings:write"
P_AUDIT_READ = "audit:read"

ALL_PERMISSIONS: FrozenSet[str] = frozenset(
    {
        P_USERS_READ,
        P_USERS_WRITE,
        P_STUDENTS_READ,
        P_STUDENTS_WRITE,
        P_COURSES_READ,
        P_COURSES_WRITE,
        P_ENROLLMENTS_WRITE,
        P_ATTENDANCE_READ,
        P_ATTENDANCE_WRITE,
        P_ACTIVITY_READ,
        P_ACTIVITY_WRITE,
        P_ASSESSMENTS_READ,
        P_ASSESSMENTS_WRITE,
        P_RESULTS_WRITE,
        P_RISK_READ,
        P_RISK_RECALC,
        P_ALERTS_READ,
        P_ALERTS_WRITE,
        P_INTERVENTIONS_READ,
        P_INTERVENTIONS_WRITE,
        P_REPORTS_READ,
        P_SETTINGS_READ,
        P_SETTINGS_WRITE,
        P_AUDIT_READ,
    }
)

# --- role -> permission map ------------------------------------------------
_READ_ONLY_CORE = {
    P_STUDENTS_READ,
    P_COURSES_READ,
    P_ATTENDANCE_READ,
    P_ACTIVITY_READ,
    P_ASSESSMENTS_READ,
    P_RISK_READ,
    P_REPORTS_READ,
}

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    # Administrator -- manages users, students, courses, enrolments and
    # system settings.
    "ADMIN": ALL_PERMISSIONS,
    # Instructor -- owns their courses' assessments, grades and alerts.
    "INSTRUCTOR": frozenset(
        _READ_ONLY_CORE
        | {
            P_ATTENDANCE_WRITE,
            P_ASSESSMENTS_WRITE,
            P_RESULTS_WRITE,
            P_RISK_RECALC,
            P_ALERTS_READ,
            P_ALERTS_WRITE,
            P_INTERVENTIONS_READ,
            P_INTERVENTIONS_WRITE,
            P_ENROLLMENTS_WRITE,
        }
    ),
    # Teaching Assistant -- records attendance and LMS activity, assists
    # with intervention tracking. No grading, no alert decisions.
    "TA": frozenset(
        _READ_ONLY_CORE
        | {
            P_ATTENDANCE_WRITE,
            P_ACTIVITY_WRITE,
            P_INTERVENTIONS_READ,
            P_INTERVENTIONS_WRITE,
        }
    ),
    # Academic Advisor -- works the alert queue and owns counselling
    # records. Does not grade or edit the catalogue.
    "ADVISOR": frozenset(
        _READ_ONLY_CORE
        | {
            P_ALERTS_READ,
            P_ALERTS_WRITE,
            P_INTERVENTIONS_READ,
            P_INTERVENTIONS_WRITE,
        }
    ),
    # Department Chair -- oversight only: statistics, reports, risk
    # summaries. Deliberately has no write permission at all.
    "CHAIR": frozenset(_READ_ONLY_CORE | {P_ALERTS_READ, P_INTERVENTIONS_READ}),
}


def permissions_for(role: str) -> FrozenSet[str]:
    """Permissions granted to ``role``; unknown roles get nothing."""
    return ROLE_PERMISSIONS.get(role, frozenset())

