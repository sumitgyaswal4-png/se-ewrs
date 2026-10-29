/** Sign-in.
 *
 * Validation runs client-side for immediate feedback, but the server is
 * the authority: it returns one deliberately generic message for both an
 * unknown email and a wrong password, and that message is shown verbatim.
 * After a successful sign-in the user is sent to the landing route the
 * server chose for their role.
 */

import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff, Loader2, LogIn, ShieldAlert } from 'lucide-react'

import { useAuth } from '../hooks/useAuth.jsx'
import { ROLE_HOME } from '../layouts/navigation.js'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const DEMO_ACCOUNTS = [
  { role: 'Administrator', email: 'admin@se-ewrs.edu' },
  { role: 'Instructor', email: 'rohit.khanna@se-ewrs.edu' },
  { role: 'Teaching Assistant', email: 'tanvi.nair@se-ewrs.edu' },
  { role: 'Academic Advisor', email: 'priya.menon@se-ewrs.edu' },
  { role: 'Department Chair', email: 'latika.rao@se-ewrs.edu' },
]
const DEMO_PASSWORD = 'Demo@12345'

/** Whether to list the seeded demo accounts and their shared password.
 *
 * On in development, off in a production build, where those accounts
 * should not exist. Set VITE_SHOW_DEMO_ACCOUNTS=true at build time for a
 * deliberate demo site, or =false to hide it in development. Vite replaces
 * these values when it builds, so a production bundle without the flag
 * does not contain the password at all.
 */
function demoAccountsEnabled() {
  return (
    import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === 'true' ||
    (import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS !== 'false')
  )
}

export default function LoginPage() {
  const { signIn, isSignedIn, user, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [form, setForm] = useState({ email: '', password: '' })
  const [touched, setTouched] = useState({})
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState(null)

  if (isSignedIn) {
    const target = location.state?.from ?? ROLE_HOME[user?.role] ?? '/dashboard'
    return <Navigate to={target} replace />
  }

  const errors = {
    email: !form.email
      ? 'Email is required'
      : !EMAIL_PATTERN.test(form.email)
        ? 'Enter a valid email address'
        : null,
    password: !form.password ? 'Password is required' : null,
  }
  const isValid = !errors.email && !errors.password

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    setServerError(null)
  }

  async function onSubmit(event) {
    event.preventDefault()
    setTouched({ email: true, password: true })
    if (!isValid) return

    setSubmitting(true)
    setServerError(null)
    try {
      const result = await signIn(form.email.trim(), form.password)
      navigate(location.state?.from ?? result.home_route ?? '/dashboard', { replace: true })
    } catch (error) {
      setServerError(error.message)
    } finally {
      setSubmitting(false)
    }
  }

  function fillDemoAccount(email) {
    setForm({ email, password: DEMO_PASSWORD })
    setTouched({})
    setServerError(null)
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* Brand panel */}
      <div className="flex flex-col justify-between bg-brand-900 px-6 py-8 text-white lg:w-[46%] lg:px-12 lg:py-14">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600">
            <ShieldAlert className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="font-bold leading-tight">SE-EWRS</p>
            <p className="text-xs leading-tight text-brand-200">Early Warning Risk System</p>
          </div>
        </div>

        <div className="my-10 max-w-lg lg:my-0">
          <h1 className="text-2xl font-bold leading-snug lg:text-3xl">
            Student Engagement &amp; Early Warning Risk System
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-brand-100">
            Attendance, LMS engagement and assessment data are aggregated into a
            transparent risk score, so a student who is slipping can be reached
            before their results show it.
          </p>
          <dl className="mt-8 grid grid-cols-3 gap-4 border-t border-white/15 pt-6 text-center">
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-brand-300">Attendance</dt>
              <dd className="mt-1 text-lg font-bold">35%</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-brand-300">Academic</dt>
              <dd className="mt-1 text-lg font-bold">40%</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-brand-300">Engagement</dt>
              <dd className="mt-1 text-lg font-bold">25%</dd>
            </div>
          </dl>
        </div>

        <p className="text-xs text-brand-300">
          DBMS course project · Department of Mathematics
          <br />
          Mohammad Adnan · Lucky Dhall · Raja · Sumit
        </p>
      </div>

      {/* Sign-in form */}
      <div className="flex flex-1 items-center justify-center bg-slate-100 px-4 py-10 sm:px-6">
        <div className="w-full max-w-md">
          <div className="card p-6 sm:p-8">
            <h2 className="text-lg font-bold text-slate-900">Sign in</h2>
            <p className="mt-1 text-sm text-slate-600">
              Use your institutional staff account.
            </p>

            {sessionExpired && (
              <div
                role="status"
                className="mt-4 flex items-start gap-2 rounded-lg border border-risk-medium/40 bg-risk-medium/10 px-3 py-2.5 text-sm text-[#875c00]"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>Your session expired. Please sign in again.</span>
              </div>
            )}

            {serverError && (
              <div
                role="alert"
                className="mt-4 flex items-start gap-2 rounded-lg border border-risk-high/40 bg-risk-high/5 px-3 py-2.5 text-sm text-[#9c2525]"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{serverError}</span>
              </div>
            )}

            <form onSubmit={onSubmit} noValidate className="mt-5 space-y-4">
              <div>
                <label htmlFor="email" className="label">
                  Email address
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  value={form.email}
                  onChange={(event) => update('email', event.target.value)}
                  onBlur={() => setTouched((t) => ({ ...t, email: true }))}
                  aria-invalid={touched.email && errors.email ? true : undefined}
                  aria-describedby={touched.email && errors.email ? 'email-error' : undefined}
                  className="input"
                  placeholder="you@se-ewrs.edu"
                />
                {touched.email && errors.email && (
                  <p id="email-error" className="mt-1 text-xs font-medium text-risk-high">
                    {errors.email}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="password" className="label">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={form.password}
                    onChange={(event) => update('password', event.target.value)}
                    onBlur={() => setTouched((t) => ({ ...t, password: true }))}
                    aria-invalid={touched.password && errors.password ? true : undefined}
                    aria-describedby={
                      touched.password && errors.password ? 'password-error' : undefined
                    }
                    className="input pr-10"
                    placeholder="Your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <Eye className="h-4 w-4" aria-hidden="true" />
                    )}
                  </button>
                </div>
                {touched.password && errors.password && (
                  <p id="password-error" className="mt-1 text-xs font-medium text-risk-high">
                    {errors.password}
                  </p>
                )}
              </div>

              <button type="submit" className="btn-primary w-full" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    Signing in…
                  </>
                ) : (
                  <>
                    <LogIn className="h-4 w-4" aria-hidden="true" />
                    Sign in
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Demo credentials, documented in the README. */}
          {demoAccountsEnabled() && (
            <div className="card mt-4 p-5">
              <p className="text-sm font-semibold text-slate-800">Demo accounts</p>
              <p className="mt-0.5 text-xs text-slate-500">
                Seeded by <code className="font-mono">database/seed.sql</code>. Every account uses
                the password{' '}
                <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-slate-700">
                  {DEMO_PASSWORD}
                </code>
                .
              </p>
              <ul className="mt-3 divide-y divide-slate-100">
                {DEMO_ACCOUNTS.map((account) => (
                  <li key={account.email} className="flex items-center justify-between gap-3 py-1.5">
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold text-slate-700">
                        {account.role}
                      </span>
                      <span className="block truncate font-mono text-[11px] text-slate-500">
                        {account.email}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => fillDemoAccount(account.email)}
                      className="btn-ghost shrink-0 px-2 py-1 text-xs"
                    >
                      Use
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
