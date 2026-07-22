# CLAUDE.md — jh-clio-lib

## Required reading (session start)

Before doing any work in this repo, read:
- `~/jh-knowledge/PLATFORM_OVERVIEW.md` — infra/environment state (what's deployed, credential models)
- `~/jh-knowledge/PROJECT_TRACKER.md` — active worklist, status, next action, blockers across all projects
- `~/jh-knowledge/ClioLearningLog.md` — durable Clio/Microsoft Graph/Lawmatics API knowledge (payload shapes, auth quirks, gotchas)
- `~/jh-knowledge/MatterKey.md` — the canonical Clio↔Lawmatics cross-system join key; **read this before writing any code that correlates a Clio record with a Lawmatics record**

If `~/jh-knowledge` doesn't resolve on this machine, run `setup_jh_knowledge_symlink.sh` before continuing — don't fall back to guessing a raw OneDrive path.

If you discover something during this session that belongs in one of the four files above (a new API gotcha, an infra change, a MatterKey edge case), add it there directly — don't just note it in this file, or the next project won't see it.

---

## What this project is

A minimal, shared Python module wrapping Clio and Lawmatics API access — token
retrieval, request/retry handling, and the write-format rules already learned the
hard way — so every new local project stops re-deriving or re-breaking the same
knowledge. Not a general SDK; scoped to exactly what the firm's tools actually need.
First consumers: ClioMCP (firm-data MCP server) and clio-hotstrings. See
`jh-clio-lib-brief.md` for the full design brief.

## Where things live

| What | Where |
|---|---|
| Repo | `~/my-automations/jh-clio-lib` |
| Remote | `https://github.com/RobertWJewett/jh-clio-lib` (private) |
| Deployed service (if any) | None — local editable install only (`pip install -e`), per brief §2 |
| Project-specific design doc (if any) | `jh-clio-lib-brief.md` (this repo) |

## Project-specific conventions

- Package name is `jh_clio_lib` (underscored) even though the repo/PyPI-style name is
  `jh-clio-lib` (hyphenated) — standard Python packaging convention.
- Clio custom-field name→id cache lives in Firestore
  (`clio_manage_state/custom_field_definitions`), not a local file — must stay
  consistent across machines and consumers (brief §3). This supersedes
  ClioMCP's original `firm_data/field_map.py`, which cached to a local gitignored
  JSON file; ClioMCP has not yet been migrated to consume this library (deferred to a
  separate session).
- Tests mock all Firestore/HTTP access (see `tests/conftest.py`'s `fake_firestore`
  fixture + `responses`) — no test should require live credentials. Live behavior is
  verified manually via `python -c "..."` snippets against real infra when scaffolding
  changes, not via the automated suite.

## Current status

See this project's row in `~/jh-knowledge/PROJECT_TRACKER.md` for the
authoritative current status — don't let this section drift out of sync with
it. If you update status here, update the tracker too, same session.

As of 2026-07-20: v1 scaffolded and live-smoke-tested (Clio auth, Clio custom-field
read/write, Lawmatics auth, Lawmatics custom-field write w/ GET-verify) — 22/22 mocked
tests passing. Added `clio_matters.clio_list_matters()` (bulk paginated matter
listing with braces field-selection) and promoted `clio_braces_get` to public on
`clio_client` when `clio-hotstrings` needed them — the "second consumer" the design
brief anticipated. `clio-hotstrings` now consumes this library (editable install);
ClioMCP has not yet migrated.

**Update 2026-07-21:** `clio_braces_get` got two resilience fixes, both surfaced by
clio-hotstrings bulk-fetching ~1,550 Contact records for the first time (previously
every consumer only ever called it once per matter, occasionally) — it now retries
429/502/503/504 with backoff (honoring `Retry-After`) and retries connection-level
failures (timeouts etc.), matching what `clio_request` already did. See
`ClioLearningLog.md` §5 for the full incident/fix writeup.

**Update 2026-07-22:** added `clio_list_contacts()`, mirroring `clio_list_matters()`
(shared pagination loop extracted into `_paginate_braces()`) — a **third** consumer,
outside the original ClioMCP/clio-hotstrings pair: a one-time Clio contact
phone-number-format backfill script in `jh-law-scripts/clio/clio_phone_backfill.py`,
which needed to scan every Clio contact headlessly (that repo's own Clio config
module always pops a blocking Tkinter dialog on startup, incompatible with a
one-off script run from Claude Code). 28/28 mocked tests passing.

## Open items specific to this project

- ClioMCP migration: point ClioMCP's `firm_data/` module at this library instead of
  its own duplicated `clio_auth.py`/`clio_client.py`/`field_map.py` — deliberately
  deferred to a separate session (see PROJECT_TRACKER.md).
- Lawmatics list/picklist-type custom fields: `lawmatics_update_custom_field`'s
  GET-verify doesn't yet resolve internal option ids back to labels (see the docstring
  in `lawmatics_client.py`) — no current consumer writes a list field, so this is
  deferred until one does.
