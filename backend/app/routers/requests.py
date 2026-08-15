"""BE-18: POST /api/requests, GET /api/requests/{id}, override-urgency,
split-out, verify/reject/dispatch-standalone, rescue, merge (FR-205c)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_llm_client, get_store
from app.models.schemas import ActorIn, MergeIn, OverrideUrgencyIn, SubmitRequestIn
from app.models.domain import Location
from app.serializers import action_json, event_full_json, request_full_json
from app.services import clustering_service, detail_service, intake_service
from app.services.action_service import action_service
from app.services.feedback_service import record_urgency_override
from app.services.intake_service import ValidationError

router = APIRouter(prefix="/api/requests", tags=["requests"])


@router.post("", status_code=201)
def submit_request(body: SubmitRequestIn, store=Depends(get_store), llm_client=Depends(get_llm_client)):
    req = intake_service.submit(
        store, llm_client,
        need_description=body.need_description,
        location=Location(lat=body.location.lat, lng=body.location.lng),
        device_fingerprint_id=body.device_fingerprint_id,
        photo_url=body.photo_url,
    )
    return request_full_json(store, req)


@router.get("/{request_id}")
def get_request(request_id: str, store=Depends(get_store)):
    detail = detail_service.request_detail(store, request_id)
    body = request_full_json(store, detail["request"])
    body["suggested_merges"] = detail["suggested_merges"]
    body["action_history"] = [action_json(a) for a in detail["action_history"]]
    return body


@router.post("/{request_id}/verify-standalone")
def verify_standalone(request_id: str, body: ActorIn, store=Depends(get_store)):
    r = action_service.verify_standalone(store, request_id, actor=body.actor)
    return request_full_json(store, r)


@router.post("/{request_id}/reject-standalone")
def reject_standalone(request_id: str, body: ActorIn, store=Depends(get_store)):
    r = action_service.reject_standalone(store, request_id, actor=body.actor)
    return request_full_json(store, r)


@router.post("/{request_id}/dispatch-standalone")
def dispatch_standalone(request_id: str, body: ActorIn, store=Depends(get_store)):
    r = action_service.dispatch_standalone(store, request_id, actor=body.actor)
    return request_full_json(store, r)


@router.post("/{request_id}/split-out")
def split_out(request_id: str, body: ActorIn, store=Depends(get_store), llm_client=Depends(get_llm_client)):
    r = action_service.split_out(store, llm_client, request_id, actor=body.actor)
    event = store.events.get(r.event_id) if r.event_id else None
    return {
        "request": request_full_json(store, r),
        "event_dissolved": r.event_id is None,
        "event": event_full_json(store, event) if event else None,
    }


@router.post("/{request_id}/rescue")
def rescue(request_id: str, body: ActorIn, store=Depends(get_store), llm_client=Depends(get_llm_client)):
    r = action_service.rescue(store, llm_client, request_id, actor=body.actor)
    return request_full_json(store, r)


@router.post("/{request_id}/override-urgency")
def override_urgency(request_id: str, body: OverrideUrgencyIn, store=Depends(get_store)):
    if request_id not in store.requests:
        raise KeyError(f"request {request_id}")
    record_urgency_override(store, request_id, corrected_score=body.corrected_score,
                             reason=body.reason, actor=body.actor)
    return request_full_json(store, store.requests[request_id])


@router.post("/{request_id}/merge")
def merge(request_id: str, body: MergeIn, store=Depends(get_store)):
    if bool(body.target_event_id) == bool(body.target_request_id):
        raise ValidationError(
            "exactly one of target_event_id / target_request_id must be set", field="target_event_id",
        )
    if body.target_event_id and body.target_event_id not in store.events:
        raise KeyError(f"event {body.target_event_id}")
    if body.target_request_id and body.target_request_id not in store.requests:
        raise KeyError(f"request {body.target_request_id}")
    if request_id not in store.requests:
        raise KeyError(f"request {request_id}")

    valid_targets = {
        sm.get("event_id") or sm.get("request_id_2")
        for sm in store.suggested_merges
        if sm.get("request_id") == request_id
    }
    target = body.target_event_id or body.target_request_id
    if target not in valid_targets:
        raise KeyError(f"{target} is not a suggested merge target for {request_id}")

    event = clustering_service.manual_merge(
        store, request_id, target_event_id=body.target_event_id,
        target_request_id=body.target_request_id, actor=body.actor,
    )
    return event_full_json(store, event)
