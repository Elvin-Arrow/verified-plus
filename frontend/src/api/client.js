// FE-01/FE-02: API client matching docs/api-spec.md exactly.
//
// Base path is configurable so the same client can point at the local mock
// server (FE-02, contract-mocked tests) or the real backend (FE-16), per
// docs/api-spec.md §1 ("Base path: /api").
const DEFAULT_BASE_URL = '/api'

export function getBaseUrl() {
  // Vite exposes env vars via import.meta.env; fall back to the documented
  // default when unset (e.g. plain unit tests with no env configured).
  try {
    if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL) {
      return import.meta.env.VITE_API_BASE_URL
    }
  } catch {
    // import.meta not available in this environment; use the default.
  }
  return DEFAULT_BASE_URL
}

/** Thrown for any non-2xx response. Mirrors docs/api-spec.md §1.1's error envelope. */
export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details || null
  }
}

async function request(method, path, body) {
  const baseUrl = getBaseUrl()
  const init = { method, headers: {} }
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`${baseUrl}${path}`, init)
  } catch {
    // Network failure — docs/ui-spec.md §11's "500/network failure" bucket.
    throw new ApiError(0, 'NETWORK_ERROR', 'Network request failed')
  }

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const payload = isJson ? await response.json().catch(() => null) : null

  if (!response.ok) {
    const err = payload && payload.error ? payload.error : {}
    throw new ApiError(
      response.status,
      err.code || 'INTERNAL_ERROR',
      err.message || `Request failed with status ${response.status}`,
      err.details
    )
  }

  return payload
}

// --- Intake (docs/api-spec.md §2) ---

export function submitRequest(body) {
  return request('POST', '/requests', body)
}

// --- Queues (§3) ---

export function getIntakeInbox() {
  return request('GET', '/intake-inbox')
}

export function getDispatchQueue() {
  return request('GET', '/dispatch-queue')
}

export function getQuarantine() {
  return request('GET', '/quarantine')
}

export function getArchive() {
  return request('GET', '/archive')
}

// --- Event actions (§4) ---

export function verifyEvent(eventId, actor) {
  return request('POST', `/events/${eventId}/verify`, { actor })
}

export function approvePending(eventId, actor) {
  return request('POST', `/events/${eventId}/approve-pending`, { actor })
}

export function dispatchEvent(eventId, actor) {
  return request('POST', `/events/${eventId}/dispatch`, { actor })
}

export function rejectAndFlagDevice(eventId, deviceId, actor) {
  return request('POST', `/events/${eventId}/devices/${deviceId}/reject-and-flag`, { actor })
}

export function dismissEvent(eventId, actor) {
  return request('POST', `/events/${eventId}/dismiss`, { actor })
}

// --- Standalone request actions (§5) ---

export function verifyStandalone(requestId, actor) {
  return request('POST', `/requests/${requestId}/verify-standalone`, { actor })
}

export function rejectStandalone(requestId, actor) {
  return request('POST', `/requests/${requestId}/reject-standalone`, { actor })
}

export function dispatchStandalone(requestId, actor) {
  return request('POST', `/requests/${requestId}/dispatch-standalone`, { actor })
}

export function splitOut(requestId, actor) {
  return request('POST', `/requests/${requestId}/split-out`, { actor })
}

export function mergeRequest(requestId, { actor, targetEventId = null, targetRequestId = null }) {
  return request('POST', `/requests/${requestId}/merge`, {
    actor,
    target_event_id: targetEventId,
    target_request_id: targetRequestId,
  })
}

export function rescueRequest(requestId, actor) {
  return request('POST', `/requests/${requestId}/rescue`, { actor })
}

export function rejectAllQuarantined(deviceId, actor) {
  return request('POST', `/quarantine/${deviceId}/reject-all`, { actor })
}

export function overrideUrgency(requestId, { actor, correctedScore, reason = null }) {
  return request('POST', `/requests/${requestId}/override-urgency`, {
    actor,
    corrected_score: correctedScore,
    reason,
  })
}

// --- Demo support (§6) ---

export function seedReplay({ mode, geofenceRadiusKm = null, maxClusterSpanKm = null }) {
  return request('POST', '/seed/replay', {
    mode,
    geofence_radius_km: geofenceRadiusKm,
    max_cluster_span_km: maxClusterSpanKm,
  })
}

// --- Detail views (§7) ---

export function getRequestDetail(requestId) {
  return request('GET', `/requests/${requestId}`)
}

export function getEventDetail(eventId) {
  return request('GET', `/events/${eventId}`)
}
