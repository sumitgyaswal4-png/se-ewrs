/** Generic status chips for non-risk vocabularies. */

const TONES = {
  neutral: 'bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-200',
  brand: 'bg-brand-50 text-brand-800 ring-1 ring-inset ring-brand-200',
  success: 'bg-risk-low/10 text-[#076b07] ring-1 ring-inset ring-risk-low/30',
  warning: 'bg-risk-medium/15 text-[#875c00] ring-1 ring-inset ring-risk-medium/40',
  danger: 'bg-risk-high/10 text-[#9c2525] ring-1 ring-inset ring-risk-high/30',
}

export const ALERT_STATUS_TONE = {
  NEW: 'danger',
  ACKNOWLEDGED: 'warning',
  IN_PROGRESS: 'brand',
  RESOLVED: 'success',
}

export const SUBMISSION_TONE = {
  ON_TIME: 'success',
  LATE: 'warning',
  MISSING: 'danger',
}

export const ATTENDANCE_TONE = {
  PRESENT: 'success',
  LATE: 'warning',
  ABSENT: 'danger',
  EXCUSED: 'neutral',
}

export const OUTCOME_TONE = {
  IMPROVED: 'success',
  PENDING: 'neutral',
  NO_CHANGE: 'warning',
  ESCALATED: 'danger',
  DECLINED: 'neutral',
}

export default function Badge({ children, tone = 'neutral', icon: Icon, className = '' }) {
  return (
    <span className={`chip ${TONES[tone] ?? TONES.neutral} ${className}`}>
      {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
      {children}
    </span>
  )
}
