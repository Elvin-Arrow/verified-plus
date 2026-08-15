import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App.jsx'

// FE-01: smoke test confirming the routing shell mounts both entry points
// (docs/ui-spec.md §2) without crashing.
describe('App routing shell', () => {
  it('renders the intake form at /intake', () => {
    render(
      <MemoryRouter initialEntries={['/intake']}>
        <App />
      </MemoryRouter>
    )
    expect(screen.getByLabelText(/what do you need/i)).toBeInTheDocument()
  })

  it('redirects / to /intake', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    )
    expect(screen.getByLabelText(/what do you need/i)).toBeInTheDocument()
  })

  it('renders the dashboard shell and defaults to the intake inbox tab', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <App />
      </MemoryRouter>
    )
    expect(screen.getByRole('link', { name: /intake & verification/i })).toHaveClass('dashboard-tab')
  })
})
