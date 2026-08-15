"""BE-04: InMemoryStore, the single source of truth. docs/design.md §3."""
from __future__ import annotations

import itertools
import threading

from app.models.domain import CoordinatorAction, DeviceFingerprint, Event, Request, SessionConfig


class InMemoryStore:
    def __init__(self, config: SessionConfig | None = None) -> None:
        self.requests: dict[str, Request] = {}
        self.events: dict[str, Event] = {}
        self.devices: dict[str, DeviceFingerprint] = {}
        self.actions: list[CoordinatorAction] = []
        self.urgency_calibration_buffer: list[dict] = []
        self.match_calibration_buffer: list[dict] = []
        self.suggested_merges: list[dict] = []
        self.config: SessionConfig = config or SessionConfig()
        self._lock = threading.Lock()
        self._id_counters: dict[str, itertools.count] = {}

    def new_id(self, prefix: str) -> str:
        """Monotonic, human-legible IDs (req_1, evt_1, dev_1, act_1, ...)."""
        counter = self._id_counters.setdefault(prefix, itertools.count(1))
        return f"{prefix}_{next(counter)}"

    def reset(self) -> None:
        """FR-702 reset-mode cascading wipe. Config is deliberately NOT reset
        here — the caller (seed_service.replay) applies FR-208 overrides (or
        defaults) explicitly after calling this, per docs/design.md §4.8."""
        self.requests.clear()
        self.events.clear()
        self.devices.clear()
        self.actions.clear()
        self.urgency_calibration_buffer.clear()
        self.match_calibration_buffer.clear()
        self.suggested_merges.clear()
        self._id_counters.clear()
