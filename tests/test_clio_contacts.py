from __future__ import annotations

from jh_clio_lib import clio_client, clio_contacts


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_create_contact_returns_new_id(monkeypatch):
    captured = {}

    def _fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return _FakeResponse({"data": {"id": 2575659425, "name": "Tina Marie Brown"}})

    monkeypatch.setattr(clio_client, "clio_request", _fake_request)

    result = clio_contacts.clio_create_contact("Tina Marie", "Brown")

    assert result == 2575659425
    assert captured["method"] == "POST"
    assert captured["path"] == "/contacts.json"
    assert captured["json"] == {"data": {"type": "Person", "first_name": "Tina Marie", "last_name": "Brown"}}


def test_update_contact_details_sends_only_provided_fields(monkeypatch):
    captured = {}

    def _fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return _FakeResponse({})

    monkeypatch.setattr(clio_client, "clio_request", _fake_request)

    clio_contacts.clio_update_contact_details(42, phone="555-555-0100")

    assert captured["path"] == "/contacts/42.json"
    assert captured["json"] == {
        "data": {"phone_numbers": [{"name": "Mobile", "number": "555-555-0100", "default_number": True}]}
    }
    # addresses/email_addresses keys must be absent entirely, not just empty —
    # confirmed live that an absent key leaves the existing value untouched.
    assert "addresses" not in captured["json"]["data"]
    assert "email_addresses" not in captured["json"]["data"]


def test_update_contact_details_all_three_fields(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        clio_client, "clio_request",
        lambda method, path, **kw: (captured.update(json=kw.get("json")), _FakeResponse({}))[1],
    )

    clio_contacts.clio_update_contact_details(
        42,
        address={"street": "1 Test Way", "city": "Testville", "province": "TX", "postal_code": "77000"},
        phone="555-555-0100",
        email="w@example.com",
    )

    data = captured["json"]["data"]
    assert data["addresses"] == [{"street": "1 Test Way", "city": "Testville", "province": "TX", "postal_code": "77000"}]
    assert data["phone_numbers"] == [{"name": "Mobile", "number": "555-555-0100", "default_number": True}]
    assert data["email_addresses"] == [{"name": "Home", "address": "w@example.com", "default_email": True}]


def test_update_contact_details_no_op_when_nothing_passed(monkeypatch):
    def _fail(*a, **kw):
        raise AssertionError("should not make an HTTP call with nothing to update")

    monkeypatch.setattr(clio_client, "clio_request", _fail)

    clio_contacts.clio_update_contact_details(42)  # must not raise
