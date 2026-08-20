#!/usr/bin/env python3
"""Build the cross-listing panel.

SIGNAL uses RAW (unadjusted) closes on both legs -- price LEVELS must be point-in-time, and
the log RATIO of two raw closes is the ratio an arbitrageur actually saw. Splits/ratio changes
are handled by a structural-break reset, not by retroactive adjustment.

P&L uses ADJUSTED US closes ONLY. No untradable price ever enters a return.
"""
import json, math, pathlib
import numpy as np
from scripts.t29_crosslist.xl_universe import ADR_MAP, REGIONS, COUNTRY_ETF, US_US_PAIRS

CACHE = pathlib.Path("/home/anont/meme/research/data/t29_crosslist_cache")
BREAK = 0.15          # log-spread jump that means "this is a corporate action, forget the level"
MAX_HOME_STALE = 4    # calendar days


def _load():
    us_raw = json.loads((CACHE / "us_bars_raw.json").read_text())
    us_adj = json.loads((CACHE / "us_bars_all.json").read_text())
    home = json.loads((CACHE / "home_bars.json").read_text())
    fxetf = json.loads((CACHE / "fx_etf_bars.json").read_text())
    return us_raw, us_adj, home, fxetf


def _byday(bars):
    return {b["t"][:10]: b for b in bars}


def _yb(series):
    return {r["d"]: r for r in series["rows"]} if series else {}


def _ffill_lookup(dmap, dates):
    """value on date d, else most recent <= d within MAX_HOME_STALE calendar days."""
    import datetime as dt
    keys = sorted(dmap)
    out = {}
    j = 0
    for d in dates:
        while j < len(keys) and keys[j] <= d:
            j += 1
        if j == 0:
            continue
        k = keys[j - 1]
        gap = (dt.date.fromisoformat(d) - dt.date.fromisoformat(k)).days
        if gap <= MAX_HOME_STALE:
            out[d] = (dmap[k], gap)
    return out


def build_panel():
    us_raw, us_adj, home, fxetf = _load()
    us_dates = sorted({b["t"][:10] for s in us_raw.values() for b in s})
    fx = {k: _yb(v) for k, v in fxetf.items()}
    fx_l = {k: _ffill_lookup({d: r["c"] for d, r in v.items()}, us_dates) for k, v in fx.items()}

    names = {}
    census = []
    for u, (h, reg) in ADR_MAP.items():
        if u not in us_raw or u not in us_adj or h not in home:
            census.append({"us": u, "home": h, "region": reg, "status": "missing_leg",
                           "us_ok": u in us_raw, "home_ok": h in home})
            continue
        R, A = _byday(us_raw[u]), _byday(us_adj[u])
        H = _ffill_lookup({d: r["c"] for d, r in _yb(home[h]).items()}, us_dates)
        F = fx_l.get(REGIONS[reg]["fx"], {})
        rows = []
        for d in us_dates:
            if d not in R or d not in A or d not in H or d not in F:
                continue
            pu, ph, f = R[d]["c"], H[d][0], F[d][0]
            if pu <= 0 or ph <= 0 or f <= 0:
                continue
            rows.append((d, math.log(pu) - math.log(ph) - math.log(f), A[d]["c"],
                         R[d]["c"] * R[d]["v"], R[d]["c"], H[d][1]))
        if len(rows) < 300:
            census.append({"us": u, "home": h, "region": reg, "status": "too_short",
                           "n": len(rows)})
            continue
        names[u] = {"home": h, "region": reg,
                    "d": [r[0] for r in rows],
                    "s": np.array([r[1] for r in rows]),
                    "px_adj": np.array([r[2] for r in rows]),
                    "dv": np.array([r[3] for r in rows]),
                    "px_raw": np.array([r[4] for r in rows]),
                    "stale": np.array([r[5] for r in rows])}
        census.append({"us": u, "home": h, "region": reg, "status": "ok", "n": len(rows),
                       "first": rows[0][0], "last": rows[-1][0],
                       "median_stale_days": float(np.median([r[5] for r in rows]))})
    return names, census, us_dates, us_raw, us_adj


def corwin_schultz(bars, lo, hi):
    """Standard Corwin-Schultz: negatives set to zero, then AVERAGED.

    An earlier version took the MEDIAN of the zero-floored series. For a high-volatility
    name CS is negative on more than half the days, so the median is exactly 0.00 -- a
    zero where a measurement is missing, which is the one cost failure this programme has
    a written rule against. Mean-of-zero-floored is the estimator's own convention, and it
    is combined below with a measured NBBO floor and a half-tick floor so that a degenerate
    CS can never price a crossing at free.
    """
    ds = sorted(d for d in bars if lo <= d <= hi)
    k = 3 - 2 * math.sqrt(2)
    vals, px = [], []
    for i in range(len(ds) - 1):
        a, b = bars[ds[i]], bars[ds[i + 1]]
        if min(a["l"], b["l"]) <= 0:
            continue
        beta = math.log(a["h"] / a["l"]) ** 2 + math.log(b["h"] / b["l"]) ** 2
        gamma = math.log(max(a["h"], b["h"]) / min(a["l"], b["l"])) ** 2
        alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
        s = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha))
        vals.append(max(s, 0.0))
        px.append(a["c"])
    if not vals:
        return None, None
    return float(np.mean(vals)), float(np.median(px))


def half_spreads(us_raw, syms, lo, hi, quotes=None, detail=None):
    """half-spread = max(Corwin-Schultz/2, measured NBBO/2 inside this window, half a tick).

    Three independent lower bounds, and the largest wins. The NBBO term is a real
    point-in-time SIP measurement sampled inside the same window (xl_quotes.py); the
    half-tick term is the arithmetic floor no US equity crossing can beat.
    """
    qwin = {}
    if quotes:
        for d, per in quotes.items():
            if not (lo <= d <= hi):
                continue
            for s, bp in per.items():
                qwin.setdefault(s, []).append(bp)
    out = {}
    for s in syms:
        if s not in us_raw:
            continue
        cs, medpx = corwin_schultz(_byday(us_raw[s]), lo, hi)
        if cs is None or not medpx:
            out[s] = None
            continue
        tick_floor = 0.005 / medpx                       # half of a one-cent tick
        nbbo = qwin.get(s)
        nbbo_h = (float(np.median(nbbo)) * 1e-4 / 2.0) if nbbo else 0.0
        out[s] = max(cs / 2.0, nbbo_h, tick_floor)
        if detail is not None:
            detail[s] = {"cs_half_bp": round(cs / 2 * 1e4, 2),
                         "nbbo_half_bp": round(nbbo_h * 1e4, 2),
                         "tick_floor_bp": round(tick_floor * 1e4, 2),
                         "used_bp": round(out[s] * 1e4, 2),
                         "nbbo_samples": len(nbbo or [])}
    return out
