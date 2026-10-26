/** Risk badges must never rely on colour alone.
 *
 * Two of the four band colours fall below a 3:1 contrast ratio against
 * white, and colour is invisible to a colourblind reader regardless - so
 * every badge carries an icon and a text label. These tests pin that.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import RiskBadge, { RiskDot } from './RiskBadge.jsx'

describe('RiskBadge', () => {
  it.each([
    ['LOW', 'Low risk'],
    ['MEDIUM', 'Medium risk'],
    ['HIGH', 'High risk'],
    ['INSUFFICIENT_DATA', 'Needs more data'],
  ])('labels %s in words', (category, label) => {
    render(<RiskBadge category={category} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('ships an icon alongside the label, so colour is never the only cue', () => {
    const { container } = render(<RiskBadge category="HIGH" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.getByText('High risk')).toBeInTheDocument()
  })

  it('shows the score rounded to a whole number when given one', () => {
    render(<RiskBadge category="HIGH" score={77.8} />)
    expect(screen.getByText('78')).toBeInTheDocument()
  })

  it('omits the score when there is none, rather than showing zero', () => {
    render(<RiskBadge category="INSUFFICIENT_DATA" score={null} />)
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('shows a score of zero when that is the real value', () => {
    render(<RiskBadge category="LOW" score={0} />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('can show the band range', () => {
    render(<RiskBadge category="MEDIUM" showRange />)
    expect(screen.getByText('(30-59)')).toBeInTheDocument()
  })

  it('falls back to the neutral band for an unknown category', () => {
    render(<RiskBadge category="SOMETHING_ELSE" />)
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })
})

describe('RiskDot', () => {
  it('pairs the swatch with a label', () => {
    render(<RiskDot category="HIGH" />)
    expect(screen.getByText('High risk')).toBeInTheDocument()
  })

  it('accepts an override label', () => {
    render(<RiskDot category="LOW" label="Doing fine" />)
    expect(screen.getByText('Doing fine')).toBeInTheDocument()
  })
})
