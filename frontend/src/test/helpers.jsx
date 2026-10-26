/** Shared render helper: wraps a component in the router and providers. */

import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AuthProvider } from '../hooks/useAuth.jsx'
import { ToastProvider } from '../hooks/useToast.jsx'

export function renderWithProviders(ui, { route = '/' } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ToastProvider>
        <AuthProvider>{ui}</AuthProvider>
      </ToastProvider>
    </MemoryRouter>,
  )
}

export function renderPlain(ui, { route = '/' } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ToastProvider>{ui}</ToastProvider>
    </MemoryRouter>,
  )
}

export const ALL_PERMISSIONS = [
  'students:read',
  'students:write',
  'courses:read',
  'courses:write',
  'enrollments:write',
  'attendance:read',
  'attendance:write',
  'activity:read',
  'activity:write',
  'assessments:read',
  'assessments:write',
  'results:write',
  'risk:read',
  'risk:recalculate',
  'alerts:read',
  'alerts:write',
  'interventions:read',
  'interventions:write',
  'reports:read',
  'settings:read',
  'settings:write',
  'users:read',
  'users:write',
  'audit:read',
]
