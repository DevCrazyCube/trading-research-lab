"""The candidate and evidence records.

The rule that shapes both classes: **nothing enters a briefing that is not an `Evidence` row**, and
every `Evidence` row carries a URL the recipient can open plus the UTC instant we observed it. If a
sentence in a briefing cannot point at one of these, it is either a parameter quote from RVO or it
does not get written.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any


@dataclasses.dataclass(frozen=True)
class Evidence:
    """One publicly checkable fact about a candidate."""

    source: str  # "github" | "peppol" | "website" | "tenderned"
    kind: str  # short machine key, e.g. "recent_push", "public_repo", "careers_page"
    claim_nl: str  # the sentence, in Dutch, as it may appear in a briefing
    url: str  # where the reader verifies it
    observed_utc: str
    detail: dict[str, Any] = dataclasses.field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Candidate:
    """A scanned organisation. `score` ranks it; `exclusions` is why it may be dropped."""

    candidate_id: str
    display_name: str
    github_login: str
    github_url: str
    website: str | None = None
    public_email: str | None = None
    location_text: str | None = None
    github_created_at: str | None = None
    public_repos: int | None = None
    followers: int | None = None
    evidence: list[Evidence] = dataclasses.field(default_factory=list)
    signals: dict[str, Any] = dataclasses.field(default_factory=dict)
    exclusions: list[str] = dataclasses.field(default_factory=list)
    score: float = 0.0
    scanned_utc: str = ""

    def add(self, ev: Evidence) -> None:
        self.evidence.append(ev)

    def evidence_of(self, kind: str) -> list[Evidence]:
        return [e for e in self.evidence if e.kind == kind]

    @property
    def excluded(self) -> bool:
        return bool(self.exclusions)

    def as_dict(self) -> dict[str, Any]:
        doc = dataclasses.asdict(self)
        doc["excluded"] = self.excluded
        return doc

    @classmethod
    def from_dict(cls, doc: dict[str, Any]) -> "Candidate":
        doc = dict(doc)
        doc.pop("excluded", None)
        evidence = [Evidence(**e) for e in doc.pop("evidence", [])]
        return cls(evidence=evidence, **doc)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
