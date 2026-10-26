/** Grouped risk bars: one stacked bar per department / semester / course. */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import GroupedRiskChart from './GroupedRiskChart.jsx'

const rows = [
  {
    group_key: 'MATH',
    group_label: 'Department of Mathematics',
    high_risk: 6,
    medium_risk: 18,
    low_risk: 24,
    insufficient_data: 4,
    total: 52,
  },
  {
    group_key: 'CSE',
    group_label: 'Computer Science',
    high_risk: 1,
    medium_risk: 4,
    low_risk: 7,
    insufficient_data: 0,
    total: 12,
  },
]

describe('GroupedRiskChart', () => {
  it('draws a segment per band per group', () => {
    const { container } = render(<GroupedRiskChart rows={rows} />)
    // 2 groups x 4 bands, minus the zero-height CSE "needs more data"
    expect(container.querySelectorAll('.recharts-rectangle').length).toBeGreaterThanOrEqual(7)
  })

  it('always carries a legend, so identity is never colour-alone', () => {
    render(<GroupedRiskChart rows={rows} />)
    expect(screen.getAllByText('High risk').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Medium risk').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Low risk').length).toBeGreaterThan(0)
  })

  it('shows an empty state for no rows', () => {
    render(<GroupedRiskChart rows={[]} />)
    expect(screen.getByText('Nothing to group')).toBeInTheDocument()
  })
})
