import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ArchiveView from './ArchiveView.jsx'
import * as api from '../../api/client.js'

vi.mock('../../api/client.js')

function renderView() {
  return render(
    <MemoryRouter>
      <ArchiveView />
    </MemoryRouter>
  )
}

const archiveData = {
  events: [
    {
      id: 'evt_1',
      status: 'dispatched',
      members: [{ id: 'req_a', need_description: 'Collapsed building', device_flagged: false, urgency_score: 5 }],
    },
  ],
  standalone_requests: [
    { id: 'req_b', need_description: 'need blankets', status: 'rejected', device_flagged: true, urgency_score: 2 },
  ],
}

afterEach(() => vi.resetAllMocks())

describe('ArchiveView (§8, FR-406)', () => {
  it('renders dispatched events and terminal standalone requests', async () => {
    api.getArchive.mockResolvedValue(archiveData)
    renderView()
    expect(await screen.findByText(/collapsed building/i)).toBeInTheDocument()
    expect(screen.getByText(/need blankets/i)).toBeInTheDocument()
  })

  it('is entirely read-only — no action buttons anywhere on the screen', async () => {
    api.getArchive.mockResolvedValue(archiveData)
    renderView()
    await screen.findByText(/collapsed building/i)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('shows a static, non-interactive scrutiny marker for a flagged device (FR-309)', async () => {
    api.getArchive.mockResolvedValue(archiveData)
    renderView()
    const row = await screen.findByTestId('archive-row-req_b')
    expect(row.querySelector('[data-testid="scrutiny-marker"]')).toBeInTheDocument()
    const cleanRow = screen.getByTestId('archive-row-req_a')
    expect(cleanRow.querySelector('[data-testid="scrutiny-marker"]')).not.toBeInTheDocument()
  })
})
