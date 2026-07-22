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
