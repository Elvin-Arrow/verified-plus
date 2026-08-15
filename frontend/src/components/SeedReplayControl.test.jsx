import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SeedReplayControl from './SeedReplayControl.jsx'
import * as api from '../api/client.js'

vi.mock('../api/client.js')

afterEach(() => vi.resetAllMocks())

// FE-14: docs/ui-spec.md §12, FR-702 — no default mode, Run disabled until chosen.
describe('SeedReplayControl', () => {
  it('opens the panel on toggle, with no mode pre-selected', async () => {
    render(<SeedReplayControl />)
    await userEvent.click(screen.getByRole('button', { name: /seed\/replay/i }))
    expect(screen.queryByRole('radio', { checked: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^run$/i })).toBeDisabled()
  })

  it('shows geofence radius / max cluster span inputs only in reset mode', async () => {
    render(<SeedReplayControl />)
    await userEvent.click(screen.getByRole('button', { name: /seed\/replay/i }))
    expect(screen.queryByLabelText(/geofence radius/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /reset/i }))
    expect(screen.getByLabelText(/geofence radius/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/max cluster span/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /^append$/i }))
    expect(screen.queryByLabelText(/geofence radius/i)).not.toBeInTheDocument()
  })

  it('Run becomes enabled once a mode is chosen', async () => {
    render(<SeedReplayControl />)
    await userEvent.click(screen.getByRole('button', { name: /seed\/replay/i }))
    await userEvent.click(screen.getByRole('radio', { name: /^append$/i }))
    expect(screen.getByRole('button', { name: /^run$/i })).toBeEnabled()
  })

  it('calls seedReplay with mode append and no spatial params', async () => {
    api.seedReplay.mockResolvedValue({ mode: 'append', requests_submitted: 50, wiped: false })
    render(<SeedReplayControl />)
    await userEvent.click(screen.getByRole('button', { name: /seed\/replay/i }))
    await userEvent.click(screen.getByRole('radio', { name: /^append$/i }))
    await userEvent.click(screen.getByRole('button', { name: /^run$/i }))
    expect(api.seedReplay).toHaveBeenCalledWith({ mode: 'append', geofenceRadiusKm: null, maxClusterSpanKm: null })
  })

  it('calls seedReplay with mode reset and the configured spatial params', async () => {
    api.seedReplay.mockResolvedValue({ mode: 'reset', requests_submitted: 50, wiped: true })
    render(<SeedReplayControl />)
    await userEvent.click(screen.getByRole('button', { name: /seed\/replay/i }))
    await userEvent.click(screen.getByRole('radio', { name: /reset/i }))

    const radiusInput = screen.getByLabelText(/geofence radius/i)
    await userEvent.clear(radiusInput)
    await userEvent.type(radiusInput, '2.5')

    await userEvent.click(screen.getByRole('button', { name: /^run$/i }))
    expect(api.seedReplay).toHaveBeenCalledWith({ mode: 'reset', geofenceRadiusKm: 2.5, maxClusterSpanKm: 1.5 })
  })
})
