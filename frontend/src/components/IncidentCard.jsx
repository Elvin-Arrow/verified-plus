import { useState } from 'react'
import { Link } from 'react-router-dom'
import SeverityBadge from './SeverityBadge.jsx'
import { useActionButton } from './useActionButton.js'
import './IncidentCard.css'

function groupByDevice(members) {
  const groups = new Map()
  for (const m of members) {
    if (!groups.has(m.device_fingerprint_id)) groups.set(m.device_fingerprint_id, [])
    groups.get(m.device_fingerprint_id).push(m)
  }
  return groups
}

function DeviceGroupActionButton({ deviceId, eventId, onRejectAndFlagDevice }) {
  const [run, inFlight] = useActionButton(async () => onRejectAndFlagDevice(eventId, deviceId))
  return (
    <button type="button" onClick={run} disabled={inFlight}>
      Reject & Flag Device
    </button>
  )
}

function SplitOutButton({ requestId, onSplitOut }) {
  const [run, inFlight] = useActionButton(async () => onSplitOut(requestId))
  return (
    <button type="button" onClick={run} disabled={inFlight} aria-label={`Split Out ${requestId}`}>
      ✕ Split Out
    </button>
  )
}

function MergeButton({ requestId, onMerge }) {
  const [run, inFlight] = useActionButton(async () => onMerge(requestId))
  return (
    <button type="button" onClick={run} disabled={inFlight}>
      ⚠ Possible related event — Merge?
    </button>
  )
}

/**
 * FE-07: Incident Card — docs/ui-spec.md §5.1 (candidate/Intake Inbox) and
 * §6 (verified/Dispatch Queue). Collapsed by default; every primary action
 * is available collapsed (principle 1). Expanded view groups members by
 * device fingerprint (FR-503) with a per-device Reject & Flag Device
 * action, a per-member Split Out, and — candidate Events only — a
 * card-level Dismiss Cluster, visually separated from per-device actions.
 */
export default function IncidentCard({
  event,
  variant, // "candidate" | "verified"
  onVerifyEvent,
  onApprove,
  onApprovePending,
  onRejectAndFlagDevice,
  onSplitOut,
  onDismissCluster,
  onMerge,
  suggestedMergeRequestIds = [],
}) {
  const [expanded, setExpanded] = useState(false)
  const [runVerify, verifyInFlight] = useActionButton(async () => onVerifyEvent(event.id))
  const [runApprove, approveInFlight] = useActionButton(async () => onApprove(event.id))
  const [runApprovePending, approvePendingInFlight] = useActionButton(async () => onApprovePending(event.id))
  const [runDismiss, dismissInFlight] = useActionButton(async () => onDismissCluster(event.id))

  const title = event.members?.[0]?.need_description || 'Incident'
  const deviceGroups = expanded ? groupByDevice(event.members || []) : new Map()
  const pendingGroups = expanded ? groupByDevice(event.pending_members || []) : new Map()

  return (
    <div className="incident-card" data-testid="incident-card">
      <div className="incident-card-header">
        <SeverityBadge score={event.max_urgency_score} />
        <div className="incident-card-title">
          <span>{title}</span>
          <span className="incident-card-badge">
            {event.member_count} corroborating reports · {event.distinct_device_count} devices
          </span>
        </div>
        <div className="incident-card-primary-action">
          {variant === 'candidate' ? (
            <button type="button" onClick={runVerify} disabled={verifyInFlight}>
              Verify Event & Approve All
            </button>
          ) : (
            <button type="button" onClick={runApprove} disabled={approveInFlight}>
              Approve
            </button>
          )}
        </div>
        <button type="button" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'collapse ▴' : 'expand ▾'}
        </button>
      </div>

      {expanded && (
        <div className="incident-card-expanded">
          {[...deviceGroups.entries()].map(([deviceId, members]) => (
            <div className="device-group" data-testid={`device-group-${deviceId}`} key={deviceId}>
              <div className="device-group-header">{deviceId}</div>
              {members.map((m) => (
                <div className="device-group-member" key={m.id}>
                  <SeverityBadge score={m.urgency_score} />
                  <span>{m.need_description}</span>
                  <SplitOutButton requestId={m.id} onSplitOut={onSplitOut} />
                  {suggestedMergeRequestIds.includes(m.id) && <MergeButton requestId={m.id} onMerge={onMerge} />}
                </div>
              ))}
              <DeviceGroupActionButton deviceId={deviceId} eventId={event.id} onRejectAndFlagDevice={onRejectAndFlagDevice} />
            </div>
          ))}

          {variant === 'candidate' && (
            <div className="incident-card-dismiss">
              <button type="button" onClick={runDismiss} disabled={dismissInFlight}>
                Dismiss Cluster
              </button>
            </div>
          )}

          {variant === 'verified' && pendingGroups.size > 0 && (
            <div className="incident-card-pending" data-testid="pending-additions">
              <div className="incident-card-pending-header">
                {event.pending_members.length} pending addition{event.pending_members.length === 1 ? '' : 's'}, awaiting review
              </div>
              {[...pendingGroups.entries()].map(([deviceId, members]) => (
                <div className="device-group" data-testid={`pending-device-group-${deviceId}`} key={deviceId}>
                  <div className="device-group-header">{deviceId}</div>
                  {members.map((m) => (
                    <div className="device-group-member" key={m.id}>
                      <SeverityBadge score={m.urgency_score} />
                      <span>{m.need_description}</span>
                    </div>
                  ))}
                </div>
              ))}
              <button type="button" onClick={runApprovePending} disabled={approvePendingInFlight}>
                Approve All Pending
              </button>
            </div>
          )}

          <div className="incident-card-footer">
            <Link to={`/dashboard/events/${event.id}`}>Event log</Link>
          </div>
        </div>
      )}
    </div>
  )
}
