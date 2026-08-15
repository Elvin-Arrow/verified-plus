# Data Model Specification — Aid Request Triage & Trust Tool

Version 0.3 · Implements `docs/spec.md` v0.3 §6 and `docs/design.md` v0.3 §3 (post 6-document alignment pass — see §7 — and an 8-document pass adding `docs/ui-spec.md`, which surfaced a missing `quarantined → rejected` transition; fixed here alongside `docs/spec.md`/`docs/api-spec.md`/`docs/design.md`). This document is the authoritative field-by-field schema — types, constraints, defaults, relationships, and state machines — that `docs/api-spec.md`'s request/response bodies and `docs/design.md`'s pseudocode both serialize to/from.

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
| `urgency_score` | `int \| null` | `1 ≤ x ≤ 5`, or `null` | `null` in exactly two cases: (a) an LLM/embedding call failed or is still pending (NFR-103), or (b) the submitting device was flagged, so the request was quarantined at intake and the pipeline never ran at all (FR-107/308) — neither case is "an ambiguous input," which is a *third*, unrelated situation that still produces a valid non-null score (the FR-301 default of `3`). |
| `urgency_reasoning` | `string \| null` | — | `null` under the same two conditions as `urgency_score`. |
| `original_urgency_score` | `int \| null` | `1 ≤ x ≤ 5`, or `null` | Set only once, the first time `override-urgency` (FR-603) is called; never overwritten again — a second override changes `urgency_score` but not this field, so it always holds the LLM's original value, not the previous override. See `docs/design.md` §4.7 for the guard that enforces this. |
| `match_reasons` | `list[MatchResult]` | — | `MatchResult { candidate_id: string, is_match: bool, reason: string }`. The LLM's per-candidate judgments from FR-204, persisted at submission time so `GET /api/requests/{id}` (`docs/api-spec.md` §7) can render them later without a second LLM call. Empty list if there were no candidates in the geofenced pool; unset (not applicable) if the request was quarantined at intake. |
| `event_id` | `string \| null` | FK → `Event.id`, nullable | Set for `in_candidate_event`, `pending_addition`, `in_verified_event`; `null` for `standalone`/terminal-after-dissolution. |
| `status` | `RequestStatus` (§2.6) | required | See state machine, §3.1. |
| `verified` | `bool` | default `false` | Orthogonal to `status` — see §3.3. The field that actually decides Dispatch Queue membership for a `standalone` request. |
| `embedding` | `list[float] \| null` | — | Cached at submission time (FR-201); `null` under the same two conditions as `urgency_score` above. Never re-embedded on later comparisons — a fixed embedding model is assumed stable for the session's duration. |
| `device_flagged` | `bool` (derived, not stored) | — | Computed at read time as `DeviceFingerprint(device_fingerprint_id).device_flag`. Listed here because it appears in every API response (`RequestSummary`, `api-spec.md` §1.3) — not a column on `Request` itself, to avoid a denormalized copy going stale. |

**Not modeled** (explicitly, per `docs/spec.md` §8 and NFR-201): no name, phone number, or any other individually-identifying field. `device_fingerprint_id` is pseudonymous by design.

### 2.2 `Event`

A cluster of requests believed to describe one underlying incident.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `string` | PK, server-generated | e.g. `evt_d4e5f6` |
| `member_request_ids` | `list[string]` | FK[] → `Request.id`; **2+ required for the Event to exist as an Incident Card** (FR-501) | Active, current members — for a `candidate` Event these are still individually unverified (`status = in_candidate_event`); they only become coordinator-*approved* once the Event itself is verified (`verify_event`, `docs/design.md` §4.2b). Auto-dissolves at 0–1 (FR-504b, §3.4). |
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
  | reject_quarantined_group
```

### 2.7 Session-scoped, non-entity state

Not part of any entity's schema, but part of the store (`docs/design.md` §3) and referenced across `docs/spec.md`/`docs/api-spec.md`:

- `SessionConfig { geofence_radius_km: float = 1.0, max_cluster_span_km: float = 1.5 }` — FR-208. One instance per store, not per-request.
- `urgency_calibration_buffer: list[{text, original, corrected, reason}]`, `match_calibration_buffer: list[{a, b, reason}]` — FR-604, each capped at N=5 (FIFO eviction).
- `suggested_merges: list[{request_id, event_id?, request_id_2?, distance_km}]` — FR-205b. Exactly one of `event_id`/`request_id_2` is set, matching whichever side of the pair was excluded (§3.1 of `docs/design.md` §4.2). `distance_km` is the haversine distance that caused the geometric-filter exclusion — surfaced by `GET /api/requests/{id}` (`docs/api-spec.md` §7) so a coordinator reviewing the "Suggested Merge" affordance can see how close a near-miss it was. Cleared for a given request once a `merge` (FR-205c) or a later dissolution removes the relevant Event/request, and wholesale on a full FR-702 reset.

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
  quarantined ──reject_quarantined_group (FR-407, bulk per device)──▶ rejected (terminal;
      does NOT re-set device_flag — the device is already flagged, that's why it's here)
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

`verified` is set to `true` **only** by: `verify_event` (for current members), `approve_pending` (for promoted pending members), `verify_standalone`. It is set to `false` by: a `pending_addition` member reverting on dissolution without ever having been approved (`docs/design.md` §4.5), and — the case worth calling out explicitly, since it's easy to get backwards — **`split_out`, even when the request being split out was already `verified = true`** (`docs/design.md` §4.5b). FR-504 explicitly allows Split Out on any individual member of an *expanded Incident Card*, including a `verified` Event's card sitting in the Dispatch Queue — Split Out is not restricted to `candidate` Events the way Dismiss Cluster (FR-507) is. When it's used on an already-verified member, that member's own prior approval does not carry over: FR-504 calls this "re-evaluated independently," meaning it re-enters as a fresh, unverified standalone request. This is the opposite of FR-504b's *dissolution* case (§3.1 above) — dissolution preserves the **sole remaining, non-split-out** member's own verified state, precisely because that member wasn't the one a coordinator judged didn't belong; the member actively split out was.

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

## 7. Change log — 6-document alignment pass (v0.1 → v0.2)

A Gemini review across all six project documents (`idea.md`, `spec.md`, `design.md`, and this document's siblings `api-spec.md`/`architecture.md`) found several real defects, fixed here and in `docs/design.md`/`docs/spec.md` together:

1. **`urgency_score`/`embedding`/`urgency_reasoning` being `null` was documented as meaning only an LLM/embedding failure (NFR-103)** — wrong; a device-flagged-at-intake quarantine (FR-107) also skips the pipeline entirely and leaves these `null`, for an unrelated reason. §2.1 now names both cases.
2. **`member_request_ids` was labeled "approved members only"** — wrong for `candidate` Events, whose members are active but individually unverified until the whole Event is verified. §2.2 reworded.
3. **A factually incorrect claim that Split Out can never apply to an already-verified member** — FR-504 explicitly allows it on any member of an expanded Incident Card, verified or not. §3.3 rewritten with the correct behavior: a split-out member's own `verified` flag resets to `false` regardless of its prior state, which is the opposite of (and easily confused with) FR-504b's dissolution case.
4. **`match_reasons` (FR-506) had no field anywhere** — `api-spec.md` promised it in the detail response, but neither this document nor `design.md`'s `Request` dataclass had anywhere to store it. Added to §2.1 and to `design.md`'s submission pipeline.
5. **`suggested_merges` (§2.7) was missing `distance_km`**, which `api-spec.md` §7's example response already assumed. Added, and traced back to where `design.md`'s `assign()` now computes and stores it.
6. **`original_urgency_score`'s "never overwritten" guarantee wasn't actually enforced in `design.md`'s pseudocode** — a second override call blindly reset it every time. Fixed in `design.md` §4.7.
7. **`DeviceFingerprint.confirmed_fraud_request_ids` was never populated** by `design.md`'s `reject_and_flag_device`. Fixed.
8. **A real state-machine bug**: `reject_and_flag_device` updated a rejected member's `status` but never removed it from `Event.member_request_ids`, so `maybe_dissolve_event`'s length check could never see the membership actually shrink — Events could accumulate only-rejected members and never dissolve, violating the §3.4 invariant. Fixed by centralizing all member removal through one `detach_from_event` helper in `design.md` §4.4, used consistently by reject-and-flag, split-out, and the quarantine sweep.
9. **`split_out` and `rescue` were referenced by name in `api-spec.md`/`design.md`'s prose but had no actual pseudocode anywhere.** Added as `design.md` §4.5b.
