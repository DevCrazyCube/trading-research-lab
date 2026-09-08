"""A polite, auditable HTTP client.

Three properties this needs to have, and each is enforced here rather than left to the caller:

1. **Bounded.** Every run declares a request budget. When it is spent the client raises instead of
   quietly continuing, so a scan cannot turn into a crawl by accident.
2. **Polite.** Per-host minimum interval, an honest User-Agent, and `robots.txt` consulted before
   any request to a host that is not a documented public API. GitHub, the Peppol Directory and
   TenderNed are consulted through their published JSON APIs; company websites are consulted only
   where robots.txt permits it.
3. **Auditable.** Every request is appended to a receipt log with URL, status, byte count and
   timestamp. The evidence in a briefing has to be traceable to a fetch that actually happened.

There is no auth anywhere in this module, by construction: `_forbid_credentials` refuses to send an
Authorization header or a token query parameter. Scanning behind a login is out of scope for this
task and the client should make that impossible rather than merely unlikely.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import time
import urllib.parse
import urllib.robotparser
from typing import Any

import requests

USER_AGENT = (
    "wbso-candidate-scanner/0.1 (research prototype; public-data only; "
    "contact: set SCANNER_CONTACT in params/sender_profile.json)"
)

# Public JSON APIs whose terms are the API terms; robots.txt governs their websites, not these
# endpoints. Everything NOT in this set is treated as a website and robots-checked.
API_HOSTS = frozenset(
    {
        "api.github.com",
        "directory.peppol.eu",
        "www.tenderned.nl",  # papi/* documented public API; robots.txt allows it anyway
    }
)

DEFAULT_MIN_INTERVAL = {
    "api.github.com": 6.5,  # unauthenticated search allows 10 req/min; stay under it
    "directory.peppol.eu": 1.5,
    "www.tenderned.nl": 1.5,
    "*": 2.0,
}


class BudgetExhausted(RuntimeError):
    """The run's request budget is spent. Not an error condition; a stop condition."""


class RobotsDisallowed(RuntimeError):
    """robots.txt forbids this path for our User-Agent. Never retried, never worked around."""


class CredentialAttempt(RuntimeError):
    """Something tried to authenticate. This scanner is public-data-only by construction."""


@dataclasses.dataclass
class Receipt:
    url: str
    status: int | None
    bytes_: int
    elapsed_ms: int
    at_utc: str
    from_cache: bool
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "bytes": self.bytes_,
            "elapsed_ms": self.elapsed_ms,
            "at_utc": self.at_utc,
            "from_cache": self.from_cache,
            "note": self.note,
        }


class PoliteClient:
    def __init__(
        self,
        *,
        cache_dir: pathlib.Path,
        budget: int = 200,
        receipts_path: pathlib.Path | None = None,
        min_interval: dict[str, float] | None = None,
        offline: bool = False,
        cache_ttl_s: int = 7 * 24 * 3600,
    ) -> None:
        self.cache_dir = pathlib.Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.budget = budget
        self.spent = 0
        self.offline = offline
        self.cache_ttl_s = cache_ttl_s
        self.min_interval = dict(min_interval or DEFAULT_MIN_INTERVAL)
        self.receipts: list[Receipt] = []
        self.receipts_path = receipts_path
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    # -- policy ---------------------------------------------------------------------------

    @staticmethod
    def _forbid_credentials(url: str, headers: dict[str, str] | None) -> None:
        if headers:
            for key in headers:
                if key.lower() in ("authorization", "cookie", "x-api-key", "private-token"):
                    raise CredentialAttempt(f"refusing to send {key} header (public data only)")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        for key in query:
            if key.lower() in ("access_token", "api_key", "apikey", "token", "client_secret"):
                raise CredentialAttempt(f"refusing credential query parameter {key!r}")

    def _robots_ok(self, url: str) -> bool:
        host = urllib.parse.urlsplit(url).netloc
        if host in API_HOSTS:
            return True
        if host not in self._robots:
            self._robots[host] = self._load_robots(url)
        rp = self._robots[host]
        if rp is None:
            # No robots.txt readable => RFC 9309 says allowed. We still apply the interval.
            return True
        return rp.can_fetch(USER_AGENT, url)

    def _load_robots(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urllib.parse.urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        try:
            self._throttle(parts.netloc)
            resp = self._session.get(robots_url, timeout=15)
            # Counted against the budget: a robots fetch is a request to someone else's server, and
            # a budget that quietly excludes them is not a budget.
            self.spent += 1
            self._record(Receipt(robots_url, resp.status_code, len(resp.content), 0, _now(), False, "robots"))
            if resp.status_code >= 400:
                return None
            rp.parse(resp.text.splitlines())
            return rp
        except requests.RequestException:
            return None

    def _throttle(self, host: str) -> None:
        interval = self.min_interval.get(host, self.min_interval.get("*", 2.0))
        last = self._last_hit.get(host)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    # -- fetching -------------------------------------------------------------------------

    def _cache_path(self, url: str) -> pathlib.Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        host = urllib.parse.urlsplit(url).netloc.replace(":", "_")
        return self.cache_dir / f"{host}__{digest}.json"

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        allow_cache: bool = True,
        note: str = "",
        expect_json: bool = True,
    ) -> tuple[int, Any]:
        """Return (status, payload). Payload is parsed JSON when `expect_json`, else text."""
        self._forbid_credentials(url, headers)
        cache_path = self._cache_path(url)
        if allow_cache and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age <= self.cache_ttl_s:
                doc = json.loads(cache_path.read_text(encoding="utf-8"))
                self._record(Receipt(url, doc["status"], doc["bytes"], 0, _now(), True, note))
                return doc["status"], doc["payload"]

        if self.offline:
            raise BudgetExhausted(f"offline mode and no cache entry for {url}")
        if self.spent >= self.budget:
            raise BudgetExhausted(f"request budget of {self.budget} exhausted before {url}")
        if not self._robots_ok(url):
            raise RobotsDisallowed(url)

        host = urllib.parse.urlsplit(url).netloc
        self._throttle(host)
        started = time.monotonic()
        merged = dict(headers or {})
        try:
            resp = self._session.get(url, headers=merged, timeout=timeout)
        except requests.RequestException as exc:
            # A DNS failure or a timeout on one company's website is data about that company, not a
            # reason to abandon a scan that has already spent ten minutes of rate limit.
            self.spent += 1
            self._record(
                Receipt(url, None, 0, int((time.monotonic() - started) * 1000), _now(), False,
                        f"{note} FAILED {type(exc).__name__}")
            )
            return 0, None
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self.spent += 1

        if expect_json:
            try:
                payload: Any = resp.json()
            except ValueError:
                payload = None
        else:
            payload = resp.text

        self._record(Receipt(url, resp.status_code, len(resp.content), elapsed_ms, _now(), False, note))
        if resp.status_code == 200:
            cache_path.write_text(
                json.dumps({"status": resp.status_code, "bytes": len(resp.content), "payload": payload}),
                encoding="utf-8",
            )
        return resp.status_code, payload

    def _record(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)
        if self.receipts_path:
            self.receipts_path.parent.mkdir(parents=True, exist_ok=True)
            with self.receipts_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt.as_dict()) + "\n")

    def summary(self) -> dict[str, Any]:
        by_host: dict[str, int] = {}
        for r in self.receipts:
            host = urllib.parse.urlsplit(r.url).netloc
            by_host[host] = by_host.get(host, 0) + 1
        return {
            "requests_made": self.spent,
            "budget": self.budget,
            "receipts": len(self.receipts),
            "cache_hits": sum(1 for r in self.receipts if r.from_cache),
            "by_host": by_host,
        }


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
