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

**Update 2026-08-12:** added `lawmatics_collections.py` — read access to
Lawmatics' new Collections API (v1.22.0+), a firm-defined repeatable-data
object distinct from Custom Fields, first touched anywhere in this platform.
`lawmatics_list_collections`/`lawmatics_get_collection`/
`lawmatics_list_collection_items`/`lawmatics_get_collection_item`, plus
`resolve_collection_item_values()` which flattens an item's own inline
`name`/`formatted_value` into a plain dict (confirmed live that no separate
schema join is actually needed for the common case — see
`ClioLearningLog.md` §7). Built on the existing `lawmatics_request()`
auth/retry primitive, no new HTTP code. Live-verified against real data on
Lawmatics Prospect `18634852` (a "Real Property" + two "Financial Accounts"
collection items) — scoped from `clio-lm-xfer`, with an eye toward eventually
feeding ClioMCP's estate-inventory recipe. Read-only so far — write methods
(create/update/delete_collection_item) deliberately deferred. 36/36 mocked
tests passing.

**Same day, follow-up:** added `matterkey_index.py` — reads the shared
`clio_matterkey_index` Firestore collection (built nightly by
`email-processor/deploy_matterkey_index/build_matterkey_lm_index.py`, see
`MatterKey.md` §6a) to resolve a Clio matter id to its Lawmatics prospect id,
the missing piece needed to actually call `lawmatics_collections` from a
Clio-side consumer. `get_lm_prospect_id_for_matter()`/
`get_matterkey_index_entry()`, mocked via the existing `fake_firestore`
fixture. This is what ClioMCP's `deed_engine/lawmatics_collections_data.py`
(new the same day) uses to wire Lawmatics Collection data into the
PR-Inventory-Full recipe's Schedule A/B tables — see that repo's own
docstrings for the full writeup. 40/40 mocked tests passing.

**2026-09-26: write support added** — `lawmatics_create_collection_item`/
`lawmatics_delete_collection_item`, closing out the "deferred until a safe
test-write target is confirmed" note below. Confirmed live against the
dedicated test record (Prospect `18634852`) rather than assumed from vendor
docs, and two real gotchas found doing so: the `POST /collection_items` body
is flat (not JSON:API-wrapped like the read endpoints), and a `currency`
field's write value must be **raw cents as an integer** — a decimal string
like `"1234.56"` is silently truncated at the decimal point and misread as
cents (stored as `$12.34`, no error). `lawmatics_create_collection_item`
GET-verifies its own write, same reasoning as `lawmatics_update_custom_field`;
delete is a real delete (confirmed via 404 read-back), no GET-verify needed
there. Driven by ClioMCP's need to migrate legacy free-text inventory fields
into real Collection items across a batch of Probate/Heirship matters — see
ClioMCP's own CLAUDE.md for that effort. 46/46 mocked tests passing.

**Same day, follow-up: found and fixed a real, previously-latent read bug
while verifying the write above against ClioMCP's real matter, 01858-
Yarbrough.** `lawmatics_list_collection_items`'s client-side `collection_id`
filter compared a collection's own `id` (a JSON:API **string**, from
`lawmatics_list_collections`/`lawmatics_get_collection`) against a collection
item's own `collection_id` attribute (a real **int**) with bare `==` —
silently matching zero items for any caller that resolves `collection_id` by
name lookup rather than passing a hardcoded int literal. This is exactly the
path every real consumer uses (`deed_engine.lawmatics_collections_data.
get_matter_collection_items` resolves by collection *name*), so this API has
silently never returned real data to any actual consumer since the
2026-08-12 build — every prior "live confirmation" (including this repo's
own 2026-08-12 entry above) happened to test with a literal int, masking it.
Fixed by comparing both sides as `str()`; added a regression test
reproducing the exact mismatch. 47/47 mocked tests passing. No real matter
had actual Collection data before this was found (confirmed against two real
Probate/Heirship matters), so no past production output was actually wrong
— this was a latent bug, not a live-data incident.

**2026-09-26: two small read-only additions, driven by clio-hotstrings' new
`witness_lm_sync` feature (a Clio-witness-relation -> Lawmatics-prospect
sync, unrelated to this repo's own witness-field work).**
`clio_matters.clio_list_matter_related_contacts(matter_id)` — Clio's
Related Contacts feature is NOT a `matters.json` sub-field (every guess at
that 400s); the real resource is the nested
`GET /matters/{id}/related_contacts.json?fields=id,name,relationship{id,
description}` (see `ClioLearningLog.md` §14, added same session). Also
found and documented there: `GET /contacts.json?matter_id=<id>` silently
ignores that filter — same bug class as the already-known Lawmatics
`prospects?contact_id=` bug, just on the Clio side this time.
`lawmatics_client.lawmatics_fetch_prospect_custom_fields(prospect_id)` —
the read counterpart to the existing single-field
`lawmatics_update_custom_field`, exposing the same `GET /prospects/{id}?
fields=all` extraction that write helper's own read-back-verify step
already does internally, so a caller can check "does this field already
have a value" before deciding whether to write it at all. Both exported
from `jh_clio_lib/__init__.py`. 51/51 mocked tests passing (4 new).

**Same day, follow-up: real bug found and fixed while running clio-hotstrings'
new `lawmatics_to_clio` reverse sync for real.** `_paginate_braces`'s `query`
param (and `extra_params` values) were never URL-encoded — every EXISTING
consumer had only ever passed single-word queries ("Doe"), so this was latent
until a real multi-word search (a witness's full name, "Anita Madison") put a
literal space in the URL, which `http.client` (used deliberately instead of
`requests`, to avoid `requests` percent-encoding the `{}` in `fields=`) rejects
outright as a control character — a hard crash, not a wrong-but-tolerated
request. Confirmed the crash happened before any real write in that run (see
clio-hotstrings' own CLAUDE.md). Fixed with `urllib.parse.quote()` on just the
query/extra_params values, leaving the braces syntax elsewhere in the path
untouched. 57/57 mocked tests passing (1 new regression test).

## Open items specific to this project

- ClioMCP migration: point ClioMCP's `firm_data/` module at this library instead of
  its own duplicated `clio_auth.py`/`clio_client.py`/`field_map.py` — deliberately
  deferred to a separate session (see PROJECT_TRACKER.md).
- Lawmatics list/picklist-type custom fields: `lawmatics_update_custom_field`'s
  GET-verify doesn't yet resolve internal option ids back to labels (see the docstring
  in `lawmatics_client.py`) — no current consumer writes a list field, so this is
  deferred until one does.
- Lawmatics Collections write methods: create/delete built 2026-09-26 (see dated entry
  above). `update_collection_item` still not built — no consumer has needed an in-place
  edit yet (ClioMCP's migration only ever creates new items, never edits existing ones).
- **The actual goal (Robert's framing, 2026-08-12):** Lawmatics has no built-in way to
  merge Collections data into a Word document at all — this has to be done
  programmatically on our side. The plan is to read each Collection's items via
  `lawmatics_collections.py` and populate the *corresponding table* in ClioMCP's
  estate-inventory recipe (`full_inventory.py`), one table per collection
  name/type (e.g. "Real Property" → the real-property schedule table, "Financial
  Accounts" → the accounts schedule table). This needs a genuinely new pattern in
  ClioMCP — a real repeating-row Jinja `{% for %}` loop in a docxtpl template; that
  repo currently only flattens multi-item data into `<br>`-joined text, never a true
  table loop. Not started — see `PROJECT_TRACKER.md`'s jh-clio-lib section for the
  next-action writeup.
