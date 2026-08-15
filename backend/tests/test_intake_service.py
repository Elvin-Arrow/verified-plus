"""BE-07: intake pipeline (steps 1-5), per testing-spec.md §3.2's two flagship
contract cases -- quarantine short-circuit and LLM-failure-returns-201 --
exercised here at the service layer (BE-18 wires the actual 201 later)."""
import pytest

from app.models.domain import DeviceFingerprint, Location, RequestStatus
from app.services.intake_service import ValidationError, submit
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse


def make_store():
    return InMemoryStore()


def test_missing_location_raises_validation_error():
    store = make_store()
    client = FakeLLMClient()
    with pytest.raises(ValidationError) as exc:
        submit(store, client, need_description="need water", location=None, device_fingerprint_id="dev_1")
    assert exc.value.field == "location"


def test_empty_need_description_raises_validation_error():
    store = make_store()
    client = FakeLLMClient()
    with pytest.raises(ValidationError) as exc:
        submit(store, client, need_description="   ", location=Location(1, 1), device_fingerprint_id="dev_1")
    assert exc.value.field == "need_description"


def test_flagged_device_short_circuits_to_quarantined_never_calls_llm():
    store = make_store()
    store.devices["dev_1"] = DeviceFingerprint(id="dev_1", device_flag=True)
    client = FakeLLMClient()
    req = submit(store, client, need_description="need water", location=Location(1, 1), device_fingerprint_id="dev_1")
    assert req.status == RequestStatus.QUARANTINED
    assert req.urgency_score is None
    assert req.event_id is None
    assert client.calls == []
    assert client.embed_calls == []


def test_first_time_device_gets_created_unflagged():
    store = make_store()
    client = FakeLLMClient()
    client.script("need water", ScriptedResponse(urgency_score=3, urgency_reasoning="ok"))
    submit(store, client, need_description="need water", location=Location(1, 1), device_fingerprint_id="dev_new")
    assert store.devices["dev_new"].device_flag is False


def test_successful_submission_sets_urgency_and_stores_request():
    store = make_store()
    client = FakeLLMClient()
    client.script("need water", ScriptedResponse(urgency_score=4, urgency_reasoning="serious"))
    req = submit(store, client, need_description="need water", location=Location(1, 1), device_fingerprint_id="dev_1")
    assert req.urgency_score == 4
    assert req.urgency_reasoning == "serious"
    assert req.id in store.requests
    assert req.status == RequestStatus.STANDALONE  # clustering stub, BE-09 replaces


def test_llm_failure_never_raises_and_returns_pending_state_not_error():
    store = make_store()
    client = FakeLLMClient()
    client.script("flaky text", ScriptedResponse(fail=True))
    req = submit(store, client, need_description="flaky text", location=Location(1, 1), device_fingerprint_id="dev_1")
    assert req.urgency_score is None
    assert req.urgency_reasoning is None
    assert req.status == RequestStatus.STANDALONE
    assert req.id in store.requests  # still created/stored, never dropped (NFR-103)


def test_embedding_failure_never_raises_and_returns_pending_state():
    store = make_store()
    client = FakeLLMClient()
    client.fail_embedding_for("bad embed text")
    req = submit(store, client, need_description="bad embed text", location=Location(1, 1), device_fingerprint_id="dev_1")
    assert req.urgency_score is None
    assert req.status == RequestStatus.STANDALONE


def test_request_gets_a_utc_timestamp():
    store = make_store()
    client = FakeLLMClient()
    client.script("need water", ScriptedResponse())
    req = submit(store, client, need_description="need water", location=Location(1, 1), device_fingerprint_id="dev_1")
    assert req.submitted_at is not None
