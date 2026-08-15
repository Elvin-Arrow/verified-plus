"""FR-601-605: audit log + calibration buffer maintenance. docs/design.md §4.7.

Full dedicated test coverage (N=5 eviction, both `record_duplicate_
correction` trigger points, buffer-reaches-prompt) lands under BE-15/#20
-- this module is introduced here because `split_out`/`dismiss_cluster`
(BE-13) have a real runtime dependency on `record_duplicate_correction`,
same pattern as BE-07 pulling `matching_service` forward for BE-08.
"""
from __future__ import annotations

from app.services.action_log import log_action
from app.store.memory_store import InMemoryStore


def record_urgency_override(store: InMemoryStore, request_id: str, corrected_score: int,
                             reason: str | None, actor: str) -> None:
    r = store.requests[request_id]
    if r.original_urgency_score is None:
        # set ONLY on the first override (data-model.md §2.1) -- a second
        # override must not clobber the LLM's true original with an
        # intermediate coordinator-corrected value.
        r.original_urgency_score = r.urgency_score
    r.urgency_score = corrected_score
    store.urgency_calibration_buffer.append({
        "text": r.need_description,
        "original": r.original_urgency_score,
        "corrected": corrected_score,
        "reason": reason,
    })
    n = store.config.calibration_buffer_n
    store.urgency_calibration_buffer[:] = store.urgency_calibration_buffer[-n:]
    log_action(store, actor, "override_urgency", request_id, note=reason)


def record_duplicate_correction(store: InMemoryStore, request_a_text: str, request_b_text: str,
                                 reason: str) -> None:
    """Called from split_out() and dismiss_cluster() -- both imply "the
    LLM's match judgment was wrong"."""
    store.match_calibration_buffer.append({"a": request_a_text, "b": request_b_text, "reason": reason})
    n = store.config.calibration_buffer_n
    store.match_calibration_buffer[:] = store.match_calibration_buffer[-n:]
