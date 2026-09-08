"""Frozen RVO parameter loading.

The parameters are *not* constants in code. They live in `params/rvo_wbso_2026.json` with the
source URL, the access date and the literal quote each number was read from, because a briefing
that states "36% of the first EUR 391,020" is making a factual claim about Dutch tax law on the
owner's letterhead. When RVO changes a number, exactly one file changes and every briefing
regenerated afterwards carries the new citation.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pathlib
from typing import Any

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PARAMS_PATH = PACKAGE_ROOT / "params" / "rvo_wbso_2026.json"

# How stale the frozen parameters may be before the CLI starts complaining. RVO republishes
# parameters yearly and the calendar page is edited more often than that; 120 days is chosen so a
# freeze made at the start of the Sept-Dec selling season is re-checked before the season ends.
STALENESS_WARN_DAYS = 120


class ParameterError(ValueError):
    """The frozen parameter file is missing, malformed, or internally inconsistent."""


@dataclasses.dataclass(frozen=True)
class WbsoParams:
    scheme_year: int
    frozen_on: dt.date
    tarief_schijf1: float
    tarief_schijf1_starters: float
    grens_schijf1: int
    tarief_schijf2: float
    aftrek_zelfstandigen: int
    aftrek_zelfstandigen_starters_extra: int
    default_uurloon: int
    forfait_per_uur_tot_1800: int
    forfait_per_uur_boven_1800: int
    forfait_drempel_uren: int
    deadlines: dict[str, Any]
    voorwaarden_quotes: tuple[str, ...]
    sources: tuple[dict[str, Any], ...]
    worked_examples: tuple[dict[str, Any], ...]
    raw: dict[str, Any]

    def source_urls(self) -> list[str]:
        return [str(s["url"]) for s in self.sources]

    def age_days(self, today: dt.date | None = None) -> int:
        return ((today or dt.date.today()) - self.frozen_on).days

    def is_stale(self, today: dt.date | None = None) -> bool:
        return self.age_days(today) > STALENESS_WARN_DAYS


def load_params(path: pathlib.Path | str | None = None) -> WbsoParams:
    path = pathlib.Path(path) if path else DEFAULT_PARAMS_PATH
    if not path.exists():
        raise ParameterError(f"frozen parameter file not found: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != "wbso-params/1":
        raise ParameterError(f"unexpected schema {doc.get('schema')!r} in {path}")

    rates = doc["rates"]
    grond = doc["grondslag"]
    sources = tuple(doc.get("sources", ()))
    if not sources:
        raise ParameterError("parameter file carries no sources; every number must be traceable")
    for src in sources:
        if not src.get("url") or not src.get("accessed_utc") or not src.get("quotes"):
            raise ParameterError(f"source entry missing url/accessed_utc/quotes: {src}")

    voorwaarden: list[str] = []
    for src in sources:
        if src["url"].rstrip("/").endswith("voorwaarden"):
            voorwaarden = list(src["quotes"])

    params = WbsoParams(
        scheme_year=int(doc["scheme_year"]),
        frozen_on=dt.date.fromisoformat(doc["frozen_on"]),
        tarief_schijf1=float(rates["tarief_eerste_schijf"]),
        tarief_schijf1_starters=float(rates["tarief_eerste_schijf_starters"]),
        grens_schijf1=int(rates["grens_eerste_schijf_eur"]),
        tarief_schijf2=float(rates["tarief_tweede_schijf"]),
        aftrek_zelfstandigen=int(rates["so_aftrek_zelfstandigen_eur"]),
        aftrek_zelfstandigen_starters_extra=int(rates["so_aftrek_zelfstandigen_starters_extra_eur"]),
        default_uurloon=int(grond["default_so_uurloon_eur"]),
        forfait_per_uur_tot_1800=int(grond["forfait_kosten_eur_per_uur_first_1800"]),
        forfait_per_uur_boven_1800=int(grond["forfait_kosten_eur_per_uur_above_1800"]),
        forfait_drempel_uren=int(grond["forfait_threshold_hours"]),
        deadlines=dict(doc["deadlines"]),
        voorwaarden_quotes=tuple(voorwaarden),
        sources=sources,
        worked_examples=tuple(doc.get("worked_examples_published_by_rvo", ())),
        raw=doc,
    )
    _validate(params)
    return params


def _validate(p: WbsoParams) -> None:
    if not 0 < p.tarief_schijf2 < p.tarief_schijf1 < p.tarief_schijf1_starters <= 1:
        raise ParameterError(
            "rate ordering is wrong: expected 0 < schijf2 < schijf1 < schijf1_starters <= 1, got "
            f"{p.tarief_schijf2}, {p.tarief_schijf1}, {p.tarief_schijf1_starters}"
        )
    if p.grens_schijf1 <= 0:
        raise ParameterError("grens_eerste_schijf_eur must be positive")
    if p.default_uurloon <= 0 or p.forfait_per_uur_tot_1800 < p.forfait_per_uur_boven_1800:
        raise ParameterError("grondslag parameters are implausible")
    if not p.worked_examples:
        raise ParameterError(
            "no RVO worked examples frozen; the benefit arithmetic would then be untested"
        )
