"""WBSO benefit arithmetic, at RVO's published 2026 parameters.

This module computes what RVO's own calculator computes, and `tests/test_benefit.py` proves it by
reproducing the three worked examples RVO publishes, to the euro. That test is the only reason the
arithmetic is allowed anywhere near a briefing.

What this module deliberately does NOT do: decide whether anything qualifies. It turns an
*assumed* number of S&O hours into a benefit figure. The assumption is the whole uncertainty, and
`Scenario.assumption_nl` carries it into the briefing so it is never silently dropped.
"""
from __future__ import annotations

import dataclasses

from .params import WbsoParams


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One 'if you had N S&O hours' line. Every field is an assumption except the parameters."""

    label: str
    so_uren: int
    uurloon: int
    starter: bool
    kosten_mode: str  # "forfait" | "werkelijk"
    werkelijke_kosten: int
    loonkosten: int
    kosten_component: int
    grondslag: int
    voordeel: int
    assumption_nl: str

    @property
    def effective_rate(self) -> float:
        return self.voordeel / self.grondslag if self.grondslag else 0.0


def forfait_kosten(so_uren: int, p: WbsoParams) -> int:
    """RVO's flat cost allowance: EUR 10/hour up to 1,800 hours, EUR 4/hour above."""
    if so_uren < 0:
        raise ValueError("so_uren must be >= 0")
    below = min(so_uren, p.forfait_drempel_uren)
    above = max(0, so_uren - p.forfait_drempel_uren)
    return below * p.forfait_per_uur_tot_1800 + above * p.forfait_per_uur_boven_1800


def voordeel_from_grondslag(grondslag: float, p: WbsoParams, *, starter: bool = False) -> float:
    """Two-bracket credit on the S&O-grondslag. Starters get the higher first-bracket rate."""
    if grondslag < 0:
        raise ValueError("grondslag must be >= 0")
    schijf1_rate = p.tarief_schijf1_starters if starter else p.tarief_schijf1
    first = min(grondslag, p.grens_schijf1)
    second = max(0.0, grondslag - p.grens_schijf1)
    return schijf1_rate * first + p.tarief_schijf2 * second


def build_scenario(
    p: WbsoParams,
    *,
    label: str,
    so_uren: int,
    starter: bool = False,
    uurloon: int | None = None,
    kosten_mode: str = "forfait",
    werkelijke_kosten: int = 0,
    assumption_nl: str = "",
) -> Scenario:
    if kosten_mode not in ("forfait", "werkelijk"):
        raise ValueError("kosten_mode must be 'forfait' or 'werkelijk'")
    uurloon = p.default_uurloon if uurloon is None else uurloon
    loonkosten = so_uren * uurloon
    kosten = forfait_kosten(so_uren, p) if kosten_mode == "forfait" else werkelijke_kosten
    grondslag = loonkosten + kosten
    voordeel = voordeel_from_grondslag(grondslag, p, starter=starter)
    return Scenario(
        label=label,
        so_uren=so_uren,
        uurloon=uurloon,
        starter=starter,
        kosten_mode=kosten_mode,
        werkelijke_kosten=werkelijke_kosten,
        loonkosten=loonkosten,
        kosten_component=kosten,
        grondslag=round(grondslag),
        voordeel=round(voordeel),
        assumption_nl=assumption_nl,
    )


# Hours per developer-year used to build the illustrative ladder. These are ASSUMPTIONS, not
# measurements: 1,400 h is roughly a full-time year net of holidays and overhead, and the fractions
# below it exist because almost no developer bills 100% of the year to qualifying S&O work.
DEV_YEAR_HOURS = 1400
SO_SHARE_LADDER = (
    (0.25, "voorzichtig: een kwart van de tijd van 1 ontwikkelaar aan S&O"),
    (0.50, "midden: de helft van de tijd van 1 ontwikkelaar aan S&O"),
    (0.75, "ruim: driekwart van de tijd van 1 ontwikkelaar aan S&O"),
)


def scenario_ladder(
    p: WbsoParams, *, developers: int = 1, starter: bool = False
) -> list[Scenario]:
    """Three scenarios per assumed developer count, so the reader sees a range, not a number.

    A single euro figure reads as a promise. A ladder whose lowest rung is deliberately pessimistic
    reads as arithmetic, which is what it is.
    """
    if developers < 1:
        raise ValueError("developers must be >= 1")
    out = []
    for share, nl in SO_SHARE_LADDER:
        hours = int(round(developers * DEV_YEAR_HOURS * share))
        out.append(
            build_scenario(
                p,
                label=f"{int(share * 100)}% S&O-tijd",
                so_uren=hours,
                starter=starter,
                assumption_nl=(
                    f"aanname: {developers} ontwikkelaar(s) x {DEV_YEAR_HOURS} uur/jaar, "
                    f"{nl} = {hours} S&O-uren; S&O-uurloon EUR {p.default_uurloon} "
                    "(RVO-standaard als u in 2024 geen WBSO gebruikte); forfait voor kosten"
                ),
            )
        )
    return out


def zelfstandige_bedrag(p: WbsoParams, *, starter: bool = False) -> int:
    """Fixed deduction for a one-person business. No hours arithmetic; RVO fixes the amount."""
    return p.aftrek_zelfstandigen + (p.aftrek_zelfstandigen_starters_extra if starter else 0)


def nl_int(n: int) -> str:
    """Dutch thousands separator for a bare integer: 1800 -> 1.800."""
    return f"{int(n):,}".replace(",", ".")


NBSP = "\u00a0"


def eur(amount: float) -> str:
    """Dutch euro formatting: EUR 391.020 -- dot thousands, no cents, non-breaking space.

    The space after the sign is a NBSP on purpose: an amount that wraps to the next line as a bare
    "391.020" in an email client is an amount that can be misread.
    """
    return "\u20ac" + NBSP + nl_int(round(amount))
