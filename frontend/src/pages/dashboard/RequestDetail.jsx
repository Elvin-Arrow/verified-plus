import { useState } from 'react'
import { useParams } from 'react-router-dom'
import * as api from '../../api/client.js'
import { usePolling } from '../../api/usePolling.js'
import SeverityBadge from '../../components/SeverityBadge.jsx'
import OverrideUrgencyForm from '../../components/OverrideUrgencyForm.jsx'
import MergeConfirmation from '../../components/MergeConfirmation.jsx'
import ErrorBanner from '../../components/ErrorBanner.jsx'

const ACTOR = 'coordinator_1'

/**
 * FE-12: Request detail — docs/ui-spec.md §10, FR-506/602/603. Renders
 * GET /api/requests/{id}'s full response.
 */
export default function RequestDetail() {
  const { id } = useParams()
  const { data, error, loading, refetch } = usePolling(() => api.getRequestDetail(id), 0)
  const [overrideOpen, setOverrideOpen] = useState(false)
  const [mergingTarget, setMergingTarget] = useState(null)

  if (loading) return <div>Loading…</div>
  if (error) return <ErrorBanner onRetry={refetch} />
  if (!data) return null

  const isNullScore = data.urgency_score == null

  async function handleOverrideSubmit({ correctedScore, reason }) {
    await api.overrideUrgency(id, { actor: ACTOR, correctedScore, reason })
    setOverrideOpen(false)
    await refetch()
  }

  async function handleMergeConfirm() {
    await api.mergeRequest(id, {
      actor: ACTOR,
      targetEventId: mergingTarget.target_event_id ?? null,
      targetRequestId: mergingTarget.target_request_id ?? null,
    })
    setMergingTarget(null)
    await refetch()
  }

  return (
    <div className="request-detail">
      <h1>{data.need_description}</h1>
      <p>
        Submitted {data.submitted_at} · {data.device_fingerprint_id}
      </p>

      <section>
        <SeverityBadge score={data.urgency_score} />
        <p>{data.urgency_reasoning}</p>
        {!overrideOpen && (
          <button type="button" onClick={() => setOverrideOpen(true)}>
            {isNullScore ? 'Set Urgency' : 'Override Urgency'}
          </button>
        )}
        {overrideOpen && (
          <OverrideUrgencyForm
            currentScore={data.urgency_score}
            onSubmit={handleOverrideSubmit}
            onCancel={() => setOverrideOpen(false)}
          />
        )}
      </section>

      <section>
        <h2>Duplicate/match evaluation</h2>
        <ul>
          {(data.match_reasons ?? []).map((m) => (
            <li key={m.candidate_id}>
              {m.is_match ? '✓' : '✗'} matches {m.candidate_id} — {m.reason}
            </li>
          ))}
        </ul>
      </section>

      {(data.suggested_merges ?? []).map((sm, i) => (
        <section key={i}>
          <p>
            Possible related event {sm.distance_km}km away —{' '}
            <button type="button" onClick={() => setMergingTarget(sm)}>
              Merge
            </button>
          </p>
        </section>
      ))}

      {mergingTarget && (
        <MergeConfirmation
          suggestedMerge={mergingTarget}
          onConfirm={handleMergeConfirm}
          onCancel={() => setMergingTarget(null)}
        />
      )}

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
