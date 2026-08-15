import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import { useActionErrorHandling } from '../../api/useActionErrorHandling.js'
import { useActionButton } from '../../components/useActionButton.js'
import ErrorBanner from '../../components/ErrorBanner.jsx'
import Toast from '../../components/Toast.jsx'

const POLL_INTERVAL_MS = 5000 // docs/design.md §6.3: 5s on lower-priority views.
const ACTOR = 'coordinator_1'

function RescueButton({ requestId, onRescue }) {
  const [run, inFlight] = useActionButton(async () => onRescue(requestId))
  return (
    <button type="button" onClick={run} disabled={inFlight}>
      Rescue
    </button>
  )
}

function RejectAllButton({ deviceId, onRejectAll }) {
  const [run, inFlight] = useActionButton(async () => onRejectAll(deviceId))
  return (
    <button type="button" onClick={run} disabled={inFlight}>
      Reject All
    </button>
  )
}

/**
 * FE-10/FE-13: Quarantine Inbox — docs/ui-spec.md §7, §11, FR-407.
 * Grouped by device, never a flat list. "Reject All" is scoped to one
 * device group at a time (never the whole tab); each request also gets
 * its own individual "Rescue".
 */
export default function QuarantineView() {
  const { data, error, loading, refreshing, refetch } = usePolling(api.getQuarantine, POLL_INTERVAL_MS)
  const { toast, bannerError, retryBanner, runAction } = useActionErrorHandling(refetch)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />

  const groups = data?.groups ?? []

  if (groups.length === 0) {
    return (
      <div>
        <Toast message={toast} />
        {bannerError && <ErrorBanner onRetry={retryBanner} />}
        <p>No quarantined requests.</p>
      </div>
    )
  }

  return (
    <div>
      <Toast message={toast} />
      {bannerError && <ErrorBanner onRetry={retryBanner} />}
      {refreshing && (
        <span className="poll-indicator" aria-label="Refreshing">
          ⟳
        </span>
      )}
      {groups.map((group) => (
        <div key={group.device_fingerprint_id} className="quarantine-group" data-testid={`quarantine-group-${group.device_fingerprint_id}`}>
          <div className="quarantine-group-header">
            <span>{group.device_fingerprint_id}</span>
            {group.device_flag && <span>(flagged)</span>}
            <RejectAllButton
              deviceId={group.device_fingerprint_id}
              onRejectAll={(id) => runAction(() => api.rejectAllQuarantined(id, ACTOR))}
            />
          </div>
          {group.requests.map((r) => (
            <div key={r.id} className="quarantine-request-row">
              <span>{r.need_description}</span>
              <RescueButton requestId={r.id} onRescue={(id) => runAction(() => api.rescueRequest(id, ACTOR))} />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
