"""TenderNed — probed, and it does NOT do what the survey assumed. Recorded here as a negative.

T26 §7 day-1 proposed using "the winning-supplier names in the 2,214 awards we already hold" as a
second candidate population. Probed on 2026-08-19 against the free, unauthenticated public API:

    GET https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties            -> 200
    GET https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties/{id}       -> 200

The list response carries `aanbestedingNaam`, `opdrachtgeverNaam` (the *contracting authority*),
`typePublicatie`, `opdrachtBeschrijving`, CPV codes and a publication link. The detail response adds
`cpvCodes`, `nutsCodes`, `isGegund`, `publicatiePdfId` — and still **no awarded-supplier field**.
The winning supplier's name is inside the award PDF, not the JSON.

So TenderNed cannot supply a supplier population without PDF parsing, which is a separate build with
its own accuracy risk. What it *can* supply for free, today, is a **demand signal**: which public
bodies are buying software and data work right now, and in which municipality. That is useful for
prioritising a region and for mechanism #3 in the survey, and it is what this module exposes.

The correction matters more than the feature: the survey's day-1 plan named a source that does not
contain the field it needed, and that would have been discovered after building on it.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ..http_client import PoliteClient

PUBLICATIES = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"

ICT_KEYWORDS = (
    "software",
    "applicatie",
    "ict",
    "informatievoorziening",
    "data",
    "platform",
    "digitalisering",
    "webapplicatie",
    "koppelvlak",
    "api",
    "cloud",
    "algoritme",
)

# CPV division 72 = IT services, 48 = software packages.
ICT_CPV_PREFIXES = ("72", "48")


def fetch_publications(client: PoliteClient, *, pages: int = 2, size: int = 100) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(pages):
        url = f"{PUBLICATIES}?page={page}&size={size}"
        status, payload = client.get(url, note=f"tenderned page {page}")
        if status != 200 or not isinstance(payload, dict):
            break
        content = payload.get("content") or []
        out.extend(content)
        if len(content) < size:
            break
    return out


def ict_demand_signal(publications: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the free stream into 'who is buying software work, where'."""
    hits = []
    for pub in publications:
        text = " ".join(
            str(pub.get(k) or "")
            for k in ("aanbestedingNaam", "opdrachtBeschrijving")
        ).lower()
        if any(kw in text for kw in ICT_KEYWORDS):
            hits.append(
                {
                    "publicatieId": pub.get("publicatieId"),
                    "naam": pub.get("aanbestedingNaam"),
                    "opdrachtgever": pub.get("opdrachtgeverNaam"),
                    "datum": pub.get("publicatieDatum"),
                    "type": (pub.get("typePublicatie") or {}).get("omschrijving"),
                    "url": (pub.get("link") or {}).get("href"),
                }
            )
    buyers: dict[str, int] = {}
    for hit in hits:
        key = hit["opdrachtgever"] or "onbekend"
        buyers[key] = buyers.get(key, 0) + 1
    return {
        "publications_seen": len(publications),
        "ict_matches": len(hits),
        "top_buyers": sorted(buyers.items(), key=lambda kv: -kv[1])[:15],
        "sample": hits[:10],
        "observed_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def supplier_field_probe(client: PoliteClient, publication_id: str | int) -> dict[str, Any]:
    """Demonstrate the negative: list the detail fields and show no supplier name is among them."""
    status, payload = client.get(f"{PUBLICATIES}/{publication_id}", note="tenderned detail probe")
    fields = sorted(payload.keys()) if isinstance(payload, dict) else []
    supplier_like = [
        f
        for f in fields
        if any(t in f.lower() for t in ("opdrachtnemer", "winnaar", "leverancier", "gegunde", "inschrijver"))
    ]
    return {
        "publication_id": publication_id,
        "status": status,
        "detail_fields": fields,
        "supplier_name_fields_found": supplier_like,
        "conclusion": (
            "no awarded-supplier name in the JSON; it exists only in the publication PDF"
            if not supplier_like
            else "supplier-like fields present; re-open the survey's day-1 plan"
        ),
    }
