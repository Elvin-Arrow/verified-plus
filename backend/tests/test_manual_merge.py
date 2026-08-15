"""BE-11: manual_merge (FR-205c) integration test, per docs/testing-spec.md
§6.1's manual-merge-bootstrap scenario. manual_merge() itself shipped
under BE-09 (same module/design section, docs/design.md §4.2); this adds
the dedicated scenario testing-spec.md calls for."""
from app.models.domain import Event, EventStatus, Location, MatchResult, RequestStatus, SessionConfig
from app.services.clustering_service import assign, manual_merge
from app.store.memory_store import InMemoryStore


def match(candidate_id):
    return MatchResult(candidate_id=candidate_id, is_match=True, reason="matched")


def test_manual_merge_bootstraps_new_event_from_two_geometrically_excluded_standalones():
    # geofence radius configured larger than max-cluster-span, so both are
    # candidates the LLM sees (FR-202) but geometrically excluded from each
    # other by FR-205 step 1.
    cfg = SessionConfig(geofence_radius_km=3.0, max_cluster_span_km=1.0)
    store = InMemoryStore(config=cfg)

    from app.models.domain import Request

    a = Request(id="req_a", need_description="need a", location=Location(0.0, 0.0), device_fingerprint_id="dev_a")
    b = Request(id="req_b", need_description="need b", location=Location(1.5 / 111.19, 0.0), device_fingerprint_id="dev_b")
    store.requests = {"req_a": a, "req_b": b}

    # assign() runs for req_b matching req_a -- excluded by the 1.0km span
    assign(store, b, [match("req_a")])

    assert b.status == RequestStatus.STANDALONE
    assert store.events == {}
    assert len(store.suggested_merges) == 1
    sm = store.suggested_merges[0]
    assert sm["request_id"] == "req_b"
    assert sm["request_id_2"] == "req_a"
    assert sm["distance_km"] > 1.0

    event = manual_merge(store, "req_b", target_event_id=None, target_request_id="req_a", actor="coordinator_1")

    assert event.status == EventStatus.CANDIDATE
    assert set(event.member_request_ids) == {"req_a", "req_b"}
    assert a.event_id == event.id
    assert b.event_id == event.id
    assert a.status == RequestStatus.IN_CANDIDATE_EVENT
    assert b.status == RequestStatus.IN_CANDIDATE_EVENT

    log = [act for act in store.actions if act.action_type == "manual_merge"]
    assert len(log) == 1
    assert log[0].target_id == "req_b"
    assert log[0].actor == "coordinator_1"


def test_manual_merge_attaches_to_existing_event_bypassing_geometric_filter_only():
    cfg = SessionConfig(geofence_radius_km=3.0, max_cluster_span_km=1.0)
    store = InMemoryStore(config=cfg)

    from app.models.domain import Request

    member = Request(id="req_m", need_description="need m", location=Location(0.0, 0.0),
                      device_fingerprint_id="dev_m", status=RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1")
    new = Request(id="req_new", need_description="need new", location=Location(1.5 / 111.19, 0.0),
                  device_fingerprint_id="dev_new")
    store.requests = {"req_m": member, "req_new": new}
    store.events["evt_1"] = Event(id="evt_1", status=EventStatus.CANDIDATE,
                                   representative_location=Location(0.0, 0.0), member_request_ids=["req_m"])

    assign(store, new, [match("req_m")])  # excluded, remains standalone
    assert new.status == RequestStatus.STANDALONE
    assert len(store.suggested_merges) == 1
    assert store.suggested_merges[0]["event_id"] == "evt_1"

    event = manual_merge(store, "req_new", target_event_id="evt_1", target_request_id=None, actor="coordinator_1")

    assert event.id == "evt_1"
    assert "req_new" in event.member_request_ids
    assert new.status == RequestStatus.IN_CANDIDATE_EVENT
    assert new.event_id == "evt_1"


def test_manual_merge_into_verified_event_attaches_as_pending_addition():
    """manual_merge bypasses only the geometric filter, never the
    authority/pending-addition logic (FR-205c)."""
    cfg = SessionConfig(geofence_radius_km=3.0, max_cluster_span_km=1.0)
    store = InMemoryStore(config=cfg)

    from app.models.domain import Request

    new = Request(id="req_new", need_description="need new", location=Location(0.0, 0.0), device_fingerprint_id="dev_new")
    store.requests = {"req_new": new}
    store.events["evt_v"] = Event(id="evt_v", status=EventStatus.VERIFIED,
                                   representative_location=Location(0.0, 0.0), member_request_ids=["req_other"])

    event = manual_merge(store, "req_new", target_event_id="evt_v", target_request_id=None, actor="coordinator_1")

    assert new.status == RequestStatus.PENDING_ADDITION
    assert "req_new" in event.pending_member_request_ids
    assert "req_new" not in event.member_request_ids
