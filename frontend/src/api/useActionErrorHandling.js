import { useCallback, useState } from 'react'

/**
 * FE-13: docs/ui-spec.md §11's action-level error rules, shared across
 * every mutating queue view (FE-08–FE-10):
 *   - 404 NOT_FOUND / 409 INVALID_STATE_TRANSITION: the client's view was
 *     stale (a concurrent action, or a poll-interval lag) — show a toast
 *     ("This item has changed — refreshing") and immediately re-fetch,
 *     never a raw error dialog. Both codes get the same treatment since
 *     they share the same root cause in practice.
 *   - anything else (500 / network failure): a persistent banner with a
 *     manual retry action, never silently swallowed — this is the one
 *     category the architecture doc treats as a real bug, not a
 *     designed-for path.
 */
export function useActionErrorHandling(refetch) {
  const [toast, setToast] = useState(null)
  const [bannerError, setBannerError] = useState(null)

  const runAction = useCallback(
    async (fn) => {
      try {
        await fn()
        await refetch()
      } catch (err) {
        if (err?.status === 404 || err?.status === 409) {
          setToast('This item has changed — refreshing')
          await refetch()
        } else {
          setBannerError(err)
        }
      }
    },
    [refetch]
  )

  const retryBanner = useCallback(() => {
    setBannerError(null)
    refetch()
  }, [refetch])

  return { toast, dismissToast: () => setToast(null), bannerError, retryBanner, runAction }
}
