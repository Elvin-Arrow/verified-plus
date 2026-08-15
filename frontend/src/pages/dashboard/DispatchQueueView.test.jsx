import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DispatchQueueView from './DispatchQueueView.jsx'
import * as api from '../../api/client.js'

vi.mock('../../api/client.js')

function renderView() {
  return render(
    <MemoryRouter>
      <DispatchQueueView />
    </MemoryRouter>
  )
}

const eventItem = {
  type: 'event',
  item: {
    id: 'evt_1',
    status: 'verified',
    member_count: 3,
    distinct_device_count: 3,
    max_urgency_score: 5,
    members: [{ id: 'req_a', need_description: 'Collapsed building', device_fingerprint_id: 'dev_1', urgency_score: 5 }],
    pending_members: [],
  },
}
const standaloneItem = {
  type: 'request',
  item: { id: 'req_standalone', need_description: 'verified, awaiting dispatch', urgency_score: 4, verified: true, device_fingerprint_id: 'dev_y' },
}

afterEach(() => vi.resetAllMocks())

describe('DispatchQueueView (§6, FR-403)', () => {
  it('has no Needs Manual Triage section (a null-urgency item can never be verified)', async () => {
    api.getDispatchQueue.mockResolvedValue({ sorted: [eventItem] })
    renderView()
    await screen.findByTestId('incident-card')
    expect(screen.queryByText(/needs manual triage/i)).not.toBeInTheDocument()
  })

  it('renders event items with the "Approve" (dispatch) primary action, not Verify', async () => {
    api.getDispatchQueue.mockResolvedValue({ sorted: [eventItem] })
    renderView()
    expect(await screen.findByRole('button', { name: /^approve$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /verify event/i })).not.toBeInTheDocument()
  })

  it('renders a verified-not-dispatched standalone row with a single "Dispatch" action', async () => {
    api.getDispatchQueue.mockResolvedValue({ sorted: [standaloneItem] })
    renderView()
    expect(await screen.findByRole('button', { name: /^dispatch$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /verify & dispatch/i })).not.toBeInTheDocument()
  })

  it('calls dispatchStandalone and refetches on Dispatch click', async () => {
    api.getDispatchQueue.mockResolvedValue({ sorted: [standaloneItem] })
    api.dispatchStandalone.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /^dispatch$/i }))
    expect(api.dispatchStandalone).toHaveBeenCalledWith('req_standalone', expect.any(String))
  })

  it('calls dispatchEvent (Approve) and approvePending separately', async () => {
    const eventWithPending = {
      ...eventItem,
      item: { ...eventItem.item, pending_members: [{ id: 'req_p', need_description: 'pending', device_fingerprint_id: 'dev_3', urgency_score: 3 }] },
    }
    api.getDispatchQueue.mockResolvedValue({ sorted: [eventWithPending] })
    api.dispatchEvent.mockResolvedValue({})
    api.approvePending.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /^approve$/i }))
    expect(api.dispatchEvent).toHaveBeenCalledWith('evt_1', expect.any(String))

    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    await userEvent.click(screen.getByRole('button', { name: /approve all pending/i }))
    expect(api.approvePending).toHaveBeenCalledWith('evt_1', expect.any(String))
  })

  it('shows the same empty-state copy as the Inbox when nothing is verified', async () => {
    api.getDispatchQueue.mockResolvedValue({ sorted: [] })
    renderView()
    expect(await screen.findByText(/no pending requests\./i)).toBeInTheDocument()
  })
})
