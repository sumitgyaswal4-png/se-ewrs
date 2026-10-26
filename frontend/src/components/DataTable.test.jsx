/** DataTable: the four states and server-side sorting. */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import DataTable from './DataTable.jsx'

const columns = [
  { key: 'name', header: 'Name', sortKey: 'name', render: (row) => row.name },
  { key: 'score', header: 'Score', align: 'right', render: (row) => row.score },
]

const rows = [
  { id: 1, name: 'Aisha Menon', score: 78 },
  { id: 2, name: 'Rehan Bose', score: 42 },
]

const rowKey = (row) => row.id

describe('DataTable states', () => {
  it('shows a loading state while the request is in flight', () => {
    render(<DataTable columns={columns} rows={[]} rowKey={rowKey} loading />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('Loading table data')).toBeInTheDocument()
  })

  it('shows the error message and a retry button on failure', async () => {
    const onRetry = vi.fn()
    render(
      <DataTable
        columns={columns}
        rows={[]}
        rowKey={rowKey}
        error={{ message: 'Could not reach the API.' }}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Could not reach the API.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('lists field-level problems from a validation error', () => {
    render(
      <DataTable
        columns={columns}
        rows={[]}
        rowKey={rowKey}
        error={{
          message: 'Request validation failed',
          problems: [{ field: 'semester', message: 'must be between 1 and 12' }],
        }}
      />,
    )
    expect(screen.getByText('semester')).toBeInTheDocument()
    expect(screen.getByText(/must be between 1 and 12/)).toBeInTheDocument()
  })

  it('shows an empty state with guidance, not a blank table', () => {
    render(
      <DataTable
        columns={columns}
        rows={[]}
        rowKey={rowKey}
        emptyTitle="No students yet"
        emptyDescription="Add one to get started."
      />,
    )
    expect(screen.getByText('No students yet')).toBeInTheDocument()
    expect(screen.getByText('Add one to get started.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('renders the rows once loaded', () => {
    render(<DataTable columns={columns} rows={rows} rowKey={rowKey} caption="Students" />)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('Aisha Menon')).toBeInTheDocument()
    expect(screen.getByText('Rehan Bose')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2
  })
})

describe('DataTable sorting', () => {
  it('reports the requested column and direction to the caller', async () => {
    const onSort = vi.fn()
    render(
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={rowKey}
        sortBy="name"
        sortDir="asc"
        onSort={onSort}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: /name/i }))
    // Already ascending, so the next click asks for descending.
    expect(onSort).toHaveBeenCalledWith('name', 'desc')
  })

  it('exposes the sort direction to assistive technology', () => {
    render(
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={rowKey}
        sortBy="name"
        sortDir="desc"
        onSort={vi.fn()}
      />,
    )
    expect(screen.getByRole('columnheader', { name: /name/i })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
  })

  it('does not make a column sortable without a sortKey', () => {
    const plain = [{ key: 'name', header: 'Name', render: (row) => row.name }]
    render(<DataTable columns={plain} rows={rows} rowKey={rowKey} onSort={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /name/i })).not.toBeInTheDocument()
  })
})
