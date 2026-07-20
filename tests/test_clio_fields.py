from __future__ import annotations

import pytest

from jh_clio_lib import clio_client, clio_fields
from jh_clio_lib.exceptions import AmbiguousFieldError, FieldNotFoundError


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_uses_firestore_cache_without_hitting_clio(fake_firestore, monkeypatch):
    fmap = {"DecedentNameorWard": [{"id": 111, "field_type": "text_line", "parent_type": "Matter"}]}
    fake_firestore.seed("clio_manage_state", "custom_field_definitions", {"fields": fmap})

    def _fail(*_a, **_kw):
        raise AssertionError("should not call Clio when cache is warm")

    monkeypatch.setattr(clio_client, "clio_request", _fail)

    assert clio_fields.clio_list_custom_field_definitions() == fmap


def test_refreshes_from_clio_when_cache_missing(fake_firestore, monkeypatch):
    rows = [
        {"id": 1, "name": "Applicant", "field_type": "text_line", "parent_type": "Matter"},
        {"id": 2, "name": "Applicant", "field_type": "text_line", "parent_type": "Contact"},
    ]
    monkeypatch.setattr(
        clio_client, "clio_request",
        lambda method, path, **kw: _FakeResponse({"data": rows, "meta": {}}),
    )

    fmap = clio_fields.clio_list_custom_field_definitions()

    assert fmap["Applicant"] == [
        {"id": 1, "field_type": "text_line", "parent_type": "Matter"},
        {"id": 2, "field_type": "text_line", "parent_type": "Contact"},
    ]
    stored = fake_firestore.collection("clio_manage_state").document("custom_field_definitions").get().to_dict()
    assert stored["fields"] == fmap


def test_resolve_name_to_id_not_found():
    with pytest.raises(FieldNotFoundError):
        clio_fields._resolve_name_to_id("Nonexistent", {})


def test_resolve_name_to_id_ambiguous():
    fmap = {"Child_02_Email": [
        {"id": 1, "field_type": "email", "parent_type": "Matter"},
        {"id": 2, "field_type": "email", "parent_type": "Matter"},
    ]}
    with pytest.raises(AmbiguousFieldError):
        clio_fields._resolve_name_to_id("Child_02_Email", fmap, parent_type="Matter")


def test_update_matter_custom_fields_updates_existing_and_creates_new(monkeypatch):
    fmap = {
        "DecedentNameorWard": [{"id": 111, "field_type": "text_line", "parent_type": "Matter"}],
        "Hearing_Date": [{"id": 222, "field_type": "date", "parent_type": "Matter"}],
    }
    monkeypatch.setattr(clio_fields, "clio_list_custom_field_definitions", lambda: fmap)
    # Definition 111 already has a value instance (id "inst-1"); 222 does not.
    monkeypatch.setattr(
        clio_fields, "_get_matter_custom_field_values",
        lambda matter_id: [{"id": "inst-1", "value": "old", "custom_field": {"id": 111}}],
    )

    captured = {}

    def _fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return _FakeResponse({})

    monkeypatch.setattr(clio_client, "clio_request", _fake_request)

    clio_fields.clio_update_matter_custom_fields(
        42, {"DecedentNameorWard": "Jane Doe", "Hearing_Date": "2026-08-01"}
    )

    assert captured["method"] == "PATCH"
    assert captured["path"] == "/matters/42.json"
    items = captured["json"]["data"]["custom_field_values"]
    updates = [i for i in items if "id" in i]
    creates = [i for i in items if "custom_field" in i]
    assert updates == [{"id": "inst-1", "value": "Jane Doe"}]
    assert creates == [{"custom_field": {"id": 222}, "value": "2026-08-01"}]


def test_update_matter_custom_fields_fails_loud_on_unknown_name(monkeypatch):
    monkeypatch.setattr(clio_fields, "clio_list_custom_field_definitions", lambda: {})
    with pytest.raises(FieldNotFoundError):
        clio_fields.clio_update_matter_custom_fields(42, {"Nope": "value"})
