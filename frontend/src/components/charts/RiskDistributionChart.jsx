/** Risk distribution as a part-to-whole horizontal stacked bar.
 *
 * Why this form: the four bands are shares of one total, which is a
 * stacked bar's job - not a pie's. It runs horizontally because the band
 * names are long. Each segment carries a direct count label, a legend
 * entry and an icon-bearing chip in the table underneath, so the status
 * colours never carry the meaning alone.
 */

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { RISK_LABELS } from '../../utils/constants.js'
import { RISK_COLORS } from '../../utils/charts.js'
import { EmptyState } from '../States.jsx'
import { RiskDot } from '../RiskBadge.jsx'

const ORDER = ['HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_DATA']

export default function RiskDistributionChart({ distribution }) {
  const counts = Object.fromEntries((distribution ?? []).map((row) => [row.category, row.count]))
  const total = ORDER.reduce((sum, key) => sum + (counts[key] ?? 0), 0)

  if (!total) {
    return (
      <EmptyState
        title="No risk scores yet"
        description="Run a risk recalculation to populate this chart."
      />
    )
  }

  // One row, one stacked series per band. The row needs a category value
  // for the (hidden) Y axis: a vertical-layout BarChart places its bars
  // against a category axis, and without one Recharts draws nothing.
  const data = [{ band: 'all', ...Object.fromEntries(ORDER.map((key) => [key, counts[key] ?? 0])) }]

  return (
    <div className="p-5">
      <div className="h-[72px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <XAxis type="number" hide domain={[0, total]} />
            <YAxis type="category" dataKey="band" hide />
            <Tooltip
              cursor={{ fill: 'rgba(148,163,184,0.12)' }}
              contentStyle={{
                borderRadius: '0.5rem',
                border: '1px solid #e2e8f0',
                fontSize: '0.8125rem',
              }}
              formatter={(value, name) => [
                `${value} enrolment${value === 1 ? '' : 's'} (${((value / total) * 100).toFixed(0)}%)`,
                RISK_LABELS[name] ?? name,
              ]}
            />
            {ORDER.map((key, index) => (
              <Bar
                key={key}
                dataKey={key}
                stackId="risk"
                fill={RISK_COLORS[key]}
                // 2px surface gap between segments keeps adjacent fills
                // from reading as one block.
                stroke="#ffffff"
                strokeWidth={2}
                barSize={44}
                isAnimationActive={false}
                radius={
                  index === 0 ? [4, 0, 0, 4] : index === ORDER.length - 1 ? [0, 4, 4, 0] : 0
                }
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend with the direct counts: identity is never colour-alone. */}
      <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        {ORDER.map((key) => {
          const value = counts[key] ?? 0
          return (
            <li key={key} className="flex flex-col gap-0.5">
              <RiskDot category={key} />
              <span className="text-sm font-bold tabular-nums text-slate-900">
                {value}
                <span className="ml-1 text-xs font-normal text-slate-500">
                  ({total ? ((value / total) * 100).toFixed(0) : 0}%)
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
