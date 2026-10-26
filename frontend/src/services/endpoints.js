/** Every backend call the UI makes, in one place.
 *
 * Grouped to mirror the FastAPI routers so a page never builds a URL by
 * hand and a route rename is a one-line change here.
 */

import { del, downloadCsv, get, patch, post, put } from './api.js'

export const authApi = {
  login: (email, password) => post('/auth/login', { email, password }),
  me: () => get('/auth/me'),
  permissions: () => get('/auth/permissions'),
  changePassword: (payload) => post('/auth/change-password', payload),
  listUsers: (params) => get('/auth/users', params),
  assignableUsers: () => get('/auth/users/assignable'),
  createUser: (payload) => post('/auth/users', payload),
  updateUser: (userId, payload) => put(`/auth/users/${userId}`, payload),
}

export const lookupApi = {
  enums: () => get('/enums'),
  departments: () => get('/departments'),
  createDepartment: (payload) => post('/departments', payload),
  courseOptions: () => get('/course-options'),
  studentOptions: (params) => get('/student-options', params),
}

export const dashboardApi = {
  summary: () => get('/dashboard/summary'),
  recentAlerts: (params) => get('/dashboard/recent-alerts', params),
  performanceTrend: (params) => get('/dashboard/performance-trend', params),
}

export const studentApi = {
  list: (params) => get('/students', params),
  get: (pk) => get(`/students/${pk}`),
  profile: (pk) => get(`/students/${pk}/profile`),
  create: (payload) => post('/students', payload),
  update: (pk, payload) => put(`/students/${pk}`, payload),
  deactivate: (pk) => patch(`/students/${pk}/deactivate`),
  reactivate: (pk) => patch(`/students/${pk}/reactivate`),
}

export const courseApi = {
  list: (params) => get('/courses', params),
  get: (pk) => get(`/courses/${pk}`),
  create: (payload) => post('/courses', payload),
  update: (pk, payload) => put(`/courses/${pk}`, payload),
  roster: (pk) => get(`/courses/${pk}/roster`),
  assignInstructor: (pk, payload) => post(`/courses/${pk}/instructors`, payload),
  removeInstructor: (pk, userId) => del(`/courses/${pk}/instructors/${userId}`),
}

export const enrollmentApi = {
  list: (params) => get('/enrollments', params),
  create: (payload) => post('/enrollments', payload),
  bulkCreate: (payload) => post('/enrollments/bulk', payload),
  updateStatus: (id, payload) => patch(`/enrollments/${id}`, payload),
}

export const attendanceApi = {
  list: (params) => get('/attendance', params),
  summary: (params) => get('/attendance/summary', params),
  record: (payload) => post('/attendance', payload),
  bulkRecord: (payload) => post('/attendance/bulk', payload),
  remove: (id) => del(`/attendance/${id}`),
}

export const activityApi = {
  list: (params) => get('/activity', params),
  summary: (params) => get('/activity/summary', params),
  create: (payload) => post('/activity', payload),
}

export const assessmentApi = {
  list: (params) => get('/assessments', params),
  get: (id) => get(`/assessments/${id}`),
  create: (payload) => post('/assessments', payload),
  update: (id, payload) => put(`/assessments/${id}`, payload),
  results: (id) => get(`/assessments/${id}/results`),
  trends: (params) => get('/assessments/trends', params),
  listResults: (params) => get('/assessment-results', params),
  upsertResult: (payload) => post('/assessment-results', payload),
  bulkResults: (payload) => post('/assessment-results/bulk', payload),
}

export const riskApi = {
  list: (params) => get('/risk-assessments', params),
  detail: (enrollmentId) => get(`/risk-assessments/${enrollmentId}`),
  history: (enrollmentId, params) => get(`/risk-assessments/${enrollmentId}/history`, params),
  recalculate: (payload) => post('/risk-assessments/recalculate', payload ?? {}),
}

export const alertApi = {
  list: (params) => get('/alerts', params),
  summary: () => get('/alerts/summary'),
  detail: (id) => get(`/alerts/${id}`),
  update: (id, payload) => patch(`/alerts/${id}`, payload),
}

export const interventionApi = {
  list: (params) => get('/interventions', params),
  get: (id) => get(`/interventions/${id}`),
  create: (payload) => post('/interventions', payload),
  update: (id, payload) => put(`/interventions/${id}`, payload),
}

export const reportApi = {
  riskDistribution: (params) => get('/reports/risk-distribution', params),
  coursePerformance: (params) => get('/reports/course-performance', params),
  courseAttendance: (params) => get('/reports/course-attendance', params),
  submissionPatterns: (params) => get('/reports/submission-patterns', params),
  highRiskStudents: (params) => get('/reports/high-risk-students', params),
  departmentRisk: () => get('/reports/department-risk'),
  interventionOutcomes: (params) => get('/reports/intervention-outcomes', params),
  exportCsv: (report, params) =>
    downloadCsv('/reports/export', { report, ...params }, `se-ewrs-${report}.csv`),
}

export const settingsApi = {
  list: () => get('/settings'),
  riskConfig: () => get('/settings/risk-config'),
  update: (key, payload) => put(`/settings/${key}`, payload),
  auditLogs: (params) => get('/settings/audit/logs', params),
}
