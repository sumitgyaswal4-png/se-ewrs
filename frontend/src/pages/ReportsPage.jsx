/** Reports and analytics.
 *
 * Every report is computed by SQL in the backend; this page only applies
 * filters and renders. The same figures are always available as a table
 * next to the chart, and each one exports to CSV.
 */

import { useMemo, useState } from 'react'
import { Download, FileBarChart } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { FilterDate, FilterSelect } from '../components/Form.jsx'
import { ChartSkeleton, ErrorState } from '../components/States.jsx'
import GroupedRiskChart from '../components/charts/GroupedRiskChart.jsx'
import SubmissionChart from '../components/charts/SubmissionChart.jsx'
import { useMutation, useQuery } from '../hooks/useApi.js'
import { useToast } from '../hooks/useToast.jsx'
import { lookupApi, reportApi } from '../services/endpoints.js'
import { RISK_LABELS, SEMESTERS } from '../utils/constants.js'
import { dateTime, humanise, percent, score } from '../utils/format.js'

const REPORTS = [
  { id: 'risk-distribution', label: 'Risk distribution' },
  { id: 'course-performance', label: 'Course performance' },
  { id: 'course-attendance', label: 'Course attendance' },
  { id: 'submission-patterns', label: 'Submission patterns' },
  { id: 'high-risk-students', label: 'At-risk students' },
  { id: 'department-risk', label: 'Department summary' },
  { id: 'intervention-outcomes', label: 'Intervention outcomes' },
]

export default function ReportsPage() {
  const toast = useToast()

  const [report, setReport] = useState('risk-distribution')
  const [groupBy, setGroupBy] = useState('category')
  const [coursePk, setCoursePk] = useState(null)
  const [deptId, setDeptId] = useState(null)
  const [semester, setSemester] = useState(null)
  const [dateFrom, setDateFrom] = useState(null)
  const [dateTo, setDateTo] = useState(null)

  const courses = useQuery(() => lookupApi.courseOptions(), [])
  const departments = useQuery(() => lookupApi.departments(), [])

  const filters = useMemo(
    () => ({
      group_by: groupBy,
      course_pk: coursePk || undefined,
      dept_id: deptId || undefined,
      semester: semester || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
    [groupBy, coursePk, deptId, semester, dateFrom, dateTo],
  )

  const data = useQuery(() => {
    switch (report) {
      case 'risk-distribution':
        return reportApi.riskDistribution(filters)
      case 'course-performance':
        return reportApi.coursePerformance(filters)
      case 'course-attendance':
        return reportApi.courseAttendance(filters)
      case 'submission-patterns':
        return reportApi.submissionPatterns(filters)
      case 'high-risk-students':
        return reportApi.highRiskStudents(filters)
      case 'department-risk':
        return reportApi.departmentRisk()
      case 'intervention-outcomes':
        return reportApi.interventionOutcomes(filters)
      default:
        return Promise.resolve([])
    }
  }, [report, JSON.stringify(filters)])

  const exportCsv = useMutation(() => reportApi.exportCsv(report, filters))

  async function onExport() {
    try {
      await exportCsv.run()
      toast.success('CSV downloaded')
    } catch (error) {
      toast.error(error.message)
    }
  }

  const courseOptions = (courses.data ?? []).map((course) => ({
    value: String(course.course_pk),
    label: course.label,
  }))
  const deptOptions = (departments.data ?? []).map((dept) => ({
    value: String(dept.dept_id),
    label: `${dept.dept_code} — ${dept.dept_name}`,
  }))

  const COLUMNS = {
    'risk-distribution': [
      { key: 'group', header: 'Group', render: (r) => <span className="font-medium">{r.group_label}</span> },
      { key: 'total', header: 'Total', align: 'right', render: (r) => <span className="tabular-nums">{r.total}</span> },
      { key: 'high', header: 'High', align: 'right', render: (r) => (r.high_risk ? <Badge tone="danger">{r.high_risk}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'medium', header: 'Medium', align: 'right', render: (r) => (r.medium_risk ? <Badge tone="warning">{r.medium_risk}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'low', header: 'Low', align: 'right', render: (r) => (r.low_risk ? <Badge tone="success">{r.low_risk}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'insufficient', header: 'Needs data', align: 'right', render: (r) => <span className="tabular-nums text-slate-500">{r.insufficient_data}</span> },
      { key: 'avg', header: 'Mean score', align: 'right', render: (r) => <span className="font-semibold tabular-nums">{score(r.avg_risk_score, 1)}</span> },
    ],
    'course-performance': [
      { key: 'course', header: 'Course', render: (r) => (<div><span className="block font-semibold">{r.course_code}</span><span className="block text-xs text-slate-500">{r.course_name}</span></div>) },
      { key: 'dept', header: 'Dept', render: (r) => <Badge tone="neutral">{r.dept_code}</Badge> },
      { key: 'sem', header: 'Sem', align: 'right', render: (r) => <span className="tabular-nums">{r.semester}</span> },
      { key: 'students', header: 'Students', align: 'right', render: (r) => <span className="tabular-nums">{r.enrolled_students}</span> },
      { key: 'assessments', header: 'Assessments', align: 'right', render: (r) => <span className="tabular-nums">{r.assessment_count}</span> },
      { key: 'graded', header: 'Graded', align: 'right', render: (r) => <span className="tabular-nums">{r.graded_results}</span> },
      { key: 'avg', header: 'Avg marks', align: 'right', render: (r) => <span className="font-semibold tabular-nums">{percent(r.avg_percentage, 1)}</span> },
      { key: 'pass', header: 'Pass rate', align: 'right', render: (r) => <span className="tabular-nums">{percent(r.pass_rate_percentage, 1)}</span> },
      { key: 'attendance', header: 'Attendance', align: 'right', render: (r) => <span className="tabular-nums">{percent(r.avg_attendance_percentage, 1)}</span> },
      { key: 'high', header: 'High risk', align: 'right', render: (r) => (r.high_risk_count ? <Badge tone="danger">{r.high_risk_count}</Badge> : <span className="text-slate-400">0</span>) },
    ],
    'course-attendance': [
      { key: 'course', header: 'Course', render: (r) => (<div><span className="block font-semibold">{r.course_code}</span><span className="block text-xs text-slate-500">{r.course_name}</span></div>) },
      { key: 'dept', header: 'Dept', render: (r) => <Badge tone="neutral">{r.dept_code}</Badge> },
      { key: 'students', header: 'Students', align: 'right', render: (r) => <span className="tabular-nums">{r.enrolled_students}</span> },
      { key: 'held', header: 'Sessions held', align: 'right', render: (r) => <span className="tabular-nums">{r.total_sessions_held}</span> },
      { key: 'attended', header: 'Attended', align: 'right', render: (r) => <span className="tabular-nums">{r.total_sessions_attended}</span> },
      { key: 'rate', header: 'Attendance', align: 'right', render: (r) => (<span className={`font-semibold tabular-nums ${r.avg_attendance_percentage < 75 ? 'text-risk-high' : ''}`}>{percent(r.avg_attendance_percentage, 1)}</span>) },
      { key: 'below', header: 'Below 75%', align: 'right', render: (r) => (r.students_below_75 ? <Badge tone="warning">{r.students_below_75}</Badge> : <span className="text-slate-400">0</span>) },
    ],
    'submission-patterns': [
      { key: 'assessment', header: 'Assessment', render: (r) => (<div><span className="block font-semibold">{r.assessment_title}</span><span className="block text-xs text-slate-500">{r.course_code} · {humanise(r.assessment_type)}</span></div>) },
      { key: 'due', header: 'Deadline', render: (r) => <span className="text-xs text-slate-600">{dateTime(r.due_at)}</span> },
      { key: 'expected', header: 'Expected', align: 'right', render: (r) => <span className="tabular-nums">{r.total_expected}</span> },
      { key: 'ontime', header: 'On time', align: 'right', render: (r) => <span className="tabular-nums">{r.on_time}</span> },
      { key: 'late', header: 'Late', align: 'right', render: (r) => (r.late ? <Badge tone="warning">{r.late}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'missing', header: 'Missing', align: 'right', render: (r) => (r.missing ? <Badge tone="danger">{r.missing}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'rate', header: 'On-time rate', align: 'right', render: (r) => <span className="font-semibold tabular-nums">{percent(r.on_time_rate, 1)}</span> },
      { key: 'avg', header: 'Avg marks', align: 'right', render: (r) => <span className="tabular-nums">{percent(r.avg_percentage, 1)}</span> },
    ],
    'high-risk-students': [
      { key: 'student', header: 'Student', render: (r) => (<div><span className="block font-semibold">{r.student_name}</span><span className="block font-mono text-xs text-slate-500">{r.student_id}</span></div>) },
      { key: 'dept', header: 'Dept', render: (r) => <Badge tone="neutral">{r.dept_code}</Badge> },
      { key: 'sem', header: 'Sem', align: 'right', render: (r) => <span className="tabular-nums">{r.semester}</span> },
      { key: 'count', header: 'At-risk courses', align: 'right', render: (r) => <Badge tone={r.at_risk_courses > 1 ? 'danger' : 'warning'}>{r.at_risk_courses}</Badge> },
      { key: 'courses', header: 'Courses', render: (r) => <span className="text-xs text-slate-600">{r.courses}</span> },
      { key: 'avg', header: 'Mean score', align: 'right', render: (r) => <span className="tabular-nums">{score(r.avg_risk_score, 1)}</span> },
      { key: 'max', header: 'Worst score', align: 'right', render: (r) => <span className="font-semibold tabular-nums">{score(r.max_risk_score, 1)}</span> },
      { key: 'alerts', header: 'Open alerts', align: 'right', render: (r) => (r.open_alerts ? <Badge tone="danger">{r.open_alerts}</Badge> : <span className="text-slate-400">0</span>) },
    ],
    'department-risk': [
      { key: 'dept', header: 'Department', render: (r) => (<div><span className="block font-semibold">{r.dept_code}</span><span className="block text-xs text-slate-500">{r.dept_name}</span></div>) },
      { key: 'students', header: 'Students', align: 'right', render: (r) => <span className="tabular-nums">{r.students_tracked}</span> },
      { key: 'enrolments', header: 'Enrolments', align: 'right', render: (r) => <span className="tabular-nums">{r.enrollments_tracked}</span> },
      { key: 'high', header: 'High', align: 'right', render: (r) => (r.high_risk ? <Badge tone="danger">{r.high_risk}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'medium', header: 'Medium', align: 'right', render: (r) => (r.medium_risk ? <Badge tone="warning">{r.medium_risk}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'low', header: 'Low', align: 'right', render: (r) => (r.low_risk ? <Badge tone="success">{r.low_risk}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'avg', header: 'Mean score', align: 'right', render: (r) => <span className="tabular-nums">{score(r.avg_risk_score, 1)}</span> },
      { key: 'attendance', header: 'Attendance', align: 'right', render: (r) => <span className="tabular-nums">{percent(r.avg_attendance_percentage, 1)}</span> },
      { key: 'assessment', header: 'Assessment', align: 'right', render: (r) => <span className="tabular-nums">{percent(r.avg_assessment_percentage, 1)}</span> },
      { key: 'alerts', header: 'Open alerts', align: 'right', render: (r) => <span className="tabular-nums">{r.open_alerts}</span> },
    ],
    'intervention-outcomes': [
      { key: 'type', header: 'Intervention type', render: (r) => <Badge tone="brand">{humanise(r.intervention_type)}</Badge> },
      { key: 'total', header: 'Total', align: 'right', render: (r) => <span className="tabular-nums">{r.total}</span> },
      { key: 'improved', header: 'Improved', align: 'right', render: (r) => (r.improved ? <Badge tone="success">{r.improved}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'no_change', header: 'No change', align: 'right', render: (r) => <span className="tabular-nums">{r.no_change}</span> },
      { key: 'pending', header: 'Pending', align: 'right', render: (r) => <span className="tabular-nums">{r.pending}</span> },
      { key: 'escalated', header: 'Escalated', align: 'right', render: (r) => (r.escalated ? <Badge tone="danger">{r.escalated}</Badge> : <span className="text-slate-400">0</span>) },
      { key: 'rate', header: 'Improvement rate', align: 'right', render: (r) => <span className="font-semibold tabular-nums">{percent(r.improvement_rate, 1)}</span> },
      { key: 'risk', header: 'Mean current risk', align: 'right', render: (r) => <span className="tabular-nums">{score(r.avg_current_risk, 1)}</span> },
    ],
  }

  const activeReport = REPORTS.find((item) => item.id === report)
  const showsFilters = report !== 'department-risk'

  return (
    <>
      <PageHeader
        title="Reports and analytics"
        description="Database-driven reports. Every figure is aggregated by SQL from the recorded data."
        actions={
          <button
            type="button"
            onClick={onExport}
            className="btn-secondary"
            disabled={exportCsv.pending}
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {exportCsv.pending ? 'Preparing…' : 'Export CSV'}
          </button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Report">
        {REPORTS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={report === item.id}
            onClick={() => setReport(item.id)}
            className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
              report === item.id
                ? 'border-brand-600 bg-brand-600 text-white'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {showsFilters && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-end gap-3 p-4">
            {report === 'risk-distribution' && (
              <FilterSelect
                label="Group by"
                value={groupBy}
                onChange={(value) => setGroupBy(value ?? 'category')}
                options={[
                  { value: 'category', label: 'Risk band' },
                  { value: 'semester', label: 'Semester' },
                  { value: 'department', label: 'Department' },
                  { value: 'course', label: 'Course' },
                ]}
                placeholder="Risk band"
              />
            )}
            <FilterSelect label="Course" value={coursePk} onChange={setCoursePk} options={courseOptions} />
            <FilterSelect label="Department" value={deptId} onChange={setDeptId} options={deptOptions} />
            <FilterSelect
              label="Semester"
              value={semester}
              onChange={setSemester}
              options={SEMESTERS.map((value) => ({ value: String(value), label: `Sem ${value}` }))}
            />
            <FilterDate label="From" value={dateFrom} onChange={setDateFrom} />
            <FilterDate label="To" value={dateTo} onChange={setDateTo} />
            {(coursePk || deptId || semester || dateFrom || dateTo) && (
              <button
                type="button"
                onClick={() => {
                  setCoursePk(null)
                  setDeptId(null)
                  setSemester(null)
                  setDateFrom(null)
                  setDateTo(null)
                }}
                className="btn-ghost pb-1.5 text-xs"
              >
                Clear filters
              </button>
            )}
          </div>
        </Card>
      )}

      {/* Chart first where one helps, table always. */}
      {(report === 'risk-distribution' || report === 'department-risk') && (
        <Card
          title={report === 'department-risk' ? 'Risk bands per department' : 'Risk bands per group'}
          bodyClassName="p-0"
          className="mb-4"
        >
          {data.loading ? (
            <ChartSkeleton height={200} />
          ) : data.error ? (
            <ErrorState error={data.error} onRetry={data.reload} />
          ) : (
            <GroupedRiskChart
              rows={
                report === 'department-risk'
                  ? (data.data ?? []).map((row) => ({ ...row, group_label: row.dept_code }))
                  : data.data
              }
            />
          )}
        </Card>
      )}

      {report === 'submission-patterns' && (
        <Card title="On-time, late and missing submissions" bodyClassName="p-0" className="mb-4">
          {data.loading ? (
            <ChartSkeleton height={260} />
          ) : data.error ? (
            <ErrorState error={data.error} onRetry={data.reload} />
          ) : (
            <SubmissionChart rows={data.data} />
          )}
        </Card>
      )}

      <Card
        title={activeReport?.label}
        description="The same figures as the chart, as a table."
        bodyClassName="p-0"
      >
        <DataTable
          columns={COLUMNS[report]}
          rows={data.data}
          rowKey={(row, index) =>
            row.group_key ?? row.course_pk ?? row.student_pk ?? row.dept_id ??
            row.assessment_id ?? row.intervention_type ?? index
          }
          loading={data.loading}
          error={data.error}
          onRetry={data.reload}
          caption={activeReport?.label}
          emptyTitle="No rows matched these filters"
          emptyDescription="Widen the date range or clear a filter. Reports read live data, so an empty database gives an empty report."
        />
      </Card>

      <p className="mt-4 flex items-start gap-2 rounded-lg bg-slate-100 px-4 py-3 text-xs text-slate-600">
        <FileBarChart className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          Risk bands use a fixed status palette and always carry an icon and a label, so
          they stay readable without relying on colour. Every chart on this page has the
          matching table beside it.
        </span>
      </p>
    </>
  )
}
