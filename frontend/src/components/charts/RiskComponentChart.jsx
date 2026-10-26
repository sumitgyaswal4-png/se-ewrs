/** The three weighted components behind one student's risk score.
 *
 * All three bars measure the same thing - risk on 0-100 - so they use a
 * single hue rather than three categorical colours: the job here is
 * comparing magnitude, not telling unrelated series apart. A component
 * with no data gets no bar at all and says so, instead of being drawn as
 * a zero.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { BAR_RADIUS_H, PRIMARY_SERIES, axisProps, gridProps, tooltipStyle } from '../../utils/charts.js'

export default function RiskComponentChart({ components, height = 200 }) {
  const available = (components ?? []).filter((component) => component.available)
  const missing = (components ?? []).filter((component) => !component.available)

  return (
    <div className="p-5">
      {available.length > 0 ? (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={available}
              layout="vertical"
              margin={{ top: 4, right: 44, bottom: 0, left: 8 }}
              barCategoryGap="28%"
            >
              <CartesianGrid {...gridProps} vertical horizontal={false} />
              <XAxis type="number" domain={[0, 100]} {...axisProps} />
              <YAxis
                type="category"
                dataKey="name"
                width={86}
                {...axisProps}
                tick={{ fill: '#475569', fontSize: 12 }}
              />
              <Tooltip
                {...tooltipStyle}
                cursor={{ fill: 'rgba(148,163,184,0.12)' }}
                formatter={(value, _name, item) => [
                  `${Number(value).toFixed(1)} / 100 risk  ·  weight ${(
                    item.payload.effective_weight * 100
                  ).toFixed(0)}%`,
                  item.payload.observed_label,
                ]}
              />
              <Bar
                dataKey="risk_value"
                fill={PRIMARY_SERIES}
                radius={BAR_RADIUS_H}
                barSize={18}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey="risk_value"
                  position="right"
                  formatter={(value) => Number(value).toFixed(0)}
                  style={{ fill: '#334155', fontSize: 12, fontWeight: 700 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="py-6 text-center text-sm text-slate-500">
          None of the three components has enough data to score yet.
        </p>
      )}

      {missing.length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <p className="text-xs font-semibold text-slate-700">Not counted</p>
          <ul className="mt-1.5 space-y-1">
            {missing.map((component) => (
              <li key={component.name} className="text-xs text-slate-600">
                <span className="font-medium text-slate-700">{component.name}:</span>{' '}
                {component.unavailable_reason ?? component.observed_label}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-500">
            The remaining weights were re-normalised so a missing input is not
            treated as a zero.
          </p>
        </div>
      )}
    </div>
  )
}
