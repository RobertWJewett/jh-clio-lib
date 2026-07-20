"""Lawmatics token access — a static long-lived token, not a refresh-grant flow.
The Lawmatics OAuth app supports ONLY authorization_code; client_credentials and
refresh_token both return unsupported_grant_type — there is no refresh token
(ClioLearningLog.md §7)."""
from __future__ import annotations

from jh_clio_lib import config
from jh_clio_lib.exceptions import LawmaticsAuthError


def get_lawmatics_token() -> str:
    token = config.LM_ACCESS_TOKEN
    if not token:
        raise LawmaticsAuthError(
            "LM_ACCESS_TOKEN not found in ~/.env.jh. First try "
            "`python jh-law-scripts/tools/bootstrap_env.py` to re-pull it from Secret "
            "Manager. If the token itself is invalid/expired (no auto-refresh exists), "
            "re-mint via `python jh-law-scripts/lm/lawmatics_auth.py` (one-time OAuth "
            "flow), update the `lawmatics-access-token` Secret Manager secret with the "
            "new value, then re-run bootstrap_env.py."
        )
    return token
