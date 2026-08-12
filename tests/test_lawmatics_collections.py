from __future__ import annotations

import pytest
import responses

from jh_clio_lib import config, lawmatics_auth, lawmatics_collections as lc


@pytest.fixture(autouse=True)
def _lm_token(monkeypatch):
    monkeypatch.setattr(lawmatics_auth, "get_lawmatics_token", lambda: "lm-tok")


@responses.activate
def test_list_collections_paginates():
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/collections",
        json={
            "data": [{"id": 1, "attributes": {"name": "Assets", "custom_fields": []}}],
            "meta": {"total_pages": 2},
        },
        status=200,
    )
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/collections",
        json={
            "data": [{"id": 2, "attributes": {"name": "Heirs", "custom_fields": []}}],
            "meta": {"total_pages": 2},
        },
        status=200,
    )

    rows = lc.lawmatics_list_collections()

    assert [r["id"] for r in rows] == [1, 2]
    assert rows[0]["name"] == "Assets"
    assert len(responses.calls) == 2


@responses.activate
def test_get_collection_flattens_attributes():
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/collections/3",
        json={"data": {"id": 3, "attributes": {
            "name": "Assets",
            "custom_fields": [{"id": 295, "name": "Item Description", "field_type": "text"}],
        }}},
        status=200,
    )

    schema = lc.lawmatics_get_collection(3)

    assert schema == {
        "id": 3,
        "name": "Assets",
        "custom_fields": [{"id": 295, "name": "Item Description", "field_type": "text"}],
    }


@responses.activate
def test_list_collection_items_filters_by_contactable_type_and_collection_id():
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/collection_items",
        json={
            "data": [
                {"id": 10, "attributes": {
                    "contactable_type": "Prospect", "contactable_id": 18634852,
                    "collection_id": 3, "custom_field_values": [],
                }},
                {"id": 11, "attributes": {
                    "contactable_type": "Contact", "contactable_id": 18634852,
                    "collection_id": 3, "custom_field_values": [],
                }},
                {"id": 12, "attributes": {
                    "contactable_type": "Prospect", "contactable_id": 18634852,
                    "collection_id": 9, "custom_field_values": [],
                }},
            ],
            "meta": {"total_pages": 1},
        },
        status=200,
    )

    rows = lc.lawmatics_list_collection_items("Prospect", 18634852, collection_id=3)

    assert [r["id"] for r in rows] == [10]


@responses.activate
def test_get_collection_item():
    responses.add(
        responses.GET, f"{config.LAWMATICS_BASE}/collection_items/10",
        json={"data": {"id": 10, "attributes": {
            "contactable_type": "Prospect", "contactable_id": 18634852,
            "collection_id": 3,
            "custom_field_values": [{"id": 50, "custom_field_id": 295, "value": "House"}],
        }}},
        status=200,
    )

    row = lc.lawmatics_get_collection_item(10)

    assert row["custom_field_values"] == [{"id": 50, "custom_field_id": 295, "value": "House"}]


def test_resolve_collection_item_values_uses_own_inline_name_and_formatted_value():
    # Matches the real live shape (confirmed 2026-08-12) — no schema needed.
    item = {"id": 10, "custom_field_values": [
        {"id": 50, "custom_field_id": 295, "name": "Address", "field_type": "string",
         "value": "16627 Havasu Drive, Cypress, Texas 77433",
         "formatted_value": "16627 Havasu Drive, Cypress, Texas 77433"},
        {"id": 51, "custom_field_id": 296, "name": "Ownership", "field_type": "list",
         "value": "1640732", "formatted_value": "Community"},
        {"id": 52, "custom_field_id": 297, "name": "Appraised Value", "field_type": "currency",
         "value": 35000000, "formatted_value": "$350,000.00"},
    ]}

    assert lc.resolve_collection_item_values(item) == {
        "Address": "16627 Havasu Drive, Cypress, Texas 77433",
        "Ownership": "Community",
        "Appraised Value": "$350,000.00",
    }


def test_resolve_collection_item_values_falls_back_to_raw_value_when_unformatted():
    item = {"id": 10, "custom_field_values": [
        {"id": 50, "custom_field_id": 295, "name": "Notes", "value": "plain text", "formatted_value": None},
    ]}

    assert lc.resolve_collection_item_values(item) == {"Notes": "plain text"}


def test_resolve_collection_item_values_falls_back_to_schema_when_name_missing():
    schema = {"id": 3, "name": "Assets", "custom_fields": [
        {"id": 999, "name": "Legacy Field", "field_type": "string"},
    ]}
    item = {"id": 10, "custom_field_values": [
        {"id": 52, "custom_field_id": 999, "value": "orphaned", "formatted_value": None},
    ]}

    assert lc.resolve_collection_item_values(item, schema) == {"Legacy Field": "orphaned"}


def test_resolve_collection_item_values_unknown_field_id_kept_not_dropped():
    item = {"id": 10, "custom_field_values": [
        {"id": 52, "custom_field_id": 999, "value": "orphaned", "formatted_value": None},
    ]}

    assert lc.resolve_collection_item_values(item) == {"field_999": "orphaned"}
