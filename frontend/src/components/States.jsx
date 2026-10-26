/** Loading, empty and error states.
 *
 * Every list and chart in the app renders through one of these, so the
 * four states a request can be in look the same everywhere.
 */

import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react'

export function Spinner({ className = 'h-5 w-5' }) {
  return <Loader2 className={`animate-spin ${className}`} aria-hidden="true" />
}

export function LoadingState({ label = 'Loading', rows = 3 }) {
  return (
    <div className="p-6" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex items-center gap-4">
            <div className="h-9 w-9 animate-pulse rounded-full bg-slate-200" />
            <div className="flex-1 space-y-2">
              <div className="h-3 w-1/3 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-slate-100" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ChartSkeleton({ height = 260 }) {
  return (
    <div className="p-5" role="status" aria-live="polite">
      <span className="sr-only">Loading chart</span>
      <div className="animate-pulse rounded-lg bg-slate-100" style={{ height }} />
    </div>
  )
}

export function EmptyState({
  title = 'Nothing to show yet',
  description,
  icon: Icon = Inbox,
  action,
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 rounded-full bg-slate-100 p-3">
        <Icon className="h-6 w-6 text-slate-400" aria-hidden="true" />
      </div>
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry, title = 'Could not load this data' }) {
  const message =
    error?.message ?? 'An unexpected error occurred while talking to the API.'
  return (
    <div role="alert" className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-risk-high/10 p-3">
        <AlertTriangle className="h-6 w-6 text-risk-high" aria-hidden="true" />
      </div>
      <p className="text-sm font-semibold text-slate-800">{title}</p>
      <p className="mt-1 max-w-lg text-sm text-slate-600">{message}</p>
      {Array.isArray(error?.problems) && error.problems.length > 0 && (
        <ul className="mt-3 space-y-1 text-left text-xs text-slate-500">
          {error.problems.map((problem) => (
            <li key={problem.field}>
              <span className="font-medium text-slate-700">{problem.field}</span>:{' '}
              {problem.message}
            </li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary mt-4">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  )
}

/**
 * Renders the right state for a query result.
 * Keeps every page from re-implementing the same four branches.
 */
export function QueryState({
  loading,
  error,
  isEmpty,
  onRetry,
  skeleton,
  empty,
  children,
}) {
  if (loading) return skeleton ?? <LoadingState />
  if (error) return <ErrorState error={error} onRetry={onRetry} />
  if (isEmpty) return empty ?? <EmptyState />
  return children
}
