import { Link } from 'react-router-dom'
import SeverityBadge from './SeverityBadge.jsx'
import { useActionButton } from './useActionButton.js'
import './StandaloneRow.css'

/**
 * FE-06: the standalone row / Needs Manual Triage item — docs/ui-spec.md
 * §5.0, §5.2, §6.
 *
 * variant:
 *   - "triage": Needs Manual Triage section (§5.0). Same actions as
 *     "inbox" plus "Set Urgency" — none of the three are gated on
 *     urgency_score existing, so this item never dead-ends (principle 4).
 *   - "inbox": Intake & Verification Inbox sorted section (§5.2).
 *     Verify & Dispatch / Reject, optional Merge affordance.
 *   - "dispatch": Dispatch Queue's FR-504b case (§6) — verified=true, not
 *     yet dispatched. Single "Dispatch" action, deliberately NOT labeled
 *     "Verify & Dispatch" since a decision isn't pending anymore.
 */
export default function StandaloneRow({
  item,
  variant,
  hasSuggestedMerge = false,
  onVerifyDispatch,
  onReject,
  onSetUrgency,
  onMerge,
  onDispatch,
}) {
  const [runVerifyDispatch, verifyDispatchInFlight] = useActionButton(async () => onVerifyDispatch(item.id))
  const [runReject, rejectInFlight] = useActionButton(async () => onReject(item.id))
  const [runDispatch, dispatchInFlight] = useActionButton(async () => onDispatch(item.id))
  const [runMerge, mergeInFlight] = useActionButton(async () => onMerge(item.id))

  return (
    <div className="standalone-row" data-testid="standalone-row">
      <SeverityBadge score={item.urgency_score} />
      <span className="standalone-row-text">{item.need_description}</span>

      <div className="standalone-row-actions">
        {variant === 'dispatch' ? (
          <button type="button" onClick={runDispatch} disabled={dispatchInFlight}>
            Dispatch
          </button>
        ) : (
          <>
            <button type="button" onClick={runVerifyDispatch} disabled={verifyDispatchInFlight}>
              Verify & Dispatch
            </button>
            <button type="button" onClick={runReject} disabled={rejectInFlight}>
              Reject
            </button>
            {variant === 'triage' && (
              <button type="button" onClick={() => onSetUrgency(item.id)}>
                Set Urgency
              </button>
            )}
            {hasSuggestedMerge && (
              <button type="button" onClick={runMerge} disabled={mergeInFlight}>
                Merge
              </button>
            )}
            <Link to={`/dashboard/requests/${item.id}`}>details</Link>
          </>
        )}
      </div>
    </div>
  )
}
