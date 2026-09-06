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


def _paginate_braces(
    resource: str,
    fields: str,
    *,
    query: str = "",
    updated_since: str | None = None,
    created_since: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    next_token: str | None = None
    while True:
        path = f"/{resource}.json?limit={_PAGE_LIMIT}&fields={fields}"
        if query:
            path += f"&query={query}"
        if updated_since:
            path += f"&updated_since={updated_since}"
        if created_since:
            path += f"&created_since={created_since}"
        for key, value in (extra_params or {}).items():
            path += f"&{key}={value}"
        if next_token:
            path += f"&page_token={next_token}"
        body = clio_client.clio_braces_get(path)
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

    Returns raw Clio rows (dicts), unfiltered -- callers narrow down to the fields
    they need.
    """
    return _paginate_braces(
        resource, fields, query=query, updated_since=updated_since, created_since=created_since,
        extra_params=extra_params,
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
