// FE-02: a hand-rolled mock server implementing docs/api-spec.md's
// documented contract exactly (not a live backend) -- used by MSW to
// intercept fetch() in tests, per docs/development-plan.md FE-02's scope
// ("build against the documented contract via a mock").
//
// This is a deliberately small in-memory model, just enough to exercise
// every endpoint's documented shape/status codes -- it is NOT a
// reimplementation of the backend's clustering/state-machine logic.
import { http, HttpResponse } from 'msw'

const BASE = '/api'

function errorBody(code, message, details = null) {
  return { error: { code, message, details } }
}

function makeRequestSummary(overrides = {}) {
  return {
    id: 'req_a1b2c3',
    need_description: 'Flooding hit our well, no clean water for 2 days',
    location: { lat: 12.34, lng: 56.78 },
    device_fingerprint_id: 'dev_x1y2',
    submitted_at: '2026-08-15T14:03:00Z',
    urgency_score: 4,
    urgency_reasoning: 'No access to clean water, tier 3 baseline, escalated for duration (2 days).',
    status: 'in_candidate_event',
    verified: false,
    event_id: 'evt_d4e5f6',
    device_flagged: false,
    ...overrides,
  }
}

export const handlers = [
  // --- Intake ---
  http.post(`${BASE}/requests`, async ({ request }) => {
    const body = await request.json()
    if (!body.need_description || !body.location || !body.device_fingerprint_id) {
      return HttpResponse.json(errorBody('VALIDATION_ERROR', 'missing required field', { field: 'need_description' }), { status: 400 })
    }
    if (body.device_fingerprint_id === 'dev_flagged') {
      return HttpResponse.json(
        makeRequestSummary({
          status: 'quarantined',
          event_id: null,
          urgency_score: null,
          urgency_reasoning: null,
          device_fingerprint_id: body.device_fingerprint_id,
          matches: null,
        }),
        { status: 201 }
      )
    }
    return HttpResponse.json(
      {
        ...makeRequestSummary({ device_fingerprint_id: body.device_fingerprint_id, need_description: body.need_description }),
        photo_url: body.photo_url ?? null,
        matches: [{ candidate_id: 'req_990z', is_match: true, reason: 'Same flooded street, submitted 40 min ago, 90m away.' }],
      },
      { status: 201 }
    )
  }),

  // --- Queues ---
  http.get(`${BASE}/intake-inbox`, () => {
    return HttpResponse.json({
      needs_manual_triage: [
        { type: 'request', item: makeRequestSummary({ id: 'req_triage1', urgency_score: null, urgency_reasoning: null, status: 'standalone', event_id: null }) },
      ],
      sorted: [
        {
          type: 'event',
          item: {
            id: 'evt_d4e5f6',
            status: 'candidate',
            member_count: 3,
            distinct_device_count: 3,
            max_urgency_score: 5,
            representative_location: { lat: 12.34, lng: 56.78 },
            members: [makeRequestSummary()],
          },
        },
        { type: 'request', item: makeRequestSummary({ id: 'req_standalone1', status: 'standalone', event_id: null, urgency_score: 4 }) },
      ],
    })
  }),

  http.get(`${BASE}/dispatch-queue`, () => {
    return HttpResponse.json({
      sorted: [
        {
          type: 'event',
          item: {
            id: 'evt_d4e5f6',
            status: 'verified',
            member_count: 3,
            distinct_device_count: 3,
            max_urgency_score: 4,
            members: [makeRequestSummary({ status: 'in_verified_event', verified: true })],
            pending_members: [makeRequestSummary({ id: 'req_pending1', status: 'pending_addition' })],
          },
        },
      ],
    })
  }),

  http.get(`${BASE}/quarantine`, () => {
    return HttpResponse.json({
      groups: [
        {
          device_fingerprint_id: 'dev_x1y2',
          device_flag: true,
          requests: [makeRequestSummary({ status: 'quarantined', device_flagged: true })],
        },
      ],
    })
  }),

  http.get(`${BASE}/archive`, () => {
    return HttpResponse.json({
      events: [{ id: 'evt_arch1', status: 'dispatched', members: [makeRequestSummary({ status: 'dispatched' })] }],
      standalone_requests: [makeRequestSummary({ id: 'req_arch1', status: 'rejected', event_id: null })],
    })
  }),

  // --- Event actions ---
  http.post(`${BASE}/events/:id/verify`, ({ params }) => {
    if (params.id === 'evt_missing') return HttpResponse.json(errorBody('NOT_FOUND', 'no such event'), { status: 404 })
    if (params.id === 'evt_already_verified')
      return HttpResponse.json(errorBody('INVALID_STATE_TRANSITION', 'already verified', { current_status: 'verified' }), { status: 409 })
    return HttpResponse.json({ id: params.id, status: 'verified', member_count: 3, distinct_device_count: 3, max_urgency_score: 4, members: [] })
  }),

  http.post(`${BASE}/events/:id/approve-pending`, ({ params }) => {
    return HttpResponse.json({ id: params.id, status: 'verified', pending_members: [], members: [] })
  }),

  http.post(`${BASE}/events/:id/dispatch`, ({ params }) => {
    return HttpResponse.json({ id: params.id, status: 'dispatched' })
  }),

  http.post(`${BASE}/events/:id/devices/:deviceId/reject-and-flag`, ({ params }) => {
    if (params.deviceId === 'dev_dissolve') {
      return HttpResponse.json({ event: null, rejected_request_ids: ['req_1'], quarantined_request_ids: [], event_dissolved: true })
    }
    return HttpResponse.json({
      event: { id: params.id, status: 'candidate' },
      rejected_request_ids: ['req_1', 'req_2'],
      quarantined_request_ids: ['req_3'],
      event_dissolved: false,
    })
  }),

  http.post(`${BASE}/events/:id/dismiss`, ({ params }) => {
    if (params.id === 'evt_verified')
      return HttpResponse.json(errorBody('INVALID_STATE_TRANSITION', 'not candidate', { current_status: 'verified' }), { status: 409 })
    return HttpResponse.json({ reverted_request_ids: ['req_1', 'req_2', 'req_3'] })
  }),

  // --- Standalone actions ---
  http.post(`${BASE}/requests/:id/verify-standalone`, ({ params }) => {
    return HttpResponse.json(makeRequestSummary({ id: params.id, status: 'dispatched', verified: true, event_id: null }))
  }),

  http.post(`${BASE}/requests/:id/reject-standalone`, ({ params }) => {
    return HttpResponse.json(makeRequestSummary({ id: params.id, status: 'rejected', event_id: null }))
  }),

  http.post(`${BASE}/requests/:id/dispatch-standalone`, ({ params }) => {
    return HttpResponse.json(makeRequestSummary({ id: params.id, status: 'dispatched', event_id: null }))
  }),

  http.post(`${BASE}/requests/:id/split-out`, ({ params }) => {
    return HttpResponse.json({
      request: makeRequestSummary({ id: params.id, status: 'standalone', event_id: null }),
      event_dissolved: false,
      event: { id: 'evt_d4e5f6', status: 'candidate' },
    })
  }),

  http.post(`${BASE}/requests/:id/merge`, async ({ request }) => {
    const body = await request.json()
    const hasEvent = body.target_event_id != null
    const hasRequest = body.target_request_id != null
    if (hasEvent === hasRequest) {
      return HttpResponse.json(errorBody('VALIDATION_ERROR', 'exactly one target must be set'), { status: 400 })
    }
    return HttpResponse.json({ id: 'evt_merged', status: 'candidate', member_count: 2 })
  }),

  http.post(`${BASE}/requests/:id/rescue`, ({ params }) => {
    return HttpResponse.json(makeRequestSummary({ id: params.id, status: 'standalone', event_id: null }))
  }),

  http.post(`${BASE}/quarantine/:deviceId/reject-all`, ({ params }) => {
    if (params.deviceId === 'dev_empty') {
      return HttpResponse.json(errorBody('NOT_FOUND', 'no currently-quarantined requests'), { status: 404 })
    }
    return HttpResponse.json({ device_fingerprint_id: params.deviceId, rejected_request_ids: ['req_1', 'req_2'] })
  }),

  http.post(`${BASE}/requests/:id/override-urgency`, async ({ request, params }) => {
    const body = await request.json()
    if (body.corrected_score < 1 || body.corrected_score > 5) {
      return HttpResponse.json(errorBody('VALIDATION_ERROR', 'corrected_score out of range'), { status: 400 })
    }
    return HttpResponse.json(
      makeRequestSummary({ id: params.id, urgency_score: body.corrected_score })
    )
  }),

  // --- Demo support ---
  http.post(`${BASE}/seed/replay`, async ({ request }) => {
    const body = await request.json()
    if (body.mode !== 'reset' && body.mode !== 'append') {
      return HttpResponse.json(errorBody('VALIDATION_ERROR', 'mode is required'), { status: 400 })
    }
    return HttpResponse.json({ mode: body.mode, requests_submitted: 50, wiped: body.mode === 'reset' })
  }),

  // --- Detail views ---
  http.get(`${BASE}/requests/:id`, ({ params }) => {
    if (params.id === 'req_missing') return HttpResponse.json(errorBody('NOT_FOUND', 'no such request'), { status: 404 })
    return HttpResponse.json({
      ...makeRequestSummary({ id: params.id }),
      photo_url: null,
      original_urgency_score: null,
      match_reasons: [{ candidate_id: 'req_990z', is_match: true, reason: 'Same flooded street, submitted 40 min ago, 90m away.' }],
      suggested_merges: [],
      action_history: [],
    })
  }),

  http.get(`${BASE}/events/:id`, ({ params }) => {
    if (params.id === 'evt_missing') return HttpResponse.json(errorBody('NOT_FOUND', 'no such event'), { status: 404 })
    return HttpResponse.json({
      id: params.id,
      status: 'verified',
      representative_location: { lat: 12.34, lng: 56.78 },
      verified_by: 'coordinator_1',
      verified_at: '2026-08-15T14:05:00Z',
      created_at: '2026-08-15T14:03:00Z',
      members: [makeRequestSummary()],
      pending_members: [],
      action_history: [{ id: 'act_2', actor: 'coordinator_1', action_type: 'verify_event', target_id: params.id, timestamp: '2026-08-15T14:05:00Z', note: null }],
    })
  }),
]
