# Software Design Specification — Aid Request Triage & Trust Tool

Version 0.2 · Implements `docs/spec.md` v0.3 (post rubric, sanity-pass, and cross-document alignment pass — see spec.md §11). Every design decision below is traced to the requirement ID(s) it satisfies — search for "FR-"/"NFR-" to cross-reference.

## 1. Architecture overview

Single-process monolith, matching the hackathon scope in spec.md §3: one FastAPI backend, one in-memory store, one React dashboard. No microservices, no external DB, no message queue — deliberately, to keep NFR-101/102 achievable without infra risk.

```
┌─────────────────────┐        ┌───────────────────────────────────────────┐
│   Intake Form (web)  │──POST──▶                                          │
│  (public, no login)  │        │              FastAPI backend              │
└─────────────────────┘        │                                           │
                                │  routers/ → services/ → store (in-memory) │
┌─────────────────────┐        │                     │                     │
│ Coordinator Dashboard│◀─poll──┤                     ▼                     │
│      (React SPA)     │        │            llm/ (embedding + chat)       │
└─────────────────────┘        └───────────────────┬───────────────────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │  Hosted LLM API     │
                                          │  (embeddings + chat)│
                                          └──────────────────────┘
```

- **Intake Form** and **Coordinator Dashboard** are two separate frontend entry points sharing one API client, per spec.md §1 (public intake vs. coordinator-only views — FR-104 requires no login on intake, but nothing in scope requires the dashboard to be public).
- The dashboard polls (§6.3) rather than holding a websocket — simplest way to satisfy FR-405 ("update within bounded time... without manual reload") at hackathon scope.
- The **seed/replay script** (FR-701) is a backend-internal client of the same `POST /api/requests` route real submissions use — never a direct store write — enforced by routing it through `services/intake_service.py` like any other caller.

## 2. Backend module layout

```
backend/
  app/
    main.py                  # FastAPI app, router registration, CORS, startup config load
    config.py                # SessionConfig: geofence_radius_km, max_cluster_span_km (FR-208), calibration N (FR-604)
    models/
      domain.py               # dataclasses: Request, Event, DeviceFingerprint, CoordinatorAction (§6 mirror)
      schemas.py               # Pydantic request/response models for the API layer
    store/
      memory_store.py          # InMemoryStore: the single source of truth, thread-safe via one lock
    services/
      intake_service.py        # FR-101-107: validate + create Request, kick off matching
      matching_service.py      # FR-201-206, FR-208: embed, geofence, cosine top-5, LLM judge
      clustering_service.py    # FR-205, FR-205b, FR-304b, FR-504b: cluster assignment & dissolution
      scoring_service.py       # FR-301-302: urgency rubric call, ambiguous-input default
      device_service.py        # FR-305-309: device_flag lifecycle, quarantine sweep
      queue_service.py         # FR-401-407: sort/filter for Intake Inbox, Dispatch Queue, Quarantine, Archive
      action_service.py        # FR-502-507: coordinator actions, each wrapping a store mutation + audit log write
      feedback_service.py      # FR-601-605: audit log + calibration buffer maintenance
      seed_service.py          # FR-701-702: batch synth-request generation/replay, cascading reset
    llm/
      client.py                # thin wrapper: embed(text) -> vector, complete(prompt) -> structured JSON
      prompts.py                # prompt templates: URGENCY_AND_MATCH_PROMPT (embeds FR-301 rubric verbatim), few-shot injection (FR-604)
    geo.py                     # haversine_km(), geofence filter, centroid recompute
    sort.py                     # lexicographic_sort() shared by FR-401 and FR-403
    routers/
      requests.py               # POST /api/requests, GET /api/requests/{id}, override-urgency, split-out,
                                 #   verify/reject/dispatch-standalone, rescue, merge (FR-205c)
      events.py                 # verify, approve-pending, dispatch, reject-and-flag, dismiss
      queues.py                 # GET intake-inbox, dispatch-queue, quarantine, archive
      seed.py                   # POST /api/seed/replay
  tests/
    test_geo.py                 # haversine correctness, geofence boundary cases
    test_clustering.py          # FR-205 geometric-filter-then-authority ordering (incl. Finding 13's bug case)
    test_sort.py                 # lexicographic sort tie-breaking
    test_state_machine.py        # FR-504b dissolution, FR-308 quarantine sweep, FR-702 cascading wipe
    test_api_flows.py            # end-to-end: submit → cluster → verify → dispatch; submit → fraud → reject-and-flag → quarantine sweep
```

Rationale for the services split: each service maps to one FR-block in spec.md so a reviewer (or Gemini, next round) can check module-by-module against the requirement it implements, rather than hunting through one large file.

## 3. Core data structures (backend)

Mirrors spec.md §6 exactly, as Python dataclasses (or `TypedDict`/Pydantic models — dataclasses shown for clarity; either serializes identically over the API):

```python
# app/models/domain.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class RequestStatus(str, Enum):
    STANDALONE = "standalone"
    IN_CANDIDATE_EVENT = "in_candidate_event"
    PENDING_ADDITION = "pending_addition"
    IN_VERIFIED_EVENT = "in_verified_event"
    DISPATCHED = "dispatched"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"

class EventStatus(str, Enum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    DISPATCHED = "dispatched"

@dataclass
class Location:
    lat: float
    lng: float

@dataclass
class Request:
    id: str
    need_description: str
    location: Location
    photo_url: str | None
    device_fingerprint_id: str
    submitted_at: datetime
    urgency_score: int | None = None          # FR-301; None = NFR-103 pending/failed
    urgency_reasoning: str | None = None
    original_urgency_score: int | None = None  # FR-603
    event_id: str | None = None
    status: RequestStatus = RequestStatus.STANDALONE
    verified: bool = False                     # FR-504b/spec §6: orthogonal to status — set True the moment
                                                # this specific request is individually approved (FR-304,
                                                # FR-304b's promotion, or FR-505), independent of its Event's
                                                # lifecycle; see §4.2b for exactly where it's set
    embedding: list[float] | None = None       # cached, not re-embedded on every comparison

@dataclass
class Event:
    id: str
    member_request_ids: list[str] = field(default_factory=list)
    pending_member_request_ids: list[str] = field(default_factory=list)  # FR-304b; see §4.2
    status: EventStatus = EventStatus.CANDIDATE
    verified_by: str | None = None
    verified_at: datetime | None = None
    representative_location: Location | None = None   # centroid; recomputed on membership change
    created_at: datetime = field(default_factory=datetime.utcnow)
    # FR-205b's excluded-match pairs live on InMemoryStore.suggested_merges (below), not here —
    # see §4.2 for why a flat store-level list is simpler than a field on each side of the pair

@dataclass
class DeviceFingerprint:
    id: str
    first_seen_at: datetime
    device_flag: bool = False
    confirmed_fraud_request_ids: list[str] = field(default_factory=list)

@dataclass
class CoordinatorAction:
    id: str
    actor: str
    action_type: str   # see spec.md §6 enum; kept as str here to avoid import cycles
    target_id: str
    timestamp: datetime
    note: str | None = None
```

### `InMemoryStore`

```python
# app/store/memory_store.py
class InMemoryStore:
    def __init__(self):
        self.requests: dict[str, Request] = {}
        self.events: dict[str, Event] = {}
        self.devices: dict[str, DeviceFingerprint] = {}
        self.actions: list[CoordinatorAction] = []
        self.urgency_calibration_buffer: list[dict] = []   # FR-604, max N entries
        self.match_calibration_buffer: list[dict] = []      # FR-604, max N entries
        self.suggested_merges: list[dict] = []               # FR-205b: excluded-match pairs, see §4.2
        self.config: SessionConfig = SessionConfig()        # FR-208 defaults
        self._lock = threading.Lock()   # single coarse lock; see §6.4 on concurrency
```

A single coarse lock around every store mutation is a deliberate, documented simplification: at demo scale (NFR-102: ≤1,000 requests, ≤50 concurrent Incident Cards, one coordinator persona expected in the pitch) lock contention is a non-issue, and it removes an entire class of races (e.g. two near-simultaneous submissions both computing a stale centroid) for near-zero cost. Not a design to defend at real production scale — noted explicitly so nobody mistakes it for an oversight.

## 4. Core algorithms

### 4.1 Submission pipeline (FR-101–107, FR-201–208, FR-301–302)

```
POST /api/requests
  1. validate payload (FR-101/102): reject if lat/lng missing or need_description empty
  2. device = get_or_create_device_fingerprint(device_fingerprint_id)     # FR-105
  3. if device.device_flag:                                              # FR-107/308
       request.status = QUARANTINED; store; return early — skip 4-9
  4. request = Request(status=STANDALONE, ...); store.requests[id] = request
  5. try:
       embedding = llm_client.embed(need_description)                    # FR-201
       request.embedding = embedding
       candidates = matching_service.geofenced_candidates(request)       # FR-202, FR-208
       top5 = matching_service.top_k_cosine(embedding, candidates, k=5)  # FR-203
       llm_result = llm_client.complete(
           prompts.urgency_and_match_prompt(
               request, top5,
               distances=geo.haversine_each(request, top5),              # FR-204
               calibration=store.urgency_calibration_buffer + store.match_calibration_buffer  # FR-604
           )
       )                                                                  # returns {urgency_score, urgency_reasoning, matches: [...]}
       request.urgency_score = llm_result.urgency_score                  # FR-301, ambiguous-input default=3 handled inside the prompt contract
       request.urgency_reasoning = llm_result.urgency_reasoning
     except (LLMTimeoutError, EmbeddingError):
       request.urgency_score = None; request.urgency_reasoning = "pending/unavailable"  # NFR-103
       return request   # do NOT proceed to clustering with a failed match result
  6. clustering_service.assign(request, llm_result.matches)               # FR-205/205b, see 4.2
  7. return request
```

Failure isolation: an embedding/LLM failure short-circuits *before* clustering runs — a failed request never gets force-matched with `matches=[]`, and it surfaces via the Needs Manual Triage section (FR-401) instead of silently entering `standalone` with an unexamined false "no duplicates" assumption.

### 4.2 Cluster assignment (FR-205, FR-205b, FR-205c) — geometric-filter-then-authority, with bootstrapping

This is the part earlier verification found two contradictions in (chaining, and the ordering bug from Finding 13), plus one the cross-document alignment pass found: the original version never explained how the *first* Event forms from two standalone requests. `llm_matches` here reference matched candidate **requests** (the top-5 from FR-203), not Events directly — each candidate may or may not already belong to one.

```python
def assign(request: Request, llm_matches: list[MatchResult]) -> None:
    matched = [store.requests[m.candidate_request_id] for m in llm_matches if m.is_match]
    matched_in_event = {c.event_id: store.events[c.event_id] for c in matched if c.event_id}
    matched_standalone = [c for c in matched if not c.event_id]

    # Step 1: geometric filter, applied separately to existing-Event matches and standalone matches
    geo_valid_events = [
        e for e in matched_in_event.values()
        if geo.haversine_km(request.location, e.representative_location) <= store.config.max_cluster_span_km
    ]
    geo_valid_standalone = [
        c for c in matched_standalone
        if geo.haversine_km(request.location, c.location) <= store.config.max_cluster_span_km
    ]
    for e in matched_in_event.values():
        if e not in geo_valid_events:
            store.suggested_merges.append({"request_id": request.id, "event_id": e.id})       # FR-205b
    for c in matched_standalone:
        if c not in geo_valid_standalone:
            store.suggested_merges.append({"request_id": request.id, "request_id_2": c.id})   # FR-205b

    if geo_valid_events:
        # Step 2: authority selection among geometrically valid EXISTING Events
        authority_rank = {"dispatched": 2, "verified": 1, "candidate": 0}
        target = max(geo_valid_events, key=lambda e: authority_rank[e.status])
        _attach_to_event(request, target)                          # steps 3/4
        return

    if geo_valid_standalone:
        # Step 5: bootstrap a brand-new candidate Event — this is how every Event originates,
        # since two requests must first match each other before either belongs to one
        new_event = Event(id=new_id(), status=EventStatus.CANDIDATE)
        for r in [request, *geo_valid_standalone]:
            r.event_id = new_event.id
            r.status = RequestStatus.IN_CANDIDATE_EVENT
            new_event.member_request_ids.append(r.id)
        recompute_centroid(new_event)
        store.events[new_event.id] = new_event
        return

    # Step 6: nothing survived the geometric filter, or no matches at all — remain standalone
    request.status = RequestStatus.STANDALONE

    # Step 7: no code path here ever merges two pre-existing Events into each other


def _attach_to_event(request: Request, target: Event) -> None:
    if target.status in ("verified", "dispatched"):
        request.status = RequestStatus.PENDING_ADDITION            # FR-304b — no auto-inherit
        request.event_id = target.id
        target.pending_member_request_ids.append(request.id)       # not in member_request_ids yet — see §4.2b
    else:  # candidate
        request.status = RequestStatus.IN_CANDIDATE_EVENT
        request.event_id = target.id
        target.member_request_ids.append(request.id)
        recompute_centroid(target)


def manual_merge(request_id: str, target_event_id_or_request_id: str, actor: str) -> None:   # FR-205c
    request = store.requests[request_id]
    if target_event_id_or_request_id in store.events:
        _attach_to_event(request, store.events[target_event_id_or_request_id])
    else:
        # both sides were standalone — bootstrap, same as step 5 above
        other = store.requests[target_event_id_or_request_id]
        new_event = Event(id=new_id(), status=EventStatus.CANDIDATE,
                           member_request_ids=[request.id, other.id])
        request.event_id = new_event.id; request.status = RequestStatus.IN_CANDIDATE_EVENT
        other.event_id = new_event.id; other.status = RequestStatus.IN_CANDIDATE_EVENT
        recompute_centroid(new_event)
        store.events[new_event.id] = new_event
    log_action(actor, "manual_merge", request_id)
```

`store.suggested_merges` (added to `InMemoryStore`, §3) is a flat list of excluded-match pairs rather than a field on `Request`/`Event`, since the pairing is symmetric and only needs to render a "Suggested Merge" affordance in the UI — no need to duplicate the pointer on both sides of the pair.

Pending members live in `Event.pending_member_request_ids` (§3), kept separate from `member_request_ids` so the latter always means "counts toward FR-501's 2+ threshold and FR-504b's dissolve check" without extra filtering at every read site.

### 4.2b Where `verified` gets set (and where dissolution must account for pending members)

`Request.verified` (§3) is set exactly at the moments a coordinator approves that specific request, never inferred from its Event:

```python
def verify_event(event_id: str, actor: str) -> None:                       # FR-304, FR-502 "Verify Event & Approve All"
    event = store.events[event_id]
    event.status = EventStatus.VERIFIED
    event.verified_by = actor; event.verified_at = now()
    for rid in event.member_request_ids:                                   # only CURRENT members — FR-304
        r = store.requests[rid]
        r.status = RequestStatus.IN_VERIFIED_EVENT
        r.verified = True
    log_action(actor, "verify_event", event_id)

def approve_pending(event_id: str, actor: str) -> None:                    # FR-304b, FR-502 "Approve All Pending"
    event = store.events[event_id]
    for rid in event.pending_member_request_ids:
        r = store.requests[rid]
        r.status = RequestStatus.IN_VERIFIED_EVENT
        r.verified = True
        event.member_request_ids.append(rid)                               # promoted: now counts for FR-501/504b
    event.pending_member_request_ids.clear()
    recompute_centroid(event)
    log_action(actor, "approve_pending", event_id)

def verify_standalone(request_id: str, actor: str) -> None:                # FR-505: "Verify & Dispatch," atomic
    r = store.requests[request_id]
    r.verified = True
    r.status = RequestStatus.DISPATCHED   # terminal immediately — no intermediate Dispatch Queue residency;
    log_action(actor, "verify_standalone", request_id)     # a lone request has no batching benefit from the split

def dispatch_standalone(request_id: str, actor: str) -> None:              # FR-505b
    r = store.requests[request_id]
    assert r.verified and r.status == RequestStatus.STANDALONE, \
        "only reachable for the FR-504b case: verified via a dissolved Event, not yet dispatched"
    r.status = RequestStatus.DISPATCHED
    log_action(actor, "dispatch_standalone", request_id)
```

Note the asymmetry between `verify_standalone` and `verify_event`: a freshly-standalone request goes straight to `dispatched` (FR-505), while an Incident Card's "Verify Event & Approve All" (`verify_event`, above) only reaches `verified`/`in_verified_event`, needing a separate later "Approve" (dispatch) click. This is intentional, not an inconsistency — the two-step split exists specifically to support batch-approving a cluster (FR-502), which doesn't apply to a single ungrouped request. The one case where a standalone request *does* need that separate dispatch step is exactly `dispatch_standalone` above: a request that was already `verified = True` as an Event member before that Event dissolved out from under it (FR-504b) — it re-enters as `standalone` but skips re-verification, going straight to the Dispatch Queue awaiting its own dispatch click.

`maybe_dissolve_event` (§4.5) never *sets* `verified` — by design, it only clears `event_id`/resets `status`, and leaves each affected request's `verified` flag exactly as the functions above already set it, so a dissolved Event's sole surviving active member correctly keeps routing to whichever queue it earned its way into. §4.5 also explicitly reverts any `pending_addition` members still attached at dissolution time (not just the sole active member) — see the corrected §4.5 below.

### 4.3 Lexicographic sort (FR-401, FR-403)

One shared function, used identically by both queues per spec.md's Finding 4 fix:

```python
# app/sort.py
def sort_key(item: Request | Event) -> tuple[int, int]:
    members = resolve_members(item)   # a standalone Request is its own single-member list
    urgencies = [m.urgency_score for m in members if m.urgency_score is not None]
    max_urgency = max(urgencies) if urgencies else -1   # should not occur for non-triage items
    distinct_devices = len({m.device_fingerprint_id for m in members})
    return (max_urgency, distinct_devices)   # tuple sort = lexicographic, descending via reverse=True

def sorted_queue(items: list[Request | Event]) -> list:
    needs_triage = [i for i in items if any(m.urgency_score is None for m in resolve_members(i))]
    rest = [i for i in items if i not in needs_triage]
    return needs_triage + sorted(rest, key=sort_key, reverse=True)   # NFR-103 / FR-401 §1 + §2
```

### 4.4 Device flag → quarantine sweep (FR-306, FR-308, FR-503)

```python
def reject_and_flag_device(event_id: str, device_id: str, actor: str) -> None:
    with store._lock:
        device = store.devices[device_id]
        device.device_flag = True                                            # FR-306

        event = store.events[event_id]
        this_cards_members = [r for r in requests_of(event) if r.device_fingerprint_id == device_id]
        for r in this_cards_members:
            r.status = RequestStatus.REJECTED                                 # FR-503(b)
        maybe_dissolve_event(event)                                           # FR-504b check

        for r in store.requests.values():                                     # FR-503(c) / FR-308(b)
            if r.device_fingerprint_id == device_id and r.status not in (RequestStatus.DISPATCHED, RequestStatus.REJECTED):
                r.status = RequestStatus.QUARANTINED
                if r.event_id:
                    detach_from_event(r)   # remove from whatever member/pending list it was in, may trigger dissolve

        log_action(actor, "reject_flag_device", event_id, note=f"device={device_id}")
```

### 4.5 Event dissolution (FR-504b)

Centralized in one function so every caller (Split Out, Reject & Flag, Rescue) goes through the same rule — this exact duplication was the root cause of Finding 11 in the verification pass, so the design deliberately has one call site:

```python
def maybe_dissolve_event(event: Event) -> None:
    if len(event.member_request_ids) > 1:
        return   # nothing to do — still a valid Incident Card per FR-501

    # active membership is 0 or 1 — dissolve the Event entirely
    if event.member_request_ids:
        sole = store.requests[event.member_request_ids[0]]
        sole.event_id = None
        sole.status = RequestStatus.STANDALONE
        # sole.verified is deliberately left untouched here — verify_event/approve_pending
        # (§4.2b) already set it correctly when this request was individually approved;
        # dissolution never overrides that. It's what routes this standalone request to
        # the Dispatch Queue (FR-403, verified=True) vs. the Intake Inbox (FR-401, verified=False).

    # any pending_addition members must also be reverted — their parent Event no longer
    # exists, so leaving event_id pointing at a deleted Event would dangle. They were never
    # approved, so verified stays False and they re-enter independent evaluation.
    for rid in event.pending_member_request_ids:
        pending = store.requests[rid]
        pending.event_id = None
        pending.status = RequestStatus.STANDALONE
        pending.verified = False

    del store.events[event.id]
```

### 4.6 Dismiss Cluster (FR-507)

```python
def dismiss_cluster(event_id: str, actor: str) -> None:
    event = store.events[event_id]
    assert event.status == EventStatus.CANDIDATE, "Dismiss Cluster only valid on candidate Events"
    for rid in event.member_request_ids:
        r = store.requests[rid]
        r.event_id = None
        r.status = RequestStatus.STANDALONE
        # re-run matching_service against the current pool, since the pool has changed
        # since this request last searched — cheap at demo scale, avoids stale non-matches
    del store.events[event_id]
    log_action(actor, "dismiss_cluster", event_id)
    # no device_flag touched anywhere in this function — that's the entire point of FR-507
```

### 4.7 Adaptive calibration buffer (FR-603–605)

```python
def record_urgency_override(request_id, corrected_score, reason, actor):
    r = store.requests[request_id]
    r.original_urgency_score = r.urgency_score
    r.urgency_score = corrected_score
    store.urgency_calibration_buffer.append({
        "text": r.need_description, "original": r.original_urgency_score,
        "corrected": corrected_score, "reason": reason,
    })
    store.urgency_calibration_buffer = store.urgency_calibration_buffer[-N:]   # FR-604 rolling window
    log_action(actor, "override_urgency", request_id, note=reason)

def record_duplicate_correction(request_a_text, request_b_text, reason):
    store.match_calibration_buffer.append({"a": request_a_text, "b": request_b_text, "reason": reason})
    store.match_calibration_buffer = store.match_calibration_buffer[-N:]
    # called from split_out() and dismiss_cluster() — both imply "the LLM's match judgment was wrong"
```

`prompts.py` renders both buffers into the prompt as a short few-shot block, prepended before the rubric (FR-604's example format). FR-605's scope boundary — never call this fine-tuning — is enforced by naming: no function in this module is named `train`, `fit`, or similar, and the module docstring states the boundary explicitly.

### 4.8 Seed/replay reset (FR-701, FR-702)

```python
def replay(mode: Literal["reset", "append"], batch: list[SeedRequest], geofence_radius_km=None, max_cluster_span_km=None):
    if mode == "reset":
        store.requests.clear(); store.events.clear(); store.devices.clear()
        store.actions.clear()                                    # FR-702: audit log wiped too
        store.urgency_calibration_buffer.clear(); store.match_calibration_buffer.clear()
        if geofence_radius_km: store.config.geofence_radius_km = geofence_radius_km   # FR-208
        if max_cluster_span_km: store.config.max_cluster_span_km = max_cluster_span_km
    for seed_req in batch:
        intake_service.submit(seed_req, is_seed=True)             # FR-701: through the real intake path
```

## 5. LLM interface design

### 5.1 Structured output contract

Single call per submission (FR-204/FR-301 share it) returns:

```json
{
  "urgency_score": 4,
  "urgency_reasoning": "Explicit mention of insulin running out within hours — FR-301 tier 4.",
  "matches": [
    {"candidate_id": "req_113", "is_match": true, "reason": "Same flooded street, submitted 12 min ago, 90m away."},
    {"candidate_id": "req_098", "is_match": false, "reason": "Different need (water vs. medical), 300m away — not the same incident."}
  ]
}
```

Enforced via the LLM provider's structured-output/JSON-schema mode where available; a Pydantic model validates the response regardless (`LLMResponseSchema`), and a validation failure is treated identically to a call failure for NFR-103 purposes (never trust an unparseable response as if it were a valid urgency=3).

### 5.2 Prompt assembly (`prompts.py`)

```
[SYSTEM] You are triaging aid requests. <FR-301 rubric table, embedded verbatim>
         <FR-302 instruction: score content not eloquence>
         <FR-604 calibration block, if buffers non-empty:
            "Recent coordinator corrections to learn from:
             - text: '...' | model said 2, coordinator corrected to 5, reason: '...'
             - ..."
         >
[USER]   New request: "<need_description>"
         Candidates (with precomputed distance, FR-204):
           1. req_113 (90m away, 12 min ago): "<text>"
           2. req_098 (300m away, 40 min ago): "<text>"
         Return JSON matching <schema>.
```

## 6. Frontend design

### 6.1 Two entry points

- `/intake` — public form: location capture (map pin or `navigator.geolocation`, FR-101), need text, optional photo upload, hidden device-fingerprint field (generated/read from `localStorage` on load, FR-105).
- `/dashboard` — coordinator SPA, tab-based navigation matching the four views defined in spec.md §4.4/§4.5:

```
Dashboard
├── IntakeVerificationInbox   (FR-401/402)
│     ├── NeedsManualTriageSection
│     └── SortedList
│           ├── IncidentCard (2+ members)         → DeviceGroup[] (FR-503) each with Reject & Flag
│           │                                       + Dismiss Cluster (FR-507, candidate only)
│           │                                       + Verify Event & Approve All (FR-502)
│           └── StandaloneRow (1 member)            → inline Verify&Dispatch / Reject (FR-505)
│                                                       + Merge button if a SuggestedMerge exists (FR-205c)
├── DispatchQueue             (FR-403)
│     ├── IncidentCard (verified) → Approve (dispatch, FR-502) / Approve All Pending (FR-304b) / Reject&Flag
│     └── StandaloneRow (verified=true, not yet dispatched — FR-504b case only) → inline Dispatch (FR-505b)
├── QuarantineInbox           (FR-407)
│     └── grouped by device  → bulk Reject All / individual Rescue
├── ArchiveView               (FR-406)
│     └── read-only list, scrutiny marker for flagged devices (FR-309)
└── RequestDetail (modal/route)  (FR-506, FR-602, FR-603)
      ├── reasoning strings (match + urgency)
      ├── action history (audit log)
      └── Override Urgency control
```

`IncidentCard`'s device-grouping (FR-503) is a shared sub-component used by both the Intake Inbox (candidate Events) and Dispatch Queue (verified Events with `pending_addition` members) — same grouping logic, different action set passed as props, keeping FR-502/FR-503's two contexts from diverging in implementation.

### 6.2 State management

Lightweight: no Redux needed at this scope. Each view is a component that polls its corresponding `GET` endpoint (§6.3) via a shared `usePolling(url, intervalMs)` hook, holding results in local component state. Mutations (`POST` actions) optimistically disable the clicked control, await the response, then trigger an immediate re-fetch rather than waiting for the next poll tick — keeps FR-405's "no manual reload" requirement snappy without websocket complexity.

### 6.3 Polling interval

3-second poll on the two live queues (Intake Inbox, Dispatch Queue); 5-second on Quarantine/Archive (lower-priority views). Chosen to comfortably clear NFR-101's 5-second per-submission budget while feeling live during a demo; documented as a tunable constant, not a hard requirement.

### 6.4 Concurrency note (backend)

FastAPI runs async by default; all store mutations go through `InMemoryStore`'s single `threading.Lock`, acquired synchronously around each mutating operation (§3). LLM/embedding calls happen *before* the lock is acquired (they're the slow part) so a single slow LLM call never blocks other requests' store reads — only the final, fast state-mutation is serialized. This keeps NFR-101 achievable even with several submissions landing close together.

## 7. Gaps surfaced while writing this design (already folded into spec.md)

Writing the design surfaced two requirement/implementation-level gaps, both resolved here and in spec.md directly (not left as future recommendations):

- **FR-504b's "keeps whichever verification state it individually held"** was unimplementable with `Request.status` alone, since `standalone` was used for both "never verified" (routes to Intake Inbox) and "was verified, Event dissolved" (routes to Dispatch Queue) — one enum value, two routing meanings. Resolved with an orthogonal `verified: bool` field on `Request` (§3), set only by the explicit approval actions in §4.2b and left untouched by dissolution (§4.5). spec.md §6/FR-403/FR-504b were updated to match.
- **Dissolution didn't account for `pending_addition` members**: an Event with 1 active member and 2 pending members would previously be deleted outright, leaving the pending members' `event_id` dangling. §4.5 now explicitly reverts any `pending_member_request_ids` to standalone (`verified = False`, since they were never approved) in the same pass that dissolves the Event.

A subsequent cross-document alignment pass (checking idea.md/spec.md/design.md against each other, not just spec vs. design) found three more real gaps, all fixed in both documents (spec.md §11):

- **FR-205b's "Suggested Merge" indicator had no way to act on it** — no requirement or route executed a merge. Added FR-205c and `manual_merge()` (§4.2).
- **FR-205's original wording never explained how the first Event forms** — it only described joining a new request to an *already-existing* Event. Rewritten (§4.2) to bootstrap a new Event when matched candidates are themselves standalone.
- **Standalone requests could get stuck verified-but-never-dispatched** — FR-505's "Verify & Dispatch" now performs both steps atomically (§4.2b) for the common case, and the one path that still needs a separate dispatch step (a request that re-enters standalone via FR-504b already verified) has one: `dispatch_standalone()` / FR-505b.

## 8. Traceability summary

| Spec section | Design section(s) |
|---|---|
| FR-1xx Intake | §4.1 |
| FR-2xx Matching/geofence | §4.1, §4.2, §5 |
| FR-3xx Verification/device | §4.2, §4.4, §5.2 |
| FR-4xx Queues | §4.3, §6.1 |
| FR-5xx Incident Cards/actions | §4.2, §4.4–4.6, §6.1 |
| FR-6xx Feedback loop | §4.7, §5.2 |
| FR-7xx Demo support | §4.8 |
| NFR-101/102 Latency/scale | §3 (coarse lock rationale), §6.4 |
| NFR-103 Resilience | §4.1 (failure isolation), §4.3 (Needs Manual Triage sort) |
| NFR-201/202 Privacy/data | §3 (no PII fields in domain model) |
| NFR-301/302 Explainability/auditability | §5.1 (reasoning always returned), §4.7 (audit log) |
| NFR-401 Usability | §6.1 (inline standalone actions), §6.2 (optimistic UI) |
