"""Bulk matter listing with braces field-selection support.

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


def clio_list_matters(fields: str, *, query: str = "") -> list[dict]:
    """GET /matters.json?fields=<fields> across all pages (page_token pagination).

    `fields` may include Clio's brace sub-selection syntax (e.g.
    "id,display_number,client{name},custom_field_values{id,value,custom_field}") —
    passed through literally via clio_braces_get. Returns raw Clio matter rows
    (dicts), unfiltered — callers narrow down to the fields they need.
    """
    rows: list[dict] = []
    next_token: str | None = None
    while True:
        path = f"/matters.json?limit={_PAGE_LIMIT}&fields={fields}"
        if query:
            path += f"&query={query}"
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
