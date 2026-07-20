from __future__ import annotations

import pytest
import responses

from jh_clio_lib import config, lawmatics_auth, lawmatics_client
from jh_clio_lib.exceptions import LawmaticsWriteUnconfirmedError


@pytest.fixture(autouse=True)
def _lm_token(monkeypatch):
    monkeypatch.setattr(lawmatics_auth, "get_lawmatics_token", lambda: "lm-tok")


@responses.activate
def test_update_custom_field_success():
    responses.add(
        responses.PATCH, f"{config.LAWMATICS_BASE}/prospects/99",
        json={"data": {}}, status=200,
    )
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/prospects/99",
        json={"data": {"attributes": {"custom_fields": [{"id": "611260", "value": "Fort Bend"}]}}},
        status=200,
    )

    lawmatics_client.lawmatics_update_custom_field(99, "611260", "Fort Bend")

    patch_call = responses.calls[0]
    assert patch_call.request.body is not None
    import json as _json
    assert _json.loads(patch_call.request.body) == {
        "custom_fields": [{"id": "611260", "value": "Fort Bend"}]
    }


@responses.activate
def test_update_custom_field_raises_on_readback_mismatch():
    responses.add(
        responses.PATCH, f"{config.LAWMATICS_BASE}/prospects/99",
        json={"data": {}}, status=200,
    )
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/prospects/99",
        json={"data": {"attributes": {"custom_fields": [{"id": "611260", "value": "stale"}]}}},
        status=200,
    )

    with pytest.raises(LawmaticsWriteUnconfirmedError):
        lawmatics_client.lawmatics_update_custom_field(99, "611260", "Fort Bend")


@responses.activate
def test_none_value_sent_and_verified_as_empty_string():
    responses.add(
        responses.PATCH, f"{config.LAWMATICS_BASE}/prospects/99",
        json={"data": {}}, status=200,
    )
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/prospects/99",
        json={"data": {"attributes": {"custom_fields": [{"id": "611260", "value": ""}]}}},
        status=200,
    )

    lawmatics_client.lawmatics_update_custom_field(99, "611260", None)

    import json as _json
    assert _json.loads(responses.calls[0].request.body) == {
        "custom_fields": [{"id": "611260", "value": ""}]
    }
