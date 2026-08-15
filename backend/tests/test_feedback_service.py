"""BE-15 (HIGH RISK): calibration buffers. docs/design.md §4.7; FR-603-605.

record_urgency_override/record_duplicate_correction shipped under BE-13
(split_out has a real runtime dependency on record_duplicate_correction).
This adds the dedicated coverage docs/testing-spec.md §4.5 calls out:
N=5 FIFO eviction on both buffers, the original_urgency_score
first-override-only guard (the exact bug named in data-model.md §7
finding 6 -- a one-line mutation away), both record_duplicate_correction
trigger points tested separately, and a buffer-reaches-prompt
integration test.
"""
from app.models.domain import Event, EventStatus, Location, Request, RequestStatus
from app.services.action_service import action_service
from app.services.feedback_service import record_duplicate_correction, record_urgency_override
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse


def make_request(store, id_, status=RequestStatus.STANDALONE, urgency=3, text=None, event_id=None, device="dev_1"):
    r = Request(id=id_, need_description=text or f"need-{id_}", location=Location(0, 0),
                device_fingerprint_id=device, status=status, urgency_score=urgency, event_id=event_id)
    store.requests[id_] = r
    return r


# --- original_urgency_score: first-override-only guard (the named regression) ---

def test_first_override_sets_original_urgency_score():
    store = InMemoryStore()
    r = make_request(store, "r1", urgency=2)
    record_urgency_override(store, "r1", corrected_score=5, reason="implies trapped", actor="c1")
    assert r.original_urgency_score == 2
    assert r.urgency_score == 5


def test_second_override_does_not_clobber_original_urgency_score():
    """The exact bug from docs/data-model.md §7 finding 6: a second
    override must not overwrite original_urgency_score with the
    intermediate coordinator-corrected value."""
    store = InMemoryStore()
    r = make_request(store, "r1", urgency=2)
    record_urgency_override(store, "r1", corrected_score=5, reason="first correction", actor="c1")
    record_urgency_override(store, "r1", corrected_score=4, reason="second correction", actor="c1")
    assert r.original_urgency_score == 2  # still the LLM's true original, not 5
    assert r.urgency_score == 4


def test_third_override_still_preserves_original():
    store = InMemoryStore()
    r = make_request(store, "r1", urgency=1)
    record_urgency_override(store, "r1", corrected_score=2, reason="a", actor="c1")
    record_urgency_override(store, "r1", corrected_score=3, reason="b", actor="c1")
    record_urgency_override(store, "r1", corrected_score=5, reason="c", actor="c1")
    assert r.original_urgency_score == 1
    assert r.urgency_score == 5


def test_override_urgency_logs_action_with_note():
    store = InMemoryStore()
    make_request(store, "r1", urgency=2)
    record_urgency_override(store, "r1", corrected_score=5, reason="my reason", actor="coordinator_1")
    log = [a for a in store.actions if a.action_type == "override_urgency"]
    assert len(log) == 1
    assert log[0].note == "my reason"
    assert log[0].actor == "coordinator_1"


# --- N=5 eviction, urgency buffer ---

def test_urgency_buffer_evicts_at_n5_fifo():
    store = InMemoryStore()
    for i in range(6):
        make_request(store, f"r{i}", urgency=1)
        record_urgency_override(store, f"r{i}", corrected_score=5, reason=f"reason-{i}", actor="c1")
    assert len(store.urgency_calibration_buffer) == 5
    # the FIRST call's entry (reason-0) must be the one evicted
    reasons = [e["reason"] for e in store.urgency_calibration_buffer]
    assert "reason-0" not in reasons
    assert reasons == [f"reason-{i}" for i in range(1, 6)]


# --- N=5 eviction, match buffer (via split_out) ---

def test_match_buffer_evicts_at_n5_fifo_via_split_out():
    store = InMemoryStore()
    client = FakeLLMClient()
    for i in range(6):
        a = make_request(store, f"a{i}", status=RequestStatus.IN_CANDIDATE_EVENT,
                          text=f"text-a{i}", event_id=f"evt_{i}")
        b = make_request(store, f"b{i}", status=RequestStatus.IN_CANDIDATE_EVENT,
                          text=f"text-b{i}", event_id=f"evt_{i}")
        store.events[f"evt_{i}"] = Event(id=f"evt_{i}", status=EventStatus.CANDIDATE,
                                          representative_location=Location(0, 0),
                                          member_request_ids=[f"a{i}", f"b{i}"])
        client.script(f"text-a{i}", ScriptedResponse())
        action_service.split_out(store, client, f"a{i}", actor="c1")

    assert len(store.match_calibration_buffer) == 5
    a_texts = [e["a"] for e in store.match_calibration_buffer]
    assert "text-a0" not in a_texts
    assert a_texts == [f"text-a{i}" for i in range(1, 6)]


# --- record_duplicate_correction's two trigger points, tested separately ---

def test_record_duplicate_correction_direct_call_populates_buffer():
    store = InMemoryStore()
    record_duplicate_correction(store, "text a", "text b", reason="manual test call")
    assert len(store.match_calibration_buffer) == 1
    assert store.match_calibration_buffer[0]["a"] == "text a"


def test_split_out_is_a_trigger_point_for_duplicate_correction():
    store = InMemoryStore()
    client = FakeLLMClient()
    a = make_request(store, "a1", status=RequestStatus.IN_CANDIDATE_EVENT, text="alpha", event_id="evt_1")
    b = make_request(store, "b1", status=RequestStatus.IN_CANDIDATE_EVENT, text="beta", event_id="evt_1")
    store.events["evt_1"] = Event(id="evt_1", status=EventStatus.CANDIDATE,
                                   representative_location=Location(0, 0), member_request_ids=["a1", "b1"])
    client.script("alpha", ScriptedResponse())

    assert store.match_calibration_buffer == []
    action_service.split_out(store, client, "a1", actor="c1")
    assert len(store.match_calibration_buffer) == 1


def test_dismiss_cluster_is_a_trigger_point_for_duplicate_correction():
    """dismiss_cluster doesn't itself call record_duplicate_correction per
    docs/design.md §4.6's pseudocode (no per-pair "wrong LLM judgment"
    signal exists for an N-member cluster dismissal the way split_out's
    single-pair sibling comparison does) -- this test documents that
    design choice explicitly rather than leaving it silently untested,
    so a future change adding it doesn't go unnoticed either way."""
    store = InMemoryStore()
    a = make_request(store, "a1", status=RequestStatus.IN_CANDIDATE_EVENT, text="alpha", event_id="evt_1")
    b = make_request(store, "b1", status=RequestStatus.IN_CANDIDATE_EVENT, text="beta", event_id="evt_1")
    store.events["evt_1"] = Event(id="evt_1", status=EventStatus.CANDIDATE,
                                   representative_location=Location(0, 0), member_request_ids=["a1", "b1"])

    action_service.dismiss_cluster(store, "evt_1", actor="c1")

    assert store.match_calibration_buffer == []


# --- buffer contents reach the rendered prompt (integration-level) ---

def test_calibration_buffer_contents_reach_the_rendered_prompt():
    from app.services.intake_service import submit

    store = InMemoryStore()
    client = FakeLLMClient()
    store.urgency_calibration_buffer.append(
        {"text": "trapped under debris", "original": 2, "corrected": 5, "reason": "implies trapped"}
    )
    client.script("new submission text", ScriptedResponse(urgency_score=4, urgency_reasoning="ok"))

    submit(store, client, need_description="new submission text", location=Location(1, 1),
           device_fingerprint_id="dev_1")

    assert len(client.calls) == 1
    rendered_prompt = client.calls[0]
    assert "trapped under debris" in rendered_prompt
    assert "implies trapped" in rendered_prompt
