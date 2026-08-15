import './SeverityBadge.css'

// FE-05: docs/ui-spec.md §9 severity color encoding, shared across every
// list view. Color is never the sole signal — always paired with the
// numeral (or an explicit pending marker), per principle "never color
// alone" and NFR-401's accessibility requirement.
const COLOR_CLASS = {
  5: 'severity-red',
  4: 'severity-orange',
  3: 'severity-yellow',
  2: 'severity-blue',
  1: 'severity-gray',
}

export default function SeverityBadge({ score }) {
  if (score == null) {
    return (
      <span
        className="severity-badge severity-pending"
        data-testid="severity-badge"
        role="img"
        aria-label="Urgency pending — evaluation unavailable"
        title="Urgency pending / unavailable"
      >
        ⚠
      </span>
    )
  }

  return (
    <span
      className={`severity-badge ${COLOR_CLASS[score] || ''}`}
      data-testid="severity-badge"
      role="img"
      aria-label={`Urgency ${score}`}
    >
      {score}
    </span>
  )
}
