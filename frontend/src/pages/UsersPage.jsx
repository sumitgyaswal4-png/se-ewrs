/** Staff account administration. */

import { useMemo, useState } from 'react'
import { Plus, UserCog } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import SearchInput from '../components/SearchInput.jsx'
import { FilterSelect, SelectInput, TextInput } from '../components/Form.jsx'
import { useDebounced, useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { authApi, lookupApi } from '../services/endpoints.js'
import { ROLE_LABELS } from '../layouts/navigation.js'
import { dateTime, relativeDays } from '../utils/format.js'

const ROLE_TONE = {
  ADMIN: 'danger',
  INSTRUCTOR: 'brand',
  TA: 'neutral',
  ADVISOR: 'warning',
  CHAIR: 'success',
}

const EMPTY = { full_name: '', email: '', password: '', role: 'INSTRUCTOR', dept_id: '', phone: '' }

export default function UsersPage() {
  const { can, user: me } = useAuth()
  const toast = useToast()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(1)
  const [role, setRole] = useState(null)
  const [activeFilter, setActiveFilter] = useState(null)

  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [formErrors, setFormErrors] = useState({})

  const departments = useQuery(() => lookupApi.departments(), [])

  const params = useMemo(
    () => ({
      page,
      page_size: 20,
      search: debouncedSearch || undefined,
      role: role || undefined,
      is_active: activeFilter === null ? undefined : activeFilter === 'true',
    }),
    [page, debouncedSearch, role, activeFilter],
  )
  const users = useQuery(() => authApi.listUsers(params), [JSON.stringify(params)])

  const save = useMutation((payload) =>
    editing === 'new' ? authApi.createUser(payload) : authApi.updateUser(editing.user_id, payload),
  )

  function openNew() {
    setForm({ ...EMPTY, dept_id: departments.data?.[0]?.dept_id ?? '' })
    setFormErrors({})
    setEditing('new')
  }

  function openEdit(row) {
    setForm({
      full_name: row.full_name,
      email: row.email,
      password: '',
      role: row.role,
      dept_id: row.dept_id ? String(row.dept_id) : '',
      phone: row.phone ?? '',
      is_active: row.is_active,
    })
    setFormErrors({})
    setEditing(row)
  }

  function validate() {
    const errors = {}
    if (form.full_name.trim().length < 2) errors.full_name = 'Enter the full name'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errors.email = 'Enter a valid email'
    if (editing === 'new' && form.password.length < 8) {
      errors.password = 'At least 8 characters'
    }
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function onSubmit(event) {
    event.preventDefault()
    if (!validate()) return

    const payload = {
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      role: form.role,
      dept_id: form.dept_id ? Number(form.dept_id) : null,
      phone: form.phone.trim() || null,
    }
    if (editing === 'new') {
      payload.password = form.password
    } else {
      payload.is_active = form.is_active
    }

    try {
      await save.run(payload)
      toast.success(editing === 'new' ? 'Account created' : 'Account updated')
      setEditing(null)
      users.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const columns = [
    {
      key: 'user',
      header: 'Name',
      render: (row) => (
        <div className="min-w-0">
          <span className="block font-semibold text-slate-800">
            {row.full_name}
            {row.user_id === me?.user_id && (
              <span className="ml-1.5 text-xs font-normal text-slate-400">(you)</span>
            )}
          </span>
          <span className="block truncate text-xs text-slate-500">{row.email}</span>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      render: (row) => <Badge tone={ROLE_TONE[row.role]}>{ROLE_LABELS[row.role] ?? row.role}</Badge>,
    },
    {
      key: 'dept',
      header: 'Department',
      render: (row) => {
        const dept = (departments.data ?? []).find((item) => item.dept_id === row.dept_id)
        return dept ? (
          <Badge tone="neutral">{dept.dept_code}</Badge>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )
      },
    },
    {
      key: 'phone',
      header: 'Phone',
      render: (row) => <span className="text-xs text-slate-600">{row.phone ?? '—'}</span>,
    },
    {
      key: 'last_login',
      header: 'Last sign-in',
      render: (row) => (
        <div>
          <span className="block text-xs text-slate-600">
            {row.last_login_at ? relativeDays(row.last_login_at) : 'never'}
          </span>
          {row.last_login_at && (
            <span className="block text-xs text-slate-400">{dateTime(row.last_login_at)}</span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) =>
        row.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="neutral">Disabled</Badge>,
    },
    ...(can('users:write')
      ? [
          {
            key: 'actions',
            header: '',
            align: 'right',
            render: (row) => (
              <button
                type="button"
                onClick={() => openEdit(row)}
                className="btn-ghost px-2 py-1 text-xs"
              >
                <UserCog className="h-3.5 w-3.5" aria-hidden="true" />
                Edit
              </button>
            ),
          },
        ]
      : []),
  ]

  return (
    <>
      <PageHeader
        title="Staff accounts"
        description="Roles decide what each person can see and do. The API enforces this server-side on every request."
        actions={
          can('users:write') && (
            <button type="button" onClick={openNew} className="btn-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add account
            </button>
          )
        }
      />

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Name or email"
            label="Search accounts"
            className="min-w-[13rem] flex-1"
          />
          <FilterSelect
            label="Role"
            value={role}
            onChange={(value) => {
              setRole(value)
              setPage(1)
            }}
            options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <FilterSelect
            label="Status"
            value={activeFilter}
            onChange={(value) => {
              setActiveFilter(value)
              setPage(1)
            }}
            options={[
              { value: 'true', label: 'Active' },
              { value: 'false', label: 'Disabled' },
            ]}
          />
        </div>

        <DataTable
          columns={columns}
          rows={users.data?.items}
          rowKey={(row) => row.user_id}
          loading={users.loading}
          error={users.error}
          onRetry={users.reload}
          caption="Staff accounts"
          emptyTitle="No accounts match these filters"
        />

        {users.data?.total > 0 && (
          <div className="border-t border-slate-200 px-4 py-3">
            <Pagination
              page={users.data.page}
              pageSize={users.data.page_size}
              total={users.data.total}
              pages={users.data.pages}
              onPageChange={setPage}
            />
          </div>
        )}
      </Card>

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'Add a staff account' : `Edit ${editing?.full_name ?? ''}`}
        description={
          editing === 'new'
            ? 'The password is hashed with Argon2id before it is stored and is never returned by the API.'
            : undefined
        }
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" form="user-form" className="btn-primary" disabled={save.pending}>
              {save.pending ? 'Saving…' : 'Save account'}
            </button>
          </>
        }
      >
        <form id="user-form" onSubmit={onSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
          <TextInput
            label="Full name"
            required
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            error={formErrors.full_name}
          />
          <TextInput
            label="Email"
            type="email"
            required
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            error={formErrors.email}
          />
          {editing === 'new' && (
            <TextInput
              label="Password"
              type="password"
              required
              autoComplete="new-password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              error={formErrors.password}
              hint="At least 8 characters"
              className="sm:col-span-2"
            />
          )}
          <SelectInput
            label="Role"
            required
            value={form.role}
            onChange={(event) => setForm({ ...form, role: event.target.value })}
            options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <SelectInput
            label="Department"
            value={form.dept_id}
            onChange={(event) => setForm({ ...form, dept_id: event.target.value })}
            options={(departments.data ?? []).map((dept) => ({
              value: String(dept.dept_id),
              label: `${dept.dept_code} — ${dept.dept_name}`,
            }))}
            placeholder="No department"
          />
          <TextInput
            label="Phone"
            value={form.phone}
            onChange={(event) => setForm({ ...form, phone: event.target.value })}
            hint="Optional"
          />
          {editing !== 'new' && (
            <div className="flex items-end">
              <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={form.is_active ?? true}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                  disabled={editing?.user_id === me?.user_id}
                  className="h-4 w-4 rounded border-slate-300 text-brand-600"
                />
                Account is active
                {editing?.user_id === me?.user_id && (
                  <span className="text-xs text-slate-400">(cannot disable your own)</span>
                )}
              </label>
            </div>
          )}
        </form>
      </Modal>
    </>
  )
}
