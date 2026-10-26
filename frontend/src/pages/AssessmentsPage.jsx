/** Assessments: create items, enter marks for a class, review history. */

import { useMemo, useState } from 'react'
import { ClipboardList, Plus, Save } from 'lucide-react'

import Badge, { SUBMISSION_TONE } from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import { FilterSelect, SelectInput, TextInput } from '../components/Form.jsx'
import { ChartSkeleton, EmptyState, ErrorState, LoadingState } from '../components/States.jsx'
import TrendChart from '../components/charts/TrendChart.jsx'
import { useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { assessmentApi, lookupApi } from '../services/endpoints.js'
import { dateTime, humanise, percent } from '../utils/format.js'

const EMPTY_ASSESSMENT = {
  course_pk: '',
  title: '',
  assessment_type: 'ASSIGNMENT',
  max_marks: '20',
  weight_percent: '10',
  due_at: '',
}

export default function AssessmentsPage() {
  const { can } = useAuth()
  const toast = useToast()

  const [tab, setTab] = useState('assessments')
  const [coursePk, setCoursePk] = useState(null)
  const [assessmentType, setAssessmentType] = useState(null)
  const [page, setPage] = useState(1)

  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY_ASSESSMENT)
  const [formErrors, setFormErrors] = useState({})
  const [gradingFor, setGradingFor] = useState(null)
  const [grades, setGrades] = useState({})

  const courses = useQuery(() => lookupApi.courseOptions(), [])
  const enums = useQuery(() => lookupApi.enums(), [])

  const listParams = useMemo(
    () => ({
      page,
      page_size: 20,
      course_pk: coursePk || undefined,
      assessment_type: assessmentType || undefined,
    }),
    [page, coursePk, assessmentType],
  )
  const assessments = useQuery(
    () => assessmentApi.list(listParams),
    [JSON.stringify(listParams)],
    { enabled: tab === 'assessments' },
  )

  const resultParams = useMemo(
    () => ({ page, page_size: 25, course_pk: coursePk || undefined }),
    [page, coursePk],
  )
  const results = useQuery(
    () => assessmentApi.listResults(resultParams),
    [JSON.stringify(resultParams)],
    { enabled: tab === 'results' },
  )

  const trend = useQuery(
    () => assessmentApi.trends({ course_pk: coursePk || undefined }),
    [coursePk],
    { enabled: tab === 'trends' },
  )

  const grid = useQuery(
    () => assessmentApi.results(gradingFor.assessment_id),
    [gradingFor?.assessment_id],
    { enabled: Boolean(gradingFor) },
  )

  const create = useMutation((payload) => assessmentApi.create(payload))
  const saveGrades = useMutation((payload) => assessmentApi.bulkResults(payload))

  function validate() {
    const errors = {}
    if (!form.course_pk) errors.course_pk = 'Choose a course'
    if (form.title.trim().length < 2) errors.title = 'Enter a title'
    const max = Number(form.max_marks)
    if (!max || max <= 0) errors.max_marks = 'Maximum marks must be greater than zero'
    if (!form.due_at) errors.due_at = 'Set a deadline'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function onCreate(event) {
    event.preventDefault()
    if (!validate()) return
    try {
      await create.run({
        course_pk: Number(form.course_pk),
        title: form.title.trim(),
        assessment_type: form.assessment_type,
        max_marks: Number(form.max_marks),
        weight_percent: Number(form.weight_percent || 0),
        due_at: new Date(form.due_at).toISOString(),
      })
      toast.success('Assessment created')
      setCreating(false)
      setForm(EMPTY_ASSESSMENT)
      assessments.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  function openGrading(assessment) {
    setGrades({})
    setGradingFor(assessment)
  }

  async function onSaveGrades() {
    const rows = Object.entries(grades)
      .filter(([, value]) => value.marks !== '' || value.submitted)
      .map(([enrollmentId, value]) => ({
        enrollment_id: Number(enrollmentId),
        marks_obtained: value.marks === '' ? null : Number(value.marks),
        submitted_at: value.submitted ? new Date(value.submitted).toISOString() : null,
      }))

    if (!rows.length) {
      toast.error('Enter at least one mark')
      return
    }
    try {
      const result = await saveGrades.run({
        assessment_id: gradingFor.assessment_id,
        rows,
      })
      toast.success(result.detail)
      setGradingFor(null)
      assessments.reload()
      results.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const courseOptions = (courses.data ?? []).map((course) => ({
    value: String(course.course_pk),
    label: course.label,
  }))
  const typeOptions = enums.data?.assessment_types ?? []

  const assessmentColumns = [
    {
      key: 'title',
      header: 'Assessment',
      render: (row) => (
        <div className="min-w-0">
          <span className="block font-semibold text-slate-800">{row.title}</span>
          <span className="block text-xs text-slate-500">{row.course_name}</span>
        </div>
      ),
    },
    { key: 'course', header: 'Course', render: (row) => <Badge tone="neutral">{row.course_code}</Badge> },
    {
      key: 'type',
      header: 'Type',
      render: (row) => <Badge tone="brand">{humanise(row.assessment_type)}</Badge>,
    },
    {
      key: 'max',
      header: 'Max / weight',
      align: 'right',
      render: (row) => (
        <div className="tabular-nums">
          <span className="font-semibold">{row.max_marks}</span>
          <span className="block text-xs text-slate-400">{row.weight_percent}% of grade</span>
        </div>
      ),
    },
    {
      key: 'due',
      header: 'Deadline',
      render: (row) => <span className="text-xs text-slate-600">{dateTime(row.due_at)}</span>,
    },
    {
      key: 'graded',
      header: 'Graded',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">
          {row.graded_count}
          <span className="text-slate-400"> / {row.expected_count}</span>
        </span>
      ),
    },
    {
      key: 'avg',
      header: 'Class average',
      align: 'right',
      render: (row) => (
        <span className="font-semibold tabular-nums">{percent(row.avg_percentage, 1)}</span>
      ),
    },
    ...(can('results:write')
      ? [
          {
            key: 'actions',
            header: '',
            align: 'right',
            render: (row) => (
              <button
                type="button"
                onClick={() => openGrading(row)}
                className="btn-ghost px-2 py-1 text-xs text-brand-700"
              >
                Enter marks
              </button>
            ),
          },
        ]
      : []),
  ]

  const resultColumns = [
    {
      key: 'student',
      header: 'Student',
      render: (row) => (
        <div className="min-w-0">
          <span className="block text-sm font-medium text-slate-800">{row.student_name}</span>
          <span className="block font-mono text-xs text-slate-500">{row.student_id}</span>
        </div>
      ),
    },
    {
      key: 'assessment',
      header: 'Assessment',
      render: (row) => (
        <div className="min-w-0">
          <span className="block text-sm text-slate-800">{row.assessment_title}</span>
          <span className="block text-xs text-slate-500">
            {row.course_code} · {humanise(row.assessment_type)}
          </span>
        </div>
      ),
    },
    {
      key: 'marks',
      header: 'Marks',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">
          {row.marks_obtained === null ? (
            <span className="text-slate-400">not graded</span>
          ) : (
            <>
              <span className="font-semibold">{row.marks_obtained}</span>
              <span className="text-slate-400"> / {row.max_marks}</span>
            </>
          )}
        </span>
      ),
    },
    {
      key: 'percentage',
      header: 'Percentage',
      align: 'right',
      render: (row) => (
        <span
          className={`font-bold tabular-nums ${
            row.percentage === null
              ? 'text-slate-400'
              : row.percentage < 40
                ? 'text-risk-high'
                : 'text-slate-900'
          }`}
        >
          {percent(row.percentage, 1)}
        </span>
      ),
    },
    {
      key: 'submission',
      header: 'Submission',
      render: (row) => (
        <Badge tone={SUBMISSION_TONE[row.submission_status]}>
          {humanise(row.submission_status)}
        </Badge>
      ),
    },
    {
      key: 'submitted',
      header: 'Submitted at',
      render: (row) => (
        <span className="text-xs text-slate-500">
          {row.submitted_at ? dateTime(row.submitted_at) : '—'}
        </span>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Assessments"
        description="Assignments, quizzes and examinations, with marks entry and performance history."
        actions={
          can('assessments:write') && (
            <button type="button" onClick={() => setCreating(true)} className="btn-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
              New assessment
            </button>
          )
        }
      />

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <div role="tablist" aria-label="Assessment view" className="flex rounded-lg bg-slate-100 p-1">
            {[
              { id: 'assessments', label: 'Assessments' },
              { id: 'results', label: 'Results' },
              { id: 'trends', label: 'Trends' },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => {
                  setTab(item.id)
                  setPage(1)
                }}
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

          {tab === 'assessments' && (
            <FilterSelect
              label="Type"
              value={assessmentType}
              onChange={(value) => {
                setAssessmentType(value)
                setPage(1)
              }}
              options={typeOptions}
            />
          )}
        </div>

        {tab === 'assessments' && (
          <>
            <DataTable
              columns={assessmentColumns}
              rows={assessments.data?.items}
              rowKey={(row) => row.assessment_id}
              loading={assessments.loading}
              error={assessments.error}
              onRetry={assessments.reload}
              caption="Assessments with their grading progress"
              emptyTitle="No assessments yet"
              emptyDescription="Create an assignment, quiz or examination to start recording marks."
              emptyAction={
                can('assessments:write') && (
                  <button type="button" onClick={() => setCreating(true)} className="btn-primary">
                    <Plus className="h-4 w-4" aria-hidden="true" />
                    New assessment
                  </button>
                )
              }
            />
            {assessments.data?.total > 0 && (
              <div className="border-t border-slate-200 px-4 py-3">
                <Pagination
                  page={assessments.data.page}
                  pageSize={assessments.data.page_size}
                  total={assessments.data.total}
                  pages={assessments.data.pages}
                  onPageChange={setPage}
                />
              </div>
            )}
          </>
        )}

        {tab === 'results' && (
          <>
            <DataTable
              columns={resultColumns}
              rows={results.data?.items}
              rowKey={(row) => row.result_id}
              loading={results.loading}
              error={results.error}
              onRetry={results.reload}
              caption="Assessment results history"
              emptyTitle="No results recorded yet"
              emptyDescription="Enter marks against an assessment to populate this history."
            />
            {results.data?.total > 0 && (
              <div className="border-t border-slate-200 px-4 py-3">
                <Pagination
                  page={results.data.page}
                  pageSize={results.data.page_size}
                  total={results.data.total}
                  pages={results.data.pages}
                  onPageChange={setPage}
                />
              </div>
            )}
          </>
        )}

        {tab === 'trends' &&
          (trend.loading ? (
            <ChartSkeleton />
          ) : trend.error ? (
            <ErrorState error={trend.error} onRetry={trend.reload} />
          ) : (
            <TrendChart points={trend.data} />
          ))}
      </Card>

      {/* Create assessment */}
      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="Create an assessment"
        description="Marks entered later are validated against this maximum; percentages are derived by the database."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button
              type="submit"
              form="assessment-form"
              className="btn-primary"
              disabled={create.pending}
            >
              <ClipboardList className="h-4 w-4" aria-hidden="true" />
              {create.pending ? 'Creating…' : 'Create'}
            </button>
          </>
        }
      >
        <form id="assessment-form" onSubmit={onCreate} noValidate className="grid gap-4 sm:grid-cols-2">
          <SelectInput
            label="Course"
            required
            value={form.course_pk}
            onChange={(event) => setForm({ ...form, course_pk: event.target.value })}
            options={courseOptions}
            placeholder="Select a course"
            error={formErrors.course_pk}
          />
          <SelectInput
            label="Type"
            required
            value={form.assessment_type}
            onChange={(event) => setForm({ ...form, assessment_type: event.target.value })}
            options={typeOptions}
          />
          <TextInput
            label="Title"
            required
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            error={formErrors.title}
            hint="Must be unique within the course"
            className="sm:col-span-2"
          />
          <TextInput
            label="Maximum marks"
            type="number"
            required
            min={1}
            max={1000}
            step="0.5"
            value={form.max_marks}
            onChange={(event) => setForm({ ...form, max_marks: event.target.value })}
            error={formErrors.max_marks}
          />
          <TextInput
            label="Weight (% of final grade)"
            type="number"
            min={0}
            max={100}
            value={form.weight_percent}
            onChange={(event) => setForm({ ...form, weight_percent: event.target.value })}
          />
          <TextInput
            label="Deadline"
            type="datetime-local"
            required
            value={form.due_at}
            onChange={(event) => setForm({ ...form, due_at: event.target.value })}
            error={formErrors.due_at}
            hint="Submissions after this are marked LATE automatically"
            className="sm:col-span-2"
          />
        </form>
      </Modal>

      {/* Marks entry */}
      <Modal
        open={Boolean(gradingFor)}
        onClose={() => setGradingFor(null)}
        title={gradingFor ? `Enter marks — ${gradingFor.title}` : ''}
        description={
          gradingFor
            ? `Out of ${gradingFor.max_marks}. Leave a mark blank to record a submission without a grade; percentages are calculated for you. One out-of-range mark rejects the whole sheet.`
            : ''
        }
        size="lg"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setGradingFor(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={onSaveGrades}
              disabled={saveGrades.pending}
            >
              <Save className="h-4 w-4" aria-hidden="true" />
              {saveGrades.pending ? 'Saving…' : 'Save marks'}
            </button>
          </>
        }
      >
        {grid.loading ? (
          <LoadingState rows={5} />
        ) : !grid.data?.length ? (
          <EmptyState
            title="Nobody is enrolled on this course"
            description="Enrol students before entering marks."
          />
        ) : (
          <table className="min-w-full divide-y divide-slate-200">
            <thead>
              <tr>
                <th className="th">Student</th>
                <th className="th">Marks (max {gradingFor?.max_marks})</th>
                <th className="th">Submitted at</th>
                <th className="th">Current</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {grid.data.map((row) => {
                const draft = grades[row.enrollment_id] ?? { marks: '', submitted: '' }
                return (
                  <tr key={row.enrollment_id}>
                    <td className="td">
                      <span className="block text-sm font-medium text-slate-800">
                        {row.student_name}
                      </span>
                      <span className="block font-mono text-xs text-slate-500">
                        {row.student_id}
                      </span>
                    </td>
                    <td className="td">
                      <input
                        type="number"
                        min={0}
                        max={row.max_marks}
                        step="0.5"
                        value={draft.marks}
                        placeholder={
                          row.marks_obtained === null ? '—' : String(row.marks_obtained)
                        }
                        onChange={(event) =>
                          setGrades((current) => ({
                            ...current,
                            [row.enrollment_id]: { ...draft, marks: event.target.value },
                          }))
                        }
                        aria-label={`Marks for ${row.student_name}`}
                        className="input w-24 py-1.5"
                      />
                    </td>
                    <td className="td">
                      <input
                        type="datetime-local"
                        value={draft.submitted}
                        onChange={(event) =>
                          setGrades((current) => ({
                            ...current,
                            [row.enrollment_id]: { ...draft, submitted: event.target.value },
                          }))
                        }
                        aria-label={`Submission time for ${row.student_name}`}
                        className="input w-52 py-1.5"
                      />
                    </td>
                    <td className="td">
                      {row.marks_obtained === null ? (
                        <Badge tone={SUBMISSION_TONE[row.submission_status]}>
                          {humanise(row.submission_status)}
                        </Badge>
                      ) : (
                        <span className="text-xs tabular-nums text-slate-600">
                          {row.marks_obtained}/{row.max_marks} ({percent(row.percentage, 0)})
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Modal>
    </>
  )
}
