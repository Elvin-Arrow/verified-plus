# Architecture Specification — Aid Request Triage & Trust Tool

Version 0.1 · Sits above `docs/design.md` (module/algorithm level) and below `docs/idea.md` (pitch level). This document owns the *system-level* decisions: process topology, deployment, runtime characteristics, integration points, and the sequence-level view of how components talk to each other. Module boundaries and pseudocode live in `docs/design.md`; this doc explains why the system is shaped the way it is and how it actually runs.

## 1. System context

```
                    ┌───────────────────────────────────────────────┐
                    │                  End users                     │
                    │  (aid requesters — public, anonymous)          │
                    └──────────────────────┬──────────────────────────┘
                                            │ HTTPS (public intake form)
                                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          This system (single deployable)                  │
│                                                                            │
│   ┌────────────┐        ┌───────────────────────┐        ┌────────────┐  │
│   │Intake Form │──POST──▶│   FastAPI backend     │◀─poll──│ Coordinator│  │
│   │(public SPA)│        │  (see docs/design.md)  │        │ Dashboard  │  │
│   └────────────┘        └───────────┬────────────┘        └────────────┘  │
│                                       │                                    │
│                          ┌────────────▼────────────┐                      │
│                          │   InMemoryStore (single   │                      │
│                          │  process, one lock)       │                      │
│                          └────────────────────────────┘                      │
└──────────────────────────────────────┬───────────────────────────────────┘
                                        │ HTTPS (outbound)
                                        ▼
                          ┌────────────────────────────┐
                          │  Hosted LLM provider API     │
                          │  (embeddings + chat)          │
                          └────────────────────────────┘

Out of system boundary (not built, not integrated — spec.md §8):
  HELM / LINK / Platforma-class logistics tools (conceptual handoff only, no live API call)
```

The system has exactly **one external runtime dependency**: the hosted LLM provider. Everything else — storage, both frontends, routing — is self-contained in one deployable, which is the load-bearing architectural decision behind almost every choice below.

## 2. Why a monolith, and what it costs

This is a **single-process monolith**, not a deliberate simplification made grudgingly — it's the correct shape at this system's actual scale (NFR-102: ≤1,000 requests, ≤50 concurrent Incident Cards, one coordinator persona expected live). The alternative (separate services for intake/matching/queue/etc., a real database, a message queue) buys nothing at this scale and costs:

- **Deployment risk** during a live demo — more moving pieces that can fail to start or fail to talk to each other.
- **Debugging time** during the build window — a stack trace in one process beats correlating logs across services.
- **No actual scaling need** — NFR-101/102 are both comfortably met by a single process with an in-memory store; there is no load pattern in scope that would saturate one machine.

What it explicitly does **not** support, on purpose (documented so it's a stated boundary, not a discovered one later): horizontal scaling, zero-downtime deploys, surviving a process crash without data loss, multiple coordinators safely acting concurrently on the same Event (spec.md §8 lists this as out of scope). None of these are requirements this system needs to satisfy.

## 3. Runtime topology

**Single process**, one FastAPI application, run with an ASGI server (e.g. `uvicorn`):

```
$ uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Serves the JSON API (`docs/api-spec.md`) under `/api/*`.
- The two frontends (Intake Form, Coordinator Dashboard — `docs/design.md` §6.1) are static builds, served either from the same process (mounted as static files) or a separate lightweight static host (Vite/CRA dev server locally, any static host for the demo) — architecturally irrelevant which, since they only ever talk to the backend over the public `/api/*` contract, never anything internal.
- No reverse proxy, no load balancer, no container orchestration required. A single machine (a laptop, for the demo) is a complete deployment.

**Environment configuration** (the only required runtime inputs):

| Variable | Purpose |
|---|---|
| `LLM_API_KEY` | Auth for the hosted embedding + chat provider (§5). |
| `LLM_MODEL` / `EMBEDDING_MODEL` | Model identifiers — kept configurable, not hardcoded, so a provider/model swap doesn't touch code (`docs/spec.md` §3 lists these as an assumption, not a requirement — swapping providers is explicitly cheap by design). |
| `PORT` | Defaults to `8000`. |

No database connection string, no secrets beyond the LLM key — a direct consequence of the in-memory store decision (§4).

## 4. State & persistence

**All state is process memory** (`InMemoryStore`, `docs/design.md` §3). This means:

- **Restart = full data loss.** Acceptable and intended: FR-702's "reset" seed/replay mode is the *designed* way to clear state between demo runs — a process restart is just a heavier-handed version of the same reset, not a failure mode to guard against.
- **No migrations, no schema versioning, no backup/restore.** `docs/data-model.md` is the schema; there's no database to keep it in sync with.
- **Single point of write serialization**: one `threading.Lock` around every store mutation (`docs/design.md` §3, §6.4). This is a correctness mechanism, not a performance one — at this scale, lock hold time is dominated by dict operations measured in microseconds, never by the (already-outside-the-lock) LLM call. See §6.4 of `docs/design.md` for why the lock is acquired only after the slow I/O completes.

**Why not even SQLite-on-disk for cheap durability?** Considered and rejected: it would add a schema-migration concern and a file-locking concern for zero benefit within this system's actual lifetime (a demo session), while the reset-on-seed workflow (FR-702) already assumes and depends on state being freely wipeable. Durability is explicitly not a requirement here.

## 5. External integration: the LLM provider

**One integration point**, wrapped behind `app/llm/client.py` (`docs/design.md` §2) with exactly two operations:

```
embed(text: str) -> list[float]
complete(prompt: str, schema: PydanticModel) -> schema_instance
```

- **Called once per submission** (`docs/design.md` §4.1) — one embedding call, one chat-completion call returning the combined urgency+match-judgment JSON (`docs/design.md` §5.1). This single-call-per-submission design is itself an architectural constraint that keeps NFR-101's 5-second budget achievable: no submission ever triggers more than 2 outbound network calls, regardless of how many candidates it's compared against (the candidates are batched into one prompt, not one call each — `docs/spec.md` FR-204).
- **Failure isolation is architectural, not incidental**: a failed `embed()` or `complete()` call is caught before any store mutation happens (`docs/design.md` §4.1's `try/except` wraps steps 5 only, not step 6's clustering) — this is what makes NFR-103 achievable as a clean boundary rather than a scattered set of null-checks throughout the clustering/scoring logic.
- **No retry logic in this version.** A failed call surfaces immediately as a pending/`null` state (NFR-103) rather than retrying — retries would blow the 5-second latency budget (NFR-101) unpredictably; a coordinator manually re-triggering (or the request simply sitting in Needs Manual Triage until overridden, FR-603) is the chosen failure-handling strategy, not silent automatic retry.
- **Swap cost**: changing LLM provider or model touches `llm/client.py` and the two env vars in §3 — never `services/`, `routers/`, or any business logic, because every caller depends on the `embed`/`complete` function signatures, not the provider's SDK shape directly.

## 6. Key flow sequences

### 6.1 Submission → clustering (happy path)

```
Requester        Intake Form        Backend                    LLM Provider       Store
   │                  │                 │                            │              │
   │  fill form        │                 │                            │              │
   ├──────────────────▶│                 │                            │              │
   │                  │  POST /requests │                            │              │
   │                  ├────────────────▶│                            │              │
   │                  │                 │  embed(need_description)   │              │
   │                  │                 ├───────────────────────────▶│              │
   │                  │                 │◀───────────────────────────┤              │
   │                  │                 │  vector                    │              │
   │                  │                 │                            │              │
   │                  │                 │  geofence + cosine top-5    │              │
   │                  │                 │  (in-process, no I/O) ─────────────────────▶│ read
   │                  │                 │◀─────────────────────────────────────────────┤
   │                  │                 │  candidates                │              │
   │                  │                 │  complete(prompt+candidates)│              │
   │                  │                 ├───────────────────────────▶│              │
   │                  │                 │◀───────────────────────────┤              │
   │                  │                 │  {urgency, matches}        │              │
   │                  │                 │  assign() — acquire lock,   │              │
   │                  │                 │  mutate, release ──────────────────────────▶│ write
   │                  │  201 Created    │                            │              │
   │                  │◀────────────────┤                            │              │
   │◀──────────────────┤                 │                            │              │
```

Note the lock is acquired only for the final in-memory mutation — both outbound LLM calls happen unlocked, so a slow LLM response never blocks other requests' reads or the coordinator dashboard's polling (`docs/design.md` §6.4).

### 6.2 Coordinator action (e.g. "Reject & Flag Device")

```
Coordinator      Dashboard          Backend                Store
    │                │                 │                     │
    │  click action   │                 │                     │
    ├───────────────▶│                 │                     │
    │                │ disable button   │                     │
    │                │ (optimistic UI, │                     │
    │                │  design.md §6.2)│                     │
    │                │ POST .../reject-and-flag                │
    │                ├────────────────▶│  acquire lock         │
    │                │                 ├──────────────────────▶│
    │                │                 │  mutate: flag device,  │
    │                │                 │  reject card's group,  │
    │                │                 │  sweep other requests, │
    │                │                 │  maybe dissolve Event  │
    │                │                 │  log_action()          │
    │                │                 │  release lock          │
    │                │                 │◀──────────────────────┤
    │                │  200 OK          │                     │
    │                │◀────────────────┤                     │
    │                │  immediate       │                     │
    │                │  re-fetch queues │                     │
    │                │  (not wait for   │                     │
    │                │  next poll tick) │                     │
    │◀───────────────┤                 │                     │
```

All coordinator actions follow this same shape — a single locked, synchronous, no-external-I/O mutation. This is why coordinator actions have no NFR-101-style latency budget of their own: they're bounded by dict operations, not network calls, and complete in low single-digit milliseconds regardless of store size at this scale.

### 6.3 Dashboard live-update loop

```
Dashboard                          Backend
    │                                 │
    │  GET /intake-inbox  ────────────▶│  (every 3s, IntakeVerificationInbox tab)
    │◀─────────────────────────────────┤
    │  GET /dispatch-queue ───────────▶│  (every 3s, DispatchQueue tab)
    │◀─────────────────────────────────┤
    │  GET /quarantine, /archive ─────▶│  (every 5s, lower-priority tabs)
    │◀─────────────────────────────────┤
```

Chosen over WebSockets/SSE deliberately (`docs/design.md` §6.2–6.3): at this scale and session length, polling is simpler to build, simpler to demo (no persistent-connection failure mode to worry about on stage), and the 3-second interval is imperceptibly different from push for a human coordinator's decision cadence. Mutations trigger an immediate targeted re-fetch (§6.2) rather than waiting for the next tick, so the "feels live" property doesn't depend on interval tuning.

## 7. Cross-cutting concerns

### 7.1 Error handling architecture

Two, and only two, failure categories reach the client (`docs/api-spec.md` §1.1–1.2):
1. **Client/request errors** (`400`/`404`/`409`) — synchronous, immediate, from validation or state-machine checks.
2. **LLM/embedding failures** — never surfaced as an HTTP error; absorbed into the domain model as a `null` urgency state (NFR-103). This is a deliberate architectural choice to keep "my dependency is flaky" from ever looking like "the user did something wrong."

A third category — unhandled server faults (`500`) — is treated as a bug, not a designed-for path; no circuit breaker, fallback provider, or graceful-degradation-beyond-NFR-103 exists for this version.

### 7.2 Observability

Minimal, matching hackathon scope: structured request logging (method, path, status, latency) at the ASGI layer, plus the `CoordinatorAction` audit log (`docs/data-model.md` §2.4) doubling as a functional/business-event log — every meaningful state change is already captured there for free, since FR-601 requires it for product reasons independent of observability. No metrics/tracing infrastructure (Prometheus, OpenTelemetry, etc.) is in scope; NFR-101's 5-second budget is verified by manual/test-suite timing (`docs/design.md`'s `tests/` layout), not live dashboards.

### 7.3 Security posture

Explicitly out of scope for this version (`docs/spec.md` §8): dashboard authentication, request-payload rate limiting, and CSRF/CORS hardening beyond permissive defaults needed for the two frontends to reach the API in a demo environment. NFR-201/202 (no PII, synthetic data only) are the only security-adjacent requirements actually in scope, and both are data-model decisions (`docs/data-model.md` §2.1's "not modeled" note), not runtime/network security ones. Deploying this beyond a demo would require revisiting this section specifically — it is a known, stated boundary, not an oversight.

### 7.4 Configuration vs. code

Two knobs are runtime-configurable without a redeploy (`docs/spec.md` FR-208): `geofence_radius_km`, `max_cluster_span_km`, set via `POST /api/seed/replay`'s `mode: "reset"` body. Everything else that might look like a tunable (the calibration buffer size N, poll intervals, the 48h dedup window, the 5-candidate top-k) is a documented constant in code, not exposed configuration — deliberately, since exposing every constant as a runtime parameter trades build-time simplicity for a flexibility this system has no requirement to offer.

## 8. Deployment view (demo-day)

```
Presenter's machine
├── backend process (uvicorn, :8000)
├── frontend static build (served by backend or a second local static server)
└── outbound HTTPS → LLM provider (requires network connectivity at demo time —
                                     the one external dependency with no offline fallback)
```

One machine, one process to start, one API key to have configured. The `POST /api/seed/replay` "Chaos Button" (`docs/spec.md` roadmap item 6) is what turns this static topology into a live-looking demo — see `docs/design.md` §4.8 for the reset semantics that make repeated demo runs safe.

## 9. Cross-references

| This document | Corresponds to |
|---|---|
| §2 Monolith rationale | `docs/design.md` §1 architecture overview |
| §3 Runtime topology | `docs/design.md` §2 module layout (what runs inside the one process) |
| §4 State & persistence | `docs/design.md` §3 `InMemoryStore`; `docs/data-model.md` §1 |
| §5 LLM integration | `docs/design.md` §5 LLM interface design; `docs/spec.md` §3 |
| §6 Sequences | `docs/design.md` §4.1–4.8 (the pseudocode these sequences narrate) |
| §7.1 Error handling | `docs/api-spec.md` §1.1–1.2 |
| §7.3 Security posture | `docs/spec.md` §8 Out of scope; NFR-201/202 |
