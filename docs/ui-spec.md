# UI Specification — Aid Request Triage & Trust Tool

Version 0.1 · Implements `docs/design.md` v0.3 §6 (frontend design) and consumes `docs/api-spec.md` v0.1 end-to-end. This document is the authoritative screen-by-screen, component-by-component UI contract — layout, states, visual encoding, and exactly which API call each interaction fires — that `docs/design.md`'s frontend component tree sketch and `docs/testing-spec.md`'s acceptance scenarios both point back to.

## 1. Design principles

Four principles, each traceable to a specific requirement rather than generic taste:

1. **Never force per-item review of what's already understood.** Incident Cards, device-grouped bulk actions, and single-click inline standalone actions all exist because NFR-401 requires a coordinator to process a ~50-request seeded batch in minutes, not hours. Any new UI element added later should be checked against this principle before it's checked against anything else.
2. **No judgment without its reason, ever.** NFR-301: a duplicate match, an urgency score, a device flag — none of them render as a bare value anywhere in this UI. Every severity badge, every flag icon, every "N corroborating reports" count has its reasoning one click away (the detail view, §5), never zero clicks away by default (that would clutter the list views this system depends on staying scannable).
3. **Destructive actions require intent proportional to their blast radius.** FR-503's per-device grouping, FR-507's fraud-free Dismiss Cluster, and the asymmetric approve/reject split (`docs/spec.md` §10 finding — bulk-approve is one click, bulk-destroy is scoped to a device group, never a whole card) all trade off the same way: batch the safe direction, never the unsafe one.
4. **A coordinator should never see a dead end.** Every state a request/Event can be in (per `docs/data-model.md` §3) has a corresponding visible action in this document — if a screen ever shows an item with nothing a coordinator can do to it, that's a UI bug, not an acceptable resting state (this is the literal lesson of the Suggested-Merge-with-no-merge-button and stuck-standalone-request bugs `docs/spec.md` §11 fixed at the requirements level).

## 2. Screens

Two entry points, per `docs/design.md` §6.1:

| Route | Audience | Auth | Device target |
|---|---|---|---|
| `/intake` | Anyone submitting a request (FR-104: no login) | None | **Mobile-first.** The realistic intake channel is a phone in the field (`docs/idea.md` §Scope: GPS-native channels), not a desk. |
| `/dashboard/*` | Coordinator | None in this version (`docs/architecture.md` §7.3) | **Desktop-first.** Incident Cards, device-grouping, and side-by-side queue comparison need width; this is a person at a workstation, not a phone. |

## 3. `/intake` — public request form

```
┌─────────────────────────────────────┐
│  [Map / "Use my location" button]     │  ← FR-101: map pin or navigator.geolocation.
│  (tap-to-place pin if GPS denied)     │     A denied/unavailable geolocation permission
│                                        │     does NOT silently fall back to a text field
│  What do you need?                    │     (FR-101 forbids free-text-only location) — it
│  [___________________________]        │     falls back to the tap-to-place map, always.
│  (free text, any language)            │
│                                        │
│  Photo (optional)                     │  ← FR-103. Passive only — no upload progress
│  [+ Add photo]                        │     tied to any analysis step, since none runs.
│                                        │
│  [ Submit ]                           │  ← POST /api/requests
└─────────────────────────────────────┘
```

### 3.1 States

- **Idle**: as above. Submit disabled until both location and a non-empty description are present (client-side mirror of FR-101/102's server validation — the client check is a UX nicety, not a substitute for the server's `400 VALIDATION_ERROR`, which the form must still handle if the client check is somehow bypassed).
- **Submitting**: Submit button disabled + spinner, per `docs/design.md` §6.2's optimistic-disable pattern — this form is the one place in the system where "optimistic" still means "wait for the real response" rather than "assume success," because a submitter needs to know their request actually landed.
- **Success**: replace the form with a plain confirmation — "Your request has been received." **No status detail, no urgency score, no match information is ever shown to the submitter.** This is a deliberate omission: NFR-301's explainability requirement is scoped to the coordinator-facing side; showing a requester their own urgency score or "3 similar requests found nearby" would either cause alarm (a low score) or invite gaming (learning what triggers a high one) with no coordinator in the loop yet to contextualize it.
- **Error** (`400 VALIDATION_ERROR`): inline message under the specific invalid field (`error.details.field` from `docs/api-spec.md` §1.1), form remains filled in — never clear the submitter's typed description on an error.
- **Quarantined outcome** (device flagged, `docs/api-spec.md` §2): still renders the same plain **Success** confirmation as any other submission. A flagged device must never be told it's flagged — that would defeat the quarantine mechanism's entire premise (`docs/spec.md` FR-308's "accepted but withheld," not "rejected").

## 4. `/dashboard` — shared chrome

```
┌──────────────────────────────────────────────────────────────┐
│  [Intake & Verification]  [Dispatch Queue]  [Quarantine]  [Archive]  │  ← tab bar
│  ───────────────────────                                             │
│                                                    [Seed/Replay ▾]     │  ← §8, demo-only control
├──────────────────────────────────────────────────────────────┤
│  (active tab's content — §5–7 below)                                 │
└──────────────────────────────────────────────────────────────┘
```

Tab labels never show a raw item count badge for the two "live" tabs (Intake, Dispatch) — a bouncing number next to a tab is exactly the kind of undifferentiated-urgency signal principle 2 argues against; the *content* of the sorted list itself is where urgency lives, not a tab badge that can't distinguish "50 low-priority items" from "1 critical one."

## 5. Intake & Verification Inbox (FR-401, FR-402)

Two-section layout, matching `docs/api-spec.md` §3's response shape exactly:

```
┌──────────────────────────────────────────────────────────────┐
│  ⚠ NEEDS MANUAL TRIAGE (2)                                     │  ← unsorted, always first,
│  ┌────────────────────────────────────────────────────────┐   │     visually distinct (amber
│  │ [pending icon] "flooding hit our well..." — urgency:    │   │     background, not just a
│  │  pending/unavailable — device: dev_x1y2                  │   │     label) so it can never be
│  │  [Retry evaluation]  [Override Urgency manually]         │   │     mistaken for "just low
│  └────────────────────────────────────────────────────────┘   │     priority" (NFR-103's point)
│                                                                  │
│  SORTED (urgency, then corroboration)                          │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 🔴 5  Incident Card: "Collapsed building, Sector 4"       │   │  ← §5.1
│  │  3 corroborating reports · 3 devices                      │   │
│  │  [Verify Event & Approve All]  [expand ▾]                 │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ 🟠 4  "insulin runs out tonight" (standalone)              │   │  ← §5.2
│  │  [Verify & Dispatch]  [Reject]  [details]                 │   │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 5.1 Incident Card (candidate)

- Header: severity dot (§9 color table) at the card's `max_urgency_score`, title (first member's location/need summary, not a coordinator-authored label — nothing in the data model provides one), "N corroborating reports · M devices" badge.
- Collapsed by default; **"Verify Event & Approve All"** is available collapsed (principle 1 — the common case never requires expanding).
- **Expanded**: members grouped by device fingerprint (FR-503), each device-group showing its member requests and a **"Reject & Flag Device"** button scoped to that group. A single **"✕ Split Out"** per individual request. A card-level **"Dismiss Cluster"** button, visually separated from the per-device actions (different color/position) so it's never confused with a per-device reject — Dismiss Cluster's whole purpose (FR-507) is "the grouping was wrong, not the people," so it must not sit where a coordinator's eye expects a fraud action.
- If any member has an entry in `suggested_merges` (`docs/api-spec.md` §7), a **"⚠ Possible related event N km away — Merge?"** affordance appears on that member's row inside the expanded view (never on the collapsed card, since it's a per-request signal, not a per-Event one) — clicking it opens a confirmation showing both sides before calling `POST /api/requests/{id}/merge`.

### 5.2 Standalone row

- Severity dot, need text (truncated with a "details" link to §11's detail view), **"Verify & Dispatch"** / **"Reject"** inline (FR-505) — no expand affordance, since there's nothing to expand.
- If a `suggested_merges` entry exists for this request, the same Merge affordance as §5.1 appears inline.

### 5.3 Empty state

"No pending requests." (not "No requests" — the Archive/Quarantine tabs may still hold items; this tab's emptiness is specifically about the active queue, and should read that way rather than implying the system has never seen traffic).

## 6. Dispatch Queue (FR-403)

Same list mechanics as §5's sorted section (no Needs Manual Triage section here — a `null`-urgency item is never verified, so it structurally can't appear), plus two differences:

- Incident Card's primary action is **"Approve"** (dispatch, not verify — it's already verified to be here). If the Event has `pending_members` (FR-304b), a visually distinct **sub-section within the expanded card** — "N pending additions, awaiting review" — device-grouped the same way as §5.1, with its own **"Approve All Pending"** action, kept separate from the main "Approve" button so a coordinator can't accidentally dispatch-and-forget genuinely new corroboration that hasn't been looked at yet.
- A standalone row here (the FR-504b dissolution case only — `verified=true`, not yet `dispatched`) shows a single **"Dispatch"** action (FR-505b), not "Verify & Dispatch" — the label difference matters: this item is already verified, relabeling it "Verify" would misleadingly imply a decision is still pending.

## 7. Quarantine Inbox (FR-407)

Grouped by device, not a flat list — matching `docs/api-spec.md` §3's `groups` response shape:

```
┌──────────────────────────────────────────────────────────────┐
│  dev_x1y2  (flagged)                          [Reject All]     │
│    • "need water" — quarantined 2h ago         [Rescue]        │
│    • "need water urgently" — quarantined 1h ago [Rescue]       │
└──────────────────────────────────────────────────────────────┘
```

Each request within a device group gets its own **"Rescue"** action (individual, since a shared device — the entire reason this tier exists — may hold one legitimate request among several fraudulent ones); **"Reject All"** is device-group-scoped like everywhere else in this UI, never a single blanket action across the whole tab.

## 8. Archive (FR-406)

Read-only. No action buttons anywhere on this screen — that's the point of a terminal state (`docs/data-model.md` §3.1). A flagged device's items carry a static scrutiny badge (FR-309) but it's non-interactive here (§4's Quarantine tab is where a flag is actually acted on).

## 9. Severity color encoding

| `urgency_score` | Color | Never relies on color alone |
|---|---|---|
| 5 | Red | Always paired with the numeral itself (`🔴 5`), not a bare color swatch — colorblind-safe by construction, not by a separate accessibility pass bolted on after. |
| 4 | Orange | " |
| 3 | Yellow | " |
| 2 | Blue | " |
| 1 | Gray | " |
| `null` (pending/unavailable) | Amber, distinct pattern (hatched/striped background, not just a different hue) | Deliberately NOT on the 1–5 red-to-gray scale — a pending score must never be visually confusable with "urgency 2" or any other real score, since it isn't one (`docs/data-model.md` §2.1's distinction). |

Device-flag scrutiny marker (§8, Archive only, per FR-309): a small outlined icon, not a color fill — reserving red/orange for urgency exclusively avoids a flagged-but-low-urgency item looking more alarming at a glance than it is.

## 10. Request detail view (FR-506, FR-602, FR-603)

Opened from any "details"/expand affordance across §5–8. Renders `GET /api/requests/{id}`'s full response:

```
┌──────────────────────────────────────────────────────────────┐
│  "Flooding hit our well, no clean water for 2 days"             │
│  Submitted 2026-08-15 14:03 UTC · dev_x1y2                      │
│                                                                    │
│  Urgency: 🟠 4   "No access to clean water, tier 3 baseline,     │
│                    escalated for duration (2 days)."               │
│  [Override Urgency]                                               │
│                                                                    │
│  Duplicate/match evaluation:                                      │
│    ✓ matches req_990z — "Same flooded street, submitted 40 min    │
│      ago, 90m away."                                              │
│                                                                    │
│  Possible related event 1.9km away — [Merge]                     │  ← if suggested_merges non-empty
│                                                                    │
│  Action history:                                                  │
│    2026-08-15 14:10  coordinator_1  override_urgency               │
│      "Implies trapped, not just discomfort."                       │
└──────────────────────────────────────────────────────────────┘
```

**"Override Urgency"** opens a small inline form: a 1–5 selector (defaulting to the current score, never blank) and an optional reason field, with the reason field's placeholder text making its downstream use explicit — "Why? (helps the system calibrate on similar requests)" — so a coordinator understands FR-604's calibration effect rather than treating it as a discarded audit comment. Submits to `POST /api/requests/{id}/override-urgency`.

`match_reasons` renders every candidate the LLM evaluated, not only the ones judged a match — a `✗` no-match entry with its reason is what makes an incorrect non-match debuggable by a coordinator, not just a correct match.

## 11. Loading and error states (all screens)

- **Loading** (initial fetch or any poll tick, `docs/design.md` §6.2–6.3): existing content stays visible with a subtle in-place indicator, never a full-screen spinner that blanks the queue a coordinator is mid-review of — a poll tick is a background refresh, not a navigation.
- **Action in flight**: the clicked control is disabled (not hidden — hiding it would shift layout under the coordinator's cursor mid-click on an adjacent control).
- **`404 NOT_FOUND`** on an action (target was mutated by a concurrent action — `docs/architecture.md` §7 notes multi-coordinator concurrency isn't a supported scenario, but a stale client view after a poll-interval lag is still possible even for one coordinator across two tabs): toast — "This item has changed — refreshing" — and trigger an immediate re-fetch of the current view, not a raw error dialog.
- **`409 INVALID_STATE_TRANSITION`**: same toast pattern, since it's the same root cause (client's view was stale) as a `404` in practice, even though the API distinguishes them for a good server-side reason (`docs/api-spec.md` §1.1).
- **`500`/network failure**: a persistent (not auto-dismissing) banner — "Something went wrong — retry" — with a manual retry action; never silently swallowed, since this is the one error category `docs/architecture.md` §7.1 explicitly treats as a bug, not a designed-for path, and a coordinator seeing it repeat is exactly the signal that should surface.

## 12. Seed/Replay control (demo support, FR-701–702)

A dashboard-chrome dropdown (§4), not a prominent primary button — this is a presenter tool, not a coordinator workflow feature, and should read that way in the UI hierarchy:

```
[Seed/Replay ▾]
  Mode:  ( ) Reset   ( ) Append
  Geofence radius (km):     [1.0]   (reset mode only)
  Max cluster span (km):    [1.5]   (reset mode only)
  [ Run ]
```

No default pre-selected for Mode (`docs/spec.md` FR-702: "an explicit, documented choice... not an implicit default") — **Run stays disabled until a mode is explicitly chosen**, mirroring the API's refusal to accept an omitted `mode` as `400 VALIDATION_ERROR`.

## 13. Accessibility

- Every icon-only affordance (Split Out's ✕, the pending-triage ⚠) has a text label available via `aria-label` / visible on hover — never icon-only with no text equivalent anywhere in the DOM.
- All interactive elements in §5–8's list views are reachable and operable via keyboard alone (tab order following visual/severity order, Enter/Space activating the focused action) — a direct requirement of NFR-401's "process a batch in minutes" claim holding up for a coordinator who isn't exclusively mouse-driven.
- Color is never the sole signal (§9) — severity, pending state, and flags all pair a color with a numeral, icon shape, or text label.

## 14. Cross-references

| This document | Corresponds to |
|---|---|
| §3 Intake form | `docs/spec.md` FR-101–107; `docs/design.md` §6.1 |
| §5–8 Dashboard screens | `docs/spec.md` FR-401–407, FR-501–507; `docs/api-spec.md` §3–6 |
| §9 Severity encoding | `docs/spec.md` FR-301 rubric; `docs/data-model.md` §2.1 |
| §10 Detail view | `docs/spec.md` FR-506, FR-602, FR-603; `docs/api-spec.md` §7 |
| §11 Loading/error states | `docs/api-spec.md` §1.1–1.2; `docs/architecture.md` §7.1 |
| §12 Seed/Replay | `docs/spec.md` FR-701–702, FR-208; `docs/api-spec.md` §6 |
| §13 Accessibility | NFR-401 |
