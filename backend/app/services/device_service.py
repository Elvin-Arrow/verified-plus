"""BE-14 (HIGH RISK): device_flag lifecycle, quarantine sweep. docs/design.md §4.4.

FR-306, FR-308, FR-503, FR-407. `reject_and_flag_device` is the exact
function `docs/testing-spec.md` §4.3's Invariant 1 regression targets --
it MUST route every membership removal through
`dissolution.detach_from_event` (never mutate `status` alone), or a
member's status can flip to `rejected` without the Event's
`member_request_ids` ever shrinking, and `maybe_dissolve_event` never
fires -- a ghost Event, full of already-rejected requests, forever.
"""
from __future__ import annotations

from app.models.domain import ActionType, DeviceFingerprint, RequestStatus
from app.services.action_log import log_action
from app.services.dissolution import detach_from_event
from app.store.memory_store import InMemoryStore

_TERMINAL = {RequestStatus.DISPATCHED, RequestStatus.REJECTED}


class _DeviceService:
    def reject_and_flag_device(self, store: InMemoryStore, event_id: str, device_id: str, actor: str) -> dict:
        with store._lock:  # BE-20: coarse lock around the whole mutation, per docs/design.md §6.4
            event = store.events[event_id]  # KeyError -> 404 at the router layer
            this_cards_members = [
                r for r in (store.requests[rid] for rid in list(event.member_request_ids))
                if r.device_fingerprint_id == device_id
            ]
            if not this_cards_members:
                # api-spec.md §4: "404 (bad event_id or device_id -- i.e. that
                # device has no requests on this card)" -- validated before any
                # mutation (device_flag included) so a bad call is a true no-op.
                raise KeyError(f"device {device_id} has no requests on event {event_id}")

            device = store.devices.setdefault(device_id, DeviceFingerprint(id=device_id))
            device.device_flag = True  # FR-306

            rejected_ids: list[str] = []
            for r in this_cards_members:
                r.status = RequestStatus.REJECTED  # FR-503(b) -- terminal
                device.confirmed_fraud_request_ids.append(r.id)  # data-model.md §2.3 audit trail
                detach_from_event(store, r)  # removes from member/pending list + clears event_id + dissolve check
                rejected_ids.append(r.id)

            quarantined_ids: list[str] = []
            for r in list(store.requests.values()):  # FR-503(c) / FR-308(b)
                if r.device_fingerprint_id == device_id and r.status not in _TERMINAL and r.status != RequestStatus.QUARANTINED:
                    r.status = RequestStatus.QUARANTINED
                    if r.event_id:
                        detach_from_event(store, r)
                    quarantined_ids.append(r.id)

            log_action(store, actor, ActionType.REJECT_FLAG_DEVICE.value, event_id, note=f"device={device_id}")

            survives = event_id in store.events
            return {
                "event": store.events[event_id] if survives else None,
                "rejected_request_ids": rejected_ids,
                "quarantined_request_ids": quarantined_ids,
                "event_dissolved": not survives,
            }

    def reject_all_quarantined(self, store: InMemoryStore, device_id: str, actor: str) -> list[str]:
        with store._lock:
            rejected_ids = []
            for r in store.requests.values():
                if r.device_fingerprint_id == device_id and r.status == RequestStatus.QUARANTINED:
                    r.status = RequestStatus.REJECTED  # terminal; already detached during the sweep
                    rejected_ids.append(r.id)
            # deliberately does NOT touch device.device_flag -- it's already
            # True (that's why these requests were quarantined); this is
            # disposal, not a fraud confirmation.
            log_action(store, actor, ActionType.REJECT_QUARANTINED_GROUP.value, device_id,
                       note=f"{len(rejected_ids)} requests")
            return rejected_ids


device_service = _DeviceService()
