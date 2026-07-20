from __future__ import annotations

import responses

from jh_clio_lib import clio_auth, clio_client, config


@responses.activate
def test_clio_request_success(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "tok")
    responses.add(
        responses.GET, f"{config.CLIO_BASE}/matters/1.json",
        json={"data": {"id": 1}}, status=200,
    )

    resp = clio_client.clio_request("GET", "/matters/1.json")

    assert resp.status_code == 200
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"


@responses.activate
def test_clio_request_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "tok")
    monkeypatch.setattr(clio_client.time, "sleep", lambda *_: None)
    responses.add(responses.GET, f"{config.CLIO_BASE}/matters/1.json", status=429)
    responses.add(
        responses.GET, f"{config.CLIO_BASE}/matters/1.json",
        json={"data": {"id": 1}}, status=200,
    )

    resp = clio_client.clio_request("GET", "/matters/1.json")

    assert resp.status_code == 200
    assert len(responses.calls) == 2


@responses.activate
def test_clio_request_refreshes_once_on_401(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "stale-tok")
    refreshed = {"called": False}

    def _refresh():
        refreshed["called"] = True

    monkeypatch.setattr(clio_auth, "refresh_clio_token", _refresh)
    responses.add(responses.GET, f"{config.CLIO_BASE}/matters/1.json", status=401)
    responses.add(
        responses.GET, f"{config.CLIO_BASE}/matters/1.json",
        json={"data": {"id": 1}}, status=200,
    )

    resp = clio_client.clio_request("GET", "/matters/1.json")

    assert resp.status_code == 200
    assert refreshed["called"] is True
    assert len(responses.calls) == 2


@responses.activate
def test_clio_request_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "tok")
    monkeypatch.setattr(clio_client.time, "sleep", lambda *_: None)
    for _ in range(4):
        responses.add(responses.GET, f"{config.CLIO_BASE}/matters/1.json", status=503)

    resp = clio_client.clio_request("GET", "/matters/1.json")

    assert resp.status_code == 503
    assert len(responses.calls) == 4
