"""BE-10 (HIGH RISK): detach_from_event + maybe_dissolve_event. docs/design.md §4.4/§4.5.

`detach_from_event` is the single call site for "remove this request from
its Event, whichever list it's in." Every path that pulls a member out of
an Event (reject, split-out, quarantine sweep) goes through this -- not a
duplicated remove-from-list snippet at each call site -- because that
duplication is exactly what let a real bug slip through an earlier draft:
a member's own `status` was updated without ever being removed from the
Event's `member_request_ids`, so `maybe_dissolve_event`'s length check
never saw the membership actually shrink, and the Event could never
dissolve -- a ghost Event, still on the board, full of already-rejected
requests, forever.
"""
from __future__ import annotations

from app.models.domain import Event, Request, RequestStatus
from app.services.clustering_service import recompute_centroid
from app.store.memory_store import InMemoryStore


def maybe_dissolve_event(store: InMemoryStore, event: Event) -> None:
    if len(event.member_request_ids) > 1:
        return  # nothing to do -- still a valid Incident Card per FR-501

    # active membership is 0 or 1 -- dissolve the Event entirely
    if event.member_request_ids:
        sole = store.requests[event.member_request_ids[0]]
        sole.event_id = None
        sole.status = RequestStatus.STANDALONE
        # sole.verified is deliberately left untouched here -- verify_event/
        # approve_pending already set it correctly when this request was
        # individually approved; dissolution never overrides that.

    # any pending_addition members must also be reverted -- their parent
    # Event no longer exists, so leaving event_id pointing at a deleted
    # Event would dangle. They were never approved, so verified stays
    # False and they re-enter independent evaluation.
    for rid in event.pending_member_request_ids:
        pending = store.requests[rid]
        pending.event_id = None
        pending.status = RequestStatus.STANDALONE
        pending.verified = False

    if event.id in store.events:
        del store.events[event.id]


def detach_from_event(store: InMemoryStore, r: Request) -> None:
    event = store.events.get(r.event_id) if r.event_id else None
    r.event_id = None
    if not event:
        return
    if r.id in event.member_request_ids:
        event.member_request_ids.remove(r.id)
        if event.id in store.events:  # may already be gone if maybe_dissolve_event ran elsewhere
            recompute_centroid(store, event)
    elif r.id in event.pending_member_request_ids:
        event.pending_member_request_ids.remove(r.id)
    maybe_dissolve_event(store, event)
