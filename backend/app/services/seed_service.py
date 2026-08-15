"""FR-701-702: seed/replay. docs/design.md §4.8.

A minimal placeholder batch ships here so BE-18's `POST /api/seed/replay`
endpoint is real and exercisable end-to-end now; BE-19/#24 replaces
_PLACEHOLDER_BATCH with the full ~50-request synthetic batch (multi-device
event clusters, a single-device fraud cluster, standalone unrelated
requests) and adds the dedicated cascading-wipe tests.
"""
from __future__ import annotations

from typing import Literal, NamedTuple

from app.models.domain import Location
from app.services import intake_service
from app.store.memory_store import InMemoryStore


class SeedRequest(NamedTuple):
    need_description: str
    lat: float
    lng: float
    device_fingerprint_id: str


_PLACEHOLDER_BATCH: list[SeedRequest] = [
    SeedRequest("Trapped under rubble, can't move my leg", 12.340, 56.780, "dev_seed_1"),
    SeedRequest("Building collapsed near us, people trapped", 12.3401, 56.7801, "dev_seed_2"),
    SeedRequest("Need blankets for winter, otherwise safe", 12.500, 56.900, "dev_seed_3"),
]


def replay(store: InMemoryStore, llm_client, mode: Literal["reset", "append"],
           geofence_radius_km: float | None = None, max_cluster_span_km: float | None = None) -> dict:
    wiped = False
    if mode == "reset":
        store.reset()  # FR-702: full cascading wipe
        if geofence_radius_km is not None:
            store.config.geofence_radius_km = geofence_radius_km
        if max_cluster_span_km is not None:
            store.config.max_cluster_span_km = max_cluster_span_km
        wiped = True

    submitted = 0
    for seed in _PLACEHOLDER_BATCH:
        intake_service.submit(
            store, llm_client,
            need_description=seed.need_description,
            location=Location(lat=seed.lat, lng=seed.lng),
            device_fingerprint_id=seed.device_fingerprint_id,
        )
        submitted += 1

    return {"mode": mode, "requests_submitted": submitted, "wiped": wiped}
