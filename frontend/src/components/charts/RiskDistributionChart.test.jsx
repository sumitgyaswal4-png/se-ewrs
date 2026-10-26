/** The risk-distribution stacked bar.
 *
 * Regression guard: a vertical-layout Recharts BarChart places its bars
 * against a *category* axis. Without one it renders silently empty - the
 * legend and counts still appear, so the bug is invisible in a snapshot
 * of the text. These tests assert that the marks are actually drawn.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import RiskDistributionChart from './RiskDistributionChart.jsx'

const distribution = [
  { category: 'HIGH', label: 'High risk (60-100)', count: 9 },
  { category: 'MEDIUM', label: 'Medium risk (30-59)', count: 26 },
  { category: 'LOW', label: 'Low risk (0-29)', count: 41 },
  { category: 'INSUFFICIENT_DATA', label: 'Needs more data', count: 4 },
]

describe('RiskDistributionChart', () => {
  it('draws one mark per band', () => {
    const { container } = render(<RiskDistributionChart distribution={distribution} />)
    expect(container.querySelectorAll('.recharts-rectangle').length).toBe(4)
  })

  it('labels every band in words beside its count', () => {
    render(<RiskDistributionChart distribution={distribution} />)
    expect(screen.getByText('High risk')).toBeInTheDocument()
    expect(screen.getByText('Medium risk')).toBeInTheDocument()
    expect(screen.getByText('Low risk')).toBeInTheDocument()
    expect(screen.getByText('Needs more data')).toBeInTheDocument()
  })

  it('shows the direct count and share for each band', () => {
    render(<RiskDistributionChart distribution={distribution} />)
    // 9 of 80 = 11%, 41 of 80 = 51%
    expect(screen.getByText('9')).toBeInTheDocument()
    expect(screen.getByText('(11%)')).toBeInTheDocument()
    expect(screen.getByText('41')).toBeInTheDocument()
    expect(screen.getByText('(51%)')).toBeInTheDocument()
  })

  it('shows an empty state rather than a zero-width bar when nothing is scored', () => {
    const { container } = render(
      <RiskDistributionChart
        distribution={[
          { category: 'HIGH', label: 'High', count: 0 },
          { category: 'LOW', label: 'Low', count: 0 },
        ]}
      />,
    )
    expect(screen.getByText('No risk scores yet')).toBeInTheDocument()
    expect(container.querySelectorAll('.recharts-rectangle').length).toBe(0)
  })

  it('handles a missing distribution without throwing', () => {
    render(<RiskDistributionChart distribution={undefined} />)
    expect(screen.getByText('No risk scores yet')).toBeInTheDocument()
  })

  it('still renders bands that the payload omits, as zero', () => {
    render(<RiskDistributionChart distribution={[{ category: 'LOW', label: 'Low', count: 5 }]} />)
    expect(screen.getByText('High risk')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })
})
