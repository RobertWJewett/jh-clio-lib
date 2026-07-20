# jh-clio-lib — Shared Clio/Lawmatics Auth & Request Module

**Status:** design brief, ready for scaffolding
**Repo:** `~/my-automations/jh-clio-lib` (new, standalone)
**First consumers:** ClioMCP (firm-data MCP server), clio-hotstrings

---

## 1. Purpose

A minimal, shared Python module wrapping Clio and Lawmatics API access —
token retrieval, request/retry handling, and the write-format rules already
learned the hard way — so every new local project stops re-deriving or
re-breaking the same knowledge. Not a general SDK; scoped to exactly what
the firm's tools actually need.

This directly fulfills what `clio-mcp-server-tool-spec.md` already said the
firm-data MCP server should be: "a thin wrapper over API access that already
exists in the firm's other projects." ClioMCP's tools should call into this
library rather than reimplementing the same logic a second time.

## 2. Scope: local-only for now

Both initial consumers run locally (ClioMCP's stdio server, clio-hotstrings'
local helper) — neither is Cloud Run-deployed. Distribution is therefore an
editable local install (`pip install -e ../jh-clio-lib` or equivalent), not
a published package. **Deliberately deferred:** how a future Cloud
Run-deployed consumer would pull this in (private-repo pip install during a
Cloud Run build) — not a problem worth solving before it's needed.

**Also deliberately deferred:** retrofitting existing Cloud Run services
(`email-processor`, `clio-email-filer`, `matterkey-maintenance-job`) onto
this module. Worth doing eventually for consistency; not part of this
extraction, to avoid scope creep onto already-working production code.

## 3. API surface — v1

### Auth
- `get_clio_token()` — reads the current Clio access token from Firestore
  `clio_manage_state/tokens.access_token` (the Gen 2 pattern — **not** the
  stale Secret Manager `clio-access-token` secret). Requires ADC
  (`gcloud auth application-default login` +
  `set-quota-project jh-law-rc-clio-personal`).
- `get_lawmatics_token()` — reads from the canonical local Lawmatics token
  storage. On missing/invalid token, raises a clear error pointing at
  `scripts/lawmatics_connect.py` — not a bare auth failure a consumer has to
  go debug from scratch.

### Request wrappers
- `clio_request(method, path, **kwargs)` — injects bearer token + base URL
  (`https://app.clio.com/api/v4` or whatever's currently canonical — verify
  against `docs.developers.clio.com/openapi.json` at build time, not from
  memory), with the retry/backoff policy already proven in
  `_migrate_dup_fields.py` (4 retries, exponential backoff on
  `OSError`/`URLError`/429/502/503/504).
- `lawmatics_request(method, path, **kwargs)` — same shape, base URL
  `https://api.lawmatics.com/v1` (not `app.lawmatics.com/api/v1`).

### High-level helpers (the load-bearing part)
- `clio_update_matter_custom_fields(matter_id, {field_name: value})` —
  resolves human field names → IDs via a cached custom-field-definitions
  pull, and handles the two-ID split from `deed-engine-spec-v0.3.md` §10
  (definition ID to create a value vs. `custom_field_value` instance ID to
  update/clear an existing one) automatically. Fails loud on an unresolvable
  field name — never emits a silent blank write.
- `lawmatics_update_custom_field(prospect_id, field_id, value)` — enforces
  the `custom_fields` array format with **string** IDs as the only path
  through this module (no flat `custom_field_{id}` keys, no integer IDs —
  those are simply not exposed as an option here). Performs the mandatory
  GET-verify immediately after the PATCH and raises if the value didn't
  actually change, since Lawmatics returns HTTP 200 on silently-failed
  writes.
- `clio_list_custom_field_definitions()` / cache — feeds the name→ID
  resolution above. **Cached in Firestore, not a local file** — needs to
  stay consistent across machines (Mac now, Windows later) and across
  consumers (ClioMCP, clio-hotstrings), so a per-machine local cache file
  would silently defeat that goal. Refreshed on demand or on a schedule,
  matching the same pattern as the rest of the Gen 2 credential/cache model.

## 4. Explicit non-goals for v1

- Not a full Clio or Lawmatics SDK — only what current consumers need.
- Not handling Microsoft Graph auth (separate existing pattern, separate
  concern — no reason to fold it in here).
- Not solving Cloud Run distribution (§2).
- Not retrofitting existing production services (§2).

## 5. Versioning

Pin consumers by git commit or tag rather than floating to `main` — cheap
insurance against a WIP change in this library silently breaking a
different project mid-session. A lightweight habit, not a formal release
process.

## 6. Open items

1. Confirm current Clio API base URL against the live OpenAPI spec at build
   time (documented above as `app.clio.com/api/v4` from memory — verify,
   don't trust).
2. Decide exact local storage location/format for the Lawmatics token if
   it needs to differ from existing local dev conventions.
