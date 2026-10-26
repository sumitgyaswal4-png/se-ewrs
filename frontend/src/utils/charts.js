/**
 * Chart colour tokens and shared Recharts presentation settings.
 *
 * Two separate colour jobs, kept apart on purpose:
 *
 *  - RISK_COLORS is a **status** palette. Risk has polarity (low is good,
 *    high is bad), so the bands use fixed good / warning / critical steps
 *    that are never reused for an ordinary data series. "Needs more data"
 *    is deliberately a neutral grey: it is an absence of information, not
 *    a degree of risk.
 *  - SERIES_COLORS is a **categorical** palette, assigned in fixed slot
 *    order and never cycled. It is for telling unrelated series apart.
 *
 * Both palettes were checked with a CVD/contrast validator. Two values sit
 * below 3:1 against a white surface (`medium` at 1.79:1 and `low` at
 * 3.27:1 which is only just over), so every risk band ships an icon, a
 * text label and a direct count - colour never carries the meaning on its
 * own - and the same figures are always available as a table.
 */

export const RISK_COLORS = {
  LOW: '#0ca30c',
  MEDIUM: '#fab219',
  HIGH: '#d03b3b',
  INSUFFICIENT_DATA: '#8c8b85',
}

/** Categorical slots, in fixed order. Never generate a new hue. */
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a']

/** The single hue used whenever one measure is plotted on its own. */
export const PRIMARY_SERIES = '#2a78d6'

export const CHART_INK = {
  axis: '#64748b',
  grid: '#e2e8f0',
  label: '#475569',
}

/** Recessive grid and axes, so the data reads before the furniture. */
export const axisProps = {
  stroke: CHART_INK.axis,
  tick: { fill: CHART_INK.label, fontSize: 12 },
  tickLine: false,
}

export const gridProps = {
  stroke: CHART_INK.grid,
  strokeDasharray: '3 3',
  vertical: false,
}

/** Chart marks are drawn without an entry animation.
 *
 * Each chart passes `isAnimationActive={false}` on its Bar/Line. These
 * charts redraw whenever a filter changes or the data reloads, so an
 * entry animation on every pass is noise rather than information -- and
 * it means the marks are present as soon as the component renders, which
 * is what lets the chart tests assert on them.
 */

/** 4px rounded data-end, anchored to the baseline. */
export const BAR_RADIUS = [4, 4, 0, 0]
export const BAR_RADIUS_H = [0, 4, 4, 0]

export const tooltipStyle = {
  contentStyle: {
    borderRadius: '0.5rem',
    border: '1px solid #e2e8f0',
    boxShadow: '0 4px 12px -2px rgb(15 23 42 / 0.10)',
    fontSize: '0.8125rem',
    padding: '0.5rem 0.75rem',
  },
  labelStyle: { color: '#0f172a', fontWeight: 600, marginBottom: '0.25rem' },
}

export function riskColor(category) {
  return RISK_COLORS[category] ?? RISK_COLORS.INSUFFICIENT_DATA
}
