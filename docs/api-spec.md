# API Specification — Aid Request Triage & Trust Tool

Version 0.3 · Implements `docs/spec.md` v0.3 §7 and `docs/design.md` v0.5 §2/§4. This document is the authoritative contract for every HTTP endpoint — request/response shapes, status codes, and error behavior — that `docs/spec.md`'s illustrative API table and `docs/design.md`'s router pseudocode both point back to. `match_reasons` and `suggested_merges[].distance_km` (§7) were the two fields this spec anticipated correctly before `docs/design.md`/`docs/data-model.md` had matching storage for them — see `docs/data-model.md` §7 for that fix. `POST /api/quarantine/{device_id}/reject-all` and `GET /api/events/{id}` (§5/§7) were added in the subsequent 8-document pass that added `docs/ui-spec.md` — both were UI affordances/FR-602 requirements with no endpoint anywhere until then. `RequestSummary.has_suggested_merge` (§1.3) was added after implementation surfaced the reverse gap: `docs/ui-spec.md` required a list-view affordance this shape had no field for.

## 1. Conventions

- **Base path**: `/api`. All paths below are relative to it.
- **Format**: JSON in, JSON out. `Content-Type: application/json` on every request with a body.
- **Auth**: none. Per FR-104, intake requires no account; per spec.md §8 ("Out of scope"), the coordinator dashboard has no auth in this version — `actor` fields in request bodies are a free-text coordinator name/label, not an authenticated identity. Not a decision to defend past the hackathon demo.
- **IDs**: all entity IDs are opaque strings (e.g. `req_a1b2c3`, `evt_d4e5f6`, `dev_...`). Clients MUST NOT parse them.
- **Timestamps**: ISO-8601 UTC, e.g. `"2026-08-15T14:03:00Z"`.
- **Idempotency**: none of these endpoints are idempotent under retry (a double-submitted `POST /api/requests` creates two requests; a double-clicked action logs two `CoordinatorAction` entries and may error the second time — e.g. verifying an already-verified Event). The frontend's responsibility (design.md §6.2: disable-on-click) is the mitigation, not the API.
- **Concurrency**: every mutating endpoint acquires `InMemoryStore`'s single lock (design.md §3/§6.4) — requests are serialized server-side, so no client-side optimistic-concurrency headers (`If-Match` etc.) are needed or supported.

### 1.1 Standard error envelope

Every non-2xx response body has this shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "need_description must not be empty",
    "details": { "field": "need_description" }
  }
}
```

| `code` | HTTP status | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Request body failed schema/field validation (e.g. FR-101/102 missing fields). |
| `NOT_FOUND` | 404 | The referenced `request_id`/`event_id`/`device_id` doesn't exist in the store. |
| `INVALID_STATE_TRANSITION` | 409 | The action doesn't apply to the target's current state (e.g. "Dismiss Cluster" on a `verified` Event — FR-507 restricts this to `candidate` only). Response `details` includes `current_status` and `expected_status`. |
| `INTERNAL_ERROR` | 500 | Unhandled server fault. Distinct from an LLM/embedding failure, which is NOT an error response — see §1.2. |

### 1.2 How LLM/embedding failures surface (NFR-103)

`POST /api/requests` **never** returns an error for an LLM or embedding call failure. Per NFR-103, the request is still created and returned with `201 Created`; `urgency_score` and `matches` are simply absent/`null`, and it's picked up by the Needs Manual Triage section of `GET /api/intake-inbox` (FR-401). This is a deliberate asymmetry: a slow/flaky third-party dependency must never look like a client error.

### 1.3 Shared types referenced below

```
Location        { "lat": number, "lng": number }
RequestStatus   "standalone" | "in_candidate_event" | "pending_addition" | "in_verified_event"
                | "dispatched" | "rejected" | "quarantined"
EventStatus     "candidate" | "verified" | "dispatched"
ActionType      "verify_event" | "approve_pending" | "approve_dispatch" | "reject_flag_device"
                | "dismiss_cluster" | "split_out" | "rescue_from_quarantine" | "verify_standalone"
                | "reject_standalone" | "dispatch_standalone" | "override_urgency" | "manual_merge"
```

`RequestSummary` (used in list responses, a trimmed `Request` — full shape in `docs/data-model.md`):

```json
{
  "id": "req_a1b2c3",
  "need_description": "Flooding hit our well, no clean water for 2 days",
  "location": { "lat": 12.34, "lng": 56.78 },
  "device_fingerprint_id": "dev_x1y2",
  "submitted_at": "2026-08-15T14:03:00Z",
  "urgency_score": 4,
  "urgency_reasoning": "No access to clean water, tier 3 baseline, escalated for duration (2 days).",
  "status": "in_candidate_event",
  "verified": false,
  "event_id": "evt_d4e5f6",
  "device_flagged": false,
  "has_suggested_merge": false
}
```

`has_suggested_merge` — added in a cross-document alignment pass after `docs/ui-spec.md` §5.1/§5.2 was found to require a per-row Merge affordance in list views (Intake Inbox, Dispatch Queue) that this shape had no field to drive. Deliberately a cheap boolean, not the full `distance_km`/target detail (that stays on `GET /api/requests/{id}`'s `suggested_merges` array, §7) — a list row only needs to know *whether* to show the affordance; clicking it fetches the detail to render the actual confirmation.

## 2. Intake

### `POST /api/requests`

Submit a new request. Implements FR-101–107, FR-201–208, FR-301–302.

**Request body:**

```json
{
  "need_description": "Flooding hit our well, no clean water for 2 days",
  "location": { "lat": 12.34, "lng": 56.78 },
  "photo_url": null,
  "device_fingerprint_id": "dev_x1y2"
}
```

- `need_description` — required, non-empty string (FR-102).
- `location` — required `Location` (FR-101). Missing/malformed → `400 VALIDATION_ERROR`.
- `photo_url` — optional; the API accepts a pre-uploaded asset URL, not a raw file (file upload is a separate, unspecified static-asset concern outside this API's scope — see `docs/design.md` §6.1 note).
- `device_fingerprint_id` — required (FR-105); client-generated, see `docs/design.md` §3 "Device fingerprint."

**Response `201 Created`:**

```json
{
  "id": "req_a1b2c3",
  "need_description": "Flooding hit our well, no clean water for 2 days",
  "location": { "lat": 12.34, "lng": 56.78 },
  "photo_url": null,
  "device_fingerprint_id": "dev_x1y2",
  "submitted_at": "2026-08-15T14:03:00Z",
  "urgency_score": 4,
  "urgency_reasoning": "No access to clean water, tier 3 baseline, escalated for duration (2 days).",
  "status": "in_candidate_event",
  "verified": false,
  "event_id": "evt_d4e5f6",
  "matches": [
    { "candidate_id": "req_990z", "is_match": true, "reason": "Same flooded street, submitted 40 min ago, 90m away." }
  ]
}
```

- If the submitting device is flagged (`device_flag = true`), the response still returns `201` but `status` is `"quarantined"` and `event_id`/`matches`/`urgency_score` are all `null` — the pipeline (FR-201–206) never runs for a quarantined submission (FR-107/308).
- If the LLM/embedding call fails, `urgency_score`, `urgency_reasoning`, and `matches` are `null`; `status` is `"standalone"` and no clustering occurred (§1.2, NFR-103).

**Errors**: `400 VALIDATION_ERROR` only.

## 3. Queues

### `GET /api/intake-inbox`

List the Intake & Verification Inbox (FR-401, FR-402).

**Response `200 OK`:**

```json
{
  "needs_manual_triage": [
    { "type": "request", "item": { "...RequestSummary, urgency_score: null...": true } }
  ],
  "sorted": [
    {
      "type": "event",
      "item": {
        "id": "evt_d4e5f6",
        "status": "candidate",
        "member_count": 3,
        "distinct_device_count": 3,
        "max_urgency_score": 4,
        "representative_location": { "lat": 12.34, "lng": 56.78 },
        "members": [ "...RequestSummary...": true ]
      }
    },
    { "type": "request", "item": { "...RequestSummary (standalone)...": true } }
  ]
}
```

- `needs_manual_triage` — items with any member's `urgency_score = null`; unsorted, rendered first (FR-401 §1).
- `sorted` — a mixed list of `event` and `request` (standalone) items, each carrying enough of the sort inputs (`max_urgency_score`, `distinct_device_count`) for the frontend to render without recomputing, ordered per the lexicographic rule (FR-401 §2). A `candidate` Event with `pending_member_request_ids` does NOT show those pending members here — they only ever surface on the Dispatch Queue's copy of the same Event once it's verified (see below).

**Errors**: none (always `200`, possibly with both arrays empty).

### `GET /api/dispatch-queue`

List the Dispatch Queue (FR-403). Same response shape as `/api/intake-inbox`'s `sorted` array, but:
- only `verified` Events and standalone requests with `verified = true`, excluding `dispatched`/`rejected`/`quarantined` (FR-403).
- Event items additionally include `"pending_members": [ ...RequestSummary... ]` for any `pending_addition` requests attached (FR-304b) — these don't count toward `member_count`/sort inputs, but the frontend needs them to render the "Approve All Pending" affordance (FR-502).

```json
{
  "sorted": [
    {
      "type": "event",
      "item": {
        "id": "evt_d4e5f6",
        "status": "verified",
        "member_count": 3,
        "distinct_device_count": 3,
        "max_urgency_score": 4,
        "members": [ "...": true ],
        "pending_members": [ "...RequestSummary (status: pending_addition)...": true ]
      }
    }
  ]
}
```

### `GET /api/quarantine`

List the Quarantine Inbox (FR-407), grouped by device.

```json
{
  "groups": [
    {
      "device_fingerprint_id": "dev_x1y2",
      "device_flag": true,
      "requests": [ "...RequestSummary (status: quarantined)...": true ]
    }
  ]
}
```

### `GET /api/archive`

List resolved/terminal items (FR-406): `dispatched` and `rejected` requests/Events, flat and read-only.

```json
{
  "events": [ { "id": "evt_...", "status": "dispatched", "members": [ "...": true ] } ],
  "standalone_requests": [ "...RequestSummary (status: dispatched|rejected)...": true ]
}
```

Each item includes `device_flagged: bool` per member (FR-309's scrutiny marker).

## 4. Event actions

### `POST /api/events/{event_id}/verify`

Verify a `candidate` Event and approve its current members (FR-304, FR-502 "Verify Event & Approve All").

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:** the updated Event (same shape as the Dispatch Queue's event item).

**Errors:**
- `404 NOT_FOUND` — no such Event.
- `409 INVALID_STATE_TRANSITION` — Event is not `candidate` (`details: { current_status: "verified" }`).

### `POST /api/events/{event_id}/approve-pending`

Admit all `pending_addition` members of an already-`verified` Event (FR-304b, FR-502 "Approve All Pending").

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:** the updated Event, `pending_members` now empty, those requests moved into `members`.

**Errors:** `404`; `409` if the Event isn't `verified` or has no pending members (`details: { pending_count: 0 }`).

### `POST /api/events/{event_id}/dispatch`

Mark a `verified` Event and its active members `dispatched` (terminal) — FR-502 "Approve."

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:** the Event with `status: "dispatched"`. It no longer appears in `GET /api/dispatch-queue`; subsequent reads come from `GET /api/archive`.

**Errors:** `404`; `409` if not `verified`.

### `POST /api/events/{event_id}/devices/{device_id}/reject-and-flag`

Reject one device group's requests within this card, flag the device, and sweep its other active requests into quarantine (FR-503, FR-306, FR-308).

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:**

```json
{
  "event": { "...updated Event, possibly dissolved (see event: null below)...": true },
  "rejected_request_ids": ["req_1", "req_2"],
  "quarantined_request_ids": ["req_3"],
  "event_dissolved": false
}
```

If this action drops the Event's active membership to 0–1, `event_dissolved: true` and `event` is `null` — the client should treat the Event as gone and re-fetch the affected request(s) directly (`GET /api/requests/{id}`) rather than expect an Event object back (FR-504b).

**Errors:** `404` (bad `event_id` or `device_id` — i.e. that device has no requests on this card).

### `POST /api/events/{event_id}/dismiss`

Dismiss a `candidate` Event as a false-positive grouping (FR-507). No device flag is touched.

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:** `{ "reverted_request_ids": ["req_1", "req_2", "req_3"] }` — the Event no longer exists; each ID reverts to `standalone`, `verified: false`.

**Errors:** `404`; `409` if the Event isn't `candidate` (FR-507 explicitly excludes `verified` Events — use Split Out per-member instead).

## 5. Standalone request actions

### `POST /api/requests/{request_id}/verify-standalone`

Verify AND dispatch a standalone request atomically (FR-505).

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:** the updated request, `status: "dispatched"`, `verified: true`.

**Errors:** `404`; `409` if the request isn't `standalone` (e.g. it's already part of an Event).

### `POST /api/requests/{request_id}/reject-standalone`

**Request body:** `{ "actor": "coordinator_1" }`
**Response `200 OK`:** the updated request, `status: "rejected"`.
**Errors:** `404`; `409` if not `standalone`.

### `POST /api/requests/{request_id}/dispatch-standalone`

Dispatch a standalone request that's `verified = true` but not yet `dispatched` — reachable only via the FR-504b dissolution path (FR-505b).

**Request body:** `{ "actor": "coordinator_1" }`
**Response `200 OK`:** the updated request, `status: "dispatched"`.
**Errors:** `404`; `409` if `verified` is not `true` or `status` is not `standalone` (`details` explains which precondition failed).

### `POST /api/requests/{request_id}/split-out`

Eject one member request from its Event; may dissolve the Event (FR-504, FR-504b).

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:**

```json
{
  "request": { "...updated request, status: standalone...": true },
  "event_dissolved": false,
  "event": { "...updated Event if still standing, else null...": true }
}
```

**Errors:** `404`; `409` if the request has no `event_id` (nothing to split out of).

### `POST /api/requests/{request_id}/merge`

Manually merge a geometrically-excluded request into its suggested Event, or bootstrap a new one if both sides were standalone (FR-205c).

**Request body:**

```json
{ "actor": "coordinator_1", "target_event_id": "evt_...", "target_request_id": null }
```

Exactly one of `target_event_id` / `target_request_id` must be set, matching one entry in that request's suggested-merge list (see `GET /api/requests/{id}` §7). Setting both or neither → `400 VALIDATION_ERROR`.

**Response `200 OK`:** the resulting Event (existing, now with the new member; or newly bootstrapped).

**Errors:** `404` if the request or target doesn't exist, or if the target isn't actually in that request's suggested-merge list (treated as not-found rather than a silent no-op, so the UI can't merge arbitrary unrelated items).

### `POST /api/requests/{request_id}/rescue`

Move a quarantined request back into the Intake & Verification Inbox (FR-407, FR-504b).

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:** the updated request, `status` reverted to whatever it would have been absent quarantine (typically `standalone`, re-queued for matching — see `docs/design.md` §4.4 for why a rescue re-runs FR-202–206 rather than restoring stale state).

**Errors:** `404`; `409` if `status` isn't `quarantined`.

### `POST /api/quarantine/{device_id}/reject-all`

Bulk-reject every currently-quarantined request from one device (FR-407). Distinct from `/api/events/{id}/devices/{device_id}/reject-and-flag` (§4) — this endpoint does **not** set `device_flag` (it's already `true`, that's why these requests are quarantined) and applies to standalone quarantined requests, not an Incident Card's members.

**Request body:** `{ "actor": "coordinator_1" }`

**Response `200 OK`:**

```json
{ "device_fingerprint_id": "dev_x1y2", "rejected_request_ids": ["req_1", "req_2", "req_3"] }
```

**Errors:** `404` if the device has no currently-quarantined requests (an empty reject is treated as not-found, same convention as `merge`'s target validation in §5).

### `POST /api/requests/{request_id}/override-urgency`

Coordinator sets a corrected `urgency_score` (FR-603, feeding FR-604's calibration buffer).

**Request body:**

```json
{ "actor": "coordinator_1", "corrected_score": 5, "reason": "Implies trapped, not just discomfort." }
```

- `corrected_score` — required integer 1–5.
- `reason` — optional but strongly recommended; it's what gets injected as a few-shot example (FR-604) — an override with no reason still updates the score but contributes a weaker calibration example.

**Response `200 OK`:** the updated request, `urgency_score` = `corrected_score`, `original_urgency_score` preserved.

**Errors:** `404`; `400 VALIDATION_ERROR` if `corrected_score` is outside 1–5.

## 6. Demo support

### `POST /api/seed/replay`

Bulk-inject a synthetic demo batch through the live intake path (FR-701–702, FR-208).

**Request body:**

```json
{
  "mode": "reset",
  "geofence_radius_km": 1.0,
  "max_cluster_span_km": 1.5
}
```

- `mode` — required, `"reset"` or `"append"`. No default (spec.md FR-702: "an explicit, documented choice... not an implicit default") — omitting it is a `400 VALIDATION_ERROR`, not a silent fallback.
- `geofence_radius_km` / `max_cluster_span_km` — optional, only meaningful with `mode: "reset"` (FR-208); ignored with a request-level warning (not an error) if supplied alongside `mode: "append"`.
- The actual batch of ~50 synthetic requests (FR-701) is server-side seed data, not part of this request body — this endpoint triggers replay of a fixture set, it doesn't accept arbitrary payloads to inject.

**Response `200 OK`:**

```json
{ "mode": "reset", "requests_submitted": 50, "wiped": true }
```

**Errors:** `400 VALIDATION_ERROR` if `mode` is missing/invalid.

## 7. Detail view

### `GET /api/requests/{request_id}`

Full detail: reasoning, action history, suggested merges (FR-506, FR-602).

**Response `200 OK`:**

```json
{
  "id": "req_a1b2c3",
  "need_description": "...",
  "location": { "lat": 12.34, "lng": 56.78 },
  "photo_url": null,
  "device_fingerprint_id": "dev_x1y2",
  "device_flagged": false,
  "submitted_at": "2026-08-15T14:03:00Z",
  "urgency_score": 5,
  "urgency_reasoning": "...",
  "original_urgency_score": 4,
  "status": "in_verified_event",
  "verified": true,
  "event_id": "evt_d4e5f6",
  "match_reasons": [
    { "candidate_id": "req_990z", "is_match": true, "reason": "Same flooded street, submitted 40 min ago, 90m away." }
  ],
  "suggested_merges": [
    { "target_event_id": "evt_far_away", "distance_km": 1.9 }
  ],
  "action_history": [
    {
      "id": "act_1", "actor": "coordinator_1", "action_type": "override_urgency",
      "target_id": "req_a1b2c3", "timestamp": "2026-08-15T14:10:00Z",
      "note": "Implies trapped, not just discomfort."
    }
  ]
}
```

**Errors:** `404 NOT_FOUND`.

### `GET /api/events/{event_id}`

Full Event detail: members, pending members, and the Event's own action history (FR-602). This is the second half of FR-602's "request/Event detail view" requirement — an Event-level action (`verify_event`, `approve_pending`, `reject_flag_device`, `dismiss_cluster`) is logged against the Event's `id`, not any single member's, so it's only visible here, not via any member's `GET /api/requests/{id}`. Also the data source for the Merge confirmation UI (`docs/ui-spec.md` §5.1/§10) when a `suggested_merges` entry's target is an Event rather than another standalone request.

**Response `200 OK`:**

```json
{
  "id": "evt_d4e5f6",
  "status": "verified",
  "representative_location": { "lat": 12.34, "lng": 56.78 },
  "verified_by": "coordinator_1",
  "verified_at": "2026-08-15T14:05:00Z",
  "created_at": "2026-08-15T14:03:00Z",
  "members": [ "...RequestSummary...": true ],
  "pending_members": [ "...RequestSummary (status: pending_addition)...": true ],
  "action_history": [
    {
      "id": "act_2", "actor": "coordinator_1", "action_type": "verify_event",
      "target_id": "evt_d4e5f6", "timestamp": "2026-08-15T14:05:00Z", "note": null
    }
  ]
}
```

**Errors:** `404 NOT_FOUND` — including for an Event that has since dissolved (its `id` is gone, not soft-deleted; see `docs/data-model.md` §3.2). A client holding a stale `event_id` across a poll interval should treat this the same as any other `404` — re-fetch the current queue view (`docs/ui-spec.md` §11's stale-view handling).

## 8. Endpoint index

| Method | Path | Spec refs |
|---|---|---|
| `POST` | `/api/requests` | FR-101–107, FR-201–208, FR-301–302 |
| `GET` | `/api/intake-inbox` | FR-401–402 |
| `GET` | `/api/dispatch-queue` | FR-403 |
| `GET` | `/api/quarantine` | FR-407 |
| `GET` | `/api/archive` | FR-406 |
| `POST` | `/api/events/{id}/verify` | FR-304, FR-502 |
| `POST` | `/api/events/{id}/approve-pending` | FR-304b, FR-502 |
| `POST` | `/api/events/{id}/dispatch` | FR-502 |
| `POST` | `/api/events/{id}/devices/{device_id}/reject-and-flag` | FR-503, FR-306, FR-308 |
| `POST` | `/api/events/{id}/dismiss` | FR-507 |
| `POST` | `/api/requests/{id}/verify-standalone` | FR-505 |
| `POST` | `/api/requests/{id}/reject-standalone` | FR-505 |
| `POST` | `/api/requests/{id}/dispatch-standalone` | FR-505b |
| `POST` | `/api/requests/{id}/split-out` | FR-504, FR-504b |
| `POST` | `/api/requests/{id}/merge` | FR-205c |
| `POST` | `/api/requests/{id}/rescue` | FR-407, FR-504b |
| `POST` | `/api/quarantine/{device_id}/reject-all` | FR-407 |
| `POST` | `/api/requests/{id}/override-urgency` | FR-603, FR-604 |
| `GET` | `/api/requests/{id}` | FR-506, FR-602 |
| `GET` | `/api/events/{id}` | FR-602 |
| `POST` | `/api/seed/replay` | FR-701–702, FR-208 |
