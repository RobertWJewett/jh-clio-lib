"""Lawmatics request wrapper + custom-field write with mandatory GET-verify.

Lawmatics returns HTTP 200 on silently-failed writes (ClioLearningLog.md §7), so a
PATCH is never trusted at face value — the update helper below always reads the
record back and raises if the value didn't actually change. Ported from
email-processor/main.py:update_lawmatics_prospect_fields, narrowed to the
single-field-by-id shape the design brief specifies (no field-name resolution here —
Lawmatics field-name mapping, if a consumer needs it, is a consumer-side concern).
"""
from __future__ import annotations

import time

import requests

from jh_clio_lib import config, lawmatics_auth
from jh_clio_lib.exceptions import LawmaticsWriteUnconfirmedError

_MAX_ATTEMPTS = 4
_RETRYABLE_STATUS = {429, 502, 503, 504}


def lawmatics_request(method: str, path: str, **kwargs) -> requests.Response:
    url = path if path.startswith("http") else f"{config.LAWMATICS_BASE}{path}"
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["Authorization"] = f"Bearer {lawmatics_auth.get_lawmatics_token()}"
    timeout = kwargs.pop("timeout", 20)
    resp: requests.Response | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, OSError):
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
            time.sleep(2 ** attempt)
            continue
        return resp

    return resp


def lawmatics_update_custom_field(prospect_id: int, field_id: str, value: object) -> None:
    """PATCH a single Lawmatics prospect custom field via the `custom_fields` array
    format — **string** field ids only (the flat `custom_field_{id}` keys and integer
    ids are not exposed as an option here; design brief §3). Lawmatics silently
    IGNORES a null value instead of clearing the field, so a `None` value is sent as
    "" to actually clear it (confirmed live). Immediately GET-verifies the write and
    raises LawmaticsWriteUnconfirmedError if the read-back doesn't match, since
    Lawmatics returns HTTP 200 on silently-failed writes.

    Known gap: list/picklist-type fields read back as their internal option id, not
    the label written — comparing that raw id against the written label would flag a
    successful write as a false mismatch. No consumer of this helper writes a list
    field yet; resolving that (as email-processor's fuller helper does via a
    per-field list_options lookup) is deferred until one does.
    """
    expected = "" if value is None else value
    body = {"custom_fields": [{"id": str(field_id), "value": expected}]}
    resp = lawmatics_request("PATCH", f"/prospects/{prospect_id}", json=body)
    resp.raise_for_status()

    rb = lawmatics_request("GET", f"/prospects/{prospect_id}", params={"fields": "all"})
    rb.raise_for_status()
    rb_attrs = (rb.json().get("data") or {}).get("attributes", {})
    rb_by_id = {
        str(cf.get("id")): cf.get("value")
        for cf in rb_attrs.get("custom_fields", [])
        if cf.get("id") is not None
    }
    actual = rb_by_id.get(str(field_id))
    if str(actual).strip() != str(expected).strip():
        raise LawmaticsWriteUnconfirmedError(
            f"Lawmatics prospect {prospect_id} field {field_id}: wrote {expected!r}, "
            f"read back {actual!r} after HTTP 200 PATCH."
        )
