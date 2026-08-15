# Testing Specification — Aid Request Triage & Trust Tool

Version 0.1 · Implements `docs/spec.md` v0.3, `docs/design.md` v0.3, `docs/data-model.md` v0.2, `docs/api-spec.md` v0.1, `docs/architecture.md` v0.1. This document is the authoritative testing contract: what gets tested, at what level, with what tooling, to what bar — and, since the project builds test-first, what "done" means for a requirement before any implementation code for it is considered complete.

## 1. TDD approach and what "done" means

This project is built test-first: for any FR/NFR being implemented, the corresponding test(s) in §9's traceability matrix are written and observed failing *before* the implementation exists, then implementation is written only to the extent needed to pass them (red → green → refactor). This is a process commitment, not a tooling one — nothing here enforces it mechanically except code review discipline and the CI gate in §8, which can tell you tests exist and pass, not that they were written first. State that honestly rather than claim automated enforcement that doesn't exist.

**Definition of done for a requirement**, in order:
1. A failing test exists that encodes the requirement's acceptance criterion (§9).
2. Implementation makes it pass without weakening the test.
3. The mutation score for the touched module meets §5's threshold (a green test suite that a trivial mutant survives is not done).
4. For anything touching the state machines in `docs/data-model.md` §3, the specific transition/invariant tests in §4 pass, not just a happy-path test.

## 2. Test levels — the pyramid, and why it's shaped this way

```
                    ▲  fewer, slower
                    │
      E2E / Acceptance (§7)         — full HTTP stack, real store, LLM double
      ─────────────────────────
      Contract tests (§3)            — api-spec.md schema conformance
      ─────────────────────────
      Integration tests (§6)         — multi-service flows, real store, LLM double
      ─────────────────────────
      State-machine tests (§4)       — every transition + invariant in data-model.md §3
      ─────────────────────────
      Unit tests (§3) + Property-based (§4.4) + Mutation (§5)
                    │
                    ▼  many, fast
```

The heavy weighting toward the bottom three layers is deliberate: this system's actual risk is almost entirely in **stateful business logic** (cluster assignment ordering, dissolution, the verified/status split) rather than in I/O or infrastructure — the LLM call is a thin wrapper (`docs/architecture.md` §5), the store is a dict, the API layer is CRUD-shaped. Concentrating test investment where the bugs actually were (every one of `docs/data-model.md` §7's findings was a state-machine defect) is a direct response to what the alignment-review passes actually caught, not a generic pyramid cargo-culted in.

## 3. Unit and contract tests

### 3.1 Pure-function unit tests

No mocks needed — these are deterministic functions over plain data.

| Module | What to test | Key edge cases |
|---|---|---|
| `geo.py` (`haversine_km`) | Distance correctness against known reference pairs | Antipodal points, `0 km` (same point), the exact boundary values used elsewhere (1.0 km, 1.5 km) — off-by-epsilon at a boundary must round the same way the geofence filter does. |
| `sort.py` (`sort_key`, `sorted_queue`) | Lexicographic ordering, `needs_manual_triage` partitioning | All-null-urgency batch (everything triage), tie on `max_urgency_score` broken by `distinct_device_count`, a single-member item vs. a multi-member Event compared side by side, empty queue. |
| `prompts.py` (rubric/prompt assembly) | The FR-301 rubric table is embedded verbatim, not paraphrased; FR-604 calibration block renders only when buffers are non-empty | Snapshot test against the literal rubric text in `spec.md` §4.3 — a rubric edit in `spec.md` without a matching prompt-template update should fail this test, catching exactly the kind of doc/code drift the alignment passes have been finding by hand. |
| `matching_service` internals (`geofenced_candidates`, `top_k_cosine`) | Geofence filter correctness (FR-202: active-Event age exemption vs. 48h cutoff for standalone/inactive); top-5 selection and ordering | Candidate pool with 0/1/exactly-5/more-than-5 matches; a candidate belonging to a `dispatched` Event just past 48h old (must still be included, per FR-202). |

### 3.2 Contract tests (API schema conformance)

Every endpoint in `docs/api-spec.md` §8's index gets a contract test asserting: request validation matches §1.3's field constraints, response shape matches the documented JSON exactly (field names, types, nullability), and every documented error code (§1.1) is actually reachable and correctly shaped. Tooling: `schemathesis` (or equivalent) driven off a generated OpenAPI document, supplemented by hand-written cases for the state-dependent 409s that a schema-only tool can't derive (e.g. "verify an already-verified Event" requires seeded state, not just a malformed request).

**Explicit contract cases worth calling out** (each is a documented API behavior that's easy to implement wrong):
- `POST /api/requests` from a flagged device returns `201`, not an error, with `status: "quarantined"` and every pipeline field `null` (api-spec.md §2).
- `POST /api/requests` on LLM failure returns `201`, not `500` (§1.2's asymmetry — this is the single most important contract test in the suite, since getting it wrong means a flaky third-party dependency starts looking like the API's own fault).
- `POST /api/events/{id}/devices/{device_id}/reject-and-flag` returns `event: null` + `event_dissolved: true` when dissolution occurs, not a stale/partial Event object.
- `POST /api/requests/{id}/merge` with both `target_event_id` and `target_request_id` set (or neither) → `400`, not a silent pick-one.

## 4. State-machine and invariant tests

This is the highest-value layer given §2's rationale — every transition diagram in `docs/data-model.md` §3 becomes a table of test cases, and every invariant becomes a property test that tries to break it, not just confirm the happy path.

### 4.1 `Request.status` transition tests (data-model.md §3.1)

One test per **edge** in the diagram, plus one test per **illegal** transition attempted from the wrong source state (asserting `409 INVALID_STATE_TRANSITION`, not that it silently succeeds or crashes):

- `standalone → in_candidate_event` (bootstrap, FR-205 step 5) and `standalone → in_candidate_event` (join existing candidate, step 4) — both paths, since they're different code paths (`assign()`'s bootstrap branch vs. `_attach_to_event`'s candidate branch) that happen to produce the same resulting status.
- `in_candidate_event → in_verified_event` (`verify_event`) — and the **negative** case: calling `verify_event` on an Event that's already `verified` → `409`.
- `pending_addition → in_verified_event` (`approve_pending`) — and: `approve_pending` on an Event with an empty `pending_member_request_ids` → `409` (per `docs/api-spec.md` §4).
- `in_verified_event → dispatched` (`approve_dispatch`).
- `standalone → dispatched` (`verify_standalone`, the atomic FR-505 path) — assert this happens in one call, never passing through an intermediate observable `verified=true, status=standalone` state (a test that submits, verifies, then immediately re-fetches should never see that intermediate — if the implementation ever *does* pass through it observably, that's the sign someone accidentally split `verify_standalone` into two operations).
- `standalone (verified=true) → dispatched` via `dispatch_standalone` (FR-505b) — and the negative case: calling it on a `standalone, verified=false` request → `409` (this is the case most likely to get accidentally merged with `verify_standalone` during implementation, since both end at the same place).
- `* → quarantined` (device flagged, sweep) from **every** non-terminal source status — `in_candidate_event`, `pending_addition`, `in_verified_event`, and `standalone` — as four separate test cases, not one generic "any active status," because the sweep's interaction with `detach_from_event` differs depending on whether the request was in `member_request_ids` or `pending_member_request_ids` (§4.3 below).
- `quarantined → standalone` (`rescue`) — assert `verified` resets to `false` and matching re-runs (per `docs/design.md` §4.5b) rather than restoring stale pre-quarantine state.
- `* → rejected` from `standalone` (`reject_standalone`) and from an Event member (`reject_flag_device`) — as separate cases, since only the latter also flags the device and populates `confirmed_fraud_request_ids`.

### 4.2 `Event.status` transition tests (data-model.md §3.2)

- `candidate → verified → dispatched`, asserting `verified_by`/`verified_at` are set exactly once, at the `candidate → verified` edge, never touched again by the `dispatch` call.
- `candidate → (deleted)` via `dismiss` — and the negative case: `dismiss` on a `verified` Event → `409` (FR-507 explicitly restricts this).
- `candidate/verified → (deleted)` via dissolution at 0–1 active members — see §4.3, this is the highest-risk transition in the whole system.

### 4.3 Dissolution and orphan-prevention invariant tests (data-model.md §3.4)

These are the tests that would have caught `docs/data-model.md` §7 finding 8 (the `reject_and_flag_device`/`maybe_dissolve_event` bug) — written first, they'd have failed against the buggy implementation immediately:

- **Invariant 1** ("no Event with ≤1 active member exists at rest"): after every mutating action in §4.1/4.2's tables that can reduce membership (`split_out`, `reject_and_flag_device`, `rescue`'s implicit detach, `dismiss_cluster`), assert `len(event.member_request_ids) >= 2` for every Event still present in the store — including a **specific regression test** that creates a 3-member Event, rejects two members belonging to different devices in two separate `reject_and_flag_device` calls, and asserts the Event is gone (not silently sitting at 1 member) after the second call.
- **Invariant 2** ("no `Request.event_id` points to a nonexistent Event"): after every dissolution-triggering action, iterate every `Request` in the store and assert `event_id is None or event_id in store.events`. This should run as a store-wide sanity check after *every* mutating test in this document (a shared test fixture/teardown assertion), not just the dissolution-specific ones — an invariant violated by a completely unrelated code path is still a violation.
- **Pending-member dissolution**: an Event with 1 active member and 2 `pending_addition` members dissolves correctly on the active member dropping out — assert all three affected requests end up `standalone` with correct `verified` values (the active one keeps whatever it had; the two pending ones become `verified=false`), not just the formerly-active one.
- **The Finding-13 regression** (`docs/spec.md` §10 #13): a request matching two Events — one `verified` but 1.6km away (geometrically excluded), one `candidate` and 0.5km away (geometrically valid) — must join the `candidate` Event, not get force-excluded by the far Event's authority ranking. This exact scenario, by name, as a permanent regression test.

### 4.4 Property-based tests

For the handful of functions where "try every documented edge case by hand" is weaker than "assert the invariant holds for randomly generated inputs":

- **Sort stability/correctness**: for any randomly generated set of (urgency, distinct_device_count) pairs, `sorted_queue`'s output is non-increasing on the `(urgency, device_count)` tuple, and every input item appears exactly once in the output (no duplication, no drop).
- **Geofence/centroid math**: for any three points where A and B are within `max_cluster_span_km` of each other's Events and C is not, adding C never gets silently accepted (the geometric filter in FR-205 step 1 correctly excludes it regardless of point configuration, not just the specific worked examples in `docs/design.md` §4.2).
- **Dissolution never orphans**: for a randomly generated Event with N members and M pending members, removing members one at a time down to 0 never leaves a dangling `event_id` at any intermediate step (a stronger, generative version of §4.3's invariant tests).

Tooling: `hypothesis` (Python) for the generative cases; the sort/geofence properties above are natural `hypothesis` strategies over floats/small lists.

## 5. Mutation testing

**Why it's here, explicitly, not just "high coverage"**: line/branch coverage measures that a test *executed* a piece of code, not that the test would *fail* if that code were wrong. Given this system's bug history so far is entirely "logic that looked right and had a green test around the happy path" (the `docs/data-model.md` §7 findings), coverage percentage is the wrong signal to optimize — mutation score is the one that actually correlates with "would we have caught this."

- **Tooling**: `mutmut` (or `cosmic-ray`) for Python, run against the `services/`, `geo.py`, and `sort.py` modules specifically (`docs/design.md` §2's module layout) — not the `routers/`/`llm/` layers, where mutations mostly produce trivially-equivalent or untestable-without-a-live-LLM mutants.
- **Target modules, in priority order** (matching where the real bugs actually were): `clustering_service.py` (`assign`, `_attach_to_event`, `manual_merge`, `maybe_dissolve_event`, `detach_from_event`), `device_service.py` (`reject_and_flag_device`), `queue_service.py` (`sorted_queue`), `feedback_service.py` (`record_urgency_override`'s `original_urgency_score` guard — the exact bug from `docs/data-model.md` §7 finding 6 is a one-line mutation, `if r.original_urgency_score is None` → unconditional, that a mutation run would flag immediately).
- **Threshold**: **≥85% mutation score** on the priority modules above before a PR touching them merges (§8); no fixed threshold enforced on lower-priority modules, but a mutation report is still generated and reviewed for anything glaring.
- **Explicitly excluded from mutation scoring**: `prompts.py` (mutating a prompt string produces a "different but not wrong" LLM behavior a unit test can't meaningfully assert against without a live call — covered instead by the snapshot test in §3.1 and the LLM contract tests in §6.2), and any dataclass/schema file with no branching logic (mutating a field default isn't a meaningful mutant).
- **Process**: mutation testing runs in CI (§8) on every PR touching a priority module, not on every commit — it's too slow for tight inner-loop TDD cycling; the fast red-green-refactor loop uses the regular unit/state-machine suite, and mutation testing is the pre-merge gate that catches "the tests all pass but wouldn't catch a plausible bug."

## 6. Integration tests

Multi-function, multi-service flows through a real (in-process) `InMemoryStore`, with the LLM layer replaced by a **test double**, not a live call (see §6.2 for why and how).

### 6.1 Core flow integration tests

- **Submit → cluster → verify → dispatch**: three requests submitted in sequence (LLM double configured to report the 2nd and 3rd as matching the 1st), assert a `candidate` Event forms at request 2 (bootstrap, FR-205 step 5), request 3 joins it as a third member, `verify_event` moves it to the Dispatch Queue, `approve_dispatch` moves it to the Archive — checking the *queue membership* at each step via `queue_service`, not just the entity's own `status` field, since a status can be individually correct while the queue-listing logic that reads it is wrong.
- **Submit → fraud cluster → reject-and-flag → quarantine sweep**: 4 requests from the same device, LLM double reports them all as mutually matching (bootstraps a 4-member Event), `reject_and_flag_device` on that device — assert: the Event dissolves entirely (4 members, all same device, all rejected), the device's `confirmed_fraud_request_ids` has all 4, and a 5th late-arriving request from the same device is auto-quarantined at intake (FR-107) without ever reaching the matching pipeline (assert the LLM double was never called for it).
- **Two-tier queue interaction**: an unverified 3-device cluster appears in the Intake Inbox sorted ahead of a 1-device cluster with higher raw urgency but lower device count only if the lexicographic rule is respected (i.e. this test is written to fail if someone "simplifies" the sort back to a multiplicative formula — a direct regression guard for `docs/spec.md` §10 finding 4).
- **Manual merge bootstrap**: two standalone requests, geofence radius configured (FR-208) larger than max-cluster-span so they're candidates but geometrically excluded from each other, assert a `suggested_merges` entry appears with the correct `distance_km`, then `POST .../merge` and assert a brand-new 2-member `candidate` Event is bootstrapped (not an error, not a no-op) — this is the FR-205c path the alignment pass added, and its own test is what would have caught it being unimplemented in the first place had TDD been followed strictly.
- **Seed/replay reset**: seed with `mode: "reset"`, perform some actions (verify an Event, flag a device), seed again with `mode: "reset"` — assert zero residual state: empty `actions` log, no flagged devices, no `suggested_merges`, no orphaned IDs referenced by the new batch (the exact scenario `docs/spec.md` §10 finding 12 fixed).

### 6.2 LLM integration — double strategy and a thin live contract test

- **Unit/integration test double**: a fake `embed`/`complete` implementation that returns pre-scripted responses keyed by input text, used throughout §3/§4/§6.1 — deterministic, fast, and lets every clustering/scoring test above be written without network access or LLM cost.
- **Golden-response fixtures**: a small fixed set of real (or realistically-shaped) LLM responses captured once and checked into the test fixtures directory, used to validate the double's contract matches what the real API actually returns — if the provider changes its response shape, this fixture set is what would need updating, and a mismatch here is a signal to check §6.3.
- **§6.3 — one real smoke test against the live LLM provider**, run in CI on a schedule (not per-PR, to avoid flaking the merge gate on third-party latency/cost) and manually before a demo: submit one real request through the full pipeline with a live API key, assert a response comes back with the expected shape and an `urgency_score` in range — this is the only place a live network call to the LLM provider happens in the entire test suite, and it exists specifically to catch "the provider changed something and our double is now lying to us."

## 7. Acceptance / end-to-end tests

Full HTTP stack (real router → service → store), LLM double, one scenario per acceptance criterion — these are the tests a demo dry-run effectively performs manually; codifying them means the dry-run isn't the first time a full scenario is exercised.

| Scenario | Traces to |
|---|---|
| A genuine mass-casualty event (many distinct devices, high urgency) reaches the top of the Intake Inbox and, once verified, the top of the Dispatch Queue. | FR-401, FR-403, `docs/spec.md` §10 finding 4 |
| A single-device paraphrase-spam flood does NOT reach the top of the Intake Inbox unattended. | FR-401's device-count sort key, `docs/spec.md` §10 finding 1/9 |
| A miscluster (two unrelated needs geofenced together) is fixed via Split Out without affecting the rest of the Incident Card. | FR-504 |
| A wrongly-formed cluster with no fraud involved is fixed via Dismiss Cluster, and the device(s) involved are NOT flagged. | FR-507 |
| A 500-ticket, 5-device spam flood on one Incident Card is cleared in 5 actions (one `reject-and-flag` per device group), not 500. | `docs/idea.md` UX note; NFR-401 |
| A shared device (one legitimate user's bad submission, followed by a different legitimate user on the same device) — the second user's request is quarantined, then rescued, and reaches the normal queue. | FR-308, FR-407, NFR-201's shared-device rationale |
| A coordinator overrides an urgency score twice; `original_urgency_score` still reflects the LLM's first output, not the intermediate correction. | FR-603, `docs/data-model.md` §7 finding 6 |
| A full seed/replay reset between two consecutive demo runs leaves no visible trace of the first run's state in any queue/archive/quarantine view. | FR-702 |
| An LLM outage during a submission does not return an error to the submitter, and the request is recoverable from Needs Manual Triage once the outage clears (simulated via the double toggling failure on/off). | NFR-103 |

## 8. Non-functional and performance tests

- **NFR-101 (latency)**: a load-test harness (e.g. `locust`, or a plain async benchmark script) submits requests at a steady rate against a store pre-populated to 1,000 requests (NFR-102's stated scale ceiling) and asserts p95 end-to-end submission latency (embed → geofence → cosine → LLM judgment) stays under 5 seconds using the LLM double configured with realistic (not zero) latency, not the live provider — this measures the system's own overhead, not the provider's response time, which is out of this system's control and shouldn't gate the build.
- **NFR-102 (scale)**: the same 1,000-request pre-population, plus a specific check that `GET /api/intake-inbox`/`GET /api/dispatch-queue` render (server-side sort + serialize) in well under a human-perceptible threshold (a few hundred ms) at that scale, confirming the "no UI degradation" claim isn't just asserted but measured.
- **Concurrency**: a test that fires N concurrent mutating requests (e.g. 20 simultaneous submissions near the same location) against the single-lock store (`docs/architecture.md` §4) and asserts the invariants in §4.3 still hold afterward — not a performance test so much as a correctness-under-concurrency test, verifying the coarse lock actually serializes safely rather than merely being present.

## 9. Traceability matrix

A condensed view — full detail lives in §3–7 above; this is the "did we cover every requirement" checklist.

| Requirement range | Primary test level(s) |
|---|---|
| FR-1xx Intake | Contract (§3.2), integration (§6.1) |
| FR-2xx Matching/geofence/merge | Unit (§3.1), property-based (§4.4), state-machine (§4.1), integration (§6.1) |
| FR-3xx Verification/device | State-machine (§4.1–4.3), integration (§6.1) |
| FR-4xx Queues | Unit (§3.1 sort), acceptance (§7) |
| FR-5xx Incident Cards/actions | State-machine (§4.1–4.3), mutation (§5), acceptance (§7) |
| FR-6xx Feedback loop | Unit (§3.1 prompt snapshot), state-machine (§4.1), mutation (§5 — `record_urgency_override`) |
| FR-7xx Demo support | Integration (§6.1 seed/replay), acceptance (§7) |
| NFR-101/102 Latency/scale | §8 |
| NFR-103 Resilience | Contract (§3.2), acceptance (§7), integration (§6.2 double) |
| NFR-201/202 Privacy/data | Data-model review (no automated test — a code-review checklist item: no new field on `Request`/`DeviceFingerprint` without checking it against `docs/data-model.md` §2.1's "Not modeled" list) |
| NFR-301/302 Explainability/auditability | Contract (§3.2 — reasoning strings never null on a successful response), integration (§6.1 audit log assertions) |
| NFR-401 Usability | Acceptance (§7 — the 5-clicks-not-500 scenario) |

## 10. Tooling summary

| Concern | Tool |
|---|---|
| Unit / state-machine / integration / acceptance | `pytest` |
| Property-based | `hypothesis` |
| Mutation testing | `mutmut` (or `cosmic-ray`) |
| API contract | `schemathesis` (schema-driven) + hand-written state-dependent cases |
| Load/latency | `locust` or a plain async benchmark script |
| LLM double | Hand-rolled fixture-keyed fake, no live network by default |

## 11. Cross-references

| This document | Corresponds to |
|---|---|
| §3.1 Unit tests | `docs/design.md` §2 module layout, §4 algorithms |
| §3.2 Contract tests | `docs/api-spec.md` (every section) |
| §4 State-machine tests | `docs/data-model.md` §3 (all subsections), §7 change log |
| §5 Mutation testing | `docs/design.md` §4.2–4.7 (the priority-module functions) |
| §6 Integration tests | `docs/design.md` §4.1–4.8; `docs/architecture.md` §6 sequence diagrams |
| §7 Acceptance tests | `docs/idea.md` (scenario language), `docs/spec.md` §10–11 change logs |
| §8 Non-functional tests | `docs/spec.md` NFR-101/102; `docs/architecture.md` §2, §4 |
