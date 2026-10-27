/** The meter colour must mean what a status colour says it means.
 *
 * These cases are the band edges of the documented risk model: a figure
 * is banded by its own component risk (100 - value), so 70% attendance
 * sits exactly on the low/medium edge and 40% on the medium/high edge.
 */

import { describe, expect, it } from 'vitest'

import { RISK_COLORS, meterColor } from './charts.js'

describe('meterColor', () => {
  it('calls a healthy figure low risk', () => {
    expect(meterColor(95)).toBe(RISK_COLORS.LOW)
    expect(meterColor(71)).toBe(RISK_COLORS.LOW)
  })

  it('bands the low/medium edge by component risk, not by the figure', () => {
    // 70% attendance -> risk 30 -> medium starts here.
    expect(meterColor(70)).toBe(RISK_COLORS.MEDIUM)
    expect(meterColor(70.5)).toBe(RISK_COLORS.LOW)
  })

  it('bands the medium/high edge the same way', () => {
    // 40% attendance -> risk 60 -> high starts here.
    expect(meterColor(40)).toBe(RISK_COLORS.HIGH)
    expect(meterColor(41)).toBe(RISK_COLORS.MEDIUM)
  })

  it('never paints a poor figure green', () => {
    // The defect this helper exists to prevent: 33.3% attendance and an
    // engagement score of 9 were both drawn in a reassuring colour.
    expect(meterColor(33.33)).toBe(RISK_COLORS.HIGH)
    expect(meterColor(9)).toBe(RISK_COLORS.HIGH)
    expect(meterColor(20.7)).toBe(RISK_COLORS.HIGH)
  })

  it('honours configured thresholds instead of the defaults', () => {
    const strict = { medium: 10, high: 20 }
    expect(meterColor(85, strict)).toBe(RISK_COLORS.MEDIUM)
    expect(meterColor(75, strict)).toBe(RISK_COLORS.HIGH)
    expect(meterColor(95, strict)).toBe(RISK_COLORS.LOW)
  })

  it('marks an unknown figure as needing more data', () => {
    expect(meterColor(null)).toBe(RISK_COLORS.INSUFFICIENT_DATA)
    expect(meterColor(undefined)).toBe(RISK_COLORS.INSUFFICIENT_DATA)
    expect(meterColor(Number.NaN)).toBe(RISK_COLORS.INSUFFICIENT_DATA)
  })
})
