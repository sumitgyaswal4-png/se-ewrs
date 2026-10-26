/** One enrolment's risk score over successive recalculations.
 *
 * A single series, so no legend box - the card title names it. Threshold
 * guides mark the band edges so a reader can see which way the line is
 * heading without reading the axis.
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { PRIMARY_SERIES, axisProps, gridProps, tooltipStyle } from '../../utils/charts.js'
import { RISK_COLORS } from '../../utils/charts.js'
import { EmptyState } from '../States.jsx'

export default function RiskHistoryChart({ history, thresholds, height = 220 }) {
  if (!history?.length) {
    return (
      <EmptyState
        title="No risk history yet"
        description="A point is added here each time risk is recalculated."
      />
    )
  }

  const data = history.map((point) => ({
    ...point,
    label: new Date(point.calculated_at).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    }),
  }))

  return (
    <div className="p-5">
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="label" {...axisProps} />
            <YAxis domain={[0, 100]} {...axisProps} />
            <Tooltip
              {...tooltipStyle}
              formatter={(value) => [
                value === null ? 'not scored' : Number(value).toFixed(1),
                'Risk score',
              ]}
            />
            {thresholds?.medium != null && (
              <ReferenceLine
                y={thresholds.medium}
                stroke={RISK_COLORS.MEDIUM}
                strokeDasharray="4 4"
                label={{
                  value: `medium ${thresholds.medium}`,
                  position: 'insideTopRight',
                  fill: '#875c00',
                  fontSize: 10,
                }}
              />
            )}
            {thresholds?.high != null && (
              <ReferenceLine
                y={thresholds.high}
                stroke={RISK_COLORS.HIGH}
                strokeDasharray="4 4"
                label={{
                  value: `high ${thresholds.high}`,
                  position: 'insideTopRight',
                  fill: '#9c2525',
                  fontSize: 10,
                }}
              />
            )}
            <Line
              type="monotone"
              dataKey="risk_score"
              stroke={PRIMARY_SERIES}
              strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, stroke: '#ffffff' }}
              activeDot={{ r: 6, strokeWidth: 2, stroke: '#ffffff' }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
