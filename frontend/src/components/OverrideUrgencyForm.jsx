import { useState } from 'react'

/**
 * docs/ui-spec.md §10: "Override Urgency" (labeled "Set Urgency" when
 * opened on a null-urgency item, §5.0). Default selector value is the
 * current score when one exists; when it's null, nothing is pre-selected
 * and Submit stays disabled until a coordinator explicitly picks one —
 * "never blank" only applies once a real score exists to default to.
 */
export default function OverrideUrgencyForm({ currentScore, onSubmit, onCancel }) {
  const [score, setScore] = useState(currentScore ?? null)
  const [reason, setReason] = useState('')

  const canSubmit = score != null

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (!canSubmit) return
        onSubmit({ correctedScore: score, reason: reason || null })
      }}
    >
      <fieldset>
        <legend>Urgency</legend>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n}>
            <input
              type="radio"
              name="urgency-score"
              value={n}
              checked={score === n}
              onChange={() => setScore(n)}
            />
            {n}
          </label>
        ))}
      </fieldset>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Why? (helps the system calibrate on similar requests)"
      />
      <button type="submit" disabled={!canSubmit}>
        Submit
      </button>
      {onCancel && (
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      )}
    </form>
  )
}
