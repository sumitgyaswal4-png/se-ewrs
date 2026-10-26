/** Role-based navigation.
 *
 * The sidebar must show a role only what it can actually use. This is a
 * convenience - the API enforces the same map server-side - but a menu
 * full of entries that 403 would be worse than useless.
 */

import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/endpoints.js', () => ({
  authApi: { login: vi.fn(), me: vi.fn(), permissions: vi.fn() },
}))

import { renderPlain } from '../test/helpers.jsx'
import { NAV_SECTIONS, ROLE_HOME, ROLE_LABELS } from './navigation.js'

/** The permission sets the backend grants, mirrored from app/core/permissions.py. */
const READ_ONLY_CORE = [
  'students:read',
  'courses:read',
  'attendance:read',
  'activity:read',
  'assessments:read',
  'risk:read',
  'reports:read',
]

const ROLE_PERMISSIONS = {
  ADMIN: [
    ...READ_ONLY_CORE,
    'students:write', 'courses:write', 'enrollments:write', 'attendance:write',
    'activity:write', 'assessments:write', 'results:write', 'risk:recalculate',
    'alerts:read', 'alerts:write', 'interventions:read', 'interventions:write',
    'settings:read', 'settings:write', 'users:read', 'users:write', 'audit:read',
  ],
  INSTRUCTOR: [
    ...READ_ONLY_CORE,
    'attendance:write', 'assessments:write', 'results:write', 'risk:recalculate',
    'alerts:read', 'alerts:write', 'interventions:read', 'interventions:write',
    'enrollments:write',
  ],
  TA: [
    ...READ_ONLY_CORE,
    'attendance:write', 'activity:write', 'interventions:read', 'interventions:write',
  ],
  ADVISOR: [
    ...READ_ONLY_CORE,
    'alerts:read', 'alerts:write', 'interventions:read', 'interventions:write',
  ],
  CHAIR: [...READ_ONLY_CORE, 'alerts:read', 'interventions:read'],
}

/** Minimal stand-in for the sidebar's filtering logic. */
function Sidebar({ permissions }) {
  const granted = new Set(permissions)
  return (
    <nav aria-label="Main navigation">
      {NAV_SECTIONS.map((section) => {
        const visible = section.items.filter((item) =>
          item.permissions.every((permission) => granted.has(permission)),
        )
        if (!visible.length) return null
        return (
          <ul key={section.title}>
            {visible.map((item) => (
              <li key={item.to}>{item.label}</li>
            ))}
          </ul>
        )
      })}
    </nav>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('sidebar visibility per role', () => {
  it('shows an administrator everything', () => {
    renderPlain(<Sidebar permissions={ROLE_PERMISSIONS.ADMIN} />)
    const expected = NAV_SECTIONS.flatMap((section) => section.items.map((item) => item.label))
    for (const label of expected) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('hides staff accounts and settings from everyone but an administrator', () => {
    for (const role of ['INSTRUCTOR', 'TA', 'ADVISOR', 'CHAIR']) {
      const { unmount } = renderPlain(<Sidebar permissions={ROLE_PERMISSIONS[role]} />)
      expect(screen.queryByText('Staff accounts')).not.toBeInTheDocument()
      expect(screen.queryByText('Settings')).not.toBeInTheDocument()
      unmount()
    }
  })

  it('hides the alert queue from a teaching assistant', () => {
    renderPlain(<Sidebar permissions={ROLE_PERMISSIONS.TA} />)
    expect(screen.queryByText('Alerts')).not.toBeInTheDocument()
    // but a TA does record attendance and activity
    expect(screen.getByText('Attendance')).toBeInTheDocument()
    expect(screen.getByText('LMS activity')).toBeInTheDocument()
  })

  it('shows an advisor the alert queue and interventions', () => {
    renderPlain(<Sidebar permissions={ROLE_PERMISSIONS.ADVISOR} />)
    expect(screen.getByText('Alerts')).toBeInTheDocument()
    expect(screen.getByText('Interventions')).toBeInTheDocument()
    expect(screen.getByText('Risk analysis')).toBeInTheDocument()
  })

  it('shows a chair the oversight pages', () => {
    renderPlain(<Sidebar permissions={ROLE_PERMISSIONS.CHAIR} />)
    expect(screen.getByText('Reports')).toBeInTheDocument()
    expect(screen.getByText('Risk analysis')).toBeInTheDocument()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('shows nothing at all without permissions', () => {
    renderPlain(<Sidebar permissions={[]} />)
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })
})

describe('navigation definitions', () => {
  it('declares a permission for every entry', () => {
    for (const section of NAV_SECTIONS) {
      for (const item of section.items) {
        expect(item.permissions.length, `${item.label} must declare a permission`).toBeGreaterThan(0)
        expect(item.to.startsWith('/')).toBe(true)
        expect(item.icon).toBeTruthy()
      }
    }
  })

  it('gives every role a landing route it can reach', () => {
    for (const [role, home] of Object.entries(ROLE_HOME)) {
      const entry = NAV_SECTIONS.flatMap((section) => section.items).find(
        (item) => item.to === home,
      )
      expect(entry, `${role} lands on ${home}, which must be a real page`).toBeTruthy()
      const granted = new Set(ROLE_PERMISSIONS[role])
      expect(
        entry.permissions.every((permission) => granted.has(permission)),
        `${role} must be permitted to view its own landing route ${home}`,
      ).toBe(true)
    }
  })

  it('has a label for every role', () => {
    for (const role of Object.keys(ROLE_PERMISSIONS)) {
      expect(ROLE_LABELS[role]).toBeTruthy()
    }
  })
})
