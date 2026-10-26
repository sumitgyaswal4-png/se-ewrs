/** LMS activity: login frequency, last-seen and the raw event log. */

import { useMemo, useState } from 'react'
import { Activity, Plus } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import { FilterDate, FilterSelect, SelectInput, TextInput } from '../components/Form.jsx'
import { useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { activityApi, courseApi, lookupApi } from '../services/endpoints.js'
import { dateTime, humanise, relativeDays } from '../utils/format.js'

export default function ActivityPage() {
  const { can } = useAuth()
  const toast = useToast()

  const [tab, setTab] = useState('summary')
  const [coursePk, setCoursePk] = useState(null)
  const [activityType, setActivityType] = useState(null)
  const [dateFrom, setDateFrom] = useState(null)
  const [dateTo, setDateTo] = useState(null)
  const [page, setPage] = useState(1)

  const [logging, setLogging] = useState(false)
  const [form, setForm] = useState({
    course_pk: '',
    enrollment_id: '',
    activity_type: 'LOGIN',
    duration_minutes: '',
    resource_ref: '',
  })

  const courses = useQuery(() => lookupApi.courseOptions(), [])
  const enums = useQuery(() => lookupApi.enums(), [])

  const summaryParams = useMemo(() => ({ course_pk: coursePk || undefined }), [coursePk])
  const summary = useQuery(
    () => activityApi.summary(summaryParams),
    [JSON.stringify(summaryParams)],
    { enabled: tab === 'summary' },
  )

  const logParams = useMemo(
    () => ({
      page,
      page_size: 25,
      course_pk: coursePk || undefined,
      activity_type: activityType || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
    [page, coursePk, activityType, dateFrom, dateTo],
  )
  const log = useQuery(() => activityApi.list(logParams), [JSON.stringify(logParams)], {
    enabled: tab === 'log',
  })

  const roster = useQuery(() => courseApi.roster(form.course_pk), [form.course_pk], {
    enabled: logging && Boolean(form.course_pk),
  })

  const create = useMutation((payload) => activityApi.create(payload))

  async function onSubmit(event) {
    event.preventDefault()
    if (!form.enrollment_id) {
      toast.error('Choose a student')
      return
    }
    try {
      await create.run({
        enrollment_id: Number(form.enrollment_id),
        activity_type: form.activity_type,
        duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : null,
        resource_ref: form.resource_ref.trim() || null,
      })
      toast.success('Activity recorded')
      setLogging(false)
      setForm({ ...form, enrollment_id: '', duration_minutes: '', resource_ref: '' })
      summary.reload()
      log.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const courseOptions = (courses.data ?? []).map((course) => ({
    value: String(course.course_pk),
    label: course.label,
  }))
  const activityTypeOptions = enums.data?.activity_types ?? []

  const summaryColumns = [
    {
      key: 'student',
      header: 'Student',
      render: (row) => (
        <div className="min-w-0">
          <span className="block font-medium text-slate-800">{row.student_name}</span>
          <span className="block font-mono text-xs text-slate-500">{row.student_id}</span>
        </div>
      ),
    },
    { key: 'course', header: 'Course', render: (row) => <Badge tone="neutral">{row.course_code}</Badge> },
    {
      key: 'logins30',
      header: 'Logins (30d)',
      align: 'right',
      render: (row) => (
        <span
          className={`font-bold tabular-nums ${
            row.login_count_30d === 0
              ? 'text-risk-high'
              : row.login_count_30d < 4
                ? 'text-[#875c00]'
                : 'text-slate-900'
          }`}
        >
          {row.login_count_30d}
        </span>
      ),
    },
    {
      key: 'logins',
      header: 'Logins (total)',
      align: 'right',
      render: (row) => <span className="tabular-nums">{row.login_count_total}</span>,
    },
    {
      key: 'quizzes',
      header: 'Quiz attempts',
      align: 'right',
      render: (row) => <span className="tabular-nums">{row.quiz_attempts}</span>,
    },
    {
      key: 'submissions',
      header: 'Submission events',
      align: 'right',
      render: (row) => <span className="tabular-nums">{row.submission_events}</span>,
    },
    {
      key: 'minutes',
      header: 'Minutes',
      align: 'right',
      render: (row) => <span className="tabular-nums">{row.total_minutes}</span>,
    },
    {
      key: 'last',
      header: 'Last activity',
      render: (row) => (
        <div>
          <span
            className={`block text-sm ${
              row.days_since_last_activity === null || row.days_since_last_activity > 14
                ? 'font-semibold text-risk-high'
                : 'text-slate-700'
            }`}
          >
            {row.last_activity_at ? relativeDays(row.last_activity_at) : 'never seen'}
          </span>
          {row.last_activity_at && (
            <span className="block text-xs text-slate-400">
              {dateTime(row.last_activity_at)}
            </span>
          )}
        </div>
      ),
    },
  ]

  const logColumns = [
    {
      key: 'when',
      header: 'When',
      render: (row) => (
        <div>
          <span className="block text-sm text-slate-800">{dateTime(row.activity_at)}</span>
          <span className="block text-xs text-slate-400">{relativeDays(row.activity_at)}</span>
        </div>
      ),
    },
    {
      key: 'student',
      header: 'Student',
      render: (row) => (
        <div className="min-w-0">
          <span className="block text-sm text-slate-800">{row.student_name}</span>
          <span className="block font-mono text-xs text-slate-500">{row.student_id}</span>
        </div>
      ),
    },
    { key: 'course', header: 'Course', render: (row) => <Badge tone="neutral">{row.course_code}</Badge> },
    {
      key: 'type',
      header: 'Event',
      render: (row) => <Badge tone="brand">{humanise(row.activity_type)}</Badge>,
    },
    {
      key: 'duration',
      header: 'Duration',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums text-xs">
          {row.duration_minutes === null ? '—' : `${row.duration_minutes} min`}
        </span>
      ),
    },
    {
      key: 'resource',
      header: 'Resource',
      render: (row) => (
        <span className="font-mono text-xs text-slate-500">{row.resource_ref ?? '—'}</span>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="LMS activity"
        description="Login frequency, time on task and the raw engagement event log."
        actions={
          can('activity:write') && (
            <button type="button" onClick={() => setLogging(true)} className="btn-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
              Log an event
            </button>
          )
        }
      />

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <div role="tablist" aria-label="Activity view" className="flex rounded-lg bg-slate-100 p-1">
            {[
              { id: 'summary', label: 'Per student' },
              { id: 'log', label: 'Event log' },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  tab === item.id
                    ? 'bg-white text-brand-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-800'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <FilterSelect
            label="Course"
            value={coursePk}
            onChange={(value) => {
              setCoursePk(value)
              setPage(1)
            }}
            options={courseOptions}
            placeholder="All courses"
          />

          {tab === 'log' && (
            <>
              <FilterSelect
                label="Event type"
                value={activityType}
                onChange={(value) => {
                  setActivityType(value)
                  setPage(1)
                }}
                options={activityTypeOptions}
              />
              <FilterDate label="From" value={dateFrom} onChange={(value) => { setDateFrom(value); setPage(1) }} />
              <FilterDate label="To" value={dateTo} onChange={(value) => { setDateTo(value); setPage(1) }} />
            </>
          )}
        </div>

        {tab === 'summary' ? (
          <DataTable
            columns={summaryColumns}
            rows={summary.data}
            rowKey={(row) => row.enrollment_id}
            loading={summary.loading}
            error={summary.error}
            onRetry={summary.reload}
            caption="Login frequency and last activity per enrolled student"
            emptyTitle="No activity data yet"
            emptyDescription="LMS events appear here once they are logged against an enrolment."
          />
        ) : (
          <>
            <DataTable
              columns={logColumns}
              rows={log.data?.items}
              rowKey={(row) => row.activity_id}
              loading={log.loading}
              error={log.error}
              onRetry={log.reload}
              caption="LMS activity event log"
              emptyTitle="No events match these filters"
              emptyDescription="Try a different date range or event type."
            />
            {log.data?.total > 0 && (
              <div className="border-t border-slate-200 px-4 py-3">
                <Pagination
                  page={log.data.page}
                  pageSize={log.data.page_size}
                  total={log.data.total}
                  pages={log.data.pages}
                  onPageChange={setPage}
                />
              </div>
            )}
          </>
        )}
      </Card>

      <Modal
        open={logging}
        onClose={() => setLogging(false)}
        title="Log an LMS event"
        description="Records a single engagement event against one enrolment."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setLogging(false)}>
              Cancel
            </button>
            <button
              type="submit"
              form="activity-form"
              className="btn-primary"
              disabled={create.pending}
            >
              <Activity className="h-4 w-4" aria-hidden="true" />
              {create.pending ? 'Saving…' : 'Record event'}
            </button>
          </>
        }
      >
        <form id="activity-form" onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2">
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
          <SelectInput
            label="Event type"
            required
            value={form.activity_type}
            onChange={(event) => setForm({ ...form, activity_type: event.target.value })}
            options={activityTypeOptions}
          />
          <TextInput
            label="Duration (minutes)"
            type="number"
            min={0}
            max={1440}
            value={form.duration_minutes}
            onChange={(event) => setForm({ ...form, duration_minutes: event.target.value })}
            hint="Optional"
          />
          <TextInput
            label="Resource reference"
            value={form.resource_ref}
            onChange={(event) => setForm({ ...form, resource_ref: event.target.value })}
            hint="Optional, e.g. week-03-slides.pdf"
            className="sm:col-span-2"
          />
        </form>
      </Modal>
    </>
  )
}
