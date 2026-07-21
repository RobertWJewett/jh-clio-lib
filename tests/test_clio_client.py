from __future__ import annotations

import http.client

import responses

from jh_clio_lib import clio_auth, clio_client, config


class _FakeResponse:
    def __init__(self, status, body=b'{"data": {"id": 1}}', headers=None):
        self.status = status
        self._body = body
        self._headers = headers or {}

    def read(self):
        return self._body

    def getheader(self, name):
        return self._headers.get(name)


class _FakeConn:
    """Queue of responses/exceptions returned by successive getresponse() calls —
    stands in for http.client.HTTPSConnection since `responses` only mocks `requests`,
    not raw http.client (why clio_braces_get had no test coverage before 2026-07-21)."""

    queue: list = []

    def __init__(self, *_args, **_kwargs):
        pass

    def request(self, *_args, **_kwargs):
        pass

    def getresponse(self):
        item = _FakeConn.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


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


def test_clio_braces_get_success(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "tok")
    _FakeConn.queue = [_FakeResponse(200)]
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConn)

    assert clio_client.clio_braces_get("/matters/1.json") == {"data": {"id": 1}}


def test_clio_braces_get_retries_429_honoring_retry_after(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "tok")
    sleeps = []
    monkeypatch.setattr(clio_client.time, "sleep", lambda s: sleeps.append(s))
    _FakeConn.queue = [
        _FakeResponse(429, body=b"", headers={"Retry-After": "14"}),
        _FakeResponse(200),
    ]
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConn)

    result = clio_client.clio_braces_get("/matters/1.json")

    assert result == {"data": {"id": 1}}
    assert sleeps == [14.0]


def test_clio_braces_get_retries_connection_error(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "tok")
    monkeypatch.setattr(clio_client.time, "sleep", lambda *_: None)
    _FakeConn.queue = [TimeoutError("handshake timed out"), _FakeResponse(200)]
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConn)

    assert clio_client.clio_braces_get("/matters/1.json") == {"data": {"id": 1}}


def test_clio_braces_get_refreshes_once_on_401(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "stale-tok")
    refreshed = {"called": False}
    monkeypatch.setattr(clio_auth, "refresh_clio_token", lambda: refreshed.update(called=True))
    _FakeConn.queue = [_FakeResponse(401, body=b""), _FakeResponse(200)]
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConn)

    assert clio_client.clio_braces_get("/matters/1.json") == {"data": {"id": 1}}
    assert refreshed["called"] is True


def test_clio_braces_get_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(clio_auth, "get_clio_token", lambda: "tok")
    monkeypatch.setattr(clio_client.time, "sleep", lambda *_: None)
    _FakeConn.queue = [_FakeResponse(503, body=b"down") for _ in range(4)]
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConn)

    try:
        clio_client.clio_braces_get("/matters/1.json")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "503" in str(e)
