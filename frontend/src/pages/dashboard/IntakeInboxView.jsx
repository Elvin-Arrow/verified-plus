import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import { useActionErrorHandling } from '../../api/useActionErrorHandling.js'
import { useMergeFlow } from '../../api/useMergeFlow.js'
import IncidentCard from '../../components/IncidentCard.jsx'
import StandaloneRow from '../../components/StandaloneRow.jsx'
import MergeConfirmation from '../../components/MergeConfirmation.jsx'
import ErrorBanner from '../../components/ErrorBanner.jsx'
import Toast from '../../components/Toast.jsx'

const POLL_INTERVAL_MS = 3000 // docs/design.md §6.3: 3s on the two live queues.
const ACTOR = 'coordinator_1' // no auth in this version, per api-spec.md §1.

/**
 * FE-08/FE-13: Intake & Verification Inbox — docs/ui-spec.md §5, §11,
 * FR-401/402. Two-section layout matching GET /api/intake-inbox's
 * response shape exactly: Needs Manual Triage (unsorted, always first)
 * then the sorted list of Incident Cards / standalone rows.
 */
export default function IntakeInboxView() {
  const { data, error, loading, refreshing, refetch } = usePolling(api.getIntakeInbox, POLL_INTERVAL_MS)
  const { toast, bannerError, retryBanner, runAction } = useActionErrorHandling(refetch)
  const { mergingTarget, openMergeConfirm, confirmMerge, cancelMerge } = useMergeFlow(runAction)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />

  const triage = data?.needs_manual_triage ?? []
  const sorted = data?.sorted ?? []
  const isEmpty = triage.length === 0 && sorted.length === 0

  return (
    <div>
      <Toast message={toast} />
      {bannerError && <ErrorBanner onRetry={retryBanner} />}
      {refreshing && (
        <span className="poll-indicator" aria-label="Refreshing">
          ⟳
        </span>
      )}

      {triage.length > 0 && (
        <section aria-label="Needs manual triage">
          <h2>⚠ Needs Manual Triage ({triage.length})</h2>
          {triage.map(({ item }) => (
            <StandaloneRow
              key={item.id}
              item={item}
              variant="triage"
              onVerifyDispatch={(id) => runAction(() => api.verifyStandalone(id, ACTOR))}
              onReject={(id) => runAction(() => api.rejectStandalone(id, ACTOR))}
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
                suggestedMergeRequestIds={entry.item.members
                  .filter((m) => m.has_suggested_merge)
                  .map((m) => m.id)}
                onVerifyEvent={(id) => runAction(() => api.verifyEvent(id, ACTOR))}
                onRejectAndFlagDevice={(eventId, deviceId) =>
                  runAction(() => api.rejectAndFlagDevice(eventId, deviceId, ACTOR))
                }
                onSplitOut={(id) => runAction(() => api.splitOut(id, ACTOR))}
                onDismissCluster={(id) => runAction(() => api.dismissEvent(id, ACTOR))}
                onMerge={openMergeConfirm}
              />
            ) : (
              <StandaloneRow
                key={entry.item.id}
                item={entry.item}
                variant="inbox"
                hasSuggestedMerge={entry.item.has_suggested_merge}
                onVerifyDispatch={(id) => runAction(() => api.verifyStandalone(id, ACTOR))}
                onReject={(id) => runAction(() => api.rejectStandalone(id, ACTOR))}
                onMerge={openMergeConfirm}
              />
            )
          )
        )}
      </section>

      {mergingTarget && (
        <MergeConfirmation suggestedMerge={mergingTarget} onConfirm={confirmMerge} onCancel={cancelMerge} />
      )}
    </div>
  )
}
