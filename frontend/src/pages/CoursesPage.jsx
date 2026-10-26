/** Course management: catalogue, instructors, roster and enrolment. */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Plus, UserPlus, Users, X } from 'lucide-react'

import Badge from '../components/Badge.jsx'
import Card from '../components/Card.jsx'
import DataTable from '../components/DataTable.jsx'
import Modal from '../components/Modal.jsx'
import PageHeader from '../components/PageHeader.jsx'
import Pagination from '../components/Pagination.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import SearchInput from '../components/SearchInput.jsx'
import { FilterSelect, SelectInput, TextInput } from '../components/Form.jsx'
import { EmptyState, LoadingState } from '../components/States.jsx'
import { useDebounced, useMutation, useQuery } from '../hooks/useApi.js'
import { useAuth } from '../hooks/useAuth.jsx'
import { useToast } from '../hooks/useToast.jsx'
import { authApi, courseApi, enrollmentApi, lookupApi } from '../services/endpoints.js'
import { SEMESTERS } from '../utils/constants.js'
import { percent } from '../utils/format.js'

const EMPTY_COURSE = {
  course_code: '',
  course_name: '',
  dept_id: '',
  semester: '',
  credits: '3',
  academic_term: '2025-ODD',
  total_sessions: '0',
}

export default function CoursesPage() {
  const { can } = useAuth()
  const toast = useToast()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(1)
  const [deptId, setDeptId] = useState(null)
  const [semester, setSemester] = useState(null)

  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_COURSE)
  const [formErrors, setFormErrors] = useState({})
  const [rosterFor, setRosterFor] = useState(null)
  const [enrollFor, setEnrollFor] = useState(null)
  const [selectedStudents, setSelectedStudents] = useState([])
  const [studentSearch, setStudentSearch] = useState('')
  const [instructorFor, setInstructorFor] = useState(null)
  const [instructorId, setInstructorId] = useState('')

  const departments = useQuery(() => lookupApi.departments(), [])
  const staff = useQuery(() => authApi.assignableUsers(), [], { enabled: can('courses:write') })

  const params = useMemo(
    () => ({
      page,
      page_size: 20,
      search: debouncedSearch || undefined,
      dept_id: deptId || undefined,
      semester: semester || undefined,
    }),
    [page, debouncedSearch, deptId, semester],
  )
  const courses = useQuery(() => courseApi.list(params), [JSON.stringify(params)])

  const roster = useQuery(() => courseApi.roster(rosterFor.course_pk), [rosterFor?.course_pk], {
    enabled: Boolean(rosterFor),
  })
  const debouncedStudentSearch = useDebounced(studentSearch)
  const studentOptions = useQuery(
    () => lookupApi.studentOptions({ search: debouncedStudentSearch || undefined, limit: 200 }),
    [debouncedStudentSearch],
    { enabled: Boolean(enrollFor) },
  )

  const save = useMutation((payload) =>
    editing === 'new' ? courseApi.create(payload) : courseApi.update(editing.course_pk, payload),
  )
  const enroll = useMutation((payload) => enrollmentApi.bulkCreate(payload))
  const assign = useMutation(({ coursePk, userId }) =>
    courseApi.assignInstructor(coursePk, { user_id: userId, role_in_course: 'PRIMARY' }),
  )
  const unassign = useMutation(({ coursePk, userId }) =>
    courseApi.removeInstructor(coursePk, userId),
  )

  function openNew() {
    setForm({ ...EMPTY_COURSE, dept_id: departments.data?.[0]?.dept_id ?? '' })
    setFormErrors({})
    setEditing('new')
  }

  function openEdit(course) {
    setForm({
      course_code: course.course_code,
      course_name: course.course_name,
      dept_id: String(course.dept_id),
      semester: String(course.semester),
      credits: String(course.credits),
      academic_term: course.academic_term,
      total_sessions: String(course.total_sessions),
    })
    setFormErrors({})
    setEditing(course)
  }

  function validate() {
    const errors = {}
    if (editing === 'new' && form.course_code.trim().length < 2) {
      errors.course_code = 'Enter a course code'
    }
    if (form.course_name.trim().length < 3) errors.course_name = 'Enter the course name'
    if (!form.dept_id) errors.dept_id = 'Choose a department'
    if (!form.semester) errors.semester = 'Choose a semester'
    if (editing === 'new' && form.academic_term.trim().length < 4) {
      errors.academic_term = 'Enter an academic term, e.g. 2025-ODD'
    }
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function onSubmit(event) {
    event.preventDefault()
    if (!validate()) return

    const payload = {
      course_name: form.course_name.trim(),
      dept_id: Number(form.dept_id),
      semester: Number(form.semester),
      credits: Number(form.credits),
      total_sessions: Number(form.total_sessions),
    }
    if (editing === 'new') {
      payload.course_code = form.course_code.trim()
      payload.academic_term = form.academic_term.trim()
    }

    try {
      await save.run(payload)
      toast.success(editing === 'new' ? 'Course created' : 'Course updated')
      setEditing(null)
      courses.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  async function onEnroll() {
    if (!selectedStudents.length) {
      toast.error('Select at least one student')
      return
    }
    try {
      const result = await enroll.run({
        course_pk: enrollFor.course_pk,
        student_pks: selectedStudents,
      })
      toast.success(result.detail)
      setEnrollFor(null)
      setSelectedStudents([])
      setStudentSearch('')
      courses.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  async function onAssignInstructor() {
    if (!instructorId) {
      toast.error('Choose a member of staff')
      return
    }
    try {
      await assign.run({ coursePk: instructorFor.course_pk, userId: Number(instructorId) })
      toast.success('Instructor assigned')
      setInstructorId('')
      setInstructorFor(null)
      courses.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  async function onUnassign(coursePk, userId) {
    try {
      await unassign.run({ coursePk, userId })
      toast.success('Instructor removed')
      courses.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const departmentOptions = (departments.data ?? []).map((dept) => ({
    value: String(dept.dept_id),
    label: `${dept.dept_code} — ${dept.dept_name}`,
  }))

  const columns = [
    {
      key: 'course',
      header: 'Course',
      sortKey: 'course_code',
      render: (row) => (
        <div className="min-w-0">
          <span className="block font-semibold text-slate-800">{row.course_code}</span>
          <span className="block truncate text-xs text-slate-500">{row.course_name}</span>
        </div>
      ),
    },
    {
      key: 'meta',
      header: 'Dept / Sem / Credits',
      render: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral">{row.dept_code}</Badge>
          <span className="text-xs text-slate-500">Sem {row.semester}</span>
          <span className="text-xs text-slate-500">· {row.credits} cr</span>
        </div>
      ),
    },
    { key: 'term', header: 'Term', render: (row) => <Badge tone="brand">{row.academic_term}</Badge> },
    {
      key: 'instructors',
      header: 'Instructors',
      render: (row) =>
        row.instructors.length ? (
          <ul className="space-y-0.5">
            {row.instructors.map((instructor) => (
              <li key={instructor.user_id} className="flex items-center gap-1.5 text-xs">
                <span className="text-slate-700">{instructor.full_name}</span>
                <span className="text-slate-400">
                  ({instructor.role_in_course.toLowerCase().replace('_', ' ')})
                </span>
                {can('courses:write') && (
                  <button
                    type="button"
                    onClick={() => onUnassign(row.course_pk, instructor.user_id)}
                    className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-risk-high"
                    aria-label={`Remove ${instructor.full_name} from ${row.course_code}`}
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-xs text-slate-400">none assigned</span>
        ),
    },
    {
      key: 'enrolled',
      header: 'Enrolled',
      align: 'right',
      render: (row) => <span className="tabular-nums font-semibold">{row.enrolled_count}</span>,
    },
    {
      key: 'attendance',
      header: 'Attendance',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">{percent(row.avg_attendance_percentage, 0)}</span>
      ),
    },
    {
      key: 'marks',
      header: 'Avg marks',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">{percent(row.avg_assessment_percentage, 0)}</span>
      ),
    },
    {
      key: 'risk',
      header: 'High risk',
      align: 'right',
      render: (row) =>
        row.high_risk_count > 0 ? (
          <Badge tone="danger">{row.high_risk_count}</Badge>
        ) : (
          <span className="text-xs text-slate-400">0</span>
        ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <div className="flex flex-wrap justify-end gap-1">
          <button
            type="button"
            onClick={() => setRosterFor(row)}
            className="btn-ghost px-2 py-1 text-xs"
          >
            <Users className="h-3.5 w-3.5" aria-hidden="true" />
            Roster
          </button>
          {can('enrollments:write') && (
            <button
              type="button"
              onClick={() => {
                setEnrollFor(row)
                setSelectedStudents([])
              }}
              className="btn-ghost px-2 py-1 text-xs"
            >
              <UserPlus className="h-3.5 w-3.5" aria-hidden="true" />
              Enrol
            </button>
          )}
          {can('courses:write') && (
            <>
              <button
                type="button"
                onClick={() => setInstructorFor(row)}
                className="btn-ghost px-2 py-1 text-xs"
              >
                Staff
              </button>
              <button
                type="button"
                onClick={() => openEdit(row)}
                className="btn-ghost px-2 py-1 text-xs"
              >
                Edit
              </button>
            </>
          )}
        </div>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Courses"
        description="The course catalogue, its teaching staff and enrolment."
        actions={
          can('courses:write') && (
            <button type="button" onClick={openNew} className="btn-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
              Create course
            </button>
          )
        }
      />

      <Card bodyClassName="p-0">
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Course code or name"
            label="Search courses"
            className="min-w-[14rem] flex-1"
          />
          <FilterSelect
            label="Department"
            value={deptId}
            onChange={(value) => {
              setDeptId(value)
              setPage(1)
            }}
            options={departmentOptions}
          />
          <FilterSelect
            label="Semester"
            value={semester}
            onChange={(value) => {
              setSemester(value)
              setPage(1)
            }}
            options={SEMESTERS.map((value) => ({ value: String(value), label: `Sem ${value}` }))}
          />
        </div>

        <DataTable
          columns={columns}
          rows={courses.data?.items}
          rowKey={(row) => row.course_pk}
          loading={courses.loading}
          error={courses.error}
          onRetry={courses.reload}
          caption="Course catalogue"
          emptyTitle="No courses match these filters"
          emptyDescription="Create a course to begin tracking engagement against it."
          emptyAction={
            can('courses:write') && (
              <button type="button" onClick={openNew} className="btn-primary">
                <Plus className="h-4 w-4" aria-hidden="true" />
                Create course
              </button>
            )
          }
        />

        {courses.data?.total > 0 && (
          <div className="border-t border-slate-200 px-4 py-3">
            <Pagination
              page={courses.data.page}
              pageSize={courses.data.page_size}
              total={courses.data.total}
              pages={courses.data.pages}
              onPageChange={setPage}
            />
          </div>
        )}
      </Card>

      {/* Create / edit */}
      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'Create a course' : `Edit ${editing?.course_code ?? ''}`}
        description={
          editing === 'new'
            ? 'A course code may repeat across academic terms but not within one.'
            : undefined
        }
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button type="submit" form="course-form" className="btn-primary" disabled={save.pending}>
              {save.pending ? 'Saving…' : 'Save course'}
            </button>
          </>
        }
      >
        <form id="course-form" onSubmit={onSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
          {editing === 'new' && (
            <TextInput
              label="Course code"
              required
              value={form.course_code}
              onChange={(event) => setForm({ ...form, course_code: event.target.value })}
              error={formErrors.course_code}
              placeholder="MTH201"
            />
          )}
          <TextInput
            label="Course name"
            required
            value={form.course_name}
            onChange={(event) => setForm({ ...form, course_name: event.target.value })}
            error={formErrors.course_name}
            className={editing === 'new' ? undefined : 'sm:col-span-2'}
          />
          <SelectInput
            label="Department"
            required
            value={form.dept_id}
            onChange={(event) => setForm({ ...form, dept_id: event.target.value })}
            options={departmentOptions}
            placeholder="Select a department"
            error={formErrors.dept_id}
          />
          <SelectInput
            label="Semester"
            required
            value={form.semester}
            onChange={(event) => setForm({ ...form, semester: event.target.value })}
            options={SEMESTERS.map((value) => ({ value: String(value), label: `Semester ${value}` }))}
            placeholder="Select a semester"
            error={formErrors.semester}
          />
          <TextInput
            label="Credits"
            type="number"
            min={1}
            max={10}
            value={form.credits}
            onChange={(event) => setForm({ ...form, credits: event.target.value })}
          />
          {editing === 'new' && (
            <TextInput
              label="Academic term"
              required
              value={form.academic_term}
              onChange={(event) => setForm({ ...form, academic_term: event.target.value })}
              error={formErrors.academic_term}
              hint="e.g. 2025-ODD"
            />
          )}
          <TextInput
            label="Planned sessions"
            type="number"
            min={0}
            max={500}
            value={form.total_sessions}
            onChange={(event) => setForm({ ...form, total_sessions: event.target.value })}
            hint="Total classes scheduled for the term"
          />
        </form>
      </Modal>

      {/* Roster */}
      <Modal
        open={Boolean(rosterFor)}
        onClose={() => setRosterFor(null)}
        title={rosterFor ? `${rosterFor.course_code} roster` : ''}
        description={rosterFor?.course_name}
        size="lg"
      >
        {roster.loading ? (
          <LoadingState rows={5} />
        ) : !roster.data?.length ? (
          <EmptyState
            title="Nobody is enrolled yet"
            description="Use the Enrol action to add students to this course."
          />
        ) : (
          <table className="min-w-full divide-y divide-slate-200">
            <thead>
              <tr>
                <th className="th">Student</th>
                <th className="th text-right">Attendance</th>
                <th className="th text-right">Assessment</th>
                <th className="th">Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {roster.data.map((row) => (
                <tr key={row.enrollment_id}>
                  <td className="td">
                    <Link
                      to={`/students/${row.student_pk}`}
                      className="font-medium text-slate-800 hover:text-brand-700"
                    >
                      {row.student_name}
                    </Link>
                    <span className="block font-mono text-xs text-slate-500">
                      {row.student_id}
                    </span>
                  </td>
                  <td className="td text-right tabular-nums">
                    {percent(row.attendance_percentage, 0)}
                  </td>
                  <td className="td text-right tabular-nums">
                    {percent(row.avg_assessment_percentage, 0)}
                  </td>
                  <td className="td">
                    <RiskBadge category={row.risk_category} score={row.risk_score} size="sm" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Modal>

      {/* Enrol students */}
      <Modal
        open={Boolean(enrollFor)}
        onClose={() => setEnrollFor(null)}
        title={enrollFor ? `Enrol students in ${enrollFor.course_code}` : ''}
        description="Students already enrolled are skipped automatically — a duplicate enrolment is impossible."
        size="lg"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEnrollFor(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={onEnroll}
              disabled={enroll.pending || !selectedStudents.length}
            >
              {enroll.pending
                ? 'Enrolling…'
                : `Enrol ${selectedStudents.length || ''} student${
                    selectedStudents.length === 1 ? '' : 's'
                  }`}
            </button>
          </>
        }
      >
        <SearchInput
          value={studentSearch}
          onChange={setStudentSearch}
          placeholder="Search by roll number or name"
          label="Search students to enrol"
          className="mb-3"
        />
        {studentOptions.loading ? (
          <LoadingState rows={4} />
        ) : !studentOptions.data?.length ? (
          <EmptyState title="No students found" description="Try a different search." />
        ) : (
          <ul className="max-h-72 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
            {studentOptions.data.map((option) => {
              const checked = selectedStudents.includes(option.student_pk)
              return (
                <li key={option.student_pk}>
                  <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) =>
                        setSelectedStudents((current) =>
                          event.target.checked
                            ? [...current, option.student_pk]
                            : current.filter((pk) => pk !== option.student_pk),
                        )
                      }
                      className="h-4 w-4 rounded border-slate-300 text-brand-600"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-slate-800">
                        {option.full_name}
                      </span>
                      <span className="block font-mono text-xs text-slate-500">
                        {option.student_id} · Sem {option.semester}
                      </span>
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
        )}
      </Modal>

      {/* Assign instructor */}
      <Modal
        open={Boolean(instructorFor)}
        onClose={() => setInstructorFor(null)}
        title={instructorFor ? `Assign staff to ${instructorFor.course_code}` : ''}
        description="Only instructors, teaching assistants and administrators can hold a course assignment."
        size="sm"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setInstructorFor(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={onAssignInstructor}
              disabled={assign.pending}
            >
              {assign.pending ? 'Assigning…' : 'Assign'}
            </button>
          </>
        }
      >
        <SelectInput
          label="Member of staff"
          value={instructorId}
          onChange={(event) => setInstructorId(event.target.value)}
          placeholder="Select a member of staff"
          options={(staff.data ?? []).map((user) => ({
            value: String(user.user_id),
            label: `${user.full_name} (${user.role})`,
          }))}
        />
      </Modal>
    </>
  )
}
