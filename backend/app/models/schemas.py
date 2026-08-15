"""BE-18: Pydantic request-body models for the API layer. docs/api-spec.md."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LocationIn(BaseModel):
    lat: float
    lng: float


class SubmitRequestIn(BaseModel):
    need_description: str
    location: LocationIn
    photo_url: str | None = None
    device_fingerprint_id: str


class ActorIn(BaseModel):
    actor: str


class OverrideUrgencyIn(BaseModel):
    actor: str
    corrected_score: int = Field(ge=1, le=5)
    reason: str | None = None


class MergeIn(BaseModel):
    actor: str
    target_event_id: str | None = None
    target_request_id: str | None = None


class SeedReplayIn(BaseModel):
    mode: Literal["reset", "append"]
    geofence_radius_km: float | None = None
    max_cluster_span_km: float | None = None
