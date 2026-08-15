"""BE-16: queue assembly. docs/design.md §4.3; FR-401-407.

GET intake-inbox / dispatch-queue / quarantine / archive read models,
built on top of sort.py's shared lexicographic ordering.
"""
from app.models.domain import DeviceFingerprint, Event, EventStatus, Location, Request, RequestStatus
from app.services import queue_service
from app.store.memory_store import InMemoryStore


def make_request(store, id_, status, urgency=3, device="dev_1", event_id=None, verified=False):
    r = Request(id=id_, need_description=f"need-{id_}", location=Location(0, 0),
                device_fingerprint_id=device, status=status, urgency_score=urgency,
                event_id=event_id, verified=verified)
    store.requests[id_] = r
    return r


def make_event(store, id_, member_ids, status=EventStatus.CANDIDATE, pending_ids=None):
    e = Event(id=id_, status=status, representative_location=Location(0, 0),
              member_request_ids=list(member_ids), pending_member_request_ids=list(pending_ids or []))
    store.events[id_] = e
    return e


# --- intake-inbox: FR-401 ---

def test_intake_inbox_contains_candidate_events_and_standalone_requests():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", urgency=4)
    make_request(store, "r2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_1", urgency=4, device="dev_2")
    make_event(store, "evt_1", ["r1", "r2"])
    make_request(store, "r3", RequestStatus.STANDALONE, urgency=2)

    result = queue_service.intake_inbox(store)

    sorted_items = result["sorted"]
    assert len(sorted_items) == 2
    ids = [i.id for i in sorted_items]
    assert "evt_1" in ids and "r3" in ids


def test_intake_inbox_excludes_verified_dispatched_rejected_quarantined():
    store = InMemoryStore()
    make_request(store, "r_verified", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_v", verified=True)
    make_event(store, "evt_v", ["r_verified", "r_v2"], status=EventStatus.VERIFIED)
    make_request(store, "r_v2", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_v", verified=True)
    make_request(store, "r_dispatched", RequestStatus.DISPATCHED)
    make_request(store, "r_rejected", RequestStatus.REJECTED)
    make_request(store, "r_quarantined", RequestStatus.QUARANTINED)

    result = queue_service.intake_inbox(store)

    all_ids = [i.id for i in result["sorted"]] + [i.id for i in result["needs_manual_triage"]]
    assert "evt_v" not in all_ids
    assert "r_dispatched" not in all_ids
    assert "r_rejected" not in all_ids
    assert "r_quarantined" not in all_ids


def test_intake_inbox_needs_manual_triage_section():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.STANDALONE, urgency=None)

    result = queue_service.intake_inbox(store)

    assert len(result["needs_manual_triage"]) == 1
    assert result["needs_manual_triage"][0].id == "r1"
    assert result["sorted"] == []


def test_intake_inbox_sorted_by_urgency_then_device_count():
    store = InMemoryStore()
    make_request(store, "lo", RequestStatus.STANDALONE, urgency=2)
    make_request(store, "hi", RequestStatus.STANDALONE, urgency=5)

    result = queue_service.intake_inbox(store)

    assert [i.id for i in result["sorted"]] == ["hi", "lo"]


def test_intake_inbox_empty_store_returns_empty_arrays():
    store = InMemoryStore()
    result = queue_service.intake_inbox(store)
    assert result == {"needs_manual_triage": [], "sorted": []}


# --- dispatch-queue: FR-403 ---

def test_dispatch_queue_contains_verified_events_and_verified_standalone():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True, urgency=4)
    make_request(store, "r2", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True, urgency=4, device="dev_2")
    make_event(store, "evt_1", ["r1", "r2"], status=EventStatus.VERIFIED)
    make_request(store, "r3", RequestStatus.STANDALONE, verified=True, urgency=3)

    result = queue_service.dispatch_queue(store)

    ids = [i.id for i in result["sorted"]]
    assert "evt_1" in ids
    assert "r3" in ids


def test_dispatch_queue_excludes_unverified_standalone_dispatched_rejected_quarantined_candidate():
    store = InMemoryStore()
    make_request(store, "r_unverified", RequestStatus.STANDALONE, verified=False)
    make_request(store, "r_dispatched", RequestStatus.DISPATCHED, verified=True)
    make_request(store, "r_rejected", RequestStatus.REJECTED)
    make_request(store, "r_quarantined", RequestStatus.QUARANTINED)
    make_request(store, "r_cand", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_c")
    make_event(store, "evt_c", ["r_cand", "r_cand2"], status=EventStatus.CANDIDATE)
    make_request(store, "r_cand2", RequestStatus.IN_CANDIDATE_EVENT, event_id="evt_c")

    result = queue_service.dispatch_queue(store)

    ids = [i.id for i in result["sorted"]]
    assert ids == []


def test_dispatch_queue_event_includes_pending_members_separately():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.IN_VERIFIED_EVENT, event_id="evt_1", verified=True)
    make_request(store, "rp", RequestStatus.PENDING_ADDITION, event_id="evt_1")
    make_event(store, "evt_1", ["r1"], status=EventStatus.VERIFIED, pending_ids=["rp"])

    result = queue_service.dispatch_queue(store)

    evt_item = next(i for i in result["sorted"] if i.id == "evt_1")
    assert evt_item.pending_member_request_ids == ["rp"]


# --- quarantine: FR-407, grouped by device ---

def test_quarantine_groups_by_device():
    store = InMemoryStore()
    store.devices["dev_x"] = DeviceFingerprint(id="dev_x", device_flag=True)
    store.devices["dev_y"] = DeviceFingerprint(id="dev_y", device_flag=True)
    make_request(store, "q1", RequestStatus.QUARANTINED, device="dev_x")
    make_request(store, "q2", RequestStatus.QUARANTINED, device="dev_x")
    make_request(store, "q3", RequestStatus.QUARANTINED, device="dev_y")

    result = queue_service.quarantine(store)

    groups = {g["device_fingerprint_id"]: g for g in result["groups"]}
    assert set(r.id for r in groups["dev_x"]["requests"]) == {"q1", "q2"}
    assert set(r.id for r in groups["dev_y"]["requests"]) == {"q3"}
    assert groups["dev_x"]["device_flag"] is True


def test_quarantine_excludes_non_quarantined_requests():
    store = InMemoryStore()
    make_request(store, "r1", RequestStatus.STANDALONE, device="dev_x")
    result = queue_service.quarantine(store)
    assert result["groups"] == []


# --- archive: FR-406 ---

def test_archive_contains_dispatched_and_rejected():
    store = InMemoryStore()
    make_request(store, "r_d", RequestStatus.DISPATCHED)
    make_request(store, "r_r", RequestStatus.REJECTED)
    make_request(store, "r_active", RequestStatus.STANDALONE)
    make_event(store, "evt_d", ["r_e1", "r_e2"], status=EventStatus.DISPATCHED)
    make_request(store, "r_e1", RequestStatus.DISPATCHED, event_id="evt_d")
    make_request(store, "r_e2", RequestStatus.DISPATCHED, event_id="evt_d")

    result = queue_service.archive(store)

    standalone_ids = [r.id for r in result["standalone_requests"]]
    assert "r_d" in standalone_ids
    assert "r_r" in standalone_ids
    assert "r_active" not in standalone_ids
    event_ids = [e.id for e in result["events"]]
    assert "evt_d" in event_ids


def test_archive_device_flagged_marker_present():
    """FR-309: any Archive item whose device is flagged carries a scrutiny marker."""
    store = InMemoryStore()
    store.devices["dev_x"] = DeviceFingerprint(id="dev_x", device_flag=True)
    make_request(store, "r_d", RequestStatus.DISPATCHED, device="dev_x")

    result = queue_service.archive(store)

    assert queue_service.is_device_flagged(store, result["standalone_requests"][0]) is True


def test_has_suggested_merge_true_when_request_id_present_in_store_list():
    """Cross-doc alignment fix: RequestSummary needs a cheap boolean so list views
    (e.g. the Intake Inbox) can render the Merge affordance without fetching full
    detail for every row -- docs/api-spec.md §1.3, docs/data-model.md §4."""
    store = InMemoryStore()
    r = make_request(store, "r_x", RequestStatus.STANDALONE)
    store.suggested_merges.append({"request_id": "r_x", "event_id": "evt_far", "distance_km": 1.9})

    assert queue_service.has_suggested_merge(store, r) is True


def test_has_suggested_merge_false_when_absent():
    store = InMemoryStore()
    r = make_request(store, "r_y", RequestStatus.STANDALONE)

    assert queue_service.has_suggested_merge(store, r) is False


def test_has_suggested_merge_only_matches_its_own_request_id():
    store = InMemoryStore()
    r = make_request(store, "r_z", RequestStatus.STANDALONE)
    store.suggested_merges.append({"request_id": "some_other_request", "event_id": "evt_far", "distance_km": 2.1})

    assert queue_service.has_suggested_merge(store, r) is False
