/** The sidebar definition.
 *
 * Each entry lists the permissions it needs. The sidebar renders an entry
 * only when the signed-in role holds them - which is exactly the map the
 * API enforces, fetched from `GET /api/auth/permissions`. This is a
 * convenience, not a control: the server still refuses the call.
 */

import {
  Activity,
  BellRing,
  BookOpen,
  CalendarCheck,
  ClipboardList,
  FileBarChart,
  GraduationCap,
  LayoutDashboard,
  LifeBuoy,
  Settings,
  ShieldAlert,
  Users,
} from 'lucide-react'

export const NAV_SECTIONS = [
  {
    title: 'Overview',
    items: [
      {
        to: '/dashboard',
        label: 'Dashboard',
        icon: LayoutDashboard,
        permissions: ['reports:read'],
      },
    ],
  },
  {
    title: 'Academic records',
    items: [
      { to: '/students', label: 'Students', icon: GraduationCap, permissions: ['students:read'] },
      { to: '/courses', label: 'Courses', icon: BookOpen, permissions: ['courses:read'] },
      {
        to: '/attendance',
        label: 'Attendance',
        icon: CalendarCheck,
        permissions: ['attendance:read'],
      },
      { to: '/activity', label: 'LMS activity', icon: Activity, permissions: ['activity:read'] },
      {
        to: '/assessments',
        label: 'Assessments',
        icon: ClipboardList,
        permissions: ['assessments:read'],
      },
    ],
  },
  {
    title: 'Early warning',
    items: [
      { to: '/risk', label: 'Risk analysis', icon: ShieldAlert, permissions: ['risk:read'] },
      { to: '/alerts', label: 'Alerts', icon: BellRing, permissions: ['alerts:read'] },
      {
        to: '/interventions',
        label: 'Interventions',
        icon: LifeBuoy,
        permissions: ['interventions:read'],
      },
    ],
  },
  {
    title: 'Administration',
    items: [
      { to: '/reports', label: 'Reports', icon: FileBarChart, permissions: ['reports:read'] },
      { to: '/users', label: 'Staff accounts', icon: Users, permissions: ['users:read'] },
      { to: '/settings', label: 'Settings', icon: Settings, permissions: ['settings:read'] },
    ],
  },
]

export const ROLE_LABELS = {
  ADMIN: 'Administrator',
  INSTRUCTOR: 'Instructor',
  TA: 'Teaching Assistant',
  ADVISOR: 'Academic Advisor',
  CHAIR: 'Department Chair',
}

/** Where each role lands after signing in; mirrors HOME_ROUTES server-side. */
export const ROLE_HOME = {
  ADMIN: '/dashboard',
  INSTRUCTOR: '/dashboard',
  TA: '/attendance',
  ADVISOR: '/alerts',
  CHAIR: '/reports',
}
