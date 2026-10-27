/** A legend must never name a line the chart cannot draw.
 *
 * The dashboard's trend endpoint returns assessment and attendance; the
 * per-student one returns assessment alone. The same component serves
 * both, so it has to decide what to draw from the data it was given.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import TrendChart from './TrendChart.jsx'

const BOTH = [
  { period: '2026-08', avg_percentage: 60.1, avg_attendance_percentage: 81.0 },
  { period: '2026-09', avg_percentage: 62.0, avg_attendance_percentage: 79.4 },
]

const ASSESSMENT_ONLY = [
  { period: '2026-08', avg_percentage: 86.9 },
  { period: '2026-09', avg_percentage: 81.9 },
]

function lines(container) {
  return container.querySelectorAll('.recharts-line-curve').length
}

describe('TrendChart', () => {
  it('draws both series and a legend when the data carries both', () => {
    const { container } = render(<TrendChart points={BOTH} />)
    expect(lines(container)).toBe(2)
    expect(screen.getByText('Assessment average')).toBeInTheDocument()
    expect(screen.getByText('Attendance rate')).toBeInTheDocument()
  })

  it('drops the absent series, and the legend with it', () => {
    const { container } = render(<TrendChart points={ASSESSMENT_ONLY} />)
    expect(lines(container)).toBe(1)
    // No legend box: with one series the card title names it.
    expect(screen.queryByText('Attendance rate')).not.toBeInTheDocument()
    expect(container.querySelector('.recharts-legend-wrapper')).toBeNull()
  })

  it('says so plainly when there is nothing to plot', () => {
    render(<TrendChart points={[]} />)
    expect(screen.getByText(/No performance history yet/i)).toBeInTheDocument()
  })
})
