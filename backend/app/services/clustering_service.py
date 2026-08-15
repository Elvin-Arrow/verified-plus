"""BE-09 (HIGH RISK): cluster assignment. docs/design.md §4.2; FR-205/205b/205c.

Geometric-filter-then-authority, with bootstrapping. `llm_matches` here
reference matched candidate **requests** (the top-5 from FR-203), not
Events directly -- each candidate may or may not already belong to one.
The geometric filter (step 1) runs BEFORE authority selection (step 2) --
this ordering is deliberate and is exactly what the Finding-13 regression
test guards (docs/spec.md §10 #13): an Event with higher authority but
excluded by the geometric filter must never block a closer, lower-authority
Event from winning.
"""
from __future__ import annotations

from app.geo import centroid, haversine_km
from app.models.domain import Event, EventStatus, MatchResult, Request, RequestStatus
from app.services.action_log import log_action
from app.store.memory_store import InMemoryStore

_AUTHORITY_RANK = {
    EventStatus.DISPATCHED: 2,
    EventStatus.VERIFIED: 1,
    EventStatus.CANDIDATE: 0,
}


def recompute_centroid(store: InMemoryStore, event: Event) -> None:
    members = [store.requests[rid] for rid in event.member_request_ids if rid in store.requests]
    if members:
        event.representative_location = centroid([m.location for m in members])


def _attach_to_event(store: InMemoryStore, request: Request, target: Event) -> None:
    if target.status in (EventStatus.VERIFIED, EventStatus.DISPATCHED):
        request.status = RequestStatus.PENDING_ADDITION  # FR-304b -- no auto-inherit
        request.event_id = target.id
        target.pending_member_request_ids.append(request.id)
    else:  # candidate
        request.status = RequestStatus.IN_CANDIDATE_EVENT
        request.event_id = target.id
        target.member_request_ids.append(request.id)
        recompute_centroid(store, target)


def assign(store: InMemoryStore, request: Request, llm_matches: list[MatchResult]) -> None:
    matched_ids = [m.candidate_id for m in llm_matches if m.is_match]
    matched = [store.requests[cid] for cid in matched_ids if cid in store.requests]

    matched_in_event: dict[str, Event] = {}
    matched_standalone: list[Request] = []
    for c in matched:
        if c.event_id and c.event_id in store.events:
            matched_in_event[c.event_id] = store.events[c.event_id]
        elif not c.event_id:
            matched_standalone.append(c)

    max_span = store.config.max_cluster_span_km

    # Step 1: geometric filter, applied separately to existing-Event matches and standalone matches
    geo_valid_events = [
        e for e in matched_in_event.values()
        if e.representative_location is not None
        and haversine_km(request.location, e.representative_location) <= max_span
    ]
    geo_valid_standalone = [
        c for c in matched_standalone
        if haversine_km(request.location, c.location) <= max_span
    ]

    for e in matched_in_event.values():
        if e not in geo_valid_events:
            store.suggested_merges.append({  # FR-205b
                "request_id": request.id,
                "event_id": e.id,
                "distance_km": haversine_km(request.location, e.representative_location),
            })
    for c in matched_standalone:
        if c not in geo_valid_standalone:
            store.suggested_merges.append({  # FR-205b
                "request_id": request.id,
                "request_id_2": c.id,
                "distance_km": haversine_km(request.location, c.location),
            })

    if geo_valid_events:
        # Step 2: authority selection among geometrically valid EXISTING Events
        target = max(geo_valid_events, key=lambda e: _AUTHORITY_RANK[e.status])
        _attach_to_event(store, request, target)  # steps 3/4
        return

    if geo_valid_standalone:
        # Step 5: bootstrap a brand-new candidate Event -- this is how every
        # Event originates, since two requests must first match each other
        # before either belongs to one.
        new_event = Event(id=store.new_id("evt"), status=EventStatus.CANDIDATE)
        for r in [request, *geo_valid_standalone]:
            r.event_id = new_event.id
            r.status = RequestStatus.IN_CANDIDATE_EVENT
            new_event.member_request_ids.append(r.id)
        recompute_centroid(store, new_event)
        store.events[new_event.id] = new_event
        return

    # Step 6: nothing survived the geometric filter, or no matches at all -- remain standalone
    request.status = RequestStatus.STANDALONE

    # Step 7: no code path here ever merges two pre-existing Events into each other


def manual_merge(store: InMemoryStore, request_id: str, target_event_id: str | None,
                  target_request_id: str | None, actor: str) -> Event:
    """FR-205c: bypasses only the geometric filter, never authority/pending-addition logic."""
    with store._lock:  # BE-20
        request = store.requests[request_id]
        if target_event_id:
            event = store.events[target_event_id]
            _attach_to_event(store, request, event)
            result_event = event
        else:
            other = store.requests[target_request_id]
            new_event = Event(id=store.new_id("evt"), status=EventStatus.CANDIDATE,
                               member_request_ids=[request.id, other.id])
            request.event_id = new_event.id
            request.status = RequestStatus.IN_CANDIDATE_EVENT
            other.event_id = new_event.id
            other.status = RequestStatus.IN_CANDIDATE_EVENT
            recompute_centroid(store, new_event)
            store.events[new_event.id] = new_event
            result_event = new_event
        log_action(store, actor, "manual_merge", request_id)
        return result_event
