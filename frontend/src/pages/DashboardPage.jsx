/** The main dashboard.
 *
 * Every number on this page comes from `GET /api/dashboard/*`, which
 * aggregates it in SQL. Nothing here is hardcoded - with an empty
 * database the tiles read zero and the charts show their empty states.
 */

import { Link } from 'react-router-dom'
import {
  BellRing,
  BookOpen,
  CalendarCheck,
  ClipboardList,
  GraduationCap,
  LifeBuoy,
  RefreshCw,
  ShieldAlert,
  TrendingUp,
  Users,
} from 'lucide-react'

import Badge, { ALERT_STATUS_TONE } from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import PageHeader from '../components/PageHeader.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import StatCard from '../components/StatCard.jsx'
import { ChartSkeleton, EmptyState, ErrorState, LoadingState } from '../components/States.jsx'
import GroupedRiskChart from '../components/charts/GroupedRiskChart.jsx'
import RiskDistributionChart from '../components/charts/RiskDistributionChart.jsx'
import TrendChart from '../components/charts/TrendChart.jsx'
import { useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { dashboardApi, reportApi, riskApi } from '../services/endpoints.js'
import { ALERT_STATUS_LABELS } from '../utils/constants.js'
import { count, percent, relativeDays } from '../utils/format.js'

export default function DashboardPage() {
  const { can, user } = useAuth()
  const toast = useToast()

  const summary = useQuery(() => dashboardApi.summary(), [])
  const alerts = useQuery(() => dashboardApi.recentAlerts({ limit: 6 }), [], {
    enabled: can('alerts:read'),
  })
  const trend = useQuery(() => dashboardApi.performanceTrend({ months: 12 }), [])
  const byDepartment = useQuery(
    () => reportApi.riskDistribution({ group_by: 'department' }),
    [],
  )

  const recalculate = useMutation(() => riskApi.recalculate({}))

  async function onRecalculate() {
    try {
      const result = await recalculate.run()
      toast.success(result.detail)
      summary.reload()
      alerts.reload()
      byDepartment.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const data = summary.data

  return (
    <>
      <PageHeader
        title={`Welcome back, ${user?.full_name?.split(' ')[0] ?? 'there'}`}
        description="Engagement, academic performance and early-warning status across the department."
        actions={
          can('risk:recalculate') && (
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
              {recalculate.pending ? 'Recalculating…' : 'Recalculate risk'}
            </button>
          )
        }
      />

      {summary.error ? (
        <div className="card">
          <ErrorState error={summary.error} onRetry={summary.reload} />
        </div>
      ) : (
        <>
          {/* Unresolved high-risk alerts, surfaced above everything else. */}
          {!summary.loading && data?.unresolved_high_risk_alerts > 0 && can('alerts:read') && (
            <Link
              to="/alerts?risk_category=HIGH&only_open=true"
              className="mb-6 flex items-start gap-3 rounded-xl border border-risk-high/40 bg-risk-high/5 p-4 transition hover:bg-risk-high/10"
            >
              <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-risk-high" aria-hidden="true" />
              <div>
                <p className="text-sm font-semibold text-[#9c2525]">
                  {data.unresolved_high_risk_alerts} unresolved high-risk alert
                  {data.unresolved_high_risk_alerts === 1 ? '' : 's'}
                </p>
                <p className="mt-0.5 text-sm text-slate-600">
                  These students need contact. Open the alert queue to acknowledge or assign them.
                </p>
              </div>
            </Link>
          )}

          {/* Headline counters: a KPI row, not a chart. */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Active students"
              value={summary.loading ? '…' : count(data?.total_students)}
              icon={GraduationCap}
              to={can('students:read') ? '/students' : undefined}
            />
            <StatCard
              label="Active courses"
              value={summary.loading ? '…' : count(data?.total_courses)}
              icon={BookOpen}
              to={can('courses:read') ? '/courses' : undefined}
            />
            <StatCard
              label="Enrolments"
              value={summary.loading ? '…' : count(data?.total_enrollments)}
              icon={Users}
              hint={data ? `across ${count(data.total_departments)} departments` : undefined}
            />
            <StatCard
              label="Open alerts"
              value={summary.loading ? '…' : count(data?.open_alerts)}
              icon={BellRing}
              accent={data?.open_alerts > 0 ? 'high' : 'neutral'}
              to={can('alerts:read') ? '/alerts?only_open=true' : undefined}
            />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="High risk"
              value={summary.loading ? '…' : count(data?.high_risk)}
              icon={ShieldAlert}
              accent="high"
              hint="score 60-100"
              to={can('risk:read') ? '/risk?risk_category=HIGH' : undefined}
            />
            <StatCard
              label="Medium risk"
              value={summary.loading ? '…' : count(data?.medium_risk)}
              icon={TrendingUp}
              accent="medium"
              hint="score 30-59"
              to={can('risk:read') ? '/risk?risk_category=MEDIUM' : undefined}
            />
            <StatCard
              label="Average attendance"
              value={summary.loading ? '…' : percent(data?.avg_attendance_percentage)}
              icon={CalendarCheck}
              accent="brand"
              hint="across active enrolments"
            />
            <StatCard
              label="Average assessment"
              value={summary.loading ? '…' : percent(data?.avg_assessment_percentage)}
              icon={ClipboardList}
              accent="brand"
              hint="graded work only"
            />
          </div>

          <div className="mt-6 grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2 space-y-4">
              <Card
                title="Academic performance and attendance over time"
                description="Monthly means across all graded assessments and recorded sessions."
                bodyClassName="p-0"
              >
                {trend.loading ? (
                  <ChartSkeleton />
                ) : trend.error ? (
                  <ErrorState error={trend.error} onRetry={trend.reload} />
                ) : (
                  <TrendChart points={trend.data} />
                )}
              </Card>

              <Card
                title="Risk by department"
                description="Enrolments in each band, per department."
                bodyClassName="p-0"
              >
                {byDepartment.loading ? (
                  <ChartSkeleton height={180} />
                ) : byDepartment.error ? (
                  <ErrorState error={byDepartment.error} onRetry={byDepartment.reload} />
                ) : (
                  <GroupedRiskChart rows={byDepartment.data} />
                )}
              </Card>
            </div>

            <div className="space-y-4">
              <Card
                title="Risk distribution"
                description="Share of active enrolments in each band."
                bodyClassName="p-0"
              >
                {summary.loading ? (
                  <ChartSkeleton height={120} />
                ) : (
                  <RiskDistributionChart distribution={data?.risk_distribution} />
                )}
              </Card>

              <Card
                title="Other signals"
                bodyClassName="divide-y divide-slate-100"
              >
                <dl>
                  {[
                    {
                      label: 'Low-risk enrolments',
                      value: count(data?.low_risk),
                      icon: ShieldAlert,
                    },
                    {
                      label: 'Awaiting more data',
                      value: count(data?.insufficient_data),
                      icon: GraduationCap,
                      hint: 'not enough attendance or graded work to score yet',
                    },
                    {
                      label: 'Open interventions',
                      value: count(data?.open_interventions),
                      icon: LifeBuoy,
                    },
                    {
                      label: 'Assessments due in 7 days',
                      value: count(data?.assessments_due_next_7_days),
                      icon: ClipboardList,
                    },
                  ].map((row) => (
                    <div
                      key={row.label}
                      className="flex items-start justify-between gap-3 px-5 py-3"
                    >
                      <div className="min-w-0">
                        <dt className="text-sm text-slate-600">{row.label}</dt>
                        {row.hint && <p className="mt-0.5 text-xs text-slate-400">{row.hint}</p>}
                      </div>
                      <dd className="shrink-0 text-sm font-bold tabular-nums text-slate-900">
                        {summary.loading ? '…' : row.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Card>
            </div>
          </div>

          {can('alerts:read') && (
            <Card
              title="Recent risk alerts"
              description="Highest risk first."
              bodyClassName="p-0"
              actions={
                <Link to="/alerts" className="btn-secondary px-2.5 py-1.5 text-xs">
                  View all
                </Link>
              }
              className="mt-6"
            >
              <div className="mt-0">
                {alerts.loading ? (
                  <LoadingState rows={4} />
                ) : alerts.error ? (
                  <ErrorState error={alerts.error} onRetry={alerts.reload} />
                ) : !alerts.data?.length ? (
                  <EmptyState
                    title="No open alerts"
                    description="Nobody has crossed the early-warning threshold. Recalculate risk after new data is entered."
                    icon={BellRing}
                  />
                ) : (
                  <ul className="divide-y divide-slate-100">
                    {alerts.data.map((alert) => (
                      <li key={alert.alert_id}>
                        <Link
                          to={`/alerts?focus=${alert.alert_id}`}
                          className="flex flex-wrap items-start justify-between gap-3 px-5 py-3.5 transition hover:bg-slate-50"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-semibold text-slate-800">
                                {alert.student_name}
                              </span>
                              <span className="font-mono text-xs text-slate-500">
                                {alert.student_id}
                              </span>
                              <Badge tone="neutral">{alert.course_code}</Badge>
                            </div>
                            {alert.triggering_factors && (
                              <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                                {alert.triggering_factors}
                              </p>
                            )}
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1.5">
                            <RiskBadge category={alert.risk_category} score={alert.risk_score} />
                            <div className="flex items-center gap-2">
                              <Badge tone={ALERT_STATUS_TONE[alert.status]}>
                                {ALERT_STATUS_LABELS[alert.status]}
                              </Badge>
                              <span className="text-xs text-slate-400">
                                {relativeDays(alert.created_at)}
                              </span>
                            </div>
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          )}
        </>
      )}
    </>
  )
}
