from __future__ import annotations

import pytest

from jh_clio_lib import config, lawmatics_auth
from jh_clio_lib.exceptions import LawmaticsAuthError


def test_get_lawmatics_token_returns_configured_token(monkeypatch):
    monkeypatch.setattr(config, "LM_ACCESS_TOKEN", "lm-tok")
    assert lawmatics_auth.get_lawmatics_token() == "lm-tok"


def test_get_lawmatics_token_raises_with_actionable_message(monkeypatch):
    monkeypatch.setattr(config, "LM_ACCESS_TOKEN", None)
    with pytest.raises(LawmaticsAuthError, match="bootstrap_env.py"):
        lawmatics_auth.get_lawmatics_token()
