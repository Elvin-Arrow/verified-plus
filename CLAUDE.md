# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repository is currently **spec-only** — no source code, build system, or tests exist yet. Everything is in `docs/`. `docs/development-plan.md` is the implementation roadmap (work breakdown structure, dependency graph, phased plan) for when coding actually starts; until then, there are no build/lint/test commands to run because there is nothing to build, lint, or test. Don't invent any.

## Document cascade

The docs form a dependency chain — each one implements the one(s) before it, and cites requirement IDs (`FR-xxx`, `NFR-xxx`) defined in `spec.md` throughout. Read in this order to get oriented:

1. `docs/idea.md` — pitch-level project description. Explicitly *not* authoritative for implementation details ("for anything load-bearing... the spec and design docs are authoritative").
2. `docs/spec.md` — the formal requirement spec (SRS-style, numbered `FR-`/`NFR-` requirements). This is where the requirement ID namespace is defined; every other doc references IDs from here.
3. `docs/design.md` — software design: module layout, core dataclasses, and pseudocode for every algorithm (cluster assignment, dissolution, device-flag/quarantine handling, feedback calibration, seed/replay).
4. `docs/api-spec.md`, `docs/data-model.md`, `docs/architecture.md` — three documents that elaborate on `design.md` in parallel: the full HTTP contract, the field-by-field entity schema and state machines, and the system-level (process topology, deployment, integration) view respectively.
5. `docs/testing-spec.md` — the TDD contract: test levels, mutation-testing scope/threshold, state-machine test tables, acceptance scenarios, FR/NFR traceability.
6. `docs/ui-spec.md` — screen-by-screen UI contract (both the public intake form and the coordinator dashboard), consuming `api-spec.md` end-to-end.
7. `docs/development-plan.md` — work breakdown structure, dependency graph, and phased roadmap sequencing implementation of everything above.

Each doc's header states a version number and which version of its upstream docs it implements (e.g. "Implements `docs/spec.md` v0.3 §7"). When editing a doc in a way that changes its contract (a field, an endpoint, a state transition), **check every doc downstream of it in the cascade** for now-stale references, not just the one you're editing.

## Working conventions specific to this repo

- **Requirement IDs are the cross-document vocabulary.** Before changing behavior described by `FR-205` (or any other ID), `grep -rn "FR-205" docs/` to find every place it's cited — the same requirement is typically referenced from `design.md`'s pseudocode, `api-spec.md`'s endpoint table, `data-model.md`'s field notes, `testing-spec.md`'s traceability matrix, and often `ui-spec.md`/`development-plan.md` too.
- **Every doc carries its own "Change log" section** (numbered, e.g. `spec.md` §10/§11, `data-model.md` §7, `ui-spec.md` §15, `development-plan.md` §8) recording what an alignment pass found and fixed, with a rationale — not just "updated X." Continue this pattern rather than silently editing past history; it's how contradictions get caught before they compound.
- **Substantial edits get cross-checked against the full document set, not just the doc being changed.** The established process in this repo's history: after drafting or materially changing a doc, review it both internally and against every other doc in `docs/` for contradictions, missing coverage, and stale cross-references, then fix real findings (not manufactured ones) and log them. Several of the most serious bugs caught this way were in `design.md`'s state-machine pseudocode (e.g. a rejected Event member never being removed from `member_request_ids`, so dissolution could never trigger) — this class of bug is the reason the cross-check step matters more than it might look like for "just documentation."
- **Bash commit messages**: avoid raw apostrophes/backticks inside single-quoted shell strings (`'...don't...'`, `` `code` `` ) — both have broken commits in this repo's history. Write the message to a scratch file and use `git commit -F <file>` for anything non-trivial.
