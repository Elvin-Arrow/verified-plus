"""BE-06: prompt templates. docs/design.md §5.2.

FR-301's rubric table is embedded verbatim below (RUBRIC_TABLE_MD is a
byte-for-byte copy of docs/spec.md §4.3's table) rather than paraphrased,
per FR-301's "SHALL be embedded verbatim... so scoring is reproducible."
tests/test_prompts.py snapshot-tests this constant against the literal
spec.md text so a rubric edit there without a matching update here fails
loudly, per docs/testing-spec.md §3.1.
"""
from __future__ import annotations

from app.models.domain import Location, Request

RUBRIC_TABLE_MD = """\
| Score | Label | Criteria | Examples |
|---|---|---|---|
| **5** | Immediate threat to life | Person(s) trapped, unable to escape, or in active physical danger; medical emergency (unconscious, severe bleeding, not breathing, in labor, cardiac/stroke symptoms); imminent structural or environmental danger (collapsing building, active fire, rising floodwater with people inside). | "trapped under rubble, can't move my leg"; "my father collapsed, not responding"; "water is rising fast, we're on the roof" |
| **4** | Serious, time-sensitive risk | Injured but currently stable; exposed to severe weather/conditions with no shelter; a known medical condition running out of a critical supply within hours (insulin, oxygen, dialysis); unaccompanied children, elderly, or disabled individuals in an unsafe-but-not-immediately-life-threatening situation. | "broken arm, in pain, no transport to clinic"; "insulin runs out tonight"; "3 kids alone since yesterday, no adult" |
| **3** | Urgent unmet basic need | No access to clean water or food for self/household; displaced with no shelter but not facing immediate exposure danger; a medical need that should be treated within a day or two, not this hour. | "no clean water for 2 days"; "house flooded, we're staying with neighbors but need somewhere"; "wound needs cleaning, not bleeding badly" |
| **2** | Important, not urgent | General supply request (blankets, hygiene kits, routine food resupply) for a household that is otherwise safe; property damage with no one at risk. | "need blankets for winter"; "roof damaged, we're fine, need tarp eventually" |
| **1** | Non-urgent / informational | Requests that could reasonably wait days without harm; general information requests; low-priority asks. | "when will the aid center reopen"; "would like extra supplies if available" |"""

AMBIGUOUS_DEFAULT_INSTRUCTION = (
    "If the free-text description does not clearly indicate severity (e.g. it's ambiguous, "
    "truncated, or off-topic), default to urgency_score 3 rather than silently guessing at "
    "either extreme, and set urgency_reasoning to explicitly state the score is a default due "
    "to insufficient information."
)

SCORE_CONTENT_NOT_FLUENCY_INSTRUCTION = (
    "Score based on described severity, not on writing fluency, message length, or language; "
    "brevity or non-native phrasing must NOT by itself lower the score."
)


def system_prompt() -> str:
    return (
        "You are triaging aid requests.\n\n"
        f"{RUBRIC_TABLE_MD}\n\n"
        f"{AMBIGUOUS_DEFAULT_INSTRUCTION}\n"
        f"{SCORE_CONTENT_NOT_FLUENCY_INSTRUCTION}"
    )


def calibration_block(urgency_buffer: list[dict], match_buffer: list[dict]) -> str:
    """FR-604: renders only when at least one buffer is non-empty."""
    if not urgency_buffer and not match_buffer:
        return ""
    lines = ["Recent coordinator corrections to learn from:"]
    for entry in urgency_buffer:
        lines.append(
            f"- text: '{entry['text']}' | model said {entry['original']}, "
            f"coordinator corrected to {entry['corrected']}, reason: '{entry.get('reason') or ''}'"
        )
    for entry in match_buffer:
        lines.append(
            f"- duplicate judgment correction: '{entry['a']}' vs '{entry['b']}', "
            f"reason: '{entry.get('reason') or ''}'"
        )
    return "\n".join(lines)


def format_candidate_line(index: int, candidate: Request, distance_km: float, now) -> str:
    age = now - candidate.submitted_at
    minutes = max(0, int(age.total_seconds() // 60))
    distance_m = distance_km * 1000
    distance_str = f"{distance_m:.0f}m away" if distance_m < 1000 else f"{distance_km:.2f}km away"
    return f'{index}. {candidate.id} ({distance_str}, {minutes} min ago): "{candidate.need_description}"'


def urgency_and_match_prompt(
    request: Request,
    candidates: list[Request],
    distances: dict[str, float],
    urgency_buffer: list[dict] | None = None,
    match_buffer: list[dict] | None = None,
    now=None,
) -> str:
    """FR-204/FR-301: single combined prompt. `distances` maps candidate.id
    -> haversine_km (FR-204: explicit, human-readable distance, never raw
    lat/lng as the only spatial signal)."""
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    parts = [system_prompt()]
    cal = calibration_block(urgency_buffer or [], match_buffer or [])
    if cal:
        parts.append(cal)
    parts.append(f'New request: "{request.need_description}"')
    if candidates:
        parts.append("Candidates (with precomputed distance, FR-204):")
        for i, c in enumerate(candidates, start=1):
            parts.append(format_candidate_line(i, c, distances[c.id], now))
    else:
        parts.append("Candidates: none in range.")
    parts.append(
        'Return JSON matching {"urgency_score": int, "urgency_reasoning": str, '
        '"matches": [{"candidate_id": str, "is_match": bool, "reason": str}]}.'
    )
    return "\n\n".join(parts)
