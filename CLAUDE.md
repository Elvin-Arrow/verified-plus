# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

"Aid Request Triage & Trust Tool" — a triage/dedup/fraud-scrutiny system for humanitarian aid coordinators. Full stack now implemented per the spec cascade in `docs/`: `backend/` (Python/FastAPI) and `frontend/` (React/Vite). `docs/development-plan.md` is the work breakdown structure this was built against — every module/component traces back to a chunk ID (`BE-xx`/`FE-xx`/`TI-xx`/`DA-xx`) and a GitHub issue.

## Document cascade

`docs/` holds the spec chain everything is built against, each doc citing requirement IDs (`FR-xxx`/`NFR-xxx`) from `spec.md` and versioned against what it implements: `idea.md` (pitch, not authoritative for details) → `spec.md` (numbered requirements — the ID namespace) → `design.md` (module layout + algorithm pseudocode) → `api-spec.md`/`data-model.md`/`architecture.md` (HTTP contract, entity schema/state machines, system topology — elaborate on `design.md` in parallel) → `testing-spec.md` (TDD contract, test levels, mutation-testing scope) → `ui-spec.md` (screen/component contract) → `development-plan.md` (WBS, dependency graph, phased roadmap — what actually got built, in what order). When changing behavior a doc describes, check every doc downstream of it in this chain for now-stale references.

## Commands

### Backend (`backend/`)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # first time only
pip install -r requirements.txt

pytest -q                                # full suite
pytest tests/test_clustering_assign.py -q             # one file
pytest tests/test_clustering_assign.py::test_name -q  # one test

mutmut run                               # mutation testing — scope is set in pyproject.toml
                                          # [tool.mutmut] to the priority modules only
                                          # (clustering_service, device_service, queue_service,
                                          # feedback_service, action_service, geo, sort — the
                                          # modules docs/testing-spec.md §5 flags as highest-risk)

uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000   # run the API
```

No `LLM_API_KEY` env var is available in most dev/agent environments — this is expected. The intake pipeline degrades gracefully without one (submissions land in Needs Manual Triage per NFR-103), and the entire test suite runs against `tests/fixtures/llm_double.py`, a fixture-keyed fake, never a live call. Don't treat a missing key as a blocker.

CI (`.github/workflows/backend-ci.yml`) runs `pytest -q` on every push/PR touching `backend/**`.

### Frontend (`frontend/`)

```bash
cd frontend
npm install                              # first time only

npm test                                 # vitest run — full suite
npx vitest run src/api/useMergeFlow.test.js           # one file
npx vitest run -t "test name"                          # by test name
npm run test:watch                       # watch mode

npm run lint                             # oxlint
npm run dev -- --port 5173               # dev server
```

Component tests always run against the MSW-mocked API (`src/mocks/handlers.js`), never a live backend. To point the dev server at a real running backend instead of the relative `/api` path, copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` (see that file's comment for the exact uvicorn invocation).

**Known pre-existing failure**: `src/api/client.test.js` (26 tests) fails on a network/MSW mocking issue unrelated to any recent change — confirmed to reproduce identically on a clean checkout. Don't assume you broke it; don't spend time "fixing" it as a side effect of an unrelated task without flagging it explicitly.

## Working conventions specific to this repo

- **This project is built strictly test-first (TDD)** per `docs/testing-spec.md` §1: the test is written and observed failing before any implementation exists — never together, never reversed. Continue this discipline for any new work.
- **Requirement IDs are the cross-document vocabulary.** Before changing behavior described by `FR-205` (or any other ID), `grep -rn "FR-205" docs/ backend/ frontend/` to find every place it's cited — spec.md, design.md's pseudocode, api-spec.md's endpoint table, data-model.md's field notes, testing-spec.md's traceability matrix, ui-spec.md, and now the actual implementing code/tests.
- **Every doc carries its own "Change log" section** (numbered, e.g. `spec.md` §10/§11, `data-model.md` §7, `ui-spec.md` §15). Continue this pattern for doc-level fixes rather than silently editing past history.
- **A gap or bug found during implementation gets fixed at the doc level too, not just patched in code.** Several real defects (a missing state transition, an unwired UI affordance, a field a list endpoint needed but didn't have) were caught this way — the fix always updated the relevant spec doc(s) alongside the code, in the same pass, with a rationale.
- **Substantial doc edits get cross-checked against the full document set** before/after changing them — not just the doc being edited. This has repeatedly caught real bugs (a rejected Event member never removed from `member_request_ids` so dissolution could never trigger; a factually backwards test assertion that would have enforced the exact bug it claimed to prevent) that a narrower review would have missed.
- **GitHub issues track the WBS**: every chunk in `docs/development-plan.md` §2 has a corresponding issue (`gh issue list`), assigned by track (backend vs. frontend) and milestone (by phase), labeled `backend`/`frontend`/`test-infra`/`data` plus `critical-path`/`high-risk` where applicable. Closing convention: commit message ends with `Closes #N`, pushed to `main` (this repo has no PR workflow — direct-to-`main` is the norm). A short dev-log comment (what was built, what broke and how it got fixed, or "went clean") goes on the issue before/alongside the closing push.
- **Bash commit messages**: avoid raw apostrophes/backticks inside single-quoted shell strings — both have broken commits in this repo's history. Write the message to a scratch file and use `git commit -F <file>` for anything non-trivial.
