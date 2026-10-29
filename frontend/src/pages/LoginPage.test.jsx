/** Sign-in: validation, the server's message, and role-based redirection. */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/endpoints.js', () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn(),
    permissions: vi.fn(),
  },
}))

import { renderPlain } from '../test/helpers.jsx'
import { authApi } from '../services/endpoints.js'
import { AuthProvider } from '../hooks/useAuth.jsx'
import LoginPage from './LoginPage.jsx'

function renderLogin() {
  return renderPlain(
    <AuthProvider>
      <LoginPage />
    </AuthProvider>,
    { route: '/login' },
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('LoginPage form validation', () => {
  it('renders the email and password fields', () => {
    renderLogin()
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('rejects an empty submission without calling the API', async () => {
    renderLogin()
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText('Email is required')).toBeInTheDocument()
    expect(screen.getByText('Password is required')).toBeInTheDocument()
    expect(authApi.login).not.toHaveBeenCalled()
  })

  it('rejects a malformed email without calling the API', async () => {
    renderLogin()
    await userEvent.type(screen.getByLabelText(/email address/i), 'not-an-email')
    await userEvent.type(screen.getByLabelText(/^password$/i), 'Demo@12345')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
    expect(authApi.login).not.toHaveBeenCalled()
  })

  it('marks an invalid field with aria-invalid', async () => {
    renderLogin()
    const email = screen.getByLabelText(/email address/i)
    await userEvent.type(email, 'bad')
    await userEvent.tab()
    await waitFor(() => expect(email).toHaveAttribute('aria-invalid', 'true'))
  })
})

describe('LoginPage authentication', () => {
  it('submits valid credentials and stores the token', async () => {
    authApi.login.mockResolvedValue({
      access_token: 'a-token',
      token_type: 'bearer',
      expires_in_minutes: 480,
      user: { user_id: 1, full_name: 'Anita Verma', email: 'admin@se-ewrs.edu', role: 'ADMIN', is_active: true },
      permissions: ['students:read'],
      home_route: '/dashboard',
    })

    renderLogin()
    await userEvent.type(screen.getByLabelText(/email address/i), 'admin@se-ewrs.edu')
    await userEvent.type(screen.getByLabelText(/^password$/i), 'Demo@12345')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(authApi.login).toHaveBeenCalledWith('admin@se-ewrs.edu', 'Demo@12345'),
    )
    await waitFor(() => expect(localStorage.getItem('se-ewrs.token')).toBe('a-token'))
  })

  it("shows the server's message verbatim when credentials are wrong", async () => {
    authApi.login.mockRejectedValue(new Error('Incorrect email or password'))

    renderLogin()
    await userEvent.type(screen.getByLabelText(/email address/i), 'admin@se-ewrs.edu')
    await userEvent.type(screen.getByLabelText(/^password$/i), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Incorrect email or password')
    expect(localStorage.getItem('se-ewrs.token')).toBeNull()
  })

  it('explains a throttled sign-in instead of calling it a wrong password', async () => {
    authApi.login.mockRejectedValue(
      new Error('Too many failed sign-in attempts. Try again in 15 minutes.'),
    )

    renderLogin()
    await userEvent.type(screen.getByLabelText(/email address/i), 'admin@se-ewrs.edu')
    await userEvent.type(screen.getByLabelText(/^password$/i), 'Demo@12345')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/try again in 15 minutes/i)
    expect(localStorage.getItem('se-ewrs.token')).toBeNull()
    // The form stays usable, so the user can retry once the wait is over.
    expect(screen.getByRole('button', { name: /sign in/i })).toBeEnabled()
  })

  it('surfaces an unreachable backend as an explanation, not a silent failure', async () => {
    authApi.login.mockRejectedValue(
      new Error('Could not reach the API. Check that the backend is running on port 8000.'),
    )

    renderLogin()
    await userEvent.type(screen.getByLabelText(/email address/i), 'admin@se-ewrs.edu')
    await userEvent.type(screen.getByLabelText(/^password$/i), 'Demo@12345')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the api/i)
  })
})

describe('LoginPage demo credentials', () => {
  it('lists one account per role', () => {
    renderLogin()
    expect(screen.getByText('Administrator')).toBeInTheDocument()
    expect(screen.getByText('Instructor')).toBeInTheDocument()
    expect(screen.getByText('Teaching Assistant')).toBeInTheDocument()
    expect(screen.getByText('Academic Advisor')).toBeInTheDocument()
    expect(screen.getByText('Department Chair')).toBeInTheDocument()
  })

  it('fills the form when a demo account is chosen', async () => {
    renderLogin()
    const buttons = screen.getAllByRole('button', { name: /^use$/i })
    await userEvent.click(buttons[0])

    expect(screen.getByLabelText(/email address/i)).toHaveValue('admin@se-ewrs.edu')
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('Demo@12345')
  })
})

describe('LoginPage password visibility', () => {
  it('toggles the password between hidden and visible', async () => {
    renderLogin()
    const password = screen.getByLabelText(/^password$/i)
    expect(password).toHaveAttribute('type', 'password')

    await userEvent.click(screen.getByRole('button', { name: /show password/i }))
    expect(password).toHaveAttribute('type', 'text')

    await userEvent.click(screen.getByRole('button', { name: /hide password/i }))
    expect(password).toHaveAttribute('type', 'password')
  })
})
