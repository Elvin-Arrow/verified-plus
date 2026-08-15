import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RequestDetail from './RequestDetail.jsx'
import * as api from '../../api/client.js'

vi.mock('../../api/client.js')

function renderAt(id) {
  return render(
    <MemoryRouter initialEntries={[`/dashboard/requests/${id}`]}>
      <Routes>
        <Route path="/dashboard/requests/:id" element={<RequestDetail />} />
      </Routes>
    </MemoryRouter>
  )
}

const baseDetail = {
  id: 'req_a1b2c3',
  need_description: 'Flooding hit our well, no clean water for 2 days',
  device_fingerprint_id: 'dev_x1y2',
  submitted_at: '2026-08-15T14:03:00Z',
  urgency_score: 4,
  urgency_reasoning: 'No access to clean water, tier 3 baseline.',
  original_urgency_score: null,
  match_reasons: [
    { candidate_id: 'req_990z', is_match: true, reason: 'Same flooded street, submitted 40 min ago, 90m away.' },
    { candidate_id: 'req_888y', is_match: false, reason: 'Different neighborhood, unrelated need.' },
  ],
  suggested_merges: [],
  action_history: [
    { id: 'act_1', actor: 'coordinator_1', action_type: 'override_urgency', target_id: 'req_a1b2c3', timestamp: '2026-08-15T14:10:00Z', note: 'Implies trapped.' },
  ],
}

afterEach(() => vi.resetAllMocks())

describe('RequestDetail (§10, FR-506/602/603)', () => {
  it('renders need text, urgency + reasoning, and action history', async () => {
    api.getRequestDetail.mockResolvedValue(baseDetail)
    renderAt('req_a1b2c3')
    expect(await screen.findByText(/flooding hit our well/i)).toBeInTheDocument()
    expect(screen.getByText(/no access to clean water, tier 3 baseline/i)).toBeInTheDocument()
    expect(screen.getByText(/implies trapped/i)).toBeInTheDocument()
  })

  it('renders every match_reasons entry, matches and non-matches alike', async () => {
    api.getRequestDetail.mockResolvedValue(baseDetail)
    renderAt('req_a1b2c3')
    await screen.findByText(/flooding hit our well/i)
    expect(screen.getByText(/same flooded street/i)).toBeInTheDocument()
    expect(screen.getByText(/different neighborhood, unrelated need/i)).toBeInTheDocument()
  })

  it('Override Urgency defaults the selector to the current score when one exists', async () => {
    api.getRequestDetail.mockResolvedValue(baseDetail)
    renderAt('req_a1b2c3')
    await userEvent.click(await screen.findByRole('button', { name: /override urgency/i }))
    expect(screen.getByRole('radio', { name: '4', checked: true })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit/i })).toBeEnabled()
  })

  it('for a null-urgency item, the button reads "Set Urgency", opens with nothing pre-selected, and Submit stays disabled until a value is picked', async () => {
    api.getRequestDetail.mockResolvedValue({ ...baseDetail, urgency_score: null, urgency_reasoning: null })
    renderAt('req_a1b2c3')
    await userEvent.click(await screen.findByRole('button', { name: /set urgency/i }))
    expect(screen.queryByRole('radio', { checked: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('radio', { name: '5' }))
    expect(screen.getByRole('button', { name: /submit/i })).toBeEnabled()
  })

  it('submits corrected_score and reason to override-urgency', async () => {
    api.getRequestDetail.mockResolvedValue(baseDetail)
    api.overrideUrgency.mockResolvedValue({ ...baseDetail, urgency_score: 5 })
    renderAt('req_a1b2c3')
    await userEvent.click(await screen.findByRole('button', { name: /override urgency/i }))
    await userEvent.click(screen.getByRole('radio', { name: '5' }))
    await userEvent.type(screen.getByPlaceholderText(/helps the system calibrate/i), 'Implies trapped, not discomfort')
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))
    expect(api.overrideUrgency).toHaveBeenCalledWith('req_a1b2c3', {
      actor: expect.any(String),
      correctedScore: 5,
      reason: 'Implies trapped, not discomfort',
    })
  })

  it('shows a Merge affordance when suggested_merges is non-empty, with a confirmation before calling merge', async () => {
    api.getRequestDetail.mockResolvedValue({
      ...baseDetail,
      suggested_merges: [{ target_event_id: 'evt_far_away', distance_km: 1.9 }],
    })
    api.getEventDetail.mockResolvedValue({ id: 'evt_far_away', representative_location: { lat: 1, lng: 2 }, members: [{ need_description: 'other side text' }] })
    api.mergeRequest.mockResolvedValue({})
    renderAt('req_a1b2c3')

    await userEvent.click(await screen.findByRole('button', { name: /merge/i }))
    expect(await screen.findByText(/other side text/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /confirm/i }))
    expect(api.mergeRequest).toHaveBeenCalledWith('req_a1b2c3', { actor: expect.any(String), targetEventId: 'evt_far_away', targetRequestId: null })
  })
})
