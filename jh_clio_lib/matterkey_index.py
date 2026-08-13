"""Reader for the shared `clio_matterkey_index` Firestore collection — built
nightly by `email-processor/deploy_matterkey_index/build_matterkey_lm_index.py`,
the cheap way to resolve a Clio matter id to its Lawmatics prospect id without
paying Lawmatics' full-prospects-page-and-match cost (MatterKey.md §6a).

Caveat: only as fresh as last night's run — a matter/prospect pairing created
today won't appear until tomorrow's run. Callers needing same-day freshness
must tolerate the delay rather than treat a miss here as "no Lawmatics record."
"""
from __future__ import annotations

from jh_clio_lib import config

_COLLECTION = "clio_matterkey_index"


def get_matterkey_index_entry(clio_matter_id: int) -> dict | None:
    """Raw index doc: {matterkey, display_number, lm_prospect_id, lm_prospect_name,
    validated, updated_at}, or None if this matter has no entry yet."""
    from google.cloud import firestore

    db = firestore.Client(project=config.GCP_PROJECT)
    doc = db.collection(_COLLECTION).document(str(clio_matter_id)).get()
    return doc.to_dict() if doc.exists else None


def get_lm_prospect_id_for_matter(clio_matter_id: int) -> int | None:
    """The Lawmatics prospect id linked to this Clio matter, per the nightly
    index — None if there's no entry yet (new pairing since last night's run)
    or the entry exists but has no linked prospect (a Clio-only matter with no
    Lawmatics record)."""
    entry = get_matterkey_index_entry(clio_matter_id)
    if entry is None:
        return None
    return entry.get("lm_prospect_id")
