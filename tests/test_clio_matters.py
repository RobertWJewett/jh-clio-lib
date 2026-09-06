from __future__ import annotations

from jh_clio_lib import clio_client, clio_matters


def test_clio_list_matters_paginates_via_page_token(monkeypatch):
    pages = [
        {
            "data": [{"id": 1, "display_number": "24-001"}],
            "meta": {"paging": {"next": "https://app.clio.com/api/v4/matters.json?page_token=abc"}},
        },
        {
            "data": [{"id": 2, "display_number": "24-002"}],
            "meta": {"paging": {}},
        },
    ]
    calls = []

    def _fake_braces_get(path):
        calls.append(path)
        return pages.pop(0)

    monkeypatch.setattr(clio_client, "clio_braces_get", _fake_braces_get)

    rows = clio_matters.clio_list_matters("id,display_number")

    assert [r["id"] for r in rows] == [1, 2]
    assert "page_token=abc" not in calls[0]
    assert "page_token=abc" in calls[1]


def test_clio_list_matters_passes_query_and_fields(monkeypatch):
    captured = {}

    def _fake_braces_get(path):
        captured["path"] = path
        return {"data": [], "meta": {}}

    monkeypatch.setattr(clio_client, "clio_braces_get", _fake_braces_get)

    clio_matters.clio_list_matters("id,custom_field_values{id,value,custom_field}", query="Doe")

    assert "fields=id,custom_field_values{id,value,custom_field}" in captured["path"]
    assert "query=Doe" in captured["path"]


def test_clio_list_resource_passes_since_filters_and_resource_name(monkeypatch):
    captured = {}

    def _fake_braces_get(path):
        captured["path"] = path
        return {"data": [], "meta": {}}

    monkeypatch.setattr(clio_client, "clio_braces_get", _fake_braces_get)

    clio_matters.clio_list_resource(
        "trust_line_items",
        "id,date,total",
        updated_since="2026-09-01T00:00:00Z",
        created_since="2026-08-01T00:00:00Z",
    )

    assert captured["path"].startswith("/trust_line_items.json")
    assert "fields=id,date,total" in captured["path"]
    assert "updated_since=2026-09-01T00:00:00Z" in captured["path"]
    assert "created_since=2026-08-01T00:00:00Z" in captured["path"]


def test_clio_list_resource_passes_extra_params(monkeypatch):
    captured = {}

    def _fake_braces_get(path):
        captured["path"] = path
        return {"data": [], "meta": {}}

    monkeypatch.setattr(clio_client, "clio_braces_get", _fake_braces_get)

    clio_matters.clio_list_resource("notes", "id,subject", extra_params={"type": "Matter"})

    assert "type=Matter" in captured["path"]


def test_clio_list_resource_deep_paginate_recovers_from_depth_limit(monkeypatch):
    # Page 1 succeeds; page 2 (via page_token) hits Clio's real depth-limit 422;
    # recovery should restart from the last record's created_at with no
    # page_token, then a fresh page 2 (via a NEW page_token) succeeds.
    calls = []
    responses = [
        {
            "data": [{"id": 1, "created_at": "2026-01-01T00:00:00Z"}],
            "meta": {"paging": {"next": "https://app.clio.com/api/v4/documents.json?page_token=stale"}},
        },
        RuntimeError(
            "Clio GET /documents.json?...&page_token=stale -> 422: "
            "{'error': {'message': 'page_token is now out of bounds and cannot be used.'}}"
        ),
        {
            "data": [{"id": 2, "created_at": "2026-01-02T00:00:00Z"}],
            "meta": {"paging": {}},
        },
    ]

    def _fake_braces_get(path):
        calls.append(path)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(clio_client, "clio_braces_get", _fake_braces_get)

    rows = clio_matters.clio_list_resource("documents", "id,created_at", deep_paginate=True)

    assert [r["id"] for r in rows] == [1, 2]
    assert "order=created_at(asc)" in calls[0]
    assert "page_token=stale" in calls[1]
    assert "created_since=2026-01-01T00:00:00Z" in calls[2]
    assert "page_token" not in calls[2]


def test_clio_list_contacts_paginates_via_page_token(monkeypatch):
    pages = [
        {
            "data": [{"id": 1, "name": "Jane Doe"}],
            "meta": {"paging": {"next": "https://app.clio.com/api/v4/contacts.json?page_token=abc"}},
        },
        {
            "data": [{"id": 2, "name": "John Smith"}],
            "meta": {"paging": {}},
        },
    ]
    calls = []

    def _fake_braces_get(path):
        calls.append(path)
        return pages.pop(0)

    monkeypatch.setattr(clio_client, "clio_braces_get", _fake_braces_get)

    rows = clio_matters.clio_list_contacts("id,name,phone_numbers{id,number}")

    assert [r["id"] for r in rows] == [1, 2]
    assert "/contacts.json" in calls[0]
    assert "page_token=abc" in calls[1]
