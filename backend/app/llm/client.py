"""BE-05: llm/client.py interface — thin wrapper per docs/design.md §2/§5.

`embed(text) -> vector` and `complete(prompt) -> structured JSON` are the
only two operations services depend on. `LLMClient` is a `Protocol` so both
the real hosted-API implementation (`HostedLLMClient`) and the test double
(`tests/fixtures/llm_double.FakeLLMClient`) satisfy it structurally — no
inheritance required, matching docs/architecture.md's "thin LLM integration
boundary" framing.

No real API key is available/required in this environment (per the task
brief) — `HostedLLMClient` is written to the documented contract but is
never exercised by the test suite except the out-of-scope live smoke test
(docs/testing-spec.md §6.3), which is intentionally not part of this queue.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol

from app.models.domain import MatchResult


class LLMTimeoutError(Exception):
    """The chat/completion call failed or timed out (NFR-103)."""


class EmbeddingError(Exception):
    """The embedding call failed or timed out (NFR-103)."""


@dataclass
class LLMCompletionResult:
    """The parsed/validated shape of docs/design.md §5.1's structured
    output contract: {urgency_score, urgency_reasoning, matches: [...]}."""

    urgency_score: int
    urgency_reasoning: str
    matches: list[MatchResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (1 <= self.urgency_score <= 5):
            raise ValueError(f"urgency_score out of range 1-5: {self.urgency_score}")


class LLMClient(Protocol):
    """Structural interface every LLM client (real or fake) must satisfy."""

    def embed(self, text: str) -> list[float]:
        ...

    def complete(self, prompt: str, key: str | None = None) -> LLMCompletionResult:
        ...


class HostedLLMClient:
    """Real hosted-API implementation (embedding model + chat model, per
    docs/spec.md §3). Deliberately minimal — the actual HTTP call is
    isolated to these two methods so a provider swap never touches
    services/. Raises LLMTimeoutError/EmbeddingError uniformly on any
    failure so callers (intake_service, per docs/design.md §4.1) can
    catch one exception type each, regardless of the underlying cause."""

    def __init__(self, api_key: str | None = None, embedding_model: str = "text-embedding-3-small",
                 chat_model: str = "gpt-4o-mini", timeout_s: float = 5.0) -> None:
        self.api_key = api_key or os.environ.get("LLM_API_KEY")
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.timeout_s = timeout_s

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise EmbeddingError("no LLM_API_KEY configured — cannot call a live embedding model")
        try:
            import httpx

            resp = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.embedding_model, "input": text},
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception as exc:  # noqa: BLE001 — any failure maps to one error type (NFR-103)
            raise EmbeddingError(str(exc)) from exc

    def complete(self, prompt: str, key: str | None = None) -> LLMCompletionResult:
        if not self.api_key:
            raise LLMTimeoutError("no LLM_API_KEY configured — cannot call a live chat model")
        try:
            import httpx

            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            matches = [MatchResult(**m) for m in data.get("matches", [])]
            return LLMCompletionResult(
                urgency_score=data["urgency_score"],
                urgency_reasoning=data["urgency_reasoning"],
                matches=matches,
            )
        except Exception as exc:  # noqa: BLE001 — a validation failure is treated the same as a
            # call failure for NFR-103 purposes (never trust an unparseable response as urgency=3)
            raise LLMTimeoutError(str(exc)) from exc
