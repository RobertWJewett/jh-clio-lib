"""Core Clio Manage request wrapper: bearer auth, refresh-once-and-retry on 401, and
exponential backoff on transient failures (4 attempts, per the retry policy proven in
production email-processor/ClioMCP code — connection errors and 429/502/503/504).
Model: ClioMCP/firm_data/clio_client.py's module-scoped _request(), generalized with
the broader retry policy the design brief calls for.
"""
from __future__ import annotations

import http.client
import json
import time

import requests

from jh_clio_lib import clio_auth, config

_MAX_ATTEMPTS = 4
_RETRYABLE_STATUS = {429, 502, 503, 504}


def clio_braces_get(path_with_query: str, *, _retry: bool = True) -> dict:
    """GET via http.client directly — `requests` percent-encodes `{`/`}`, which Clio's
    field sub-selection syntax (e.g. custom_field_values{id,value,custom_field}) needs
    literal. Ported from ClioMCP/firm_data/clio_client.py:_braces_get. `path_with_query`
    is relative to the API root (no /api/v4 prefix — added here).

    Retries 429/502/503/504 with backoff (honoring a Retry-After header if Clio sends
    one, e.g. its 429 "Rate limit of 50 exceeded" response), and retries connection-
    level failures (timeouts, dropped connections) the same way `clio_request()`
    already does — added 2026-07-21 when a bulk per-client Contact fetch
    (clio-hotstrings populate script, ~1500 contacts) hit both a 429 with no retry and,
    once that was fixed, an unhandled SSL handshake timeout partway through."""
    full_path = f"/api/v4{path_with_query}"
    for attempt in range(_MAX_ATTEMPTS):
        token = clio_auth.get_clio_token()
        conn = http.client.HTTPSConnection("app.clio.com", timeout=15)
        try:
            try:
                conn.request("GET", full_path, headers={"Authorization": f"Bearer {token}"})
                resp = conn.getresponse()
                body = resp.read()
                status = resp.status
                retry_after = resp.getheader("Retry-After")
            except OSError:
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        finally:
            conn.close()

        if status == 401 and _retry:
            clio_auth.refresh_clio_token()
            return clio_braces_get(path_with_query, _retry=False)
        if status in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
            time.sleep(float(retry_after) if retry_after else 2 ** attempt)
            continue
        if status >= 400:
            raise RuntimeError(f"Clio GET {path_with_query} -> {status}: {body[:500]!r}")
        return json.loads(body)


def clio_request(method: str, path: str, **kwargs) -> requests.Response:
    url = path if path.startswith("http") else f"{config.CLIO_BASE}{path}"
    caller_headers = kwargs.pop("headers", {}) or {}
    timeout = kwargs.pop("timeout", 20)
    refreshed = False
    resp: requests.Response | None = None

    for attempt in range(_MAX_ATTEMPTS):
        headers = dict(caller_headers)
        headers["Authorization"] = f"Bearer {clio_auth.get_clio_token()}"
        try:
            resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, OSError):
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(2 ** attempt)
                continue
            raise

        if resp.status_code == 401 and not refreshed:
            clio_auth.refresh_clio_token()
            refreshed = True
            continue
        if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
            time.sleep(2 ** attempt)
            continue
        return resp

    return resp
