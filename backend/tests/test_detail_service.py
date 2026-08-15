"""BE-17: detail reads. docs/api-spec.md §7; FR-506, FR-602."""
import pytest

from app.models.domain import CoordinatorAction, DeviceFingerprint, Event, EventStatus, Location, Request, RequestStatus
from app.services import detail_service
from app.store.memory_store import InMemoryStore


def make_request(store, id_, **kwargs):
    r = Request(id=id_, need_description=f"need-{id_}", location=Location(0, 0),
                device_fingerprint_id=kwargs.pop("device", "dev_1"), **kwargs)
    store.requests[id_] = r
    return r


def test_request_detail_includes_action_history_filtered_by_target():
    store = InMemoryStore()
    r = make_request(store, "r1")
    store.actions.append(CoordinatorAction(id="act_1", actor="c1", action_type="override_urgency", target_id="r1"))
    store.actions.append(CoordinatorAction(id="act_2", actor="c1", action_type="verify_event", target_id="evt_other"))

    detail = detail_service.request_detail(store, "r1")

    assert detail["request"].id == "r1"
    assert [a.id for a in detail["action_history"]] == ["act_1"]


def test_request_detail_includes_suggested_merges_filtered_by_request_id():
    store = InMemoryStore()
    make_request(store, "r1")
    store.suggested_merges.append({"request_id": "r1", "event_id": "evt_far", "distance_km": 1.9})
    store.suggested_merges.append({"request_id": "r_other", "event_id": "evt_x", "distance_km": 2.0})

    detail = detail_service.request_detail(store, "r1")

    assert len(detail["suggested_merges"]) == 1
    assert detail["suggested_merges"][0]["event_id"] == "evt_far"


def test_request_detail_includes_device_flagged_marker():
    store = InMemoryStore()
    store.devices["dev_x"] = DeviceFingerprint(id="dev_x", device_flag=True)
    make_request(store, "r1", device="dev_x")

    detail = detail_service.request_detail(store, "r1")

    assert detail["device_flagged"] is True


def test_request_detail_unknown_id_raises_keyerror():
    store = InMemoryStore()
    with pytest.raises(KeyError):
        detail_service.request_detail(store, "req_missing")


def test_event_detail_includes_members_pending_members_and_action_history():
    store = InMemoryStore()
    r1 = make_request(store, "r1", status=RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    rp = make_request(store, "rp", status=RequestStatus.PENDING_ADDITION, event_id="evt_1")
    store.events["evt_1"] = Event(id="evt_1", status=EventStatus.VERIFIED,
                                   representative_location=Location(0, 0),
                                   member_request_ids=["r1"], pending_member_request_ids=["rp"])
    store.actions.append(CoordinatorAction(id="act_1", actor="c1", action_type="verify_event", target_id="evt_1"))
    store.actions.append(CoordinatorAction(id="act_2", actor="c1", action_type="override_urgency", target_id="r1"))

    detail = detail_service.event_detail(store, "evt_1")

    assert [m.id for m in detail["members"]] == ["r1"]
    assert [m.id for m in detail["pending_members"]] == ["rp"]
    assert [a.id for a in detail["action_history"]] == ["act_1"]  # not act_2 -- that's r1's own log


def test_event_detail_unknown_id_raises_keyerror():
    store = InMemoryStore()
    with pytest.raises(KeyError):
        detail_service.event_detail(store, "evt_missing")
