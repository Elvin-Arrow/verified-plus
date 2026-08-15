"""BE-20: NFR-101/102 load harness. docs/testing-spec.md §8.

A plain benchmark (no locust dependency needed at this scope) against a
store pre-populated to NFR-102's stated scale ceiling (1,000 stored
requests), using the LLM double configured with a realistic (not zero)
simulated latency -- this measures the system's OWN overhead, not a
third-party provider's response time, which is out of scope to gate the
build on.
"""
import statistics
import time

from app.models.domain import Location, Request, RequestStatus
from app.services import intake_service, queue_service
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse

SCALE = 1000


def _prepopulate(store: InMemoryStore, n: int) -> None:
    """Direct store population (not through the live API) for the *existing*
    n requests -- realistic demo-scale prior state, not the thing being
    timed. Scattered widely so they mostly fall outside any single new
    submission's geofence, keeping candidate-pool sizes representative."""
    for i in range(n):
        store.requests[f"seed_{i}"] = Request(
            id=f"seed_{i}",
            need_description=f"prior need {i}",
            location=Location(lat=(i % 180) - 90.0, lng=(i % 360) - 180.0),
            device_fingerprint_id=f"seed_dev_{i}",
            status=RequestStatus.STANDALONE,
            urgency_score=(i % 5) + 1,
        )


def test_nfr_101_p95_submission_latency_under_5s_at_1000_stored_requests():
    store = InMemoryStore()
    _prepopulate(store, SCALE)
    client = FakeLLMClient(latency_s=0.02)  # realistic-ish simulated network latency

    latencies = []
    for i in range(20):
        text = f"new submission {i}"
        client.script(text, ScriptedResponse(urgency_score=3, urgency_reasoning="ok"))
        start = time.perf_counter()
        intake_service.submit(
            store, client,
            need_description=text,
            location=Location(lat=1.0, lng=1.0),
            device_fingerprint_id=f"dev_new_{i}",
        )
        latencies.append(time.perf_counter() - start)

    latencies.sort()
    p95_index = max(0, int(len(latencies) * 0.95) - 1)
    p95 = latencies[p95_index]
    assert p95 < 5.0, f"p95 submission latency {p95:.3f}s exceeds NFR-101's 5s budget"


def test_nfr_102_queue_reads_render_well_under_a_human_perceptible_threshold_at_1000():
    store = InMemoryStore()
    _prepopulate(store, SCALE)

    start = time.perf_counter()
    queue_service.intake_inbox(store)
    queue_service.dispatch_queue(store)
    queue_service.quarantine(store)
    queue_service.archive(store)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5, f"queue assembly at {SCALE} requests took {elapsed:.3f}s (budget: 0.5s)"


def test_nfr_102_store_supports_at_least_1000_requests_without_error():
    store = InMemoryStore()
    _prepopulate(store, SCALE)
    assert len(store.requests) == SCALE
    result = queue_service.intake_inbox(store)
    assert len(result["sorted"]) + len(result["needs_manual_triage"]) == SCALE
