"""BE-09 (HIGH RISK): assign() -- geometric filter, authority selection,
bootstrap, _attach_to_event. Per docs/design.md §4.2, docs/testing-spec.md
§4.1 (state-machine transitions) and §4.3 (the Finding-13 regression +
authority-selection-alone case, mirrored at unit level here; the
integration-level versions live in later BE-1x commits' flow tests)."""
from app.models.domain import Event, EventStatus, Location, MatchResult, Request, RequestStatus
from app.services.clustering_service import assign
from app.store.memory_store import InMemoryStore


def make_request(store, id_, lat=0.0, lng=0.0, status=RequestStatus.STANDALONE, event_id=None, device="dev_1"):
    r = Request(id=id_, need_description=f"need-{id_}", location=Location(lat, lng),
                device_fingerprint_id=device, status=status, event_id=event_id)
    store.requests[id_] = r
    return r


def make_event(store, id_, lat=0.0, lng=0.0, status=EventStatus.CANDIDATE, member_ids=None):
    e = Event(id=id_, status=status, representative_location=Location(lat, lng),
              member_request_ids=list(member_ids or []))
    store.events[id_] = e
    return e


def make_new_request(store, id_="req_new", lat=0.0, lng=0.0):
    r = Request(id=id_, need_description="new", location=Location(lat, lng), device_fingerprint_id="dev_x")
    store.requests[id_] = r
    return r


def match(candidate_id, is_match=True, reason="matched"):
    return MatchResult(candidate_id=candidate_id, is_match=is_match, reason=reason)


# --- FR-205 step 5: bootstrap a new candidate Event from two standalones ---

def test_bootstrap_new_candidate_event_from_two_standalones():
    store = InMemoryStore()
    other = make_request(store, "req_other", 0.0001, 0.0001)
    new = make_new_request(store)

    assign(store, new, [match("req_other")])

    assert new.status == RequestStatus.IN_CANDIDATE_EVENT
    assert other.status == RequestStatus.IN_CANDIDATE_EVENT
    assert new.event_id == other.event_id
    assert new.event_id is not None
    evt = store.events[new.event_id]
    assert evt.status == EventStatus.CANDIDATE
    assert set(evt.member_request_ids) == {"req_new", "req_other"}
    assert evt.representative_location is not None


# --- FR-205 step 4: join an existing candidate Event directly ---

def test_join_existing_candidate_event_directly():
    store = InMemoryStore()
    member = make_request(store, "req_m1", 0.0001, 0.0001, status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    make_event(store, "evt_1", 0.0001, 0.0001, status=EventStatus.CANDIDATE, member_ids=["req_m1"])
    new = make_new_request(store)

    assign(store, new, [match("req_m1")])

    assert new.status == RequestStatus.IN_CANDIDATE_EVENT
    assert new.event_id == "evt_1"
    assert "req_new" in store.events["evt_1"].member_request_ids


# --- FR-205 step 3 / FR-304b: standalone -> pending_addition on verified/dispatched Event ---

def test_matching_verified_event_attaches_as_pending_addition_not_direct_member():
    store = InMemoryStore()
    make_request(store, "req_m1", 0.0001, 0.0001, status=RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1")
    make_event(store, "evt_1", 0.0001, 0.0001, status=EventStatus.VERIFIED, member_ids=["req_m1"])
    new = make_new_request(store)

    assign(store, new, [match("req_m1")])

    assert new.status == RequestStatus.PENDING_ADDITION
    assert new.event_id == "evt_1"
    assert new.id not in store.events["evt_1"].member_request_ids
    assert new.id in store.events["evt_1"].pending_member_request_ids


def test_matching_dispatched_event_also_attaches_as_pending_addition():
    store = InMemoryStore()
    make_request(store, "req_m1", 0.0001, 0.0001, status=RequestStatus.DISPATCHED, event_id="evt_1")
    make_event(store, "evt_1", 0.0001, 0.0001, status=EventStatus.DISPATCHED, member_ids=["req_m1"])
    new = make_new_request(store)

    assign(store, new, [match("req_m1")])

    assert new.status == RequestStatus.PENDING_ADDITION
    assert new.id in store.events["evt_1"].pending_member_request_ids


# --- FR-205 step 6: no candidate survives -> remain standalone, no phantom Event ---

def test_no_llm_matches_remains_standalone():
    store = InMemoryStore()
    new = make_new_request(store)
    assign(store, new, [])
    assert new.status == RequestStatus.STANDALONE
    assert new.event_id is None
    assert store.events == {}


def test_llm_match_but_geometrically_excluded_remains_standalone_with_suggested_merge():
    store = InMemoryStore()
    far = make_request(store, "req_far", 2.0, 2.0)  # ~300+km away, way past default 1.5km span
    new = make_new_request(store)

    assign(store, new, [match("req_far")])

    assert new.status == RequestStatus.STANDALONE
    assert new.event_id is None
    assert store.events == {}
    assert len(store.suggested_merges) == 1
    sm = store.suggested_merges[0]
    assert sm["request_id"] == "req_new"
    assert sm["request_id_2"] == "req_far"
    assert sm["distance_km"] > 1.5


def test_geometrically_excluded_existing_event_produces_suggested_merge_with_event_id():
    store = InMemoryStore()
    make_request(store, "req_m1", 2.0, 2.0, status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_far")
    make_event(store, "evt_far", 2.0, 2.0, status=EventStatus.CANDIDATE, member_ids=["req_m1"])
    new = make_new_request(store)

    assign(store, new, [match("req_m1")])

    assert new.status == RequestStatus.STANDALONE
    assert len(store.suggested_merges) == 1
    assert store.suggested_merges[0]["event_id"] == "evt_far"
    assert store.suggested_merges[0]["request_id"] == "req_new"


# --- non-match candidates never considered ---

def test_is_match_false_candidate_ignored():
    store = InMemoryStore()
    other = make_request(store, "req_other", 0.0001, 0.0001)
    new = make_new_request(store)
    assign(store, new, [match("req_other", is_match=False)])
    assert new.status == RequestStatus.STANDALONE
    assert store.events == {}


# --- FR-205 step 2: authority selection among geometrically-valid EXISTING Events ---

def test_authority_selection_verified_beats_candidate_when_both_geometrically_valid():
    store = InMemoryStore()
    make_request(store, "req_c1", 0.0001, 0.0001, status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_candidate")
    make_event(store, "evt_candidate", 0.0001, 0.0001, status=EventStatus.CANDIDATE, member_ids=["req_c1"])
    make_request(store, "req_v1", 0.0002, 0.0002, status=RequestStatus.IN_VERIFIED_EVENT, event_id="evt_verified")
    make_event(store, "evt_verified", 0.0002, 0.0002, status=EventStatus.VERIFIED, member_ids=["req_v1"])
    new = make_new_request(store)

    assign(store, new, [match("req_c1"), match("req_v1")])

    assert new.event_id == "evt_verified"
    assert new.status == RequestStatus.PENDING_ADDITION


def test_authority_selection_dispatched_beats_verified_when_both_geometrically_valid():
    store = InMemoryStore()
    make_request(store, "req_v1", 0.0001, 0.0001, status=RequestStatus.IN_VERIFIED_EVENT, event_id="evt_verified")
    make_event(store, "evt_verified", 0.0001, 0.0001, status=EventStatus.VERIFIED, member_ids=["req_v1"])
    make_request(store, "req_d1", 0.0002, 0.0002, status=RequestStatus.DISPATCHED, event_id="evt_dispatched")
    make_event(store, "evt_dispatched", 0.0002, 0.0002, status=EventStatus.DISPATCHED, member_ids=["req_d1"])
    new = make_new_request(store)

    assign(store, new, [match("req_v1"), match("req_d1")])

    assert new.event_id == "evt_dispatched"
    assert new.status == RequestStatus.PENDING_ADDITION


# --- The Finding-13 regression (docs/spec.md §10 #13), by name ---

def test_finding_13_regression_geometric_filter_runs_before_authority_selection():
    """A request matching two Events -- one verified but 1.6km away
    (geometrically excluded), one candidate and 0.5km away (geometrically
    valid) -- must join the candidate Event, not get force-excluded by
    the far Event's higher authority ranking."""
    store = InMemoryStore()
    # ~0.5km north of the new request (well within default 1.5km span)
    close_lat_offset = 0.5 / 111.19
    make_request(store, "req_close", close_lat_offset, 0.0, status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_close")
    make_event(store, "evt_close", close_lat_offset, 0.0, status=EventStatus.CANDIDATE, member_ids=["req_close"])
    # ~1.6km away (just past the default 1.5km max-cluster-span) but VERIFIED (higher authority)
    far_lat_offset = 1.6 / 111.19
    make_request(store, "req_far", far_lat_offset, 0.0, status=RequestStatus.IN_VERIFIED_EVENT, event_id="evt_far")
    make_event(store, "evt_far", far_lat_offset, 0.0, status=EventStatus.VERIFIED, member_ids=["req_far"])
    new = make_new_request(store)

    assign(store, new, [match("req_close"), match("req_far")])

    assert new.event_id == "evt_close"
    assert new.status == RequestStatus.IN_CANDIDATE_EVENT
    # the excluded far match still surfaces as a Suggested Merge (FR-205b)
    assert any(sm.get("event_id") == "evt_far" for sm in store.suggested_merges)


# --- FR-205 step 7: never auto-merges two distinct existing Events ---

def test_never_auto_merges_two_existing_events_only_one_gets_the_new_member():
    store = InMemoryStore()
    make_request(store, "req_a", 0.0001, 0.0001, status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_a")
    make_event(store, "evt_a", 0.0001, 0.0001, status=EventStatus.CANDIDATE, member_ids=["req_a"])
    make_request(store, "req_b", 0.0002, 0.0002, status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_b")
    make_event(store, "evt_b", 0.0002, 0.0002, status=EventStatus.CANDIDATE, member_ids=["req_b"])
    new = make_new_request(store)

    assign(store, new, [match("req_a"), match("req_b")])

    assert len(store.events) == 2  # evt_a and evt_b both still exist, separately
    assert new.event_id in ("evt_a", "evt_b")
    other_event_id = "evt_b" if new.event_id == "evt_a" else "evt_a"
    assert new.id not in store.events[other_event_id].member_request_ids
