"""Peppol Directory: a free, unauthenticated route to Dutch legal-entity identifiers.

**What this fixes.** T26 §2 recorded the Peppol directory as "200 but 0 matches on our query
syntax" and treated the KVK paywall as a hard wall. The working syntax is
`https://directory.peppol.eu/search/1.0/json?q=<name>&rpc=<n>` (or `country=NL`), probed
2026-08-19: 112,674 NL participants, and each match carries a `participantID` such as
`0106:14075247` or `9944:nl001675801b01`.

Those prefixes are ISO 6523 ICDs, and OpenPeppol's own published code list
(`Peppol Code Lists - Participant identifier schemes v9.7`, fetched 2026-08-19) says:
`0106 = NL:KVK` (Dutch Chamber of Commerce number) and `9944 = NL:VAT`. So a match gives a real,
publicly registered Dutch business identifier without paying for KVK access.

**The honest limits, which are large.**
* Coverage is partial: only organisations that registered for Peppol e-invoicing appear at all,
  which skews to firms that invoice government or larger customers.
* The match is on a *name string*. "Nedap" matched a Belgian entity before a Dutch one in our probe.
  A name match is therefore corroboration for the operator's own checking, never an identity claim.

Because of the second limit this module's output is marked `verify_before_use=True` and the briefing
generator is forbidden from printing a KVK number to the recipient. It goes in the owner's dossier
with "verify at kvk.nl before you rely on this" attached.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Any

from ..http_client import PoliteClient
from ..model import Evidence, now_utc

SEARCH = "https://directory.peppol.eu/search/1.0/json"
KVK_SCHEME = "0106"
VAT_SCHEME = "9944"

# Legal-form and filler tokens dropped before comparing names. "Acme B.V." and "Acme" are the same
# company; "Acme Software" and "Acme Logistics" are not, so only these are dropped.
LEGAL_TOKENS = frozenset(
    {"bv", "b.v", "nv", "n.v", "vof", "cv", "holding", "group", "groep", "the", "de", "het"}
)


def normalise(name: str) -> str:
    """Fold a company name to its comparable core.

    Dots are deleted rather than turned into spaces, so "Voorbeeld B.V." collapses to
    "voorbeeld bv" and the legal-form token can then be dropped. Turning them into spaces would
    leave "b" and "v" as separate tokens and "Voorbeeld B.V." would never match "Voorbeeld".
    """
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().replace("&", " en ")
    name = re.sub(r"[.'’`]", "", name)
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    tokens = [t for t in name.split() if t and t not in LEGAL_TOKENS]
    return " ".join(tokens)


def lookup(client: PoliteClient, name: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Name search against the public directory. Returns raw matches (may be empty)."""
    url = f"{SEARCH}?q={urllib.parse.quote(name)}&rpc={limit}"
    status, payload = client.get(url, note=f"peppol {name}")
    if status != 200 or not isinstance(payload, dict):
        return []
    return list(payload.get("matches") or [])


def best_nl_match(matches: list[dict[str, Any]], query_name: str) -> dict[str, Any] | None:
    """Pick the single NL entity whose normalised name equals the query's. Exact or nothing.

    Fuzzy matching here would manufacture identity claims out of coincidence, and the cost of a
    wrong KVK number in front of a stranger is far higher than the cost of a missed match.
    """
    target = normalise(query_name)
    if not target:
        return None
    for match in matches:
        for entity in match.get("entities") or []:
            if (entity.get("countryCode") or "").upper() != "NL":
                continue
            for name_row in entity.get("name") or []:
                if normalise(name_row.get("name") or "") == target:
                    pid = match.get("participantID") or {}
                    scheme, _, value = str(pid.get("value", "")).partition(":")
                    return {
                        "participant_id": pid.get("value"),
                        "scheme": scheme,
                        "identifier": value,
                        "is_kvk": scheme == KVK_SCHEME,
                        "is_vat": scheme == VAT_SCHEME,
                        "entity_name": name_row.get("name"),
                        "country": "NL",
                        "reg_date": entity.get("regDate"),
                        "verify_before_use": True,
                    }
    return None


def attach_evidence(cand, match: dict[str, Any]) -> None:
    """Record the match as *corroboration*. Deliberately worded as 'an entity with this name'."""
    scheme_nl = "KVK-nummer" if match["is_kvk"] else ("btw-identificatie" if match["is_vat"] else "identificatie")
    cand.signals["peppol_match"] = match
    cand.add(
        Evidence(
            source="peppol",
            kind="nl_entity_corroboration",
            claim_nl=(
                f"In de openbare Peppol Directory staat een Nederlandse organisatie met de naam "
                f"“{match['entity_name']}” geregistreerd voor e-facturatie ({scheme_nl}). "
                "Wij hebben niet geverifieerd dat dit dezelfde organisatie is."
            ),
            url=f"https://directory.peppol.eu/participant/{urllib.parse.quote(str(match['participant_id']))}",
            observed_utc=now_utc(),
            detail={k: v for k, v in match.items() if k != "identifier"},
        )
    )


def probe(client: PoliteClient) -> dict[str, Any]:
    """Reproduce the availability probe: how many NL participants the directory holds today."""
    status, payload = client.get(f"{SEARCH}?country=NL&rpc=1", note="peppol probe")
    return {
        "endpoint": f"{SEARCH}?country=NL",
        "status": status,
        "nl_participants": (payload or {}).get("total-result-count") if isinstance(payload, dict) else None,
        "observed_utc": now_utc(),
    }
