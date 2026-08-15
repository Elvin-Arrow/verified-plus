A triage & trust tool for humanitarian aid coordinators

## The problem

Aid orgs receive requests for help (supplies, medical aid, evacuation) with no good way to tell a genuine urgent request from a duplicate or a fraudulent one. Coordinators manually sift through claims, and fraud/duplication quietly drains limited resources meant for real people.

Existing logistics software (HELM, LINK, Platforma) tracks _inventory and shipping_ well but doesn't touch the _incoming request_ itself — nobody verifies the ask before it enters the system. That's the gap. We do not attempt to replace those tools: once a request is verified and ranked, it hands off (conceptually, via API) to systems like HELM for the actual supply routing.

**Themes:** Humanitarian logistics + Trusted information (problems 4 & 5 from "The Six")

## What it does

1. **Intake** — anyone submits a request: need, location (map pin / geolocation — a real lat/lng, not just typed free text, since duplicate/cluster detection depends on real coordinates), optional photo, free-text description (any language/phrasing).
2. **Verification** — new requests are geofenced and semantically checked against existing nearby ones (see "Semantic duplicate detection" below).
3. **Dual-signal scoring** — two separate signals, not one blended "trust score":
   - **Event confidence** (drives queue priority, cold-start-safe): when a coordinator verifies a real emergency in an area, similar incoming requests from that same location/event get a confidence boost. This rewards corroboration of the *event*, not the *requester's history* — so a first-time victim in a real disaster is never penalized for having no track record.
   - **Device flag** (drives scrutiny, never priority): a lightweight anonymous fingerprint (persistent local-storage token + IP/UA hash, since intake has no verified accounts) is attached to each submission. A fingerprint with a history of *confirmed* fraudulent/rejected claims gets flagged for mandatory extra scrutiny on future submissions. Clean/new devices get standard treatment — a new device is never treated as suspicious by default. Known limitation: a bad actor can reset this by clearing storage or switching devices; this is a deterrent/scrutiny signal, not proof of identity.
4. **Smart queue** — coordinators see a ranked list, ranked strictly by (urgency × event confidence) and filtered/gated by device flag — not a flat unsorted pile. ("Proximity to supply" was deliberately dropped from ranking — see Judging criteria fit below.)
5. **Urgency** is not self-reported (a "how urgent is this?" dropdown is trivially gameable — everyone picks "critical"). It's LLM-derived: the same LLM call that evaluates duplicate/cluster matches also outputs a rubric-based `urgency_score` (1–5, standard triage rubric — e.g. 5 = immediate threat to life/medical, 2 = general supply request) from the free-text description, as part of one structured JSON response (urgency + duplicate match + human-readable reasoning).

## What makes it smart

|#|Feature|Why it matters|
|---|---|---|
|1|**Semantic duplicate detection**|Two-stage: (a) a fast, cheap embedding model converts each request to a vector; a **geofence pre-filter** (bounding box, ~1km / 48h) narrows the candidate pool to physically nearby recent requests first — text embeddings alone have no concept of geography, so "collapsed roof, need water" in Sector A would otherwise match the same phrase from Sector Z ten miles away. (b) in-memory cosine similarity over that nearby subset finds the top ~5 candidates, and only those are passed to the LLM for final match evaluation — no external vector DB needed at demo scale (hundreds–low thousands of records), no dumping the whole request history into one LLM call.|
|2|**Geofenced retrieval**|Prevents cross-region false merges and keeps the pipeline fast: bounding-box filter runs before semantic comparison, not after, so the LLM only ever evaluates candidates that are actually near each other in space and time.|
|3|**Explainable flagging**|Flags come with a human-readable reason ("closely matches request #114, submitted 20 min ago, same neighborhood") instead of a bare score — makes the human-escalation screen actually usable.|
|4|**Event-confidence clustering**|Groups semantically- and geographically-matched requests into a single "High-Confidence Crisis Event" — not a fraud signal. A real disaster naturally produces many similar, tightly-timed reports from the same area; treating that as fraud would penalize the most acute emergencies. Clustering here *boosts* urgency/confidence instead of flagging it down.|
|5|**Device-fingerprint fraud flag**|A separate, narrower mechanism from clustering: flags a specific anonymous device/session that has a *confirmed* history of fraudulent or rejected claims. This is what actually catches "one person pretending to be many," as distinct from "many real people reporting the same event."|
|6|**Feedback loop**|When a coordinator overrides a decision (approves a flagged request, rejects a clean one), it feeds back into event confidence and device flags — the system visibly gets smarter with use.|

_(Dropped: photo-claim consistency checking via vision models — too flaky/unpredictable to trust live in a demo.)_

## Judging criteria fit

- **Usefulness (40%)** — solves a real, specific, named gap in aid logistics (verification of the request itself, not just tracking supply). Ranking is deliberately scoped to (urgency × event confidence) only — "proximity to supply" was cut from the formula because it would require building/mocking a parallel inventory & depot system, which is exactly the "tracking" problem this tool explicitly stays out of (see "The problem"). Fulfillment/routing is handed off to existing tools.
- **Execution (40%)** — genuinely demoable end-to-end pipeline: submit → geofence → embed/match → flag → rank → decide, with a live coordinator dashboard.
- **Innovation (20%)** — explainable escalation + dual-signal (event confidence / device flag) scoring that improves with feedback is a real point of difference from existing enterprise tools, without the ethical/cold-start trap of a single blended "trust score."

## UX note: Incident Cards

Clustered requests (feature #4) must not render as a flat list of individually-approved rows — if the backend knows 50 requests are the same incident, forcing a coordinator to click "Approve" 50 times defeats the point. The dashboard rolls a cluster into one **Incident Card** (e.g. "Critical: Sector 4 Flooding," badge "50 corroborating reports") with a single approve/reject action that cascades to all members. Because the clustering model will sometimes mis-group (e.g. merging "need drinking water" with a nearby-but-distinct "need evacuation boat" report), each child request inside an expanded Incident Card gets a **"✕ Split Out"** action that ejects it into its own separate ticket — the human-in-the-loop override that keeps the feedback loop meaningful instead of all-or-nothing.

## Data strategy

No existing dataset has individual aid-request records labeled for duplication/fraud — that specific angle doesn't exist publicly (makes sense, it'd be sensitive data even if it did). Plan, as one pipeline:

1. **Text realism base**: pull real disaster-related text from **HumAID** / **CrisisNLP** (labeled tweets from real disasters, 2016–2019).
2. **Schema rewrite**: raw tweets are broadcast-style ("Huge flooding on 5th street, power out!"), not first-person triage asks — using them directly would make the demo look like a sentiment tracker, not a triage tool. Pass each tweet through a fast LLM pre-hackathon with a prompt like *"rewrite this as a first-person emergency intake submission directed at an NGO, adding a specific requested supply or intervention,"* to get requests in the actual intake schema (need, location, description).
3. **Structured ground truth**: reuse the same rewrite pass to generate reworded duplicate variants (same event, different phrasing — the actual semantic-match test set) and a few deliberately seeded fraud clusters (same device/session pattern, coordinated timing, confirmed-fraud history) so detection has known answers to test against.
4. **Images**: 🚩 **FLAGGED — need to build a synthetic image set.** No existing dataset labels reused/duplicate images tied to fraudulent aid claims. CrisisMMD has real disaster images but no duplicate/fraud labeling. Will need to generate or assemble our own set (e.g. real disaster photos reused across multiple synthetic "requests" as the duplicate-fraud ground truth) before building or testing any image-based duplicate check.

## Build roadmap

1. Core request pipeline (form + map pin for real lat/lng + device fingerprint on intake)
2. Geofence pre-filter + embedding/cosine duplicate & plausibility check (semantic matching)
3. Dual-signal scoring (event confidence + device flag) and LLM urgency rubric, via one structured LLM call
4. Ranked dispatch queue (urgency × event confidence) with Incident Card rollup + Split Out override
5. Human escalation view (explainable flags)
6. **Seed/replay script**: bulk-inject ~50 synthetic requests (incl. seeded duplicates + a fraud cluster) into the live intake API on demand — the mechanism that actually drives the live demo, since the core value props (clustering, ranking, flagging) are only visible under volume that can't be typed in by hand during a pitch
7. Polish & demo narrative
