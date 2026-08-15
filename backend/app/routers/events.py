"""BE-18: verify, approve-pending, dispatch, reject-and-flag, dismiss, GET /api/events/{id}."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_store
from app.models.schemas import ActorIn
from app.serializers import action_json, event_full_json, request_full_json
from app.services import detail_service
from app.services.action_service import action_service
from app.services.device_service import device_service

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/{event_id}")
def get_event(event_id: str, store=Depends(get_store)):
    detail = detail_service.event_detail(store, event_id)
    body = event_full_json(store, detail["event"])
    body["action_history"] = [action_json(a) for a in detail["action_history"]]
    return body


@router.post("/{event_id}/verify")
def verify_event(event_id: str, body: ActorIn, store=Depends(get_store)):
    event = action_service.verify_event(store, event_id, actor=body.actor)
    return event_full_json(store, event)


@router.post("/{event_id}/approve-pending")
def approve_pending(event_id: str, body: ActorIn, store=Depends(get_store)):
    event = action_service.approve_pending(store, event_id, actor=body.actor)
    return event_full_json(store, event)


@router.post("/{event_id}/dispatch")
def dispatch_event(event_id: str, body: ActorIn, store=Depends(get_store)):
    event = action_service.dispatch_event(store, event_id, actor=body.actor)
    return event_full_json(store, event)


@router.post("/{event_id}/dismiss")
def dismiss(event_id: str, body: ActorIn, store=Depends(get_store)):
    reverted_ids = action_service.dismiss_cluster(store, event_id, actor=body.actor)
    return {"reverted_request_ids": reverted_ids}


@router.post("/{event_id}/devices/{device_id}/reject-and-flag")
def reject_and_flag(event_id: str, device_id: str, body: ActorIn, store=Depends(get_store)):
    result = device_service.reject_and_flag_device(store, event_id, device_id, actor=body.actor)
    return {
        "event": event_full_json(store, result["event"]) if result["event"] else None,
        "rejected_request_ids": result["rejected_request_ids"],
        "quarantined_request_ids": result["quarantined_request_ids"],
        "event_dissolved": result["event_dissolved"],
    }
