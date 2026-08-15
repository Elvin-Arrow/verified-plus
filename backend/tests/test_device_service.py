"""BE-14 (HIGH RISK): reject_and_flag_device, reject_all_quarantined.
docs/design.md §4.4; FR-306/FR-308/FR-503/FR-407.
"""
import pytest

from app.models.domain import DeviceFingerprint, Event, EventStatus, Location, Request, RequestStatus
from app.services.device_service import device_service
from app.store.memory_store import InMemoryStore


def make_request(store, id_, status, event_id=None, device="dev_1", verified=False):
    r = Request(id=id_, need_description=f"need-{id_}", location=Location(0, 0),
                device_fingerprint_id=device, status=status, event_id=event_id, verified=verified)
    store.requests[id_] = r
    return r


def make_event(store, id_, member_ids=None, status=EventStatus.CANDIDATE):
    e = Event(id=id_, status=status, representative_location=Location(0, 0),
              member_request_ids=list(member_ids or []))
    store.events[id_] = e
    return e


# --- reject_and_flag_device ---

def test_reject_and_flag_device_sets_flag_and_rejects_cards_members():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_x")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_y")
    r3 = make_request(store, "r3", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_x")
    make_event(store, "evt_1", member_ids=["r1", "r2", "r3"])

    result = device_service.reject_and_flag_device(store, "evt_1", "dev_x", actor="coordinator_1")

    assert store.devices["dev_x"].device_flag is True
    assert r1.status == RequestStatus.REJECTED
    assert r3.status == RequestStatus.REJECTED
    assert r1.event_id is None and r3.event_id is None
    assert "r1" in store.devices["dev_x"].confirmed_fraud_request_ids
    assert "r3" in store.devices["dev_x"].confirmed_fraud_request_ids
    assert set(result["rejected_request_ids"]) == {"r1", "r3"}
    # r2 is the sole survivor -- membership dropped to 1, so the Event
    # auto-dissolves and r2 reverts to standalone (FR-504b), untouched otherwise
    assert r2.status == RequestStatus.STANDALONE
    assert r2.event_id is None


def test_reject_and_flag_device_sweeps_other_active_requests_from_same_device():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_x")
    other = make_event(store, "evt_1", member_ids=["r1"])
    elsewhere = make_request(store, "r_elsewhere", RequestStatus.STANDALONE, device="dev_x")

    result = device_service.reject_and_flag_device(store, "evt_1", "dev_x", actor="coordinator_1")

    assert elsewhere.status == RequestStatus.QUARANTINED
    assert "r_elsewhere" in result["quarantined_request_ids"]


def test_reject_and_flag_device_does_not_sweep_terminal_requests():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_x")
    make_event(store, "evt_1", member_ids=["r1"])
    already_dispatched = make_request(store, "r_done", RequestStatus.DISPATCHED, device="dev_x")
    already_rejected = make_request(store, "r_gone", RequestStatus.REJECTED, device="dev_x")

    device_service.reject_and_flag_device(store, "evt_1", "dev_x", actor="coordinator_1")

    assert already_dispatched.status == RequestStatus.DISPATCHED
    assert already_rejected.status == RequestStatus.REJECTED


def test_reject_and_flag_device_dissolves_event_when_dropping_to_one_member():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_x")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_y")
    make_event(store, "evt_1", member_ids=["r1", "r2"])

    result = device_service.reject_and_flag_device(store, "evt_1", "dev_x", actor="coordinator_1")

    assert "evt_1" not in store.events
    assert result["event_dissolved"] is True
    assert result["event"] is None
    assert r2.event_id is None
    assert r2.status == RequestStatus.STANDALONE


def test_reject_and_flag_device_returns_event_when_still_valid():
    store = InMemoryStore()
    for i, dev in enumerate(["dev_x", "dev_y", "dev_z"]):
        make_request(store, f"r{i}", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device=dev)
    make_event(store, "evt_1", member_ids=["r0", "r1", "r2"])

    result = device_service.reject_and_flag_device(store, "evt_1", "dev_x", actor="coordinator_1")

    assert result["event_dissolved"] is False
    assert result["event"] is not None
    assert len(result["event"].member_request_ids) == 2


def test_reject_and_flag_device_regression_two_sequential_calls_different_devices():
    """docs/testing-spec.md §4.3 Invariant 1's named regression: a
    3-member Event, two members from different devices rejected in two
    separate reject_and_flag_device calls, must be gone after the second
    call -- not silently sitting at 1 member."""
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_a")
    make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_b")
    make_request(store, "r3", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_c")
    make_event(store, "evt_1", member_ids=["r1", "r2", "r3"])

    device_service.reject_and_flag_device(store, "evt_1", "dev_a", actor="coordinator_1")
    assert "evt_1" in store.events
    assert len(store.events["evt_1"].member_request_ids) == 2

    device_service.reject_and_flag_device(store, "evt_1", "dev_b", actor="coordinator_1")

    assert "evt_1" not in store.events


def test_reject_and_flag_device_logs_action():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_x")
    make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_y")
    make_event(store, "evt_1", member_ids=["r1", "r2"])
    device_service.reject_and_flag_device(store, "evt_1", "dev_x", actor="coordinator_1")
    log = [a for a in store.actions if a.action_type == "reject_flag_device"]
    assert len(log) == 1
    assert log[0].note == "device=dev_x"


def test_reject_and_flag_device_unknown_event_raises_lookup():
    store = InMemoryStore()
    store.devices["dev_x"] = DeviceFingerprint(id="dev_x")
    with pytest.raises(KeyError):
        device_service.reject_and_flag_device(store, "evt_missing", "dev_x", actor="c")


# --- FR-107/308: subsequent submissions from a flagged device auto-quarantine ---

def test_device_flag_persists_for_future_lookups():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_x")
    make_event(store, "evt_1", member_ids=["r1"] * 1 + ["r_other"])
    make_request(store, "r_other", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_other")

    device_service.reject_and_flag_device(store, "evt_1", "dev_x", actor="coordinator_1")

    assert store.devices["dev_x"].device_flag is True


# --- reject_all_quarantined ---

def test_reject_all_quarantined_rejects_only_that_devices_quarantined_requests():
    store = InMemoryStore()
    q1 = make_request(store, "q1", RequestStatus.QUARANTINED, device="dev_x")
    q2 = make_request(store, "q2", RequestStatus.QUARANTINED, device="dev_x")
    other_device = make_request(store, "q3", RequestStatus.QUARANTINED, device="dev_y")

    ids = device_service.reject_all_quarantined(store, "dev_x", actor="coordinator_1")

    assert set(ids) == {"q1", "q2"}
    assert q1.status == RequestStatus.REJECTED
    assert q2.status == RequestStatus.REJECTED
    assert other_device.status == RequestStatus.QUARANTINED


def test_reject_all_quarantined_does_not_touch_device_flag():
    store = InMemoryStore()
    store.devices["dev_x"] = DeviceFingerprint(id="dev_x", device_flag=True)
    make_request(store, "q1", RequestStatus.QUARANTINED, device="dev_x")
    device_service.reject_all_quarantined(store, "dev_x", actor="coordinator_1")
    assert store.devices["dev_x"].device_flag is True  # already true, untouched (not a re-confirmation)


def test_reject_all_quarantined_logs_distinct_action_type_from_reject_flag_device():
    store = InMemoryStore()
    make_request(store, "q1", RequestStatus.QUARANTINED, device="dev_x")
    device_service.reject_all_quarantined(store, "dev_x", actor="coordinator_1")
    log = [a for a in store.actions if a.action_type == "reject_quarantined_group"]
    assert len(log) == 1
    assert "reject_flag_device" not in [a.action_type for a in store.actions]


def test_reject_all_quarantined_with_no_quarantined_requests_returns_empty():
    store = InMemoryStore()
    ids = device_service.reject_all_quarantined(store, "dev_nonexistent", actor="coordinator_1")
    assert ids == []
