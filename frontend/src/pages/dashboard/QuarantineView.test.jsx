import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import QuarantineView from './QuarantineView.jsx'
import * as api from '../../api/client.js'

vi.mock('../../api/client.js')

function renderView() {
  return render(
    <MemoryRouter>
      <QuarantineView />
    </MemoryRouter>
  )
}

const group = {
  device_fingerprint_id: 'dev_x1y2',
  device_flag: true,
  requests: [
    { id: 'req_1', need_description: 'need water', submitted_at: '2026-08-15T12:00:00Z' },
    { id: 'req_2', need_description: 'need water urgently', submitted_at: '2026-08-15T13:00:00Z' },
  ],
}

afterEach(() => vi.resetAllMocks())

describe('QuarantineView (§7, FR-407)', () => {
  it('groups by device, showing the device id, flagged marker, and a device-scoped Reject All', async () => {
    api.getQuarantine.mockResolvedValue({ groups: [group] })
    renderView()
    const groupEl = await screen.findByTestId('quarantine-group-dev_x1y2')
    expect(within(groupEl).getByText(/flagged/i)).toBeInTheDocument()
    expect(within(groupEl).getByRole('button', { name: /reject all/i })).toBeInTheDocument()
  })

  it('each request within a group has its own individual Rescue action', async () => {
    api.getQuarantine.mockResolvedValue({ groups: [group] })
    renderView()
    const groupEl = await screen.findByTestId('quarantine-group-dev_x1y2')
    expect(within(groupEl).getAllByRole('button', { name: /rescue/i })).toHaveLength(2)
  })

  it('calls rejectAllQuarantined scoped to that device, not a blanket action', async () => {
    api.getQuarantine.mockResolvedValue({ groups: [group] })
    api.rejectAllQuarantined.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /reject all/i }))
    expect(api.rejectAllQuarantined).toHaveBeenCalledWith('dev_x1y2', expect.any(String))
  })

  it('calls rescueRequest for the individual request clicked', async () => {
    api.getQuarantine.mockResolvedValue({ groups: [group] })
    api.rescueRequest.mockResolvedValue({})
    renderView()
    const groupEl = await screen.findByTestId('quarantine-group-dev_x1y2')
    await userEvent.click(within(groupEl).getAllByRole('button', { name: /rescue/i })[0])
    expect(api.rescueRequest).toHaveBeenCalledWith('req_1', expect.any(String))
  })

  it('shows an empty state when there are no quarantined groups', async () => {
    api.getQuarantine.mockResolvedValue({ groups: [] })
    renderView()
    expect(await screen.findByText(/no quarantined requests/i)).toBeInTheDocument()
  })
})
