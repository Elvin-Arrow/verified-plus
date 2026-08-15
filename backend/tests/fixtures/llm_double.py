"""TI-02: fixture-keyed LLM test double, per docs/testing-spec.md §6.2.

Deterministic, no network. `embed`/`complete` are keyed by the request's
`need_description` (or an explicit key) against a dict of pre-scripted
responses supplied by the test. Never calls a live provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.domain import MatchResult


class LLMTimeoutError(Exception):
    """Raised by the double (and the real client) on a simulated/actual call failure."""


class EmbeddingError(Exception):
    """Raised by the double (and the real client) on a simulated/actual embedding failure."""


@dataclass
class LLMCompletionResult:
    urgency_score: int
    urgency_reasoning: str
    matches: list[MatchResult] = field(default_factory=list)


@dataclass
class ScriptedResponse:
    urgency_score: int = 3
    urgency_reasoning: str = "default"
    matches: list[MatchResult] = field(default_factory=list)
    fail: bool = False  # simulate an LLM call failure for this key (NFR-103)


class FakeLLMClient:
    """Golden-response-fixture-backed fake of app.llm.client.LLMClient.

    - `script(key, response)` registers a canned response for a given
      `need_description` (or explicit key).
    - `embed` returns a small deterministic vector derived from the text
      (not a real embedding, but stable and comparable across calls with
      the same text) unless `fail_embedding_for` marks that key to raise.
    - `complete` records every prompt it was called with (`self.calls`) so
      integration tests can assert the calibration buffer reached the
      rendered prompt (docs/testing-spec.md §4.5).
    """

    def __init__(self) -> None:
        self._responses: dict[str, ScriptedResponse] = {}
        self._fail_embedding: set[str] = set()
        self.calls: list[str] = []
        self.embed_calls: list[str] = []

    def script(self, key: str, response: ScriptedResponse) -> None:
        self._responses[key] = response

    def fail_embedding_for(self, key: str) -> None:
        self._fail_embedding.add(key)

    def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        if text in self._fail_embedding:
            raise EmbeddingError(f"simulated embedding failure for {text!r}")
        # Deterministic pseudo-embedding: stable hash-derived floats so
        # identical/similar text compares consistently across calls.
        h = abs(hash(text))
        return [((h >> (8 * i)) & 0xFF) / 255.0 for i in range(8)]

    def complete(self, prompt: str, key: str | None = None) -> LLMCompletionResult:
        self.calls.append(prompt)
        lookup_key = key or prompt
        resp = self._responses.get(lookup_key)
        if resp is None:
            raise KeyError(
                f"FakeLLMClient has no scripted response for key {lookup_key!r} — "
                "call .script(key, ScriptedResponse(...)) in the test setup first"
            )
        if resp.fail:
            raise LLMTimeoutError(f"simulated LLM failure for {lookup_key!r}")
        return LLMCompletionResult(
            urgency_score=resp.urgency_score,
            urgency_reasoning=resp.urgency_reasoning,
            matches=list(resp.matches),
        )
