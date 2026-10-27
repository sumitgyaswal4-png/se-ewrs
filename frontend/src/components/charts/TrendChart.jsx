/** Academic performance and attendance over time.
 *
 * Up to two series, both percentages, so they share one y-axis - never a
 * second scale on the right. They are drawn from the fixed categorical
 * slots in order (blue, orange).
 *
 * Only the series the data actually carries are drawn. The dashboard's
 * trend endpoint returns assessment and attendance; the per-student one
 * returns assessment alone, and a legend naming a line that the chart
 * cannot draw is worse than no legend. With a single series the card
 * title names it, so the legend box is dropped entirely.
 */

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { SERIES_COLORS, axisProps, gridProps, tooltipStyle } from '../../utils/charts.js'
import { EmptyState } from '../States.jsx'

const SERIES = [
  { key: 'avg_percentage', name: 'Assessment average', color: SERIES_COLORS[0] },
  { key: 'avg_attendance_percentage', name: 'Attendance rate', color: SERIES_COLORS[1] },
]

function formatPeriod(period) {
  if (!period) return ''
  const [year, month] = period.split('-')
  const date = new Date(Number(year), Number(month) - 1, 1)
  if (Number.isNaN(date.getTime())) return period
  return date.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

export default function TrendChart({ points, height = 280 }) {
  if (!points?.length) {
    return (
      <EmptyState
        title="No performance history yet"
        description="Trends appear once assessments have been graded and attendance recorded."
      />
    )
  }

  const series = SERIES.filter((item) =>
    points.some((point) => point[item.key] !== null && point[item.key] !== undefined),
  )

  return (
    <div className="p-5">
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="period" tickFormatter={formatPeriod} {...axisProps} />
            <YAxis domain={[0, 100]} unit="%" {...axisProps} />
            <Tooltip
              {...tooltipStyle}
              labelFormatter={formatPeriod}
              formatter={(value, name) => [
                value === null || value === undefined ? 'no data' : `${Number(value).toFixed(1)}%`,
                name,
              ]}
            />
            {series.length > 1 && (
              <Legend
                verticalAlign="top"
                align="right"
                height={28}
                iconType="plainline"
                wrapperStyle={{ fontSize: '0.75rem', color: '#475569' }}
              />
            )}
            {series.map((item) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                name={item.name}
                stroke={item.color}
                strokeWidth={2}
                dot={{ r: 4, strokeWidth: 2, stroke: '#ffffff' }}
                activeDot={{ r: 6, strokeWidth: 2, stroke: '#ffffff' }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
