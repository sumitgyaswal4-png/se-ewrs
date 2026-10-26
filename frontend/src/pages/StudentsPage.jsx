/** Student management: list, search, filter, create, edit, deactivate. */

import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { GraduationCap, Plus, UserCheck, UserX } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal, { ConfirmDialog } from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import SearchInput from '../components/SearchInput.jsx'
import { FilterSelect, SelectInput, TextInput } from '../components/Form.jsx'
import { useDebounced, useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { lookupApi, studentApi } from '../services/endpoints.js'
import { SEMESTERS } from '../utils/constants.js'
import { percent, relativeDays } from '../utils/format.js'

const EMPTY_FORM = {
  student_id: '',
  full_name: '',
  email: '',
  dept_id: '',
  semester: '',
  enrollment_year: String(new Date().getFullYear()),
  phone: '',
}

export default function StudentsPage() {
  const { can } = useAuth()
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [deptId, setDeptId] = useState(searchParams.get('dept_id'))
  const [semester, setSemester] = useState(searchParams.get('semester'))
  const [riskCategory, setRiskCategory] = useState(searchParams.get('risk_category'))
  const [activeFilter, setActiveFilter] = useState('true')
  const [sortBy, setSortBy] = useState('student_id')
  const [sortDir, setSortDir] = useState('asc')

  const [editing, setEditing] = useState(null) // null | 'new' | student object
  const [form, setForm] = useState(EMPTY_FORM)
  const [formErrors, setFormErrors] = useState({})
  const [deactivating, setDeactivating] = useState(null)

  const departments = useQuery(() => lookupApi.departments(), [])

  const params = useMemo(
    () => ({
      page,
      page_size: pageSize,
      search: debouncedSearch || undefined,
      dept_id: deptId || undefined,
      semester: semester || undefined,
      risk_category: riskCategory || undefined,
      is_active: activeFilter === '' ? undefined : activeFilter === 'true',
      sort_by: sortBy,
      sort_dir: sortDir,
    }),
    [page, pageSize, debouncedSearch, deptId, semester, riskCategory, activeFilter, sortBy, sortDir],
  )

  const students = useQuery(() => studentApi.list(params), [JSON.stringify(params)])

  const save = useMutation((payload) =>
    editing === 'new'
      ? studentApi.create(payload)
      : studentApi.update(editing.student_pk, payload),
  )
  const toggleActive = useMutation(({ pk, active }) =>
    active ? studentApi.reactivate(pk) : studentApi.deactivate(pk),
  )

  function openNew() {
    setForm({ ...EMPTY_FORM, dept_id: departments.data?.[0]?.dept_id ?? '' })
    setFormErrors({})
    setEditing('new')
  }

  function openEdit(student) {
    setForm({
      student_id: student.student_id,
      full_name: student.full_name,
      email: student.email,
      dept_id: String(student.dept_id),
      semester: String(student.semester),
      enrollment_year: String(student.enrollment_year),
      phone: student.phone ?? '',
    })
    setFormErrors({})
    setEditing(student)
  }

  function validate() {
    const errors = {}
    if (editing === 'new' && form.student_id.trim().length < 3) {
      errors.student_id = 'Roll number must be at least 3 characters'
    }
    if (form.full_name.trim().length < 2) errors.full_name = 'Enter the full name'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errors.email = 'Enter a valid email'
    if (!form.dept_id) errors.dept_id = 'Choose a department'
    if (!form.semester) errors.semester = 'Choose a semester'
    const year = Number(form.enrollment_year)
    if (!year || year < 2000 || year > 2100) errors.enrollment_year = 'Year must be 2000-2100'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function onSubmit(event) {
    event.preventDefault()
    if (!validate()) return

    const payload = {
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      dept_id: Number(form.dept_id),
      semester: Number(form.semester),
      enrollment_year: Number(form.enrollment_year),
      phone: form.phone.trim() || null,
    }
    if (editing === 'new') payload.student_id = form.student_id.trim()

    try {
      await save.run(payload)
      toast.success(
        editing === 'new' ? 'Student added' : `${form.full_name} updated`,
      )
      setEditing(null)
      students.reload()
    } catch (error) {
      toast.error(error.message)
      if (error.problems?.length) {
        setFormErrors(
          Object.fromEntries(error.problems.map((problem) => [problem.field, problem.message])),
        )
      }
    }
  }

  async function onToggleActive(student) {
    try {
      const result = await toggleActive.run({
        pk: student.student_pk,
        active: !student.is_active,
      })
      toast.success(result.detail)
      setDeactivating(null)
      students.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  function onSort(column, direction) {
    setSortBy(column)
    setSortDir(direction)
    setPage(1)
  }

  function updateFilter(setter, key) {
    return (value) => {
      setter(value)
      setPage(1)
      const next = new URLSearchParams(searchParams)
      if (value) next.set(key, value)
      else next.delete(key)
      setSearchParams(next, { replace: true })
    }
  }

  const departmentOptions = (departments.data ?? []).map((dept) => ({
    value: String(dept.dept_id),
    label: `${dept.dept_code} — ${dept.dept_name}`,
  }))

  const columns = [
    {
      key: 'student',
      header: 'Student',
      sortKey: 'full_name',
      render: (row) => (
        <Link to={`/students/${row.student_pk}`} className="group block min-w-0">
          <span className="block font-semibold text-slate-800 group-hover:text-brand-700">
            {row.full_name}
          </span>
          <span className="block font-mono text-xs text-slate-500">{row.student_id}</span>
        </Link>
      ),
    },
    {
      key: 'dept',
      header: 'Dept / Sem',
      sortKey: 'semester',
      render: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral">{row.dept_code}</Badge>
          <span className="text-xs text-slate-500">Sem {row.semester}</span>
        </div>
      ),
    },
    {
      key: 'courses',
      header: 'Courses',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">{row.summary.enrolled_courses}</span>
      ),
    },
    {
      key: 'attendance',
      header: 'Attendance',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">{percent(row.summary.attendance_percentage, 0)}</span>
      ),
    },
    {
      key: 'assessment',
      header: 'Assessment',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">
          {percent(row.summary.avg_assessment_percentage, 0)}
        </span>
      ),
    },
    {
      key: 'risk',
      header: 'Highest risk',
      render: (row) =>
        row.summary.highest_risk_category ? (
          <RiskBadge
            category={row.summary.highest_risk_category}
            score={row.summary.highest_risk_score}
            size="sm"
          />
        ) : (
          <span className="text-xs text-slate-400">not scored</span>
        ),
    },
    {
      key: 'activity',
      header: 'Last seen',
      render: (row) => (
        <span className="text-xs text-slate-500">
          {relativeDays(row.summary.last_activity_at)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) =>
        row.is_active ? (
          <Badge tone="success">Active</Badge>
        ) : (
          <Badge tone="neutral">Inactive</Badge>
        ),
    },
    ...(can('students:write')
      ? [
          {
            key: 'actions',
            header: 'Actions',
            align: 'right',
            render: (row) => (
              <div className="flex justify-end gap-1">
                <button
                  type="button"
                  onClick={() => openEdit(row)}
                  className="btn-ghost px-2 py-1 text-xs"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() =>
                    row.is_active ? setDeactivating(row) : onToggleActive(row)
                  }
                  className="btn-ghost px-2 py-1 text-xs"
                  title={row.is_active ? 'Deactivate' : 'Reactivate'}
                >
                  {row.is_active ? (
                    <UserX className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <UserCheck className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  <span className="sr-only">
                    {row.is_active ? 'Deactivate' : 'Reactivate'} {row.full_name}
                  </span>
                </button>
              </div>
            ),
          },
        ]
      : []),
  ]

  return (
    <>
      <PageHeader
        title="Students"
        description="Student records with their academic and engagement summary."
        actions={
          can('students:write') && (
            <button type="button" onClick={openNew} className="btn-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add student
            </button>
          )
        }
      />

      <Card bodyClassName="p-0">
        {/* Filters in one row above the table */}
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Roll number, name or email"
            label="Search students"
            className="min-w-[14rem] flex-1"
          />
          <FilterSelect
            label="Department"
            value={deptId}
            onChange={updateFilter(setDeptId, 'dept_id')}
            options={departmentOptions}
          />
          <FilterSelect
            label="Semester"
            value={semester}
            onChange={updateFilter(setSemester, 'semester')}
            options={SEMESTERS.map((value) => ({ value: String(value), label: `Sem ${value}` }))}
          />
          <FilterSelect
            label="Risk band"
            value={riskCategory}
            onChange={updateFilter(setRiskCategory, 'risk_category')}
            options={[
              { value: 'HIGH', label: 'High risk' },
              { value: 'MEDIUM', label: 'Medium risk' },
              { value: 'LOW', label: 'Low risk' },
            ]}
          />
          <FilterSelect
            label="Status"
            value={activeFilter}
            onChange={(value) => {
              setActiveFilter(value ?? '')
              setPage(1)
            }}
            options={[
              { value: 'true', label: 'Active' },
              { value: 'false', label: 'Inactive' },
            ]}
            placeholder="All"
          />
        </div>

        <DataTable
          columns={columns}
          rows={students.data?.items}
          rowKey={(row) => row.student_pk}
          loading={students.loading}
          error={students.error}
          onRetry={students.reload}
          sortBy={sortBy}
          sortDir={sortDir}
          onSort={onSort}
          caption="Students with their engagement summary"
          emptyTitle="No students match these filters"
          emptyDescription={
            search || deptId || semester || riskCategory
              ? 'Try clearing a filter or searching for something else.'
              : 'Add a student record to get started.'
          }
          emptyAction={
            can('students:write') && (
              <button type="button" onClick={openNew} className="btn-primary">
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add student
              </button>
            )
          }
        />

        {students.data?.total > 0 && (
          <div className="border-t border-slate-200 px-4 py-3">
            <Pagination
              page={students.data.page}
              pageSize={students.data.page_size}
              total={students.data.total}
              pages={students.data.pages}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
            />
          </div>
        )}
      </Card>

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'Add a student' : `Edit ${editing?.full_name ?? ''}`}
        description={
          editing === 'new'
            ? 'The roll number must be unique and cannot be changed afterwards.'
            : undefined
        }
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" form="student-form" className="btn-primary" disabled={save.pending}>
              {save.pending ? 'Saving…' : 'Save student'}
            </button>
          </>
        }
      >
        <form id="student-form" onSubmit={onSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
          {editing === 'new' && (
            <TextInput
              label="Roll number"
              required
              value={form.student_id}
              onChange={(event) => setForm({ ...form, student_id: event.target.value })}
              error={formErrors.student_id}
              hint="e.g. MTH2024001"
              placeholder="MTH2024001"
            />
          )}
          <TextInput
            label="Full name"
            required
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            error={formErrors.full_name}
            className={editing === 'new' ? undefined : 'sm:col-span-2'}
          />
          <TextInput
            label="Email"
            type="email"
            required
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            error={formErrors.email}
            className="sm:col-span-2"
          />
          <SelectInput
            label="Department"
            required
            value={form.dept_id}
            onChange={(event) => setForm({ ...form, dept_id: event.target.value })}
            options={departmentOptions}
            placeholder="Select a department"
            error={formErrors.dept_id}
          />
          <SelectInput
            label="Semester"
            required
            value={form.semester}
            onChange={(event) => setForm({ ...form, semester: event.target.value })}
            options={SEMESTERS.map((value) => ({ value: String(value), label: `Semester ${value}` }))}
            placeholder="Select a semester"
            error={formErrors.semester}
          />
          <TextInput
            label="Enrolment year"
            type="number"
            required
            min={2000}
            max={2100}
            value={form.enrollment_year}
            onChange={(event) => setForm({ ...form, enrollment_year: event.target.value })}
            error={formErrors.enrollment_year}
          />
          <TextInput
            label="Phone"
            value={form.phone}
            onChange={(event) => setForm({ ...form, phone: event.target.value })}
            hint="Optional"
          />
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deactivating)}
        onClose={() => setDeactivating(null)}
        onConfirm={() => onToggleActive(deactivating)}
        pending={toggleActive.pending}
        destructive
        title="Deactivate this student?"
        confirmLabel="Deactivate"
        message={
          deactivating
            ? `${deactivating.full_name} (${deactivating.student_id}) will be removed from active rosters and dashboard counts. Their attendance, grades, risk history and interventions are all kept — this is a soft delete and can be undone.`
            : ''
        }
      />
    </>
  )
}
