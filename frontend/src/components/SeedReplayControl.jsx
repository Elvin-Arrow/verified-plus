import { useState } from 'react'
import { seedReplay } from '../api/client.js'
import { useActionButton } from './useActionButton.js'
import './SeedReplayControl.css'

const DEFAULT_GEOFENCE_RADIUS_KM = 1.0
const DEFAULT_MAX_CLUSTER_SPAN_KM = 1.5

/**
 * FE-14: Seed/Replay control — docs/ui-spec.md §12, FR-701/702/208.
 * A presenter tool, not a coordinator workflow feature: a dashboard-chrome
 * dropdown, not a prominent primary button. No mode is pre-selected
 * (FR-702: "an explicit, documented choice... not an implicit default") —
 * Run stays disabled until a mode is explicitly chosen, mirroring the
 * API's refusal to accept an omitted mode.
 */
export default function SeedReplayControl() {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState(null)
  const [geofenceRadiusKm, setGeofenceRadiusKm] = useState(DEFAULT_GEOFENCE_RADIUS_KM)
  const [maxClusterSpanKm, setMaxClusterSpanKm] = useState(DEFAULT_MAX_CLUSTER_SPAN_KM)

  const [run, running] = useActionButton(async () => {
    await seedReplay({
      mode,
      geofenceRadiusKm: mode === 'reset' ? geofenceRadiusKm : null,
      maxClusterSpanKm: mode === 'reset' ? maxClusterSpanKm : null,
    })
  })

  return (
    <div className="seed-replay-control">
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        Seed/Replay ▾
      </button>
      {open && (
        <div className="seed-replay-panel">
          <fieldset>
            <legend>Mode</legend>
            <label>
              <input type="radio" name="seed-mode" checked={mode === 'reset'} onChange={() => setMode('reset')} />
              Reset
            </label>
            <label>
              <input type="radio" name="seed-mode" checked={mode === 'append'} onChange={() => setMode('append')} />
              Append
            </label>
          </fieldset>

          {mode === 'reset' && (
            <>
              <label htmlFor="geofence-radius">Geofence radius (km)</label>
              <input
                id="geofence-radius"
                type="number"
                step="0.1"
                value={geofenceRadiusKm}
                onChange={(e) => setGeofenceRadiusKm(Number(e.target.value))}
              />
              <label htmlFor="max-cluster-span">Max cluster span (km)</label>
              <input
                id="max-cluster-span"
                type="number"
                step="0.1"
                value={maxClusterSpanKm}
                onChange={(e) => setMaxClusterSpanKm(Number(e.target.value))}
              />
            </>
          )}

          <button type="button" onClick={run} disabled={mode == null || running}>
            Run
          </button>
        </div>
      )}
    </div>
  )
}
