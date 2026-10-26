/** A sortable, accessible table with built-in loading / empty / error states.
 *
 * Sorting is server-side: the component reports the requested column and
 * direction, and the page passes them to the API. Sorting only the rows
 * on the current page would be a lie.
 */

import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'

import { EmptyState, ErrorState, LoadingState } from './States.jsx'

export default function DataTable({
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  sortBy,
  sortDir,
  onSort,
  emptyTitle,
  emptyDescription,
  emptyAction,
  caption,
  onRowClick,
}) {
  if (loading) return <LoadingState rows={5} label="Loading table data" />
  if (error) return <ErrorState error={error} onRetry={onRetry} />
  if (!rows?.length) {
    return (
      <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-slate-50">
          <tr>
            {columns.map((column) => {
              const sortable = Boolean(column.sortKey && onSort)
              const active = sortable && sortBy === column.sortKey
              const nextDir = active && sortDir === 'asc' ? 'desc' : 'asc'
              const SortIcon = !active ? ArrowUpDown : sortDir === 'asc' ? ArrowUp : ArrowDown

              return (
                <th
                  key={column.key}
                  scope="col"
                  className={`th ${column.align === 'right' ? 'text-right' : ''} ${
                    column.headerClassName ?? ''
                  }`}
                  aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => onSort(column.sortKey, nextDir)}
                      className={`inline-flex items-center gap-1.5 rounded hover:text-slate-800 ${
                        active ? 'text-brand-700' : ''
                      }`}
                    >
                      {column.header}
                      <SortIcon className="h-3 w-3" aria-hidden="true" />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows.map((row, index) => (
            <tr
              key={rowKey(row, index)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`transition ${
                onRowClick ? 'cursor-pointer hover:bg-brand-50/60' : 'hover:bg-slate-50'
              }`}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`td ${column.align === 'right' ? 'text-right' : ''} ${
                    column.cellClassName ?? ''
                  }`}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
