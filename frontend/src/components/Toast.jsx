import './Toast.css'

// docs/ui-spec.md §11: 404/409 stale-view toast pattern — "This item has
// changed — refreshing" — not a raw error dialog.
export default function Toast({ message }) {
  if (!message) return null
  return (
    <div className="toast" role="status">
      {message}
    </div>
  )
}
