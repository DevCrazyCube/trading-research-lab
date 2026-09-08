"""The ethical spine, enforced mechanically instead of promised in prose.

The rule from the survey: *a briefing may say "u komt mogelijk in aanmerking — hier is het publieke
bewijs", and may never say "u komt in aanmerking".* A rule that lives only in a template is one
careless edit from being broken, and the person who would find out is a stranger receiving a false
claim about their tax position. So it lives here, as a linter that the dry-run runs over every
generated briefing and that fails the run on any violation.

Four checks:

1. **Forbidden assertions** — eligibility claims, guarantees, fee-free promises, urgency pressure.
2. **Required disclosures** — the "mogelijk" hedge, an explicit no-advice line, the RVO link so the
   reader can do it without us, the assumption marker, and a working opt-out.
3. **Every company-specific claim carries a URL** the reader can open.
4. **No unsourced specifics** — every github.com/peppol URL printed in the briefing must appear in
   that candidate's evidence records. This is the anti-fabrication check: it makes it impossible to
   name a repository the scanner never saw.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any, Iterable

# (key, pattern, why it is forbidden)
FORBIDDEN: tuple[tuple[str, str, str], ...] = (
    ("stelt_eligibility_vast", r"\bu\s+(komt|voldoet)\b(?!.{0,40}\bmogelijk\b)(?=.{0,40}\b(in aanmerking|aan de voorwaarden)\b)",
     "asserts eligibility; only RVO decides"),
    ("kwalificeert", r"\b(u|uw bedrijf|uw onderneming)\s+kwalificeer\w*", "asserts eligibility"),
    ("recht_op", r"\bu\s+(heeft|hebt|hebben)\s+recht\s+op\b", "asserts entitlement"),
    ("u_ontvangt", r"\bu\s+(ontvangt|krijgt)\s+(€|EUR)\s*\d", "promises a payment"),
    ("bedraagt", r"\buw\s+wbso-voordeel\s+(bedraagt|is)\b", "states an estimate as fact"),
    ("gegarandeerd", r"\bgegarandeer\w*|\bgarantie\b|\bwij garanderen\b", "guarantee language"),
    ("zeker", r"\b(zeker|gegarandeerd|100%)\s+(recht|voordeel|toegekend|goedgekeurd)\b", "certainty language"),
    ("wij_regelen", r"\bwij\s+regelen\s+(uw|je)\s+(subsidie|wbso|aanvraag)\b",
     "implies the outcome is ours to deliver"),
    ("namens_rvo", r"\b(namens|in opdracht van|vanuit)\s+(rvo|de belastingdienst|de overheid)\b",
     "implies government affiliation"),
    ("laatste_kans", r"\b(laatste kans|nu of nooit|mis dit niet|handel snel|beperkte plaatsen)\b",
     "false urgency"),
    ("gratis_geld", r"\bgratis geld\b|\bkosteloos \d+ ?(k|duizend)\b", "misrepresents a tax credit"),
    ("en_you_qualify", r"\byou (qualify|are eligible)\b", "asserts eligibility (EN)"),
    ("en_guaranteed", r"\bguaranteed\b", "guarantee language (EN)"),
)

# (key, pattern, why it must be present)
REQUIRED: tuple[tuple[str, str, str], ...] = (
    ("mogelijk_hedge", r"\bmogelijk\s+in\s+aanmerking\b", "the MAY-qualify hedge must be explicit"),
    ("geen_toezegging", r"\bgeen\s+(toezegging|advies|beoordeling)\b",
     "must state this is not advice or a decision"),
    ("rvo_link", r"https://www\.rvo\.nl/", "reader must be able to go to the authority directly"),
    ("zelf_doen", r"\bzelf\s+(aanvragen|indienen|doen)\b",
     "must tell the reader they can do this without us"),
    ("aanname", r"\baanname[n]?\b", "every euro figure must be labelled as resting on assumptions"),
    ("onzekerheid", r"\bwat wij niet (weten|kunnen zien)\b", "the uncertainty section must exist"),
    ("afmelden", r"\bafmeld\w*|\bgeen e-?mail meer\b", "a working opt-out must be offered"),
    ("afzender", r"\bAfzender\b", "sender identity block must be present"),
)

URL_RE = re.compile(r"https?://[^\s)\]<>\"']+")
EVIDENCE_BLOCK = re.compile(r"(?s)<!--EVIDENCE-START-->(.*?)<!--EVIDENCE-END-->")


@dataclasses.dataclass
class LintResult:
    ok: bool
    violations: list[dict[str, str]]
    missing: list[dict[str, str]]
    unsourced_urls: list[str]
    unlinked_claims: list[str]

    def summary(self) -> str:
        if self.ok:
            return "clean"
        bits = []
        if self.violations:
            bits.append(f"{len(self.violations)} forbidden")
            bits.append("(" + ", ".join(v["key"] for v in self.violations) + ")")
        if self.missing:
            bits.append(f"{len(self.missing)} missing: " + ", ".join(m["key"] for m in self.missing))
        if self.unsourced_urls:
            bits.append(f"{len(self.unsourced_urls)} unsourced urls")
        if self.unlinked_claims:
            bits.append(f"{len(self.unlinked_claims)} unlinked claims")
        return "; ".join(bits)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def lint_briefing(text: str, *, evidence_urls: Iterable[str] = ()) -> LintResult:
    low = text.lower()
    violations = [
        {"key": key, "why": why, "match": m.group(0)[:80]}
        for key, pattern, why in FORBIDDEN
        if (m := re.search(pattern, low, re.IGNORECASE | re.DOTALL))
    ]
    missing = [
        {"key": key, "why": why}
        for key, pattern, why in REQUIRED
        if not re.search(pattern, text, re.IGNORECASE)
    ]

    allowed = {u.rstrip("/.,") for u in evidence_urls}
    unsourced: list[str] = []
    for url in URL_RE.findall(text):
        clean = url.rstrip("/.,")
        host = clean.split("/")[2] if clean.count("/") >= 2 else ""
        # Public reference sites are allowed unconditionally; company-specific URLs are not.
        if host in ("www.rvo.nl", "rvo.nl", "english.rvo.nl", "mijn.rvo.nl", "www.kvk.nl", "kvk.nl"):
            continue
        if clean not in allowed:
            unsourced.append(clean)

    unlinked: list[str] = []
    block = EVIDENCE_BLOCK.search(text)
    if block:
        for line in block.group(1).splitlines():
            stripped = line.strip()
            if stripped.startswith(("-", "*", "1.")) and not URL_RE.search(stripped):
                unlinked.append(stripped[:100])
    else:
        unlinked.append("NO EVIDENCE BLOCK MARKERS FOUND")

    ok = not (violations or missing or unsourced or unlinked)
    return LintResult(ok, violations, missing, unsourced, unlinked)
