"""BE-19: seed/replay, incl. full cascading wipe (FR-701-702).

The placeholder 3-request batch from BE-18 is replaced here with the full
~50-request batch design FR-701 requires: several genuine multi-device
event clusters, at least one single-device fraud cluster, and several
standalone unrelated requests -- submitted through the real intake API
(intake_service.submit), never a direct store write.
"""
from app.models.domain import CoordinatorAction, DeviceFingerprint, RequestStatus
from app.services import seed_service
from app.services.action_service import action_service
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse


def _auto_scripted_client():
    """A client that scores everything a neutral 3 and never reports a
    match -- sufficient to drive every seed request through the real
    intake pipeline without per-text scripting; clustering's own
    correctness is already covered by tests/test_clustering_assign.py."""
    client = FakeLLMClient()

    class _AutoDict(dict):
        def get(self, key, default=None):
            return super().get(key, ScriptedResponse(urgency_score=3, urgency_reasoning="auto"))

    client._responses = _AutoDict()
    return client


# --- batch composition (FR-701) ---

def test_seed_batch_has_at_least_50_requests():
    assert len(seed_service.SEED_BATCH) >= 50


def test_seed_batch_has_multiple_distinct_devices():
    devices = {s.device_fingerprint_id for s in seed_service.SEED_BATCH}
    assert len(devices) >= 10


def test_seed_batch_has_a_single_device_fraud_cluster():
    """At least one device submits several (>=3) near-identical/rapid
    requests -- the seeded fraud shape."""
    from collections import Counter
    counts = Counter(s.device_fingerprint_id for s in seed_service.SEED_BATCH)
    assert any(c >= 3 for device, c in counts.items() if device.startswith("dev_fraud"))


def test_seed_batch_has_several_standalone_unrelated_requests():
    standalone_devices = [s for s in seed_service.SEED_BATCH if s.device_fingerprint_id.startswith("dev_standalone")]
    assert len(standalone_devices) >= 5


def test_seed_batch_has_genuine_multi_device_event_clusters():
    """Several groups of >=2 distinct devices submitting from
    near-identical coordinates (a genuine corroborating-witness shape)."""
    clusters = {}
    for s in seed_service.SEED_BATCH:
        if s.device_fingerprint_id.startswith("dev_cluster"):
            key = s.device_fingerprint_id.split("_")[2]  # dev_cluster_<n>_<i>
            clusters.setdefault(key, set()).add(s.device_fingerprint_id)
    multi_device_clusters = [c for c in clusters.values() if len(c) >= 2]
    assert len(multi_device_clusters) >= 2


# --- reset mode: full cascading wipe (FR-702) ---

def test_reset_mode_submits_the_full_batch_through_the_real_intake_api():
    store = InMemoryStore()
    client = _auto_scripted_client()
    result = seed_service.replay(store, client, mode="reset")
    assert result["mode"] == "reset"
    assert result["wiped"] is True
    assert result["requests_submitted"] == len(seed_service.SEED_BATCH)
    assert len(store.requests) == len(seed_service.SEED_BATCH)


def test_reset_mode_performs_full_cascading_wipe_of_prior_state():
    store = InMemoryStore()
    client = _auto_scripted_client()

    seed_service.replay(store, client, mode="reset")
    # simulate coordinator activity between runs
    store.devices["dev_manual"] = DeviceFingerprint(id="dev_manual", device_flag=True)
    store.actions.append(CoordinatorAction(id="act_manual", actor="c1", action_type="verify_event", target_id="evt_x"))
    store.urgency_calibration_buffer.append({"text": "x", "original": 1, "corrected": 5, "reason": "y"})
    store.match_calibration_buffer.append({"a": "x", "b": "y", "reason": "z"})
    store.suggested_merges.append({"request_id": "r1", "event_id": "evt_far", "distance_km": 2.0})

    result = seed_service.replay(store, client, mode="reset")

    assert result["wiped"] is True
    # no leftover manual state survives a reset
    assert "dev_manual" not in store.devices
    assert not any(a.id == "act_manual" for a in store.actions)
    assert not any(e.get("text") == "x" and e.get("original") == 1 for e in store.urgency_calibration_buffer)
    assert store.match_calibration_buffer == [] or all(e.get("a") != "x" for e in store.match_calibration_buffer)
    assert store.suggested_merges == [] or all(sm.get("request_id") != "r1" for sm in store.suggested_merges)
    # exactly the fresh batch's requests exist -- no orphaned IDs from the prior run
    assert len(store.requests) == len(seed_service.SEED_BATCH)


def test_reset_mode_leaves_no_dangling_event_ids_from_prior_run():
    store = InMemoryStore()
    client = _auto_scripted_client()
    seed_service.replay(store, client, mode="reset")
    seed_service.replay(store, client, mode="reset")
    for r in store.requests.values():
        assert r.event_id is None or r.event_id in store.events


def test_reset_mode_applies_fr208_overrides():
    store = InMemoryStore()
    client = _auto_scripted_client()
    seed_service.replay(store, client, mode="reset", geofence_radius_km=2.5, max_cluster_span_km=4.0)
    assert store.config.geofence_radius_km == 2.5
    assert store.config.max_cluster_span_km == 4.0


def test_reset_mode_without_overrides_uses_fr208_defaults():
    store = InMemoryStore()
    client = _auto_scripted_client()
    seed_service.replay(store, client, mode="reset")
    assert store.config.geofence_radius_km == 1.0
    assert store.config.max_cluster_span_km == 1.5


# --- append mode: no wipe ---

def test_append_mode_does_not_wipe_existing_state():
    store = InMemoryStore()
    client = _auto_scripted_client()
    seed_service.replay(store, client, mode="reset")
    count_after_first = len(store.requests)

    result = seed_service.replay(store, client, mode="append")

    assert result["wiped"] is False
    assert len(store.requests) == count_after_first + len(seed_service.SEED_BATCH)


def test_append_mode_ignores_fr208_overrides_with_no_config_change():
    store = InMemoryStore()
    client = _auto_scripted_client()
    seed_service.replay(store, client, mode="reset")  # defaults
    seed_service.replay(store, client, mode="append", geofence_radius_km=9.0)
    assert store.config.geofence_radius_km == 1.0  # unchanged -- append ignores FR-208 params
