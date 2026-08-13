from __future__ import annotations

from jh_clio_lib import matterkey_index


def test_get_lm_prospect_id_for_matter_found(fake_firestore):
    fake_firestore.seed("clio_matterkey_index", "1863920690", {
        "matterkey": "2026-03-10-13-58-36",
        "display_number": "01748-Solberg",
        "lm_prospect_id": 16245955,
        "lm_prospect_name": "David Solberg",
        "validated": True,
        "updated_at": "2026-08-02T00:00:00Z",
    })

    assert matterkey_index.get_lm_prospect_id_for_matter(1863920690) == 16245955


def test_get_lm_prospect_id_for_matter_no_entry(fake_firestore):
    assert matterkey_index.get_lm_prospect_id_for_matter(999999999) is None


def test_get_lm_prospect_id_for_matter_entry_with_no_prospect(fake_firestore):
    fake_firestore.seed("clio_matterkey_index", "1234567890", {
        "matterkey": "2026-01-01-00-00-00",
        "display_number": "00001-NoLawmaticsLink",
        "lm_prospect_id": None,
        "lm_prospect_name": None,
        "validated": False,
        "updated_at": "2026-08-02T00:00:00Z",
    })

    assert matterkey_index.get_lm_prospect_id_for_matter(1234567890) is None


def test_get_matterkey_index_entry_returns_full_doc(fake_firestore):
    fake_firestore.seed("clio_matterkey_index", "1863920690", {
        "matterkey": "2026-03-10-13-58-36",
        "lm_prospect_id": 16245955,
    })

    entry = matterkey_index.get_matterkey_index_entry(1863920690)

    assert entry == {"matterkey": "2026-03-10-13-58-36", "lm_prospect_id": 16245955}
