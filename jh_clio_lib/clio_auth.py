"""Clio Manage OAuth token access — Firestore-first (Gen 2 credential model), with a
local gcloud-CLI fallback for a machine where the google-cloud-firestore client can't
initialize. Ported from ClioMCP/firm_data/clio_auth.py (itself ported from
email-processor's lawpay_connector/_env.py:clio_token() and
audit_matterkey.py:load_clio_token()).

Do NOT read the Secret Manager secret `clio-access-token` — it's refreshed only
~every 25 days and is stale most of the time (ClioLearningLog.md §1). The live token
lives in Firestore clio_manage_state/tokens, kept fresh by the refresh-on-401 logic
in clio_client.py (and, out-of-band, the refresh-clio-manage-token scheduler used by
Cloud Run services).
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from datetime import datetime, timezone

import requests

from jh_clio_lib import config
from jh_clio_lib.exceptions import ClioAuthError

_TOKENS_COLLECTION = "clio_manage_state"
_TOKENS_DOC = "tokens"


def _firestore_tokens() -> dict:
    from google.cloud import firestore

    db = firestore.Client(project=config.GCP_PROJECT)
    doc = db.collection(_TOKENS_COLLECTION).document(_TOKENS_DOC).get()
    return doc.to_dict() or {}


def _firestore_tokens_via_gcloud_rest() -> dict:
    """Local fallback when the Firestore client library can't initialize: use a
    gcloud-minted access token against the Firestore REST API directly."""
    g = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, timeout=15, check=True,
    ).stdout.strip()
    url = (
        f"https://firestore.googleapis.com/v1/projects/{config.GCP_PROJECT}"
        f"/databases/(default)/documents/{_TOKENS_COLLECTION}/{_TOKENS_DOC}"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {g}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode())
    fields = body.get("fields", {})
    return {
        "access_token": fields.get("access_token", {}).get("stringValue", ""),
        "refresh_token": fields.get("refresh_token", {}).get("stringValue", ""),
    }


def _store_tokens(access_token: str, refresh_token: str) -> None:
    """Write refreshed tokens back to Firestore so other Gen-2 services benefit too."""
    try:
        from google.cloud import firestore

        db = firestore.Client(project=config.GCP_PROJECT)
        db.collection(_TOKENS_COLLECTION).document(_TOKENS_DOC).set({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not write refreshed Clio token back to Firestore: {exc}")


# ---------------------------------------------------------------------------
# Token-broker mode (2026-10-06): a host OUTSIDE Google Cloud (e.g. a Railway standby job) cannot reach
# Firestore without a Google credential. Instead it asks a small authenticated endpoint on email-processor
# for the current ACCESS token only -- never the refresh token, and nothing is ever written back. Enabled
# only when BOTH CLIO_TOKEN_BROKER_URL and CLIO_TOKEN_BROKER_KEY are set; otherwise behavior is unchanged.
# ---------------------------------------------------------------------------

def _broker_configured() -> bool:
    return bool(config.get("CLIO_TOKEN_BROKER_URL") and config.get("CLIO_TOKEN_BROKER_KEY"))


def _broker_tokens() -> dict:
    resp = requests.get(config.get("CLIO_TOKEN_BROKER_URL"),
                        headers={"X-Broker-Key": config.get("CLIO_TOKEN_BROKER_KEY")}, timeout=15)
    if resp.status_code != 200:
        raise ClioAuthError(f"Clio token broker returned HTTP {resp.status_code}")
    access = (resp.json() or {}).get("access_token", "")
    if not access:
        raise ClioAuthError("Clio token broker returned no access_token")
    return {"access_token": access, "refresh_token": ""}


def get_tokens() -> dict:
    if _broker_configured():
        return _broker_tokens()
    try:
        tokens = _firestore_tokens()
        if tokens.get("access_token"):
            return tokens
    except Exception:
        pass
    return _firestore_tokens_via_gcloud_rest()


def get_clio_token() -> str:
    tokens = get_tokens()
    token = tokens.get("access_token", "")
    if not token:
        raise ClioAuthError(
            "Clio access_token not found in Firestore clio_manage_state/tokens "
            "(tried ADC and gcloud-REST fallback)."
        )
    return token


def refresh_clio_token() -> str:
    """Exchange the stored refresh_token for a fresh access_token. Ported from
    email-processor/main.py:_refresh_clio_manage_token().

    In broker mode there is no refresh token here (by design): this just re-fetches the broker's current
    access token, which picks up a refresh done elsewhere (the Cloud Run side owns refreshing)."""
    if _broker_configured():
        return _broker_tokens()["access_token"]
    tokens = get_tokens()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise ClioAuthError("No Clio refresh_token available in Firestore.")
    if not config.CLIO_MANAGE_CLIENT_ID or not config.CLIO_MANAGE_CLIENT_SECRET:
        raise ClioAuthError(
            "CLIO_MANAGE_CLIENT_ID/CLIO_MANAGE_CLIENT_SECRET not set — "
            "run jh-law-scripts/tools/bootstrap_env.py to refresh ~/.env.jh."
        )
    resp = requests.post(
        config.CLIO_TOKEN_URL,
        data={
            "client_id": config.CLIO_MANAGE_CLIENT_ID,
            "client_secret": config.CLIO_MANAGE_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    new_access = data.get("access_token")
    new_refresh = data.get("refresh_token") or refresh_token
    if not new_access:
        raise ClioAuthError(f"Clio refresh grant returned no access_token: {data}")
    _store_tokens(new_access, new_refresh)
    return new_access
