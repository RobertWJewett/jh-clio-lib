"""Contact creation/update — confirmed live 2026-09-26 (ClioLearningLog.md §14),
not guessed. First write-capable module for Contacts in this library (everything
else here either reads Contacts or writes Matter/Prospect custom fields).
"""
from __future__ import annotations

from jh_clio_lib import clio_client


def clio_create_contact(first_name: str, last_name: str, *, type_: str = "Person") -> int:
    """POST /contacts.json -> 201 with a new contact id. No dedup/search here —
    callers deciding whether to reuse an existing contact instead must search
    first (see clio_matters.clio_list_resource / the existing clio_list_contacts
    with a `query` filter) and only call this once they've decided a new
    Contact is actually needed."""
    resp = clio_client.clio_request(
        "POST", "/contacts.json",
        json={"data": {"type": type_, "first_name": first_name, "last_name": last_name}},
    )
    resp.raise_for_status()
    return resp.json()["data"]["id"]


def clio_update_contact_details(
    contact_id: int, *, address: dict | None = None, phone: str | None = None, email: str | None = None,
) -> None:
    """PATCH /contacts/{id}.json — set address/phone/email, one call for
    whichever of the three are passed. Confirmed live that Clio's PATCH only
    touches the top-level keys actually present in the body — omitting
    `addresses` entirely leaves a contact's existing address untouched, it
    is NOT wiped by a PATCH that only sets `phone_numbers` — so a caller
    filling in just the currently-blank fields on an existing contact can
    pass only those, without first reading and re-sending the others.
    `address` is a single dict with Clio's own address field names (street/
    city/province/postal_code/name) — this always sends exactly one address
    entry, replacing the WHOLE addresses array for the contact (same for
    phone/email) — not additive, and not a merge with any existing entries
    in that specific array. No-op (no HTTP call at all) if all three are
    None."""
    data: dict = {}
    if address is not None:
        data["addresses"] = [address]
    if phone is not None:
        data["phone_numbers"] = [{"name": "Mobile", "number": phone, "default_number": True}]
    if email is not None:
        data["email_addresses"] = [{"name": "Home", "address": email, "default_email": True}]
    if not data:
        return
    resp = clio_client.clio_request("PATCH", f"/contacts/{contact_id}.json", json={"data": data})
    resp.raise_for_status()
