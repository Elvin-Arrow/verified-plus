"""BE-06: prompt assembly — rubric snapshot, calibration block, FR-204 distances.

Per docs/testing-spec.md §3.1: "Snapshot test against the literal rubric
text in spec.md §4.3 — a rubric edit in spec.md without a matching
prompt-template update should fail this test."
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.llm.prompts import (
    RUBRIC_TABLE_MD,
    calibration_block,
    urgency_and_match_prompt,
)
from app.models.domain import Location, Request

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "spec.md"


def _make_request(id_="req_1", text="need water", device="dev_1"):
    return Request(id=id_, need_description=text, location=Location(0, 0), device_fingerprint_id=device)


def test_rubric_table_is_verbatim_substring_of_spec_md():
    spec_text = SPEC_PATH.read_text()
    for line in RUBRIC_TABLE_MD.splitlines():
        assert line in spec_text, f"rubric line drifted from spec.md: {line[:60]}..."


def test_rubric_contains_all_five_score_rows():
    for score in ["**5**", "**4**", "**3**", "**2**", "**1**"]:
        assert score in RUBRIC_TABLE_MD


def test_calibration_block_empty_when_both_buffers_empty():
    assert calibration_block([], []) == ""


def test_calibration_block_renders_urgency_entries():
    block = calibration_block(
        [{"text": "trapped", "original": 2, "corrected": 5, "reason": "implies trapped"}], []
    )
    assert "trapped" in block
    assert "2" in block and "5" in block


def test_calibration_block_renders_match_entries():
    block = calibration_block([], [{"a": "text a", "b": "text b", "reason": "same event"}])
    assert "text a" in block and "text b" in block


def test_urgency_and_match_prompt_includes_rubric_and_request_text():
    request = _make_request(text="my father collapsed")
    prompt = urgency_and_match_prompt(request, candidates=[], distances={})
    assert "my father collapsed" in prompt
    assert "Immediate threat to life" in prompt


def test_urgency_and_match_prompt_includes_explicit_distance_not_just_coords():
    now = datetime.now(timezone.utc)
    request = _make_request(id_="req_new", text="flooding here")
    candidate = _make_request(id_="req_990z", text="flooding nearby")
    candidate.submitted_at = now - timedelta(minutes=40)
    prompt = urgency_and_match_prompt(
        request, candidates=[candidate], distances={"req_990z": 0.15}, now=now
    )
    assert "150m away" in prompt
    assert "40 min ago" in prompt
    assert "req_990z" in prompt


def test_urgency_and_match_prompt_includes_calibration_when_buffers_present():
    request = _make_request()
    prompt = urgency_and_match_prompt(
        request, candidates=[], distances={},
        urgency_buffer=[{"text": "x", "original": 2, "corrected": 5, "reason": "y"}],
    )
    assert "Recent coordinator corrections" in prompt


def test_urgency_and_match_prompt_omits_calibration_when_buffers_empty():
    request = _make_request()
    prompt = urgency_and_match_prompt(request, candidates=[], distances={})
    assert "Recent coordinator corrections" not in prompt
