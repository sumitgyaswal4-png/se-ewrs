/** On-time / late / missing submissions per assessment.
 *
 * Three ordered states with polarity, so they use the status palette and
 * a legend; each bar is part-to-whole for that assessment.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { RISK_COLORS, axisProps, gridProps, tooltipStyle } from '../../utils/charts.js'
import { EmptyState } from '../States.jsx'

const SERIES = [
  { key: 'on_time', name: 'On time', color: RISK_COLORS.LOW },
  { key: 'late', name: 'Late', color: RISK_COLORS.MEDIUM },
  { key: 'missing', name: 'Missing', color: RISK_COLORS.HIGH },
]

export default function SubmissionChart({ rows, height = 300 }) {
  if (!rows?.length) {
    return (
      <EmptyState
        title="No submission data"
        description="Create assessments and record results to see submission patterns."
      />
    )
  }

  const data = rows.map((row) => ({
    ...row,
    label: `${row.course_code} · ${row.assessment_title.replace(`${row.course_code} `, '')}`,
  }))

  return (
    <div className="p-5">
      <div style={{ height: Math.max(height, data.length * 34 + 56) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
            barCategoryGap="24%"
          >
            <CartesianGrid {...gridProps} vertical horizontal={false} />
            <XAxis type="number" allowDecimals={false} {...axisProps} />
            <YAxis
              type="category"
              dataKey="label"
              width={190}
              {...axisProps}
              tick={{ fill: '#475569', fontSize: 11 }}
            />
            <Tooltip {...tooltipStyle} cursor={{ fill: 'rgba(148,163,184,0.12)' }} />
            <Legend
              verticalAlign="top"
              align="right"
              height={28}
              wrapperStyle={{ fontSize: '0.75rem', color: '#475569' }}
            />
            {SERIES.map((series, index) => (
              <Bar
                key={series.key}
                dataKey={series.key}
                name={series.name}
                stackId="submissions"
                fill={series.color}
                stroke="#ffffff"
                strokeWidth={2}
                barSize={16}
                isAnimationActive={false}
                radius={
                  index === 0 ? [4, 0, 0, 4] : index === SERIES.length - 1 ? [0, 4, 4, 0] : 0
                }
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
