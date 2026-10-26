/** Risk bands per group (department, semester or course).
 *
 * A stacked bar per group: part-to-whole within each group, with the
 * status palette and a legend. Horizontal, because group names are long.
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
import { RISK_LABELS } from '../../utils/constants.js'
import { EmptyState } from '../States.jsx'

const SERIES = [
  { key: 'high_risk', category: 'HIGH' },
  { key: 'medium_risk', category: 'MEDIUM' },
  { key: 'low_risk', category: 'LOW' },
  { key: 'insufficient_data', category: 'INSUFFICIENT_DATA' },
]

export default function GroupedRiskChart({ rows, height }) {
  if (!rows?.length) {
    return <EmptyState title="Nothing to group" description="No enrolments match these filters." />
  }

  const chartHeight = height ?? Math.max(180, rows.length * 42 + 48)

  return (
    <div className="p-5">
      <div style={{ height: chartHeight }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 4, right: 16, bottom: 0, left: 8 }}
            barCategoryGap="26%"
          >
            <CartesianGrid {...gridProps} vertical horizontal={false} />
            <XAxis type="number" allowDecimals={false} {...axisProps} />
            <YAxis
              type="category"
              dataKey="group_label"
              width={140}
              {...axisProps}
              tick={{ fill: '#475569', fontSize: 12 }}
            />
            <Tooltip
              {...tooltipStyle}
              cursor={{ fill: 'rgba(148,163,184,0.12)' }}
              formatter={(value, name) => [value, name]}
            />
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
                stackId="bands"
                name={RISK_LABELS[series.category]}
                fill={RISK_COLORS[series.category]}
                stroke="#ffffff"
                strokeWidth={2}
                barSize={18}
                isAnimationActive={false}
                radius={
                  index === 0
                    ? [4, 0, 0, 4]
                    : index === SERIES.length - 1
                      ? [0, 4, 4, 0]
                      : 0
                }
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
