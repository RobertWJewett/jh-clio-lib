from __future__ import annotations

import pytest
import responses

from jh_clio_lib import clio_auth, config
from jh_clio_lib.exceptions import ClioAuthError


def test_get_clio_token_reads_from_firestore(fake_firestore):
    fake_firestore.seed("clio_manage_state", "tokens", {"access_token": "abc123"})
    assert clio_auth.get_clio_token() == "abc123"


def test_get_clio_token_raises_when_no_token_anywhere(fake_firestore, monkeypatch):
    fake_firestore.seed("clio_manage_state", "tokens", {})
    monkeypatch.setattr(clio_auth, "_firestore_tokens_via_gcloud_rest", lambda: {})
    try:
        clio_auth.get_clio_token()
        assert False, "expected ClioAuthError"
    except ClioAuthError:
        pass


def test_get_clio_token_falls_back_to_gcloud_rest(fake_firestore, monkeypatch):
    # Firestore client "succeeds" but the doc has no access_token — should fall
    # through to the gcloud-REST fallback rather than trusting an empty result.
    fake_firestore.seed("clio_manage_state", "tokens", {})
    monkeypatch.setattr(
        clio_auth, "_firestore_tokens_via_gcloud_rest",
        lambda: {"access_token": "from-gcloud", "refresh_token": "r"},
    )
    assert clio_auth.get_clio_token() == "from-gcloud"


@responses.activate
def test_refresh_clio_token_exchanges_and_stores(fake_firestore, monkeypatch):
    monkeypatch.setattr(config, "CLIO_MANAGE_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "CLIO_MANAGE_CLIENT_SECRET", "client-secret")
    fake_firestore.seed(
        "clio_manage_state", "tokens",
        {"access_token": "old", "refresh_token": "refresh-1"},
    )
    responses.add(
        responses.POST, config.CLIO_TOKEN_URL,
        json={"access_token": "new-access", "refresh_token": "refresh-2"},
        status=200,
    )

    new_token = clio_auth.refresh_clio_token()

    assert new_token == "new-access"
    stored = fake_firestore.collection("clio_manage_state").document("tokens").get().to_dict()
    assert stored["access_token"] == "new-access"
    assert stored["refresh_token"] == "refresh-2"


def test_refresh_clio_token_raises_without_client_credentials(fake_firestore, monkeypatch):
    monkeypatch.setattr(config, "CLIO_MANAGE_CLIENT_ID", None)
    monkeypatch.setattr(config, "CLIO_MANAGE_CLIENT_SECRET", None)
    fake_firestore.seed(
        "clio_manage_state", "tokens",
        {"access_token": "old", "refresh_token": "refresh-1"},
    )
    try:
        clio_auth.refresh_clio_token()
        assert False, "expected ClioAuthError"
    except ClioAuthError:
        pass


# --- token-broker mode (2026-10-06) ---------------------------------------------------------------

@responses.activate
def test_broker_mode_returns_access_token_only(monkeypatch):
    monkeypatch.setenv("CLIO_TOKEN_BROKER_URL", "https://broker.example/clio-token-broker")
    monkeypatch.setenv("CLIO_TOKEN_BROKER_KEY", "k")
    responses.add(responses.GET, "https://broker.example/clio-token-broker",
                  json={"access_token": "ACCESS", "updated_at": "x"}, status=200)

    assert clio_auth.get_clio_token() == "ACCESS"
    assert clio_auth.get_tokens()["refresh_token"] == ""
    assert responses.calls[0].request.headers["X-Broker-Key"] == "k"


@responses.activate
def test_broker_mode_wrong_key_raises(monkeypatch):
    monkeypatch.setenv("CLIO_TOKEN_BROKER_URL", "https://broker.example/clio-token-broker")
    monkeypatch.setenv("CLIO_TOKEN_BROKER_KEY", "bad")
    responses.add(responses.GET, "https://broker.example/clio-token-broker", status=404)

    with pytest.raises(ClioAuthError):
        clio_auth.get_clio_token()


@responses.activate
def test_broker_mode_refresh_only_refetches_never_posts(monkeypatch):
    monkeypatch.setenv("CLIO_TOKEN_BROKER_URL", "https://broker.example/clio-token-broker")
    monkeypatch.setenv("CLIO_TOKEN_BROKER_KEY", "k")
    responses.add(responses.GET, "https://broker.example/clio-token-broker",
                  json={"access_token": "NEW"}, status=200)

    assert clio_auth.refresh_clio_token() == "NEW"
    assert all(c.request.method == "GET" for c in responses.calls)   # no OAuth refresh grant, no writes

