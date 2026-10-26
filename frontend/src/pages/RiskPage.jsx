/** The risk-analysis table. */

import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { RefreshCw, ShieldAlert } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import SearchInput from '../components/SearchInput.jsx'
import { FilterSelect } from '../components/Form.jsx'
import { useDebounced, useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { lookupApi, riskApi } from '../services/endpoints.js'
import { RISK_LABELS, SEMESTERS } from '../utils/constants.js'
import { dateOnly, percent, relativeDays, score, splitFactors } from '../utils/format.js'

export default function RiskPage() {
  const { can } = useAuth()
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [coursePk, setCoursePk] = useState(searchParams.get('course_pk'))
  const [deptId, setDeptId] = useState(searchParams.get('dept_id'))
  const [semester, setSemester] = useState(searchParams.get('semester'))
  const [riskCategory, setRiskCategory] = useState(searchParams.get('risk_category'))
  const [hasAlert, setHasAlert] = useState(null)
  const [sortBy, setSortBy] = useState('risk_score')
  const [sortDir, setSortDir] = useState('desc')

  const courses = useQuery(() => lookupApi.courseOptions(), [])
  const departments = useQuery(() => lookupApi.departments(), [])

  const params = useMemo(
    () => ({
      page,
      page_size: pageSize,
      search: debouncedSearch || undefined,
      course_pk: coursePk || undefined,
      dept_id: deptId || undefined,
      semester: semester || undefined,
      risk_category: riskCategory || undefined,
      has_open_alert: hasAlert === null ? undefined : hasAlert === 'true',
      sort_by: sortBy,
      sort_dir: sortDir,
    }),
    [page, pageSize, debouncedSearch, coursePk, deptId, semester, riskCategory, hasAlert, sortBy, sortDir],
  )
  const rows = useQuery(() => riskApi.list(params), [JSON.stringify(params)])

  const recalculate = useMutation(() =>
    riskApi.recalculate(coursePk ? { course_pk: Number(coursePk) } : {}),
  )

  async function onRecalculate() {
    try {
      const result = await recalculate.run()
      toast.success(result.detail)
      rows.reload()
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
      sortKey: 'student_name',
      render: (row) => (
        <Link to={`/risk/${row.enrollment_id}`} className="group block min-w-0">
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
      sortKey: 'course_code',
      render: (row) => (
        <div className="min-w-0">
          <Badge tone="neutral">{row.course_code}</Badge>
          <span className="mt-0.5 block truncate text-xs text-slate-500">{row.course_name}</span>
        </div>
      ),
    },
    {
      key: 'score',
      header: 'Risk score',
      sortKey: 'risk_score',
      align: 'right',
      render: (row) => (
        <div className="flex flex-col items-end gap-1">
          <span className="text-lg font-bold tabular-nums text-slate-900">
            {score(row.risk_score, 1)}
          </span>
          <RiskBadge category={row.risk_category} size="sm" />
        </div>
      ),
    },
    {
      key: 'attendance',
      header: 'Attendance',
      align: 'right',
      render: (row) => (
        <div className="tabular-nums">
          <span className={row.attendance_percentage < 75 ? 'font-semibold text-risk-high' : ''}>
            {percent(row.attendance_percentage, 0)}
          </span>
          <span className="block text-xs text-slate-400">
            {row.sessions_attended}/{row.sessions_held}
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
          <span
            className={row.avg_assessment_percentage < 50 ? 'font-semibold text-risk-high' : ''}
          >
            {percent(row.avg_assessment_percentage, 0)}
          </span>
          <span className="block text-xs text-slate-400">{row.graded_assessments} graded</span>
        </div>
      ),
    },
    {
      key: 'submissions',
      header: 'Submissions',
      render: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.late_submissions > 0 && <Badge tone="warning">{row.late_submissions} late</Badge>}
          {row.missing_submissions > 0 && (
            <Badge tone="danger">{row.missing_submissions} missing</Badge>
          )}
          {!row.late_submissions && !row.missing_submissions && (
            <span className="text-xs text-slate-400">none</span>
          )}
        </div>
      ),
    },
    {
      key: 'activity',
      header: 'Recent LMS activity',
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
          <span className="block text-xs text-slate-400">
            {row.login_count_30d} logins / 30d
          </span>
        </div>
      ),
    },
    {
      key: 'factors',
      header: 'Main factors',
      render: (row) => {
        const factors = splitFactors(row.contributing_factors)
        if (row.risk_category === 'INSUFFICIENT_DATA') {
          return (
            <span className="text-xs text-slate-500">
              {row.missing_data_reasons ?? 'Needs more data'}
            </span>
          )
        }
        if (!factors.length || factors[0] === 'No adverse factors detected') {
          return <span className="text-xs text-slate-400">none detected</span>
        }
        return (
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
        )
      },
    },
    {
      key: 'last_assessment',
      header: 'Latest assessment',
      render: (row) => (
        <span className="text-xs text-slate-500">{dateOnly(row.last_assessment_date)}</span>
      ),
    },
    {
      key: 'alert',
      header: 'Alert',
      render: (row) =>
        row.open_alert_id ? (
          <Link to={`/alerts?focus=${row.open_alert_id}`} className="inline-block">
            <Badge tone="danger">{row.open_alert_status}</Badge>
          </Link>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Student risk analysis"
        description="The latest score for every active enrolment, with the figures behind it."
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
              {recalculate.pending
                ? 'Recalculating…'
                : coursePk
                  ? 'Recalculate this course'
                  : 'Recalculate all'}
            </button>
          )
        }
      />

      <div className="mb-4 flex items-start gap-3 rounded-xl border border-brand-200 bg-brand-50 p-4">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-brand-700" aria-hidden="true" />
        <p className="text-sm text-brand-900">
          <span className="font-semibold">
            Risk Score = 0.35 × Attendance Risk + 0.40 × Academic Risk + 0.25 × Engagement Risk.
          </span>{' '}
          A score is an early-warning indicator for starting a conversation, not a
          judgement about a student. Where an input is missing, that component is
          dropped and the remaining weights are re-normalised — a student with no
          graded work yet is reported as <em>needs more data</em>, never as high risk.
        </p>
      </div>

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Student or course"
            label="Search risk table"
            className="min-w-[13rem] flex-1"
          />
          <FilterSelect
            label="Risk band"
            value={riskCategory}
            onChange={updateFilter(setRiskCategory, 'risk_category')}
            options={Object.entries(RISK_LABELS).map(([value, label]) => ({ value, label }))}
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
          <FilterSelect
            label="Department"
            value={deptId}
            onChange={updateFilter(setDeptId, 'dept_id')}
            options={(departments.data ?? []).map((dept) => ({
              value: String(dept.dept_id),
              label: dept.dept_code,
            }))}
          />
          <FilterSelect
            label="Semester"
            value={semester}
            onChange={updateFilter(setSemester, 'semester')}
            options={SEMESTERS.map((value) => ({ value: String(value), label: `Sem ${value}` }))}
          />
          <FilterSelect
            label="Open alert"
            value={hasAlert}
            onChange={(value) => {
              setHasAlert(value)
              setPage(1)
            }}
            options={[
              { value: 'true', label: 'Has an alert' },
              { value: 'false', label: 'No alert' },
            ]}
          />
        </div>

        <DataTable
          columns={columns}
          rows={rows.data?.items}
          rowKey={(row) => row.enrollment_id}
          loading={rows.loading}
          error={rows.error}
          onRetry={rows.reload}
          sortBy={sortBy}
          sortDir={sortDir}
          onSort={(column, direction) => {
            setSortBy(column)
            setSortDir(direction)
            setPage(1)
          }}
          caption="Risk scores per student and course"
          emptyTitle="No enrolments match these filters"
          emptyDescription="Clear a filter, or recalculate risk if no scores have been produced yet."
        />

        {rows.data?.total > 0 && (
          <div className="border-t border-slate-200 px-4 py-3">
            <Pagination
              page={rows.data.page}
              pageSize={rows.data.page_size}
              total={rows.data.total}
              pages={rows.data.pages}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
            />
          </div>
        )}
      </Card>
    </>
  )
}
