import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SeverityBadge from './SeverityBadge.jsx'

// FE-05: docs/ui-spec.md §9 — severity color encoding, never color alone.
describe('SeverityBadge', () => {
  it.each([
    [5, 'severity-red', '5'],
    [4, 'severity-orange', '4'],
    [3, 'severity-yellow', '3'],
    [2, 'severity-blue', '2'],
    [1, 'severity-gray', '1'],
  ])('renders score %i with class %s and the numeral visible', (score, expectedClass) => {
    render(<SeverityBadge score={score} />)
    const badge = screen.getByTestId('severity-badge')
    expect(badge).toHaveClass(expectedClass)
    expect(badge).toHaveTextContent(String(score))
  })

  it('renders a null score as pending/unavailable, distinct amber styling, never confused with a real score', () => {
    render(<SeverityBadge score={null} />)
    const badge = screen.getByTestId('severity-badge')
    expect(badge).toHaveClass('severity-pending')
    expect(badge).not.toHaveClass('severity-gray')
    expect(badge.textContent).not.toMatch(/^[1-5]$/)
  })

  it('always exposes a text label, never icon/color only (accessibility)', () => {
    render(<SeverityBadge score={5} />)
    expect(screen.getByLabelText(/urgency 5/i)).toBeInTheDocument()
  })

  it('exposes an accessible label for the pending state too', () => {
    render(<SeverityBadge score={null} />)
    expect(screen.getByLabelText(/pending|unavailable/i)).toBeInTheDocument()
  })
})
