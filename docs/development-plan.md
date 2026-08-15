# Development Plan — Aid Request Triage & Trust Tool

Version 0.2 · Sequences the implementation of `docs/design.md` v0.5, `docs/api-spec.md` v0.2, `docs/data-model.md` v0.3, `docs/architecture.md` v0.1, `docs/testing-spec.md` v0.2, and `docs/ui-spec.md` v0.2 into small, independently-completable, test-first work items — a work breakdown structure (WBS), a dependency graph, and a phased roadmap with explicit parallel tracks. This document doesn't introduce new requirements or design decisions; every chunk below cites the document section it implements. (Hardened via a 9-document Gemini alignment pass — see §8.)

## 1. Chunking philosophy

Every chunk in §3 is sized to be:

- **A single TDD red-green-refactor unit or a tight cluster of them** — small enough that "write the failing test, make it pass" is a single sitting, not a multi-day effort. A chunk that would take more than ~1 day is a sign it should be split further (§3's chunks are already split to this grain; if implementation reveals one is still too big, split it again rather than let it run long).
- **Independently testable** — every chunk has a concrete test-level from `docs/testing-spec.md` §2's pyramid attached, and a chunk is not "done" until that test level passes, per `docs/testing-spec.md` §1's definition of done.
- **Traceable** — every chunk cites the FR/NFR(s) it implements and the design/data-model/api-spec/ui-spec section it follows, so there's never a question of "which document governs this code."
- **Ordered by actual dependency, not by document order** — the chunk order below follows what genuinely has to exist before what else can be built or tested, not the order topics happen to appear in `docs/design.md`.

Four tracks run through this plan, distinguished by prefix:

| Prefix | Track | Can generally proceed independently of |
|---|---|---|
| `BE-` | Backend (services, store, algorithms) | Frontend entirely |
| `FE-` | Frontend (both `/intake` and `/dashboard`) | Backend implementation, once `TI-01`'s API stub exists (§4) |
| `TI-` | Test infrastructure | — (feeds every other track) |
| `DA-` | Data/fixtures (seed batch, calibration/validation sets) | Everything except needing the intake API to exist for final seeding (`DA-01` can be *authored* anytime; *loading* it needs `BE-06`) |

## 2. Work breakdown structure

### 2.1 Test infrastructure (`TI-`)

| ID | Chunk | Implements | Depends on | Test level (`docs/testing-spec.md`) |
|---|---|---|---|---|
| `TI-01` | Pytest project skeleton + CI wiring (lint, unit, contract stages as separate jobs) | §8 (tooling), §1 (CI gate) | — | — (infra, not itself tested) |
| `TI-02` | LLM test double: fixture-keyed fake `embed`/`complete` + golden-response fixture set | §6.2 | `BE-01` (needs the `MatchResult`/response shape to fake) | Used by every backend test from `BE-04` onward |
| `TI-03` | `hypothesis` property-test scaffolding (strategies for `Location`, small request/Event graphs) | §4.4 | `BE-01` | Enables `BE-02`/`BE-03`/`BE-08`'s property tests |
| `TI-04` | `mutmut` config targeting the priority modules list | §5 | `BE-08`, `BE-09`, `BE-11` existing (config can be written earlier, but only meaningfully *run* once those modules exist) | CI gate, non-blocking until `BE-08` lands |
| `TI-05` | `schemathesis` contract-test harness against a generated OpenAPI doc | §3.2 | `BE-18` (needs real, fully-wired routes to point at) | Contract |

`TI-01` is the one true prerequisite for everything else in the plan — nothing in `BE-`/`FE-` starts before it exists.

### 2.2 Backend (`BE-`)

| ID | Chunk | Implements | Depends on | Test level |
|---|---|---|---|---|
| `BE-01` | Domain dataclasses/enums (`Request`, `Event`, `DeviceFingerprint`, `CoordinatorAction`, `Location`, `SessionConfig`) | `docs/data-model.md` §2 | `TI-01` | Unit (construction, defaults) |
| `BE-02` | `geo.py` — `haversine_km`, geofence radius filter | `docs/design.md` §4.2 (geometry primitives); FR-202 | `BE-01`, `TI-03` | Unit + property-based (§3.1, §4.4) |
| `BE-03` | `sort.py` — `sort_key`, `sorted_queue` | `docs/design.md` §4.3; FR-401/403 | `BE-01`, `TI-03` | Unit + property-based |
| `BE-04` | `InMemoryStore` (empty collections, single lock, `SessionConfig` instance) | `docs/design.md` §3, §6.4 | `BE-01` | Unit (concurrency test deferred to `BE-15`) |
| `BE-05` | `llm/client.py` interface (`embed`/`complete` signatures) wired to `TI-02`'s double in test config, a real provider SDK in prod config | `docs/architecture.md` §5 | `BE-01`, `TI-02` | Contract (double vs. real response shape match) |
| `BE-06` | `prompts.py` — FR-301 rubric embedded verbatim, FR-302 content-not-eloquence instruction, FR-604 calibration block (renders empty when buffers are empty) | `docs/design.md` §5.2 | `BE-05` | Unit — snapshot test against `docs/spec.md` §4.3's literal rubric text |
| `BE-07` | Intake pipeline: `POST /api/requests` handler minus clustering — validation (FR-101/102), device fingerprint lookup, FR-107 quarantine short-circuit, embed+complete call, NFR-103 failure isolation | `docs/design.md` §4.1 steps 1–5 | `BE-02`, `BE-04`, `BE-05`, `BE-06` | Contract (`docs/testing-spec.md` §3.2's two flagship cases: quarantine short-circuit, LLM-failure-returns-201) |
| `BE-08` | Matching service: `geofenced_candidates` (FR-202/208, active-Event age exemption), `top_k_cosine` (FR-203) | `docs/design.md` §4.1 step 5's candidate-gathering | `BE-02`, `BE-04` | Unit (§3.1's candidate-pool edge cases) |
| `BE-09` | **Clustering core**: `assign()` — geometric filter, authority selection, bootstrap, `_attach_to_event` | `docs/design.md` §4.2; FR-205 | `BE-03`, `BE-08` | State-machine (§4.1's `standalone→in_candidate_event`/`pending_addition` cases) + the Finding-13 regression (§4.3) + authority-selection-alone test (§6.1) — **highest mutation-testing priority** |
| `BE-10` | `detach_from_event` + `maybe_dissolve_event` | `docs/design.md` §4.4/§4.5; FR-504b | `BE-09` | State-machine (§4.3's dissolution invariants — the exact tests that would have caught `docs/data-model.md` §7 finding 8) |
| `BE-11` | `manual_merge` (FR-205c) + `store.suggested_merges` population with `distance_km` | `docs/design.md` §4.2 | `BE-09` | Integration (§6.1's manual-merge-bootstrap scenario) |
| `BE-12` | Verification actions: `verify_event`, `approve_pending`, `dispatch_event`, `reject_standalone`, `verify_standalone`, `dispatch_standalone` | `docs/design.md` §4.2b; FR-304/304b/502/505/505b | `BE-09` (not `BE-10` — none of these functions call `detach_from_event`/`maybe_dissolve_event`; they only set status/`verified` on Events and requests `assign()` already placed) | State-machine (§4.1's edges + the atomic-`verify_standalone` intermediate-state check) |
| `BE-13` | `split_out`, `rescue`, `dismiss_cluster` | `docs/design.md` §4.5b/§4.6; FR-504/407/507 | `BE-10` | State-machine (§4.1's three "retreat to standalone" cases) |
| `BE-14` | Device/quarantine: `reject_and_flag_device`, `reject_all_quarantined` | `docs/design.md` §4.4; FR-503/306/308/407 | `BE-10` | Integration (§6.1's fraud-cluster scenario) — second mutation-testing priority |
| `BE-15` | Feedback/calibration: `record_urgency_override` (with the first-override-only guard), `record_duplicate_correction`, N=5 eviction, wiring both buffers into `BE-06`'s prompt assembly | `docs/design.md` §4.7; FR-603/604/605 | `BE-06`, `BE-01` | Calibration buffer tests (§4.5) — third mutation-testing priority |
| `BE-16` | Queue assembly: `GET /api/intake-inbox`, `GET /api/dispatch-queue`, `GET /api/quarantine`, `GET /api/archive` read models | `docs/api-spec.md` §3 | `BE-03`, `BE-12`, `BE-13`, `BE-14` | Contract + the two-assertion sort test (§6.1) |
| `BE-17` | Detail reads: `GET /api/requests/{id}`, `GET /api/events/{id}` | `docs/api-spec.md` §7 | `BE-16` | Contract |
| `BE-18` | Full router wiring — every endpoint in `docs/api-spec.md` §8's index bound to its service function, error envelope (§1.1) applied uniformly | `docs/api-spec.md` (all) | `BE-07`, `BE-11`–`BE-17` | Contract (`TI-05` runs here) |
| `BE-19` | Seed/replay: `replay()` incl. the full cascading wipe (incl. `suggested_merges`, per `docs/spec.md` FR-702) | `docs/design.md` §4.8; FR-701/702/208 | `BE-18` (must submit through the live route) | Integration (§6.1's seed/replay-reset scenario) |
| `BE-20` | Concurrency correctness test (N concurrent submissions, invariants hold) + NFR-101/102 load harness | `docs/testing-spec.md` §8 | `BE-18` | Non-functional |

### 2.3 Frontend (`FE-`)

| ID | Chunk | Implements | Depends on | Test level |
|---|---|---|---|---|
| `FE-01` | App scaffolding: routing shell (`/intake`, `/dashboard/*`), API client module matching `docs/api-spec.md` exactly, `TI-01`'s equivalent frontend test setup | `docs/design.md` §6.1 | `TI-01` | — |
| `FE-02` | API client built/tested against **`BE-18`'s documented contract, not a live server** — a local mock server (e.g. `schemathesis`'s stub mode, or a hand-rolled fixture server serving `docs/api-spec.md`'s example JSON) stands in until real integration | `docs/api-spec.md` (all) | `FE-01` | Contract-mocked |
| `FE-03` | `/intake` form: location capture, description, photo, device fingerprint generation, all four states from `docs/ui-spec.md` §3 | `docs/ui-spec.md` §3 | `FE-02` | Component/unit |
| `FE-04` | Dashboard chrome: tab bar, `/dashboard` shell | `docs/ui-spec.md` §4 | `FE-02` | Component |
| `FE-05` | Severity color/badge system (§9), shared across every list view | `docs/ui-spec.md` §9 | `FE-01` | Component (visual regression optional) |
| `FE-06` | Standalone row + Needs Manual Triage item (§5.0/§5.2) — the simpler of the two list-item types, built first | `docs/ui-spec.md` §5.0, §5.2 | `FE-04`, `FE-05` | Component |
| `FE-07` | Incident Card component: collapse/expand, device grouping, all card-level and per-device actions, Suggested Merge affordance | `docs/ui-spec.md` §5.1 | `FE-06` (shares list-row conventions) | Component |
| `FE-08` | Intake & Verification Inbox view (assembles `FE-06`+`FE-07`) | `docs/ui-spec.md` §5 | `FE-07` | Component + (later) acceptance |
| `FE-09` | Dispatch Queue view (reuses `FE-07`, adds pending-additions sub-section, `Dispatch` vs. `Verify & Dispatch` label distinction) | `docs/ui-spec.md` §6 | `FE-07` | Component |
| `FE-10` | Quarantine Inbox view | `docs/ui-spec.md` §7 | `FE-04` | Component |
| `FE-11` | Archive view (read-only) | `docs/ui-spec.md` §8 | `FE-04` | Component |
| `FE-12` | Request/Event detail view incl. Override Urgency form (with the null-vs-existing-score default logic) and Merge confirmation modal | `docs/ui-spec.md` §10 | `FE-05`, `FE-02` | Component |
| `FE-13` | Loading/error state handling (poll-tick indicator, action-in-flight disable, 404/409 stale-view toast, 500 banner) — applied across `FE-08`–`FE-11` | `docs/ui-spec.md` §11 | `FE-08`–`FE-11` | Component |
| `FE-14` | Seed/Replay control | `docs/ui-spec.md` §12 | `FE-04` | Component |
| `FE-15` | Accessibility pass: keyboard nav order, `aria-label`s, color-pairing audit across every prior `FE-` chunk | `docs/ui-spec.md` §13 | `FE-08`–`FE-14` | Manual + automated (axe or equivalent) |
| `FE-16` | Swap `FE-02`'s mock server for the real `BE-18` backend; fix whatever the mock didn't catch | — (integration checkpoint) | `FE-15`, `BE-18` | Integration |

### 2.4 Data/fixtures (`DA-`)

| ID | Chunk | Implements | Depends on | Test level |
|---|---|---|---|---|
| `DA-01` | Author the ~50-request seed batch: HumAID/CrisisNLP rewrite pipeline (`docs/idea.md` §Data strategy), incl. multi-device genuine clusters and one seeded fraud cluster | `docs/spec.md` FR-701 | — (pure content authoring, no code dependency) | — |
| `DA-02` | Author the small held-out human-labeled validation set (non-circular dedup metric) | `docs/spec.md` §Data strategy, honest-limitation note | — | — |
| `DA-03` | Load `DA-01` into `BE-19`'s replay fixture format | `docs/design.md` §4.8 | `BE-19`, `DA-01` | Integration (this *is* the seed/replay test's data) |

## 3. Dependency graph

```
TI-01 ──┬──────────────────────────────────────────────────────────────┐
        │                                                                │
        ▼                                                                ▼
      BE-01                                                            FE-01
        │                                                                │
   ┌────┼────────┬─────────┐                                            ▼
   ▼    ▼        ▼         ▼                                          FE-02 ◀── (BE-18's documented
 BE-02 BE-03   BE-04    BE-05──BE-06                                    │         contract, not the
   │    │        │         │      │                                     │         live server)
   │    │        └────┬────┘      │                                     ▼
   │    │             ▼           ▼                                   FE-03  FE-04──FE-05
   │    │           BE-07       BE-15 ◀───────────────────┐             │       │      │
   │    │                                                   │            (indep) FE-06◀─┘
   └────┴──────┐                                            │                    │
                ▼                                            │                    ▼
              BE-08                                          │                  FE-07
                │                                             │                 ┌──┴──┐
                ▼                                             │                 ▼     ▼
              BE-09 ◀── (also needs BE-03)                    │               FE-08  FE-09
                │                                              │                 │     │
        ┌───────┼───────────────┐                              │                 └──┬──┘
        ▼       ▼                ▼                              │                    ▼
      BE-11   BE-12            BE-10                             │                  FE-13 ◀── (also needs
        │       │                │                                 │                          FE-10, FE-11 —
        │       │        ┌───────┼───────┐                          │                          see below)
        │       │        ▼       ▼        ▼                          │            FE-10 FE-11 FE-12 FE-14
        │       │      BE-13   BE-14   (feeds BE-16              │                  │     │     │     │
        │       │        │       │      directly)                 │                  └──┬──┴──┬──┴─────┘
        │       │        │       │                                 │                     ▼    (all feed FE-13
        │       └────────┼───────┼─────────────────────┐            │                   FE-15   and/or FE-15 —
        └────────────────┼───────┼─────────────┐        │             │                    │    see WBS for
                          ▼       ▼              ▼        ▼             │                    ▼    exact set)
                        BE-16 (needs BE-03,12,13,14) ── BE-17            │                  FE-16
                                    │                                    │                    ▲
                                    ▼                                    │                    │
                                  BE-18 ◀──────────────────────────────────── (contract, join point)
                                    │
                        ┌──────────┼──────────────┐
                        ▼          ▼               ▼
                     BE-19       BE-20          TI-05
                        │
                     DA-03 (needs DA-01)

  TI-04 (mutmut config): authorable anytime after TI-01; first meaningful RUN gated on BE-09 and
  BE-14/BE-15 existing (the priority modules) — not drawn as a graph node since it has no code
  dependency, only a "there must be something to mutate" one.
```

The three things worth naming explicitly from this graph:

- **`BE-09` (clustering core) is the narrowest point in the whole graph, but `BE-10` (dissolution) is a narrower *sub*-bottleneck than the original draft of this document claimed.** `BE-11` (manual merge) and `BE-12` (verification actions, including the `dispatch_event`/`reject_standalone` functions `docs/design.md` §4.2b was missing until this pass added them) only call `_attach_to_event`/set status flags — neither touches `detach_from_event`/`maybe_dissolve_event`, so both can proceed the moment `BE-09` lands, in parallel with `BE-10` itself, not queued behind it. Only `BE-13` (Split Out, Rescue — both call `detach_from_event`) and `BE-14` (device/quarantine sweep, same) genuinely need `BE-10`.
- **`FE-` and `BE-` are genuinely parallel tracks after `TI-01`**, not sequential ones — `FE-02`'s mock-server approach means the entire frontend (`FE-03` through `FE-15`) can be built and component-tested against `docs/api-spec.md`'s already-frozen contract without waiting on a single line of backend code. The only true cross-track dependency is `FE-16`, the final integration swap.
- **The `FE-` track has its own real internal sequencing**, not the flat "everything in Phase 2 is parallel" picture the original draft implied: `FE-06` (standalone row conventions) → `FE-07` (Incident Card, reuses those conventions) → `FE-08`/`FE-09` (the two views assembling `FE-07`) → `FE-13` (loading/error states layered across `FE-08`, `FE-09`, `FE-10`, `FE-11`) is a real chain. `FE-10`, `FE-11`, `FE-12`, `FE-14` are the genuinely-parallel-with-each-other subset, since none of them depend on one another — but none of them are parallel with `FE-06`→`FE-07`→`FE-08`/`FE-09`, which must come first.

## 4. Phased roadmap

| Phase | Chunks | Parallelizable within phase? | Gate to next phase |
|---|---|---|---|
| **0 — Foundations** | `TI-01`, `TI-02`, `TI-03`, `BE-01`–`BE-06`, `FE-01`, `FE-02`, `FE-04`, `FE-05`, `DA-01`, `DA-02` | Yes — this phase is almost entirely independent utility/scaffolding work; a team of 3+ could split `BE-0x`, `FE-0x`, and `DA-0x` across people with zero coordination needed until Phase 1 | `BE-01`–`BE-06` all pass unit tests; `FE-02`'s mock server responds to every documented endpoint |
| **1 — Core pipeline** | `BE-07`, `BE-08`, `BE-09`, `BE-10` | Partially — `BE-07` (intake) and `BE-08` (matching) can proceed in parallel, but `BE-09` needs `BE-08` and `BE-10` needs `BE-09` (the narrow point from §3) | `BE-10`'s state-machine and dissolution-invariant tests (`docs/testing-spec.md` §4.3) all green — **this is the highest-risk gate in the whole plan; do not proceed past it on a red or skipped test** |
| **2 — Actions & queues** | `BE-11`, `BE-12`, `BE-13`, `BE-14`, `BE-15`, `BE-16`, `BE-17`, `TI-04` (first meaningful run, against `BE-09`/`BE-14`/`BE-15`) (backend) **concurrently with** `FE-03`, `FE-06`, `FE-07`, `FE-08`, `FE-09`, `FE-10`, `FE-11`, `FE-12`, `FE-13`, `FE-14` (frontend, against `FE-02`'s mock) | Within `BE-`: `BE-11` and `BE-12` can start the moment `BE-09` lands, in parallel with `BE-10` itself; `BE-13` and `BE-14` need `BE-10` specifically (§3's correction — not all four chunks share one dependency). Within `FE-`: `FE-06`→`FE-07`→`FE-08`/`FE-09`→`FE-13` is a real sequential chain (§3); `FE-10`/`FE-11`/`FE-12`/`FE-14` are the genuinely-parallel subset, and none of them are parallel with the `FE-06`→`FE-09` chain that must precede them | Backend: `BE-17` done, mutation score on `BE-09`/`BE-14`/`BE-15` meets `docs/testing-spec.md` §5's 85% threshold. Frontend: `FE-14` done, `FE-13` states wired |
| **3 — Wiring & integration** | `BE-18`, `TI-05`, `FE-15`, `FE-16` | `BE-18`+`TI-05` and `FE-15` can run in parallel; `FE-16` is the join point and must come last | `TI-05`'s full contract suite green against `BE-18`; `FE-16` shows every dashboard tab working against the real backend |
| **4 — Demo readiness** | `BE-19`, `BE-20`, `DA-03`, the full `docs/testing-spec.md` §7 acceptance suite | `BE-19`+`DA-03` and `BE-20` can run in parallel | Every acceptance scenario in `docs/testing-spec.md` §7 passes end-to-end; a live seed/replay reset demo dry-run is clean |

## 5. Critical path

The longest true dependency chain, ignoring parallel opportunity:

```
TI-01 → BE-01 → BE-02 → BE-08 → BE-09 → BE-10 → BE-14 → BE-16 → BE-17 → BE-18 → BE-19 → DA-03
                          ▲
                  BE-03 also required here (branches off BE-01 in parallel with BE-02;
                  shorter than the BE-02→BE-08 branch, so it does not itself extend the
                  chain — but it's a real prerequisite for BE-09, not an omittable detail)
```

12 chunks deep (`BE-03` sits alongside `BE-02` rather than adding a 13th link, per the note above). Everything else in the plan either feeds into this chain (`TI-02`/`TI-03`, `BE-04`–`BE-07`, `BE-15`) or hangs off it without extending it (`BE-11`/`BE-12`, which only need `BE-09`, not `BE-10`; `BE-13`, which does need `BE-10` but is shorter than the `BE-14` branch; the entire `FE-` track, gated only at the very end by `FE-16`). Practically: **the fastest path to a demoable system is keeping this specific chain moving**, and any spare capacity (a second engineer, a subagent) is best spent either (a) advancing `FE-` in parallel, since it's not on the critical path at all until `FE-16`, or (b) pulling `BE-11`/`BE-12` onto the critical path's shoulders the moment `BE-09` lands — one step earlier than the original version of this plan allowed, since they don't actually need `BE-10` (§3's correction) — or (c) `BE-13`/`BE-15` the moment `BE-10`/`BE-06` respectively land.

## 6. Risk notes

- **`BE-09`/`BE-10` risk is already well-understood, not speculative**: every state-machine bug found across the `docs/data-model.md` §7 and `docs/spec.md` §10/§11 alignment passes lived in exactly this code. Budget more review time here than the chunk's nominal size would suggest, and do not relax the state-machine test requirement from `docs/testing-spec.md` §1's definition of done to "save time" — that's precisely the shortcut that produced the bugs those passes had to catch by hand.
- **The LLM provider (`BE-05`) is the one external dependency** (`docs/architecture.md` §5) — `TI-02`'s double is what keeps it off the critical path for everything except the one scheduled live smoke test (`docs/testing-spec.md` §6.3). Confirm API key/quota access during Phase 0, not Phase 4, so a provider-access problem surfaces when there's still slack to fix it.
- **`FE-02`'s mock-server approach only works if `docs/api-spec.md` stays frozen** during Phases 1–2. If backend implementation reveals a genuine need to change a response shape (as opposed to a bug in the implementation), that change must be reflected in `docs/api-spec.md` first and treated as a mini alignment-pass, not patched silently in `BE-18` while `FE-` code still expects the old shape.
- **`DA-01`/`DA-02` have zero code dependency and can slip to the last responsible moment** without blocking anything except `DA-03`/`BE-19`'s own tests and the final demo rehearsal — but "last responsible moment" is still before Phase 4, since a bad seed batch (e.g. a fraud cluster that doesn't actually exercise `BE-14`'s dissolution path) would only be discovered there, too late to comfortably fix.

## 7. Cross-references

| This document | Corresponds to |
|---|---|
| §2.1 Test infrastructure | `docs/testing-spec.md` §5, §6.2, §8, §10 |
| §2.2 Backend WBS | `docs/design.md` §2, §4; `docs/api-spec.md` (all); `docs/spec.md` FR-1xx–7xx |
| §2.3 Frontend WBS | `docs/ui-spec.md` (all); `docs/design.md` §6 |
| §2.4 Data/fixtures | `docs/spec.md` §Data strategy; FR-701 |
| §3 Dependency graph | `docs/testing-spec.md` §5's mutation-priority ordering (cross-validated, same modules) |
| §6 Risk notes | `docs/data-model.md` §7, `docs/spec.md` §10–11, `docs/ui-spec.md` §15 (the alignment-pass change logs this plan's risk assessment is drawn from) |

## 8. Change log — 9-document alignment pass (v0.1 → v0.2)

A Gemini review checking this plan against all eight prior project documents found:

1. **A genuine upstream gap in `docs/design.md`, not just this plan**: `dispatch_event` (FR-502's Incident Card "Approve" action, backing `POST /api/events/{id}/dispatch`) and `reject_standalone` (FR-505, backing `POST /api/requests/{id}/reject-standalone`) were both already documented in `docs/api-spec.md` but had no pseudocode anywhere in `docs/design.md` §4.2b — meaning this plan's `BE-12` chunk was, correctly, working from an incomplete function list, because the function list it was working from was incomplete. Fixed in `docs/design.md` first (both functions added), then reflected here.
2. **A false `BE-10` bottleneck**: the original WBS listed `BE-12` (verification actions) as depending on `BE-10` (dissolution). Neither `verify_event`, `approve_pending`, `dispatch_event`, `reject_standalone`, `verify_standalone`, nor `dispatch_standalone` call `detach_from_event`/`maybe_dissolve_event` — only `BE-13` and `BE-14` genuinely need `BE-10`. Fixed in the WBS table, the dependency graph, the Phase 2 row, and the critical-path narrative, all four of which had independently propagated the same wrong assumption.
3. **Internal contradictions between the WBS table and the graph/prose**: `BE-11`'s graph edge and Phase 2 text said `BE-10` where the WBS table correctly said `BE-09`; `TI-05`'s WBS table said `BE-14` where the graph correctly said `BE-18`. Both reconciled to the correct value in every location.
4. **Missing chunks**: `TI-04` and `FE-13` were both defined in the WBS but absent from the dependency graph and/or the phased roadmap. Added to both.
5. **A graph rendering bug**: a self-referential `FE-13 ◀── FE-13` arrow, and `FE-10`/`FE-11` routed around `FE-13` instead of into it. Redrawn.
6. **An oversold parallelization claim**: Phase 2's frontend row implied `FE-06` through `FE-14` were all mutually parallel. In reality `FE-06 → FE-07 → FE-08`/`FE-09 → FE-13` is a real sequential chain (each stage's components are built from the previous stage's), and only `FE-10`/`FE-11`/`FE-12`/`FE-14` are genuinely independent of each other. Corrected in §3 and the Phase 2 row.
7. **A critical-path omission**: the stated chain skipped `BE-03` (`sort.py`), which `BE-09` genuinely depends on per the WBS table. Added as an annotated parallel branch (it doesn't extend the chain's length, but omitting it entirely was still wrong).
