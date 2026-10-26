/** Display formatting helpers.
 *
 * Every function here distinguishes "no data" from "zero". A null
 * percentage renders as an em dash, never as 0% - the whole point of the
 * risk model is that a missing measurement is not a bad measurement.
 */

const DASH = '—'

export function percent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH
  return `${Number(value).toFixed(digits)}%`
}

export function score(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH
  return Number(value).toFixed(digits)
}

export function count(value) {
  if (value === null || value === undefined) return DASH
  return Number(value).toLocaleString()
}

export function dateOnly(value) {
  if (!value) return DASH
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return DASH
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function dateTime(value) {
  if (!value) return DASH
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return DASH
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function relativeDays(value) {
  if (!value) return DASH
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return DASH
  const days = Math.floor((Date.now() - parsed.getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  if (days < 365) return `${Math.floor(days / 30)} months ago`
  return `${Math.floor(days / 365)} years ago`
}

/** Turn an ENUM value into something readable: ON_TIME -> On time. */
export function humanise(value) {
  if (!value) return DASH
  const text = String(value).replace(/_/g, ' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function initials(fullName) {
  if (!fullName) return '?'
  return fullName
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('')
}

/** Split the engine's "a; b; c" factor string into a list. */
export function splitFactors(text) {
  if (!text) return []
  return text
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean)
}
