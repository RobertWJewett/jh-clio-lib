"""Clio custom-field name<->id resolution and the two-ID write rule (definition id
to create a value vs. the existing value's own instance id to update/clear it).

Cache is Firestore-backed (clio_manage_state/custom_field_definitions), not a local
file — needs to stay consistent across machines (Mac now, Windows later) and across
consumers (ClioMCP, clio-hotstrings), so a per-machine local cache file would silently
defeat that goal (design brief §3). This supersedes ClioMCP/firm_data/field_map.py,
which cached to a local gitignored JSON file; the two-ID write logic here is ported
from ClioMCP/firm_data/clio_client.py:update_matter_custom_field_values.
"""
from __future__ import annotations

from datetime import datetime, timezone

from jh_clio_lib import clio_client, config
from jh_clio_lib.exceptions import AmbiguousFieldError, FieldNotFoundError

_CACHE_COLLECTION = "clio_manage_state"
_CACHE_DOC = "custom_field_definitions"


def _paginate(path: str, params: dict) -> list[dict]:
    """Follow meta.paging.next (absolute URL) to exhaustion. ClioLearningLog.md §2."""
    results: list[dict] = []
    resp = clio_client.clio_request("GET", path, params=params)
    resp.raise_for_status()
    body = resp.json()
    results.extend(body.get("data") or [])
    next_url = (body.get("meta") or {}).get("paging", {}).get("next")
    while next_url:
        resp = clio_client.clio_request("GET", next_url)
        resp.raise_for_status()
        body = resp.json()
        results.extend(body.get("data") or [])
        next_url = (body.get("meta") or {}).get("paging", {}).get("next")
    return results


def _fetch_definitions_from_clio() -> dict:
    rows = _paginate("/custom_fields.json", {"fields": "id,name,field_type,parent_type"})
    fields: dict[str, list[dict]] = {}
    for r in rows:
        name = r.get("name")
        if name is None:
            continue
        fields.setdefault(name, []).append(
            {"id": r["id"], "field_type": r.get("field_type"), "parent_type": r.get("parent_type")}
        )
    return fields


def refresh_custom_field_cache() -> dict:
    """Rebuild the name -> [{id, field_type, parent_type}, ...] cache from live Clio
    and write it to Firestore."""
    from google.cloud import firestore

    fields = _fetch_definitions_from_clio()
    db = firestore.Client(project=config.GCP_PROJECT)
    db.collection(_CACHE_COLLECTION).document(_CACHE_DOC).set({
        "fields": fields,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return fields


def clio_list_custom_field_definitions() -> dict:
    """Load the name -> [{id, field_type, parent_type}, ...] map from the Firestore
    cache, refreshing from live Clio if the cache doesn't exist yet."""
    from google.cloud import firestore

    db = firestore.Client(project=config.GCP_PROJECT)
    doc = db.collection(_CACHE_COLLECTION).document(_CACHE_DOC).get()
    if doc.exists:
        data = doc.to_dict() or {}
        fields = data.get("fields")
        if fields:
            return fields
    return refresh_custom_field_cache()


def _resolve_name_to_id(name: str, fmap: dict, *, parent_type: str = "Matter") -> int:
    entries = [e for e in (fmap.get(name) or []) if e.get("parent_type") == parent_type]
    if not entries:
        raise FieldNotFoundError(f"{name!r} (parent_type={parent_type!r})")
    if len(entries) > 1:
        raise AmbiguousFieldError(f"{name!r} (parent_type={parent_type!r}) -> {entries}")
    return entries[0]["id"]


def _get_matter_custom_field_values(matter_id: int) -> list[dict]:
    """Raw custom_field_values for a matter: [{id, value, custom_field: {id, name}}, ...].
    id here is the VALUE INSTANCE id, custom_field.id is the DEFINITION id."""
    path = f"/matters/{matter_id}.json?fields=id,custom_field_values{{id,value,custom_field}}"
    body = clio_client.clio_braces_get(path)
    data = body.get("data") or {}
    return data.get("custom_field_values") or []


def clio_update_matter_custom_fields(matter_id: int, fields: dict[str, object]) -> None:
    """Write {human field name: value} onto a matter's custom fields.

    Resolves each name to its definition id via the Firestore-backed cache — fails
    loud (FieldNotFoundError/AmbiguousFieldError) on an unresolvable or ambiguous
    name, never emits a silent blank write. Then applies the two-ID rule (design
    brief §3 / deed-engine-spec-v0.3.md §10): PATCH with the existing value's own
    instance id if one already exists for that definition (updates in place), else
    PATCH with {"custom_field": {"id": defn_id}} (creates a new value). Sending the
    definition-id form when a value already exists creates a DUPLICATE row instead
    of updating. Batches all fields into one PATCH.
    """
    fmap = clio_list_custom_field_definitions()
    values_by_defn_id: dict[int, object] = {}
    for name, value in fields.items():
        defn_id = _resolve_name_to_id(name, fmap)
        values_by_defn_id[defn_id] = value

    existing = _get_matter_custom_field_values(matter_id)
    existing_instance_id_by_defn: dict[int, str] = {}
    for row in existing:
        defn_id = (row.get("custom_field") or {}).get("id")
        instance_id = row.get("id")
        if defn_id is not None and instance_id is not None:
            existing_instance_id_by_defn[defn_id] = instance_id

    payload_items = []
    for defn_id, value in values_by_defn_id.items():
        instance_id = existing_instance_id_by_defn.get(defn_id)
        if instance_id is not None:
            payload_items.append({"id": instance_id, "value": value})
        else:
            payload_items.append({"custom_field": {"id": defn_id}, "value": value})

    body = {"data": {"custom_field_values": payload_items}}
    resp = clio_client.clio_request("PATCH", f"/matters/{matter_id}.json", json=body)
    resp.raise_for_status()
