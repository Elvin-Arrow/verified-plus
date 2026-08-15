"""DA-02: the held-out human-labeled dedup validation set.

docs/idea.md's Data strategy section names the evaluation-circularity
problem directly: the seed batch (DA-01, backend/app/services/seed_service.py
SEED_BATCH) and its duplicate/fraud shapes are authored to exercise the
clustering pipeline, not to serve as an *independent* accuracy measurement --
a dedup metric scored only against data shaped for the pipeline it's testing
is partly self-fulfilling.

This fixture is the antidote: a small, standalone set of request-text pairs,
hand-labeled true/false for "describes the same underlying incident", that
is NOT drawn from or derived by rewriting anything in SEED_BATCH -- distinct
locations, distinct phrasing patterns, authored directly against the
FR-204/FR-205 "is this the same event" question rather than through the
HumAID/CrisisNLP-rewrite pipeline DA-01 used. A future evaluation harness
(matching_service run against text_a/text_b with the geofence pre-filter's
distance_km input) reports accuracy against this set as "accuracy on a
small human-labeled sample" -- never as "dedup accuracy" unqualified,
per idea.md's own honesty note.
"""
import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dedup_validation_set.json"


def _load():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def test_fixture_file_exists():
    assert FIXTURE_PATH.exists(), "DA-02 validation set fixture is missing"


def test_has_at_least_two_dozen_pairs():
    data = _load()
    assert len(data["pairs"]) >= 24


def test_every_pair_has_required_fields():
    data = _load()
    for pair in data["pairs"]:
        assert isinstance(pair["id"], str) and pair["id"]
        assert isinstance(pair["text_a"], str) and pair["text_a"]
        assert isinstance(pair["text_b"], str) and pair["text_b"]
        assert isinstance(pair["distance_km"], (int, float))
        assert isinstance(pair["is_duplicate"], bool)
        assert isinstance(pair["note"], str) and pair["note"]


def test_both_labels_are_represented_and_reasonably_balanced():
    data = _load()
    dupes = [p for p in data["pairs"] if p["is_duplicate"]]
    non_dupes = [p for p in data["pairs"] if not p["is_duplicate"]]
    assert len(dupes) >= 8
    assert len(non_dupes) >= 8


def test_non_duplicates_include_near_misses_not_just_obviously_unrelated_text():
    """The honest-limitation note specifically calls for 'near-miss
    non-duplicates' (lexically/topically similar text describing genuinely
    different incidents), not just an easy contrast set -- otherwise the
    metric would be trivially inflated."""
    data = _load()
    near_misses = [
        p for p in data["pairs"]
        if not p["is_duplicate"] and p.get("near_miss") is True
    ]
    assert len(near_misses) >= 5


def test_pair_ids_are_unique():
    data = _load()
    ids = [p["id"] for p in data["pairs"]]
    assert len(ids) == len(set(ids))


def test_no_pair_text_is_copied_verbatim_from_the_seed_batch():
    """Independence check: this set must not be secretly derived from
    DA-01's SEED_BATCH (that would reintroduce the exact circularity this
    fixture exists to avoid)."""
    from app.services.seed_service import SEED_BATCH

    seed_texts = {s.need_description.strip().lower() for s in SEED_BATCH}
    data = _load()
    for pair in data["pairs"]:
        assert pair["text_a"].strip().lower() not in seed_texts
        assert pair["text_b"].strip().lower() not in seed_texts


def test_methodology_metadata_present():
    data = _load()
    assert "methodology" in data
    assert "human-labeled" in data["methodology"].lower()
