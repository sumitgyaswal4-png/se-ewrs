/** Data-fetching hooks.
 *
 * `useQuery` gives every page the same four states - loading, error,
 * empty and loaded - so no screen has to invent its own, and exposes
 * `reload` so a mutation can refresh the view it came from.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * @param fetcher  async function returning the payload
 * @param deps     dependency list; the request re-runs when it changes
 * @param options  { enabled, initialData }
 */
export function useQuery(fetcher, deps = [], options = {}) {
  const { enabled = true, initialData = null } = options
  const [data, setData] = useState(initialData)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(enabled)
  const [reloadToken, setReloadToken] = useState(0)

  // Guards against a slow response overwriting a newer one.
  const requestId = useRef(0)

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return undefined
    }

    const id = ++requestId.current
    let cancelled = false
    setLoading(true)
    setError(null)

    fetcher()
      .then((payload) => {
        if (cancelled || id !== requestId.current) return
        setData(payload)
      })
      .catch((caught) => {
        if (cancelled || id !== requestId.current) return
        setError(caught)
      })
      .finally(() => {
        if (cancelled || id !== requestId.current) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, reloadToken])

  const reload = useCallback(() => setReloadToken((token) => token + 1), [])

  return { data, error, loading, reload, setData }
}

/** Wraps a mutating call with pending state and error capture. */
export function useMutation(action) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  const run = useCallback(
    async (...args) => {
      setPending(true)
      setError(null)
      try {
        return await action(...args)
      } catch (caught) {
        setError(caught)
        throw caught
      } finally {
        setPending(false)
      }
    },
    [action],
  )

  return { run, pending, error, reset: () => setError(null) }
}

/** Delays a fast-changing value - used for search inputs. */
export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
