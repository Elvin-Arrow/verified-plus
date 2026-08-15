"""BE-08: geofenced_candidates / top_k_cosine edge cases, per docs/testing-spec.md §3.1.

Candidate pool with 0/1/exactly-5/more-than-5 matches; a candidate
belonging to a dispatched Event just past/before the 48h cutoff; an
active (non-dispatched) Event with no age limit however old.
"""
from datetime import datetime, timedelta, timezone

from app.models.domain import Event, EventStatus, Location, Request, RequestStatus
from app.services.matching_service import geofenced_candidates, top_k_cosine
from app.store.memory_store import InMemoryStore

NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)


def make_request(store, id_, lat, lng, submitted_at=None, status=RequestStatus.STANDALONE, event_id=None, device="dev_1"):
    r = Request(
        id=id_, need_description="need", location=Location(lat, lng), device_fingerprint_id=device,
        status=status, event_id=event_id,
    )
    if submitted_at is not None:
        r.submitted_at = submitted_at
    store.requests[id_] = r
    return r


def make_event(store, id_, lat, lng, status=EventStatus.CANDIDATE, created_at=None, member_ids=None):
    e = Event(id=id_, status=status, representative_location=Location(lat, lng), member_request_ids=member_ids or [])
    if created_at is not None:
        e.created_at = created_at
    store.events[id_] = e
    return e


def new_request(lat=0.0, lng=0.0):
    return Request(id="req_new", need_description="new", location=Location(lat, lng), device_fingerprint_id="dev_x")


def test_empty_pool_when_nothing_stored():
    store = InMemoryStore()
    req = new_request()
    assert geofenced_candidates(store, req, now=NOW) == []


def test_standalone_within_radius_and_within_48h_included():
    store = InMemoryStore()
    make_request(store, "req_1", 0.0001, 0.0001, submitted_at=NOW - timedelta(hours=1))
    req = new_request()
    result = geofenced_candidates(store, req, now=NOW)
    assert [c.id for c in result] == ["req_1"]


def test_standalone_beyond_48h_excluded_ages_out():
    store = InMemoryStore()
    make_request(store, "req_1", 0.0001, 0.0001, submitted_at=NOW - timedelta(hours=49))
    req = new_request()
    assert geofenced_candidates(store, req, now=NOW) == []


def test_standalone_just_under_48h_boundary_included():
    store = InMemoryStore()
    make_request(store, "req_1", 0.0001, 0.0001, submitted_at=NOW - timedelta(hours=48))
    req = new_request()
    result = geofenced_candidates(store, req, now=NOW)
    assert [c.id for c in result] == ["req_1"]


def test_standalone_outside_geofence_radius_excluded():
    store = InMemoryStore()
    make_request(store, "req_far", 5.0, 5.0, submitted_at=NOW)  # ~780km away
    req = new_request()
    assert geofenced_candidates(store, req, now=NOW) == []


def test_terminal_standalone_statuses_excluded():
    store = InMemoryStore()
    for status in (RequestStatus.DISPATCHED, RequestStatus.REJECTED, RequestStatus.QUARANTINED):
        make_request(store, f"req_{status.value}", 0.0001, 0.0001, submitted_at=NOW, status=status)
    req = new_request()
    assert geofenced_candidates(store, req, now=NOW) == []


def test_active_event_member_included_with_no_age_limit_however_old():
    store = InMemoryStore()
    make_event(store, "evt_1", 0.0001, 0.0001, status=EventStatus.CANDIDATE,
               created_at=NOW - timedelta(days=365), member_ids=["req_1"])
    make_request(store, "req_1", 0.0001, 0.0001, submitted_at=NOW - timedelta(days=365),
                 status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    req = new_request()
    result = geofenced_candidates(store, req, now=NOW)
    assert [c.id for c in result] == ["req_1"]


def test_dispatched_event_member_included_just_under_48h():
    store = InMemoryStore()
    make_event(store, "evt_1", 0.0001, 0.0001, status=EventStatus.DISPATCHED,
               created_at=NOW - timedelta(hours=47), member_ids=["req_1"])
    make_request(store, "req_1", 0.0001, 0.0001, status=RequestStatus.DISPATCHED, event_id="evt_1")
    req = new_request()
    result = geofenced_candidates(store, req, now=NOW)
    assert [c.id for c in result] == ["req_1"]


def test_dispatched_event_member_excluded_past_48h():
    store = InMemoryStore()
    make_event(store, "evt_1", 0.0001, 0.0001, status=EventStatus.DISPATCHED,
               created_at=NOW - timedelta(hours=49), member_ids=["req_1"])
    make_request(store, "req_1", 0.0001, 0.0001, status=RequestStatus.DISPATCHED, event_id="evt_1")
    req = new_request()
    assert geofenced_candidates(store, req, now=NOW) == []


def test_pending_addition_members_excluded_from_candidate_pool():
    store = InMemoryStore()
    make_event(store, "evt_1", 0.0001, 0.0001, status=EventStatus.VERIFIED, created_at=NOW,
               member_ids=[])
    store.events["evt_1"].pending_member_request_ids = ["req_pending"]
    make_request(store, "req_pending", 0.0001, 0.0001, status=RequestStatus.PENDING_ADDITION, event_id="evt_1")
    req = new_request()
    assert geofenced_candidates(store, req, now=NOW) == []


# --- top_k_cosine ---

def _req_with_embedding(id_, embedding):
    r = Request(id=id_, need_description="x", location=Location(0, 0), device_fingerprint_id="d")
    r.embedding = embedding
    return r


def test_top_k_cosine_zero_candidates():
    assert top_k_cosine([1.0, 0.0], [], k=5) == []


def test_top_k_cosine_one_candidate():
    c = _req_with_embedding("c1", [1.0, 0.0])
    assert top_k_cosine([1.0, 0.0], [c], k=5) == [c]


def test_top_k_cosine_exactly_five_returns_all_five():
    candidates = [_req_with_embedding(f"c{i}", [1.0, 0.0]) for i in range(5)]
    result = top_k_cosine([1.0, 0.0], candidates, k=5)
    assert len(result) == 5


def test_top_k_cosine_more_than_five_returns_only_top_five_by_similarity():
    exact_match = [_req_with_embedding(f"exact{i}", [1.0, 0.0]) for i in range(5)]
    orthogonal = [_req_with_embedding(f"orth{i}", [0.0, 1.0]) for i in range(3)]
    result = top_k_cosine([1.0, 0.0], exact_match + orthogonal, k=5)
    assert len(result) == 5
    assert all(r.id.startswith("exact") for r in result)


def test_top_k_cosine_orders_descending_by_similarity():
    low = _req_with_embedding("low", [0.1, 0.99])
    high = _req_with_embedding("high", [1.0, 0.01])
    result = top_k_cosine([1.0, 0.0], [low, high], k=5)
    assert result[0].id == "high"
    assert result[1].id == "low"
