"""BE-12: verification actions. docs/design.md §4.2b.

verify_event, approve_pending, dispatch_event, reject_standalone,
verify_standalone, dispatch_standalone -- plus their negative
(illegal-transition) cases per docs/testing-spec.md §4.1/§4.2.
"""
import pytest

from app.models.domain import Event, EventStatus, Location, Request, RequestStatus
from app.services.action_service import InvalidStateTransition, action_service
from app.store.memory_store import InMemoryStore


def make_request(store, id_, status, event_id=None, verified=False, device="dev_1"):
    r = Request(id=id_, need_description=f"need-{id_}", location=Location(0, 0),
                device_fingerprint_id=device, status=status, event_id=event_id, verified=verified)
    store.requests[id_] = r
    return r


def make_event(store, id_, member_ids=None, pending_ids=None, status=EventStatus.CANDIDATE):
    e = Event(id=id_, status=status, representative_location=Location(0, 0),
              member_request_ids=list(member_ids or []), pending_member_request_ids=list(pending_ids or []))
    store.events[id_] = e
    return e


# --- verify_event: candidate -> verified, members promoted ---

def test_verify_event_promotes_current_members_only():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1", "r2"])

    action_service.verify_event(store, "evt_1", actor="coordinator_1")

    evt = store.events["evt_1"]
    assert evt.status == EventStatus.VERIFIED
    assert evt.verified_by == "coordinator_1"
    assert evt.verified_at is not None
    assert r1.status == RequestStatus.IN_VERIFIED_EVENT and r1.verified is True
    assert r2.status == RequestStatus.IN_VERIFIED_EVENT and r2.verified is True
    log = [a for a in store.actions if a.action_type == "verify_event"]
    assert len(log) == 1 and log[0].target_id == "evt_1"


def test_verify_event_on_already_verified_raises_invalid_state_transition():
    store = InMemoryStore()
    make_event(store, "evt_1", member_ids=["r1"], status=EventStatus.VERIFIED)
    make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1")
    with pytest.raises(InvalidStateTransition):
        action_service.verify_event(store, "evt_1", actor="coordinator_1")


def test_verify_event_verified_by_and_at_untouched_by_later_dispatch():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1", "r2"])
    action_service.verify_event(store, "evt_1", actor="coordinator_1")
    verified_at = store.events["evt_1"].verified_at
    verified_by = store.events["evt_1"].verified_by

    action_service.dispatch_event(store, "evt_1", actor="coordinator_2")

    assert store.events["evt_1"].verified_at == verified_at
    assert store.events["evt_1"].verified_by == verified_by


# --- approve_pending: pending_addition -> in_verified_event ---

def test_approve_pending_promotes_and_clears_pending_list():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    p1 = make_request(store, "p1", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1"], pending_ids=["p1"], status=EventStatus.VERIFIED)

    action_service.approve_pending(store, "evt_1", actor="coordinator_1")

    assert p1.status == RequestStatus.IN_VERIFIED_EVENT
    assert p1.verified is True
    evt = store.events["evt_1"]
    assert "p1" in evt.member_request_ids
    assert evt.pending_member_request_ids == []


def test_approve_pending_on_event_with_no_pending_members_raises():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    make_event(store, "evt_1", member_ids=["r1"], status=EventStatus.VERIFIED)
    with pytest.raises(InvalidStateTransition):
        action_service.approve_pending(store, "evt_1", actor="coordinator_1")


def test_approve_pending_on_non_verified_event_raises():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    p1 = make_request(store, "p1", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1"], pending_ids=["p1"], status=EventStatus.CANDIDATE)
    with pytest.raises(InvalidStateTransition):
        action_service.approve_pending(store, "evt_1", actor="coordinator_1")


# --- dispatch_event: verified -> dispatched ---

def test_dispatch_event_moves_active_members_to_dispatched():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    make_event(store, "evt_1", member_ids=["r1"] * 1, status=EventStatus.VERIFIED)
    store.events["evt_1"].member_request_ids = ["r1"]

    action_service.dispatch_event(store, "evt_1", actor="coordinator_1")

    assert store.events["evt_1"].status == EventStatus.DISPATCHED
    assert r1.status == RequestStatus.DISPATCHED
    assert r1.verified is True


def test_dispatch_event_does_not_sweep_pending_addition_members():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    p1 = make_request(store, "p1", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1"], pending_ids=["p1"], status=EventStatus.VERIFIED)

    action_service.dispatch_event(store, "evt_1", actor="coordinator_1")

    assert r1.status == RequestStatus.DISPATCHED
    assert p1.status == RequestStatus.PENDING_ADDITION  # untouched, must be promoted first


def test_dispatch_event_on_non_verified_raises():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1"], status=EventStatus.CANDIDATE)
    with pytest.raises(InvalidStateTransition):
        action_service.dispatch_event(store, "evt_1", actor="coordinator_1")


# --- reject_standalone ---

def test_reject_standalone_terminal():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.STANDALONE)
    action_service.reject_standalone(store, "r1", actor="coordinator_1")
    assert r1.status == RequestStatus.REJECTED


def test_reject_standalone_on_non_standalone_raises():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    with pytest.raises(InvalidStateTransition):
        action_service.reject_standalone(store, "r1", actor="coordinator_1")


# --- verify_standalone: atomic, standalone -> dispatched ---

def test_verify_standalone_is_atomic_never_observable_intermediate_state():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.STANDALONE)
    action_service.verify_standalone(store, "r1", actor="coordinator_1")
    assert r1.status == RequestStatus.DISPATCHED
    assert r1.verified is True


# --- dispatch_standalone: FR-505b, verified=True & standalone -> dispatched ---

def test_dispatch_standalone_the_fr504b_case():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.STANDALONE, verified=True)
    action_service.dispatch_standalone(store, "r1", actor="coordinator_1")
    assert r1.status == RequestStatus.DISPATCHED


def test_dispatch_standalone_on_unverified_standalone_raises():
    """The case most likely to get accidentally merged with verify_standalone."""
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.STANDALONE, verified=False)
    with pytest.raises(InvalidStateTransition):
        action_service.dispatch_standalone(store, "r1", actor="coordinator_1")


def test_dispatch_standalone_on_non_standalone_status_raises():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    with pytest.raises(InvalidStateTransition):
        action_service.dispatch_standalone(store, "r1", actor="coordinator_1")
