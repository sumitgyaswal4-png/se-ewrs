/** A KPI stat tile.
 *
 * A handful of headline numbers belongs in a row of tiles, not in a
 * one-bar bar chart - so the dashboard's top row is these, not a graph.
 */

import { Link } from 'react-router-dom'

const ACCENTS = {
  brand: 'bg-brand-50 text-brand-700',
  low: 'bg-risk-low/10 text-[#076b07]',
  medium: 'bg-risk-medium/15 text-[#875c00]',
  high: 'bg-risk-high/10 text-[#9c2525]',
  neutral: 'bg-slate-100 text-slate-600',
}

export default function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  accent = 'brand',
  to,
  emphasis = false,
}) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-slate-600">{label}</p>
        {Icon && (
          <span className={`rounded-lg p-2 ${ACCENTS[accent] ?? ACCENTS.brand}`}>
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
        )}
      </div>
      <p
        className={`mt-2 font-bold tabular-nums text-slate-900 ${
          emphasis ? 'text-4xl' : 'text-2xl'
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </>
  )

  if (to) {
    return (
      <Link
        to={to}
        className="card block p-5 transition hover:border-brand-300 hover:shadow-card-hover"
      >
        {body}
      </Link>
    )
  }

  return <div className="card p-5">{body}</div>
}
