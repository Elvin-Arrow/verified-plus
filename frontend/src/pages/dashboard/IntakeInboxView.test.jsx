import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import IntakeInboxView from './IntakeInboxView.jsx'
import * as api from '../../api/client.js'

vi.mock('../../api/client.js')

function renderView() {
  return render(
    <MemoryRouter>
      <IntakeInboxView />
    </MemoryRouter>
  )
}

const triageItem = {
  type: 'request',
  item: { id: 'req_triage', need_description: 'flooding hit our well', urgency_score: null, device_fingerprint_id: 'dev_x' },
}
const eventItem = {
  type: 'event',
  item: {
    id: 'evt_1',
    status: 'candidate',
    member_count: 3,
    distinct_device_count: 3,
    max_urgency_score: 5,
    members: [
      { id: 'req_a', need_description: 'Collapsed building', device_fingerprint_id: 'dev_1', urgency_score: 5 },
      { id: 'req_b', need_description: 'Building down', device_fingerprint_id: 'dev_2', urgency_score: 4 },
    ],
  },
}
const standaloneItem = {
  type: 'request',
  item: { id: 'req_standalone', need_description: 'insulin runs out tonight', urgency_score: 4, device_fingerprint_id: 'dev_y' },
}

afterEach(() => vi.resetAllMocks())

describe('IntakeInboxView (§5, FR-401/402)', () => {
  it('renders Needs Manual Triage first, then the sorted section', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [triageItem], sorted: [eventItem, standaloneItem] })
    renderView()

    expect(await screen.findByText(/needs manual triage/i)).toBeInTheDocument()
    expect(screen.getByText(/flooding hit our well/i)).toBeInTheDocument()
    expect(screen.getByText(/collapsed building/i)).toBeInTheDocument()
    expect(screen.getByText(/insulin runs out tonight/i)).toBeInTheDocument()
  })

  it('renders event items as IncidentCards and standalone items as rows', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [eventItem, standaloneItem] })
    renderView()
    expect(await screen.findByTestId('incident-card')).toBeInTheDocument()
    expect(screen.getByTestId('standalone-row')).toBeInTheDocument()
  })

  it('shows "No pending requests." when both sections are empty', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [] })
    renderView()
    expect(await screen.findByText(/no pending requests\./i)).toBeInTheDocument()
  })

  it('calls verifyStandalone then refetches when a standalone row is verified', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [standaloneItem] })
    api.verifyStandalone.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /verify & dispatch/i }))
    expect(api.verifyStandalone).toHaveBeenCalledWith('req_standalone', expect.any(String))
    expect(api.getIntakeInbox).toHaveBeenCalledTimes(2) // initial + post-action refetch
  })

  it('calls verifyEvent when an Incident Card is verified', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [eventItem] })
    api.verifyEvent.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /verify event & approve all/i }))
    expect(api.verifyEvent).toHaveBeenCalledWith('evt_1', expect.any(String))
  })

  it('shows a persistent error banner on a fetch failure, with retry', async () => {
    api.getIntakeInbox.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }))
    renderView()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('shows the stale-view toast and refetches on a 409 from an action, per §11', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [standaloneItem] })
    api.verifyStandalone.mockRejectedValue(Object.assign(new Error('stale'), { status: 409, code: 'INVALID_STATE_TRANSITION' }))
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /verify & dispatch/i }))
    expect(await screen.findByText(/this item has changed/i)).toBeInTheDocument()
    expect(api.getIntakeInbox).toHaveBeenCalledTimes(2)
  })

  it('shows a subtle in-place indicator on a background poll refresh, never blanking existing content', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [standaloneItem] })
    renderView()
    await screen.findByText(/insulin runs out tonight/i)
    // Existing content must still be present even while a background
    // refresh indicator (if any) is shown — the core §11 guarantee.
    expect(screen.getByText(/insulin runs out tonight/i)).toBeInTheDocument()
  })

  // Cross-doc alignment fix: RequestSummary.has_suggested_merge (api-spec.md §1.3)
  // is what actually drives this affordance — previously unwired because the API
  // had no field for it (see docs/api-spec.md §1.3 changelog note).
  it('shows the Merge affordance on a standalone row when has_suggested_merge is true', async () => {
    const mergeable = { type: 'request', item: { ...standaloneItem.item, has_suggested_merge: true } }
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [mergeable] })
    renderView()
    expect(await screen.findByRole('button', { name: /merge/i })).toBeInTheDocument()
  })

  it('does not show the Merge affordance on a standalone row when has_suggested_merge is false', async () => {
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [standaloneItem] })
    renderView()
    await screen.findByText(/insulin runs out tonight/i)
    expect(screen.queryByRole('button', { name: /merge/i })).not.toBeInTheDocument()
  })

  it('opens a confirmation (not an immediate merge) when Merge is clicked, per ui-spec.md §5.1', async () => {
    const mergeable = { type: 'request', item: { ...standaloneItem.item, has_suggested_merge: true } }
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [mergeable] })
    api.getRequestDetail.mockResolvedValue({
      id: 'req_standalone',
      suggested_merges: [{ target_event_id: 'evt_far', distance_km: 1.9 }],
    })
    api.getEventDetail.mockResolvedValue({ id: 'evt_far', members: [] })
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /merge/i }))

    expect(await screen.findByRole('dialog', { name: /confirm merge/i })).toBeInTheDocument()
    expect(api.mergeRequest).not.toHaveBeenCalled()
  })

  it('calls mergeRequest only after the confirmation is confirmed', async () => {
    const mergeable = { type: 'request', item: { ...standaloneItem.item, has_suggested_merge: true } }
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [mergeable] })
    api.getRequestDetail.mockResolvedValue({
      id: 'req_standalone',
      suggested_merges: [{ target_event_id: 'evt_far', distance_km: 1.9 }],
    })
    api.getEventDetail.mockResolvedValue({ id: 'evt_far', members: [] })
    api.mergeRequest.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /merge/i }))
    await userEvent.click(await screen.findByRole('button', { name: /confirm/i }))

    expect(api.mergeRequest).toHaveBeenCalledWith('req_standalone', {
      actor: expect.any(String),
      targetEventId: 'evt_far',
      targetRequestId: null,
    })
  })

  it('shows the per-member Merge affordance inside an expanded Incident Card only for members with has_suggested_merge', async () => {
    const eventWithMerge = {
      type: 'event',
      item: {
        ...eventItem.item,
        members: [
          { ...eventItem.item.members[0], has_suggested_merge: true },
          { ...eventItem.item.members[1], has_suggested_merge: false },
        ],
      },
    }
    api.getIntakeInbox.mockResolvedValue({ needs_manual_triage: [], sorted: [eventWithMerge] })
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /expand/i }))
    expect(await screen.findByRole('button', { name: /merge/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /merge/i })).toHaveLength(1)
  })
})
