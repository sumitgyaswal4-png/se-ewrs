/** The early-warning alert queue. */

import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BellRing, LifeBuoy, ShieldAlert, UserCheck } from 'lucide-react'

import Badge, { ALERT_STATUS_TONE } from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import SearchInput from '../components/SearchInput.jsx'
import StatCard from '../components/StatCard.jsx'
import { FilterDate, FilterSelect, SelectInput, TextArea } from '../components/Form.jsx'
import { ErrorState, LoadingState } from '../components/States.jsx'
import { useDebounced, useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { alertApi, authApi, interventionApi, lookupApi } from '../services/endpoints.js'
import { ALERT_STATUS_LABELS, ALERT_TRANSITIONS } from '../utils/constants.js'
import { dateTime, humanise, relativeDays, splitFactors } from '../utils/format.js'

const today = () => new Date().toISOString().slice(0, 10)

export default function AlertsPage() {
  const { can } = useAuth()
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState(searchParams.get('alert_status'))
  const [riskCategory, setRiskCategory] = useState(searchParams.get('risk_category'))
  const [coursePk, setCoursePk] = useState(searchParams.get('course_pk'))
  const [dateFrom, setDateFrom] = useState(null)
  const [onlyOpen, setOnlyOpen] = useState(searchParams.get('only_open') === 'true')
  const [focusId, setFocusId] = useState(searchParams.get('focus'))

  const [patchNote, setPatchNote] = useState('')
  const [assignTo, setAssignTo] = useState('')
  const [interveneFor, setInterveneFor] = useState(null)
  const [intervention, setIntervention] = useState({
    intervention_type: 'COUNSELING',
    contact_date: today(),
    notes: '',
    action_plan: '',
    follow_up_date: '',
  })

  const summary = useQuery(() => alertApi.summary(), [])
  const courses = useQuery(() => lookupApi.courseOptions(), [])
  const enums = useQuery(() => lookupApi.enums(), [])
  const staff = useQuery(() => authApi.assignableUsers(), [], { enabled: can('alerts:write') })

  const params = useMemo(
    () => ({
      page,
      page_size: 20,
      search: debouncedSearch || undefined,
      alert_status: status || undefined,
      risk_category: riskCategory || undefined,
      course_pk: coursePk || undefined,
      date_from: dateFrom || undefined,
      only_open: onlyOpen || undefined,
      sort_by: 'created_at',
      sort_dir: 'desc',
    }),
    [page, debouncedSearch, status, riskCategory, coursePk, dateFrom, onlyOpen],
  )
  const alerts = useQuery(() => alertApi.list(params), [JSON.stringify(params)])

  const detail = useQuery(() => alertApi.detail(focusId), [focusId], {
    enabled: Boolean(focusId),
  })

  const patch = useMutation(({ id, payload }) => alertApi.update(id, payload))
  const createIntervention = useMutation((payload) => interventionApi.create(payload))

  useEffect(() => {
    setPatchNote('')
    setAssignTo('')
  }, [focusId])

  function closeDetail() {
    setFocusId(null)
    const next = new URLSearchParams(searchParams)
    next.delete('focus')
    setSearchParams(next, { replace: true })
  }

  function openDetail(alertId) {
    setFocusId(String(alertId))
    const next = new URLSearchParams(searchParams)
    next.set('focus', String(alertId))
    setSearchParams(next, { replace: true })
  }

  async function onTransition(alertId, nextStatus) {
    try {
      await patch.run({
        id: alertId,
        payload: { status: nextStatus, note: patchNote.trim() || undefined },
      })
      toast.success(`Alert moved to ${ALERT_STATUS_LABELS[nextStatus]}`)
      setPatchNote('')
      alerts.reload()
      summary.reload()
      detail.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  async function onAssign(alertId) {
    if (!assignTo) {
      toast.error('Choose someone to assign this alert to')
      return
    }
    try {
      await patch.run({ id: alertId, payload: { assigned_to: Number(assignTo) } })
      toast.success('Alert assigned')
      setAssignTo('')
      alerts.reload()
      summary.reload()
      detail.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  async function onCreateIntervention(event) {
    event.preventDefault()
    try {
      await createIntervention.run({
        enrollment_id: interveneFor.enrollment_id,
        alert_id: interveneFor.alert_id,
        intervention_type: intervention.intervention_type,
        contact_date: intervention.contact_date,
        notes: intervention.notes.trim() || null,
        action_plan: intervention.action_plan.trim() || null,
        follow_up_date: intervention.follow_up_date || null,
      })
      toast.success('Intervention recorded and linked to this alert')
      setInterveneFor(null)
      setIntervention({
        intervention_type: 'COUNSELING',
        contact_date: today(),
        notes: '',
        action_plan: '',
        follow_up_date: '',
      })
      detail.reload()
      alerts.reload()
    } catch (error) {
      toast.error(error.message)
    }
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

  const columns = [
    {
      key: 'student',
      header: 'Student',
      sortKey: 'student_id',
      render: (row) => (
        <div className="min-w-0">
          <span className="block font-semibold text-slate-800">{row.student_name}</span>
          <span className="block font-mono text-xs text-slate-500">{row.student_id}</span>
        </div>
      ),
    },
    {
      key: 'course',
      header: 'Course',
      render: (row) => (
        <div className="min-w-0">
          <Badge tone="neutral">{row.course_code}</Badge>
          <span className="mt-0.5 block truncate text-xs text-slate-500">{row.course_name}</span>
        </div>
      ),
    },
    {
      key: 'risk',
      header: 'Risk',
      sortKey: 'risk_score',
      render: (row) => <RiskBadge category={row.risk_category} score={row.risk_score} />,
    },
    {
      key: 'factors',
      header: 'Triggering factors',
      render: (row) => {
        const factors = splitFactors(row.triggering_factors)
        return factors.length ? (
          <ul className="space-y-0.5">
            {factors.slice(0, 2).map((factor) => (
              <li key={factor} className="text-xs text-slate-600">
                · {factor}
              </li>
            ))}
            {factors.length > 2 && (
              <li className="text-xs text-slate-400">+{factors.length - 2} more</li>
            )}
          </ul>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )
      },
    },
    {
      key: 'status',
      header: 'Status',
      sortKey: 'status',
      render: (row) => (
        <Badge tone={ALERT_STATUS_TONE[row.status]}>{ALERT_STATUS_LABELS[row.status]}</Badge>
      ),
    },
    {
      key: 'assignee',
      header: 'Assigned to',
      render: (row) =>
        row.assignee_name ? (
          <span className="text-xs text-slate-700">{row.assignee_name}</span>
        ) : (
          <span className="text-xs italic text-slate-400">unassigned</span>
        ),
    },
    {
      key: 'created',
      header: 'Raised',
      sortKey: 'created_at',
      render: (row) => (
        <div>
          <span className="block text-xs text-slate-600">{relativeDays(row.created_at)}</span>
          <span className="block text-xs text-slate-400">{row.age_days}d old</span>
        </div>
      ),
    },
    {
      key: 'interventions',
      header: 'Actions logged',
      align: 'right',
      render: (row) =>
        row.intervention_count > 0 ? (
          <Badge tone="brand">{row.intervention_count}</Badge>
        ) : (
          <span className="text-xs text-slate-400">0</span>
        ),
    },
    {
      key: 'open',
      header: '',
      align: 'right',
      render: (row) => (
        <button
          type="button"
          onClick={() => openDetail(row.alert_id)}
          className="btn-ghost px-2 py-1 text-xs text-brand-700"
        >
          Open
        </button>
      ),
    },
  ]

  const current = detail.data?.alert
  const allowedNext = current ? ALERT_TRANSITIONS[current.status] ?? [] : []

  return (
    <>
      <PageHeader
        title="Early-warning alerts"
        description="Alerts are raised automatically when a student crosses the configured risk threshold."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Unresolved high risk"
          value={summary.loading ? '…' : (summary.data?.unresolved_high_risk ?? 0)}
          icon={ShieldAlert}
          accent="high"
          emphasis
        />
        <StatCard
          label="New"
          value={summary.loading ? '…' : (summary.data?.by_status?.NEW ?? 0)}
          icon={BellRing}
          accent="medium"
        />
        <StatCard
          label="Unassigned & open"
          value={summary.loading ? '…' : (summary.data?.unassigned_open ?? 0)}
          icon={UserCheck}
          accent="neutral"
        />
        <StatCard
          label="Resolved"
          value={summary.loading ? '…' : (summary.data?.by_status?.RESOLVED ?? 0)}
          icon={LifeBuoy}
          accent="low"
        />
      </div>

      <Card bodyClassName="p-0" className="mt-6">
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Student or course"
            label="Search alerts"
            className="min-w-[13rem] flex-1"
          />
          <FilterSelect
            label="Status"
            value={status}
            onChange={updateFilter(setStatus, 'alert_status')}
            options={Object.entries(ALERT_STATUS_LABELS).map(([value, label]) => ({
              value,
              label,
            }))}
          />
          <FilterSelect
            label="Risk band"
            value={riskCategory}
            onChange={updateFilter(setRiskCategory, 'risk_category')}
            options={[
              { value: 'HIGH', label: 'High risk' },
              { value: 'MEDIUM', label: 'Medium risk' },
            ]}
          />
          <FilterSelect
            label="Course"
            value={coursePk}
            onChange={updateFilter(setCoursePk, 'course_pk')}
            options={(courses.data ?? []).map((course) => ({
              value: String(course.course_pk),
              label: course.label,
            }))}
          />
          <FilterDate
            label="Raised since"
            value={dateFrom}
            onChange={(value) => {
              setDateFrom(value)
              setPage(1)
            }}
          />
          <label className="flex items-center gap-2 pb-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={onlyOpen}
              onChange={(event) => {
                setOnlyOpen(event.target.checked)
                setPage(1)
              }}
              className="h-4 w-4 rounded border-slate-300 text-brand-600"
            />
            Hide resolved
          </label>
        </div>

        <DataTable
          columns={columns}
          rows={alerts.data?.items}
          rowKey={(row) => row.alert_id}
          loading={alerts.loading}
          error={alerts.error}
          onRetry={alerts.reload}
          caption="Early-warning alert queue"
          emptyTitle="No alerts match these filters"
          emptyDescription="Nobody has crossed the threshold with these criteria. Alerts appear after a risk recalculation."
        />

        {alerts.data?.total > 0 && (
          <div className="border-t border-slate-200 px-4 py-3">
            <Pagination
              page={alerts.data.page}
              pageSize={alerts.data.page_size}
              total={alerts.data.total}
              pages={alerts.data.pages}
              onPageChange={setPage}
            />
          </div>
        )}
      </Card>

      {/* Alert detail */}
      <Modal
        open={Boolean(focusId)}
        onClose={closeDetail}
        title={current ? `Alert for ${current.student_name}` : 'Alert'}
        description={current ? `${current.course_code} — ${current.course_name}` : undefined}
        size="lg"
      >
        {detail.loading ? (
          <LoadingState rows={5} />
        ) : detail.error ? (
          <ErrorState error={detail.error} onRetry={detail.reload} />
        ) : current ? (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <RiskBadge category={current.risk_category} score={current.risk_score} showRange />
              <Badge tone={ALERT_STATUS_TONE[current.status]}>
                {ALERT_STATUS_LABELS[current.status]}
              </Badge>
              <span className="text-xs text-slate-500">
                raised {dateTime(current.created_at)} ({current.age_days}d ago)
              </span>
              {current.assignee_name ? (
                <Badge tone="brand">Assigned to {current.assignee_name}</Badge>
              ) : (
                <Badge tone="neutral">Unassigned</Badge>
              )}
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Triggering factors
              </p>
              <ul className="mt-1.5 space-y-1">
                {splitFactors(current.triggering_factors).map((factor) => (
                  <li key={factor} className="flex items-start gap-2 text-sm text-slate-700">
                    <span
                      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-risk-high"
                      aria-hidden="true"
                    />
                    {factor}
                  </li>
                ))}
              </ul>
              <Link
                to={`/risk/${current.enrollment_id}`}
                className="mt-2 inline-block text-xs font-semibold text-brand-700 hover:text-brand-800"
              >
                See the full risk breakdown →
              </Link>
            </div>

            {can('alerts:write') && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p className="text-sm font-semibold text-slate-800">Work this alert</p>
                {allowedNext.length ? (
                  <>
                    <TextArea
                      label="Note (optional)"
                      rows={2}
                      value={patchNote}
                      onChange={(event) => setPatchNote(event.target.value)}
                      hint="Recorded against the status change in the alert's history."
                      className="mt-3"
                    />
                    <div className="mt-3 flex flex-wrap gap-2">
                      {allowedNext.map((nextStatus) => (
                        <button
                          key={nextStatus}
                          type="button"
                          onClick={() => onTransition(current.alert_id, nextStatus)}
                          disabled={patch.pending}
                          className={
                            nextStatus === 'RESOLVED' ? 'btn-secondary' : 'btn-primary'
                          }
                        >
                          Mark {ALERT_STATUS_LABELS[nextStatus].toLowerCase()}
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="mt-1.5 text-sm text-slate-600">
                    This alert is resolved, which is final. If the student&rsquo;s risk rises
                    again a fresh alert is raised automatically.
                  </p>
                )}

                <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-slate-200 pt-4">
                  <SelectInput
                    label="Assign to"
                    value={assignTo}
                    onChange={(event) => setAssignTo(event.target.value)}
                    placeholder="Select an instructor or advisor"
                    options={(staff.data ?? []).map((user) => ({
                      value: String(user.user_id),
                      label: `${user.full_name} (${user.role})`,
                    }))}
                    className="min-w-[14rem] flex-1"
                  />
                  <button
                    type="button"
                    onClick={() => onAssign(current.alert_id)}
                    className="btn-secondary"
                    disabled={patch.pending}
                  >
                    Assign
                  </button>
                </div>
              </div>
            )}

            {/* Interventions linked to this alert */}
            <div>
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Interventions ({detail.data.interventions.length})
                </p>
                {can('interventions:write') && (
                  <button
                    type="button"
                    onClick={() => setInterveneFor(current)}
                    className="btn-secondary px-2.5 py-1 text-xs"
                  >
                    <LifeBuoy className="h-3.5 w-3.5" aria-hidden="true" />
                    Record an intervention
                  </button>
                )}
              </div>
              {detail.data.interventions.length ? (
                <ul className="mt-2 space-y-2">
                  {detail.data.interventions.map((item) => (
                    <li key={item.intervention_id} className="rounded-lg border border-slate-200 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="brand">{humanise(item.intervention_type)}</Badge>
                        <Badge tone="neutral">{humanise(item.outcome)}</Badge>
                        <span className="text-xs text-slate-500">
                          {item.advisor_name} · {relativeDays(item.contact_date)}
                        </span>
                      </div>
                      {item.notes && <p className="mt-1.5 text-sm text-slate-600">{item.notes}</p>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1.5 text-sm text-slate-500">
                  Nothing logged against this alert yet.
                </p>
              )}
            </div>

            {/* Status history */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Status history
              </p>
              <ol className="mt-2 space-y-2">
                {detail.data.history.map((entry) => (
                  <li key={entry.history_id} className="flex items-start gap-3 text-sm">
                    <span
                      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-slate-700">
                        {entry.old_status ? (
                          <>
                            <span className="font-medium">
                              {ALERT_STATUS_LABELS[entry.old_status]}
                            </span>{' '}
                            → <span className="font-medium">
                              {ALERT_STATUS_LABELS[entry.new_status]}
                            </span>
                          </>
                        ) : (
                          <span className="font-medium">Alert raised</span>
                        )}
                      </p>
                      <p className="text-xs text-slate-500">
                        {entry.changed_by_name ?? 'system'} · {dateTime(entry.changed_at)}
                      </p>
                      {entry.note && (
                        <p className="mt-0.5 text-xs italic text-slate-600">{entry.note}</p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        ) : null}
      </Modal>

      {/* Record an intervention against an alert */}
      <Modal
        open={Boolean(interveneFor)}
        onClose={() => setInterveneFor(null)}
        title="Record an intervention"
        description={
          interveneFor
            ? `Linked to ${interveneFor.student_name}'s alert in ${interveneFor.course_code}.`
            : ''
        }
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setInterveneFor(null)}>
              Cancel
            </button>
            <button
              type="submit"
              form="alert-intervention-form"
              className="btn-primary"
              disabled={createIntervention.pending}
            >
              {createIntervention.pending ? 'Saving…' : 'Save intervention'}
            </button>
          </>
        }
      >
        <form
          id="alert-intervention-form"
          onSubmit={onCreateIntervention}
          className="grid gap-4 sm:grid-cols-2"
        >
          <SelectInput
            label="Intervention type"
            required
            value={intervention.intervention_type}
            onChange={(event) =>
              setIntervention({ ...intervention, intervention_type: event.target.value })
            }
            options={enums.data?.intervention_types ?? []}
          />
          <div>
            <label htmlFor="contact-date" className="label">
              Contact date
            </label>
            <input
              id="contact-date"
              type="date"
              required
              value={intervention.contact_date}
              onChange={(event) =>
                setIntervention({ ...intervention, contact_date: event.target.value })
              }
              className="input"
            />
          </div>
          <TextArea
            label="Notes"
            rows={3}
            value={intervention.notes}
            onChange={(event) => setIntervention({ ...intervention, notes: event.target.value })}
            className="sm:col-span-2"
          />
          <TextArea
            label="Action plan"
            rows={2}
            value={intervention.action_plan}
            onChange={(event) =>
              setIntervention({ ...intervention, action_plan: event.target.value })
            }
            className="sm:col-span-2"
          />
          <div>
            <label htmlFor="follow-up" className="label">
              Follow-up date
            </label>
            <input
              id="follow-up"
              type="date"
              min={intervention.contact_date}
              value={intervention.follow_up_date}
              onChange={(event) =>
                setIntervention({ ...intervention, follow_up_date: event.target.value })
              }
              className="input"
            />
          </div>
        </form>
      </Modal>
    </>
  )
}
