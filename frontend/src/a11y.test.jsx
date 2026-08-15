import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import IntakeForm from './pages/intake/IntakeForm.jsx'
import IncidentCard from './components/IncidentCard.jsx'
import StandaloneRow from './components/StandaloneRow.jsx'
import SeverityBadge from './components/SeverityBadge.jsx'
import QuarantineView from './pages/dashboard/QuarantineView.jsx'
import ArchiveView from './pages/dashboard/ArchiveView.jsx'
import * as api from './api/client.js'

vi.mock('./api/client.js')

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

afterEach(() => vi.resetAllMocks())

// FE-15: docs/ui-spec.md §13 — automated axe pass across the key
// screens/components, alongside the manual keyboard/aria checks below.
describe('Accessibility — automated (axe)', () => {
  it('IntakeForm has no violations', async () => {
    const { container } = render(<IntakeForm />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('a collapsed and an expanded IncidentCard have no violations', async () => {
    const event = {
      id: 'evt_1',
      status: 'candidate',
      member_count: 2,
      distinct_device_count: 2,
      max_urgency_score: 5,
      members: [
        { id: 'req_a', need_description: 'Collapsed building', device_fingerprint_id: 'dev_1', urgency_score: 5 },
        { id: 'req_b', need_description: 'Building down', device_fingerprint_id: 'dev_2', urgency_score: 4 },
      ],
    }
    const { container } = renderWithRouter(
      <IncidentCard event={event} variant="candidate" onVerifyEvent={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} onDismissCluster={vi.fn()} />
    )
    expect(await axe(container)).toHaveNoViolations()

    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(await axe(container)).toHaveNoViolations()
  })

  it('a StandaloneRow (triage variant, null urgency) has no violations', async () => {
    const { container } = renderWithRouter(
      <StandaloneRow
        item={{ id: 'req_1', need_description: 'flooding hit our well', urgency_score: null, device_fingerprint_id: 'dev_x' }}
        variant="triage"
        onVerifyDispatch={vi.fn()}
        onReject={vi.fn()}
        onSetUrgency={vi.fn()}
      />
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('SeverityBadge (both a real score and the pending state) has no violations', async () => {
    const { container } = render(
      <div>
        <SeverityBadge score={5} />
        <SeverityBadge score={null} />
      </div>
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('QuarantineView has no violations', async () => {
    api.getQuarantine.mockResolvedValue({
      groups: [{ device_fingerprint_id: 'dev_x1y2', device_flag: true, requests: [{ id: 'req_1', need_description: 'need water' }] }],
    })
    const { container } = renderWithRouter(<QuarantineView />)
    await screen.findByText(/need water/i)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('ArchiveView has no violations', async () => {
    api.getArchive.mockResolvedValue({
      events: [{ id: 'evt_1', status: 'dispatched', members: [{ id: 'req_a', need_description: 'text', device_flagged: true, urgency_score: 3 }] }],
      standalone_requests: [],
    })
    const { container } = renderWithRouter(<ArchiveView />)
    await screen.findByText(/text/i)
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('Accessibility — manual checklist, encoded as assertions', () => {
  it('every icon-only affordance (Split Out) has an aria-label, not icon-only with no text equivalent', () => {
    const event = {
      id: 'evt_1',
      status: 'candidate',
      member_count: 2,
      distinct_device_count: 2,
      max_urgency_score: 5,
      members: [
        { id: 'req_a', need_description: 'a', device_fingerprint_id: 'dev_1', urgency_score: 5 },
        { id: 'req_b', need_description: 'b', device_fingerprint_id: 'dev_2', urgency_score: 4 },
      ],
    }
    renderWithRouter(
      <IncidentCard event={event} variant="candidate" onVerifyEvent={vi.fn()} onRejectAndFlagDevice={vi.fn()} onSplitOut={vi.fn()} onDismissCluster={vi.fn()} />
    )
    return userEvent.click(screen.getByRole('button', { name: /expand/i })).then(() => {
      const splitButtons = screen.getAllByRole('button', { name: /split out/i })
      splitButtons.forEach((btn) => expect(btn).toHaveAccessibleName())
    })
  })

  it('the pending-triage marker (⚠) is never icon-only — a visible text label accompanies it', () => {
    renderWithRouter(
      <StandaloneRow
        item={{ id: 'req_1', need_description: 'x', urgency_score: null, device_fingerprint_id: 'dev_x' }}
        variant="triage"
        onVerifyDispatch={vi.fn()}
        onReject={vi.fn()}
        onSetUrgency={vi.fn()}
      />
    )
    // SeverityBadge's pending state carries a text/aria-label, not a bare icon.
    expect(screen.getByLabelText(/pending|unavailable/i)).toBeInTheDocument()
  })

  it('interactive list-view controls are native <button>/<a> elements, keyboard-operable by construction (Tab + Enter/Space)', () => {
    renderWithRouter(
      <StandaloneRow
        item={{ id: 'req_1', need_description: 'x', urgency_score: 4, device_fingerprint_id: 'dev_x' }}
        variant="inbox"
        onVerifyDispatch={vi.fn()}
        onReject={vi.fn()}
      />
    )
    screen.getAllByRole('button').forEach((el) => expect(el.tagName).toBe('BUTTON'))
    screen.getAllByRole('link').forEach((el) => expect(el.tagName).toBe('A'))
  })

  it('color is never the sole signal — every severity badge pairs its color with a numeral or text label', () => {
    render(<SeverityBadge score={3} />)
    const badge = screen.getByTestId('severity-badge')
    expect(badge.textContent.trim().length).toBeGreaterThan(0)
    expect(badge).toHaveAccessibleName()
  })
})
