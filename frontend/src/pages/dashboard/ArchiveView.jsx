import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import SeverityBadge from '../../components/SeverityBadge.jsx'
import ErrorBanner from '../../components/ErrorBanner.jsx'

const POLL_INTERVAL_MS = 5000

function ScrutinyMarker() {
  // FR-309: a small outlined icon, not a color fill — never as alarming-
  // looking as an urgency color, and non-interactive (Quarantine is where
  // a flag is actually acted on, not here).
  return (
    <span data-testid="scrutiny-marker" title="This device has a confirmed fraud flag" aria-label="Flagged device">
      ⚑
    </span>
  )
}

function ArchiveRow({ item }) {
  return (
    <div className="archive-row" data-testid={`archive-row-${item.id}`}>
      <SeverityBadge score={item.urgency_score} />
      <span>{item.need_description}</span>
      {item.device_flagged && <ScrutinyMarker />}
    </div>
  )
}

/**
 * FE-11: Archive — docs/ui-spec.md §8, FR-406. Read-only, no action
 * buttons anywhere on this screen (that's the point of a terminal state).
 */
export default function ArchiveView() {
  const { data, error, loading, refetch } = usePolling(api.getArchive, POLL_INTERVAL_MS)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />

  const events = data?.events ?? []
  const standaloneRequests = data?.standalone_requests ?? []

  if (events.length === 0 && standaloneRequests.length === 0) return <p>Nothing archived yet.</p>

  return (
    <div>
      {events.map((event) => (
        <div key={event.id} className="archive-event">
          {event.members.map((m) => (
            <ArchiveRow key={m.id} item={m} />
          ))}
        </div>
      ))}
      {standaloneRequests.map((r) => (
        <ArchiveRow key={r.id} item={r} />
      ))}
    </div>
  )
}
