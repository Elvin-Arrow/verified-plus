"""FR-205/205b/304b/504b: cluster assignment & dissolution.

BE-07 wires the intake pipeline up to `assign()` but only needs the
trivial "remain standalone" behavior at this stage (§4.1 step 6's
fallback) — the full geometric-filter-then-authority algorithm,
bootstrapping, and `manual_merge` are BE-09's scope (docs/design.md §4.2)
and REPLACE this stub's body, not just extend it.
"""
from __future__ import annotations

from app.models.domain import MatchResult, Request, RequestStatus
from app.store.memory_store import InMemoryStore


def assign(store: InMemoryStore, request: Request, llm_matches: list[MatchResult]) -> None:
    """Placeholder pending BE-09: no matches are ever accepted yet, so
    every request remains standalone. This still satisfies FR-206 (a
    request with no LLM-judged matches SHALL be standalone)."""
    request.status = RequestStatus.STANDALONE
