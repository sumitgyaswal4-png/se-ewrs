/** Intervention tracking: record contact, plan, follow-up and outcome. */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { LifeBuoy, Plus } from 'lucide-react'

import Badge, { OUTCOME_TONE } from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import SearchInput from '../components/SearchInput.jsx'
import { FilterDate, FilterSelect, SelectInput, TextArea } from '../components/Form.jsx'
import { useDebounced, useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { courseApi, interventionApi, lookupApi } from '../services/endpoints.js'
import { dateOnly, humanise, relativeDays } from '../utils/format.js'

const today = () => new Date().toISOString().slice(0, 10)

const EMPTY = {
  course_pk: '',
  enrollment_id: '',
  intervention_type: 'COUNSELING',
  contact_date: today(),
  notes: '',
  action_plan: '',
  follow_up_date: '',
  outcome: 'PENDING',
  resolution_status: 'OPEN',
}

export default function InterventionsPage() {
  const { can } = useAuth()
  const toast = useToast()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(1)
  const [coursePk, setCoursePk] = useState(null)
  const [type, setType] = useState(null)
  const [outcome, setOutcome] = useState(null)
  const [resolution, setResolution] = useState(null)
  const [dateFrom, setDateFrom] = useState(null)
  const [followUpDue, setFollowUpDue] = useState(false)

  const [editing, setEditing] = useState(null) // null | 'new' | row
  const [form, setForm] = useState(EMPTY)

  const courses = useQuery(() => lookupApi.courseOptions(), [])
  const enums = useQuery(() => lookupApi.enums(), [])
  const roster = useQuery(() => courseApi.roster(form.course_pk), [form.course_pk], {
    enabled: editing === 'new' && Boolean(form.course_pk),
  })

  const params = useMemo(
    () => ({
      page,
      page_size: 20,
      search: debouncedSearch || undefined,
      course_pk: coursePk || undefined,
      intervention_type: type || undefined,
      outcome: outcome || undefined,
      resolution_status: resolution || undefined,
      date_from: dateFrom || undefined,
      follow_up_due: followUpDue || undefined,
    }),
    [page, debouncedSearch, coursePk, type, outcome, resolution, dateFrom, followUpDue],
  )
  const rows = useQuery(() => interventionApi.list(params), [JSON.stringify(params)])

  const save = useMutation((payload) =>
    editing === 'new'
      ? interventionApi.create(payload)
      : interventionApi.update(editing.intervention_id, payload),
  )

  function openNew() {
    setForm(EMPTY)
    setEditing('new')
  }

  function openEdit(row) {
    setForm({
      course_pk: String(row.course_pk ?? ''),
      enrollment_id: String(row.enrollment_id),
      intervention_type: row.intervention_type,
      contact_date: row.contact_date,
      notes: row.notes ?? '',
      action_plan: row.action_plan ?? '',
      follow_up_date: row.follow_up_date ?? '',
      outcome: row.outcome,
      resolution_status: row.resolution_status,
    })
    setEditing(row)
  }

  async function onSubmit(event) {
    event.preventDefault()
    if (editing === 'new' && !form.enrollment_id) {
      toast.error('Choose a student')
      return
    }

    const payload = {
      intervention_type: form.intervention_type,
      contact_date: form.contact_date,
      notes: form.notes.trim() || null,
      action_plan: form.action_plan.trim() || null,
      follow_up_date: form.follow_up_date || null,
      outcome: form.outcome,
      resolution_status: form.resolution_status,
    }
    if (editing === 'new') payload.enrollment_id = Number(form.enrollment_id)

    try {
      await save.run(payload)
      toast.success(editing === 'new' ? 'Intervention recorded' : 'Intervention updated')
      setEditing(null)
      rows.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const courseOptions = (courses.data ?? []).map((course) => ({
    value: String(course.course_pk),
    label: course.label,
  }))

  const columns = [
    {
      key: 'student',
      header: 'Student',
      render: (row) => (
        <Link to={`/students/${row.student_pk}`} className="group block min-w-0">
          <span className="block font-semibold text-slate-800 group-hover:text-brand-700">
            {row.student_name}
          </span>
          <span className="block font-mono text-xs text-slate-500">{row.student_id}</span>
        </Link>
      ),
    },
    {
      key: 'course',
      header: 'Course',
      render: (row) => <Badge tone="neutral">{row.course_code}</Badge>,
    },
    {
      key: 'type',
      header: 'Type',
      render: (row) => <Badge tone="brand">{humanise(row.intervention_type)}</Badge>,
    },
    {
      key: 'advisor',
      header: 'Advisor',
      render: (row) => <span className="text-xs text-slate-700">{row.advisor_name ?? '—'}</span>,
    },
    {
      key: 'contact',
      header: 'Contacted',
      render: (row) => (
        <div>
          <span className="block text-xs text-slate-700">{dateOnly(row.contact_date)}</span>
          <span className="block text-xs text-slate-400">{relativeDays(row.contact_date)}</span>
        </div>
      ),
    },
    {
      key: 'follow_up',
      header: 'Follow-up',
      render: (row) => {
        if (!row.follow_up_date) return <span className="text-xs text-slate-400">—</span>
        const overdue =
          new Date(row.follow_up_date) < new Date() && row.resolution_status !== 'CLOSED'
        return (
          <span className={`text-xs ${overdue ? 'font-semibold text-risk-high' : 'text-slate-600'}`}>
            {dateOnly(row.follow_up_date)}
            {overdue && <span className="block text-[11px]">overdue</span>}
          </span>
        )
      },
    },
    {
      key: 'outcome',
      header: 'Outcome',
      render: (row) => <Badge tone={OUTCOME_TONE[row.outcome]}>{humanise(row.outcome)}</Badge>,
    },
    {
      key: 'resolution',
      header: 'Status',
      render: (row) => (
        <Badge tone={row.resolution_status === 'CLOSED' ? 'success' : 'neutral'}>
          {humanise(row.resolution_status)}
        </Badge>
      ),
    },
    {
      key: 'risk',
      header: 'Current risk',
      render: (row) =>
        row.current_risk_category ? (
          <RiskBadge
            category={row.current_risk_category}
            score={row.current_risk_score}
            size="sm"
          />
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
    {
      key: 'alert',
      header: 'Alert',
      render: (row) =>
        row.alert_id ? (
          <Link to={`/alerts?focus=${row.alert_id}`} className="text-xs font-semibold text-brand-700">
            #{row.alert_id}
          </Link>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
    ...(can('interventions:write')
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
                Update
              </button>
            ),
          },
        ]
      : []),
  ]

  return (
    <>
      <PageHeader
        title="Interventions"
        description="Counselling, tutoring and follow-up records, linked to the alerts that prompted them."
        actions={
          can('interventions:write') && (
            <button type="button" onClick={openNew} className="btn-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
              Record an intervention
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
            placeholder="Student or course"
            label="Search interventions"
            className="min-w-[13rem] flex-1"
          />
          <FilterSelect
            label="Type"
            value={type}
            onChange={(value) => {
              setType(value)
              setPage(1)
            }}
            options={enums.data?.intervention_types ?? []}
          />
          <FilterSelect
            label="Outcome"
            value={outcome}
            onChange={(value) => {
              setOutcome(value)
              setPage(1)
            }}
            options={enums.data?.intervention_outcomes ?? []}
          />
          <FilterSelect
            label="Status"
            value={resolution}
            onChange={(value) => {
              setResolution(value)
              setPage(1)
            }}
            options={enums.data?.resolution_statuses ?? []}
          />
          <FilterSelect
            label="Course"
            value={coursePk}
            onChange={(value) => {
              setCoursePk(value)
              setPage(1)
            }}
            options={courseOptions}
          />
          <FilterDate
            label="Since"
            value={dateFrom}
            onChange={(value) => {
              setDateFrom(value)
              setPage(1)
            }}
          />
          <label className="flex items-center gap-2 pb-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={followUpDue}
              onChange={(event) => {
                setFollowUpDue(event.target.checked)
                setPage(1)
              }}
              className="h-4 w-4 rounded border-slate-300 text-brand-600"
            />
            Follow-up overdue
          </label>
        </div>

        <DataTable
          columns={columns}
          rows={rows.data?.items}
          rowKey={(row) => row.intervention_id}
          loading={rows.loading}
          error={rows.error}
          onRetry={rows.reload}
          caption="Intervention history"
          emptyTitle="No interventions match these filters"
          emptyDescription="Record contact with a student from here or straight from an alert."
          emptyAction={
            can('interventions:write') && (
              <button type="button" onClick={openNew} className="btn-primary">
                <LifeBuoy className="h-4 w-4" aria-hidden="true" />
                Record an intervention
              </button>
            )
          }
        />

        {rows.data?.total > 0 && (
          <div className="border-t border-slate-200 px-4 py-3">
            <Pagination
              page={rows.data.page}
              pageSize={rows.data.page_size}
              total={rows.data.total}
              pages={rows.data.pages}
              onPageChange={setPage}
            />
          </div>
        )}
      </Card>

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'Record an intervention' : 'Update this intervention'}
        description={
          editing && editing !== 'new'
            ? `${editing.student_name} — ${editing.course_code}`
            : 'Links to the student and course through their enrolment.'
        }
        size="lg"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button
              type="submit"
              form="intervention-form"
              className="btn-primary"
              disabled={save.pending}
            >
              {save.pending ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      >
        <form id="intervention-form" onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2">
          {editing === 'new' && (
            <>
              <SelectInput
                label="Course"
                required
                value={form.course_pk}
                onChange={(event) =>
                  setForm({ ...form, course_pk: event.target.value, enrollment_id: '' })
                }
                options={courseOptions}
                placeholder="Select a course"
              />
              <SelectInput
                label="Student"
                required
                value={form.enrollment_id}
                onChange={(event) => setForm({ ...form, enrollment_id: event.target.value })}
                options={(roster.data ?? []).map((row) => ({
                  value: String(row.enrollment_id),
                  label: `${row.student_id} — ${row.student_name}`,
                }))}
                placeholder={form.course_pk ? 'Select a student' : 'Choose a course first'}
                disabled={!form.course_pk}
              />
            </>
          )}

          <SelectInput
            label="Intervention type"
            required
            value={form.intervention_type}
            onChange={(event) => setForm({ ...form, intervention_type: event.target.value })}
            options={enums.data?.intervention_types ?? []}
          />
          <div>
            <label htmlFor="intv-contact" className="label">
              Contact date <span className="text-risk-high">*</span>
            </label>
            <input
              id="intv-contact"
              type="date"
              required
              value={form.contact_date}
              onChange={(event) => setForm({ ...form, contact_date: event.target.value })}
              className="input"
            />
          </div>

          <TextArea
            label="Notes"
            rows={3}
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
            hint="What was discussed"
            className="sm:col-span-2"
          />
          <TextArea
            label="Action plan"
            rows={2}
            value={form.action_plan}
            onChange={(event) => setForm({ ...form, action_plan: event.target.value })}
            hint="What happens next, and by when"
            className="sm:col-span-2"
          />

          <div>
            <label htmlFor="intv-followup" className="label">
              Follow-up date
            </label>
            <input
              id="intv-followup"
              type="date"
              min={form.contact_date}
              value={form.follow_up_date}
              onChange={(event) => setForm({ ...form, follow_up_date: event.target.value })}
              className="input"
            />
          </div>
          <SelectInput
            label="Outcome"
            value={form.outcome}
            onChange={(event) => setForm({ ...form, outcome: event.target.value })}
            options={enums.data?.intervention_outcomes ?? []}
          />
          <SelectInput
            label="Resolution status"
            value={form.resolution_status}
            onChange={(event) => setForm({ ...form, resolution_status: event.target.value })}
            options={enums.data?.resolution_statuses ?? []}
            className="sm:col-span-2"
          />
        </form>
      </Modal>
    </>
  )
}
