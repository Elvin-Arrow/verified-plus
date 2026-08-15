import { useParams } from 'react-router-dom'
import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import ErrorBanner from '../../components/ErrorBanner.jsx'

/**
 * FE-12: Event detail — docs/ui-spec.md §5.1's "Event log" link, FR-602.
 * The Event-level action log (verify_event/approve_pending/
 * reject_flag_device/dismiss_cluster) is only visible here, never via any
 * single member's own GET /api/requests/{id}.
 */
export default function EventDetail() {
  const { id } = useParams()
  const { data, error, loading, refetch } = usePolling(() => api.getEventDetail(id), 0)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />
  if (!data) return null

  return (
    <div className="event-detail">
      <h1>Event {data.id}</h1>
      <p>Status: {data.status}</p>

      <section>
        <h2>Members</h2>
        <ul>
          {(data.members ?? []).map((m) => (
            <li key={m.id}>{m.need_description}</li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Pending members</h2>
        <ul>
          {(data.pending_members ?? []).map((m) => (
            <li key={m.id}>{m.need_description}</li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Action history</h2>
        <ul>
          {(data.action_history ?? []).map((a) => (
            <li key={a.id}>
              {a.timestamp} {a.actor} {a.action_type} {a.note && `— ${a.note}`}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
