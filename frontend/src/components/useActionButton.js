import { useCallback, useState } from 'react'

// docs/ui-spec.md §11: "Action in flight — the clicked control is disabled
// (not hidden — hiding it would shift layout under the coordinator's cursor
// mid-click on an adjacent control)." Shared by every row/card action button
// so this rule is enforced in one place, not re-implemented per component.
export function useActionButton(handler) {
  const [inFlight, setInFlight] = useState(false)
  const run = useCallback(
    async (...args) => {
      setInFlight(true)
      try {
        await handler(...args)
      } finally {
        setInFlight(false)
      }
    },
    [handler]
  )
  return [run, inFlight]
}
