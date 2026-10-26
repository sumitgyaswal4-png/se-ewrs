/** The data-fetching hook's state machine. */

import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useMutation, useQuery } from './useApi.js'

describe('useQuery', () => {
  it('starts loading, then exposes the data', async () => {
    const fetcher = vi.fn().mockResolvedValue({ total: 3 })
    const { result } = renderHook(() => useQuery(fetcher, []))

    expect(result.current.loading).toBe(true)
    expect(result.current.data).toBeNull()

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual({ total: 3 })
    expect(result.current.error).toBeNull()
  })

  it('captures the error and stops loading on failure', async () => {
    const failure = new Error('API unreachable')
    const { result } = renderHook(() => useQuery(() => Promise.reject(failure), []))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(failure)
    expect(result.current.data).toBeNull()
  })

  it('does not fire while disabled', async () => {
    const fetcher = vi.fn().mockResolvedValue('x')
    const { result } = renderHook(() => useQuery(fetcher, [], { enabled: false }))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('re-runs on reload', async () => {
    const fetcher = vi.fn().mockResolvedValue(1)
    const { result } = renderHook(() => useQuery(fetcher, []))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetcher).toHaveBeenCalledTimes(1)

    act(() => result.current.reload())
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
  })

  it('re-runs when a dependency changes', async () => {
    const fetcher = vi.fn().mockResolvedValue(1)
    const { rerender } = renderHook(({ page }) => useQuery(fetcher, [page]), {
      initialProps: { page: 1 },
    })
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))

    rerender({ page: 2 })
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
  })

  it('ignores a slow response that a newer request has superseded', async () => {
    // The first call resolves last; its result must not overwrite the second.
    let resolveFirst
    const fetcher = vi
      .fn()
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockImplementationOnce(() => Promise.resolve('second'))

    const { result, rerender } = renderHook(({ page }) => useQuery(fetcher, [page]), {
      initialProps: { page: 1 },
    })
    rerender({ page: 2 })
    await waitFor(() => expect(result.current.data).toBe('second'))

    await act(async () => {
      resolveFirst('first')
    })
    expect(result.current.data).toBe('second')
  })

  it('accepts initial data so a page can render before the first response', () => {
    const { result } = renderHook(() =>
      useQuery(() => Promise.resolve([]), [], { initialData: [] }),
    )
    expect(result.current.data).toEqual([])
  })
})

describe('useMutation', () => {
  it('tracks pending state and returns the result', async () => {
    const action = vi.fn().mockResolvedValue({ detail: 'Saved' })
    const { result } = renderHook(() => useMutation(action))

    expect(result.current.pending).toBe(false)

    let returned
    await act(async () => {
      returned = await result.current.run({ id: 1 })
    })

    expect(action).toHaveBeenCalledWith({ id: 1 })
    expect(returned).toEqual({ detail: 'Saved' })
    expect(result.current.pending).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('records the error and re-throws so the caller can react', async () => {
    const failure = new Error('Conflict')
    const { result } = renderHook(() => useMutation(() => Promise.reject(failure)))

    await act(async () => {
      await expect(result.current.run()).rejects.toThrow('Conflict')
    })
    expect(result.current.error).toBe(failure)
    expect(result.current.pending).toBe(false)
  })
})
