"""BE-01: construction/defaults unit tests for domain dataclasses/enums."""
from app.models.domain import (
    ActionType,
    CoordinatorAction,
    DeviceFingerprint,
    Event,
    EventStatus,
    Location,
    MatchResult,
    Request,
    RequestStatus,
    SessionConfig,
)


def test_request_defaults():
    r = Request(
        id="req_1",
        need_description="need water",
        location=Location(lat=1.0, lng=2.0),
        device_fingerprint_id="dev_1",
    )
    assert r.status == RequestStatus.STANDALONE
    assert r.verified is False
    assert r.urgency_score is None
    assert r.original_urgency_score is None
    assert r.match_reasons == []
    assert r.event_id is None
    assert r.embedding is None
    assert r.photo_url is None


def test_event_defaults():
    e = Event(id="evt_1")
    assert e.status == EventStatus.CANDIDATE
    assert e.member_request_ids == []
    assert e.pending_member_request_ids == []
    assert e.verified_by is None
    assert e.verified_at is None


def test_device_fingerprint_defaults():
    d = DeviceFingerprint(id="dev_1")
    assert d.device_flag is False
    assert d.confirmed_fraud_request_ids == []


def test_coordinator_action_construction():
    a = CoordinatorAction(
        id="act_1", actor="coordinator_1", action_type=ActionType.VERIFY_EVENT.value,
        target_id="evt_1",
    )
    assert a.note is None
    assert a.action_type == "verify_event"


def test_session_config_defaults_match_fr208():
    cfg = SessionConfig()
    assert cfg.geofence_radius_km == 1.0
    assert cfg.max_cluster_span_km == 1.5
    assert cfg.calibration_buffer_n == 5


def test_two_requests_get_independent_mutable_defaults():
    r1 = Request(id="req_1", need_description="a", location=Location(0, 0), device_fingerprint_id="d1")
    r2 = Request(id="req_2", need_description="b", location=Location(0, 0), device_fingerprint_id="d2")
    r1.match_reasons.append(MatchResult(candidate_id="x", is_match=True, reason="r"))
    assert r2.match_reasons == []
