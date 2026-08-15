# Data Model Specification — Aid Request Triage & Trust Tool

Version 0.1 · Implements `docs/spec.md` v0.3 §6 and `docs/design.md` v0.2 §3. This document is the authoritative field-by-field schema — types, constraints, defaults, relationships, and state machines — that `docs/api-spec.md`'s request/response bodies and `docs/design.md`'s pseudocode both serialize to/from.

## 1. Storage model

Everything below is held in one process-local `InMemoryStore` (`docs/design.md` §3) — no schema migration concerns, no ORM, no persistence across restarts. Field types are given as Python-ish annotations since that's the assumed backend language (`docs/spec.md` §3); a different backend language would map these 1:1 onto its own struct/record type.

## 2. Entities

### 2.1 `Request`

The central entity — one submitted aid ask.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `string` | PK, server-generated, immutable | e.g. `req_a1b2c3` |
| `need_description` | `string` | non-empty (FR-102) | Free text, any language. No max length enforced. |
| `location` | `Location` (§2.5) | required (FR-101) | Immutable after submission — a request never moves in space. |
| `photo_url` | `string \| null` | optional (FR-103) | Passive display only; never fed to any model. |
| `device_fingerprint_id` | `string` | required (FR-105) | FK → `DeviceFingerprint.id`. |
| `submitted_at` | `datetime` | required, server clock UTC (FR-106) | Immutable. |
| `urgency_score` | `int \| null` | `1 ≤ x ≤ 5`, or `null` | `null` only means "pending/failed" (NFR-103) — an ambiguous-input default still produces `3` (FR-301), never `null`. |
| `urgency_reasoning` | `string \| null` | — | `null` iff `urgency_score` is `null`. |
| `original_urgency_score` | `int \| null` | `1 ≤ x ≤ 5`, or `null` | Set only once, the first time `override-urgency` (FR-603) is called; never overwritten again — a second override changes `urgency_score` but not this field, so it always holds the LLM's original value, not the previous override. |
| `event_id` | `string \| null` | FK → `Event.id`, nullable | Set for `in_candidate_event`, `pending_addition`, `in_verified_event`; `null` for `standalone`/terminal-after-dissolution. |
| `status` | `RequestStatus` (§2.6) | required | See state machine, §3.1. |
| `verified` | `bool` | default `false` | Orthogonal to `status` — see §3.3. The field that actually decides Dispatch Queue membership for a `standalone` request. |
| `embedding` | `list[float] \| null` | — | Cached at submission time (FR-201); `null` iff the embedding call failed (NFR-103). Never re-embedded on later comparisons — a fixed embedding model is assumed stable for the session's duration. |
| `device_flagged` | `bool` (derived, not stored) | — | Computed at read time as `DeviceFingerprint(device_fingerprint_id).device_flag`. Listed here because it appears in every API response (`RequestSummary`, `api-spec.md` §1.3) — not a column on `Request` itself, to avoid a denormalized copy going stale. |

**Not modeled** (explicitly, per `docs/spec.md` §8 and NFR-201): no name, phone number, or any other individually-identifying field. `device_fingerprint_id` is pseudonymous by design.

### 2.2 `Event`

A cluster of requests believed to describe one underlying incident.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `string` | PK, server-generated | e.g. `evt_d4e5f6` |
| `member_request_ids` | `list[string]` | FK[] → `Request.id`; **2+ required for the Event to exist as an Incident Card** (FR-501) | Active, approved members only. Auto-dissolves at 0–1 (FR-504b, §3.4). |
| `pending_member_request_ids` | `list[string]` | FK[] → `Request.id` | FR-304b: matched to this (already-`verified`) Event but not yet coordinator-approved. Disjoint from `member_request_ids` — a request is in exactly one of the two lists, never both. |
| `status` | `EventStatus` (§2.6) | required | `candidate` → `verified` → `dispatched`, one-directional (§3.2). |
| `verified_by` | `string \| null` | — | Set alongside `status → verified`; the `actor` from that action. |
| `verified_at` | `datetime \| null` | — | Set alongside `verified_by`. |
| `representative_location` | `Location` (§2.5) | required once ≥1 member exists | Centroid of `member_request_ids`' locations (NOT including `pending_member_request_ids` — see §4.1 note). Recomputed on every membership change to `member_request_ids`. |
| `created_at` | `datetime` | required | Set once, at bootstrap (FR-205 step 5). |

**Derived, not stored** (computed at read time for API responses, per `docs/api-spec.md` §3): `member_count`, `distinct_device_count`, `max_urgency_score`.

### 2.3 `DeviceFingerprint`

An anonymous, pseudonymous submission-channel identifier.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `string` | PK, client-generated (localStorage UUID) | `docs/design.md` §3. Combined server-side with an IP/UA hash as a secondary signal — that hash is not separately modeled; treat it as an implementation detail of fingerprint derivation, not a stored field. |
| `first_seen_at` | `datetime` | required | Set on first-ever request from this fingerprint. |
| `device_flag` | `bool` | default `false` | FR-305/306. One-directional within a session: only set `true`, never reset to `false` short of a full FR-702 reset — there is no "un-flag a device" action in this version. |
| `confirmed_fraud_request_ids` | `list[string]` | FK[] → `Request.id` | The specific request(s) whose rejection is what set `device_flag = true` (i.e. the ones passed to the triggering `reject-and-flag` call) — an audit trail distinct from the general `CoordinatorAction` log, scoped to "why is this device flagged." |

### 2.4 `CoordinatorAction`

Append-only audit log entry (FR-601).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `string` | PK, server-generated | |
| `actor` | `string` | required, free text | No auth (§8 of `docs/spec.md`) — this is a self-reported label, not a verified identity. |
| `action_type` | `ActionType` (§2.6) | required | |
| `target_id` | `string` | required | A `Request.id` or `Event.id`, depending on `action_type`. Not FK-enforced at the type level (the ID space isn't namespaced by prefix at runtime, only by convention — see §5 on ID generation). |
| `timestamp` | `datetime` | required | |
| `note` | `string \| null` | optional | For `override_urgency`, this is the calibration `reason` (FR-604) — the one place `note` is more than a human-readable label, it's actually consumed downstream by the LLM prompt. |

### 2.5 `Location` (value type, not an entity)

```
Location { lat: float, lng: float }
```

No separate ID, no independent lifecycle — always embedded in a `Request` or `Event`. `lat ∈ [-90, 90]`, `lng ∈ [-180, 180]`; out-of-range values are a `400 VALIDATION_ERROR` at the API layer (`docs/api-spec.md` §2), not a data-model-level constraint enforced by the store itself (the in-memory store trusts its callers, per the "no ORM" note in §1).

### 2.6 Enumerations

```
RequestStatus:
  standalone | in_candidate_event | pending_addition | in_verified_event
  | dispatched | rejected | quarantined

EventStatus:
  candidate | verified | dispatched

ActionType:
  verify_event | approve_pending | approve_dispatch | reject_flag_device
  | dismiss_cluster | split_out | rescue_from_quarantine | verify_standalone
  | reject_standalone | dispatch_standalone | override_urgency | manual_merge
```

### 2.7 Session-scoped, non-entity state

Not part of any entity's schema, but part of the store (`docs/design.md` §3) and referenced across `docs/spec.md`/`docs/api-spec.md`:

- `SessionConfig { geofence_radius_km: float = 1.0, max_cluster_span_km: float = 1.5 }` — FR-208. One instance per store, not per-request.
- `urgency_calibration_buffer: list[{text, original, corrected, reason}]`, `match_calibration_buffer: list[{a, b, reason}]` — FR-604, each capped at N=5 (FIFO eviction).
- `suggested_merges: list[{request_id, event_id?, request_id_2?}]` — FR-205b. Cleared for a given request once a `merge` (FR-205c) or a later dissolution removes the relevant Event/request.

## 3. Relationships & state machines

### 3.1 `Request.status` transitions

```
                    ┌─────────────┐
        (submit,    │ standalone  │◀─────────────────────────┐
      no LLM match)  └──────┬──────┘                          │
                            │                                  │ split_out (FR-504) /
              (submit,      │ manual_merge → bootstrap          dismiss_cluster (FR-507) /
           matches a         ▼                                  Event dissolves (FR-504b) /
          standalone)  ┌──────────────────┐                     rescue (FR-407) — always
                        │ in_candidate_event│                    lands back on `standalone`
                        └────────┬──────────┘
                                  │ verify_event (FR-304)
                                  ▼
                         ┌──────────────────┐        approve_pending (FR-304b)
     (submit, matches     │ in_verified_event│◀───────────────────────┐
      a verified Event)   └────────┬─────────┘                        │
                                     │ approve_dispatch (FR-502)        │
                                     ▼                          ┌──────┴──────────┐
                              ┌─────────────┐                    │ pending_addition │
                              │  dispatched │  (terminal)         └──────────────────┘
                              └─────────────┘

  standalone ──reject_standalone──▶ rejected (terminal)
  in_candidate_event / in_verified_event / pending_addition
      ──reject_flag_device (FR-503)──▶ rejected (if targeted directly)
                                        or quarantined (if swept, FR-308(b))
  ANY non-terminal status ──(device gets flagged, FR-308(b))──▶ quarantined
  quarantined ──rescue (FR-407)──▶ standalone (re-enters matching, FR-202-206 rerun)
  standalone ──verify_standalone (FR-505)──▶ dispatched   (atomic, see api-spec.md §5)
  standalone (verified=true, via FR-504b) ──dispatch_standalone (FR-505b)──▶ dispatched
```

Terminal states: `dispatched`, `rejected`. No transition leaves either (a `rejected` or `dispatched` request is immutable going forward — FR-406's Archive view is explicitly read-only).

### 3.2 `Event.status` transitions

```
candidate ──verify (FR-304)──▶ verified ──dispatch (FR-502)──▶ dispatched (terminal)
candidate ──dismiss (FR-507)──▶ (Event deleted, members revert to standalone)
candidate/verified ──membership drops to 0-1 (FR-504b)──▶ (Event deleted)
```

An `Event` is **deleted**, not soft-terminal, on dissolution or dismissal — there is no `Event.status = "dissolved"` value. Once gone, its former `id` is never reused and any dangling reference (a `Request.event_id` pointing to it) must already have been cleared in the same atomic operation that deleted it (`docs/design.md` §4.5, §4.6). A `dispatched` Event is the only Event-level terminal state that persists as a row (visible in `GET /api/archive`).

### 3.3 The `verified` flag — why it's separate from `status`

`Request.status = "standalone"` is reachable from two different histories that must route to different queues:
1. **Never verified** — fresh submission with no match, or reverted via Split Out/Dismiss Cluster/Rescue. `verified = false`. → Intake & Verification Inbox (FR-401).
2. **Was verified, Event since dissolved** — this request earned `verified = true` while it was an `in_verified_event` member (via `approve_pending` or the initial `verify_event`), and its Event later dissolved out from under it (FR-504b). `verified = true` is preserved. → Dispatch Queue (FR-403), awaiting `dispatch_standalone`.

`verified` is set **only** by: `verify_event` (for current members), `approve_pending` (for promoted pending members), `verify_standalone`. It is set to `false` only when a `pending_addition` member reverts on dissolution without ever having been approved (`docs/design.md` §4.5). No other code path touches it — critically, ordinary Split Out and Dismiss Cluster leave `verified` untouched at `false` (they only ever apply to unverified members in the first place, since FR-507 restricts Dismiss Cluster to `candidate` Events and FR-504's Split Out on a `verified` Event's member would only run before that member's own `verified` flag was set — i.e. never on an already-verified member without going through dissolution instead).

### 3.4 Event dissolution and orphan prevention

Two invariants the store must never violate, both enforced in `maybe_dissolve_event` (`docs/design.md` §4.5):

1. **No `Event` exists with `len(member_request_ids) ≤ 1`** at rest (transiently true mid-operation, never observable via the API).
2. **No `Request.event_id` points to a nonexistent `Event`** — when an `Event` is deleted, every request referencing it (both `member_request_ids` and `pending_member_request_ids`) has `event_id` cleared in the same operation.

## 4. Derived/computed values (never stored)

Kept out of the schema deliberately — storing them would create a second source of truth that could drift from the fields they're computed from.

| Value | Formula | Used by |
|---|---|---|
| `Event.member_count` | `len(member_request_ids)` | FR-501 (2+ threshold), sort input |
| `Event.distinct_device_count` | `len({r.device_fingerprint_id for r in members})` | FR-401/403 sort, secondary key |
| `Event.max_urgency_score` | `max(r.urgency_score for r in members if not None)` | FR-401/403 sort, primary key |
| `Request.device_flagged` | `DeviceFingerprint(device_fingerprint_id).device_flag` | Every API response; FR-309 |
| Sort key (Event or standalone Request) | `(max_urgency_score, distinct_device_count)`, tuple-descending | FR-401, FR-403 (see `docs/design.md` §4.3) |

**4.1 Centroid note**: `representative_location` is recomputed only from `member_request_ids`, never `pending_member_request_ids` — a pending addition doesn't get to shift where the Event "is" until a coordinator actually approves it (`approve_pending` triggers a recompute at promotion time, per `docs/design.md` §4.2b).

## 5. ID generation

Not a hard requirement, but documented so `docs/api-spec.md`'s examples and any test fixtures stay consistent: IDs are generated as `{prefix}_{random}` where prefix is `req` (Request), `evt` (Event), `dev` (DeviceFingerprint), `act` (CoordinatorAction). The prefix is a debugging/readability convenience only — nothing in the data model or API parses or validates it; a request handler MUST NOT assume an ID's entity type from its prefix alone (e.g. `merge`'s `target_event_id`/`target_request_id` are still two separate, explicitly-typed fields in the request body — see `docs/api-spec.md` §5 — rather than one polymorphic `target_id` disambiguated by prefix-sniffing).

## 6. Cross-references

| This document | Corresponds to |
|---|---|
| §2.1 `Request` | `docs/spec.md` §6 `Request` block; `docs/design.md` §3 `Request` dataclass; `docs/api-spec.md` §1.3 `RequestSummary` / §7 detail response |
| §2.2 `Event` | `docs/spec.md` §6 `Event` block; `docs/design.md` §3 `Event` dataclass |
| §2.3 `DeviceFingerprint` | `docs/spec.md` §6 `DeviceFingerprint` block |
| §2.4 `CoordinatorAction` | `docs/spec.md` §6 `CoordinatorAction` block; FR-601 |
| §3.1–3.4 state machines | `docs/spec.md` FR-205/205c, FR-304/304b, FR-501–507; `docs/design.md` §4.2–4.6 |
