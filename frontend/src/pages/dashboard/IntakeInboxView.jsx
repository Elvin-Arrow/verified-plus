import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import IncidentCard from '../../components/IncidentCard.jsx'
import StandaloneRow from '../../components/StandaloneRow.jsx'
import ErrorBanner from '../../components/ErrorBanner.jsx'

const POLL_INTERVAL_MS = 3000 // docs/design.md §6.3: 3s on the two live queues.
const ACTOR = 'coordinator_1' // no auth in this version, per api-spec.md §1.

/**
 * FE-08: Intake & Verification Inbox — docs/ui-spec.md §5, FR-401/402.
 * Two-section layout matching GET /api/intake-inbox's response shape
 * exactly: Needs Manual Triage (unsorted, always first) then the sorted
 * list of Incident Cards / standalone rows.
 */
export default function IntakeInboxView() {
  const { data, error, loading, refetch } = usePolling(api.getIntakeInbox, POLL_INTERVAL_MS)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />

  const triage = data?.needs_manual_triage ?? []
  const sorted = data?.sorted ?? []
  const isEmpty = triage.length === 0 && sorted.length === 0

  async function withRefetch(fn) {
    await fn()
    await refetch()
  }

  return (
    <div>
      {triage.length > 0 && (
        <section aria-label="Needs manual triage">
          <h2>⚠ Needs Manual Triage ({triage.length})</h2>
          {triage.map(({ item }) => (
            <StandaloneRow
              key={item.id}
              item={item}
              variant="triage"
              onVerifyDispatch={(id) => withRefetch(() => api.verifyStandalone(id, ACTOR))}
              onReject={(id) => withRefetch(() => api.rejectStandalone(id, ACTOR))}
              onSetUrgency={() => {}}
            />
          ))}
        </section>
      )}

      <section aria-label="Sorted queue">
        {isEmpty ? (
          <p>No pending requests.</p>
        ) : (
          sorted.map((entry) =>
            entry.type === 'event' ? (
              <IncidentCard
                key={entry.item.id}
                event={entry.item}
                variant="candidate"
                onVerifyEvent={(id) => withRefetch(() => api.verifyEvent(id, ACTOR))}
                onRejectAndFlagDevice={(eventId, deviceId) =>
                  withRefetch(() => api.rejectAndFlagDevice(eventId, deviceId, ACTOR))
                }
                onSplitOut={(id) => withRefetch(() => api.splitOut(id, ACTOR))}
                onDismissCluster={(id) => withRefetch(() => api.dismissEvent(id, ACTOR))}
                onMerge={(id) => withRefetch(() => api.mergeRequest(id, { actor: ACTOR }))}
              />
            ) : (
              <StandaloneRow
                key={entry.item.id}
                item={entry.item}
                variant="inbox"
                onVerifyDispatch={(id) => withRefetch(() => api.verifyStandalone(id, ACTOR))}
                onReject={(id) => withRefetch(() => api.rejectStandalone(id, ACTOR))}
                onMerge={(id) => withRefetch(() => api.mergeRequest(id, { actor: ACTOR }))}
              />
            )
          )
        )}
      </section>
    </div>
  )
}
