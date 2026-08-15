"""Domain dataclasses/enums mirroring docs/spec.md §6 and docs/data-model.md §2.

BE-01. No behavior here — pure data. See docs/design.md §3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RequestStatus(str, Enum):
    STANDALONE = "standalone"
    IN_CANDIDATE_EVENT = "in_candidate_event"
    PENDING_ADDITION = "pending_addition"
    IN_VERIFIED_EVENT = "in_verified_event"
    DISPATCHED = "dispatched"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class EventStatus(str, Enum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    DISPATCHED = "dispatched"


class ActionType(str, Enum):
    VERIFY_EVENT = "verify_event"
    APPROVE_PENDING = "approve_pending"
    APPROVE_DISPATCH = "approve_dispatch"
    REJECT_FLAG_DEVICE = "reject_flag_device"
    DISMISS_CLUSTER = "dismiss_cluster"
    SPLIT_OUT = "split_out"
    RESCUE_FROM_QUARANTINE = "rescue_from_quarantine"
    VERIFY_STANDALONE = "verify_standalone"
    REJECT_STANDALONE = "reject_standalone"
    DISPATCH_STANDALONE = "dispatch_standalone"
    OVERRIDE_URGENCY = "override_urgency"
    MANUAL_MERGE = "manual_merge"
    REJECT_QUARANTINED_GROUP = "reject_quarantined_group"


@dataclass
class Location:
    lat: float
    lng: float


@dataclass
class MatchResult:
    """One LLM-judged candidate outcome from FR-204's per-candidate match call."""

    candidate_id: str
    is_match: bool
    reason: str


@dataclass
class Request:
    id: str
    need_description: str
    location: Location
    device_fingerprint_id: str
    photo_url: str | None = None
    submitted_at: datetime = field(default_factory=utcnow)
    urgency_score: int | None = None
    urgency_reasoning: str | None = None
    original_urgency_score: int | None = None
    match_reasons: list[MatchResult] = field(default_factory=list)
    event_id: str | None = None
    status: RequestStatus = RequestStatus.STANDALONE
    verified: bool = False
    embedding: list[float] | None = None


@dataclass
class Event:
    id: str
    member_request_ids: list[str] = field(default_factory=list)
    pending_member_request_ids: list[str] = field(default_factory=list)
    status: EventStatus = EventStatus.CANDIDATE
    verified_by: str | None = None
    verified_at: datetime | None = None
    representative_location: Location | None = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class DeviceFingerprint:
    id: str
    first_seen_at: datetime = field(default_factory=utcnow)
    device_flag: bool = False
    confirmed_fraud_request_ids: list[str] = field(default_factory=list)


@dataclass
class CoordinatorAction:
    id: str
    actor: str
    action_type: str
    target_id: str
    timestamp: datetime = field(default_factory=utcnow)
    note: str | None = None


@dataclass
class SessionConfig:
    """FR-208: configurable spatial parameters, fixed defaults per §3."""

    geofence_radius_km: float = 1.0
    max_cluster_span_km: float = 1.5
    calibration_buffer_n: int = 5
