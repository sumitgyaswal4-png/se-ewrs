/** Risk-band and status chips.
 *
 * A risk band always shows an icon AND a word, never colour alone: two of
 * the four band colours sit below a 3:1 contrast ratio against white, and
 * colour on its own is invisible to a colourblind reader anyway.
 */

import { CircleHelp, ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react'

import { RISK_LABELS, RISK_RANGES } from '../utils/constants.js'

const BAND = {
  LOW: {
    icon: ShieldCheck,
    chip: 'bg-risk-low/10 text-[#076b07] ring-1 ring-inset ring-risk-low/30',
    dot: 'bg-risk-low',
  },
  MEDIUM: {
    icon: TriangleAlert,
    chip: 'bg-risk-medium/15 text-[#875c00] ring-1 ring-inset ring-risk-medium/40',
    dot: 'bg-risk-medium',
  },
  HIGH: {
    icon: ShieldAlert,
    chip: 'bg-risk-high/10 text-[#9c2525] ring-1 ring-inset ring-risk-high/30',
    dot: 'bg-risk-high',
  },
  INSUFFICIENT_DATA: {
    icon: CircleHelp,
    chip: 'bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-300',
    dot: 'bg-risk-unknown',
  },
}

export default function RiskBadge({ category, score, showRange = false, size = 'md' }) {
  const band = BAND[category] ?? BAND.INSUFFICIENT_DATA
  const Icon = band.icon
  const label = RISK_LABELS[category] ?? 'Unknown'
  const sizing = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'

  return (
    <span className={`chip ${band.chip} ${sizing}`}>
      <Icon className={size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5'} aria-hidden="true" />
      <span>{label}</span>
      {score !== null && score !== undefined && (
        <span className="font-mono font-bold tabular-nums">{Number(score).toFixed(0)}</span>
      )}
      {showRange && <span className="font-normal opacity-70">({RISK_RANGES[category]})</span>}
    </span>
  )
}

/** A small colour swatch + label, for chart legends and tables. */
export function RiskDot({ category, label }) {
  const band = BAND[category] ?? BAND.INSUFFICIENT_DATA
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
      <span className={`h-2.5 w-2.5 rounded-sm ${band.dot}`} aria-hidden="true" />
      {label ?? RISK_LABELS[category]}
    </span>
  )
}
