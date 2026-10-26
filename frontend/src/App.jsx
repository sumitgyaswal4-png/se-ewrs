/** Routing and route guards. */

import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { Spinner } from './components/States.jsx'
import { useAuth } from './hooks/useAuth.jsx'
import AppLayout from './layouts/AppLayout.jsx'
import { ROLE_HOME } from './layouts/navigation.js'

import AccountPage from './pages/AccountPage.jsx'
import ActivityPage from './pages/ActivityPage.jsx'
import AlertsPage from './pages/AlertsPage.jsx'
import AssessmentsPage from './pages/AssessmentsPage.jsx'
import AttendancePage from './pages/AttendancePage.jsx'
import CoursesPage from './pages/CoursesPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import InterventionsPage from './pages/InterventionsPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import RiskDetailPage from './pages/RiskDetailPage.jsx'
import RiskPage from './pages/RiskPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import StudentProfilePage from './pages/StudentProfilePage.jsx'
import StudentsPage from './pages/StudentsPage.jsx'
import UsersPage from './pages/UsersPage.jsx'

function FullPageSpinner() {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-100" role="status">
      <div className="flex flex-col items-center gap-3 text-slate-500">
        <Spinner className="h-7 w-7" />
        <p className="text-sm">Restoring your session…</p>
      </div>
    </div>
  )
}

/** Requires a signed-in user, and optionally a set of permissions. */
function Protected({ permissions = [], children }) {
  const { status, isSignedIn, can, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <FullPageSpinner />
  if (!isSignedIn) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (permissions.length && !can(...permissions)) {
    // Signed in but not entitled to this page: send them somewhere they
    // can actually use rather than showing an empty screen.
    return <Navigate to={ROLE_HOME[user?.role] ?? '/dashboard'} replace />
  }
  return children
}

function RoleHomeRedirect() {
  const { status, isSignedIn, user } = useAuth()
  if (status === 'loading') return <FullPageSpinner />
  if (!isSignedIn) return <Navigate to="/login" replace />
  return <Navigate to={ROLE_HOME[user?.role] ?? '/dashboard'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RoleHomeRedirect />} />

      <Route
        element={
          <Protected>
            <AppLayout />
          </Protected>
        }
      >
        <Route
          path="/dashboard"
          element={
            <Protected permissions={['reports:read']}>
              <DashboardPage />
            </Protected>
          }
        />
        <Route
          path="/students"
          element={
            <Protected permissions={['students:read']}>
              <StudentsPage />
            </Protected>
          }
        />
        <Route
          path="/students/:studentPk"
          element={
            <Protected permissions={['students:read']}>
              <StudentProfilePage />
            </Protected>
          }
        />
        <Route
          path="/courses"
          element={
            <Protected permissions={['courses:read']}>
              <CoursesPage />
            </Protected>
          }
        />
        <Route
          path="/attendance"
          element={
            <Protected permissions={['attendance:read']}>
              <AttendancePage />
            </Protected>
          }
        />
        <Route
          path="/activity"
          element={
            <Protected permissions={['activity:read']}>
              <ActivityPage />
            </Protected>
          }
        />
        <Route
          path="/assessments"
          element={
            <Protected permissions={['assessments:read']}>
              <AssessmentsPage />
            </Protected>
          }
        />
        <Route
          path="/risk"
          element={
            <Protected permissions={['risk:read']}>
              <RiskPage />
            </Protected>
          }
        />
        <Route
          path="/risk/:enrollmentId"
          element={
            <Protected permissions={['risk:read']}>
              <RiskDetailPage />
            </Protected>
          }
        />
        <Route
          path="/alerts"
          element={
            <Protected permissions={['alerts:read']}>
              <AlertsPage />
            </Protected>
          }
        />
        <Route
          path="/interventions"
          element={
            <Protected permissions={['interventions:read']}>
              <InterventionsPage />
            </Protected>
          }
        />
        <Route
          path="/reports"
          element={
            <Protected permissions={['reports:read']}>
              <ReportsPage />
            </Protected>
          }
        />
        <Route
          path="/users"
          element={
            <Protected permissions={['users:read']}>
              <UsersPage />
            </Protected>
          }
        />
        <Route
          path="/settings"
          element={
            <Protected permissions={['settings:read']}>
              <SettingsPage />
            </Protected>
          }
        />
        <Route path="/account" element={<AccountPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
