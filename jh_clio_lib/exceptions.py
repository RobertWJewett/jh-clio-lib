"""Exception types raised across jh-clio-lib. Consumers should catch these rather
than bare requests/Firestore exceptions, per each module's fail-loud contract."""
from __future__ import annotations


class ClioAuthError(RuntimeError):
    """Clio token could not be retrieved or refreshed."""


class LawmaticsAuthError(RuntimeError):
    """Lawmatics token missing or invalid; points at the re-mint flow."""


class FieldNotFoundError(KeyError):
    """A human field name has no entry in the current Clio custom-field cache for
    the requested parent_type — never guess, fail loud instead."""


class AmbiguousFieldError(KeyError):
    """A field name resolves to more than one Clio custom-field definition id even
    after filtering by parent_type — a real duplicate in Clio's own field set. Never
    silently pick one."""


class LawmaticsWriteUnconfirmedError(RuntimeError):
    """A Lawmatics PATCH returned HTTP 200 but the GET-verify read-back didn't show
    the expected value — Lawmatics returns 200 on silently-failed writes."""
