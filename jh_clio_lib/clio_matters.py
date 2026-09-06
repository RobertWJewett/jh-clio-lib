"""Bulk matter/contact listing with braces field-selection support.

Ported from email-processor/audit_matterkey.py:scan_clio_matters and
maintain_clio_matterkeys.py's page_token pagination loop — the proven pattern for
pulling ALL matters (not a `query`-filtered subset) with custom_field_values
sub-selection, which `clio_request` (backed by `requests`) would break by
percent-encoding the {}.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from jh_clio_lib import clio_client

_PAGE_LIMIT = 200

# Confirmed live 2026-09-06 against /documents.json (~8,200-11,800 records deep,
# order=id(asc) default): Clio's page_token pagination has a hard depth limit --
# likely the underlying search index's default result-window cap -- and returns
# this exact 422 once exceeded, regardless of how many total records remain.
# There is no documented alternative cursor; the practical workaround is to
# restart pagination from a `created_since` floor advanced past whatever's
# already been fetched, which resets the offset to 0 for a narrower result set.
_DEPTH_LIMIT_MARKER = "page_token is now out of bounds"


def _paginate_braces(
    resource: str,
    fields: str,
    *,
    query: str = "",
    updated_since: str | None = None,
    created_since: str | None = None,
    extra_params: dict[str, str] | None = None,
    order: str | None = None,
    deep_paginate: bool = False,
) -> list[dict]:
    rows: list[dict] = []
    next_token: str | None = None
    since_floor = created_since
    while True:
        path = f"/{resource}.json?limit={_PAGE_LIMIT}&fields={fields}"
        if query:
            path += f"&query={query}"
        if updated_since:
            path += f"&updated_since={updated_since}"
        if since_floor:
            path += f"&created_since={since_floor}"
        if order:
            path += f"&order={order}"
        for key, value in (extra_params or {}).items():
            path += f"&{key}={value}"
        if next_token:
            path += f"&page_token={next_token}"
        try:
            body = clio_client.clio_braces_get(path)
        except RuntimeError as exc:
            if deep_paginate and _DEPTH_LIMIT_MARKER in str(exc) and rows:
                # Restart from just past the last record we actually got -- a
                # fresh, narrower query starts its own pagination back at
                # offset 0, clear of the depth limit. `order` must be
                # `created_at(asc)` (enforced by clio_list_resource below) for
                # "the last record we got" to be a safe floor for what's left.
                next_token = None
                since_floor = rows[-1]["created_at"]
                continue
            raise
        rows.extend(body.get("data") or [])
        next_url = (body.get("meta") or {}).get("paging", {}).get("next")
        if not next_url:
            break
        next_token = parse_qs(urlsplit(next_url).query).get("page_token", [None])[0]
        if not next_token:
            break
    return rows


def clio_list_resource(
    resource: str,
    fields: str,
    *,
    query: str = "",
    updated_since: str | None = None,
    created_since: str | None = None,
    extra_params: dict[str, str] | None = None,
    deep_paginate: bool = False,
) -> list[dict]:
    """GET /<resource>.json?fields=<fields> across all pages (page_token pagination),
    for any Clio v4 list endpoint -- e.g. "users", "practice_areas", "custom_fields",
    "bills", "trust_line_items", "activities", "notes", "documents", not just matters/
    contacts (see clio_list_matters/clio_list_contacts below, which are thin wrappers
    over this same function kept for backward compatibility).

    `fields` may include Clio's one-level brace sub-selection syntax (e.g.
    "id,display_number,client{name},custom_field_values{id,value,custom_field}") —
    passed through literally via clio_braces_get.

    `updated_since`/`created_since` (ISO-8601, e.g. "2026-09-01T00:00:00Z") map to
    Clio's own incremental-filter query params -- confirmed present on every list
    endpoint checked so far (ClioLearningLog.md §2, 2026-09-05).

    `extra_params` covers resource-specific required/optional filters not common
    enough to deserve their own keyword -- e.g. `/notes.json` unconditionally
    requires `type` (`Matter` or `Contact`) with no way to fetch both in one call
    (ClioLearningLog.md §2, 2026-09-05); pass `extra_params={"type": "Matter"}`.

    `deep_paginate=True` self-recovers from Clio's page_token depth limit (hit on
    /documents.json past ~8-12k records, ClioLearningLog.md §2, 2026-09-06) by
    restarting from a `created_since` floor once the limit is hit. Requires
    `fields` to include `created_at` -- forces `order=created_at(asc)` so "the
    last record fetched" is a safe floor for what's left. Only worth setting for
    a resource/pull large enough to plausibly hit the limit; harmless overhead
    (one extra `order=` param) otherwise.

    Returns raw Clio rows (dicts), unfiltered -- callers narrow down to the fields
    they need.
    """
    return _paginate_braces(
        resource, fields, query=query, updated_since=updated_since, created_since=created_since,
        extra_params=extra_params,
        order="created_at(asc)" if deep_paginate else None,
        deep_paginate=deep_paginate,
    )


def clio_list_matters(fields: str, *, query: str = "") -> list[dict]:
    """GET /matters.json?fields=<fields> across all pages (page_token pagination).

    `fields` may include Clio's brace sub-selection syntax (e.g.
    "id,display_number,client{name},custom_field_values{id,value,custom_field}") —
    passed through literally via clio_braces_get. Returns raw Clio matter rows
    (dicts), unfiltered — callers narrow down to the fields they need.
    """
    return clio_list_resource("matters", fields, query=query)


def clio_list_contacts(fields: str, *, query: str = "") -> list[dict]:
    """GET /contacts.json?fields=<fields> across all pages — same pattern as
    clio_list_matters, for scripts that need to scan ALL contacts (e.g. a
    phone-number-format backfill), not just contacts.json's own `query` filter."""
    return clio_list_resource("contacts", fields, query=query)
