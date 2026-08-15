"""BE-08 (used by BE-07): geofenced_candidates (FR-202/208), top_k_cosine (FR-203).

Candidate-pool construction per FR-202:
  - member requests of a non-dispatched Event (candidate/verified) within
    geofence_radius_km of the Event's representative_location — NO age
    limit (an active, ongoing emergency stays comparable however long
    it's been open).
  - member requests of a dispatched ("inactive/resolved") Event within
    geofence_radius_km, but only if the Event is <= 48h old (it ages out).
  - standalone requests within geofence_radius_km of the new request,
    but only if submitted within the last 48h (they age out too).

Only currently-active membership counts (`Event.member_request_ids`) —
`pending_member_request_ids` are deliberately excluded, since they haven't
been approved onto the Event yet and aren't representative of it.
Terminal/quarantined standalone requests (`dispatched`, `rejected`,
`quarantined`) are excluded from the pool entirely; they're archived or
held, not live corroboration candidates.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.geo import haversine_km, within_radius
from app.models.domain import Event, EventStatus, Request, RequestStatus, SessionConfig
from app.store.memory_store import InMemoryStore

AGE_CUTOFF = timedelta(hours=48)

_TERMINAL_STANDALONE_STATUSES = {
    RequestStatus.DISPATCHED,
    RequestStatus.REJECTED,
    RequestStatus.QUARANTINED,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def geofenced_candidates(store: InMemoryStore, request: Request, now: datetime | None = None) -> list[Request]:
    now = now or _now()
    radius = store.config.geofence_radius_km
    candidates: list[Request] = []

    for event in store.events.values():
        if event.representative_location is None:
            continue
        if not within_radius(request.location, event.representative_location, radius):
            continue
        if event.status != EventStatus.DISPATCHED:
            age_ok = True  # FR-202(a): active Event, no age limit
        else:
            age_ok = (now - event.created_at) <= AGE_CUTOFF  # FR-202(b): resolved Event ages out
        if not age_ok:
            continue
        for rid in event.member_request_ids:
            member = store.requests.get(rid)
            if member is not None and member.id != request.id:
                candidates.append(member)

    for other in store.requests.values():
        if other.id == request.id:
            continue
        if other.event_id is not None:
            continue  # covered via the Event branch above
        if other.status in _TERMINAL_STANDALONE_STATUSES:
            continue
        if not within_radius(request.location, other.location, radius):
            continue
        if (now - other.submitted_at) > AGE_CUTOFF:  # FR-202(b): standalone ages out
            continue
        candidates.append(other)

    return candidates


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def top_k_cosine(embedding: list[float], candidates: list[Request], k: int = 5) -> list[Request]:
    """FR-203: rank candidates by cosine similarity of their embeddings,
    return the top k (or fewer, if the pool is smaller)."""
    scored = [
        (c, _cosine_similarity(embedding, c.embedding or []))
        for c in candidates
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [c for c, _score in scored[:k]]
