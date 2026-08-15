"""BE-20: concurrency correctness test. docs/testing-spec.md §8's concurrency
scenario -- N concurrent mutating requests against the single-lock store,
asserting the §4.3 invariants still hold afterward (a correctness test,
not a performance test)."""
import threading

from app.models.domain import Location
from app.services import intake_service
from app.services.action_service import action_service
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse


def _assert_no_undersized_events(store):
    for e in store.events.values():
        assert len(e.member_request_ids) >= 2


def _assert_no_orphaned_event_ids(store):
    for r in store.requests.values():
        assert r.event_id is None or r.event_id in store.events


def test_20_concurrent_submissions_near_same_location_all_land_and_invariants_hold():
    store = InMemoryStore()
    client = FakeLLMClient()
    n = 20
    texts = [f"need water urgently, house {i}" for i in range(n)]
    for text in texts:
        client.script(text, ScriptedResponse(urgency_score=3, urgency_reasoning="ok"))  # never matches -> no clustering race

    threads = []
    for i, text in enumerate(texts):
        t = threading.Thread(
            target=intake_service.submit,
            args=(store, client),
            kwargs={
                "need_description": text,
                "location": Location(lat=1.0 + i * 0.00001, lng=1.0 + i * 0.00001),
                "device_fingerprint_id": f"dev_{i}",
            },
        )
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert all(not t.is_alive() for t in threads)  # no deadlock
    assert len(store.requests) == n  # every submission landed, none lost/duplicated
    ids = {r.id for r in store.requests.values()}
    assert len(ids) == n  # every request got a distinct ID -- no ID-counter race

    _assert_no_undersized_events(store)
    _assert_no_orphaned_event_ids(store)


def test_concurrent_verify_and_split_out_on_related_events_hold_invariants():
    """A more adversarial concurrency case: build several small Events
    first, then hit verify/split_out/reject-and-flag concurrently across
    them -- the dissolution invariants (docs/testing-spec.md §4.3) must
    still hold no matter the interleaving."""
    from app.models.domain import Event, EventStatus, Request, RequestStatus
    from app.services.device_service import device_service

    store = InMemoryStore()
    client = FakeLLMClient()

    for n in range(5):
        r1 = Request(id=f"r{n}a", need_description=f"text{n}a", location=Location(0, 0),
                     device_fingerprint_id=f"dev{n}a", status=RequestStatus.IN_CANDIDATE_EVENT, event_id=f"evt{n}")
        r2 = Request(id=f"r{n}b", need_description=f"text{n}b", location=Location(0, 0),
                     device_fingerprint_id=f"dev{n}b", status=RequestStatus.IN_CANDIDATE_EVENT, event_id=f"evt{n}")
        store.requests[r1.id] = r1
        store.requests[r2.id] = r2
        store.events[f"evt{n}"] = Event(id=f"evt{n}", status=EventStatus.CANDIDATE,
                                         representative_location=Location(0, 0),
                                         member_request_ids=[r1.id, r2.id])
        client.script(f"text{n}a", ScriptedResponse())

    def do_verify(event_id):
        try:
            action_service.verify_event(store, event_id, actor="c1")
        except Exception:
            pass

    def do_split(request_id):
        try:
            action_service.split_out(store, client, request_id, actor="c1")
        except Exception:
            pass

    def do_reject_flag(event_id, device_id):
        try:
            device_service.reject_and_flag_device(store, event_id, device_id, actor="c1")
        except Exception:
            pass

    threads = [
        threading.Thread(target=do_verify, args=("evt0",)),
        threading.Thread(target=do_split, args=("r1a",)),
        threading.Thread(target=do_reject_flag, args=("evt2", "dev2a")),
        threading.Thread(target=do_verify, args=("evt3",)),
        threading.Thread(target=do_split, args=("r4a",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert all(not t.is_alive() for t in threads)  # no deadlock
    _assert_no_undersized_events(store)
    _assert_no_orphaned_event_ids(store)
