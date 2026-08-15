"""BE-05: llm/client.py interface contract.

No live network calls here (no API key in this environment, per the task
brief) — these tests exercise the parts reachable without one: the
structured-result validation, and the "no key configured" failure path,
which itself proves failures raise the documented exception types rather
than crashing with something callers don't expect (NFR-103's contract).
"""
import pytest

from app.llm.client import EmbeddingError, HostedLLMClient, LLMCompletionResult, LLMTimeoutError
from app.models.domain import MatchResult


def test_llm_completion_result_accepts_valid_score():
    r = LLMCompletionResult(urgency_score=3, urgency_reasoning="ok")
    assert r.urgency_score == 3
    assert r.matches == []


@pytest.mark.parametrize("bad_score", [0, 6, -1, 100])
def test_llm_completion_result_rejects_out_of_range_score(bad_score):
    with pytest.raises(ValueError):
        LLMCompletionResult(urgency_score=bad_score, urgency_reasoning="x")


def test_llm_completion_result_holds_match_results():
    r = LLMCompletionResult(
        urgency_score=4, urgency_reasoning="x",
        matches=[MatchResult(candidate_id="req_1", is_match=True, reason="close")],
    )
    assert r.matches[0].candidate_id == "req_1"


def test_hosted_client_without_api_key_raises_embedding_error_not_crash():
    client = HostedLLMClient(api_key=None)
    with pytest.raises(EmbeddingError):
        client.embed("some text")


def test_hosted_client_without_api_key_raises_llm_timeout_error_not_crash():
    client = HostedLLMClient(api_key=None)
    with pytest.raises(LLMTimeoutError):
        client.complete("some prompt")


def test_hosted_client_defaults_match_spec_assumed_baseline():
    client = HostedLLMClient(api_key="fake-key-for-construction-only")
    assert client.embedding_model == "text-embedding-3-small"
    assert client.chat_model == "gpt-4o-mini"


def test_fake_llm_client_satisfies_the_same_structural_interface():
    from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse

    fake = FakeLLMClient()
    fake.script("k", ScriptedResponse(urgency_score=4, urgency_reasoning="r"))
    assert fake.embed("text") == fake.embed("text")
    result = fake.complete(prompt="p", key="k")
    assert isinstance(result, LLMCompletionResult)
