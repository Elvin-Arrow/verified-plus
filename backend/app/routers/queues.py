"""BE-18: GET intake-inbox, dispatch-queue, quarantine, archive."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_store
from app.models.domain import Event, Request
from app.serializers import event_summary_json, request_summary_json
from app.services import queue_service

router = APIRouter(prefix="/api", tags=["queues"])


def _item_json(store, item, include_pending: bool = False) -> dict:
    if isinstance(item, Request):
        return {"type": "request", "item": request_summary_json(store, item)}
    return {"type": "event", "item": event_summary_json(store, item, include_pending=include_pending)}


@router.get("/intake-inbox")
def intake_inbox(store=Depends(get_store)):
    result = queue_service.intake_inbox(store)
    return {
        "needs_manual_triage": [_item_json(store, i) for i in result["needs_manual_triage"]],
        "sorted": [_item_json(store, i) for i in result["sorted"]],
    }


@router.get("/dispatch-queue")
def dispatch_queue(store=Depends(get_store)):
    result = queue_service.dispatch_queue(store)
    return {"sorted": [_item_json(store, i, include_pending=True) for i in result["sorted"]]}


@router.get("/quarantine")
def quarantine(store=Depends(get_store)):
    result = queue_service.quarantine(store)
    return {
        "groups": [
            {
                "device_fingerprint_id": g["device_fingerprint_id"],
                "device_flag": g["device_flag"],
                "requests": [request_summary_json(store, r) for r in g["requests"]],
            }
            for g in result["groups"]
        ]
    }


@router.get("/archive")
def archive(store=Depends(get_store)):
    result = queue_service.archive(store)
    return {
        "events": [event_summary_json(store, e) for e in result["events"]],
        "standalone_requests": [request_summary_json(store, r) for r in result["standalone_requests"]],
    }
