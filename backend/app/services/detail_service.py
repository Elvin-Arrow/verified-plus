"""BE-17: detail reads. docs/api-spec.md §7; FR-506, FR-602.

Both functions raise KeyError on an unknown ID -- BE-18's router maps
that to 404 NOT_FOUND, matching api-spec.md §1.1.
"""
from __future__ import annotations

from app.services.queue_service import is_device_flagged
from app.store.memory_store import InMemoryStore


def request_detail(store: InMemoryStore, request_id: str) -> dict:
    request = store.requests[request_id]  # KeyError -> 404
    action_history = [a for a in store.actions if a.target_id == request_id]
    suggested_merges = [sm for sm in store.suggested_merges if sm.get("request_id") == request_id]
    return {
        "request": request,
        "device_flagged": is_device_flagged(store, request),
        "match_reasons": request.match_reasons,
        "suggested_merges": suggested_merges,
        "action_history": action_history,
    }


def event_detail(store: InMemoryStore, event_id: str) -> dict:
    event = store.events[event_id]  # KeyError -> 404 (dissolved/never-existed both look the same)
    members = [store.requests[rid] for rid in event.member_request_ids if rid in store.requests]
    pending_members = [store.requests[rid] for rid in event.pending_member_request_ids if rid in store.requests]
    action_history = [a for a in store.actions if a.target_id == event_id]
    return {
        "event": event,
        "members": members,
        "pending_members": pending_members,
        "action_history": action_history,
    }
