/** System settings and the audit trail (administrators only). */

import { useMemo, useState } from 'react'
import { Save, Settings as SettingsIcon, ShieldCheck } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import { FilterDate, FilterSelect } from '../components/Form.jsx'
import { ErrorState, LoadingState } from '../components/States.jsx'
import { useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { settingsApi } from '../services/endpoints.js'
import { dateTime, humanise } from '../utils/format.js'

const GROUPS = [
  {
    title: 'Risk model weights',
    description:
      'The three components must describe the whole score. Changing a weight re-shapes every future calculation; existing stored scores are left as they are until risk is recalculated.',
    prefix: 'risk.weight.',
  },
  {
    title: 'Risk bands and alerting',
    description: 'Where one band ends and the next begins, and when an alert is raised.',
    keys: ['risk.threshold.medium', 'risk.threshold.high', 'alert.min_score'],
  },
  {
    title: 'Data sufficiency',
    description:
      'How much data a component needs before it counts. These are what keep a student with no graded work from being labelled at risk.',
    keys: ['risk.min_sessions', 'risk.min_graded', 'risk.activity_window_days', 'engagement.target_logins_30d'],
  },
  {
    title: 'Model identity',
    keys: ['risk.model_version'],
  },
]

export default function SettingsPage() {
  const { can } = useAuth()
  const toast = useToast()

  const [drafts, setDrafts] = useState({})
  const [page, setPage] = useState(1)
  const [action, setAction] = useState(null)
  const [entityType, setEntityType] = useState(null)
  const [dateFrom, setDateFrom] = useState(null)

  const settings = useQuery(() => settingsApi.list(), [])
  const config = useQuery(() => settingsApi.riskConfig(), [])

  const auditParams = useMemo(
    () => ({
      page,
      page_size: 25,
      action: action || undefined,
      entity_type: entityType || undefined,
      date_from: dateFrom || undefined,
    }),
    [page, action, entityType, dateFrom],
  )
  const audit = useQuery(() => settingsApi.auditLogs(auditParams), [JSON.stringify(auditParams)], {
    enabled: can('audit:read'),
  })

  const save = useMutation(({ key, value }) => settingsApi.update(key, { setting_value: value }))

  async function onSave(key) {
    const value = drafts[key]
    if (value === undefined) return
    try {
      await save.run({ key, value })
      toast.success(`${key} updated`)
      setDrafts((current) => {
        const next = { ...current }
        delete next[key]
        return next
      })
      settings.reload()
      config.reload()
      audit.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const byKey = Object.fromEntries((settings.data ?? []).map((row) => [row.setting_key, row]))

  function groupRows(group) {
    if (group.keys) return group.keys.map((key) => byKey[key]).filter(Boolean)
    return (settings.data ?? []).filter((row) => row.setting_key.startsWith(group.prefix))
  }

  const weightTotal = config.data
    ? config.data.weights.attendance + config.data.weights.academic + config.data.weights.engagement
    : null

  const auditColumns = [
    {
      key: 'when',
      header: 'When',
      render: (row) => <span className="text-xs text-slate-600">{dateTime(row.created_at)}</span>,
    },
    {
      key: 'who',
      header: 'Who',
      render: (row) => (
        <span className="text-xs text-slate-700">{row.user_name ?? 'system'}</span>
      ),
    },
    {
      key: 'action',
      header: 'Action',
      render: (row) => (
        <Badge
          tone={
            row.action === 'LOGIN_FAILED'
              ? 'danger'
              : row.action.includes('DELETE') || row.action === 'DEACTIVATE'
                ? 'warning'
                : 'neutral'
          }
        >
          {humanise(row.action)}
        </Badge>
      ),
    },
    {
      key: 'entity',
      header: 'Entity',
      render: (row) => (
        <span className="font-mono text-xs text-slate-600">
          {row.entity_type}
          {row.entity_id ? `#${row.entity_id}` : ''}
        </span>
      ),
    },
    {
      key: 'change',
      header: 'Change',
      render: (row) => (
        <div className="max-w-md space-y-0.5">
          {row.old_values && (
            <p className="truncate font-mono text-[11px] text-slate-500">
              before: {row.old_values}
            </p>
          )}
          {row.new_values && (
            <p className="truncate font-mono text-[11px] text-slate-700">
              after: {row.new_values}
            </p>
          )}
        </div>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="System settings"
        description="The risk model is configuration, not code — these values are read at calculation time."
      />

      {config.data && (
        <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Attendance weight', `${(config.data.weights.attendance * 100).toFixed(0)}%`],
            ['Academic weight', `${(config.data.weights.academic * 100).toFixed(0)}%`],
            ['Engagement weight', `${(config.data.weights.engagement * 100).toFixed(0)}%`],
            [
              'Bands',
              `low 0–${config.data.thresholds.medium - 1} · medium ${config.data.thresholds.medium}–${
                config.data.thresholds.high - 1
              } · high ${config.data.thresholds.high}+`,
            ],
          ].map(([label, value]) => (
            <div key={label} className="card p-4">
              <p className="text-xs font-medium text-slate-500">{label}</p>
              <p className="mt-1 text-sm font-bold text-slate-900">{value}</p>
            </div>
          ))}
        </div>
      )}

      {weightTotal !== null && Math.abs(weightTotal - 1) > 0.001 && (
        <div className="mb-4 rounded-xl border border-risk-medium/40 bg-risk-medium/10 p-4 text-sm text-[#875c00]">
          The three weights currently sum to {weightTotal.toFixed(2)} rather than 1.00. The
          model still works — the available components are re-normalised at calculation
          time — but the numbers are easier to reason about when they add up to 1.
        </div>
      )}

      {settings.loading ? (
        <Card>
          <LoadingState rows={6} />
        </Card>
      ) : settings.error ? (
        <Card>
          <ErrorState error={settings.error} onRetry={settings.reload} />
        </Card>
      ) : (
        <div className="space-y-4">
          {GROUPS.map((group) => {
            const rows = groupRows(group)
            if (!rows.length) return null
            return (
              <Card key={group.title} title={group.title} description={group.description}>
                <ul className="divide-y divide-slate-100">
                  {rows.map((row) => {
                    const draft = drafts[row.setting_key]
                    const dirty = draft !== undefined && draft !== row.setting_value
                    return (
                      <li
                        key={row.setting_key}
                        className="flex flex-wrap items-end justify-between gap-3 px-5 py-3.5"
                      >
                        <div className="min-w-0 flex-1">
                          <label
                            htmlFor={`setting-${row.setting_key}`}
                            className="block font-mono text-xs font-semibold text-slate-800"
                          >
                            {row.setting_key}
                          </label>
                          {row.description && (
                            <p className="mt-0.5 text-xs text-slate-500">{row.description}</p>
                          )}
                        </div>
                        <div className="flex items-end gap-2">
                          <input
                            id={`setting-${row.setting_key}`}
                            type={row.value_type === 'STRING' ? 'text' : 'number'}
                            step={row.value_type === 'FLOAT' ? '0.01' : '1'}
                            value={draft ?? row.setting_value}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [row.setting_key]: event.target.value,
                              }))
                            }
                            disabled={!can('settings:write')}
                            className="input w-28 py-1.5 text-right tabular-nums"
                          />
                          {can('settings:write') && (
                            <button
                              type="button"
                              onClick={() => onSave(row.setting_key)}
                              disabled={!dirty || save.pending}
                              className="btn-primary px-2.5 py-1.5 text-xs"
                            >
                              <Save className="h-3.5 w-3.5" aria-hidden="true" />
                              Save
                            </button>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </Card>
            )
          })}
        </div>
      )}

      {can('audit:read') && (
        <Card
          title="Audit trail"
          description="Application events plus the row-level changes captured by the database triggers. Passwords are never recorded here."
          bodyClassName="p-0"
          className="mt-6"
          actions={
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              append-only
            </span>
          }
        >
          <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
            <FilterSelect
              label="Action"
              value={action}
              onChange={(value) => {
                setAction(value)
                setPage(1)
              }}
              options={[
                'LOGIN',
                'LOGIN_FAILED',
                'INSERT',
                'UPDATE',
                'DELETE',
                'DEACTIVATE',
                'RECALCULATE',
                'BULK_UPSERT',
                'PASSWORD_CHANGE',
              ].map((value) => ({ value, label: humanise(value) }))}
            />
            <FilterSelect
              label="Entity"
              value={entityType}
              onChange={(value) => {
                setEntityType(value)
                setPage(1)
              }}
              options={[
                'students',
                'courses',
                'enrollments',
                'users',
                'risk_alerts',
                'risk_assessments',
                'assessment_results',
                'attendance_records',
                'interventions',
                'system_settings',
              ].map((value) => ({ value, label: value }))}
            />
            <FilterDate
              label="Since"
              value={dateFrom}
              onChange={(value) => {
                setDateFrom(value)
                setPage(1)
              }}
            />
          </div>

          <DataTable
            columns={auditColumns}
            rows={audit.data?.items}
            rowKey={(row) => row.audit_id}
            loading={audit.loading}
            error={audit.error}
            onRetry={audit.reload}
            caption="Audit log"
            emptyTitle="No audit entries match these filters"
            emptyDescription="Entries are written as records are created and changed."
          />

          {audit.data?.total > 0 && (
            <div className="border-t border-slate-200 px-4 py-3">
              <Pagination
                page={audit.data.page}
                pageSize={audit.data.page_size}
                total={audit.data.total}
                pages={audit.data.pages}
                onPageChange={setPage}
              />
            </div>
          )}
        </Card>
      )}

      <p className="mt-4 flex items-start gap-2 rounded-lg bg-slate-100 px-4 py-3 text-xs text-slate-600">
        <SettingsIcon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          Saved values take effect on the next risk recalculation. Stored scores keep the
          weights they were produced with, which is why each risk row records its own{' '}
          <code className="font-mono">model_version</code>.
        </span>
      </p>
    </>
  )
}
