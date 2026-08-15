"""BE-03: lexicographic_sort shared by FR-401/FR-403.

Per docs/design.md §4.3: sort_key() operates on "an item" that resolves to a
list of member Requests (a standalone Request is its own single-member
list). This module stays decoupled from InMemoryStore — callers pass in a
`resolve_members` function so sort.py has zero store/domain-service
dependencies, per docs/testing-spec.md §3.1 ("no mocks needed — these are
deterministic functions over plain data").
"""
from __future__ import annotations

from typing import Callable, TypeVar

from app.models.domain import Request

T = TypeVar("T")

ResolveMembers = Callable[[T], list[Request]]


def sort_key(item: T, resolve_members: ResolveMembers) -> tuple[int, int]:
    """(max_urgency_score, distinct_device_fingerprint_count) — descending
    sort key. Callers must exclude Needs-Manual-Triage items (any member
    with urgency_score is None) before calling this; -1 below is only a
    defensive default, never expected to participate in a real sort."""
    members = resolve_members(item)
    urgencies = [m.urgency_score for m in members if m.urgency_score is not None]
    max_urgency = max(urgencies) if urgencies else -1
    distinct_devices = len({m.device_fingerprint_id for m in members})
    return (max_urgency, distinct_devices)


def needs_manual_triage(item: T, resolve_members: ResolveMembers) -> bool:
    return any(m.urgency_score is None for m in resolve_members(item))


def sorted_queue(items: list[T], resolve_members: ResolveMembers) -> tuple[list[T], list[T]]:
    """Returns (needs_manual_triage, sorted_rest) per FR-401 §1/§2. The
    caller decides how to render/concatenate them (FR-401 needs both
    sections separately; FR-403 typically ignores the triage list since
    the Dispatch Queue only contains already-verified, already-scored
    items, but the split is returned uniformly either way)."""
    triage = [i for i in items if needs_manual_triage(i, resolve_members)]
    triage_ids = {id(i) for i in triage}
    rest = [i for i in items if id(i) not in triage_ids]
    rest_sorted = sorted(rest, key=lambda i: sort_key(i, resolve_members), reverse=True)
    return triage, rest_sorted
