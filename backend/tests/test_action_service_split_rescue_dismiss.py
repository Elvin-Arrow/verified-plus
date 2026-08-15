"""BE-13: split_out, rescue, dismiss_cluster. docs/design.md §4.5b/§4.6."""
import pytest

from app.models.domain import Event, EventStatus, Location, Request, RequestStatus
from app.services.action_service import InvalidStateTransition, action_service
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse


def make_request(store, id_, status, event_id=None, verified=False, device="dev_1", text=None):
    r = Request(id=id_, need_description=text or f"need-{id_}", location=Location(0, 0),
                device_fingerprint_id=device, status=status, event_id=event_id, verified=verified)
    store.requests[id_] = r
    return r


def make_event(store, id_, member_ids=None, pending_ids=None, status=EventStatus.CANDIDATE):
    e = Event(id=id_, status=status, representative_location=Location(0, 0),
              member_request_ids=list(member_ids or []), pending_member_request_ids=list(pending_ids or []))
    store.events[id_] = e
    return e


def make_llm():
    client = FakeLLMClient()
    return client


# --- split_out ---

def test_split_out_ejects_member_reverts_to_standalone_unverified_false():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", text="text one")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", text="text two")
    make_event(store, "evt_1", member_ids=["r1", "r2"])
    client.script("text one", ScriptedResponse())  # rerun looks up by need_description

    action_service.split_out(store, client, "r1", actor="coordinator_1")

    assert r1.event_id is None
    assert r1.status == RequestStatus.STANDALONE
    assert r1.verified is False


def test_split_out_on_already_verified_members_event_resets_verified_to_false():
    """docs/data-model.md §3.3's explicit correction: this is the opposite
    case from dissolution (which preserves the sole survivor's verified
    state) -- the request being split OUT was judged not to belong, so it
    loses any prior approval."""
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True, text="a")
    r2 = make_request(store, "r2", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True, text="b")
    make_event(store, "evt_1", member_ids=["r1", "r2"], status=EventStatus.VERIFIED)
    client.script("a", ScriptedResponse())

    action_service.split_out(store, client, "r1", actor="coordinator_1")

    assert r1.status == RequestStatus.STANDALONE
    assert r1.verified is False


def test_split_out_with_no_event_id_raises():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.STANDALONE)
    with pytest.raises(InvalidStateTransition):
        action_service.split_out(store, client, "r1", actor="coordinator_1")


def test_split_out_may_dissolve_event_down_to_sole_member():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", text="a")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", text="b")
    make_event(store, "evt_1", member_ids=["r1", "r2"])
    client.script("a", ScriptedResponse())

    action_service.split_out(store, client, "r1", actor="coordinator_1")

    assert "evt_1" not in store.events
    assert r2.event_id is None
    assert r2.status == RequestStatus.STANDALONE


def test_split_out_records_duplicate_correction_from_sibling_text():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", text="text one")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", text="text two")
    make_event(store, "evt_1", member_ids=["r1", "r2"])
    client.script("text one", ScriptedResponse())

    action_service.split_out(store, client, "r1", actor="coordinator_1")

    assert len(store.match_calibration_buffer) == 1
    entry = store.match_calibration_buffer[0]
    assert entry["a"] == "text one"
    assert entry["b"] == "text two"


def test_split_out_logs_action():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1", "r2"])
    client.script("need-r1", ScriptedResponse())
    action_service.split_out(store, client, "r1", actor="coordinator_1")
    log = [a for a in store.actions if a.action_type == "split_out"]
    assert len(log) == 1 and log[0].target_id == "r1"


# --- rescue ---

def test_rescue_reverts_to_standalone_and_resets_verified():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.QUARANTINED, verified=True)
    client.script("need-r1", ScriptedResponse())
    action_service.rescue(store, client, "r1", actor="coordinator_1")
    assert r1.status == RequestStatus.STANDALONE
    assert r1.verified is False


def test_rescue_on_non_quarantined_raises():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.STANDALONE)
    with pytest.raises(InvalidStateTransition):
        action_service.rescue(store, client, "r1", actor="coordinator_1")


def test_rescue_logs_action():
    store = InMemoryStore()
    client = make_llm()
    r1 = make_request(store, "r1", RequestStatus.QUARANTINED)
    client.script("need-r1", ScriptedResponse())
    action_service.rescue(store, client, "r1", actor="coordinator_1")
    log = [a for a in store.actions if a.action_type == "rescue_from_quarantine"]
    assert len(log) == 1


# --- dismiss_cluster ---

def test_dismiss_cluster_reverts_all_members_to_standalone_no_device_flag():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_a")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_b")
    make_event(store, "evt_1", member_ids=["r1", "r2"])

    reverted = action_service.dismiss_cluster(store, "evt_1", actor="coordinator_1")

    assert set(reverted) == {"r1", "r2"}
    assert "evt_1" not in store.events
    assert r1.status == RequestStatus.STANDALONE and r1.event_id is None
    assert r2.status == RequestStatus.STANDALONE and r2.event_id is None
    assert "dev_a" not in store.devices or store.devices["dev_a"].device_flag is False
    assert "dev_b" not in store.devices or store.devices["dev_b"].device_flag is False


def test_dismiss_cluster_on_verified_event_raises():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1"], status=EventStatus.VERIFIED)
    with pytest.raises(InvalidStateTransition):
        action_service.dismiss_cluster(store, "evt_1", actor="coordinator_1")


def test_dismiss_cluster_logs_action():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1", "r2"])
    action_service.dismiss_cluster(store, "evt_1", actor="coordinator_1")
    log = [a for a in store.actions if a.action_type == "dismiss_cluster"]
    assert len(log) == 1 and log[0].target_id == "evt_1"
