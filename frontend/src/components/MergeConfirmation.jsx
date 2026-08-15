import { useEffect, useState } from 'react'
import { getEventDetail, getRequestDetail } from '../api/client.js'

/**
 * docs/ui-spec.md §5.1/§10: clicking a Merge affordance opens a
 * confirmation showing both sides before calling POST
 * /api/requests/{id}/merge. When the suggested target is an Event, the
 * "other side" comes from GET /api/events/{id} — the same endpoint used
 * for the Event log, not a second bespoke fetch.
 */
export default function MergeConfirmation({ suggestedMerge, onConfirm, onCancel }) {
  const [otherSideText, setOtherSideText] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (suggestedMerge.target_event_id) {
        const event = await getEventDetail(suggestedMerge.target_event_id)
        if (!cancelled) setOtherSideText(event.members?.[0]?.need_description ?? '(event)')
      } else if (suggestedMerge.target_request_id) {
        const request = await getRequestDetail(suggestedMerge.target_request_id)
        if (!cancelled) setOtherSideText(request.need_description)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [suggestedMerge])

  return (
    <div role="dialog" aria-label="Confirm merge">
      <p>Merge with the {suggestedMerge.target_event_id ? 'event' : 'request'} {suggestedMerge.distance_km}km away?</p>
      {otherSideText != null && <p>{otherSideText}</p>}
      <button type="button" onClick={onConfirm}>
        Confirm
      </button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </div>
  )
}
