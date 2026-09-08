"""The candidate's own public website: liveness, and whether it advertises development roles.

A public vacancy for a developer is the single strongest free public proxy for an S&O *wage base*,
which is what the WBSO benefit is computed on. It is also the most intrusive thing this scanner
touches, so the rules here are tight:

* `robots.txt` is fetched and obeyed for every host (see `http_client.PoliteClient._robots_ok`).
  A disallowed path is skipped and recorded as skipped, never fetched by another route.
* At most **two** GETs per company: the homepage, and one careers page linked from it.
* Nothing behind a login, no form submission, no JavaScript execution, no email harvesting from the
  page. A business address published on a company's own homepage is business contact information;
  we do not collect names of individuals.
* The whole module is **off by default** and enabled with `--fetch-sites`.
"""
from __future__ import annotations

import html as html_mod
import re
import urllib.parse
from typing import Any

from ..http_client import BudgetExhausted, PoliteClient, RobotsDisallowed
from ..model import Candidate, Evidence, now_utc

CAREERS_HINTS = (
    "vacature",
    "vacatures",
    "werken-bij",
    "werkenbij",
    "careers",
    "career",
    "jobs",
    "join-us",
    "join",
)

DEV_ROLE_TERMS = (
    "developer",
    "ontwikkelaar",
    "software engineer",
    "programmeur",
    "data engineer",
    "machine learning",
    "devops",
    "backend",
    "frontend",
    "full stack",
    "fullstack",
    "embedded",
    "r&d",
    "research engineer",
)


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html_mod.unescape(text)).strip()


def _links(raw: str, base: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw):
        href, label = m.group(1), _strip_html(m.group(2))
        out.append((urllib.parse.urljoin(base, href), label))
    return out


def probe_site(client: PoliteClient, cand: Candidate) -> dict[str, Any]:
    """Fetch homepage (robots-permitting) and at most one careers page. Attach evidence."""
    result: dict[str, Any] = {"attempted": bool(cand.website), "homepage_status": None}
    if not cand.website:
        result["skipped"] = "no website on the GitHub profile"
        return result

    try:
        status, body = client.get(
            cand.website, expect_json=False, note=f"homepage {cand.github_login}",
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
    except RobotsDisallowed:
        result["skipped"] = "robots.txt disallows the homepage; not fetched"
        cand.signals["website_robots_blocked"] = True
        return result
    except BudgetExhausted:
        result["skipped"] = "request budget exhausted"
        return result
    except Exception as exc:  # network/DNS/TLS failures are data, not crashes
        result["skipped"] = f"{type(exc).__name__}: {exc}"
        cand.signals["website_reachable"] = False
        return result

    result["homepage_status"] = status
    cand.signals["website_reachable"] = status == 200
    if status != 200 or not isinstance(body, str):
        return result

    title_m = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
    title = _strip_html(title_m.group(1)) if title_m else ""
    cand.signals["website_title"] = title[:200]
    cand.add(
        Evidence(
            source="website",
            kind="live_website",
            claim_nl=f"De website {cand.website} is bereikbaar en heeft als paginatitel “{title[:120]}”.",
            url=cand.website,
            observed_utc=now_utc(),
            detail={"http_status": status, "title": title[:200]},
        )
    )

    careers_url = None
    for href, label in _links(body, cand.website):
        blob = f"{href} {label}".lower()
        if any(h in blob for h in CAREERS_HINTS):
            if urllib.parse.urlsplit(href).netloc.endswith(urllib.parse.urlsplit(cand.website).netloc):
                careers_url = href
                break
    if not careers_url:
        result["careers"] = "no careers link found on the homepage"
        return result

    try:
        c_status, c_body = client.get(
            careers_url, expect_json=False, note=f"careers {cand.github_login}",
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
    except RobotsDisallowed:
        result["careers"] = "robots.txt disallows the careers page; not fetched"
        return result
    except BudgetExhausted:
        result["careers"] = "request budget exhausted"
        return result
    except Exception as exc:
        result["careers"] = f"{type(exc).__name__}: {exc}"
        return result

    result["careers_status"] = c_status
    if c_status != 200 or not isinstance(c_body, str):
        return result

    text = _strip_html(c_body).lower()
    found = sorted({term for term in DEV_ROLE_TERMS if term in text})
    cand.signals["careers_url"] = careers_url
    cand.signals["careers_dev_terms"] = found
    if found:
        cand.add(
            Evidence(
                source="website",
                kind="careers_dev_roles",
                claim_nl=(
                    f"Op uw eigen vacaturepagina staan termen die op ontwikkelwerk wijzen: "
                    f"{', '.join(found[:6])}."
                ),
                url=careers_url,
                observed_utc=now_utc(),
                detail={"terms": found},
            )
        )
    result["careers"] = "fetched"
    return result
