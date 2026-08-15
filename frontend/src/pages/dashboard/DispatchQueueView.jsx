import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import { useActionErrorHandling } from '../../api/useActionErrorHandling.js'
import IncidentCard from '../../components/IncidentCard.jsx'
import StandaloneRow from '../../components/StandaloneRow.jsx'
import ErrorBanner from '../../components/ErrorBanner.jsx'
import Toast from '../../components/Toast.jsx'

const POLL_INTERVAL_MS = 3000
const ACTOR = 'coordinator_1'

/**
 * FE-09/FE-13: Dispatch Queue — docs/ui-spec.md §6, §11, FR-403. Same
 * list mechanics as the Inbox's sorted section, no Needs Manual Triage
 * section here (a null-urgency item can never be verified, so it
 * structurally can't appear). Incident Cards use the "verified" variant
 * (primary action is Approve/dispatch, not Verify) and standalone rows
 * use the "dispatch" variant (the FR-504b case only).
 */
export default function DispatchQueueView() {
  const { data, error, loading, refreshing, refetch } = usePolling(api.getDispatchQueue, POLL_INTERVAL_MS)
  const { toast, bannerError, retryBanner, runAction } = useActionErrorHandling(refetch)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />

  const sorted = data?.sorted ?? []

  return (
    <div>
      <Toast message={toast} />
      {bannerError && <ErrorBanner onRetry={retryBanner} />}
      {refreshing && (
        <span className="poll-indicator" aria-label="Refreshing">
          ⟳
        </span>
      )}

      {sorted.length === 0 ? (
        <p>No pending requests.</p>
      ) : (
        sorted.map((entry) =>
          entry.type === 'event' ? (
            <IncidentCard
              key={entry.item.id}
              event={entry.item}
              variant="verified"
              onApprove={(id) => runAction(() => api.dispatchEvent(id, ACTOR))}
              onApprovePending={(id) => runAction(() => api.approvePending(id, ACTOR))}
              onRejectAndFlagDevice={(eventId, deviceId) =>
                runAction(() => api.rejectAndFlagDevice(eventId, deviceId, ACTOR))
              }
              onSplitOut={(id) => runAction(() => api.splitOut(id, ACTOR))}
            />
          ) : (
            <StandaloneRow
              key={entry.item.id}
              item={entry.item}
              variant="dispatch"
              onDispatch={(id) => runAction(() => api.dispatchStandalone(id, ACTOR))}
            />
          )
        )
      )}
    </div>
  )
}
