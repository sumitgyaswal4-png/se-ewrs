/** The risk component breakdown.
 *
 * The behaviour that matters: a component with no data must be shown as
 * explicitly unavailable, with its reason - never drawn as a zero bar,
 * which would read as "no risk" rather than "not measured".
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import RiskComponentChart from './RiskComponentChart.jsx'

const complete = [
  {
    name: 'Attendance',
    observed_value: 33.33,
    observed_label: '33.33% attended (5/15 sessions)',
    risk_value: 66.67,
    weight: 0.35,
    effective_weight: 0.35,
    contribution: 23.33,
    available: true,
    unavailable_reason: null,
  },
  {
    name: 'Academic',
    observed_value: 20.7,
    observed_label: '20.7% average across 5 graded assessment(s)',
    risk_value: 79.3,
    weight: 0.4,
    effective_weight: 0.4,
    contribution: 31.72,
    available: true,
    unavailable_reason: null,
  },
  {
    name: 'Engagement',
    observed_value: 9,
    observed_label: 'Engagement score 9/100',
    risk_value: 91,
    weight: 0.25,
    effective_weight: 0.25,
    contribution: 22.75,
    available: true,
    unavailable_reason: null,
  },
]

describe('RiskComponentChart', () => {
  it('draws a bar per available component', () => {
    const { container } = render(<RiskComponentChart components={complete} />)
    expect(container.querySelectorAll('.recharts-rectangle').length).toBe(3)
  })

  it('direct-labels each bar with its risk value', () => {
    // Scoped to the SVG label list: Recharts also renders a hidden
    // tooltip containing the same numbers, so an unscoped text query
    // would be ambiguous rather than wrong.
    const { container } = render(<RiskComponentChart components={complete} />)
    const labels = [...container.querySelectorAll('.recharts-label-list text')].map(
      (node) => node.textContent,
    )
    expect(labels).toEqual(['67', '79', '91'])
  })

  it('explains an unavailable component instead of drawing it as zero', () => {
    const partial = [
      complete[0],
      {
        ...complete[1],
        risk_value: null,
        observed_value: null,
        available: false,
        effective_weight: 0,
        contribution: null,
        unavailable_reason: 'No graded assessment yet -- not counted as a zero',
      },
      complete[2],
    ]
    const { container } = render(<RiskComponentChart components={partial} />)

    expect(container.querySelectorAll('.recharts-rectangle').length).toBe(2)
    expect(screen.getByText('Not counted')).toBeInTheDocument()
    expect(screen.getByText(/not counted as a zero/i)).toBeInTheDocument()
    expect(screen.getByText(/re-normalised/i)).toBeInTheDocument()
  })

  it('says so plainly when nothing can be scored', () => {
    const none = complete.map((c) => ({
      ...c,
      available: false,
      risk_value: null,
      effective_weight: 0,
      unavailable_reason: 'no data',
    }))
    render(<RiskComponentChart components={none} />)
    expect(
      screen.getByText(/none of the three components has enough data/i),
    ).toBeInTheDocument()
  })
})
