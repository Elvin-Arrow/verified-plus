import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/server.js'
import * as api from './client.js'
import { ApiError } from './client.js'

// FE-02: contract-mocked tests -- every client function exercised against
// the mock server built from docs/api-spec.md's documented shapes.

describe('submitRequest (§2)', () => {
  it('returns 201 with the created request on success', async () => {
    const result = await api.submitRequest({
      need_description: 'need water',
      location: { lat: 1, lng: 2 },
      device_fingerprint_id: 'dev_x1y2',
    })
    expect(result.id).toBeTruthy()
    expect(result.status).toBe('in_candidate_event')
    expect(result.matches).toBeInstanceOf(Array)
  })

  it('a flagged device still gets 201, status quarantined, pipeline fields null (§2 asymmetry)', async () => {
    const result = await api.submitRequest({
      need_description: 'need water',
      location: { lat: 1, lng: 2 },
      device_fingerprint_id: 'dev_flagged',
    })
    expect(result.status).toBe('quarantined')
    expect(result.event_id).toBeNull()
    expect(result.urgency_score).toBeNull()
  })

  it('throws ApiError(400, VALIDATION_ERROR) on a missing field', async () => {
    await expect(
      api.submitRequest({ need_description: '', location: null, device_fingerprint_id: '' })
    ).rejects.toMatchObject({ status: 400, code: 'VALIDATION_ERROR' })
  })
})

describe('queue reads (§3)', () => {
  it('getIntakeInbox returns needs_manual_triage and sorted arrays', async () => {
    const result = await api.getIntakeInbox()
    expect(result.needs_manual_triage).toBeInstanceOf(Array)
    expect(result.sorted).toBeInstanceOf(Array)
    expect(result.sorted[0].type).toBe('event')
  })

  it('getDispatchQueue events include pending_members', async () => {
    const result = await api.getDispatchQueue()
    expect(result.sorted[0].item.pending_members).toBeInstanceOf(Array)
  })

  it('getQuarantine groups by device', async () => {
    const result = await api.getQuarantine()
    expect(result.groups[0].device_fingerprint_id).toBe('dev_x1y2')
  })

  it('getArchive returns events and standalone_requests', async () => {
    const result = await api.getArchive()
    expect(result.events).toBeInstanceOf(Array)
    expect(result.standalone_requests).toBeInstanceOf(Array)
  })
})

describe('event actions (§4)', () => {
  it('verifyEvent returns the updated event', async () => {
    const result = await api.verifyEvent('evt_d4e5f6', 'coordinator_1')
    expect(result.status).toBe('verified')
  })

  it('verifyEvent throws NOT_FOUND for a missing event', async () => {
    await expect(api.verifyEvent('evt_missing', 'coordinator_1')).rejects.toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
    })
  })

  it('verifyEvent throws 409 INVALID_STATE_TRANSITION with details.current_status', async () => {
    await expect(api.verifyEvent('evt_already_verified', 'coordinator_1')).rejects.toMatchObject({
      status: 409,
      code: 'INVALID_STATE_TRANSITION',
      details: { current_status: 'verified' },
    })
  })

  it('rejectAndFlagDevice returns event:null + event_dissolved:true on dissolution', async () => {
    const result = await api.rejectAndFlagDevice('evt_d4e5f6', 'dev_dissolve', 'coordinator_1')
    expect(result.event).toBeNull()
    expect(result.event_dissolved).toBe(true)
  })

  it('rejectAndFlagDevice returns a live event when not dissolved', async () => {
    const result = await api.rejectAndFlagDevice('evt_d4e5f6', 'dev_x1y2', 'coordinator_1')
    expect(result.event).not.toBeNull()
    expect(result.event_dissolved).toBe(false)
  })

  it('dismissEvent throws 409 on a non-candidate event', async () => {
    await expect(api.dismissEvent('evt_verified', 'coordinator_1')).rejects.toMatchObject({ status: 409 })
  })
})

describe('standalone actions (§5)', () => {
  it('verifyStandalone dispatches atomically', async () => {
    const result = await api.verifyStandalone('req_x', 'coordinator_1')
    expect(result.status).toBe('dispatched')
    expect(result.verified).toBe(true)
  })

  it('splitOut returns request + event_dissolved + event', async () => {
    const result = await api.splitOut('req_x', 'coordinator_1')
    expect(result.request.status).toBe('standalone')
    expect('event_dissolved' in result).toBe(true)
  })

  it('mergeRequest with both targets set throws 400', async () => {
    await expect(
      api.mergeRequest('req_x', { actor: 'coordinator_1', targetEventId: 'evt_1', targetRequestId: 'req_2' })
    ).rejects.toMatchObject({ status: 400, code: 'VALIDATION_ERROR' })
  })

  it('mergeRequest with neither target set throws 400', async () => {
    await expect(api.mergeRequest('req_x', { actor: 'coordinator_1' })).rejects.toMatchObject({ status: 400 })
  })

  it('mergeRequest with exactly one target succeeds', async () => {
    const result = await api.mergeRequest('req_x', { actor: 'coordinator_1', targetEventId: 'evt_1' })
    expect(result.id).toBe('evt_merged')
  })

  it('rejectAllQuarantined throws 404 for a device with nothing quarantined', async () => {
    await expect(api.rejectAllQuarantined('dev_empty', 'coordinator_1')).rejects.toMatchObject({ status: 404 })
  })

  it('overrideUrgency sends corrected_score/reason and returns updated request', async () => {
    const result = await api.overrideUrgency('req_x', { actor: 'coordinator_1', correctedScore: 5, reason: 'Implies trapped' })
    expect(result.urgency_score).toBe(5)
  })

  it('overrideUrgency throws 400 for an out-of-range score', async () => {
    await expect(
      api.overrideUrgency('req_x', { actor: 'coordinator_1', correctedScore: 9 })
    ).rejects.toMatchObject({ status: 400, code: 'VALIDATION_ERROR' })
  })
})

describe('demo support (§6)', () => {
  it('seedReplay requires an explicit mode -> 400 when omitted', async () => {
    await expect(api.seedReplay({})).rejects.toMatchObject({ status: 400 })
  })

  it('seedReplay reset wipes and reports counts', async () => {
    const result = await api.seedReplay({ mode: 'reset' })
    expect(result.wiped).toBe(true)
    expect(result.requests_submitted).toBeGreaterThan(0)
  })
})

describe('detail views (§7)', () => {
  it('getRequestDetail includes match_reasons and action_history', async () => {
    const result = await api.getRequestDetail('req_a1b2c3')
    expect(result.match_reasons).toBeInstanceOf(Array)
    expect(result.action_history).toBeInstanceOf(Array)
  })

  it('getRequestDetail throws 404 for a missing request', async () => {
    await expect(api.getRequestDetail('req_missing')).rejects.toMatchObject({ status: 404, code: 'NOT_FOUND' })
  })

  it('getEventDetail includes members, pending_members, action_history', async () => {
    const result = await api.getEventDetail('evt_d4e5f6')
    expect(result.members).toBeInstanceOf(Array)
    expect(result.pending_members).toBeInstanceOf(Array)
    expect(result.action_history).toBeInstanceOf(Array)
  })
})

describe('error envelope / network handling', () => {
  it('a 500 with no error envelope still surfaces as an ApiError', async () => {
    server.use(
      http.get('/api/archive', () => new HttpResponse(null, { status: 500 }))
    )
    await expect(api.getArchive()).rejects.toBeInstanceOf(ApiError)
  })

  it('a network failure surfaces as an ApiError, not an unhandled rejection type', async () => {
    server.use(
      http.get('/api/archive', () => HttpResponse.error())
    )
    await expect(api.getArchive()).rejects.toBeInstanceOf(ApiError)
  })
})
