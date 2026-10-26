/** A single ratio against a limit, as a meter rather than a chart.
 *
 * One value against a track is a meter; a two-slice pie would be worse
 * in every way.
 */

export default function Meter({ value, label, suffix = '%', color = '#2a78d6', hint, max = 100 }) {
  const hasValue = value !== null && value !== undefined && !Number.isNaN(value)
  const pct = hasValue ? Math.max(0, Math.min(100, (Number(value) / max) * 100)) : 0

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-slate-600">{label}</span>
        <span className="text-sm font-bold tabular-nums text-slate-900">
          {hasValue ? `${Number(value).toFixed(1)}${suffix}` : '—'}
        </span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
        role="meter"
        aria-valuenow={hasValue ? Number(value) : undefined}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        {hasValue && (
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${pct}%`, backgroundColor: color }}
          />
        )}
      </div>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}
