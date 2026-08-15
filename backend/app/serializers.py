"""BE-18: domain-object -> api-spec.md JSON shape mapping."""
from __future__ import annotations

from app.models.domain import CoordinatorAction, Event, Request
from app.services.queue_service import has_suggested_merge, is_device_flagged, resolve_members
from app.store.memory_store import InMemoryStore


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def location_json(loc) -> dict | None:
    if loc is None:
        return None
    return {"lat": loc.lat, "lng": loc.lng}


def match_result_json(m) -> dict:
    return {"candidate_id": m.candidate_id, "is_match": m.is_match, "reason": m.reason}


def request_summary_json(store: InMemoryStore, r: Request) -> dict:
    return {
        "id": r.id,
        "need_description": r.need_description,
        "location": location_json(r.location),
        "device_fingerprint_id": r.device_fingerprint_id,
        "submitted_at": _iso(r.submitted_at),
        "urgency_score": r.urgency_score,
        "urgency_reasoning": r.urgency_reasoning,
        "status": r.status.value,
        "verified": r.verified,
        "event_id": r.event_id,
        "device_flagged": is_device_flagged(store, r),
        "has_suggested_merge": has_suggested_merge(store, r),
    }


def request_full_json(store: InMemoryStore, r: Request) -> dict:
    d = request_summary_json(store, r)
    d["photo_url"] = r.photo_url
    d["original_urgency_score"] = r.original_urgency_score
    d["matches"] = [match_result_json(m) for m in r.match_reasons]
    return d


def action_json(a: CoordinatorAction) -> dict:
    return {
        "id": a.id, "actor": a.actor, "action_type": a.action_type,
        "target_id": a.target_id, "timestamp": _iso(a.timestamp), "note": a.note,
    }


def event_summary_json(store: InMemoryStore, e: Event, include_pending: bool = False) -> dict:
    members = resolve_members(store, e)
    urgencies = [m.urgency_score for m in members if m.urgency_score is not None]
    d = {
        "id": e.id,
        "status": e.status.value,
        "member_count": len(members),
        "distinct_device_count": len({m.device_fingerprint_id for m in members}),
        "max_urgency_score": max(urgencies) if urgencies else None,
        "representative_location": location_json(e.representative_location),
        "members": [request_summary_json(store, m) for m in members],
    }
    if include_pending:
        pending = [store.requests[rid] for rid in e.pending_member_request_ids if rid in store.requests]
        d["pending_members"] = [request_summary_json(store, p) for p in pending]
    return d


def event_full_json(store: InMemoryStore, e: Event) -> dict:
    d = event_summary_json(store, e, include_pending=True)
    d["verified_by"] = e.verified_by
    d["verified_at"] = _iso(e.verified_at)
    d["created_at"] = _iso(e.created_at)
    return d
