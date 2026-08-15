"""BE-07: POST /api/requests handler minus clustering. docs/design.md §4.1 steps 1-5."""
from __future__ import annotations

from datetime import datetime, timezone

from app.geo import haversine_km
from app.llm.client import EmbeddingError, LLMClient, LLMTimeoutError
from app.llm.prompts import urgency_and_match_prompt
from app.models.domain import DeviceFingerprint, Location, Request, RequestStatus
from app.services import clustering_service, matching_service
from app.store.memory_store import InMemoryStore


class ValidationError(Exception):
    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def _validate(need_description: str | None, location: Location | None) -> None:
    if location is None or location.lat is None or location.lng is None:
        raise ValidationError("location {lat, lng} is required", field="location")
    if not need_description or not need_description.strip():
        raise ValidationError("need_description must not be empty", field="need_description")


def get_or_create_device_fingerprint(store: InMemoryStore, device_fingerprint_id: str) -> DeviceFingerprint:
    device = store.devices.get(device_fingerprint_id)
    if device is None:
        device = DeviceFingerprint(id=device_fingerprint_id)
        store.devices[device_fingerprint_id] = device
    return device


def submit(
    store: InMemoryStore,
    llm_client: LLMClient,
    need_description: str,
    location: Location,
    device_fingerprint_id: str,
    photo_url: str | None = None,
) -> Request:
    """FR-101-107, FR-201-208, FR-301-302. Raises ValidationError for
    FR-101/102 violations; every other failure mode (LLM/embedding) is
    absorbed into the returned Request per NFR-103 (never an exception)."""
    _validate(need_description, location)  # step 1

    device = get_or_create_device_fingerprint(store, device_fingerprint_id)  # step 2

    request_id = store.new_id("req")
    request = Request(
        id=request_id,
        need_description=need_description,
        location=location,
        device_fingerprint_id=device_fingerprint_id,
        photo_url=photo_url,
    )

    if device.device_flag:  # step 3: FR-107/308 — accept, but skip the pipeline entirely
        request.status = RequestStatus.QUARANTINED
        store.requests[request_id] = request
        return request

    store.requests[request_id] = request  # step 4

    try:  # step 5
        embedding = llm_client.embed(need_description)
        request.embedding = embedding

        candidates = matching_service.geofenced_candidates(store, request)
        top5 = matching_service.top_k_cosine(embedding, candidates, k=5)
        distances = {c.id: haversine_km(request.location, c.location) for c in top5}

        prompt = urgency_and_match_prompt(
            request,
            top5,
            distances,
            urgency_buffer=store.urgency_calibration_buffer,
            match_buffer=store.match_calibration_buffer,
        )
        llm_result = llm_client.complete(prompt, key=need_description)  # FakeLLMClient accepts `key`

        request.urgency_score = llm_result.urgency_score
        request.urgency_reasoning = llm_result.urgency_reasoning
        request.match_reasons = llm_result.matches
    except (LLMTimeoutError, EmbeddingError):  # NFR-103
        request.urgency_score = None
        request.urgency_reasoning = None
        request.status = RequestStatus.STANDALONE
        return request  # do NOT proceed to clustering with a failed match result

    clustering_service.assign(store, request, llm_result.matches)  # step 6
    return request
