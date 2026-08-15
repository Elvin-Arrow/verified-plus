# Requirement Specification — Aid Request Triage & Trust Tool

Version 0.2 (post-verification) · Derived from `docs/idea.md`, hardened via a 13-round Gemini verification pass (see §10 for a change log).

## 1. Purpose & scope

This document specifies the functional and non-functional requirements for a weekend-hackathon-scoped system that lets aid coordinators receive, verify, deduplicate, and prioritize incoming aid requests from GPS-native intake channels. It covers the intake pipeline, duplicate/event-corroboration detection, human-gated verification, the unified triage queues, and the demo-support tooling described in `docs/idea.md`.

Out of scope (explicitly, per the idea doc): inventory/supply tracking and routing (owned by HELM/LINK/Platforma-class tools), image-based duplicate/fraud detection via vision models, hotline/SMS intake without structured coordinates, and full identity verification of requesters.

## 2. Definitions

| Term | Meaning |
|---|---|
| Request | A single aid ask submitted at intake: need, location, description, optional photo. |
| Device fingerprint | An anonymous, client-generated token (persisted in local storage) plus an IP/User-Agent hash, identifying a submitting browser session. Not a verified identity. |
| Event | A cluster of geofenced + semantically matched requests believed to describe one underlying incident. Has `status`: `candidate` (unreviewed), `verified` (coordinator-confirmed, active), or `dispatched` (resolved/actioned, terminal). |
| Verification status | A per-request boolean-like state: `unverified` until a coordinator explicitly acts on it (directly, or via its Event), `verified` once approved into the active queue, `dispatched`/`rejected` as terminal states. |
| Device flag | A marker on a device fingerprint with a confirmed history of fraudulent/rejected requests, used to auto-quarantine (not auto-block) its future submissions. |
| Quarantine | A holding state for requests from a flagged device — accepted but withheld from normal triage queues pending manual review. |
| Coordinator | The human user of the dashboard who verifies events, reviews flags, and dispatches aid. |

## 3. Assumed technology baseline (hackathon defaults)

No stack was mandated; the following are assumptions, not requirements:

- **Backend**: Python, FastAPI, single-process, in-memory data store (Python dicts/lists) for the demo; no external database required.
- **Frontend**: React (or plain JS) single-page coordinator dashboard; a separate lightweight intake form (mobile-web, or simulated via the seed script).
- **Embeddings**: one hosted embedding model call per submission (e.g. `text-embedding-3-small`-class); vectors held in memory, compared via NumPy cosine similarity — no vector database.
- **LLM**: one hosted LLM call per submission (e.g. a `gpt-4o-mini`-class model) returning structured JSON (urgency score, duplicate/cluster judgment, human-readable reasoning).
- **Device fingerprint**: a UUID written to `localStorage` on first page load, sent with every submission from that browser, combined server-side with a hash of IP + User-Agent as a secondary signal.
- **Geolocation**: browser Geolocation API or an interactive map-pin picker; no server-side geocoding of free text (see FR-101).

## 4. Functional requirements

### 4.1 Intake (FR-1xx)

- **FR-101** — The system SHALL require a structured `{lat, lng}` coordinate pair at submission time, captured via browser geolocation or an interactive map pin. Free-text-only location SHALL be rejected at the client before submission.
- **FR-102** — The system SHALL require a free-text `need_description` field, accepting any language or phrasing, with no minimum length enforced beyond non-empty.
- **FR-103** — The system SHALL accept an optional photo upload per request. The photo SHALL be stored and displayed to coordinators for visual inspection only; no automated image analysis SHALL be performed on it.
- **FR-104** — The system SHALL NOT require account creation, login, or any personally identifying field to submit a request.
- **FR-105** — The system SHALL attach a device fingerprint (§3) to every submitted request, generated client-side and persisted across submissions from the same browser/device.
- **FR-106** — The system SHALL timestamp every request at submission (server clock, UTC).
- **FR-107** — If the submitting device's fingerprint has `device_flag = true` (§4.3), the system SHALL still accept the submission (never a hard reject at intake) but SHALL initialize it directly into `quarantined` status rather than routing it to the Intake & Verification Inbox (§4.4). *(This is a forward reference resolved fully in FR-308/FR-407.)*

### 4.2 Geofenced duplicate & event-match detection (FR-2xx)

- **FR-201** — On submission, the system SHALL compute a text embedding of the request's `need_description`.
- **FR-202** — Before any semantic comparison, the system SHALL build a candidate pool of prior requests/events whose `representative_location` (an Event's centroid, or a standalone request's own location) is within a **1 km** radius of the new request, **and** which meet at least one of: (a) the candidate belongs to an Event that is not yet `dispatched`/`rejected` (no age limit — an active, ongoing emergency stays comparable no matter how long it has been open), or (b) the candidate was submitted/created within the last **48 hours** (applies to standalone requests and to inactive/resolved events, which age out).
- **FR-203** — Within that candidate pool, the system SHALL rank candidates by cosine similarity of their embeddings and select the **top 5** for further evaluation.
- **FR-204** — The system SHALL pre-compute the physical distance (e.g. haversine) between the new request and each of the top-5 candidates and include it as an explicit, human-readable value (e.g. "150 meters away") in the LLM prompt used to judge each candidate — raw lat/lng floats SHALL NOT be the only spatial signal given to the LLM, since the model cannot reliably reason about proximity from coordinates alone. The LLM call SHALL return, per candidate: a match/no-match judgment and a human-readable reason (e.g. "closely matches request #114, submitted 20 min ago, same neighborhood, 150m away").
- **FR-205** — Cluster assignment for a new request that the LLM judged a match against one or more candidates:
  1. **Geometric filter first**: discard any matched candidate's Event if adding the new request would place any member (or the new request itself) more than **1.5 km** from that Event's `representative_location`.
  2. **Authority selection**: among the Events that survive the geometric filter, join the new request to the one with the highest operational authority, ranked `dispatched` > `verified` > `candidate`.
  3. If the matched Event is `verified` or `dispatched`, the new request SHALL NOT auto-inherit verified/active status — it attaches with `status = pending_addition` (see FR-304b) rather than immediately joining the active queue.
  4. If the matched Event is `candidate`, the new request joins it directly as an unverified member.
  5. If no matched Event survives the geometric filter, or there were no matches at all, the new request SHALL form its own new `candidate` Event (if it matched something geometrically excluded) or remain `standalone` (if there were no matches at all).
  6. The system SHALL NOT automatically merge two distinct existing Events under any circumstance.
- **FR-205b** — If an LLM match spans multiple distinct Events (including ones excluded by the geometric filter in FR-205 step 1), the system SHALL surface a **"Suggested Merge"** indicator on the relevant Incident Cards, allowing a coordinator to manually merge them into one Event.
- **FR-206** — A request with no LLM-judged matches SHALL be `standalone` and SHALL still be individually visible to coordinators via the Intake & Verification Inbox (§4.4), not silently dropped.

### 4.3 Verification & device scrutiny (FR-3xx)

- **FR-301** — The system SHALL compute an `urgency_score` (integer 1–5) for every request via the same LLM call as FR-204, using a fixed rubric (5 = immediate threat to life/medical, down to 1 = non-urgent/general supply request — full rubric text is an open item, see §9).
- **FR-302** — The urgency-scoring prompt SHALL instruct the model to score based on described severity, not on writing fluency, message length, or language; brevity or non-native phrasing SHALL NOT by itself lower the score.
- **FR-303** — Every request and Event SHALL carry a `verification_status` (`unverified` / `verified` / `dispatched` / `rejected` / `quarantined`, per the state values in §6). Cluster size or member/device count alone SHALL NOT change `verification_status` — only an explicit coordinator action does.
- **FR-304** — Upon coordinator verification of a candidate Event (FR-502), the system SHALL set `verification_status = verified` for that Event and for the member requests explicitly present and approved at that time. It SHALL NOT retroactively or automatically apply to requests added later.
- **FR-304b** — A new request matched (via FR-205) to an already-`verified` Event SHALL be attached to it with `status = pending_addition` and SHALL NOT enter the Dispatch Queue (§4.4) until a coordinator explicitly approves it (FR-502's "Approve All Pending" action), even though its parent Event is already verified.
- **FR-305** — The system SHALL maintain a `device_flag` (boolean) per device fingerprint, initialized `false` for every new/unseen fingerprint.
- **FR-306** — A device fingerprint's `device_flag` SHALL be set `true` only after a coordinator has taken an explicit "Reject & Flag Device" action (FR-503) confirming at least one request from that fingerprint as fraudulent — never by automated inference.
- **FR-307** — `device_flag` SHALL NOT itself be an input to any sort/ranking formula; its only effects are the quarantine routing in FR-308 and the visual scrutiny marker in FR-309.
- **FR-308** — Once `device_flag = true` for a fingerprint: (a) per FR-107, all new submissions from that fingerprint are initialized directly into `quarantined` status rather than the Intake & Verification Inbox; (b) all of that fingerprint's other currently-active requests (in any non-terminal status, across any cluster) SHALL be automatically swept into `quarantined` status at the moment the flag is set (FR-503). This SHALL NOT retroactively affect requests already in a terminal state (`dispatched`/`rejected`).
- **FR-309** — Any request visible in the Archive/Resolved view (FR-406) whose device fingerprint is flagged SHALL carry a visible scrutiny marker. (Flagged-device requests in active workflow are already isolated into Quarantine per FR-308, so no separate marker is needed there.)

### 4.4 Triage queues (FR-4xx)

- **FR-401** — The system SHALL present a unified **Intake & Verification Inbox** containing every `candidate` Event and every `unverified` standalone request (i.e., everything not yet verified, not quarantined, and not terminal), consisting of two sections:
  1. **Needs Manual Triage** (top, unsorted-by-formula): any item containing a member/request whose `urgency_score` is `null` (embedding/LLM call failed or is still pending, per NFR-103) — surfaced immediately for manual attention rather than participating in the formula below.
  2. **Sorted list**: all other items, sorted **primarily** descending by `max(urgency_score of members)`, and **secondarily** descending by `distinct_device_fingerprint_count(members)` (a standalone request is treated as a cluster of one, from one device).
- **FR-402** — Each `candidate` Event in the inbox SHALL support a **"Verify Event & Approve All"** action (FR-502) and each standalone request SHALL support single-click inline **"Verify & Dispatch"** / **"Reject"** actions (FR-505) directly from the list view. *(Explicitly dismissing a candidate Event as "not a real event," without it being device fraud, remains an open item — see §9.)*
- **FR-403** — The system SHALL present a **Dispatch Queue** listing only requests with `verification_status = verified` (i.e., Event members explicitly approved, and explicitly verified standalone requests) — excluding anything `dispatched`, `rejected`, or `quarantined`. Sorting uses the same lexicographic rule as FR-401 (urgency primary, distinct-device-count secondary) over the verified membership.
- **FR-404** — *(Reserved — device-flag visual marking in the active queues was removed by FR-308's quarantine design; flagged devices no longer appear in Dispatch Queue at all once flagged.)*
- **FR-405** — Both queues SHALL update within a bounded time (see NFR-101) after any new request is submitted or any coordinator action is taken, without requiring a manual page reload.
- **FR-406** — The system SHALL provide an **Archive / Resolved view** listing all requests/Events in a terminal state (`dispatched`, `rejected`), so the active queues stay uncluttered while remaining auditable (FR-309, FR-601).
- **FR-407** — The system SHALL provide a separate **Quarantine Inbox** listing all requests with `status = quarantined`. It SHALL support a bulk **"Reject All"** action (per device group) and an individual **"Rescue"** action that moves a request back into the normal Intake & Verification Inbox flow (for cases where a shared/legitimate device was caught behind another user's flag).

### 4.5 Incident Cards & coordinator actions (FR-5xx)

- **FR-501** — Every Event with 2+ active (non-terminal, non-quarantined) member requests SHALL render as a single **Incident Card** (not a flat list of its member rows) in whichever queue it currently belongs to, showing a title/location summary and a "N corroborating reports" badge.
- **FR-502** — An Incident Card SHALL support:
  - For a `candidate` Event: **"Verify Event & Approve All"** — sets the Event and its current members to `verification_status = verified` (FR-304) and moves the card to the Dispatch Queue.
  - For an already-`verified` Event with `pending_addition` members: a distinct **"Approve All Pending"** action, grouped by device fingerprint (mirroring FR-503) so a coordinator can admit genuine new corroboration in one click while still seeing device-level spam shape.
  - For a `verified` Event ready for action: **"Approve"** (dispatch) — transitions the Event and all its currently active member requests to `status = dispatched` (terminal; see §6), removing it from the Dispatch Queue and into the Archive (FR-406).
- **FR-503** — An expanded Incident Card SHALL group its member requests **by device fingerprint**, not as one flat list. Each device group SHALL have its own **"Reject & Flag Device"** action, which: (a) sets `device_flag = true` for that fingerprint (FR-306); (b) transitions that device group's requests within this card to `rejected`; (c) sweeps all of that device's other currently-active requests (elsewhere in the system) into `quarantined` (FR-308).
- **FR-504** — Any individual member request within an expanded Incident Card SHALL support a **"Split Out"** action that removes it from the cluster and re-inserts it as a standalone request, re-evaluated independently against FR-401/FR-403.
- **FR-504b** — If a "Split Out", "Reject & Flag Device", or "Rescue" action causes an Event's active member count to drop to exactly 1, the system SHALL automatically dissolve that Event: the sole remaining request has its `event_id` cleared, reverts to `standalone`, and keeps whichever verification state it individually held (i.e., stays in the Dispatch Queue if it was already verified, or the Intake Inbox if not) — it SHALL remain visible via FR-401/FR-403, never orphaned.
- **FR-505** — A standalone (unclustered) request SHALL be actionable individually via single-click inline **"Verify & Dispatch"** / **"Reject"** actions directly from the Intake & Verification Inbox list view, without requiring an expanded detail view, to keep per-item friction bounded even though every standalone request requires an explicit human action (see rationale in §10, Finding 3).
- **FR-506** — Every flag or match judgment shown to a coordinator (duplicate match, urgency score, device flag) SHALL be accompanied by a human-readable reason string generated at detection time (FR-204), not a bare numeric score.

### 4.6 Feedback loop (FR-6xx)

- **FR-601** — Every coordinator action that confirms, overrides, or rejects a system judgment (verify event, approve pending, reject & flag device, split out, rescue, verify/reject standalone, dispatch) SHALL be recorded in an append-only action log with: actor, action type, target ID(s), timestamp.
- **FR-602** — This action log SHALL be available in the request/Event detail view. (Whether it actively re-tunes future scoring, vs. only being displayed, remains an open item — see §9.)

### 4.7 Demo support (FR-7xx)

- **FR-701** — The system SHALL provide a seed/replay mechanism that submits a batch of pre-authored synthetic requests (target: ~50) through the same live intake API used by real submissions (not a direct database write), including at least: several genuine multi-device event clusters, at least one seeded single-device fraud cluster, and several standalone unrelated requests.
- **FR-702** — The seed/replay mechanism SHALL be triggerable on demand. If run in "reset" mode, it SHALL perform a **complete cascading wipe of all in-memory state** — Requests, Events, `DeviceFingerprint` flags, and the `CoordinatorAction` log — before injecting the new seed batch, so no orphaned IDs, stale device flags, or dangling audit-log references survive between demo runs. If run in "append" mode, this wipe SHALL NOT occur, and the behavior (append vs. reset) SHALL be an explicit, documented choice at trigger time, not an implicit default.

## 5. Non-functional requirements

- **NFR-101 (Latency)** — End-to-end processing of a single submitted request (embed → geofence filter → cosine top-5 → LLM judgment) SHALL complete within **5 seconds** under demo-scale data volumes (≤ 1,000 stored requests).
- **NFR-102 (Scale)** — The system SHALL support at least 1,000 stored requests and at least 50 concurrent Incident Cards without UI degradation, using in-memory storage (§3); no external vector database or persistent DB is required for this scale.
- **NFR-103 (Resilience)** — If the LLM or embedding call fails or times out for a given submission, the system SHALL NOT crash or drop the request; it SHALL store it with `urgency_score = null` and duplicate/cluster evaluation marked "pending/unavailable," and SHALL surface it via the **Needs Manual Triage** section (FR-401) rather than participating in the numeric sort formula (avoiding the `TypeError`/crash risk of sorting against a null value, and avoiding silently defaulting to a specific urgency).
- **NFR-201 (Privacy)** — The system SHALL NOT require or store any field that identifies a real individual (name, national ID, phone number) as a condition of submission; the device fingerprint (§3) SHALL be treated as pseudonymous, not identifying — and, per FR-308, is deliberately never used to permanently hard-block future submissions, since shared devices are common in displacement settings.
- **NFR-202 (Data handling)** — All demo/test data SHALL be synthetic or drawn from already-public, non-sensitive sources (HumAID/CrisisNLP-derived text per `docs/idea.md` §Data strategy); no real, current aid-recipient data SHALL be used.
- **NFR-301 (Explainability)** — No automated judgment (duplicate match, urgency score, device flag) SHALL be presented to a coordinator without an accompanying human-readable reason string.
- **NFR-302 (Auditability)** — Every coordinator override SHALL be attributable and timestamped (FR-601) and retrievable for at least the duration of the demo session (subject to the explicit reset behavior in FR-702).
- **NFR-401 (Usability)** — A coordinator SHALL be able to fully process (verify/reject/split) a demo-scale seeded batch (~50 requests, per FR-701) in a live pitch setting within a few minutes, relying on Incident Card rollups and single-click inline standalone actions rather than per-request detail views, for the non-flagged majority of requests.

## 6. Data model (informative)

```
Request {
  id: string
  need_description: string
  location: { lat: float, lng: float }
  photo_url: string | null
  device_fingerprint_id: string
  submitted_at: datetime (UTC)
  urgency_score: int (1-5) | null         // null = NFR-103 pending/failed state
  urgency_reasoning: string | null
  event_id: string | null                 // Event this belongs to, if any
  status: enum {
    standalone,           // no event, not yet verified
    in_candidate_event,   // member of an unverified Event
    pending_addition,     // matched to an already-verified Event, awaiting FR-304b approval
    in_verified_event,    // member of a verified, active Event
    dispatched,           // terminal — resolved/actioned (FR-502 "Approve")
    rejected,             // terminal — explicitly rejected (standalone or via FR-503)
    quarantined           // held due to device_flag (FR-308)
  }
}

Event (candidate/verified/dispatched cluster) {
  id: string
  member_request_ids: [string]            // active members; does not include split_out/quarantined
  status: enum { candidate, verified, dispatched }
  verified_by: string | null              // coordinator id
  verified_at: datetime | null
  representative_location: { lat, lng }   // centroid; used for FR-202 geofencing and FR-205 distance bound
  created_at: datetime
}

DeviceFingerprint {
  id: string
  first_seen_at: datetime
  device_flag: bool                       // FR-305/306
  confirmed_fraud_request_ids: [string]
}

CoordinatorAction (audit log, FR-601) {
  id: string
  actor: string
  action_type: enum {
    verify_event, approve_pending, approve_dispatch,
    reject_flag_device, split_out, rescue_from_quarantine,
    verify_standalone, reject_standalone
  }
  target_id: string
  timestamp: datetime
  note: string | null
}
```

Note: `event_confidence` from the v0.1 draft has been removed as a variable entirely — priority is now driven solely by the lexicographic `(urgency_score, distinct_device_fingerprint_count)` sort applied identically in both queues, gated by `verification_status`/`status` rather than a continuous weight (see §10, Finding 4).

## 7. API surface (informative, illustrative)

| Method | Path | Purpose | Requirements |
|---|---|---|---|
| `POST` | `/api/requests` | Submit a new request | FR-101–107, FR-201–206, FR-301–302 |
| `POST` | `/api/seed/replay` | Bulk-inject demo batch via the live intake path (reset or append mode) | FR-701–702 |
| `GET` | `/api/intake-inbox` | List Intake & Verification Inbox, pre-sorted, with Needs-Manual-Triage section | FR-401–402 |
| `POST` | `/api/events/{id}/verify` | Verify a candidate Event, approve current members | FR-304, FR-502 |
| `POST` | `/api/events/{id}/approve-pending` | Admit `pending_addition` members of an already-verified Event | FR-304b, FR-502 |
| `POST` | `/api/events/{id}/dispatch` | Mark a verified Event (and members) dispatched | FR-502, §6 |
| `GET` | `/api/dispatch-queue` | List Dispatch Queue, pre-sorted | FR-403 |
| `POST` | `/api/events/{id}/devices/{device_id}/reject-and-flag` | Reject a device group's members, flag device, quarantine its other requests | FR-503, FR-306, FR-308 |
| `POST` | `/api/requests/{id}/split-out` | Eject one request from its cluster (may dissolve the Event, FR-504b) | FR-504, FR-504b |
| `POST` | `/api/requests/{id}/verify-standalone` | Verify a standalone request directly | FR-505 |
| `POST` | `/api/requests/{id}/reject-standalone` | Reject a standalone request directly | FR-505 |
| `GET` | `/api/quarantine` | List Quarantine Inbox | FR-407 |
| `POST` | `/api/requests/{id}/rescue` | Move a quarantined request back to the Intake Inbox | FR-407, FR-504b |
| `GET` | `/api/archive` | List resolved/terminal items | FR-406 |
| `GET` | `/api/requests/{id}` | Full detail incl. reasoning + action history | FR-506, FR-602 |

## 8. Out of scope

- Inventory, stock levels, or depot routing (except the optional read-only stretch badge noted in `docs/idea.md`, not specified here as a firm requirement).
- Any intake channel that does not supply structured coordinates (voice hotline, plain SMS) — see FR-101 and idea.md §Scope.
- Automated image-based duplicate/fraud detection.
- Multi-coordinator conflict resolution (two coordinators acting on the same event/request simultaneously) — not addressed by this version.
- Authentication/authorization for the coordinator dashboard itself.

## 9. Open questions for the user

1. Exact urgency rubric wording beyond the 1/5 anchor points (FR-301) — needs the full 1–5 rubric text.
2. FR-402: is there an explicit "this candidate Event is not real, dismiss it" action distinct from device-level Reject & Flag, for cases where a cluster is a false-positive LLM mis-merge with no bad actor involved? (Currently unresolved — Split Out on each member is the closest existing mechanism but requires per-member action.)
3. FR-602: does the feedback/action log only display override history, or must it feed back into future scoring/rubric behavior (e.g. adaptive weighting), and if the latter, what's the mechanism given no ML training step is otherwise in scope?
4. The 1 km geofence radius (FR-202) and 1.5 km max-cluster-span bound (FR-205) are placeholder values carried from the idea doc — do these need to vary by terrain/context (dense urban vs. rural), or are fixed constants acceptable for a demo?

## 10. Change log — verification pass findings (v0.1 → v0.2)

Applied from a 13-round Gemini SRS review:

1. Verification-bypass loophole: new requests matching an already-verified Event no longer auto-inherit verified status (`pending_addition` state, FR-304b, FR-502's "Approve All Pending").
2. LLM/embedding failure would crash the sort formula (`null × int`): pending items now render in a dedicated Needs Manual Triage section instead of participating in the numeric sort (NFR-103, FR-401).
3. Standalone requests previously bypassed verification entirely and dropped straight into the Dispatch Queue: unified Intake & Verification Inbox now covers both candidate Events and standalone requests; Dispatch Queue is verified-only (FR-401, FR-403, FR-505).
4. The multiplicative `urgency × device_count` (and `urgency × event_confidence`) formulas let volume/confidence overpower severity: replaced with a lexicographic sort (urgency primary, distinct-device-count secondary) and `event_confidence` removed as a variable entirely (FR-401, FR-403, §6).
5. Geofencing against individual prior requests allowed unbounded spatial "chaining" of a single Event across a city: geofencing and cluster membership now measured against an Event's `representative_location` (centroid) with a max-span bound (FR-202, FR-205).
6. No terminal "resolved" state existed, so the Dispatch Queue would grow forever: added `dispatched` status and an Archive/Resolved view (FR-502, FR-406, §6).
7. "Ban Device" either did nothing (flag-only) or was too blunt (hard block, harmful to shared devices in displacement settings): replaced with a Quarantine mechanism — flagged devices' submissions are accepted but withheld from active queues, with bulk-reject and individual rescue (FR-308, FR-407, FR-503).
8. The 48-hour dedup window caused long-running emergencies to fragment into duplicate Events over multiple days: age limit now only applies to inactive/standalone candidates, not members of a still-active Event (FR-202).
9. No rule existed for a request matching multiple distinct existing Events: resolved via geometric filter first, then authority-based selection (`dispatched` > `verified` > `candidate`), never auto-merging, with a "Suggested Merge" UI indicator for excluded matches (FR-205, FR-205b).
10. LLMs can't reliably reason about proximity from raw lat/lng floats: backend now precomputes and injects explicit distances into the LLM prompt (FR-204).
11. "Split Out" could leave a 1-member Event that fell through UI logic (too small for an Incident Card, not flagged as standalone): Events now auto-dissolve at membership 1, reverting the sole member to `standalone` (FR-504b).
12. Seed/replay "reset" left orphaned audit-log references and stale device flags across demo runs: reset mode now performs a full cascading wipe (FR-702).
13. Two of the above fixes (geometric bound + authority-based routing) interacted to produce false-negative merges: sequencing fixed so the geometric filter runs before authority selection, not after (FR-205, folds in Finding 9).
