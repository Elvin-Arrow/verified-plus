"""BE-18: contract tests for every endpoint in docs/api-spec.md §8's index.

Per docs/testing-spec.md §3.2's flagship cases plus one representative
happy-path + error-path per endpoint; full schema-driven coverage is
TI-05's job (schemathesis, next).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.domain import DeviceFingerprint, Event, EventStatus, Location, Request, RequestStatus
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse


def make_client():
    store = InMemoryStore()
    llm = FakeLLMClient()
    app = create_app(store=store, llm_client=llm)
    return TestClient(app), store, llm


# --- POST /api/requests: the two flagship cases ---

def test_submit_from_flagged_device_returns_201_quarantined_never_calls_llm():
    client, store, llm = make_client()
    store.devices["dev_x"] = DeviceFingerprint(id="dev_x", device_flag=True)
    resp = client.post("/api/requests", json={
        "need_description": "need water", "location": {"lat": 1.0, "lng": 1.0},
        "device_fingerprint_id": "dev_x",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "quarantined"
    assert body["urgency_score"] is None
    assert body["event_id"] is None
    assert llm.calls == []


def test_submit_on_llm_failure_returns_201_not_500():
    client, store, llm = make_client()
    llm.script("flaky text", ScriptedResponse(fail=True))
    resp = client.post("/api/requests", json={
        "need_description": "flaky text", "location": {"lat": 1.0, "lng": 1.0},
        "device_fingerprint_id": "dev_1",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["urgency_score"] is None
    assert body["status"] == "standalone"


def test_submit_happy_path():
    client, store, llm = make_client()
    llm.script("need water", ScriptedResponse(urgency_score=4, urgency_reasoning="serious"))
    resp = client.post("/api/requests", json={
        "need_description": "need water", "location": {"lat": 1.0, "lng": 1.0},
        "device_fingerprint_id": "dev_1",
    })
    assert resp.status_code == 201
    assert resp.json()["urgency_score"] == 4


def test_submit_missing_location_returns_400_validation_error():
    client, store, llm = make_client()
    resp = client.post("/api/requests", json={
        "need_description": "x", "device_fingerprint_id": "dev_1",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_empty_need_description_returns_400():
    client, store, llm = make_client()
    resp = client.post("/api/requests", json={
        "need_description": "   ", "location": {"lat": 1.0, "lng": 1.0}, "device_fingerprint_id": "dev_1",
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- queues ---

def test_intake_inbox_empty_returns_200_with_empty_arrays():
    client, store, llm = make_client()
    resp = client.get("/api/intake-inbox")
    assert resp.status_code == 200
    assert resp.json() == {"needs_manual_triage": [], "sorted": []}


def test_dispatch_queue_reachable():
    client, store, llm = make_client()
    resp = client.get("/api/dispatch-queue")
    assert resp.status_code == 200
    assert resp.json() == {"sorted": []}


def test_quarantine_reachable():
    client, store, llm = make_client()
    resp = client.get("/api/quarantine")
    assert resp.status_code == 200
    assert resp.json() == {"groups": []}


def test_archive_reachable():
    client, store, llm = make_client()
    resp = client.get("/api/archive")
    assert resp.status_code == 200
    assert resp.json() == {"events": [], "standalone_requests": []}


# --- event actions ---

def _seed_event(store, member_ids=("r1", "r2"), status=EventStatus.CANDIDATE):
    for i, rid in enumerate(member_ids):
        store.requests[rid] = Request(
            id=rid, need_description=f"need-{rid}", location=Location(0, 0),
            device_fingerprint_id=f"dev_{i}", status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1",
            urgency_score=3,
        )
    store.events["evt_1"] = Event(id="evt_1", status=status, representative_location=Location(0, 0),
                                   member_request_ids=list(member_ids))


def test_verify_event_happy_path_and_conflict():
    client, store, llm = make_client()
    _seed_event(store)
    resp = client.post("/api/events/evt_1/verify", json={"actor": "c1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"

    resp2 = client.post("/api/events/evt_1/verify", json={"actor": "c1"})
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_verify_event_not_found_returns_404():
    client, store, llm = make_client()
    resp = client.post("/api/events/evt_missing/verify", json={"actor": "c1"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_dispatch_event_requires_verified_first():
    client, store, llm = make_client()
    _seed_event(store)
    resp = client.post("/api/events/evt_1/dispatch", json={"actor": "c1"})
    assert resp.status_code == 409


def test_dismiss_event_happy_path():
    client, store, llm = make_client()
    _seed_event(store)
    resp = client.post("/api/events/evt_1/dismiss", json={"actor": "c1"})
    assert resp.status_code == 200
    assert set(resp.json()["reverted_request_ids"]) == {"r1", "r2"}


def test_reject_and_flag_device_returns_null_event_on_dissolution():
    client, store, llm = make_client()
    _seed_event(store)
    resp = client.post("/api/events/evt_1/devices/dev_0/reject-and-flag", json={"actor": "c1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_dissolved"] is True
    assert body["event"] is None


def test_get_event_detail():
    client, store, llm = make_client()
    _seed_event(store)
    resp = client.get("/api/events/evt_1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "evt_1"
    assert "action_history" in resp.json()


def test_get_event_not_found():
    client, store, llm = make_client()
    resp = client.get("/api/events/evt_missing")
    assert resp.status_code == 404


# --- standalone actions ---

def test_verify_standalone_and_get_detail():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0),
                                    device_fingerprint_id="d1", status=RequestStatus.STANDALONE)
    resp = client.post("/api/requests/r1/verify-standalone", json={"actor": "c1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "dispatched"

    detail = client.get("/api/requests/r1")
    assert detail.status_code == 200
    assert "action_history" in detail.json()


def test_reject_standalone_on_wrong_state_409():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0),
                                    device_fingerprint_id="d1", status=RequestStatus.QUARANTINED)
    resp = client.post("/api/requests/r1/reject-standalone", json={"actor": "c1"})
    assert resp.status_code == 409


def test_get_request_not_found_404():
    client, store, llm = make_client()
    resp = client.get("/api/requests/req_missing")
    assert resp.status_code == 404


def test_override_urgency():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0),
                                    device_fingerprint_id="d1", urgency_score=2)
    resp = client.post("/api/requests/r1/override-urgency",
                        json={"actor": "c1", "corrected_score": 5, "reason": "trapped"})
    assert resp.status_code == 200
    assert resp.json()["urgency_score"] == 5
    assert resp.json()["original_urgency_score"] == 2


def test_override_urgency_out_of_range_returns_400():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0),
                                    device_fingerprint_id="d1", urgency_score=2)
    resp = client.post("/api/requests/r1/override-urgency", json={"actor": "c1", "corrected_score": 9})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_merge_both_targets_set_returns_400():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0), device_fingerprint_id="d1")
    resp = client.post("/api/requests/r1/merge",
                        json={"actor": "c1", "target_event_id": "evt_1", "target_request_id": "req_2"})
    assert resp.status_code == 400


def test_merge_neither_target_set_returns_400():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0), device_fingerprint_id="d1")
    resp = client.post("/api/requests/r1/merge", json={"actor": "c1"})
    assert resp.status_code == 400


def test_merge_happy_path():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0), device_fingerprint_id="d1")
    store.requests["r2"] = Request(id="r2", need_description="y", location=Location(1, 1), device_fingerprint_id="d2")
    store.suggested_merges.append({"request_id": "r1", "request_id_2": "r2", "distance_km": 2.0})
    resp = client.post("/api/requests/r1/merge", json={"actor": "c1", "target_request_id": "r2"})
    assert resp.status_code == 200
    assert set(m["id"] for m in resp.json()["members"]) == {"r1", "r2"}


def test_split_out_and_rescue():
    client, store, llm = make_client()
    _seed_event(store)
    llm.script("need-r1", ScriptedResponse())
    resp = client.post("/api/requests/r1/split-out", json={"actor": "c1"})
    assert resp.status_code == 200
    assert resp.json()["request"]["status"] == "standalone"

    store.requests["r_q"] = Request(id="r_q", need_description="need-r_q", location=Location(0, 0),
                                     device_fingerprint_id="d9", status=RequestStatus.QUARANTINED)
    llm.script("need-r_q", ScriptedResponse())
    resp2 = client.post("/api/requests/r_q/rescue", json={"actor": "c1"})
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "standalone"


def test_split_out_no_event_returns_409():
    client, store, llm = make_client()
    store.requests["r1"] = Request(id="r1", need_description="x", location=Location(0, 0), device_fingerprint_id="d1")
    resp = client.post("/api/requests/r1/split-out", json={"actor": "c1"})
    assert resp.status_code == 409


# --- quarantine reject-all ---

def test_quarantine_reject_all_happy_path_and_empty_404():
    client, store, llm = make_client()
    store.requests["q1"] = Request(id="q1", need_description="x", location=Location(0, 0),
                                    device_fingerprint_id="dev_q", status=RequestStatus.QUARANTINED)
    resp = client.post("/api/quarantine/dev_q/reject-all", json={"actor": "c1"})
    assert resp.status_code == 200
    assert resp.json()["rejected_request_ids"] == ["q1"]

    resp2 = client.post("/api/quarantine/dev_q/reject-all", json={"actor": "c1"})
    assert resp2.status_code == 404


# --- seed/replay ---

def test_seed_replay_reset_requires_mode():
    client, store, llm = make_client()
    resp = client.post("/api/seed/replay", json={})
    assert resp.status_code == 400


def test_seed_replay_reset_happy_path():
    from app.services.seed_service import SEED_BATCH

    client, store, llm = make_client()
    for seed in SEED_BATCH:
        llm.script(seed.need_description, ScriptedResponse(urgency_score=3, urgency_reasoning="ok"))
    resp = client.post("/api/seed/replay", json={"mode": "reset"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "reset"
    assert body["wiped"] is True
    assert body["requests_submitted"] == len(SEED_BATCH)
