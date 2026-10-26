/** The signed-in user's own account and password. */

import { useState } from 'react'
import { KeyRound, ShieldCheck } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { TextInput } from '../components/Form.jsx'
import { useMutation } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { ROLE_LABELS } from '../layouts/navigation.js'
import { authApi } from '../services/endpoints.js'
import { dateTime } from '../utils/format.js'

export default function AccountPage() {
  const { user, permissions } = useAuth()
  const toast = useToast()

  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [errors, setErrors] = useState({})

  const change = useMutation((payload) => authApi.changePassword(payload))

  function validate() {
    const problems = {}
    if (!form.current) problems.current = 'Enter your current password'
    if (form.next.length < 8) problems.next = 'At least 8 characters'
    if (form.next !== form.confirm) problems.confirm = 'The two passwords do not match'
    if (form.next && form.next === form.current) {
      problems.next = 'The new password must differ from the current one'
    }
    setErrors(problems)
    return Object.keys(problems).length === 0
  }

  async function onSubmit(event) {
    event.preventDefault()
    if (!validate()) return
    try {
      await change.run({ current_password: form.current, new_password: form.next })
      toast.success('Password updated')
      setForm({ current: '', next: '', confirm: '' })
    } catch (error) {
      toast.error(error.message)
      setErrors({ current: error.status === 401 ? error.message : undefined })
    }
  }

  return (
    <>
      <PageHeader title="Account" description="Your profile and sign-in credentials." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Profile">
          <dl className="divide-y divide-slate-100">
            {[
              ['Name', user?.full_name],
              ['Email', user?.email],
              ['Role', ROLE_LABELS[user?.role] ?? user?.role],
              ['Phone', user?.phone ?? '—'],
              ['Last sign-in', user?.last_login_at ? dateTime(user.last_login_at) : '—'],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 px-5 py-3">
                <dt className="text-sm text-slate-500">{label}</dt>
                <dd className="text-sm font-medium text-slate-800">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card
          title="Change password"
          description="Stored as an Argon2id digest — the plaintext is never written anywhere."
        >
          <form onSubmit={onSubmit} noValidate className="space-y-4 p-5">
            <TextInput
              label="Current password"
              type="password"
              autoComplete="current-password"
              required
              value={form.current}
              onChange={(event) => setForm({ ...form, current: event.target.value })}
              error={errors.current}
            />
            <TextInput
              label="New password"
              type="password"
              autoComplete="new-password"
              required
              value={form.next}
              onChange={(event) => setForm({ ...form, next: event.target.value })}
              error={errors.next}
              hint="At least 8 characters"
            />
            <TextInput
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              required
              value={form.confirm}
              onChange={(event) => setForm({ ...form, confirm: event.target.value })}
              error={errors.confirm}
            />
            <button type="submit" className="btn-primary" disabled={change.pending}>
              <KeyRound className="h-4 w-4" aria-hidden="true" />
              {change.pending ? 'Updating…' : 'Update password'}
            </button>
          </form>
        </Card>
      </div>

      <Card
        title="Your permissions"
        description="Granted by your role. Every endpoint checks these server-side."
        className="mt-4"
        actions={
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            {permissions.length} granted
          </span>
        }
      >
        <div className="flex flex-wrap gap-1.5 p-5">
          {permissions.map((permission) => (
            <Badge key={permission} tone={permission.endsWith(':write') ? 'brand' : 'neutral'}>
              <code className="font-mono text-[11px]">{permission}</code>
            </Badge>
          ))}
        </div>
      </Card>
    </>
  )
}
