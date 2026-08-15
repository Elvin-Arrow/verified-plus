"""BE-12/BE-13/BE-14: coordinator actions (FR-502-507), each wrapping a
store mutation + audit log write. docs/design.md §4.2b/§4.4-4.6.

Exposed as a module-level `action_service` namespace object (rather than
free functions) so routers (BE-18) can `from app.services.action_service
import action_service` and call `action_service.verify_event(...)`
uniformly, matching docs/design.md §2's one-module-per-FR-block layout
without polluting `app.services.action_service`'s own module namespace
with dozens of top-level names.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.domain import ActionType, Event, EventStatus, Request, RequestStatus
from app.services.action_log import log_action
from app.services.clustering_service import recompute_centroid
from app.services.dissolution import detach_from_event
from app.store.memory_store import InMemoryStore


class InvalidStateTransition(Exception):
    """Maps to api-spec.md §1.1's 409 INVALID_STATE_TRANSITION."""

    def __init__(self, message: str, current_status: str | None = None, expected_status: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.current_status = current_status
        self.expected_status = expected_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _ActionService:
    # --- FR-304, FR-502 "Verify Event & Approve All" ---
    def verify_event(self, store: InMemoryStore, event_id: str, actor: str) -> Event:
        event = store.events[event_id]
        if event.status != EventStatus.CANDIDATE:
            raise InvalidStateTransition(
                "only a candidate Event can be verified",
                current_status=event.status.value, expected_status=EventStatus.CANDIDATE.value,
            )
        event.status = EventStatus.VERIFIED
        event.verified_by = actor
        event.verified_at = _now()
        for rid in event.member_request_ids:  # only CURRENT members -- FR-304
            r = store.requests[rid]
            r.status = RequestStatus.IN_VERIFIED_EVENT
            r.verified = True
        log_action(store, actor, ActionType.VERIFY_EVENT.value, event_id)
        return event

    # --- FR-304b, FR-502 "Approve All Pending" ---
    def approve_pending(self, store: InMemoryStore, event_id: str, actor: str) -> Event:
        event = store.events[event_id]
        if event.status != EventStatus.VERIFIED:
            raise InvalidStateTransition(
                "only a verified Event can approve pending members",
                current_status=event.status.value, expected_status=EventStatus.VERIFIED.value,
            )
        if not event.pending_member_request_ids:
            raise InvalidStateTransition("no pending members to approve", current_status="0 pending")
        for rid in event.pending_member_request_ids:
            r = store.requests[rid]
            r.status = RequestStatus.IN_VERIFIED_EVENT
            r.verified = True
            event.member_request_ids.append(rid)  # promoted: now counts for FR-501/504b
        event.pending_member_request_ids.clear()
        recompute_centroid(store, event)
        log_action(store, actor, ActionType.APPROVE_PENDING.value, event_id)
        return event

    # --- FR-502 "Approve" (dispatch a verified Event) ---
    def dispatch_event(self, store: InMemoryStore, event_id: str, actor: str) -> Event:
        event = store.events[event_id]
        if event.status != EventStatus.VERIFIED:
            raise InvalidStateTransition(
                "only a verified Event can be dispatched",
                current_status=event.status.value, expected_status=EventStatus.VERIFIED.value,
            )
        event.status = EventStatus.DISPATCHED
        for rid in event.member_request_ids:  # current active members only -- pending_addition
            r = store.requests[rid]            # members are NOT swept along; must be promoted
            r.status = RequestStatus.DISPATCHED  # via approve_pending first
            r.verified = True
        log_action(store, actor, ActionType.APPROVE_DISPATCH.value, event_id)
        return event

    # --- FR-505 ---
    def reject_standalone(self, store: InMemoryStore, request_id: str, actor: str) -> Request:
        r = store.requests[request_id]
        if r.status != RequestStatus.STANDALONE:
            raise InvalidStateTransition(
                "only a standalone request can be rejected this way",
                current_status=r.status.value, expected_status=RequestStatus.STANDALONE.value,
            )
        r.status = RequestStatus.REJECTED
        log_action(store, actor, ActionType.REJECT_STANDALONE.value, request_id)
        return r

    def verify_standalone(self, store: InMemoryStore, request_id: str, actor: str) -> Request:
        r = store.requests[request_id]
        if r.status != RequestStatus.STANDALONE:
            raise InvalidStateTransition(
                "only a standalone request can be verified this way",
                current_status=r.status.value, expected_status=RequestStatus.STANDALONE.value,
            )
        r.verified = True
        r.status = RequestStatus.DISPATCHED  # terminal immediately -- atomic, no intermediate state
        log_action(store, actor, ActionType.VERIFY_STANDALONE.value, request_id)
        return r

    # --- FR-505b ---
    def dispatch_standalone(self, store: InMemoryStore, request_id: str, actor: str) -> Request:
        r = store.requests[request_id]
        if r.status != RequestStatus.STANDALONE or not r.verified:
            raise InvalidStateTransition(
                "only reachable for the FR-504b case: verified via a dissolved Event, not yet dispatched",
                current_status=f"status={r.status.value}, verified={r.verified}",
            )
        r.status = RequestStatus.DISPATCHED
        log_action(store, actor, ActionType.DISPATCH_STANDALONE.value, request_id)
        return r

    # --- FR-504: Split Out ---
    def split_out(self, store: InMemoryStore, llm_client, request_id: str, actor: str) -> Request:
        from app.services import matching_service
        from app.services.feedback_service import record_duplicate_correction

        r = store.requests[request_id]
        if not r.event_id:
            raise InvalidStateTransition("nothing to split out of", current_status="no event_id")

        # capture a sibling's text for calibration BEFORE detaching, while
        # r.event_id still resolves
        event = store.events.get(r.event_id)
        sibling_text = None
        if event:
            for mid in event.member_request_ids:
                if mid != r.id and mid in store.requests:
                    sibling_text = store.requests[mid].need_description
                    break

        detach_from_event(store, r)  # clears event_id, may dissolve
        r.status = RequestStatus.STANDALONE
        r.verified = False  # FR-504: "re-evaluated independently" -- the request split OUT
        # never keeps any prior approval (opposite of FR-504b dissolution's sole survivor)

        if sibling_text:
            record_duplicate_correction(
                store, r.need_description, sibling_text,
                reason="coordinator split this request out of a cluster",
            )
        log_action(store, actor, ActionType.SPLIT_OUT.value, request_id)
        matching_service.rerun(store, llm_client, r)  # re-run against the current pool
        return r

    # --- FR-407: Rescue ---
    def rescue(self, store: InMemoryStore, llm_client, request_id: str, actor: str) -> Request:
        from app.services import matching_service

        r = store.requests[request_id]
        if r.status != RequestStatus.QUARANTINED:
            raise InvalidStateTransition(
                "not quarantined", current_status=r.status.value, expected_status=RequestStatus.QUARANTINED.value,
            )
        r.status = RequestStatus.STANDALONE
        r.verified = False
        log_action(store, actor, ActionType.RESCUE_FROM_QUARANTINE.value, request_id)
        matching_service.rerun(store, llm_client, r)
        return r

    # --- FR-507: Dismiss Cluster ---
    def dismiss_cluster(self, store: InMemoryStore, event_id: str, actor: str) -> list[str]:
        event = store.events[event_id]
        if event.status != EventStatus.CANDIDATE:
            raise InvalidStateTransition(
                "Dismiss Cluster only valid on candidate Events",
                current_status=event.status.value, expected_status=EventStatus.CANDIDATE.value,
            )
        reverted_ids = list(event.member_request_ids)
        for rid in reverted_ids:
            r = store.requests[rid]
            r.event_id = None
            r.status = RequestStatus.STANDALONE
            # no device_flag touched anywhere here -- that's the entire point of FR-507
        del store.events[event_id]
        log_action(store, actor, ActionType.DISMISS_CLUSTER.value, event_id)
        return reverted_ids


action_service = _ActionService()
