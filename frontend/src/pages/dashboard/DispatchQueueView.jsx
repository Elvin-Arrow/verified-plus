import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import IncidentCard from '../../components/IncidentCard.jsx'
import StandaloneRow from '../../components/StandaloneRow.jsx'
import ErrorBanner from '../../components/ErrorBanner.jsx'

const POLL_INTERVAL_MS = 3000
const ACTOR = 'coordinator_1'

/**
 * FE-09: Dispatch Queue — docs/ui-spec.md §6, FR-403. Same list mechanics
 * as the Inbox's sorted section, no Needs Manual Triage section (a
 * null-urgency item can never be verified, so it structurally can't
 * appear here). Incident Cards use the "verified" variant (primary action
 * is Approve/dispatch, not Verify) and standalone rows use the "dispatch"
 * variant (the FR-504b case only).
 */
export default function DispatchQueueView() {
  const { data, error, loading, refetch } = usePolling(api.getDispatchQueue, POLL_INTERVAL_MS)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />

  const sorted = data?.sorted ?? []

  async function withRefetch(fn) {
    await fn()
    await refetch()
  }

  if (sorted.length === 0) return <p>No pending requests.</p>

  return (
    <div>
      {sorted.map((entry) =>
        entry.type === 'event' ? (
          <IncidentCard
            key={entry.item.id}
            event={entry.item}
            variant="verified"
            onApprove={(id) => withRefetch(() => api.dispatchEvent(id, ACTOR))}
            onApprovePending={(id) => withRefetch(() => api.approvePending(id, ACTOR))}
            onRejectAndFlagDevice={(eventId, deviceId) =>
              withRefetch(() => api.rejectAndFlagDevice(eventId, deviceId, ACTOR))
            }
            onSplitOut={(id) => withRefetch(() => api.splitOut(id, ACTOR))}
          />
        ) : (
          <StandaloneRow
            key={entry.item.id}
            item={entry.item}
            variant="dispatch"
            onDispatch={(id) => withRefetch(() => api.dispatchStandalone(id, ACTOR))}
          />
        )
      )}
    </div>
  )
}
