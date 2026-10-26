"""Aggregates every route module under the ``/api`` prefix."""

from fastapi import APIRouter

from app.api import (
    activity,
    alerts,
    assessments,
    attendance,
    auth,
    courses,
    enrollments,
    interventions,
    lookups,
    reports,
    risk,
    settings as settings_api,
    students,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(lookups.router, prefix="", tags=["Reference data"])
api_router.include_router(
    reports.dashboard_router, prefix="/dashboard", tags=["Dashboard"]
)
api_router.include_router(students.router, prefix="/students", tags=["Students"])
api_router.include_router(courses.router, prefix="/courses", tags=["Courses"])
api_router.include_router(
    enrollments.router, prefix="/enrollments", tags=["Enrollments"]
)
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
api_router.include_router(activity.router, prefix="/activity", tags=["LMS activity"])
api_router.include_router(
    assessments.router, prefix="/assessments", tags=["Assessments"]
)
api_router.include_router(
    assessments.results_router, prefix="/assessment-results", tags=["Assessments"]
)
api_router.include_router(
    risk.router, prefix="/risk-assessments", tags=["Risk analysis"]
)
api_router.include_router(alerts.router, prefix="/alerts", tags=["Early-warning alerts"])
api_router.include_router(
    interventions.router, prefix="/interventions", tags=["Interventions"]
)
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(
    settings_api.router, prefix="/settings", tags=["System settings"]
)
