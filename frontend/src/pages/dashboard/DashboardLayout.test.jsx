import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import DashboardLayout from './DashboardLayout.jsx'

function Stub(label) {
  return () => <div>{label} content</div>
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard" element={<DashboardLayout />}>
          <Route path="intake-inbox" element={Stub('Intake Inbox')()} />
          <Route path="dispatch-queue" element={Stub('Dispatch Queue')()} />
          <Route path="quarantine" element={Stub('Quarantine')()} />
          <Route path="archive" element={Stub('Archive')()} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

// FE-04: docs/ui-spec.md §4 — tab bar, no raw count badges on the two live tabs.
describe('DashboardLayout chrome', () => {
  it('renders all four tab labels', () => {
    renderAt('/dashboard/intake-inbox')
    expect(screen.getByRole('link', { name: /intake & verification/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /dispatch queue/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /quarantine/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /archive/i })).toBeInTheDocument()
  })

  it('marks the active tab distinctly', () => {
    renderAt('/dashboard/dispatch-queue')
    expect(screen.getByRole('link', { name: /dispatch queue/i })).toHaveAttribute('aria-current', 'page')
  })

  it('renders the active tab content via the Outlet', () => {
    renderAt('/dashboard/archive')
    expect(screen.getByText(/archive content/i)).toBeInTheDocument()
  })

  it('never shows a raw numeric count badge next to the Intake or Dispatch tab labels', () => {
    renderAt('/dashboard/intake-inbox')
    const intakeTab = screen.getByRole('link', { name: /intake & verification/i })
    expect(intakeTab.textContent).not.toMatch(/\(\d+\)/)
    const dispatchTab = screen.getByRole('link', { name: /dispatch queue/i })
    expect(dispatchTab.textContent).not.toMatch(/\(\d+\)/)
  })

  it('renders the Seed/Replay control affordance in the chrome', () => {
    renderAt('/dashboard/intake-inbox')
    expect(screen.getByRole('button', { name: /seed\/replay/i })).toBeInTheDocument()
  })
})
