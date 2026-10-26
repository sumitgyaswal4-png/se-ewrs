/** Formatting helpers.
 *
 * The behaviour that matters most: a missing measurement must render as
 * an em dash, never as 0 or 0%. The risk model's whole premise is that
 * no data is not the same as bad data, and the UI has to say so too.
 */

import { describe, expect, it } from 'vitest'

import {
  count,
  dateOnly,
  dateTime,
  humanise,
  initials,
  percent,
  relativeDays,
  score,
  splitFactors,
} from './format.js'

const DASH = '—'

describe('percent', () => {
  it('formats a number with one decimal by default', () => {
    expect(percent(75)).toBe('75.0%')
    expect(percent(66.666)).toBe('66.7%')
  })

  it('honours the requested precision', () => {
    expect(percent(75.44, 0)).toBe('75%')
    expect(percent(75.456, 2)).toBe('75.46%')
  })

  it('renders zero as 0%, not as missing', () => {
    expect(percent(0)).toBe('0.0%')
  })

  it('renders null and undefined as an em dash', () => {
    expect(percent(null)).toBe(DASH)
    expect(percent(undefined)).toBe(DASH)
  })

  it('does not pass NaN through as a number', () => {
    expect(percent(NaN)).toBe(DASH)
  })
})

describe('score', () => {
  it('formats a risk score', () => {
    expect(score(61.8)).toBe('61.8')
    expect(score(0)).toBe('0.0')
    expect(score(100)).toBe('100.0')
  })

  it('distinguishes an unscored profile from a zero score', () => {
    expect(score(null)).toBe(DASH)
    expect(score(0)).not.toBe(DASH)
  })
})

describe('count', () => {
  it('thousand-separates', () => {
    expect(count(1234)).toBe((1234).toLocaleString())
  })

  it('keeps zero as zero', () => {
    expect(count(0)).toBe('0')
  })

  it('renders null as an em dash', () => {
    expect(count(null)).toBe(DASH)
  })
})

describe('dateOnly and dateTime', () => {
  it('renders a valid date', () => {
    expect(dateOnly('2026-03-14')).toContain('2026')
  })

  it('renders an invalid or empty date as an em dash', () => {
    expect(dateOnly(null)).toBe(DASH)
    expect(dateOnly('')).toBe(DASH)
    expect(dateOnly('not-a-date')).toBe(DASH)
    expect(dateTime(null)).toBe(DASH)
    expect(dateTime('nonsense')).toBe(DASH)
  })
})

describe('relativeDays', () => {
  function daysAgo(days) {
    return new Date(Date.now() - days * 86_400_000).toISOString()
  }

  it('describes recent dates in words', () => {
    expect(relativeDays(daysAgo(0))).toBe('today')
    expect(relativeDays(daysAgo(1))).toBe('yesterday')
    expect(relativeDays(daysAgo(5))).toBe('5 days ago')
  })

  it('switches to months and years as the gap grows', () => {
    expect(relativeDays(daysAgo(60))).toBe('2 months ago')
    expect(relativeDays(daysAgo(400))).toBe('1 years ago')
  })

  it('renders a missing date as an em dash', () => {
    expect(relativeDays(null)).toBe(DASH)
  })
})

describe('humanise', () => {
  it('turns a database ENUM into a readable phrase', () => {
    expect(humanise('ON_TIME')).toBe('On time')
    expect(humanise('INSUFFICIENT_DATA')).toBe('Insufficient data')
    expect(humanise('TUTORING_REFERRAL')).toBe('Tutoring referral')
  })

  it('renders a missing value as an em dash', () => {
    expect(humanise(null)).toBe(DASH)
    expect(humanise('')).toBe(DASH)
  })
})

describe('initials', () => {
  it('takes at most two initials', () => {
    expect(initials('Rohit Khanna')).toBe('RK')
    expect(initials('Anita')).toBe('A')
    expect(initials('Maria del Carmen Santos')).toBe('MD')
  })

  it('falls back to a question mark', () => {
    expect(initials(null)).toBe('?')
    expect(initials('')).toBe('?')
  })
})

describe('splitFactors', () => {
  it('splits the risk engine factor string on semicolons', () => {
    const factors = splitFactors('Low attendance (45%); 2 missing submission(s); 1 late')
    expect(factors).toEqual([
      'Low attendance (45%)',
      '2 missing submission(s)',
      '1 late',
    ])
  })

  it('drops empty fragments and trailing separators', () => {
    expect(splitFactors('a;; b;')).toEqual(['a', 'b'])
  })

  it('returns an empty list for no factors', () => {
    expect(splitFactors(null)).toEqual([])
    expect(splitFactors('')).toEqual([])
  })
})
