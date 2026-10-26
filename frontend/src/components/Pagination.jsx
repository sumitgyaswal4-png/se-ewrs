import { ChevronLeft, ChevronRight } from 'lucide-react'

import { PAGE_SIZES } from '../utils/constants.js'

export default function Pagination({ page, pageSize, total, pages, onPageChange, onPageSizeChange }) {
  if (!total) return null

  const first = (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, total)

  return (
    <nav
      className="flex flex-wrap items-center justify-between gap-3"
      aria-label="Table pagination"
    >
      <p className="text-xs text-slate-500">
        Showing <span className="font-semibold text-slate-700">{first}</span>–
        <span className="font-semibold text-slate-700">{last}</span> of{' '}
        <span className="font-semibold text-slate-700">{total.toLocaleString()}</span>
      </p>

      <div className="flex items-center gap-3">
        {onPageSizeChange && (
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            Rows
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs"
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="btn-secondary px-2 py-1.5"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <span className="px-2 text-xs font-medium text-slate-600" aria-live="polite">
            Page {page} of {Math.max(pages, 1)}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= pages}
            className="btn-secondary px-2 py-1.5"
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </nav>
  )
}
