import { useState } from 'react'

// FE-04 scaffold: the toggle affordance lives in the dashboard chrome per
// docs/ui-spec.md §4/§12. The full Reset/Append form is built out in FE-14.
export default function SeedReplayControl() {
  const [open, setOpen] = useState(false)

  return (
    <div className="seed-replay-control">
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        Seed/Replay ▾
      </button>
      {open && <div className="seed-replay-panel">Seed/Replay form placeholder (FE-14)</div>}
    </div>
  )
}
