"""BE-04: InMemoryStore construction, ID generation, reset semantics."""
from app.models.domain import CoordinatorAction, DeviceFingerprint, Location, Request, SessionConfig
from app.store.memory_store import InMemoryStore


def test_store_starts_empty():
    store = InMemoryStore()
    assert store.requests == {}
    assert store.events == {}
    assert store.devices == {}
    assert store.actions == []
    assert store.urgency_calibration_buffer == []
    assert store.match_calibration_buffer == []
    assert store.suggested_merges == []


def test_store_default_config_matches_fr208_defaults():
    store = InMemoryStore()
    assert store.config.geofence_radius_km == 1.0
    assert store.config.max_cluster_span_km == 1.5


def test_store_accepts_custom_config():
    cfg = SessionConfig(geofence_radius_km=2.0, max_cluster_span_km=3.0)
    store = InMemoryStore(config=cfg)
    assert store.config.geofence_radius_km == 2.0


def test_new_id_is_monotonic_and_prefixed():
    store = InMemoryStore()
    ids = [store.new_id("req") for _ in range(3)]
    assert ids == ["req_1", "req_2", "req_3"]


def test_new_id_counters_are_independent_per_prefix():
    store = InMemoryStore()
    assert store.new_id("req") == "req_1"
    assert store.new_id("evt") == "evt_1"
    assert store.new_id("req") == "req_2"


def test_reset_cascading_wipe_clears_everything_but_not_config():
    store = InMemoryStore()
    store.requests["req_1"] = Request(
        id="req_1", need_description="x", location=Location(0, 0), device_fingerprint_id="dev_1"
    )
    store.devices["dev_1"] = DeviceFingerprint(id="dev_1")
    store.actions.append(CoordinatorAction(id="act_1", actor="c", action_type="verify_event", target_id="evt_1"))
    store.urgency_calibration_buffer.append({"a": 1})
    store.match_calibration_buffer.append({"b": 1})
    store.suggested_merges.append({"c": 1})
    store.new_id("req")  # advance a counter

    store.reset()

    assert store.requests == {}
    assert store.events == {}
    assert store.devices == {}
    assert store.actions == []
    assert store.urgency_calibration_buffer == []
    assert store.match_calibration_buffer == []
    assert store.suggested_merges == []
    # counters reset too, so a fresh seed batch after reset doesn't produce
    # IDs that collide-by-skipping with a prior run's numbering scheme
    assert store.new_id("req") == "req_1"


def test_lock_is_present_and_acquirable():
    store = InMemoryStore()
    with store._lock:
        pass
