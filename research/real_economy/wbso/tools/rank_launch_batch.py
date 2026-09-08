"""Rank the kept candidates into a launch-ready batch, and write LAUNCH_BATCH.md.

**What this is, and what it is not.** The `wbso` package's own `score` ranks a candidate by how much
public *evidence* the scanner collected. That is the right thing for the scanner to optimise and the
wrong thing for the owner to read a list by, because the owner's question is different: *which of
these do I open first, and which do I look at twice before my name goes on it?*

So this tool re-reads the same scan output — it fetches nothing, changes no exclusion rule, and
touches no file the `wbso` package owns — and projects each kept candidate onto three axes the owner
actually decides on:

    E  evidence strength   how much checkable public R&D evidence the briefing can point at
    C  contactability      can this be reached today, at a business address, without more work
    W  WBSO-fit            does this look like a Dutch *company with payroll*, not a hobby or an
                           institution — the two things RVO's conditions turn on that a repository
                           cannot show

**None of these is a claim about eligibility.** W is a fit-with-the-scheme triage number, not a
prediction of an RVO decision; a high W candidate can be rejected and a low W candidate can qualify.
The whole point of the ethical spine is that only RVO decides, and nothing here moves that line.

**The owner-review flag is deliberately one-directional.** It can add scrutiny to a candidate; it can
never remove a scanner exclusion. A candidate excluded by `wbso.scanner` never reaches this file.

    python -m tools.rank_launch_batch --batch-size 25 --today 2026-08-19
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wbso.scanner import EDUCATION_TITLE_PATTERNS, read_candidates  # noqa: E402
from wbso.model import Candidate  # noqa: E402

# A registered legal form in the *name* is the cheapest public signal that there is an entity with a
# payroll behind the repositories. Matched on the profile name only, never on the login: "codarBV"
# as a login says nothing, "Codar B.V." as a self-declared profile name does.
LEGAL_FORM_RE = re.compile(
    r"(\bb\.?\s?v\.?\b|\bn\.?\s?v\.?\b|\bv\.?o\.?f\.?\b|\bholding\b|\bgroep\b|\bgroup\b"
    r"|\bcv\b|\bcoöperatie\b|\bcooperatie\b)",
    re.IGNORECASE,
)

# Words that make an organisation likely to be a community, a foundation or a volunteer project.
# The scanner already *excludes* the unambiguous ones (vereniging, scouting, hackerspace, ...). These
# softer ones cannot justify an exclusion — plenty of real firms say "collective" — so they raise an
# owner-review flag instead. The live runs found exactly this class: a volunteer badge community that
# passes every mechanical rule a small software firm passes.
COMMUNITY_HINT_RE = re.compile(
    r"(\bcommunity\b|\bcollective\b|\bfoundation\b|\bstichting\b|\bvrijwillig\w*|\bnon-?profit\b"
    r"|\bopen ?collective\b|\bbadge\b|\bhobby\b)",
    re.IGNORECASE,
)

# A role address is a business inbox and carries no personal data. A first-name address is both a
# GDPR question and usually the wrong recipient for a tax-scheme letter.
ROLE_LOCALPARTS = {
    "info", "hello", "contact", "support", "team", "office", "sales", "mail", "admin",
    "hi", "welcome", "help", "service", "servicedesk", "kantoor", "opensource", "webteam",
    "development", "dev", "it", "post", "bureau", "aanvraag",
}

EDU_RES = tuple(re.compile(p, re.IGNORECASE) for p in EDUCATION_TITLE_PATTERNS)


def _days_since(iso: str | None, today_iso: str) -> int | None:
    if not iso:
        return None
    try:
        a = dt.date.fromisoformat(iso[:10])
        b = dt.date.fromisoformat(today_iso[:10])
    except ValueError:
        return None
    return (b - a).days


def _host(url: str | None) -> str:
    if not url:
        return ""
    return urllib.parse.urlsplit(url).netloc.lower().split(":")[0].removeprefix("www.")


def _registrable(host: str) -> str:
    """Crude eTLD+1: enough to ask 'is this email on the company's own domain?'."""
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    if parts[-2] in ("co", "com", "org", "net") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def evidence_strength(cand: Candidate, today_iso: str) -> tuple[float, dict[str, float]]:
    """E, out of 10: how much checkable public R&D evidence a briefing can actually point at."""
    s = cand.signals
    b: dict[str, float] = {}
    own = int(s.get("recent_repos_own") or 0)
    b["eigen recente repos"] = round(min(own, 5) / 5 * 4, 2)
    langs = len(s.get("languages") or [])
    b["talenbreedte"] = round(min(langs, 4) / 4 * 2, 2)
    days = _days_since(s.get("latest_push"), today_iso)
    b["recentheid laatste commit"] = 2.0 if days is not None and days <= 30 else (
        1.2 if days is not None and days <= 90 else (0.6 if days is not None and days <= 180 else 0.0)
    )
    b["live website met titel"] = 1.0 if (s.get("website_reachable") and (s.get("website_title") or "").strip()) else 0.0
    b["vacaturepagina met dev-functies"] = 1.0 if s.get("careers_dev_terms") else 0.0
    return round(sum(b.values()), 2), b


def contactability(cand: Candidate) -> tuple[float, dict[str, float]]:
    """C, out of 10: can the owner reach a business inbox today, without further research."""
    b: dict[str, float] = {}
    email = (cand.public_email or "").strip().lower()
    b["publiek e-mailadres"] = 5.0 if email else 0.0
    b["website bereikbaar"] = 3.0 if cand.signals.get("website_reachable") else 0.0
    b["contact-/vacaturepagina gevonden"] = 1.0 if cand.signals.get("careers_url") else 0.0
    on_domain = False
    if email and "@" in email and cand.website:
        on_domain = _registrable(email.split("@", 1)[1]) == _registrable(_host(cand.website))
    b["e-mail op het eigen domein"] = 1.0 if on_domain else 0.0
    return round(sum(b.values()), 2), b


def wbso_fit(cand: Candidate) -> tuple[float, dict[str, float]]:
    """W, out of 10: does this look like a Dutch company with payroll, rather than a hobby project
    or a knowledge institution. A triage number for the owner's reading order — never an eligibility
    claim, which only RVO can make."""
    s = cand.signals
    b: dict[str, float] = {}
    b["vacatures voor ontwikkelaars (loonkosten-signaal)"] = 3.0 if s.get("careers_dev_terms") else 0.0
    b["Peppol NL-entiteit met dezelfde naam"] = 2.0 if s.get("peppol_match") else 0.0
    name = (cand.display_name or "").strip()
    b["rechtsvorm in de bedrijfsnaam"] = 1.5 if LEGAL_FORM_RE.search(name) else 0.0
    b["echte bedrijfsnaam (niet de login)"] = 1.0 if name and name.lower() != cand.github_login.lower() else 0.0
    b["org ouder dan 1 jaar"] = 1.0 if (s.get("score_breakdown") or {}).get("org_older_than_1y") else 0.0
    b["meer dan één eigen recente repo"] = 1.0 if int(s.get("recent_repos_own") or 0) >= 2 else 0.0
    title = (s.get("website_title") or "").strip()
    b["zakelijke sitetitel, geen onderwijssignaal"] = 0.5 if (title and not any(r.search(title) for r in EDU_RES)) else 0.0
    return round(sum(b.values()), 2), b


def owner_review(cand: Candidate, w: float) -> list[str]:
    """Doubts that should make the owner look twice. Additive scrutiny only — never an exclusion."""
    s = cand.signals
    name = (cand.display_name or "").strip()
    title = (s.get("website_title") or "").strip()
    email = (cand.public_email or "").strip().lower()
    flags: list[str] = []

    if any(r.search(title) for r in EDU_RES):
        flags.append("sitetitel wijst op onderwijs — RVO sluit publieke kennisinstellingen uit")
    if COMMUNITY_HINT_RE.search(f"{name} {cand.github_login} {title}"):
        flags.append("naam/titel klinkt als community, stichting of vrijwilligersproject")
    if not name or name.lower() == cand.github_login.lower():
        flags.append("GitHub-org draagt geen echte bedrijfsnaam")
    if w < 3.0:
        flags.append("geen publiek signaal van een onderneming met loonkosten (W < 3)")
    if int(s.get("recent_repos_own") or 0) < 2:
        flags.append("slechts één eigen recente repository — dun bewijs")
    if not email:
        flags.append("geen publiek e-mailadres; adres moet handmatig gezocht worden")
    elif "@" in email and email.split("@", 1)[0] not in ROLE_LOCALPARTS:
        flags.append(f"e-mail lijkt persoonlijk ({email.split('@', 1)[0]}@…) — controleer AVG en ontvanger")
    if not s.get("website_reachable"):
        flags.append("website niet bereikbaar op onze leesdatum")
    elif not title:
        flags.append("website gaf geen paginatitel")
    return flags


# The threshold was chosen after looking at the live distribution, which is the only honest way to
# set it and the reason it is stated here rather than buried: a rule tuned on the data it filters is
# a triage aid, not a statistic. It is one-directional (it can only add scrutiny) and every trigger
# is printed next to the candidate, so the owner can overrule it in either direction by reading.
HARD_TRIGGERS = (
    "sitetitel wijst op onderwijs",
    "naam/titel klinkt als community",
    "GitHub-org draagt geen echte bedrijfsnaam",
    "geen publiek signaal van een onderneming",
)
MANY_FLAGS = 4


def needs_owner_review(flags: list[str]) -> bool:
    if len(flags) >= MANY_FLAGS:
        return True
    return any(f.startswith(t) for f in flags for t in HARD_TRIGGERS)


def assess(cand: Candidate, today_iso: str) -> dict[str, Any]:
    e, eb = evidence_strength(cand, today_iso)
    c, cb = contactability(cand)
    w, wb = wbso_fit(cand)
    flags = owner_review(cand, w)
    return {
        "candidate_id": cand.candidate_id,
        "login": cand.github_login,
        "name": cand.display_name or cand.github_login,
        "website": cand.website,
        "email": cand.public_email,
        "scanner_score": cand.score,
        "E": e, "E_breakdown": eb,
        "C": c, "C_breakdown": cb,
        "W": w, "W_breakdown": wb,
        "total": round(e + c + w, 2),
        "owner_review": needs_owner_review(flags),
        "owner_review_flags": flags,
        "scanner_review_flags": cand.signals.get("review_flags") or [],
        "own_recent_repos": int(cand.signals.get("recent_repos_own") or 0),
        "languages": cand.signals.get("languages") or [],
        "latest_push": (cand.signals.get("latest_push") or "")[:10],
        "peppol": bool(cand.signals.get("peppol_match")),
        "careers": bool(cand.signals.get("careers_dev_terms")),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", default=str(ROOT / "data" / "candidates.jsonl"))
    ap.add_argument("--batch-size", type=int, default=25)
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--json-out", default=str(ROOT / "logs" / "launch_batch.json"))
    args = ap.parse_args(argv)

    cands = read_candidates(pathlib.Path(args.candidates))
    kept = [c for c in cands if not c.excluded and (c.website or c.public_email)]
    rows = [assess(c, args.today) for c in kept]
    rows.sort(key=lambda r: (-r["total"], -r["scanner_score"], r["login"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["in_batch"] = i <= args.batch_size
    out = {
        "generated": args.today,
        "kept_with_contact": len(rows),
        "batch_size_target": args.batch_size,
        "batch_size_actual": min(args.batch_size, len(rows)),
        "owner_review_in_batch": sum(1 for r in rows[: args.batch_size] if r["owner_review"]),
        "rows": rows,
    }
    pathlib.Path(args.json_out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    for r in rows:
        mark = "REVIEW" if r["owner_review"] else "      "
        print(f"{r['rank']:>3} {mark} tot={r['total']:>5} E={r['E']:>4} C={r['C']:>4} W={r['W']:>4} "
              f"score={r['scanner_score']:>5} {r['login']:<22} {r['name'][:34]:<34} "
              f"{'; '.join(r['owner_review_flags'])[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
