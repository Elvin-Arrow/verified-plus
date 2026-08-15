import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import EventDetail from './EventDetail.jsx'
import * as api from '../../api/client.js'

vi.mock('../../api/client.js')

function renderAt(id) {
  return render(
    <MemoryRouter initialEntries={[`/dashboard/events/${id}`]}>
      <Routes>
        <Route path="/dashboard/events/:id" element={<EventDetail />} />
      </Routes>
    </MemoryRouter>
  )
}

afterEach(() => vi.resetAllMocks())

describe('EventDetail (§10, FR-602)', () => {
  it('renders members, pending members, and the Event-level action history distinct from any member log', async () => {
    api.getEventDetail.mockResolvedValue({
      id: 'evt_d4e5f6',
      status: 'verified',
      representative_location: { lat: 12.34, lng: 56.78 },
      verified_by: 'coordinator_1',
      verified_at: '2026-08-15T14:05:00Z',
      created_at: '2026-08-15T14:03:00Z',
      members: [{ id: 'req_a', need_description: 'member text' }],
      pending_members: [{ id: 'req_p', need_description: 'pending text' }],
      action_history: [
        { id: 'act_2', actor: 'coordinator_1', action_type: 'verify_event', target_id: 'evt_d4e5f6', timestamp: '2026-08-15T14:05:00Z', note: null },
      ],
    })
    renderAt('evt_d4e5f6')
    expect(await screen.findByText(/member text/i)).toBeInTheDocument()
    expect(screen.getByText(/pending text/i)).toBeInTheDocument()
    expect(screen.getByText(/verify_event/i)).toBeInTheDocument()
  })
})
