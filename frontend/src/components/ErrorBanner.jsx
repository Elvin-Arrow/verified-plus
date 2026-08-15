// docs/ui-spec.md §11: "500/network failure — a persistent (not
// auto-dismissing) banner... with a manual retry action; never silently
// swallowed." Shared by every polling view (FE-08–11), formalized further
// in FE-13.
export default function ErrorBanner({ onRetry }) {
  return (
    <div className="error-banner" role="alert">
      <span>Something went wrong — retry</span>
      <button type="button" onClick={onRetry}>
        Retry
      </button>
    </div>
  )
}
