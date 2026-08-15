import { render as rtlRender, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import StandaloneRow from './StandaloneRow.jsx'

function render(ui) {
  return rtlRender(<MemoryRouter>{ui}</MemoryRouter>)
}

const baseItem = {
  id: 'req_1',
  need_description: 'Insulin runs out tonight',
  urgency_score: 4,
  device_fingerprint_id: 'dev_x1y2',
}

// FE-06: docs/ui-spec.md §5.0 (Needs Manual Triage), §5.2 (standalone row), §6 (dispatch-only row).
describe('StandaloneRow', () => {
  it('§5.2 inbox variant: shows severity, need text, Verify & Dispatch / Reject / details', () => {
    render(<StandaloneRow item={baseItem} variant="inbox" onVerifyDispatch={vi.fn()} onReject={vi.fn()} />)
    expect(screen.getByText(/insulin runs out tonight/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /verify & dispatch/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^reject$/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /details/i })).toBeInTheDocument()
  })

  it('§5.0 triage variant: null urgency, Verify & Dispatch / Reject / Set Urgency, no dead end', () => {
    render(
      <StandaloneRow
        item={{ ...baseItem, urgency_score: null }}
        variant="triage"
        onVerifyDispatch={vi.fn()}
        onReject={vi.fn()}
        onSetUrgency={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /verify & dispatch/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^reject$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /set urgency/i })).toBeInTheDocument()
    // Needs Manual Triage items are never gated on urgency existing.
    expect(screen.getByRole('button', { name: /verify & dispatch/i })).not.toBeDisabled()
  })

  it('§6 dispatch variant: shows "Dispatch", never "Verify & Dispatch" (already verified)', () => {
    render(<StandaloneRow item={{ ...baseItem, verified: true }} variant="dispatch" onDispatch={vi.fn()} />)
    expect(screen.getByRole('button', { name: /^dispatch$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /verify & dispatch/i })).not.toBeInTheDocument()
  })

  it('calls onVerifyDispatch with the item id when clicked', async () => {
    const onVerifyDispatch = vi.fn()
    render(<StandaloneRow item={baseItem} variant="inbox" onVerifyDispatch={onVerifyDispatch} onReject={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /verify & dispatch/i }))
    expect(onVerifyDispatch).toHaveBeenCalledWith('req_1')
  })

  it('shows a Merge affordance when a suggested merge exists, absent otherwise', () => {
    render(<StandaloneRow item={baseItem} variant="inbox" onVerifyDispatch={vi.fn()} onReject={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /merge/i })).not.toBeInTheDocument()
  })

  it('shows a Merge button when hasSuggestedMerge is true', () => {
    render(
      <StandaloneRow
        item={baseItem}
        variant="inbox"
        onVerifyDispatch={vi.fn()}
        onReject={vi.fn()}
        hasSuggestedMerge
        onMerge={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /merge/i })).toBeInTheDocument()
  })

  it('disables the clicked action while in flight, without hiding it (§11)', async () => {
    let resolve
    const onReject = vi.fn(() => new Promise((r) => { resolve = r }))
    render(<StandaloneRow item={baseItem} variant="inbox" onVerifyDispatch={vi.fn()} onReject={onReject} />)
    const rejectBtn = screen.getByRole('button', { name: /^reject$/i })
    await userEvent.click(rejectBtn)
    expect(rejectBtn).toBeDisabled()
    resolve()
  })
})
