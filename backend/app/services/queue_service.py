"""BE-16: queue assembly. docs/design.md §4.3; FR-401-407.

Returns domain objects (Event/Request), not pre-serialized JSON -- BE-18's
router layer maps these onto api-spec.md's response shapes via
app/models/schemas.py. Sorting is delegated entirely to sort.py's shared
lexicographic rule so both live queues can never independently drift.
"""
from __future__ import annotations

from typing import Union

from app.models.domain import Event, EventStatus, Request, RequestStatus
from app.sort import sorted_queue
from app.store.memory_store import InMemoryStore

QueueItem = Union[Event, Request]


def resolve_members(store: InMemoryStore, item: QueueItem) -> list[Request]:
    if isinstance(item, Request):
        return [item]
    return [store.requests[rid] for rid in item.member_request_ids if rid in store.requests]


def is_device_flagged(store: InMemoryStore, request: Request) -> bool:
    device = store.devices.get(request.device_fingerprint_id)
    return bool(device and device.device_flag)


def intake_inbox(store: InMemoryStore) -> dict:
    """FR-401: every candidate Event + every unverified standalone request."""
    events = [e for e in store.events.values() if e.status == EventStatus.CANDIDATE]
    standalones = [
        r for r in store.requests.values()
        if r.status == RequestStatus.STANDALONE and not r.verified
    ]
    items: list[QueueItem] = [*events, *standalones]
    triage, rest = sorted_queue(items, lambda i: resolve_members(store, i))
    return {"needs_manual_triage": triage, "sorted": rest}


def dispatch_queue(store: InMemoryStore) -> dict:
    """FR-403: verified Events + standalone requests with verified=True,
    excluding dispatched/rejected/quarantined."""
    events = [e for e in store.events.values() if e.status == EventStatus.VERIFIED]
    standalones = [
        r for r in store.requests.values()
        if r.status == RequestStatus.STANDALONE and r.verified
    ]
    items: list[QueueItem] = [*events, *standalones]
    _triage, rest = sorted_queue(items, lambda i: resolve_members(store, i))
    # Dispatch Queue items are, by construction, always fully scored --
    # anything with a null urgency_score never reaches "verified" in the
    # first place -- so the triage split is discarded here (FR-403 has no
    # Needs Manual Triage section of its own).
    return {"sorted": rest}


def quarantine(store: InMemoryStore) -> dict:
    """FR-407: grouped by device."""
    by_device: dict[str, list[Request]] = {}
    for r in store.requests.values():
        if r.status == RequestStatus.QUARANTINED:
            by_device.setdefault(r.device_fingerprint_id, []).append(r)
    groups = [
        {
            "device_fingerprint_id": device_id,
            "device_flag": bool(store.devices.get(device_id) and store.devices[device_id].device_flag),
            "requests": reqs,
        }
        for device_id, reqs in by_device.items()
    ]
    return {"groups": groups}


def archive(store: InMemoryStore) -> dict:
    """FR-406: dispatched/rejected, flat and read-only."""
    events = [e for e in store.events.values() if e.status == EventStatus.DISPATCHED]
    standalones = [
        r for r in store.requests.values()
        if r.event_id is None and r.status in (RequestStatus.DISPATCHED, RequestStatus.REJECTED)
    ]
    return {"events": events, "standalone_requests": standalones}
