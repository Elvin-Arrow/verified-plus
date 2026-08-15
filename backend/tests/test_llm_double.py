"""TI-02: the fake LLM client behaves like a deterministic, fixture-keyed double."""
import json
from pathlib import Path

import pytest

from tests.fixtures.llm_double import (
    EmbeddingError,
    FakeLLMClient,
    LLMTimeoutError,
    ScriptedResponse,
)
from app.models.domain import MatchResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_complete_returns_scripted_response():
    client = FakeLLMClient()
    client.script("water", ScriptedResponse(urgency_score=3, urgency_reasoning="ok"))
    result = client.complete(prompt="irrelevant prompt text", key="water")
    assert result.urgency_score == 3
    assert result.urgency_reasoning == "ok"
    assert result.matches == []


def test_complete_unscripted_key_raises_not_silently_defaults():
    client = FakeLLMClient()
    with pytest.raises(KeyError):
        client.complete(prompt="p", key="unscripted")


def test_complete_simulated_failure_raises_llm_timeout_error():
    client = FakeLLMClient()
    client.script("flaky", ScriptedResponse(fail=True))
    with pytest.raises(LLMTimeoutError):
        client.complete(prompt="p", key="flaky")


def test_embed_is_deterministic_for_same_text():
    client = FakeLLMClient()
    v1 = client.embed("need water")
    v2 = client.embed("need water")
    assert v1 == v2


def test_embed_differs_for_different_text():
    client = FakeLLMClient()
    assert client.embed("need water") != client.embed("need food")


def test_embed_failure_simulation():
    client = FakeLLMClient()
    client.fail_embedding_for("bad text")
    with pytest.raises(EmbeddingError):
        client.embed("bad text")


def test_complete_records_calls_for_calibration_prompt_assertions():
    client = FakeLLMClient()
    client.script("k", ScriptedResponse())
    client.complete(prompt="the full rendered prompt", key="k")
    assert client.calls == ["the full rendered prompt"]


def test_matches_round_trip_as_match_result_dataclasses():
    client = FakeLLMClient()
    client.script(
        "k",
        ScriptedResponse(matches=[MatchResult(candidate_id="req_1", is_match=True, reason="close by")]),
    )
    result = client.complete(prompt="p", key="k")
    assert result.matches[0].candidate_id == "req_1"
    assert result.matches[0].is_match is True


def test_golden_response_fixtures_load_and_shape_matches_contract():
    data = json.loads((FIXTURES_DIR / "golden_responses.json").read_text())
    assert len(data) >= 1
    for entry in data:
        assert isinstance(entry["urgency_score"], int)
        assert 1 <= entry["urgency_score"] <= 5
        assert isinstance(entry["urgency_reasoning"], str) and entry["urgency_reasoning"]
        for m in entry["matches"]:
            assert set(m.keys()) == {"candidate_id", "is_match", "reason"}
