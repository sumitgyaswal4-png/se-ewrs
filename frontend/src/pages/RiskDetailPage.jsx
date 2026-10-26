/** One enrolment's risk score, fully explained. */

import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Info, RefreshCw } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import Meter from '../components/Meter.jsx'
import PageHeader from '../components/PageHeader.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import { ErrorState, LoadingState } from '../components/States.jsx'
import RiskComponentChart from '../components/charts/RiskComponentChart.jsx'
import RiskHistoryChart from '../components/charts/RiskHistoryChart.jsx'
import { useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { riskApi } from '../services/endpoints.js'
import { RISK_COLORS } from '../utils/charts.js'
import { dateOnly, relativeDays, score, splitFactors } from '../utils/format.js'

export default function RiskDetailPage() {
  const { enrollmentId } = useParams()
  const { can } = useAuth()
  const toast = useToast()

  const detail = useQuery(() => riskApi.detail(enrollmentId), [enrollmentId])
  const recalculate = useMutation(() => riskApi.recalculate({ enrollment_id: Number(enrollmentId) }))

  async function onRecalculate() {
    try {
      const result = await recalculate.run()
      toast.success(result.detail)
      detail.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  if (detail.loading) {
    return (
      <div className="card">
        <LoadingState rows={6} label="Loading risk detail" />
      </div>
    )
  }
  if (detail.error) {
    return (
      <div className="card">
        <ErrorState error={detail.error} onRetry={detail.reload} />
      </div>
    )
  }

  const { row, components, engagement_breakdown: breakdown, thresholds, weights, history, disclaimer } =
    detail.data
  const factors = splitFactors(row.contributing_factors)
  const needsData = row.risk_category === 'INSUFFICIENT_DATA'

  return (
    <>
      <Link
        to="/risk"
        className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to risk analysis
      </Link>

      <PageHeader
        title={row.student_name}
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono text-xs">{row.student_id}</span>
            <span>
              {row.course_code} — {row.course_name}
            </span>
            {row.dept_code && <Badge tone="neutral">{row.dept_code}</Badge>}
            {row.student_semester && <Badge tone="brand">Sem {row.student_semester}</Badge>}
          </span>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/students/${row.student_pk}`} className="btn-secondary">
              Student profile
            </Link>
            {can('risk:recalculate') && (
              <button
                type="button"
                onClick={onRecalculate}
                className="btn-primary"
                disabled={recalculate.pending}
              >
                <RefreshCw
                  className={`h-4 w-4 ${recalculate.pending ? 'animate-spin' : ''}`}
                  aria-hidden="true"
                />
                Recalculate
              </button>
            )}
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {/* The score itself, as a hero figure. */}
        <Card className="lg:col-span-1">
          <div className="p-5 text-center">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Overall risk score
            </p>
            <p className="mt-2 text-5xl font-bold tabular-nums text-slate-900">
              {score(row.risk_score, 1)}
              <span className="ml-1 text-xl font-normal text-slate-400">/100</span>
            </p>
            <div className="mt-3 flex justify-center">
              <RiskBadge category={row.risk_category} showRange />
            </div>
            <dl className="mt-5 space-y-1.5 border-t border-slate-100 pt-4 text-left text-xs">
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Data completeness</dt>
                <dd className="font-semibold text-slate-800">
                  {row.data_completeness.toLowerCase()}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Model</dt>
                <dd className="font-mono text-slate-800">{row.model_version ?? 'rule-v1'}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Calculated</dt>
                <dd className="text-slate-800">
                  {row.calculated_at ? relativeDays(row.calculated_at) : 'live (not stored)'}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Latest assessment</dt>
                <dd className="text-slate-800">{dateOnly(row.last_assessment_date)}</dd>
              </div>
            </dl>
          </div>
        </Card>

        <Card
          title="How the score was built"
          description={`Weights: attendance ${(weights.attendance * 100).toFixed(0)}%, academic ${(
            weights.academic * 100
          ).toFixed(0)}%, engagement ${(weights.engagement * 100).toFixed(0)}%. Bands: low 0-${
            thresholds.medium - 1
          }, medium ${thresholds.medium}-${thresholds.high - 1}, high ${thresholds.high}-100.`}
          bodyClassName="p-0"
          className="lg:col-span-2"
        >
          <RiskComponentChart components={components} />
        </Card>
      </div>

      {needsData && (
        <div className="mt-4 flex items-start gap-3 rounded-xl border border-slate-300 bg-slate-50 p-4">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-slate-800">
              This profile needs more data before it can be scored
            </p>
            <p className="mt-1 text-sm text-slate-600">{row.missing_data_reasons}</p>
            <p className="mt-1.5 text-sm text-slate-500">
              Fewer than two of the three components are observable, so no risk band is
              assigned. Missing data is not evidence of poor performance.
            </p>
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Observed figures" className="lg:col-span-1">
          <div className="space-y-4 p-5">
            <Meter
              label="Attendance"
              value={row.attendance_percentage}
              hint={`${row.sessions_attended} of ${row.sessions_held} sessions attended`}
              color={RISK_COLORS.LOW}
            />
            <Meter
              label="Assessment average"
              value={row.avg_assessment_percentage}
              hint={`${row.graded_assessments} graded assessment(s)`}
            />
            <Meter
              label="Engagement score"
              value={row.engagement_score}
              suffix="/100"
              hint="Higher is better"
              color={RISK_COLORS.MEDIUM}
            />
            <dl className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-sm">
              <div>
                <dt className="text-xs text-slate-500">Late submissions</dt>
                <dd className="font-bold tabular-nums text-slate-900">{row.late_submissions}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Missing submissions</dt>
                <dd className="font-bold tabular-nums text-slate-900">
                  {row.missing_submissions}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Logins (30 days)</dt>
                <dd className="font-bold tabular-nums text-slate-900">{row.login_count_30d}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Last LMS activity</dt>
                <dd className="text-sm font-semibold text-slate-900">
                  {row.last_activity_at ? relativeDays(row.last_activity_at) : 'never'}
                </dd>
              </div>
            </dl>
          </div>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <Card title="Main contributing factors">
            <div className="p-5">
              {factors.length && factors[0] !== 'No adverse factors detected' ? (
                <ul className="space-y-2">
                  {factors.map((factor) => (
                    <li key={factor} className="flex items-start gap-2.5">
                      <span
                        className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-risk-high"
                        aria-hidden="true"
                      />
                      <span className="text-sm text-slate-700">{factor}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">No adverse factors detected.</p>
              )}

              {Object.keys(breakdown ?? {}).length > 0 && (
                <div className="mt-5 border-t border-slate-100 pt-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Engagement penalties
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Engagement score = 100 − (recency + login frequency + missing + late),
                    clamped to 0–100.
                  </p>
                  <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                      ['Recency', breakdown.recency_penalty],
                      ['Login frequency', breakdown.login_frequency_penalty],
                      ['Missing work', breakdown.missing_submission_penalty],
                      ['Late work', breakdown.late_submission_penalty],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-lg bg-slate-50 p-2.5">
                        <dt className="text-[11px] text-slate-500">{label}</dt>
                        <dd className="text-sm font-bold tabular-nums text-slate-900">
                          −{Number(value ?? 0).toFixed(1)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
            </div>
          </Card>

          <Card
            title="Risk score over time"
            description="A point is added each time risk is recalculated."
            bodyClassName="p-0"
          >
            <RiskHistoryChart history={history} thresholds={thresholds} />
          </Card>
        </div>
      </div>

      <p className="mt-4 rounded-lg bg-slate-100 px-4 py-3 text-xs text-slate-600">
        {disclaimer}
      </p>
    </>
  )
}
