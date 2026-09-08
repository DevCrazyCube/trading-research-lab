#!/usr/bin/env python3
"""INVENT-R3 -- EVENT-CONDITIONAL SIGNALS ON A PREDICTABLE CATALYST CALENDAR.

Theme: the signal is conditioned on a KNOWN event schedule (earnings, FOMC, NFP,
triple witching, month/quarter-end index rebalance, Russell recon).

Everything here runs off two already-paid-for caches:
  research/data/inv3_cache/panel.npz      (built from t17_cache: 3521 syms x 2669 days OHLCV)
  research/data/t15_cache/earnings_8k.jsonl  (72,649 8-K item-2.02 filings, UTC to the second,
                                              WITH the item-code set of each filing)
  research/data/t7_cache/corporate_actions_all.json.gz (splits + cash dividends)

DESIGN  2016-01-04 .. 2021-12-31
HOLDOUT 2022-01-03 .. 2026-08-14   (not looked at until every design number is frozen)

Point-in-time discipline
------------------------
* An 8-K is usable only from the first session close that is strictly after its
  acceptance timestamp (15:55 ET cut, so a 16:05 filing is first tradeable at the NEXT close).
* Firm-history conditioners (median filing hour, reporting lag) use only that firm's
  own EARLIER filings.
* Peer sets are refit each January from the PRIOR calendar year's returns only.
* Predicted announcement dates use last realised filing + 91 calendar days.

No look-ahead is possible from the panel itself: every signal reads bars up to and
including day t and every position is entered at the close of day t.
"""
import datetime
import gzip
import json
import os
from collections import defaultdict
from zoneinfo import ZoneInfo

import numpy as np

ROOT = "/home/anont/meme"
PANEL = f"{ROOT}/research/data/inv3_cache/panel.npz"
E8K = f"{ROOT}/research/data/t15_cache/earnings_8k.jsonl"
S2C = f"{ROOT}/research/data/t15_cache/symbol_to_cik.json.gz"
CA = f"{ROOT}/research/data/t7_cache/corporate_actions_all.json.gz"
OUT = f"{ROOT}/research/data/inv3_cache"
ET = ZoneInfo("America/New_York")

DESIGN_END = "2021-12-31"
HOLDOUT_START = "2022-01-03"

# FOMC statement dates (scheduled meetings; the 2020 emergency cuts included because
# they were unscheduled -- flagged separately so a "known schedule" test can drop them).
FOMC = """
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-03-15 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29
""".split()


# ===========================================================================
# panel + returns
# ===========================================================================
def load_panel():
    z = np.load(PANEL, allow_pickle=False)
    days = [str(d) for d in z["dates"]]
    syms = [str(s) for s in z["syms"]]
    o = z["o"].astype(np.float32)
    h = z["h"].astype(np.float32)
    lo = z["l"].astype(np.float32)
    c = z["c"].astype(np.float32)
    v = z["v"].astype(np.float32)
    return days, syms, o, h, lo, c, v


def build_returns(days, syms, o, c, v):
    """close-to-close TOTAL return (dividend added back), split ex-dates masked."""
    nS, nD = c.shape
    didx = {d: i for i, d in enumerate(days)}
    sidx = {s: i for i, s in enumerate(syms)}

    with gzip.open(CA, "rt") as fh:
        ca = json.load(fh)

    div = np.zeros_like(c)
    for rec in ca["cash_dividends"]:
        j = sidx.get(rec["symbol"])
        i = didx.get(rec["ex_date"])
        if j is not None and i is not None and rec.get("rate"):
            div[j, i] += float(rec["rate"])

    splitmask = np.zeros(c.shape, dtype=bool)
    for key in ("forward_splits", "reverse_splits", "unit_splits", "stock_dividends",
                "spin_offs", "reorganizations"):
        for rec in ca.get(key, []):
            j = sidx.get(rec.get("symbol", ""))
            i = didx.get(rec.get("ex_date", ""))
            if j is not None and i is not None:
                splitmask[j, max(0, i - 1):i + 2] = True

    prev = np.full_like(c, np.nan)
    prev[:, 1:] = c[:, :-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        rcc = (c + div) / prev - 1.0
        roc = c / o - 1.0                       # open -> close, same session
        rco = np.full_like(c, np.nan)
        rco[:, 1:] = o[:, 1:] / c[:, :-1] - 1.0  # prev close -> open (the gap)
    bad = splitmask | ~np.isfinite(rcc) | (np.abs(rcc) > 0.9)
    rcc[bad] = np.nan
    roc[~np.isfinite(roc) | (np.abs(roc) > 0.9)] = np.nan
    rco[~np.isfinite(rco) | (np.abs(rco) > 0.9)] = np.nan

    dv = c * v                                   # dollar volume
    return rcc, roc, rco, dv


# ===========================================================================
# earnings events with 8-K metadata
# ===========================================================================
def build_earnings(days, syms):
    didx = {d: i for i, d in enumerate(days)}
    sidx = {s: i for i, s in enumerate(syms)}
    with gzip.open(S2C, "rt") as fh:
        cikmap = json.load(fh)["cik"]
    cik2cols = defaultdict(list)
    for s, ck in cikmap.items():
        j = sidx.get(s)
        if j is not None and ck is not None:
            cik2cols[int(ck)].append(j)

    # first session index whose close is strictly after a given ET datetime
    def entry_index(dt_et):
        d = dt_et.date().isoformat()
        cut = dt_et.replace(hour=15, minute=55, second=0, microsecond=0)
        i = didx.get(d)
        if i is not None and dt_et < cut:
            return i
        # next trading day at or after d+1
        import bisect
        k = bisect.bisect_right(days, d)
        return k if k < len(days) else None

    events = []   # (col, entry_idx, ann_date_idx_or_None, hour_et, itemset, period_key)
    with open(E8K) as fh:
        for line in fh:
            cik, evs = json.loads(line)
            cols = cik2cols.get(int(cik))
            if not cols:
                continue
            recs = []
            for d, ts, items, acc in evs:
                dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(ET)
                recs.append((dt, d, items))
            recs.sort(key=lambda x: x[0])
            hist_hours = []
            hist_dates = []
            for dt, d, items in recs:
                ei = entry_index(dt)
                if ei is None or ei >= len(days):
                    hist_hours.append(dt.hour + dt.minute / 60.0)
                    hist_dates.append(dt.date())
                    continue
                hour = dt.hour + dt.minute / 60.0
                # firm-history conditioners from EARLIER filings only
                med_hour = float(np.median(hist_hours[-4:])) if len(hist_hours) >= 3 else np.nan
                lag_delta = np.nan
                if len(hist_dates) >= 4:
                    prior = hist_dates[-4]           # same quarter, one year earlier
                    lag_delta = (dt.date() - prior).days - 365
                for j in cols:
                    events.append(dict(col=j, entry=ei, date=d, hour=hour,
                                       med_hour=None if not np.isfinite(med_hour) else med_hour,
                                       lag_delta=None if not np.isfinite(lag_delta) else int(lag_delta),
                                       items=items))
                hist_hours.append(hour)
                hist_dates.append(dt.date())
    return events


def main():
    os.makedirs(OUT, exist_ok=True)
    days, syms, o, h, lo, c, v = load_panel()
    rcc, roc, rco, dv = build_returns(days, syms, o, c, v)
    np.savez_compressed(f"{OUT}/rets.npz", days=np.array(days), syms=np.array(syms),
                        rcc=rcc, roc=roc, rco=rco, dv=dv.astype(np.float32),
                        o=o, h=h, l=lo, c=c)
    ev = build_earnings(days, syms)
    with open(f"{OUT}/events.json", "w") as fh:
        json.dump(ev, fh)
    print(f"days {len(days)} syms {len(syms)} events {len(ev)}")
    print("rcc finite frac %.3f" % float(np.isfinite(rcc).mean()))


if __name__ == "__main__":
    main()
