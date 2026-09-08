#!/usr/bin/env python3
"""T3 diagnostics -- EXPLORATORY, NOT PRE-REGISTERED. No verdict may be taken from this file.

The frozen test has already run and returned its verdict. These two measurements exist only to
explain *why* it landed where it did, and to price the one variant the failure points at.

D1. Bid-ask bounce. The frozen rule enters at the 15:59 last TRADE print. The fade-buy leg is by
    construction the names that just fell, whose last print is disproportionately at the BID, and
    the fade-sell leg the names that just rose, whose last print is at the ASK. Marking those
    prints to an unbiased opening auction manufactures up to one full half-spread per leg of pure
    microstructure. D1 replaces the entry print with the official CLOSING AUCTION price -- a
    single-price auction, so bounce-free on both legs -- leaving the signal untouched. Whatever
    survives is not bounce.

D2. The both-legs-auction variant. NYSE/Nasdaq stop accepting MOC orders at 15:50, so a signal
    measured at 15:59 can never be executed in the closing auction. A signal measured over
    15:29 -> 15:49 CAN: the order goes in before the cutoff, fills in the closing auction, and
    exits in the opening auction. Both legs are single-price auctions, so the modelled spread is
    ZERO on both sides. This is a DIFFERENT RULE and it is not covered by the frozen
    pre-registration; a number produced here is a reason to pre-register it, never a result.
"""

from __future__ import annotations

import gzip
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                   # noqa: E402
from scripts.trading_bot.stats import annualised_sharpe, moments            # noqa: E402


def load():
    with gzip.open(t3.CACHE / "panel.json.gz", "rt") as fh:
        panel = json.load(fh)["panel"]
    auct = t3.auctions([])          # cache hit; the symbol list is unused when cached
    cal = t3.calendar()
    days = [r["date"] for r in cal]
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    return panel, auct, nxt


def report(name, rets):
    m = moments(rets)
    return {"variant": name, "n_nights": m["n"],
            "mean_per_night_bp": m["mean"] * 1e4,
            "t_stat": m["mean"] / m["sd"] * math.sqrt(m["n"]),
            "annualised_sharpe": annualised_sharpe(rets, 252),
            "annualised_return_pct": m["mean"] * 252 * 100}


def main():
    panel, auct, nxt = load()
    uni = t3.build_universe(500)
    cut, top_n = 0.10, 500

    periods = {"design 2016-2021": lambda d: d <= t3.DESIGN_END,
               "HELD-OUT 2022-2026": lambda d: d >= t3.TEST_START}
    out = {}

    for pname, keep in periods.items():
        d1, d2 = [], []
        for day in sorted(panel):
            if not keep(day):
                continue
            nd = nxt.get(day)
            allowed = set(uni.get(day[:7], [])[:top_n])
            rows = []
            for sym, r10, r30, _overnight_from_print in panel[day]:
                if sym not in allowed:
                    continue
                a_today = auct.get(f"{sym}|{day}")
                a_next = auct.get(f"{sym}|{nd}")
                if not a_today or "c" not in a_today or not a_next or "o" not in a_next:
                    continue
                rows.append((r10, r30, a_next["o"] / a_today["c"] - 1.0))
            if len(rows) < 100:
                continue
            k = max(1, int(len(rows) * cut))

            # D1: same 10-minute signal, entry at the closing auction instead of the last print.
            by10 = sorted(rows, key=lambda r: r[0])
            d1.append(0.5 * sum(r[2] for r in by10[:k]) / k
                      - 0.5 * sum(r[2] for r in by10[-k:]) / k)

            # D2: the 15:29 -> 15:49 signal, i.e. everything known BEFORE the 15:50 MOC cutoff.
            #
            # The panel stores r10 = p59/p49-1 and r30 = p59/p29-1, both of which END at 15:59.
            # Ranking on r30 would place an order at 15:50 using nine minutes of the future --
            # the exact lookahead the T2 harness exists to make impossible, reintroduced here by
            # hand. The pre-cutoff return is recovered exactly:
            #     (1+r30)/(1+r10) = (p59/p29)/(p59/p49) = p49/p29
            by30 = sorted(rows, key=lambda r: (1.0 + r[1]) / (1.0 + r[0]) - 1.0)
            d2.append(0.5 * sum(r[2] for r in by30[:k]) / k
                      - 0.5 * sum(r[2] for r in by30[-k:]) / k)

        out[pname] = {
            "D1_close_auction_entry_10min_signal": report("D1", d1),
            "D2_auction_to_auction_1529_1549_signal": report("D2", d2),
        }

    print(json.dumps(out, indent=2))
    (ROOT / "research" / "trading_bot" / "T3_DIAGNOSTICS.json").write_text(
        json.dumps({"WARNING": "EXPLORATORY, NOT PRE-REGISTERED. No verdict follows from this "
                               "file. D2 in particular is a different rule and needs its own "
                               "freeze before any number of its is believed.",
                    "results": out}, indent=2))


if __name__ == "__main__":
    main()
