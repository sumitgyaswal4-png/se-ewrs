/** One student's full profile: summary, per-course rows, risk and history. */

import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, BookOpen, CalendarCheck, ClipboardList, Mail, Phone } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Meter from '../components/Meter.jsx'
import PageHeader from '../components/PageHeader.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import StatCard from '../components/StatCard.jsx'
import { ChartSkeleton, ErrorState, LoadingState } from '../components/States.jsx'
import TrendChart from '../components/charts/TrendChart.jsx'
import { useQuery } from '../hooks/useApi.js'
import { assessmentApi, studentApi } from '../services/endpoints.js'
import { meterColor } from '../utils/charts.js'
import { count, dateTime, percent, relativeDays } from '../utils/format.js'

export default function StudentProfilePage() {
  const { studentPk } = useParams()
  const profile = useQuery(() => studentApi.profile(studentPk), [studentPk])
  const trend = useQuery(() => assessmentApi.trends({ student_pk: studentPk }), [studentPk])

  if (profile.loading) {
    return (
      <div className="card">
        <LoadingState rows={6} label="Loading student profile" />
      </div>
    )
  }
  if (profile.error) {
    return (
      <div className="card">
        <ErrorState error={profile.error} onRetry={profile.reload} />
      </div>
    )
  }

  const { student, summary, courses, thresholds } = profile.data

  const columns = [
    {
      key: 'course',
      header: 'Course',
      render: (row) => (
        <div className="min-w-0">
          <span className="block font-semibold text-slate-800">{row.course_code}</span>
          <span className="block truncate text-xs text-slate-500">{row.course_name}</span>
        </div>
      ),
    },
    {
      key: 'enrollment',
      header: 'Enrolment',
      render: (row) => (
        <Badge tone={row.enrollment_status === 'ACTIVE' ? 'success' : 'neutral'}>
          {row.enrollment_status}
        </Badge>
      ),
    },
    {
      key: 'attendance',
      header: 'Attendance',
      align: 'right',
      render: (row) => (
        <div className="tabular-nums">
          <span className="font-semibold">{percent(row.attendance_percentage, 0)}</span>
          <span className="block text-xs text-slate-400">
            {row.sessions_attended}/{row.sessions_held} sessions
          </span>
        </div>
      ),
    },
    {
      key: 'assessment',
      header: 'Assessment',
      align: 'right',
      render: (row) => (
        <div className="tabular-nums">
          <span className="font-semibold">{percent(row.avg_assessment_percentage, 0)}</span>
          <span className="block text-xs text-slate-400">
            {row.graded_assessments} graded
          </span>
        </div>
      ),
    },
    {
      key: 'submissions',
      header: 'Submissions',
      render: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.late_submissions > 0 && (
            <Badge tone="warning">{row.late_submissions} late</Badge>
          )}
          {row.missing_submissions > 0 && (
            <Badge tone="danger">{row.missing_submissions} missing</Badge>
          )}
          {row.late_submissions === 0 && row.missing_submissions === 0 && (
            <span className="text-xs text-slate-400">all on time</span>
          )}
        </div>
      ),
    },
    {
      key: 'risk',
      header: 'Risk',
      render: (row) => <RiskBadge category={row.risk_category} score={row.risk_score} size="sm" />,
    },
    {
      key: 'open',
      header: '',
      align: 'right',
      render: (row) => (
        <Link
          to={`/risk/${row.enrollment_id}`}
          className="btn-ghost px-2 py-1 text-xs text-brand-700"
        >
          Risk detail
        </Link>
      ),
    },
  ]

  return (
    <>
      <Link
        to="/students"
        className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to students
      </Link>

      <PageHeader
        title={student.full_name}
        description={
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="font-mono text-xs">{student.student_id}</span>
            <span className="inline-flex items-center gap-1.5">
              <Mail className="h-3.5 w-3.5" aria-hidden="true" />
              {student.email}
            </span>
            {student.phone && (
              <span className="inline-flex items-center gap-1.5">
                <Phone className="h-3.5 w-3.5" aria-hidden="true" />
                {student.phone}
              </span>
            )}
          </span>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{student.dept_code}</Badge>
            <Badge tone="brand">Semester {student.semester}</Badge>
            <Badge tone="neutral">Enrolled {student.enrollment_year}</Badge>
            {student.is_active ? (
              <Badge tone="success">Active</Badge>
            ) : (
              <Badge tone="danger">Inactive</Badge>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Enrolled courses"
          value={count(summary.enrolled_courses)}
          icon={BookOpen}
        />
        <StatCard
          label="Mean attendance"
          value={percent(summary.attendance_percentage)}
          icon={CalendarCheck}
        />
        <StatCard
          label="Mean assessment"
          value={percent(summary.avg_assessment_percentage)}
          icon={ClipboardList}
        />
        <StatCard
          label="Open alerts"
          value={count(summary.open_alerts)}
          accent={summary.open_alerts > 0 ? 'high' : 'neutral'}
          hint={
            summary.highest_risk_category
              ? `highest band: ${summary.highest_risk_category.toLowerCase().replace('_', ' ')}`
              : 'not scored yet'
          }
        />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        <Card title="Engagement summary" className="xl:col-span-1">
          <div className="space-y-4 p-5">
            <Meter
              label="Attendance"
              value={summary.attendance_percentage}
              color={meterColor(summary.attendance_percentage, thresholds)}
              hint="Mean across all enrolled courses"
            />
            <Meter
              label="Assessment average"
              value={summary.avg_assessment_percentage}
              color={meterColor(summary.avg_assessment_percentage, thresholds)}
              hint="Graded work only; ungraded items are excluded"
            />
            <dl className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-sm">
              <div>
                <dt className="text-xs text-slate-500">Late submissions</dt>
                <dd className="font-bold tabular-nums text-slate-900">
                  {summary.late_submissions}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Missing submissions</dt>
                <dd className="font-bold tabular-nums text-slate-900">
                  {summary.missing_submissions}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-slate-500">Last LMS activity</dt>
                <dd className="text-sm font-semibold text-slate-900">
                  {relativeDays(summary.last_activity_at)}
                  <span className="ml-1.5 text-xs font-normal text-slate-500">
                    {summary.last_activity_at ? `(${dateTime(summary.last_activity_at)})` : ''}
                  </span>
                </dd>
              </div>
            </dl>
          </div>
        </Card>

        <Card
          title="Assessment performance over time"
          description="This student's monthly mean across graded work."
          bodyClassName="p-0"
          className="xl:col-span-2"
        >
          {trend.loading ? (
            <ChartSkeleton height={220} />
          ) : trend.error ? (
            <ErrorState error={trend.error} onRetry={trend.reload} />
          ) : (
            <TrendChart points={trend.data} height={240} />
          )}
        </Card>
      </div>

      <Card
        title="Enrolled courses"
        description="Attendance, grades and current risk per course."
        bodyClassName="p-0"
        className="mt-6"
      >
        <DataTable
          columns={columns}
          rows={courses}
          rowKey={(row) => row.enrollment_id}
          caption={`Courses ${student.full_name} is enrolled in`}
          emptyTitle="Not enrolled in any course"
          emptyDescription="Enrol this student from the Courses page to start tracking engagement."
        />
      </Card>
    </>
  )
}
