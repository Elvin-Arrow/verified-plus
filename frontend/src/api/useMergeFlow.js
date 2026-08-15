import { useCallback, useState } from 'react'
import * as api from './client.js'

const ACTOR = 'coordinator_1' // no auth in this version, per api-spec.md §1.

/**
 * docs/ui-spec.md §5.1: a list-view Merge affordance must open a confirmation
 * showing both sides BEFORE calling POST /api/requests/{id}/merge. Since
 * RequestSummary (api-spec.md §1.3) only carries the cheap has_suggested_merge
 * boolean -- not the target/distance, which stays on the detail endpoint --
 * this hook fetches GET /api/requests/{id} on click to get the real
 * suggested_merges entry, then holds it until confirmed or cancelled.
 *
 * `runAction` is the same error-handling wrapper from useActionErrorHandling
 * (404/409 -> stale-view toast + refetch, else -> banner) so the confirmed
 * merge gets identical error treatment to every other mutating action.
 */
export function useMergeFlow(runAction) {
  const [mergingTarget, setMergingTarget] = useState(null)

  const openMergeConfirm = useCallback(async (requestId) => {
    const detail = await api.getRequestDetail(requestId)
    const suggestion = (detail.suggested_merges ?? [])[0]
    if (!suggestion) return // stale click -- the affordance's own data has since resolved
    setMergingTarget({ requestId, ...suggestion })
  }, [])

  const confirmMerge = useCallback(async () => {
    if (!mergingTarget) return
    const { requestId, target_event_id, target_request_id } = mergingTarget
    await runAction(() =>
      api.mergeRequest(requestId, {
        actor: ACTOR,
        targetEventId: target_event_id ?? null,
        targetRequestId: target_request_id ?? null,
      })
    )
    setMergingTarget(null)
  }, [mergingTarget, runAction])

  const cancelMerge = useCallback(() => setMergingTarget(null), [])

  return { mergingTarget, openMergeConfirm, confirmMerge, cancelMerge }
}
