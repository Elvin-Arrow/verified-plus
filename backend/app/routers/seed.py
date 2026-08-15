"""BE-18: POST /api/seed/replay."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_llm_client, get_store
from app.models.schemas import SeedReplayIn
from app.services import seed_service

router = APIRouter(prefix="/api/seed", tags=["seed"])


@router.post("/replay")
def replay(body: SeedReplayIn, store=Depends(get_store), llm_client=Depends(get_llm_client)):
    return seed_service.replay(
        store, llm_client, mode=body.mode,
        geofence_radius_km=body.geofence_radius_km,
        max_cluster_span_km=body.max_cluster_span_km,
    )
