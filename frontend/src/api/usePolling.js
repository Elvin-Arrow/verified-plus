import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * docs/design.md §6.2/§6.3: each view polls its GET endpoint on an
 * interval, holding results in local state — no websocket, no Redux.
 * `loading` is true only until the *first* successful/failed fetch
 * resolves; subsequent poll ticks update `data`/`error` in place without
 * ever flipping `loading` back on, per docs/ui-spec.md §11 ("existing
 * content stays visible with a subtle in-place indicator, never a
 * full-screen spinner that blanks the queue"). `refreshing` distinguishes
 * a background poll tick from the initial load for that in-place indicator.
 */
export function usePolling(fetchFn, intervalMs) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const fetchFnRef = useRef(fetchFn)
  fetchFnRef.current = fetchFn

  const refetch = useCallback(async () => {
    setRefreshing(true)
    try {
      const result = await fetchFnRef.current()
      setData(result)
      setError(null)
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refetch()
    if (!intervalMs) return undefined
    const id = setInterval(refetch, intervalMs)
    return () => clearInterval(id)
  }, [refetch, intervalMs])

  return { data, error, loading, refreshing, refetch }
}
