"""The candidate funnel: enumerate, screen, enrich, score, exclude — with reasons at every step.

The funnel is shaped by the unauthenticated GitHub rate limits (search ~10/min, core 60/hour), so
cheap screening runs first and the scarce core-pool profile lookup runs only on organisations that
already look like NL software SMEs.

    windows -> org stubs        (1 search request per 100 orgs)
            -> recent repos     (1 search request per org)      <- screen: real, recent, own code
            -> org profile      (1 core request per survivor)   <- name, website, email, location
            -> Peppol match     (1 directory request)           <- NL legal-entity corroboration
            -> website probe    (<=2 requests, robots-permitting, opt-in)
            -> score + exclude

**Exclusions are first-class output, not filtered-away noise.** T26 §8 said the population proxy
fails if "GitHub org in NL" is mostly not "NL SME doing R&D" — the only way to know is to keep every
rejection with its reason and report the rates. `scan_report()` does that.

One exclusion rule is not a heuristic but Dutch law: RVO's conditions say *"U bent geen publieke
kennisinstelling"*, so universities, hogescholen and public bodies are dropped by rule, not by score.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import urllib.parse
from typing import Any, Iterable

from .http_client import BudgetExhausted, PoliteClient
from .model import Candidate, now_utc
from .sources import github_orgs as gh
from .sources import peppol, website

# --- exclusion rules -----------------------------------------------------------------------

# RVO: "U bent geen publieke kennisinstelling." Also public bodies, which are not undertakings.
PUBLIC_BODY_PATTERNS = (
    r"\buniversit(y|eit|e)\b",
    r"\bhogeschool\b",
    r"\bhbo\b",
    r"\bacadem(y|ie|isch)\b",
    r"\bgemeente\b",
    r"\bministerie\b",
    r"\bprovincie\b",
    r"\bwaterschap\b",
    r"\brijks(dienst|overheid|waterstaat)\b",
    r"\broc\b",
    r"\bscholengemeenschap\b",
    r"\bonderwijsgroep\b|\bopleidingscentrum\b",
    r"\bziekenhuis\b",
    r"\bumc\b",
    r"\btno\b",
    r"\bcwi\b",
    r"\bnwo\b",
    r"\bsurf(net|sara)?\b",
)

# Academic hosts. RVO excludes public knowledge institutions outright, and a university lab's
# GitHub org looks exactly like a small software company from the outside. The first live run found
# `ai4mde.liacs.nl` — LIACS is Leiden's computer science institute — sitting in the kept list.
ACADEMIC_HOST_PATTERNS = (
    r"(^|\.)(liacs|tudelft|tue|utwente|rug|uva|vu|ru|uu|leidenuniv|lumc|umcg|umcutrecht|erasmusmc"
    r"|wur|maastrichtuniversity|universiteitleiden|tilburguniversity|ou|hva|hu|han|fontys|saxion"
    r"|windesheim|inholland|avans|nhlstenden|zuyd)\.nl$",
    r"\.edu$",
    r"\.ac\.[a-z]{2}$",
    r"(^|\.)uni-",
)

# Volunteer associations and clubs. They may write excellent software; they do not run an S&O wage
# base. The first live run surfaced a scouting group.
NONCOMMERCIAL_NAME_PATTERNS = (
    r"\bscouting\b",
    r"\bpadvind\w*",
    r"\bvereniging\b",
    r"\bkerk\b|\bparochie\b",
    r"\bhackerspace\b|\bmakerspace\b|\bfablab\b",
    r"\bmeetup\b|\buser ?group\b|\bcommunity\b",
    r"\bsportclub\b|\bvoetbalvereniging\b|\bstudievereniging\b",
)

# Education. RVO excludes public knowledge institutions, and a school's IT department has a GitHub
# org indistinguishable from a small software firm's. The unambiguous institution words are a hard
# exclusion (below, in PUBLIC_BODY_PATTERNS); these softer ones raise a flag for the owner instead,
# because "school" also appears on the homepage of companies that sell *to* schools. The live run
# surfaced Aventus — an MBO college whose homepage title is "De school waar jij 't maakt".
EDUCATION_TITLE_PATTERNS = (
    r"\bschool\b|\bscholen\b",
    r"\bonderwijs\w*",
    r"\bopleiding\w*",
    r"\bstudent\w*|\bleerling\w*",
    r"\bmbo\b|\bhbo\b|\broc\b",
)

# A website that is parked, for sale or unbuilt is not a company we can write to about R&D.
DEAD_SITE_TITLE_PATTERNS = (
    r"\bis available\b",
    r"\bfor sale\b|\bte koop\b",
    r"\bcoming soon\b|\bbinnenkort\b",
    r"\bunder construction\b|\bin aanbouw\b",
    r"\bdomain (is )?parked\b|\bparkeerpagina\b",
    r"\bindex of /",
    r"\bdefault web page\b|\bapache2 ubuntu default\b",
)

# Not an SME. These are deliberately generous: a firm with 300 public repos and 2,000 followers is
# not a company that has never heard of WBSO.
MAX_PUBLIC_REPOS = 300
MAX_FOLLOWERS = 2000

SCORE_WEIGHTS = {
    "own_recent_repos": 6,  # per repo, capped at 5 repos
    "push_within_30d": 15,
    "push_within_90d": 10,
    "push_within_180d": 5,
    "language_breadth": 3,  # per distinct language, capped at 4
    "has_website": 8,
    "website_reachable": 5,
    "careers_dev_roles": 15,
    "peppol_nl_entity": 12,
    "public_email": 5,
    "org_older_than_1y": 3,
}


@dataclasses.dataclass
class ScanConfig:
    created_from: str = "2015-01-01"
    created_to: str = "2026-06-30"
    window_months: int = 12
    location: str = "Netherlands"
    pushed_since: str = "2026-02-01"
    max_orgs_screened: int = 60
    max_enriched: int = 25
    min_own_recent_repos: int = 1
    fetch_sites: bool = False
    site_budget: int = 10
    use_peppol: bool = True

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def looks_public_body(*texts: str | None) -> str | None:
    blob = " ".join(t.lower() for t in texts if t)
    for pattern in PUBLIC_BODY_PATTERNS:
        if re.search(pattern, blob):
            return f"lijkt een publieke instelling of overheidsorgaan ({pattern})"
    return None


def score_candidate(cand: Candidate, *, today_iso: str) -> float:
    s = cand.signals
    breakdown: dict[str, float] = {}

    own = int(s.get("recent_repos_own") or 0)
    breakdown["own_recent_repos"] = min(own, 5) * SCORE_WEIGHTS["own_recent_repos"]

    latest = (s.get("latest_push") or "")[:10]
    if latest:
        days = _days_between(latest, today_iso)
        if days <= 30:
            breakdown["recency"] = SCORE_WEIGHTS["push_within_30d"]
        elif days <= 90:
            breakdown["recency"] = SCORE_WEIGHTS["push_within_90d"]
        elif days <= 180:
            breakdown["recency"] = SCORE_WEIGHTS["push_within_180d"]

    langs = s.get("languages") or []
    breakdown["language_breadth"] = min(len(langs), 4) * SCORE_WEIGHTS["language_breadth"]

    if cand.website:
        breakdown["has_website"] = SCORE_WEIGHTS["has_website"]
    if s.get("website_reachable"):
        breakdown["website_reachable"] = SCORE_WEIGHTS["website_reachable"]
    if s.get("careers_dev_terms"):
        breakdown["careers_dev_roles"] = SCORE_WEIGHTS["careers_dev_roles"]
    if s.get("peppol_match"):
        breakdown["peppol_nl_entity"] = SCORE_WEIGHTS["peppol_nl_entity"]
    if cand.public_email:
        breakdown["public_email"] = SCORE_WEIGHTS["public_email"]
    if cand.github_created_at and _days_between(cand.github_created_at[:10], today_iso) > 365:
        breakdown["org_older_than_1y"] = SCORE_WEIGHTS["org_older_than_1y"]

    cand.signals["score_breakdown"] = breakdown
    cand.score = round(sum(breakdown.values()), 2)
    return cand.score


def apply_exclusions(cand: Candidate, cfg: ScanConfig) -> None:
    """Attach every reason this candidate is not briefable. Order matters: the first blocking fact
    ends the list, because reasons that depend on data we never fetched are not reasons.

    Without that early return the report reads "52 candidates had no website", when the truth is
    "52 candidates never had their profile fetched, because they failed the screen first". A funnel
    report that confuses the two is worse than no funnel report.
    """
    s = cand.signals
    reasons: list[str] = []

    if int(s.get("recent_repos_own") or 0) < cfg.min_own_recent_repos:
        cand.exclusions = [
            f"geen eigen, niet-geforkte publieke repository met een commit sinds {cfg.pushed_since}"
        ]
        return
    if not s.get("enriched"):
        cand.exclusions = [
            "niet verrijkt: buiten het verrijkingsbudget van deze run (geen profielgegevens opgehaald)"
        ]
        return

    public_body = looks_public_body(cand.display_name, cand.github_login, cand.location_text, s.get("website_title"))
    if public_body:
        reasons.append(public_body + " — RVO-voorwaarde: 'U bent geen publieke kennisinstelling'")

    academic = academic_host(cand.website)
    if academic:
        reasons.append(
            f"website hoort bij een kennisinstelling ({academic}) — RVO-voorwaarde: "
            "'U bent geen publieke kennisinstelling'"
        )

    # Name and login only, deliberately not the website title: marketing copy says "join our
    # community" on plenty of real companies' homepages, and excluding those would be a false
    # positive bought with nothing.
    blob = " ".join(t.lower() for t in (cand.display_name, cand.github_login) if t)
    for pattern in NONCOMMERCIAL_NAME_PATTERNS:
        if re.search(pattern, blob):
            reasons.append(
                f"lijkt een vereniging of vrijwilligersinitiatief, geen onderneming met "
                f"S&O-loonkosten ({pattern})"
            )
            break

    title = (s.get("website_title") or "").lower()
    for pattern in DEAD_SITE_TITLE_PATTERNS:
        if re.search(pattern, title):
            reasons.append(f"website is geparkeerd, te koop of nog niet in gebruik (“{title[:60]}”)")
            break

    if cand.public_repos is not None and cand.public_repos > MAX_PUBLIC_REPOS:
        reasons.append(f"te groot voor het MKB-profiel: {cand.public_repos} publieke repositories")
    if cand.followers is not None and cand.followers > MAX_FOLLOWERS:
        reasons.append(f"te bekend voor 'kent de regeling niet': {cand.followers} volgers")

    dutch, doubts = gh.location_verdict(cand.location_text)
    peppol_nl = bool(s.get("peppol_match"))
    if doubts:
        reasons.extend(doubts)
    if not dutch and not peppol_nl:
        reasons.append("Nederlandse vestiging niet aangetoond uit publieke bronnen")

    if not cand.website and not cand.public_email:
        reasons.append("geen publiek zakelijk contactkanaal (website noch e-mailadres)")

    cand.exclusions = reasons
    cand.signals["review_flags"] = review_flags(cand)


def academic_host(website: str | None) -> str | None:
    if not website:
        return None
    host = urllib.parse.urlsplit(website).netloc.lower().split(":")[0]
    for pattern in ACADEMIC_HOST_PATTERNS:
        if re.search(pattern, host):
            return host
    return None


def review_flags(cand: Candidate) -> list[str]:
    """Doubts a rule cannot settle. These do not exclude; they go in front of the owner.

    The first live run made the case for this list: a volunteer badge community and a scouting group
    both passed every mechanical rule, and no rule short of reading the website would have caught
    the first one. Pretending otherwise would be the dishonest option.
    """
    s = cand.signals
    flags: list[str] = []
    title = (s.get("website_title") or "").lower()
    for pattern in EDUCATION_TITLE_PATTERNS:
        if re.search(pattern, title):
            flags.append(
                "website-titel wijst op onderwijs — RVO sluit publieke kennisinstellingen uit; "
                "controleer of dit een school is voordat u iets verstuurt"
            )
            break
    if not s.get("peppol_match"):
        flags.append("geen NL-entiteit met dezelfde naam gevonden in de Peppol Directory")
    if not s.get("careers_dev_terms"):
        flags.append("geen vacaturepagina met ontwikkelfuncties gevonden — loonkosten onbekend")
    if (cand.display_name or "").strip().lower() == cand.github_login.lower():
        flags.append("GitHub-org draagt geen echte bedrijfsnaam")
    if not (s.get("website_title") or "").strip():
        flags.append("website gaf geen paginatitel — mogelijk geen echte bedrijfssite")
    if int(s.get("recent_repos_own") or 0) < 2:
        flags.append("slechts één eigen recente repository — dun bewijs")
    if not cand.public_email:
        flags.append("geen publiek e-mailadres; contactadres moet handmatig gezocht worden")
    return flags


def screen_org(
    client: PoliteClient, stub: dict[str, Any], cfg: ScanConfig
) -> Candidate:
    """Stage A: one search-pool request. Cheap enough to run on everything we enumerate."""
    cand = gh.build_candidate(stub.get("login", ""), stub.get("html_url", ""))
    repos = gh.recent_repos(client, cand.github_login, pushed_since=cfg.pushed_since)
    gh.attach_repo_evidence(cand, repos, pushed_since=cfg.pushed_since)
    return cand


def enrich(client: PoliteClient, cand: Candidate, cfg: ScanConfig) -> None:
    """Stage B: the scarce core-pool profile call, then the free corroboration sources."""
    detail = gh.org_detail(client, cand.github_login)
    if detail:
        gh.attach_profile_evidence(cand, detail)
        cand.signals["enriched"] = True
    else:
        cand.signals["org_detail_failed"] = True
        cand.signals["enriched"] = False

    if cfg.use_peppol and cand.display_name:
        try:
            matches = peppol.lookup(client, cand.display_name)
            match = peppol.best_nl_match(matches, cand.display_name)
            if match:
                peppol.attach_evidence(cand, match)
            else:
                cand.signals["peppol_match"] = None
        except BudgetExhausted:
            cand.signals["peppol_match"] = None


def scan(
    client: PoliteClient,
    cfg: ScanConfig,
    *,
    today_iso: str,
    progress: Any = None,
) -> tuple[list[Candidate], dict[str, Any]]:
    """Run the whole funnel. Returns (candidates, funnel_report). Never raises on budget."""
    funnel: dict[str, Any] = {
        "config": cfg.as_dict(),
        "windows": [],
        "orgs_enumerated": 0,
        "orgs_screened": 0,
        "passed_screen": 0,
        "enriched": 0,
        "stopped_early": None,
    }
    candidates: list[Candidate] = []
    seen: set[str] = set()

    windows = gh.month_windows(cfg.created_from, cfg.created_to, cfg.window_months)
    # Stratify across creation windows rather than filling the quota from the first one. Taking the
    # first 60 hits of a single window would make every candidate an org founded in the same year,
    # and the resulting keep rate would describe that year rather than the population.
    per_window = max(1, -(-cfg.max_orgs_screened // max(1, len(windows))))
    stubs: list[dict[str, Any]] = []
    try:
        for start, stop in windows:
            got = list(
                gh.search_orgs(
                    client,
                    created_from=start,
                    created_to=stop,
                    location=cfg.location,
                    max_pages=1,
                    per_page=per_window,
                )
            )
            funnel["windows"].append({"from": start, "to": stop, "returned": len(got)})
            for stub in got:
                login = (stub.get("login") or "").lower()
                if login and login not in seen:
                    seen.add(login)
                    stubs.append(stub)
            if len(stubs) >= cfg.max_orgs_screened:
                break
    except BudgetExhausted as exc:
        funnel["stopped_early"] = f"enumeration: {exc}"
    funnel["sampling_note"] = (
        f"{per_window} orgs per creation window, ordered by most recently joined. This is a "
        "stratified sample of the ~19.5k NL-located GitHub organisations, not a census."
    )

    funnel["orgs_enumerated"] = len(stubs)
    stubs = stubs[: cfg.max_orgs_screened]

    screened: list[Candidate] = []
    try:
        for i, stub in enumerate(stubs, 1):
            cand = screen_org(client, stub, cfg)
            screened.append(cand)
            if progress:
                progress(f"screened {i}/{len(stubs)} {cand.github_login} "
                         f"own_recent={cand.signals.get('recent_repos_own')}")
    except BudgetExhausted as exc:
        funnel["stopped_early"] = f"screening: {exc}"

    funnel["orgs_screened"] = len(screened)
    passed = [c for c in screened if int(c.signals.get("recent_repos_own") or 0) >= cfg.min_own_recent_repos]
    funnel["passed_screen"] = len(passed)

    passed.sort(key=lambda c: (-(int(c.signals.get("recent_repos_own") or 0)), c.signals.get("latest_push") or ""))
    to_enrich = passed[: cfg.max_enriched]

    sites_done = 0
    try:
        for i, cand in enumerate(to_enrich, 1):
            enrich(client, cand, cfg)
            if cfg.fetch_sites and cand.website and sites_done < cfg.site_budget:
                website.probe_site(client, cand)
                sites_done += 1
            if progress:
                progress(f"enriched {i}/{len(to_enrich)} {cand.github_login} -> {cand.display_name}")
    except BudgetExhausted as exc:
        funnel["stopped_early"] = f"enrichment: {exc}"

    funnel["enriched"] = sum(1 for c in to_enrich if c.signals.get("enriched"))
    funnel["sites_probed"] = sites_done

    for cand in screened:
        apply_exclusions(cand, cfg)
        score_candidate(cand, today_iso=today_iso)
    candidates = screened
    candidates.sort(key=lambda c: (-c.score, c.github_login))
    return candidates, funnel


def scan_report(candidates: Iterable[Candidate], funnel: dict[str, Any]) -> dict[str, Any]:
    cands = list(candidates)
    kept = [c for c in cands if not c.excluded]
    enriched = [c for c in cands if c.signals.get("enriched")]
    reasons: dict[str, int] = {}
    for c in cands:
        for r in c.exclusions:
            # Group on the reason itself, dropping the per-candidate detail in brackets or after an
            # em dash. Truncating at a fixed width instead produced rows cut off mid-word.
            key = re.split(r" — | \(|“", r)[0].strip()
            reasons[key] = reasons.get(key, 0) + 1
    return {
        "funnel": funnel,
        "scanned": len(cands),
        "kept": len(kept),
        "excluded": len(cands) - len(kept),
        "keep_rate": round(len(kept) / len(cands), 3) if cands else None,
        "screen_pass_rate": (
            round(funnel.get("passed_screen", 0) / len(cands), 3) if cands else None
        ),
        "keep_rate_of_enriched": round(len(kept) / len(enriched), 3) if enriched else None,
        "rate_note": (
            "keep_rate is over everything screened and is dominated by the screen; "
            "keep_rate_of_enriched is over the candidates whose profile was actually fetched. "
            "Neither says anything about whether a kept candidate is WBSO-eligible."
        ),
        "exclusion_reasons": sorted(reasons.items(), key=lambda kv: -kv[1]),
        "kept_with_contact": sum(1 for c in kept if c.website or c.public_email),
        "kept_with_peppol": sum(1 for c in kept if c.signals.get("peppol_match")),
        "score_p50": _percentile([c.score for c in kept], 0.5),
        "score_max": max([c.score for c in kept], default=None),
        "generated_utc": now_utc(),
    }


def write_candidates(path: pathlib.Path, candidates: Iterable[Candidate]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for cand in candidates:
            fh.write(json.dumps(cand.as_dict(), ensure_ascii=False) + "\n")
            n += 1
    return n


def read_candidates(path: pathlib.Path) -> list[Candidate]:
    out = []
    with pathlib.Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(Candidate.from_dict(json.loads(line)))
    return out


def _days_between(a_iso: str, b_iso: str) -> int:
    import datetime as dt

    try:
        a = dt.date.fromisoformat(a_iso[:10])
        b = dt.date.fromisoformat(b_iso[:10])
    except ValueError:
        return 10_000
    return (b - a).days


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    idx = min(len(vs) - 1, max(0, int(round(q * (len(vs) - 1)))))
    return vs[idx]
