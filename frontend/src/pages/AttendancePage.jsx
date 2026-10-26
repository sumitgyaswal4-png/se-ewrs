/** Attendance: mark a whole session, review history, see the totals. */

import { useMemo, useState } from 'react'
import { CalendarCheck, CheckCheck, Save, Trash2 } from 'lucide-react'

import Badge, { ATTENDANCE_TONE } from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import { FilterDate, FilterSelect } from '../components/Form.jsx'
import { EmptyState, LoadingState } from '../components/States.jsx'
import { useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { attendanceApi, courseApi, lookupApi } from '../services/endpoints.js'
import { ATTENDANCE_STATUS_LABELS } from '../utils/constants.js'
import { dateOnly, humanise, percent } from '../utils/format.js'

const STATUSES = ['PRESENT', 'ABSENT', 'LATE', 'EXCUSED']
const today = () => new Date().toISOString().slice(0, 10)

export default function AttendancePage() {
  const { can } = useAuth()
  const toast = useToast()

  const [tab, setTab] = useState('summary')
  const [coursePk, setCoursePk] = useState(null)
  const [dateFrom, setDateFrom] = useState(null)
  const [dateTo, setDateTo] = useState(null)
  const [status, setStatus] = useState(null)
  const [page, setPage] = useState(1)

  const [marking, setMarking] = useState(false)
  const [sessionDate, setSessionDate] = useState(today())
  const [sessionNo, setSessionNo] = useState('1')
  const [marks, setMarks] = useState({})

  const courses = useQuery(() => lookupApi.courseOptions(), [])

  const summaryParams = useMemo(() => ({ course_pk: coursePk || undefined }), [coursePk])
  const summary = useQuery(
    () => attendanceApi.summary(summaryParams),
    [JSON.stringify(summaryParams)],
    { enabled: tab === 'summary' },
  )

  const historyParams = useMemo(
    () => ({
      page,
      page_size: 20,
      course_pk: coursePk || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      attendance_status: status || undefined,
    }),
    [page, coursePk, dateFrom, dateTo, status],
  )
  const history = useQuery(
    () => attendanceApi.list(historyParams),
    [JSON.stringify(historyParams)],
    { enabled: tab === 'history' },
  )

  const roster = useQuery(() => courseApi.roster(coursePk), [coursePk], {
    enabled: marking && Boolean(coursePk),
  })

  const submitSession = useMutation((payload) => attendanceApi.bulkRecord(payload))
  const removeRecord = useMutation((id) => attendanceApi.remove(id))

  function openMarking() {
    if (!coursePk) {
      toast.error('Choose a course first')
      return
    }
    setMarks({})
    setSessionDate(today())
    setSessionNo('1')
    setMarking(true)
  }

  function setAllPresent() {
    if (!roster.data) return
    setMarks(Object.fromEntries(roster.data.map((row) => [row.enrollment_id, 'PRESENT'])))
  }

  async function onSubmitSession() {
    const rows = Object.entries(marks).map(([enrollmentId, value]) => ({
      enrollment_id: Number(enrollmentId),
      status: value,
    }))
    if (!rows.length) {
      toast.error('Mark at least one student')
      return
    }
    try {
      const result = await submitSession.run({
        course_pk: Number(coursePk),
        session_date: sessionDate,
        session_no: Number(sessionNo),
        rows,
      })
      toast.success(result.detail)
      setMarking(false)
      summary.reload()
      history.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  async function onDelete(record) {
    try {
      await removeRecord.run(record.attendance_id)
      toast.success('Attendance record deleted')
      history.reload()
      summary.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const courseOptions = (courses.data ?? []).map((course) => ({
    value: String(course.course_pk),
    label: course.label,
  }))

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
      key: 'held',
      header: 'Classes held',
      align: 'right',
      render: (row) => <span className="tabular-nums">{row.sessions_held}</span>,
    },
    {
      key: 'attended',
      header: 'Attended',
      align: 'right',
      render: (row) => <span className="tabular-nums">{row.sessions_attended}</span>,
    },
    {
      key: 'breakdown',
      header: 'Breakdown',
      render: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.sessions_late > 0 && <Badge tone="warning">{row.sessions_late} late</Badge>}
          {row.sessions_absent > 0 && <Badge tone="danger">{row.sessions_absent} absent</Badge>}
          {row.sessions_excused > 0 && (
            <Badge tone="neutral">{row.sessions_excused} excused</Badge>
          )}
          {!row.sessions_late && !row.sessions_absent && !row.sessions_excused && (
            <span className="text-xs text-slate-400">clean record</span>
          )}
        </div>
      ),
    },
    {
      key: 'percentage',
      header: 'Attendance',
      align: 'right',
      render: (row) => (
        <span
          className={`font-bold tabular-nums ${
            row.attendance_percentage === null
              ? 'text-slate-400'
              : row.attendance_percentage < 75
                ? 'text-risk-high'
                : 'text-slate-900'
          }`}
        >
          {percent(row.attendance_percentage, 1)}
        </span>
      ),
    },
    {
      key: 'last',
      header: 'Last session',
      render: (row) => (
        <span className="text-xs text-slate-500">{dateOnly(row.last_session_date)}</span>
      ),
    },
  ]

  const historyColumns = [
    {
      key: 'date',
      header: 'Session',
      render: (row) => (
        <div>
          <span className="block font-medium text-slate-800">{dateOnly(row.session_date)}</span>
          <span className="block text-xs text-slate-500">Session #{row.session_no}</span>
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
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Badge tone={ATTENDANCE_TONE[row.status]}>
          {ATTENDANCE_STATUS_LABELS[row.status] ?? humanise(row.status)}
        </Badge>
      ),
    },
    {
      key: 'recorded',
      header: 'Recorded by',
      render: (row) => (
        <span className="text-xs text-slate-500">{row.recorded_by_name ?? '—'}</span>
      ),
    },
    {
      key: 'remarks',
      header: 'Remarks',
      render: (row) => <span className="text-xs text-slate-500">{row.remarks ?? '—'}</span>,
    },
    ...(can('attendance:write')
      ? [
          {
            key: 'actions',
            header: '',
            align: 'right',
            render: (row) => (
              <button
                type="button"
                onClick={() => onDelete(row)}
                className="btn-ghost px-2 py-1 text-xs"
                aria-label={`Delete attendance for ${row.student_name} on ${row.session_date}`}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            ),
          },
        ]
      : []),
  ]

  return (
    <>
      <PageHeader
        title="Attendance"
        description="Record a whole class in one pass, then review the running totals."
        actions={
          can('attendance:write') && (
            <button type="button" onClick={openMarking} className="btn-primary">
              <CalendarCheck className="h-4 w-4" aria-hidden="true" />
              Mark a session
            </button>
          )
        }
      />

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <div role="tablist" aria-label="Attendance view" className="flex rounded-lg bg-slate-100 p-1">
            {[
              { id: 'summary', label: 'Totals' },
              { id: 'history', label: 'History' },
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

          {tab === 'history' && (
            <>
              <FilterDate label="From" value={dateFrom} onChange={(value) => { setDateFrom(value); setPage(1) }} />
              <FilterDate label="To" value={dateTo} onChange={(value) => { setDateTo(value); setPage(1) }} />
              <FilterSelect
                label="Status"
                value={status}
                onChange={(value) => {
                  setStatus(value)
                  setPage(1)
                }}
                options={STATUSES.map((value) => ({
                  value,
                  label: ATTENDANCE_STATUS_LABELS[value],
                }))}
              />
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
            caption="Classes held and attended per enrolled student"
            emptyTitle="No attendance recorded yet"
            emptyDescription="Mark a session to start building the totals. Excused absences are excluded from the denominator."
          />
        ) : (
          <>
            <DataTable
              columns={historyColumns}
              rows={history.data?.items}
              rowKey={(row) => row.attendance_id}
              loading={history.loading}
              error={history.error}
              onRetry={history.reload}
              caption="Historical attendance records"
              emptyTitle="No records match these filters"
              emptyDescription="Try widening the date range or clearing the status filter."
            />
            {history.data?.total > 0 && (
              <div className="border-t border-slate-200 px-4 py-3">
                <Pagination
                  page={history.data.page}
                  pageSize={history.data.page_size}
                  total={history.data.total}
                  pages={history.data.pages}
                  onPageChange={setPage}
                />
              </div>
            )}
          </>
        )}
      </Card>

      <Modal
        open={marking}
        onClose={() => setMarking(false)}
        title="Mark attendance"
        description="Re-marking a session you have already recorded corrects it rather than creating a duplicate."
        size="lg"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setMarking(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={onSubmitSession}
              disabled={submitSession.pending}
            >
              <Save className="h-4 w-4" aria-hidden="true" />
              {submitSession.pending ? 'Saving…' : 'Save session'}
            </button>
          </>
        }
      >
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="session-date" className="label">
              Session date
            </label>
            <input
              id="session-date"
              type="date"
              value={sessionDate}
              max={today()}
              onChange={(event) => setSessionDate(event.target.value)}
              className="input"
            />
          </div>
          <div>
            <label htmlFor="session-no" className="label">
              Session number
            </label>
            <input
              id="session-no"
              type="number"
              min={1}
              value={sessionNo}
              onChange={(event) => setSessionNo(event.target.value)}
              className="input"
            />
          </div>
          <div className="flex items-end">
            <button type="button" onClick={setAllPresent} className="btn-secondary w-full">
              <CheckCheck className="h-4 w-4" aria-hidden="true" />
              All present
            </button>
          </div>
        </div>

        {roster.loading ? (
          <LoadingState rows={5} />
        ) : !roster.data?.length ? (
          <EmptyState
            title="Nobody is enrolled on this course"
            description="Enrol students from the Courses page first."
          />
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {roster.data.map((row) => (
              <li
                key={row.enrollment_id}
                className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5"
              >
                <div className="min-w-0">
                  <span className="block text-sm font-medium text-slate-800">
                    {row.student_name}
                  </span>
                  <span className="block font-mono text-xs text-slate-500">{row.student_id}</span>
                </div>
                <div
                  role="radiogroup"
                  aria-label={`Attendance for ${row.student_name}`}
                  className="flex gap-1"
                >
                  {STATUSES.map((value) => {
                    const active = marks[row.enrollment_id] === value
                    return (
                      <button
                        key={value}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        onClick={() =>
                          setMarks((current) => ({ ...current, [row.enrollment_id]: value }))
                        }
                        className={`rounded-md border px-2 py-1 text-xs font-semibold transition ${
                          active
                            ? 'border-brand-600 bg-brand-600 text-white'
                            : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        {ATTENDANCE_STATUS_LABELS[value]}
                      </button>
                    )
                  })}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </>
  )
}
