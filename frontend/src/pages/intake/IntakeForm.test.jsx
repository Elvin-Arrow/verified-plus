import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import IntakeForm from './IntakeForm.jsx'
import * as api from '../../api/client.js'
import { ApiError } from '../../api/client.js'

vi.mock('../../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, submitRequest: vi.fn() }
})

function grantGeolocation(lat = 12.34, lng = 56.78) {
  vi.stubGlobal('navigator', {
    ...navigator,
    geolocation: {
      getCurrentPosition: (success) => success({ coords: { latitude: lat, longitude: lng } }),
    },
  })
}

function denyGeolocation() {
  vi.stubGlobal('navigator', {
    ...navigator,
    geolocation: {
      getCurrentPosition: (_success, error) => error(new Error('denied')),
    },
  })
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetAllMocks()
})

// FE-03: docs/ui-spec.md §3 — /intake public form, all four states.
describe('IntakeForm', () => {
  it('Submit is disabled until both location and a non-empty description are present', async () => {
    grantGeolocation()
    render(<IntakeForm />)
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText(/what do you need/i), 'need water')
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled() // no location yet

    await userEvent.click(screen.getByRole('button', { name: /use my location/i }))
    expect(await screen.findByRole('button', { name: /submit/i })).toBeEnabled()
  })

  it('falls back to tap-to-place map on denied/unavailable geolocation, never a free-text field', async () => {
    denyGeolocation()
    render(<IntakeForm />)
    await userEvent.click(screen.getByRole('button', { name: /use my location/i }))
    expect(await screen.findByTestId('tap-to-place-map')).toBeInTheDocument()
    expect(screen.queryByLabelText(/location.*text/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByTestId('tap-to-place-map'))
    await userEvent.type(screen.getByLabelText(/what do you need/i), 'need water')
    expect(screen.getByRole('button', { name: /submit/i })).toBeEnabled()
  })

  it('submitting disables the button and shows a spinner, then a plain success confirmation with no status/urgency/match detail', async () => {
    grantGeolocation()
    let resolveSubmit
    api.submitRequest.mockReturnValue(new Promise((r) => { resolveSubmit = r }))
    render(<IntakeForm />)
    await userEvent.click(screen.getByRole('button', { name: /use my location/i }))
    await userEvent.type(screen.getByLabelText(/what do you need/i), 'need water urgently')
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))

    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
    expect(screen.getByTestId('submit-spinner')).toBeInTheDocument()

    resolveSubmit({ id: 'req_1', status: 'in_candidate_event', urgency_score: 5, matches: [] })
    expect(await screen.findByText(/your request has been received/i)).toBeInTheDocument()
    expect(screen.queryByText(/urgency/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/5/)).not.toBeInTheDocument()
    expect(screen.queryByText(/similar/i)).not.toBeInTheDocument()
  })

  it('a quarantined outcome (flagged device) renders the identical plain success confirmation', async () => {
    grantGeolocation()
    api.submitRequest.mockResolvedValue({ id: 'req_2', status: 'quarantined', urgency_score: null, matches: null })
    render(<IntakeForm />)
    await userEvent.click(screen.getByRole('button', { name: /use my location/i }))
    await userEvent.type(screen.getByLabelText(/what do you need/i), 'need water')
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))
    expect(await screen.findByText(/your request has been received/i)).toBeInTheDocument()
    expect(screen.queryByText(/quarantine/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/flag/i)).not.toBeInTheDocument()
  })

  it('a 400 VALIDATION_ERROR shows an inline message under the specific field and keeps the form filled in', async () => {
    grantGeolocation()
    api.submitRequest.mockRejectedValue(new ApiError(400, 'VALIDATION_ERROR', 'need_description must not be empty', { field: 'need_description' }))
    render(<IntakeForm />)
    await userEvent.click(screen.getByRole('button', { name: /use my location/i }))
    await userEvent.type(screen.getByLabelText(/what do you need/i), 'need water')
    await userEvent.click(screen.getByRole('button', { name: /submit/i }))

    expect(await screen.findByText(/need_description must not be empty/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/what do you need/i)).toHaveValue('need water')
  })
})
