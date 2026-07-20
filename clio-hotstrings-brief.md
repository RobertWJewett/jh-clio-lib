# Clio Hotstrings — Project Brief

**Status:** v1 design, ready for scaffolding
**Repo:** `~/my-automations/clio-hotstrings` (new, standalone)

---

## 1. Purpose

A cross-machine hotstring/hotkey tool that lets Robert type a short trigger
(e.g. `/Decedent`) into any document, spreadsheet, or web page, pick the
relevant matter from a popup, and have a Clio field value inserted at the
cursor — without leaving the app he's working in or looking anything up
manually.

v2 extends this to multi-field templates: a single hotstring (e.g.
`/aalappt`) populates a full templated block of text (boilerplate + several
substituted fields) via a small editable popup before insertion.

## 2. Why this needs its own repo, not a ClioMCP module

MCP is a protocol between an LLM client (Claude Desktop, Claude Code) and
tools — Keyboard Maestro and AutoHotkey aren't MCP clients and can't speak
it. This tool is a different kind of consumer: a lightweight local helper
service that OS-level automation tools call via HTTP or CLI, not an
MCP-connected agent. It's a sibling to ClioMCP, not a mode of it.

## 3. Dependency: shared Clio/Lawmatics auth module

This is the **second** project (alongside ClioMCP) that needs Clio API
access outside of a single-app context. Rather than duplicate OAuth/token
logic again, this is the moment to extract a shared auth module — reused by
both ClioMCP and this tool, and by any future project touching Clio. This
was flagged as a parked idea in an earlier session; treat this project as
the trigger to actually build it.

**Scope of the shared module (minimal for now):** token acquisition/refresh,
credential storage location, and a thin request wrapper — not a general
Clio SDK. Expand later if a third consumer needs more.

## 4. Architecture — resolved

**HTTP endpoint, not CLI script.** Responsiveness is the top criterion, and
a persistent warm process (Firestore/ADC auth, field cache, matter list all
loaded once) avoids per-keystroke cold-start latency that a spawned CLI
script would pay every time.

**Build order:** Mac (Keyboard Maestro) first, prove out responsiveness in
practice, then decide on Windows/AutoHotkey. Not committing to both
platforms in v1.

**Lifecycle management:** `launchd` (Mac), with `KeepAlive: true` (auto
-restart on crash) and `RunAtLoad: true` (starts on login). A separate,
lightweight watchdog job pings a `/health` endpoint every few minutes —
covers the failure mode `launchd` alone can't (a hung-but-not-crashed
process) — and fires a macOS notification plus attempts `launchctl
kickstart` if the check fails. No general multi-service dashboard for v1 —
that's solving for a fleet of local daemons that doesn't exist yet; revisit
if/when a second local service shows up.

```
Keyboard Maestro (Mac) ─┐
AutoHotkey (Windows,    ─┼──▶  local HTTP service  ──▶  Firestore (cache-first)
  deferred until Mac    │      (launchd + watchdog)   └─▶ Clio API (fallback only)
  is proven)            │
                         └──▶  clipboard set + paste (insertion mechanism,
                                except Decedent_SSN — see §5 security note)
```

- **Matter picker:** searches the Firestore-cached matter list (display
  number, client name, MatterKey), not a live Clio call — keeps the picker
  feeling instant while typing.

## 4a. Trigger design

**Activation character: `;` (semicolon).** Semicolons essentially never
*start* an English word or sentence, making a leading `;` a low-collision
choice for a hotstring trigger — safer than the originally-discussed `/`,
which legitimately appears at the start of file paths, dates, and fractions.

**Pattern:**
- Individual hotstrings: `;` + a short mnemonic **decoupled from the actual
  Clio field name** (e.g. `;dec` → `DecedentNameorWard`, `;aal` → Ad Litem
  template) — configured in the YAML mapping (§ config), so Robert never
  has to remember Clio's real field naming to use this day-to-day.
- **Index/TOC command: `;;;`** (three semicolons) — lists all currently
  defined hotstrings, so the mnemonic set doesn't have to be memorized
  either.

**Implementation note:** trigger matching must be **exact-string**, not
"starts with" — otherwise `;;;` risks being intercepted partway through by
a shorter `;`-prefixed hotstring before the third semicolon lands. Keyboard
Maestro's "The following text was typed" trigger does exact matching by
default; confirm this explicitly when configuring rather than assuming.

## 5. Firestore caching — v1, from day one

Per decision: v1 starts with Firestore caching rather than live Clio calls,
for latency reasons (a live OAuth+API round-trip doesn't belong in a
"type and go" workflow).

**Field allowlist, v1 (final):**
- `Applicant`
- `Applicant_Name_on_ID`
- `Applicant_County`
- `DecedentNameorWard`
- `Decedent_Age_at_Death`
- `Decedent_Residence_Address`
- `Decedent_SSN_Last3` — firm policy is last-3-digits only, never full SSN;
  see note below
- `Hearing_Date`
- `Spouse_Name`
- `MatterKey`
- `LegalFees`
- Ad Litem: `Name`, `Phone`, `Email` (address deliberately excluded for
  v1 — "will likely add later" per Robert; exact Clio field names/IDs still
  TBD, confirm these exist as Clio custom fields before building)

**Note on `Decedent_SSN_Last3`:** since firm practice already limits this to
the last three digits (never a full SSN), the clipboard-exposure concern
from a full-SSN scenario doesn't really apply here — a partial 3-digit
fragment sitting briefly in clipboard history is a much lower-stakes
exposure. No special insertion handling needed; treat like the other
fields. (Worth noting for general awareness: this is still technically PII
under some frameworks even truncated, but not remotely the same risk
profile as a full SSN — not something this project needs to design around.)

**Population mechanism:** a new lightweight scheduled job (sibling to
`matterkey-maintenance-job`), pulling the allowlisted fields per matter into
Firestore on a nightly cadence — same pattern already established, not a
new one.

## 6. Security principle — stated explicitly, not implied

**This tool is read-only against Clio, always.** It is a typing convenience,
not a data-entry mechanism. No write scope, in v1 or any future version,
regardless of what gets layered on top later. If a future idea needs to
write back to Clio, that's a different tool with its own explicit scope —
not an extension of this one's permissions.

## 7. v1 scope

- Single-field hotstring → matter picker (Firestore-backed, fuzzy search) →
  clipboard-paste insertion of one cached field value.
- Depends on: shared auth module (§3), Firestore field cache + population
  job (§5).

## 8. v2 scope (later)

- Template store: `hotstring → {field_map, template_text}` — structurally
  the same recipe pattern as the deed engine (`field_map` + template),
  applied to canned correspondence instead of deeds.
- Small editable popup pre-filled with the substituted template (placeholder
  values swapped in) before final insertion — doesn't need to be elaborate
  for a first cut; Keyboard Maestro's own "large type" text prompt may cover
  this initially rather than building a custom editor immediately.

## 9. Open items — status

**Resolved this session:**
1. ~~Local helper service: HTTP vs. CLI~~ → **HTTP**, for responsiveness (§4).
2. ~~Field allowlist~~ → final list in §5, including Ad Litem name/phone/email.
3. ~~Config storage location~~ → **local YAML file, git-tracked in the repo**
   (not Firestore) — single user, single machine for now, so file-editing
   simplicity and git history beat remote-editability.
4. ~~Windows timing~~ → **Mac first**, prove responsiveness, decide
   AutoHotkey scope afterward — not committing both platforms in v1.
5. ~~`Decedent_SSN` insertion handling~~ → moot — firm policy is last-3-digits
   only, never full SSN; no special handling needed (§5).
6. ~~`clio_list_custom_field_definitions()` cache location~~ → **Firestore**,
   shared across machines and consumers — not a per-project local file (see
   `jh-clio-lib` §3 update). Keeps this consistent with the per-matter field
   *value* cache, which was already Firestore-based and therefore already
   naturally shared across machines.

**Still open:**
1. Exact Clio field names/IDs for Ad Litem `Name`/`Phone`/`Email` — confirm
   these exist before building the `/aalappt`-equivalent v2 template.
