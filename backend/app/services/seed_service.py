"""BE-19: FR-701-702: seed/replay incl. full cascading wipe. docs/design.md §4.8.

SEED_BATCH (~50 synthetic requests, FR-701) includes:
  - several genuine multi-device event clusters (dev_cluster_<n>_<i>,
    tight lat/lng groupings a real embedding+geofence pass would corroborate)
  - a single-device fraud cluster (dev_fraud_1, several near-identical
    rapid submissions from one device -- FR-701's "at least one seeded
    single-device fraud cluster")
  - several standalone unrelated requests (dev_standalone_<n>, scattered
    coordinates, distinct needs)

All submitted through intake_service.submit() (the same live path a real
browser submission uses), never a direct store write, per FR-701.
"""
from __future__ import annotations

from typing import Literal, NamedTuple

from app.models.domain import Location
from app.services import intake_service
from app.store.memory_store import InMemoryStore


class SeedRequest(NamedTuple):
    need_description: str
    lat: float
    lng: float
    device_fingerprint_id: str


def _cluster(n: int, base_lat: float, base_lng: float, texts: list[str]) -> list[SeedRequest]:
    """A genuine multi-device event cluster: distinct devices, tightly
    grouped coordinates (within a few hundred meters), corroborating text."""
    out = []
    for i, text in enumerate(texts):
        jitter = i * 0.0003  # ~30m steps -- well within the default 1km geofence
        out.append(SeedRequest(text, base_lat + jitter, base_lng + jitter, f"dev_cluster_{n}_{i}"))
    return out


def _fraud_cluster() -> list[SeedRequest]:
    """A single-device fraud cluster: one device, several near-identical
    rapid-fire submissions from the same spot."""
    base_lat, base_lng = 20.0000, 30.0000
    texts = [
        "need urgent food and water immediately please help",
        "need urgent food and water immediately please help now",
        "urgent need food water immediately help please",
        "please help urgent food water needed now immediately",
    ]
    return [SeedRequest(t, base_lat, base_lng, "dev_fraud_1") for t in texts]


def _standalones() -> list[SeedRequest]:
    texts_and_locations = [
        ("When will the aid center reopen?", 5.0, 5.0),
        ("Would like extra blankets if available", 5.5, 5.6),
        ("Roof damaged, we're fine, need a tarp eventually", 6.0, 6.1),
        ("No clean water for 2 days, household of 4", 7.0, 7.2),
        ("Broken arm, in pain, no transport to a clinic", 8.0, 8.3),
        ("Insulin runs out tonight, need resupply", 9.0, 9.4),
        ("3 kids alone since yesterday, no adult present", 10.0, 10.5),
    ]
    return [
        SeedRequest(text, lat, lng, f"dev_standalone_{i}")
        for i, (text, lat, lng) in enumerate(texts_and_locations)
    ]


SEED_BATCH: list[SeedRequest] = [
    *_cluster(1, 12.3400, 56.7800, [
        "Trapped under rubble, can't move my leg",
        "Building collapsed near us, people trapped inside",
        "Heard screaming from the collapsed building next door",
    ]),
    *_cluster(2, 13.1000, 40.2000, [
        "House flooded, we're staying with neighbors but need somewhere",
        "Water rising fast on our street, need help",
        "Flooding here too, same street, no way out by car",
        "Neighbors say the whole block is flooded, we're stuck",
    ]),
    *_cluster(3, 30.5000, -10.2000, [
        "Fire spreading fast near the market, people evacuating",
        "Smoke everywhere near the market, can't breathe",
    ]),
    *_cluster(4, -5.0000, 100.0000, [
        "Elderly couple next door needs help, can't walk far",
        "Elderly neighbors stuck upstairs, need assistance getting out",
        "Same building, elderly residents on 3rd floor need help",
    ]),
    *_fraud_cluster(),
    *_standalones(),
    # a few more standalone-shaped entries to comfortably clear the ~50 target
    SeedRequest("Need hygiene kits for a household of 6", 15.0, 15.5, "dev_standalone_7"),
    SeedRequest("Wound needs cleaning, not bleeding badly", 16.0, 16.6, "dev_standalone_8"),
    SeedRequest("Displaced with no shelter but not in immediate danger", 17.0, 17.7, "dev_standalone_9"),
    SeedRequest("General food resupply request for the week", 18.0, 18.8, "dev_standalone_10"),
    SeedRequest("Cardiac symptoms, chest pain, need urgent help", 19.0, 19.9, "dev_standalone_11"),
    SeedRequest("In labor, need transport to a clinic now", 21.0, 21.1, "dev_standalone_12"),
    SeedRequest("Rising floodwater with people inside the house", 22.0, 22.2, "dev_standalone_13"),
    SeedRequest("Roof collapsed partially, no one hurt, need a tarp", 23.0, 23.3, "dev_standalone_14"),
    SeedRequest("Low priority: extra supplies if available please", 24.0, 24.4, "dev_standalone_15"),
    SeedRequest("Need information about the next distribution date", 25.0, 25.5, "dev_standalone_16"),
    SeedRequest("Severe bleeding after an accident, need help fast", 26.0, 26.6, "dev_standalone_17"),
    SeedRequest("Stroke symptoms, one side weak, need urgent help", 27.0, 27.7, "dev_standalone_18"),
    SeedRequest("Dialysis supply running out within hours", 28.0, 28.8, "dev_standalone_19"),
    SeedRequest("Unaccompanied elderly person, unsafe situation", 29.0, 29.9, "dev_standalone_20"),
    SeedRequest("Property damage only, no one at risk here", 31.0, 31.1, "dev_standalone_21"),
    SeedRequest("Would like general information about aid centers", 32.0, 32.2, "dev_standalone_22"),
    SeedRequest("No food or water access for household of 3", 33.0, 33.3, "dev_standalone_23"),
    SeedRequest("Need a tarp and blankets, otherwise safe", 34.0, 34.4, "dev_standalone_24"),
    SeedRequest("Not breathing, need emergency medical help now", 35.0, 35.5, "dev_standalone_25"),
    SeedRequest("Unconscious, need urgent medical attention", 36.0, 36.6, "dev_standalone_26"),
    SeedRequest("Disabled resident stuck, unsafe but stable situation", 37.0, 37.7, "dev_standalone_27"),
    SeedRequest("General inquiry about registering for aid", 38.0, 38.8, "dev_standalone_28"),
    SeedRequest("Exposed to severe cold, no shelter tonight", 39.0, 39.9, "dev_standalone_29"),
    SeedRequest("Oxygen supply running low within hours", 41.0, 41.1, "dev_standalone_30"),
    SeedRequest("Minor property damage, everyone accounted for", 42.0, 42.2, "dev_standalone_31"),
    SeedRequest("Would like extra hygiene kits when convenient", 43.0, 43.3, "dev_standalone_32"),
    SeedRequest("Displaced family of 5, no immediate danger", 44.0, 44.4, "dev_standalone_33"),
    SeedRequest("Need clean water, none available for 3 days", 45.0, 45.5, "dev_standalone_34"),
]


def replay(store: InMemoryStore, llm_client, mode: Literal["reset", "append"],
           geofence_radius_km: float | None = None, max_cluster_span_km: float | None = None) -> dict:
    wiped = False
    if mode == "reset":
        store.reset()  # FR-702: full cascading wipe
        if geofence_radius_km is not None:
            store.config.geofence_radius_km = geofence_radius_km
        if max_cluster_span_km is not None:
            store.config.max_cluster_span_km = max_cluster_span_km
        wiped = True

    submitted = 0
    for seed in SEED_BATCH:
        intake_service.submit(
            store, llm_client,
            need_description=seed.need_description,
            location=Location(lat=seed.lat, lng=seed.lng),
            device_fingerprint_id=seed.device_fingerprint_id,
        )
        submitted += 1

    return {"mode": mode, "requests_submitted": submitted, "wiped": wiped}
