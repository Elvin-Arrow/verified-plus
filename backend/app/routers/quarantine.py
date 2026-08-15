"""BE-18: POST /api/quarantine/{device_id}/reject-all."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_store
from app.models.schemas import ActorIn
from app.services.device_service import device_service

router = APIRouter(prefix="/api/quarantine", tags=["quarantine"])


@router.post("/{device_id}/reject-all")
def reject_all(device_id: str, body: ActorIn, store=Depends(get_store)):
    rejected_ids = device_service.reject_all_quarantined(store, device_id, actor=body.actor)
    if not rejected_ids:
        # api-spec.md §5: an empty reject is treated as not-found, same
        # convention as merge's target validation.
        raise KeyError(f"device {device_id} has no currently-quarantined requests")
    return {"device_fingerprint_id": device_id, "rejected_request_ids": rejected_ids}
