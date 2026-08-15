import { render as rtlRender, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import IncidentCard from './IncidentCard.jsx'

function render(ui) {
  return rtlRender(<MemoryRouter>{ui}</MemoryRouter>)
}

const candidateEvent = {
  id: 'evt_1',
  status: 'candidate',
  member_count: 3,
  distinct_device_count: 3,
  max_urgency_score: 5,
  representative_location: { lat: 1, lng: 2 },
  members: [
    { id: 'req_a', need_description: 'Collapsed building sector 4', device_fingerprint_id: 'dev_1', urgency_score: 5 },
    { id: 'req_b', need_description: 'Building came down near us', device_fingerprint_id: 'dev_2', urgency_score: 4 },
    { id: 'req_c', need_description: 'Heard screaming from the rubble', device_fingerprint_id: 'dev_2', urgency_score: 5 },
  ],
}

const verifiedEvent = {
  ...candidateEvent,
  id: 'evt_2',
  status: 'verified',
  pending_members: [
    { id: 'req_p', need_description: 'Same street, need help too', device_fingerprint_id: 'dev_3', urgency_score: 3 },
  ],
}

describe('IncidentCard — collapsed (§5.1)', () => {
  it('shows severity at max_urgency_score, title, and corroboration badge collapsed', () => {
    render(<IncidentCard event={candidateEvent} variant="candidate" onVerifyEvent={vi.fn()} />)
    expect(screen.getByLabelText(/urgency 5/i)).toBeInTheDocument()
    expect(screen.getByText(/3 corroborating reports/i)).toBeInTheDocument()
    expect(screen.getByText(/3 devices/i)).toBeInTheDocument()
  })

  it('"Verify Event & Approve All" is available collapsed (principle 1)', () => {
    render(<IncidentCard event={candidateEvent} variant="candidate" onVerifyEvent={vi.fn()} />)
    expect(screen.getByRole('button', { name: /verify event & approve all/i })).toBeInTheDocument()
    expect(screen.queryByText(/dev_1/)).not.toBeInTheDocument()
  })

  it('verified variant collapsed shows "Approve" (dispatch), not "Verify"', () => {
    render(<IncidentCard event={verifiedEvent} variant="verified" onApprove={vi.fn()} onApprovePending={vi.fn()} />)
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /verify event/i })).not.toBeInTheDocument()
  })
})

describe('IncidentCard — expanded (§5.1)', () => {
  it('groups members by device fingerprint with a per-device Reject & Flag Device action', async () => {
    render(<IncidentCard event={candidateEvent} variant="candidate" onVerifyEvent={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} onDismissCluster={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))

    const group1 = screen.getByTestId('device-group-dev_1')
    expect(within(group1).getByText(/collapsed building sector 4/i)).toBeInTheDocument()
    expect(within(group1).getByRole('button', { name: /reject & flag device/i })).toBeInTheDocument()

    const group2 = screen.getByTestId('device-group-dev_2')
    expect(within(group2).getByText(/building came down near us/i)).toBeInTheDocument()
    expect(within(group2).getByText(/heard screaming from the rubble/i)).toBeInTheDocument()
  })

  it('each member row has its own Split Out action', async () => {
    render(<IncidentCard event={candidateEvent} variant="candidate" onVerifyEvent={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} onDismissCluster={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.getAllByRole('button', { name: /split out/i })).toHaveLength(3)
  })

  it('shows a card-level Dismiss Cluster action only for candidate Events', async () => {
    render(<IncidentCard event={candidateEvent} variant="candidate" onVerifyEvent={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} onDismissCluster={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.getByRole('button', { name: /dismiss cluster/i })).toBeInTheDocument()
  })

  it('never shows Dismiss Cluster for a verified Event', async () => {
    render(<IncidentCard event={verifiedEvent} variant="verified" onApprove={vi.fn()} onApprovePending={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.queryByRole('button', { name: /dismiss cluster/i })).not.toBeInTheDocument()
  })

  it('calls onRejectAndFlagDevice with the event and device id, scoped to that group', async () => {
    const onRejectAndFlagDevice = vi.fn()
    render(<IncidentCard event={candidateEvent} variant="candidate" onVerifyEvent={vi.fn()} onRejectAndFlagDevice={onRejectAndFlagDevice} onSplitOut={vi.fn()} onDismissCluster={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    const group2 = screen.getByTestId('device-group-dev_2')
    await userEvent.click(within(group2).getByRole('button', { name: /reject & flag device/i }))
    expect(onRejectAndFlagDevice).toHaveBeenCalledWith('evt_1', 'dev_2')
  })

  it('a verified Event with pending_members shows a distinct, device-grouped "N pending additions" sub-section with its own Approve All Pending action, separate from the main Approve button', async () => {
    render(<IncidentCard event={verifiedEvent} variant="verified" onApprove={vi.fn()} onApprovePending={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.getByText(/1 pending addition/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /approve all pending/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument()
  })

  it('shows a Merge affordance on a member row with a suggested merge, only in expanded view', async () => {
    render(
      <IncidentCard
        event={candidateEvent}
        variant="candidate"
        onVerifyEvent={vi.fn()}
        onRejectAndFlagDevice={vi.fn()}
        onSplitOut={vi.fn()}
        onDismissCluster={vi.fn()}
        onMerge={vi.fn()}
        suggestedMergeRequestIds={['req_a']}
      />
    )
    expect(screen.queryByRole('button', { name: /merge/i })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.getByRole('button', { name: /merge/i })).toBeInTheDocument()
  })

  it('has an Event log link sourced from the event detail endpoint', async () => {
    render(<IncidentCard event={candidateEvent} variant="candidate" onVerifyEvent={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} onDismissCluster={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.getByRole('link', { name: /event log/i })).toHaveAttribute('href', '/dashboard/events/evt_1')
  })
})
