"""Read access to Lawmatics Collections (API v1.22.0+) — firm-defined repeatable
data schemas (e.g. a list of assets, a list of heirs) attached to a Prospect or
Contact via `contactable_type`/`contactable_id`, distinct from both Custom Fields
and standard prospect/contact fields.

Read-only for now — write methods (create/update/delete_collection_item) are
deliberately deferred until a real collection schema and a safe test-write target
are confirmed live; see clio-lm-xfer's plan for this round.

Reuses `lawmatics_client.lawmatics_request` for auth + retry — no new HTTP code.
"""
from __future__ import annotations

from jh_clio_lib.lawmatics_client import lawmatics_request

# Lawmatics' list-filter query params only support one filter_by/filter_on pair
# per request (confirmed via the live API docs) — combining contactable_id with
# collection_id server-side isn't possible; filter the second dimension
# client-side after fetching by contactable_id.
_EQ = "="


def _flatten(row: dict) -> dict:
    """A JSON:API-style `{id, attributes: {...}}` row -> one flat dict."""
    flat = dict(row.get("attributes") or {})
    flat["id"] = row.get("id")
    return flat


def _paginate(path: str, params: dict) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        resp = lawmatics_request("GET", path, params={**params, "page": page})
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") or []
        rows.extend(_flatten(row) for row in data)
        total_pages = (body.get("meta") or {}).get("total_pages") or 1
        if page >= total_pages:
            break
        page += 1
    return rows


def lawmatics_list_collections() -> list[dict]:
    """GET /v1/collections, paginated. Each row: {id, name, custom_fields: [...]}."""
    return _paginate("/collections", {})


def lawmatics_get_collection(collection_id: int) -> dict:
    """GET /v1/collections/{id} -> {id, name, custom_fields: [{id, name, field_type,
    list_options?}, ...]}."""
    resp = lawmatics_request("GET", f"/collections/{collection_id}")
    resp.raise_for_status()
    return _flatten(resp.json().get("data") or {})


def lawmatics_list_collection_items(
    contactable_type: str, contactable_id: int, *, collection_id: int | None = None
) -> list[dict]:
    """GET /v1/collection_items filtered by contactable_id (the only server-side
    filter available), then narrowed client-side by contactable_type and
    (if given) collection_id — a contactable_id is only unique within one
    contactable_type, so both checks matter, not just the id.

    Each row: {id, contactable_type, contactable_id, collection_id,
    custom_field_values: [{id, custom_field_id, value, formatted_value}, ...]}.
    """
    params = {"filter_by": "contactable_id", "filter_on": contactable_id, "filter_with": _EQ}
    rows = _paginate("/collection_items", params)
    rows = [r for r in rows if r.get("contactable_type") == contactable_type]
    if collection_id is not None:
        rows = [r for r in rows if r.get("collection_id") == collection_id]
    return rows


def lawmatics_get_collection_item(item_id: int) -> dict:
    """GET /v1/collection_items/{id} -> same row shape as lawmatics_list_collection_items."""
    resp = lawmatics_request("GET", f"/collection_items/{item_id}")
    resp.raise_for_status()
    return _flatten(resp.json().get("data") or {})


def resolve_collection_item_values(item: dict, schema: dict | None = None) -> dict[str, object]:
    """Flatten an item's `custom_field_values` into a plain {field_name: value} dict.

    Confirmed live 2026-08-12 against real data (Prospect 18634852, "Real Property"/
    "Financial Accounts" items): each custom_field_value already carries its own
    `name` and `formatted_value` inline (e.g. a `list`-type field's `value` is the
    internal option id "1640732" but `formatted_value` is "Community"; a `currency`
    field's `value` is raw cents but `formatted_value` is "$350,000.00") — no
    separate schema join is required for the common case, unlike the plain Lawmatics
    custom-field list/picklist gotcha this was modeled after. `schema` (from
    lawmatics_get_collection) is an optional fallback, used only if a value is
    missing its own `name` (schema drift — an item predating a field rename)."""
    fields_by_id = {str(f["id"]): f for f in (schema or {}).get("custom_fields") or []}
    out: dict[str, object] = {}
    for cfv in item.get("custom_field_values") or []:
        field_id = str(cfv.get("custom_field_id", cfv.get("id")))
        name = cfv.get("name") or (fields_by_id.get(field_id) or {}).get("name") or f"field_{field_id}"
        formatted = cfv.get("formatted_value")
        out[name] = formatted if formatted not in (None, "") else cfv.get("value")
    return out
