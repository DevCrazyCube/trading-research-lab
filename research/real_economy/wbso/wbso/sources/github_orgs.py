"""GitHub as a free, public register of organisations that demonstrably write software.

**Why this source and not a company register.** The KVK API is key-gated and paid (probed 401,
T26 §2), as are OpenCorporates and overheid.io. GitHub's search API is free and unauthenticated and
answers a question the company register cannot: *does this organisation actually develop software,
this month, in public?* That is the signal WBSO is about. What it cannot tell us is whether the
organisation is a Dutch legal entity, how many people it employs, or whether the work is
technically novel — the three things that actually decide eligibility. The scanner's job is to be
loud about that gap, not to paper over it.

**Rate limits, which shape the whole design.** Unauthenticated: the *search* pool allows ~10
requests/minute; the *core* pool allows 60 requests/hour. Org profile lookups (`GET /orgs/{login}`)
come out of the scarce core pool, so the funnel is: cheap search enumerates and screens, expensive
core enrichment runs only on candidates that already survived screening.

**The 1,000-result ceiling.** `search/users?q=type:org location:Netherlands` reports ~19.5k matches
but returns at most 1,000 (10 pages x 100). Partitioning by `created:` date ranges slices the
population into windows each under the ceiling, which is how the full population becomes reachable
without a token.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterator

from ..http_client import PoliteClient
from ..model import Candidate, Evidence, now_utc

SEARCH_USERS = "https://api.github.com/search/users"
SEARCH_REPOS = "https://api.github.com/search/repositories"
ORG_DETAIL = "https://api.github.com/orgs/{login}"

# GitHub caps any search at 1,000 returned results regardless of total_count.
SEARCH_RESULT_CEILING = 1000

NL_LOCATION_TOKENS = (
    "netherlands",
    "nederland",
    "holland",
    "the hague",
    "den haag",
    "amsterdam",
    "rotterdam",
    "utrecht",
    "eindhoven",
    "groningen",
    "tilburg",
    "almere",
    "breda",
    "nijmegen",
    "enschede",
    "haarlem",
    "arnhem",
    "zwolle",
    "delft",
    "leiden",
    "maastricht",
    "amersfoort",
    "apeldoorn",
    "hilversum",
    "'s-hertogenbosch",
    "den bosch",
    "wageningen",
    "deventer",
    "zoetermeer",
    "leeuwarden",
    "nl",
)

# Location strings that mention another country alongside NL. A multinational's NL office is not an
# NL SME, and T26 §8 named exactly this as the way the population proxy fails.
FOREIGN_TOKENS = (
    "usa",
    "united states",
    "san francisco",
    "new york",
    "london",
    "united kingdom",
    "germany",
    "deutschland",
    "berlin",
    "munich",
    "france",
    "paris",
    "belgium",
    "brussels",
    "spain",
    "india",
    "china",
    "japan",
    "singapore",
    "canada",
    "australia",
    "switzerland",
    "zurich",
    "sweden",
    "denmark",
    "poland",
    "prague",
    "czech",
    "worldwide",
    "global",
    "remote-first",
)


def month_windows(start: str, end: str, step_months: int = 6) -> list[tuple[str, str]]:
    """Inclusive `created:` windows covering [start, end], as GitHub date ranges."""
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    out: list[tuple[str, str]] = []
    cur = s
    while cur <= e:
        year = cur.year + (cur.month - 1 + step_months) // 12
        month = (cur.month - 1 + step_months) % 12 + 1
        nxt = dt.date(year, month, 1)
        stop = min(nxt - dt.timedelta(days=1), e)
        out.append((cur.isoformat(), stop.isoformat()))
        cur = nxt
    return out


def search_orgs(
    client: PoliteClient,
    *,
    created_from: str,
    created_to: str,
    location: str = "Netherlands",
    max_pages: int = 3,
    per_page: int = 100,
) -> Iterator[dict[str, Any]]:
    """Yield org stubs (login, id, html_url) for one created-date window."""
    query = f"type:org location:{location} created:{created_from}..{created_to}"
    for page in range(1, max_pages + 1):
        url = (
            f"{SEARCH_USERS}?q={_q(query)}&per_page={per_page}&page={page}"
            "&sort=joined&order=desc"
        )
        status, payload = client.get(url, note=f"search_orgs {created_from}..{created_to} p{page}")
        if status != 200 or not isinstance(payload, dict):
            return
        items = payload.get("items") or []
        for item in items:
            yield item
        if len(items) < per_page:
            return
        if page * per_page >= min(SEARCH_RESULT_CEILING, payload.get("total_count", 0)):
            return


def window_total(client: PoliteClient, *, created_from: str, created_to: str, location: str = "Netherlands") -> int:
    query = f"type:org location:{location} created:{created_from}..{created_to}"
    url = f"{SEARCH_USERS}?q={_q(query)}&per_page=1"
    status, payload = client.get(url, note="window_total")
    if status != 200 or not isinstance(payload, dict):
        return -1
    return int(payload.get("total_count", 0))


def recent_repos(
    client: PoliteClient, login: str, *, pushed_since: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Repos owned by `login` pushed since `pushed_since`. One *search*-pool request."""
    query = f"user:{login} pushed:>={pushed_since}"
    url = f"{SEARCH_REPOS}?q={_q(query)}&sort=updated&order=desc&per_page={limit}"
    status, payload = client.get(url, note=f"recent_repos {login}")
    if status != 200 or not isinstance(payload, dict):
        return []
    return list(payload.get("items") or [])


def org_detail(client: PoliteClient, login: str) -> dict[str, Any] | None:
    """Org profile: name, blog, email, location, public_repos. One scarce *core*-pool request."""
    status, payload = client.get(ORG_DETAIL.format(login=login), note=f"org_detail {login}")
    if status != 200 or not isinstance(payload, dict):
        return None
    return payload


def build_candidate(login: str, html_url: str) -> Candidate:
    return Candidate(
        candidate_id=f"gh:{login.lower()}",
        display_name=login,
        github_login=login,
        github_url=html_url or f"https://github.com/{login}",
        scanned_utc=now_utc(),
    )


def attach_repo_evidence(cand: Candidate, repos: list[dict[str, Any]], *, pushed_since: str) -> None:
    """Turn repo metadata into checkable evidence rows, and count what actually matters.

    Forks and archived repos are counted separately and never presented as development evidence: a
    fork of someone else's project is not this company's R&D, and saying so in a briefing would be
    the exact failure mode the ethics rule exists to prevent.
    """
    own = [r for r in repos if not r.get("fork") and not r.get("archived")]
    forks = [r for r in repos if r.get("fork")]
    languages = sorted({r.get("language") for r in own if r.get("language")})

    cand.signals.update(
        {
            "recent_repos_total": len(repos),
            "recent_repos_own": len(own),
            "recent_repos_forks": len(forks),
            "languages": languages,
            "pushed_since_filter": pushed_since,
        }
    )
    if own:
        newest = max(own, key=lambda r: r.get("pushed_at") or "")
        cand.signals["latest_push"] = newest.get("pushed_at")

    for repo in own[:5]:
        if not repo.get("html_url"):
            # No verifiable URL means no evidence row. The linter would reject it downstream; drop
            # it here so the reason is visible in the signals rather than as a late lint failure.
            cand.signals.setdefault("repos_without_url", 0)
            cand.signals["repos_without_url"] += 1
            continue
        pushed = (repo.get("pushed_at") or "")[:10]
        desc = (repo.get("description") or "").strip()
        lang = repo.get("language") or "onbekend"
        cand.add(
            Evidence(
                source="github",
                kind="recent_public_repo",
                claim_nl=(
                    f"De publieke repository {repo.get('full_name')} "
                    f"(taal: {lang}) had een commit op {pushed}."
                    + (f" Omschrijving: “{desc[:160]}”." if desc else "")
                ),
                url=repo.get("html_url") or "",
                observed_utc=now_utc(),
                detail={
                    "full_name": repo.get("full_name"),
                    "pushed_at": repo.get("pushed_at"),
                    "language": repo.get("language"),
                    "stargazers": repo.get("stargazers_count"),
                    "fork": False,
                },
            )
        )


def attach_profile_evidence(cand: Candidate, detail: dict[str, Any]) -> None:
    cand.display_name = (detail.get("name") or cand.github_login).strip()
    cand.website = _clean_url(detail.get("blog"))
    cand.public_email = detail.get("email") or None
    cand.location_text = detail.get("location") or None
    cand.github_created_at = detail.get("created_at")
    cand.public_repos = detail.get("public_repos")
    cand.followers = detail.get("followers")
    cand.signals["org_type"] = detail.get("type")

    if cand.location_text:
        cand.add(
            Evidence(
                source="github",
                kind="stated_location",
                claim_nl=(
                    f"Het GitHub-profiel van {cand.github_login} vermeldt als locatie "
                    f"“{cand.location_text}”."
                ),
                url=cand.github_url,
                observed_utc=now_utc(),
                detail={"location": cand.location_text},
            )
        )
    if cand.website:
        cand.add(
            Evidence(
                source="github",
                kind="stated_website",
                claim_nl=f"Het GitHub-profiel verwijst naar de website {cand.website}.",
                url=cand.github_url,
                observed_utc=now_utc(),
                detail={"website": cand.website},
            )
        )


def location_verdict(location_text: str | None) -> tuple[bool, list[str]]:
    """(looks_dutch, reasons_to_doubt). Empty location is a doubt, not a disqualification."""
    if not location_text:
        return False, ["geen locatie op het GitHub-profiel"]
    low = location_text.lower()
    dutch = any(_token_in(tok, low) for tok in NL_LOCATION_TOKENS)
    doubts = [f"locatie noemt ook '{tok}'" for tok in FOREIGN_TOKENS if _token_in(tok, low)]
    return dutch, doubts


def _token_in(token: str, haystack: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", haystack) is not None


def _clean_url(blog: str | None) -> str | None:
    if not blog:
        return None
    blog = blog.strip()
    if not blog:
        return None
    if not blog.startswith(("http://", "https://")):
        blog = "https://" + blog
    return blog


def _q(query: str) -> str:
    import urllib.parse

    return urllib.parse.quote(query, safe=":><=./*")
