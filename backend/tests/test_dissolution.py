"""BE-10 (HIGH RISK): detach_from_event + maybe_dissolve_event.

Per docs/design.md §4.4/§4.5 and docs/testing-spec.md §4.3: the
dissolution/orphan-prevention invariants, including the pending-member
dissolution case and the single-call-site rationale in design.md's
detach_from_event docstring (a member's status updated without being
removed from member_request_ids is exactly the bug that let a ghost
Event survive forever in an earlier draft).
"""
from app.models.domain import Event, EventStatus, Location, Request, RequestStatus
from app.services.clustering_service import recompute_centroid
from app.services.dissolution import detach_from_event, maybe_dissolve_event
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


def assert_no_orphaned_event_ids(store):
    """Invariant 2 (testing-spec.md §4.3): no Request.event_id points to a
    nonexistent Event."""
    for r in store.requests.values():
        assert r.event_id is None or r.event_id in store.events


def assert_no_undersized_events(store):
    """Invariant 1: no Event with <=1 active member exists at rest."""
    for e in store.events.values():
        assert len(e.member_request_ids) >= 2


# --- maybe_dissolve_event: no-op above threshold ---

def test_maybe_dissolve_noop_when_still_two_or_more_members():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_request(store, "r3", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    evt = make_event(store, "evt_1", member_ids=["r1", "r2", "r3"])
    evt.member_request_ids.remove("r3")  # simulate a prior removal down to 2
    maybe_dissolve_event(store, evt)
    assert "evt_1" in store.events
    assert_no_undersized_events(store)


# --- detach_from_event: the single call site ---

def test_detach_from_event_removes_from_member_list_and_clears_event_id():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    r3 = make_request(store, "r3", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1", "r2", "r3"])

    detach_from_event(store, r3)

    assert r3.event_id is None
    assert "r3" not in store.events["evt_1"].member_request_ids
    assert "evt_1" in store.events  # still 2 active members, survives
    assert_no_undersized_events(store)
    assert_no_orphaned_event_ids(store)


def test_detach_from_event_dissolves_when_dropping_to_one_active_member():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    r2 = make_request(store, "r2", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    make_event(store, "evt_1", member_ids=["r1", "r2"], status=EventStatus.VERIFIED)

    detach_from_event(store, r2)

    assert "evt_1" not in store.events
    assert r1.event_id is None
    assert r1.status == RequestStatus.STANDALONE
    assert r1.verified is True  # dissolution never overrides verified state
    assert_no_orphaned_event_ids(store)


def test_detach_from_pending_member_list_works_too():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    r2 = make_request(store, "r2", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    pending = make_request(store, "rp", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r1", "r2"], pending_ids=["rp"], status=EventStatus.VERIFIED)

    detach_from_event(store, pending)

    assert pending.event_id is None
    assert "rp" not in store.events["evt_1"].pending_member_request_ids
    assert "evt_1" in store.events  # 2 active members untouched, still valid


def test_detach_from_event_noop_when_request_has_no_event():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.STANDALONE)
    detach_from_event(store, r1)  # must not raise
    assert r1.event_id is None


# --- Pending-member dissolution (testing-spec.md §4.3) ---

def test_pending_member_dissolution_reverts_all_three_correctly():
    """An Event with 1 active member and 2 pending members dissolves
    correctly on the active member dropping out: all three end up
    standalone -- the active one keeps whatever `verified` it had, the
    two pending ones become verified=False."""
    store = InMemoryStore()
    active = make_request(store, "r_active", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    sibling = make_request(store, "r_sibling", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    pending1 = make_request(store, "rp1", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    pending2 = make_request(store, "rp2", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r_active", "r_sibling"], pending_ids=["rp1", "rp2"],
               status=EventStatus.VERIFIED)

    detach_from_event(store, sibling)  # drops active membership to 1 -> dissolves

    assert "evt_1" not in store.events
    assert active.status == RequestStatus.STANDALONE
    assert active.event_id is None
    assert active.verified is True

    for p in (pending1, pending2):
        assert p.status == RequestStatus.STANDALONE
        assert p.event_id is None
        assert p.verified is False

    assert_no_orphaned_event_ids(store)


def test_dissolution_with_zero_active_members_still_reverts_pending():
    """Edge case: an Event's active membership can reach exactly 0 (e.g.
    via reject_and_flag_device rejecting the last active member) while
    pending members remain -- they must still be reverted, not left
    dangling."""
    store = InMemoryStore()
    last_active = make_request(store, "r_last", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    pending1 = make_request(store, "rp1", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    make_event(store, "evt_1", member_ids=["r_last"], pending_ids=["rp1"], status=EventStatus.VERIFIED)

    detach_from_event(store, last_active)

    assert "evt_1" not in store.events
    assert pending1.status == RequestStatus.STANDALONE
    assert pending1.event_id is None
    assert pending1.verified is False


# --- Invariant regression: the Finding-8-shaped bug (reject_and_flag_device /
# maybe_dissolve_event never seeing membership shrink because a member's
# status was updated without being removed from member_request_ids) ---

def test_regression_three_member_event_two_sequential_detaches_from_different_devices_dissolves():
    store = InMemoryStore()
    r1 = make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_a")
    r2 = make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_b")
    r3 = make_request(store, "r3", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", device="dev_c")
    make_event(store, "evt_1", member_ids=["r1", "r2", "r3"])

    r1.status = RequestStatus.REJECTED
    detach_from_event(store, r1)
    assert "evt_1" in store.events
    assert len(store.events["evt_1"].member_request_ids) == 2

    r2.status = RequestStatus.REJECTED
    detach_from_event(store, r2)

    assert "evt_1" not in store.events  # must be gone, not sitting at 1 member
    assert r3.event_id is None
    assert r3.status == RequestStatus.STANDALONE
    assert_no_orphaned_event_ids(store)
    assert_no_undersized_events(store)


def test_detach_recomputes_centroid_when_event_survives():
    store = InMemoryStore()
    r1 = Request(id="r1", need_description="x", location=Location(0.0, 0.0),
                 device_fingerprint_id="d1", status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    r2 = Request(id="r2", need_description="x", location=Location(0.0, 0.0),
                 device_fingerprint_id="d2", status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    r3 = Request(id="r3", need_description="x", location=Location(10.0, 10.0),
                 device_fingerprint_id="d3", status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    store.requests = {"r1": r1, "r2": r2, "r3": r3}
    make_event(store, "evt_1", member_ids=["r1", "r2", "r3"])
    recompute_centroid(store, store.events["evt_1"])

    detach_from_event(store, r3)  # remove the far-away outlier

    evt = store.events["evt_1"]
    assert evt.representative_location.lat == 0.0
    assert evt.representative_location.lng == 0.0
