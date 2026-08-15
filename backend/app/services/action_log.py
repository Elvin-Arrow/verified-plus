"""FR-601: append-only coordinator action log. Shared by every service that
mutates state on a coordinator's behalf, so there is exactly one call site
that constructs a CoordinatorAction (actor, action_type, target_id,
timestamp, note) rather than each action function rolling its own."""
from __future__ import annotations

from app.models.domain import CoordinatorAction
from app.store.memory_store import InMemoryStore


def log_action(store: InMemoryStore, actor: str, action_type: str, target_id: str,
                note: str | None = None) -> CoordinatorAction:
    action = CoordinatorAction(
        id=store.new_id("act"),
        actor=actor,
        action_type=action_type,
        target_id=target_id,
        note=note,
    )
    store.actions.append(action)
    return action
