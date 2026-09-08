#!/usr/bin/env python3
"""INVENT-R3 -- DEALER POSITIONING / OPTIONS-FLOW, tracks B (price-only footprints)
and C (0DTE / VIX1D era).  Track A (real per-strike gamma) lives in the same file
but only runs once research/data/gex_cache/exp is populated.

Every formula carries: a one-sentence mechanism, a sign FIXED BEFORE the data is
read, a design window and an untouched holdout window.

Costs: charged per side on |dw| each rebalance.  Headline 1.5 bp (SPY intraday
marketable, above the 0.13 bp measured 15:45 half-spread + 0.15 bp regulatory);
rungs 0.5 / 1.0 / 1.5 / 3.0 reported.
"""
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

ROOT = "/home/anont/meme"
OUT = os.path.join(ROOT, "research/trading_bot")
HEADLINE_BP = 1.5
RUNGS = [0.5, 1.0, 1.5, 3.0]

# ---------------------------------------------------------------- calendar ---


def _nth_weekday(y, month, weekday, n):
    d = date(y, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(days=7 * (n - 1))


def et_offset(d: date) -> int:
    """US eastern UTC offset. DST = 2nd Sun Mar .. 1st Sun Nov (post-2007)."""
    start = _nth_weekday(d.year, 3, 6, 2)
    end = _nth_weekday(d.year, 11, 6, 1)
    return -4 if start <= d < end else -5


def third_friday(y, m):
    d = date(y, m, 1)
    d += timedelta(days=(4 - d.weekday()) % 7)
    return d + timedelta(days=14)


# ------------------------------------------------------------ intraday panel ---


def build_sessions():
    bars = json.load(open(os.path.join(ROOT, "research/data/spy_30min_bars.json")))
    by_day = defaultdict(dict)
    for b in bars:
        ts = datetime.strptime(b["t"], "%Y-%m-%dT%H:%M:%SZ")
        d0 = ts.date()
        off = et_offset(d0)
        et = ts + timedelta(hours=off)
        if et.date() != d0:
            continue
        by_day[et.date().isoformat()][et.strftime("%H:%M")] = b
    sess = {}
    for d, m in by_day.items():
        need = ["09:30", "10:00", "12:30", "13:30", "14:30", "15:30"]
        if not all(k in m for k in need):
            continue
        sess[d] = {
            "open": m["09:30"]["o"],
            "p10": m["09:30"]["c"],
            "p11": m["10:00"]["c"],
            "p13": m["12:30"]["c"],
            "p14": m["13:30"]["c"],
            "p15": m["14:30"]["c"],
            "close": m["15:30"]["c"],
            "hi": max(m[k]["h"] for k in need),
            "lo": min(m[k]["l"] for k in need),
            "vol": sum(m[k]["v"] for k in need),
        }
    return dict(sorted(sess.items()))


# --------------------------------------------------------------- cboe series ---


def cboe(name, col=None):
    p = os.path.join(ROOT, "research/data/optimp_cache", f"cboe_{name}.csv")
    out = {}
    with open(p) as f:
        hdr = f.readline().strip().split(",")
        ci = hdr.index(col) if col else (hdr.index("CLOSE") if "CLOSE" in hdr else 1)
        for line in f:
            parts = line.strip().split(",")
            if len(parts) <= ci:
                continue
            try:
                mm, dd, yy = parts[0].split("/")
                v = float(parts[ci])
            except ValueError:
                continue
            if v <= 0:
                continue
            out[f"{yy}-{mm}-{dd}"] = v
    return out


# ------------------------------------------------------------------ stats -----


def sharpe(rets):
    n = len(rets)
    if n < 20:
        return 0.0, 0.0, n
    mu = sum(rets) / n
    var = sum((r - mu) ** 2 for r in rets) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0, 0.0, n
    s = mu / sd * math.sqrt(252)
    t = mu / sd * math.sqrt(n)
    return s, t, n


def zmap(vals):
    """Expanding-window z-score: strictly causal, min 250 obs."""
    out, s, s2 = [], 0.0, 0.0
    for i, v in enumerate(vals):
        if i >= 250:
            mu = s / i
            sd = math.sqrt(max(1e-12, s2 / i - mu * mu))
            out.append((v - mu) / sd if sd > 0 else 0.0)
        else:
            out.append(None)
        s += v
        s2 += v * v
    return out


def evaluate(name, mech, sign_note, obs, dwin, hwin, cost_bp=HEADLINE_BP):
    """obs = list of (date, weight, gross_return). Cost charged on |dw|."""
    obs = sorted(obs)
    res = {}
    for tag, (a, b) in (("design", dwin), ("holdout", hwin)):
        sel = [o for o in obs if a <= o[0] <= b]
        rows = {}
        for rung in RUNGS:
            prev = 0.0
            rets = []
            for _, w, gr in sel:
                rets.append(w * gr - abs(w - prev) * rung * 1e-4)
                prev = w
            s, t, n = sharpe(rets)
            rows[str(rung)] = round(s, 3)
            if rung == cost_bp:
                res[tag] = {
                    "sharpe": round(s, 3), "t": round(t, 2), "n": n,
                    "mean_bp": round(1e4 * (sum(rets) / n if n else 0), 3),
                }
        res[tag]["rungs"] = rows
        res[tag]["gross_sharpe"] = round(sharpe([w * gr for _, w, gr in sel])[0], 3)
    return {"name": name, "mechanism": mech, "sign": sign_note, **res}


# =============================== TRACK B ======================================


def track_b(sess, vix9, vix3, vix, skew):
    days = list(sess)
    di = {d: i for i, d in enumerate(days)}
    F = []
    DWIN = ("2016-01-01", "2021-12-31")
    HWIN = ("2022-01-01", "2026-12-31")

    def ret(d, a, b):
        return sess[d][b] / sess[d][a] - 1.0

    # --- pinning family ------------------------------------------------------
    def pin(name, grid, day_filter, t_from, t_to, band):
        obs = []
        for d in days:
            if not day_filter(d):
                continue
            s = sess[d][t_from]
            k = round(s / grid) * grid
            dist = (s - k) / s
            if abs(dist) > band:
                continue
            w = -1.0 if dist > 0 else 1.0  # pulled TOWARD the strike
            obs.append((d, w, sess[d][t_to] / s - 1.0))
        return evaluate(
            name,
            f"dealers long gamma at the heavy ${grid} strike pin spot to it into the "
            f"{t_to} mark",
            "position points TOWARD the nearest strike; fixed before any fit",
            obs, DWIN, HWIN)

    is_mfri = lambda d: date.fromisoformat(d) == third_friday(*map(int, d.split("-")[:2]))
    is_fri = lambda d: date.fromisoformat(d).weekday() == 4
    allday = lambda d: True

    F.append(pin("B1_PIN_MONTHLY_1D", 1.0, is_mfri, "p14", "close", 0.0020))
    F.append(pin("B2_PIN_FRIDAY_1D", 1.0, is_fri, "p14", "close", 0.0020))
    F.append(pin("B3_PIN_ALLDAY_1D", 1.0, allday, "p14", "close", 0.0020))
    F.append(pin("B4_PIN_FRIDAY_5D", 5.0, is_fri, "p14", "close", 0.0020))
    F.append(pin("B5_PIN_MONTHLY_5D", 5.0, is_mfri, "p13", "close", 0.0030))

    # --- B6 post-OpEx gamma roll-off ----------------------------------------
    obs = []
    for i, d in enumerate(days[:-1]):
        if not is_mfri(d):
            continue
        nd = days[i + 1]
        obs.append((nd, -1.0, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "B6_POSTOPEX_ROLLOFF", "monthly expiry retires the dealer long-gamma book; the "
        "clamp on downside is released the next session",
        "SHORT the session after monthly expiry; sign from the mechanism",
        obs, DWIN, HWIN))

    # --- B7 OpEx-week reversal amplification --------------------------------
    def opex_week(d):
        dd = date.fromisoformat(d)
        tf = third_friday(dd.year, dd.month)
        return 0 <= (tf - dd).days <= 4 and dd.weekday() < 5

    for tag, filt in (("B7_OPEXWEEK_REV", opex_week),
                      ("B8_NONOPEX_REV", lambda d: not opex_week(d))):
        obs = []
        for i in range(1, len(days)):
            d, p = days[i], days[i - 1]
            if not filt(d):
                continue
            r0 = sess[p]["close"] / sess[p]["open"] - 1.0
            w = -1.0 if r0 > 0 else 1.0
            obs.append((d, w, sess[d]["close"] / sess[d]["open"] - 1.0))
        F.append(evaluate(
            tag, "peak dealer long gamma during expiry week clamps and reverses the "
            "prior session's move", "FADE the prior session; sign fixed by mechanism",
            obs, DWIN, HWIN))

    # --- B9/B10 gamma-sign proxy applied INTRADAY ---------------------------
    ratio = {d: vix9[d] / vix3[d] for d in vix9 if d in vix3}
    rdays = sorted(ratio)
    rz = dict(zip(rdays, zmap([ratio[d] for d in rdays])))

    def gsign(name, lo, hi, mode, t_sig, t_entry, t_exit):
        obs = []
        for i in range(1, len(days)):
            d, p = days[i], days[i - 1]
            z = rz.get(p)
            if z is None or not (lo <= z < hi):
                continue
            r0 = sess[d][t_sig] / sess[d]["open"] - 1.0
            if r0 == 0:
                continue
            w = (-1.0 if mode == "rev" else 1.0) * (1.0 if r0 > 0 else -1.0)
            obs.append((d, w, sess[d][t_exit] / sess[d][t_entry] - 1.0))
        return evaluate(
            name,
            "VIX9D/VIX3M is the sign of the dealer gamma book: deep contango = long "
            "gamma = intraday moves get absorbed; backwardation = short gamma = they "
            "get amplified",
            f"{'FADE' if mode=='rev' else 'FOLLOW'} the morning move; fixed by sign of gamma",
            obs, DWIN, HWIN)

    F.append(gsign("B9_GSIGN_CONTANGO_FADE", -9, -0.5, "rev", "p10", "p10", "close"))
    F.append(gsign("B10_GSIGN_BACKWARD_RIDE", 0.5, 9, "mom", "p10", "p10", "close"))
    F.append(gsign("B11_GSIGN_CONTANGO_LASTHR", -9, -0.5, "rev", "p15", "p15", "close"))
    F.append(gsign("B12_GSIGN_BACKWARD_LASTHR", 0.5, 9, "mom", "p15", "p15", "close"))

    # --- B13 vanna: skew level x vol change ---------------------------------
    vdays = sorted(set(skew) & set(vix) & set(sess))
    skz = dict(zip(vdays, zmap([skew[d] for d in vdays])))
    obs = []
    for i in range(1, len(vdays)):
        d, p = vdays[i], vdays[i - 1]
        if d not in di or di[d] == 0:
            continue
        z = skz.get(p)
        if z is None:
            continue
        dv = vix[p] / vix[vdays[i - 2]] - 1.0 if i >= 2 else 0.0
        sig = z * (-dv)
        w = max(-1.0, min(1.0, sig * 3.0))
        nd = days[di[d] + 1] if di[d] + 1 < len(days) else None
        if nd is None:
            continue
        obs.append((nd, w, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "B13_VANNA_SKEWxDVOL", "dealers short a rich put wing carry positive vanna: a "
        "vol DROP mechanically raises their delta and forces spot buying, scaled by how "
        "rich the wing is",
        "LONG when skew is rich AND vol fell; product sign fixed by the vanna identity",
        obs, DWIN, HWIN))

    # --- B14 charm into monthly expiry --------------------------------------
    obs = []
    for i in range(1, len(days) - 1):
        d = days[i]
        dd = date.fromisoformat(d)
        tf = third_friday(dd.year, dd.month)
        k = (tf - dd).days
        if not (0 < k <= 4):
            continue
        z = skz.get(days[i - 1])
        if z is None or z <= 0:
            continue
        nd = days[i + 1]
        obs.append((nd, 1.0, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "B14_CHARM_EXPIRY_DRIFT", "charm: as monthly expiry approaches, the delta of a "
        "dealer's short OTM put decays toward zero, forcing him to buy back the spot he "
        "sold as a hedge",
        "LONG the run-in to monthly expiry when the put wing is rich; fixed by charm sign",
        obs, DWIN, HWIN))

    # --- B15 control: no options information at all -------------------------
    obs = []
    for i in range(1, len(days)):
        d, p = days[i], days[i - 1]
        r0 = sess[d]["p10"] / sess[d]["open"] - 1.0
        w = -1.0 if r0 > 0 else 1.0
        obs.append((d, w, sess[d]["close"] / sess[d]["p10"] - 1.0))
    F.append(evaluate(
        "B15_CONTROL_UNCOND_FADE", "CONTROL -- unconditional intraday fade, contains no "
        "options or dealer information whatsoever",
        "FADE always. Any dealer formula must beat THIS, not zero.",
        obs, DWIN, HWIN))

    # --- B16/B17 INTERACTION with the live basket: does the gamma sign modulate
    #     the overnight reversal that T3 already trades?
    for tag, lo, hi, note in (
            ("B16_OVERNIGHT_REV_LONGGAMMA", -9, -0.5,
             "a long-gamma dealer book has to buy the close down / sell it up, and the "
             "flow unwinds against him overnight -- the reversal T3 trades should be "
             "LARGER here"),
            ("B17_OVERNIGHT_REV_SHORTGAMMA", 0.5, 9,
             "a short-gamma book chases the close, so the overnight session should "
             "CONTINUE, not revert")):
        obs = []
        for i in range(1, len(days) - 1):
            d, p = days[i], days[i - 1]
            z = rz.get(p)
            if z is None or not (lo <= z < hi):
                continue
            r0 = sess[d]["close"] / sess[d]["open"] - 1.0
            if r0 == 0:
                continue
            w = (-1.0 if lo < 0 else 1.0) * (1.0 if r0 > 0 else -1.0)
            nd = days[i + 1]
            obs.append((nd, w, sess[nd]["open"] / sess[d]["close"] - 1.0))
        F.append(evaluate(
            tag, note, "sign set by the gamma regime, not by fitting; interaction test "
            "against the basket's T3 overnight reversal", obs, DWIN, HWIN))

    # --- B18 the OpEx AM-settlement overnight -------------------------------
    obs = []
    for i in range(1, len(days)):
        d = days[i]
        if not is_mfri(d):
            continue
        obs.append((d, 1.0, sess[d]["open"] / sess[days[i - 1]]["close"] - 1.0))
    F.append(evaluate(
        "B18_OPEX_AM_SETTLE_GAP", "SPX AM-settled monthly options print off the opening "
        "auction, so the unwind of the hedge against them lands in the overnight gap",
        "LONG the expiry-morning gap; sign fixed by the direction of the unwind",
        obs, DWIN, HWIN))
    return F


# =============================== TRACK C ======================================


def track_c(sess, v1d, vix, vix9):
    days = list(sess)
    F = []
    DWIN = ("2022-05-13", "2024-12-31")
    HWIN = ("2025-01-01", "2026-12-31")
    common = sorted(set(v1d) & set(vix))
    ratio = {d: v1d[d] / vix[d] for d in common}
    rd = sorted(ratio)
    rz = dict(zip(rd, zmap([ratio[d] for d in rd])))
    # zmap needs 250 obs; with ~1070 rows that leaves ~820 usable
    slope = {d: v1d[d] - vix9[d] for d in v1d if d in vix9}
    sd_ = sorted(slope)
    sz = dict(zip(sd_, zmap([slope[d] for d in sd_])))

    def intraday(name, zsrc, lo, hi, mode, t_sig, t_entry, t_exit, mech, note):
        obs = []
        for i in range(1, len(days)):
            d, p = days[i], days[i - 1]
            z = zsrc.get(p)
            if z is None or not (lo <= z < hi):
                continue
            r0 = sess[d][t_sig] / sess[d][t_entry if t_entry != t_sig else "open"] - 1.0
            if t_sig == t_entry:
                r0 = sess[d][t_sig] / sess[d]["open"] - 1.0
            if r0 == 0:
                continue
            w = (1.0 if mode == "mom" else -1.0) * (1.0 if r0 > 0 else -1.0)
            obs.append((d, w, sess[d][t_exit] / sess[d][t_entry] - 1.0))
        return evaluate(name, mech, note, obs, DWIN, HWIN)

    F.append(intraday(
        "C1_V1D_RICH_MOMENTUM", rz, 0.5, 9, "mom", "p10", "p10", "close",
        "VIX1D rich to VIX = the day's flow is concentrated in 0DTE, where dealers are "
        "net SHORT gamma, so an intraday move gets chased not absorbed",
        "FOLLOW the morning move on heavy-0DTE days; sign fixed by short-gamma"))
    F.append(intraday(
        "C2_V1D_CHEAP_FADE", rz, -9, -0.5, "rev", "p10", "p10", "close",
        "VIX1D cheap to VIX = little 0DTE demand, dealers keep the longer-dated long-"
        "gamma book, so intraday moves are absorbed",
        "FADE the morning move on light-0DTE days; sign fixed by long-gamma"))
    F.append(intraday(
        "C3_V1D_RICH_LASTHOUR", rz, 0.5, 9, "mom", "p15", "p15", "close",
        "0DTE gamma goes hyperbolic in the final hour; a short-gamma dealer's hedge is "
        "self-reinforcing right into settlement",
        "FOLLOW the 13:00-15:00 move into the close on heavy-0DTE days"))
    F.append(intraday(
        "C4_V1DSLOPE_RICH_MOM", sz, 0.5, 9, "mom", "p10", "p10", "close",
        "VIX1D - VIX9D is the pure 0DTE kink in the term structure, cleaner than the "
        "VIX1D/VIX ratio which carries the whole level",
        "FOLLOW the morning move when the 0DTE kink is steep"))

    # C5 -- 0DTE variance premium, close to close
    obs = []
    di = {d: i for i, d in enumerate(days)}
    rv = {}
    for i in range(1, len(days)):
        d, p = days[i], days[i - 1]
        rv[d] = abs(math.log(sess[d]["close"] / sess[p]["close"])) * math.sqrt(252) * 100 * 1.2533
    vrp_d = sorted(d for d in v1d if d in rv)
    vz = dict(zip(vrp_d, zmap([v1d[d] - rv[d] for d in vrp_d])))
    obs = []
    for i in range(2, len(days) - 1):
        d, p = days[i], days[i - 1]
        z = vz.get(d)
        if z is None:
            continue
        r0 = sess[d]["close"] / sess[p]["close"] - 1.0
        w = (-1.0 if z > 0 else 1.0) * (1.0 if r0 > 0 else -1.0)
        nd = days[i + 1]
        obs.append((nd, w, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "C5_V1D_VRP_SIGNFLIP", "a fat 0DTE variance premium means the vol sellers are "
        "solvent and supplying gamma (dealers long) -> next-day reversal; a negative one "
        "means they have been run over (dealers short) -> next-day continuation",
        "REVERSE when 0DTE VRP is fat, CONTINUE when thin; both signs fixed in advance",
        obs, DWIN, HWIN))

    # C6 -- VIX1D spike = panic 0DTE put buying
    obs = []
    dv = {}
    for i in range(1, len(vrp_d)):
        dv[vrp_d[i]] = v1d[vrp_d[i]] / v1d[vrp_d[i - 1]] - 1.0
    dd_ = sorted(dv)
    dvz = dict(zip(dd_, zmap([dv[d] for d in dd_])))
    for i in range(2, len(days) - 1):
        d, p = days[i], days[i - 1]
        z = dvz.get(d)
        if z is None or z < 1.0:
            continue
        r0 = sess[d]["close"] / sess[p]["close"] - 1.0
        w = 1.0 if r0 > 0 else -1.0
        nd = days[i + 1]
        obs.append((nd, w, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "C6_V1D_SPIKE_CONTINUE", "a VIX1D spike is a rush into same-day protection; the "
        "dealer selling it is short gamma at the money and must sell into weakness",
        "CONTINUE the day's move after a 0DTE-vol spike; fixed by short-gamma",
        obs, DWIN, HWIN))
    return F


# =============================== TRACK A ======================================

SQ2PI = math.sqrt(2 * math.pi)


def bs_gamma(S, K, T, sig):
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + 0.5 * sig * sig * T) / (sig * math.sqrt(T))
    return math.exp(-0.5 * d1 * d1) / SQ2PI / (S * sig * math.sqrt(T))


def load_gex(sess, vix):
    """Per observation-day t: gamma-weighted cumulative option volume by strike,
    over every cached expiry E with 0 <= (E - t) <= 5 sessions."""
    expd = os.path.join(ROOT, "research/data/gex_cache/exp")
    files = sorted(f for f in os.listdir(expd) if f.endswith(".json"))
    days = list(sess)
    di = {d: i for i, d in enumerate(days)}
    # cum[t][(K, cp)] = (gamma-weighted cumulative volume, dte)
    acc = defaultdict(lambda: {"c": defaultdict(float), "p": defaultdict(float)})
    for fn in files:
        rec = json.load(open(os.path.join(expd, fn)))
        E = rec["expiry"]
        if E not in di:
            continue
        iE = di[E]
        for sym, bars in rec["bars"].items():
            cp = "c" if sym[-9] == "C" else "p"
            K = int(sym[-8:]) / 1000.0
            cum = 0.0
            for t, v, c, o, h, lo in bars:
                cum += v
                if t not in di:
                    continue
                dte = iE - di[t]
                if not (0 <= dte <= 5):
                    continue
                S = sess[t]["close"]
                sig = max(0.05, vix.get(t, 15.0) / 100.0)
                T = max(dte, 0.5) / 252.0
                g = bs_gamma(S, K, T, sig) * cum * 100 * S * S * 0.01
                acc[t][cp][K] += g
    return {t: {"c": dict(v["c"]), "p": dict(v["p"])} for t, v in acc.items()}


def track_a(sess, vix):
    expd = os.path.join(ROOT, "research/data/gex_cache/exp")
    if not os.path.isdir(expd) or len(os.listdir(expd)) < 500:
        return [], {"status": "gex cache incomplete"}
    G = load_gex(sess, vix)
    days = [d for d in sess if d in G]
    di = {d: i for i, d in enumerate(list(sess))}
    alld = list(sess)
    F = []
    DWIN = ("2024-02-01", "2025-08-31")
    HWIN = ("2025-09-01", "2026-12-31")

    def nxt(d):
        i = di[d]
        return alld[i + 1] if i + 1 < len(alld) else None

    feats = {}
    for d in days:
        c, p = G[d]["c"], G[d]["p"]
        S = sess[d]["close"]
        gc, gp = sum(c.values()), sum(p.values())
        if gc + gp <= 0:
            continue
        gex = gc - gp                       # dealers long calls, short puts
        tot = {k: c.get(k, 0) + p.get(k, 0) for k in set(c) | set(p)}
        wsum = sum(tot.values())
        gcm = sum(k * v for k, v in tot.items()) / wsum if wsum else S
        # zero-gamma strike: running net gamma vs strike
        ks = sorted(tot)
        run, flip = 0.0, None
        for k in ks:
            run += c.get(k, 0) - p.get(k, 0)
        cum = 0.0
        for k in ks:
            cum += c.get(k, 0) - p.get(k, 0)
            if flip is None and cum > 0:
                flip = k
        call_wall = max(((k, v) for k, v in c.items() if k > S), default=(None, 0))[0]
        put_wall = max(((k, v) for k, v in p.items() if k < S), default=(None, 0))[0]
        feats[d] = {"S": S, "gex": gex, "norm": gex / (gc + gp), "gcm": gcm,
                    "flip": flip, "cw": call_wall, "pw": put_wall,
                    "mag": (gc + gp)}

    fd = sorted(feats)
    nz = dict(zip(fd, zmap([feats[d]["norm"] for d in fd])))
    mz = dict(zip(fd, zmap([math.log(feats[d]["mag"]) for d in fd])))

    # A1 -- gamma sign flips the daily autocorrelation
    obs = []
    for i in range(1, len(fd)):
        d, p = fd[i], fd[i - 1]
        nd = nxt(d)
        if nd is None:
            continue
        r0 = sess[d]["close"] / sess[p]["close"] - 1.0
        w = (-1.0 if feats[d]["norm"] > 0 else 1.0) * (1.0 if r0 > 0 else -1.0)
        obs.append((nd, w, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "A1_GEX_SIGN_AUTOCORR", "net dealer gamma built from real per-strike SPY option "
        "volume across every expiry inside 5 sessions: positive net gamma makes hedging "
        "counter-trend (reversal), negative makes it pro-trend (momentum)",
        "REVERSE when net gamma > 0, CONTINUE when < 0; both fixed by the hedging identity",
        obs, DWIN, HWIN))

    # A1b -- strictly lag-safe twin: the option daily bar for t is only complete at the
    #        16:15 options close, after the 16:00 cash close, so A1's entry is optimistic.
    obs = []
    for i in range(1, len(fd)):
        d, p = fd[i], fd[i - 1]
        nd = nxt(d)
        if nd is None:
            continue
        r0 = sess[d]["close"] / sess[p]["close"] - 1.0
        w = (-1.0 if feats[d]["norm"] > 0 else 1.0) * (1.0 if r0 > 0 else -1.0)
        obs.append((nd, w, sess[nd]["close"] / sess[nd]["open"] - 1.0))
    F.append(evaluate(
        "A1b_GEX_SIGN_LAGSAFE", "A1's mechanism, entered at the next cash open so no "
        "position is ever taken on an option bar that has not printed",
        "REVERSE when net gamma > 0, CONTINUE when < 0; lag-safe entry",
        obs, DWIN, HWIN))

    # A2 -- pin toward the gamma centre of mass, close to close
    obs = []
    for d in fd:
        nd = nxt(d)
        if nd is None:
            continue
        gap = (feats[d]["gcm"] - feats[d]["S"]) / feats[d]["S"]
        w = max(-1.0, min(1.0, gap / 0.004))
        obs.append((nd, w, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "A2_GAMMA_CofM_PIN", "the gamma-weighted centre of mass of the near-dated strike "
        "ladder is where a long-gamma dealer book has the least to hedge; spot is drawn "
        "to it", "LONG when the centre of mass sits above spot; fixed by the pin mechanism",
        obs, DWIN, HWIN))

    # A3 -- same, intraday (open -> close, signal from prior close)
    obs = []
    for d in fd:
        nd = nxt(d)
        if nd is None:
            continue
        gap = (feats[d]["gcm"] - feats[d]["S"]) / feats[d]["S"]
        w = max(-1.0, min(1.0, gap / 0.004))
        obs.append((nd, w, sess[nd]["close"] / sess[nd]["open"] - 1.0))
    F.append(evaluate(
        "A3_GAMMA_CofM_INTRADAY", "as A2 but the pull is claimed to act during the cash "
        "session when the hedging actually happens, not across the overnight gap",
        "LONG when the centre of mass sits above spot; open-to-close",
        obs, DWIN, HWIN))

    # A4 -- gamma flip level
    obs = []
    for i in range(1, len(fd)):
        d, p = fd[i], fd[i - 1]
        nd = nxt(d)
        if nd is None or feats[d]["flip"] is None:
            continue
        above = feats[d]["S"] > feats[d]["flip"]
        r0 = sess[d]["close"] / sess[p]["close"] - 1.0
        w = (-1.0 if above else 1.0) * (1.0 if r0 > 0 else -1.0)
        obs.append((nd, w, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "A4_GAMMA_FLIP_LEVEL", "the strike at which the running net gamma profile crosses "
        "zero: above it dealers are long gamma and damp, below it short and amplify",
        "REVERSE above the flip, CONTINUE below; fixed by the profile's sign",
        obs, DWIN, HWIN))

    # A4b -- lag-safe twin of the flip level
    obs = []
    for i in range(1, len(fd)):
        d, p = fd[i], fd[i - 1]
        nd = nxt(d)
        if nd is None or feats[d]["flip"] is None:
            continue
        above = feats[d]["S"] > feats[d]["flip"]
        r0 = sess[d]["close"] / sess[p]["close"] - 1.0
        w = (-1.0 if above else 1.0) * (1.0 if r0 > 0 else -1.0)
        obs.append((nd, w, sess[nd]["close"] / sess[nd]["open"] - 1.0))
    F.append(evaluate(
        "A4b_GAMMA_FLIP_LAGSAFE", "A4's mechanism entered at the next cash open",
        "REVERSE above the flip, CONTINUE below; lag-safe entry", obs, DWIN, HWIN))

    # A5 -- put-gamma surge
    obs = []
    for i in range(1, len(fd)):
        d, p = fd[i], fd[i - 1]
        nd = nxt(d)
        if nd is None:
            continue
        dz = (nz[d] - nz[p]) if nz[d] is not None and nz[p] is not None else None
        if dz is None:
            continue
        w = max(-1.0, min(1.0, dz))
        obs.append((nd, w, sess[nd]["close"] / sess[d]["close"] - 1.0))
    F.append(evaluate(
        "A5_PUTGAMMA_SURGE", "a day-on-day collapse in the call/put gamma balance is a "
        "hedging rush: the dealer taking the other side is newly short downside gamma "
        "and will have to sell spot into any further weakness",
        "SHORT when the balance swings to puts; fixed by the short-gamma channel",
        obs, DWIN, HWIN))

    # A9/A9b -- RELATIVE dealer gamma.  On SPY 0-5DTE the near-money put book dominates
    #   the call book on ~97 % of days, so the textbook "GEX crosses zero" split is
    #   degenerate.  The non-degenerate form of the same mechanism is the call/put gamma
    #   balance measured against its OWN expanding history.
    for tag, exitmode in (("A9_RELGAMMA_AUTOCORR", "cc"), ("A9b_RELGAMMA_LAGSAFE", "oc")):
        obs = []
        for i in range(1, len(fd)):
            d, p = fd[i], fd[i - 1]
            nd = nxt(d)
            if nd is None or nz[d] is None:
                continue
            r0 = sess[d]["close"] / sess[p]["close"] - 1.0
            w = (-1.0 if nz[d] > 0 else 1.0) * (1.0 if r0 > 0 else -1.0)
            gr = (sess[nd]["close"] / sess[d]["close"] - 1.0) if exitmode == "cc" \
                else (sess[nd]["close"] / sess[nd]["open"] - 1.0)
            obs.append((nd, w, gr))
        F.append(evaluate(
            tag, "the call/put gamma balance relative to its own expanding history: an "
            "unusually call-heavy book is the long-gamma regime (damping), an unusually "
            "put-heavy one is the short-gamma regime (amplifying)",
            "REVERSE in the relatively-long-gamma regime, CONTINUE in the short one; "
            "both fixed by the hedging identity", obs, DWIN, HWIN))

    # A6/A7 -- walls
    for tag, key, side, note in (
            ("A6_CALL_WALL_RESIST", "cw", -1.0,
             "the strike carrying the most call gamma above spot is where dealer supply "
             "is thickest; spot stalls there"),
            ("A7_PUT_WALL_SUPPORT", "pw", 1.0,
             "the strike carrying the most put gamma below spot is where dealer demand "
             "is thickest; spot bounces there")):
        obs = []
        for d in fd:
            k = feats[d][key]
            if k is None:
                continue
            nd = nxt(d)
            if nd is None:
                continue
            gap = abs(feats[d]["S"] - k) / feats[d]["S"]
            if gap > 0.0035:
                continue
            obs.append((nd, side, sess[nd]["close"] / sess[nd]["open"] - 1.0))
        F.append(evaluate(tag, note, "sign fixed by which wall spot is against",
                          obs, DWIN, HWIN))

    # A8 -- total gamma magnitude clamps intraday range
    obs = []
    for d in fd:
        nd = nxt(d)
        if nd is None or mz[d] is None:
            continue
        if mz[d] < 0.5:
            continue
        r0 = sess[nd]["p10"] / sess[nd]["open"] - 1.0
        if r0 == 0:
            continue
        w = -1.0 if r0 > 0 else 1.0
        obs.append((nd, w, sess[nd]["close"] / sess[nd]["p10"] - 1.0))
    F.append(evaluate(
        "A8_BIG_GAMMA_CLAMP", "when the absolute size of the near-dated gamma book is "
        "large, hedging volume dominates the tape and the morning move gets absorbed",
        "FADE the morning move on big-gamma days; fixed by the long-gamma clamp",
        obs, DWIN, HWIN))
    return F, {"status": "ok", "days": len(fd)}


# =================================== main =====================================


def main():
    sess = build_sessions()
    vix = cboe("VIX")
    vix9 = cboe("VIX9D")
    vix3 = cboe("VIX3M")
    v1d = cboe("VIX1D")
    skew = cboe("SKEW", "SKEW")
    print(f"sessions {len(sess)} {min(sess)}..{max(sess)}", flush=True)

    F = []
    F += track_b(sess, vix9, vix3, vix, skew)
    F += track_c(sess, v1d, vix, vix9)
    fa, ameta = track_a(sess, vix)
    F += fa

    N = len(F)
    res = {
        "theme": "dealer positioning / options flow",
        "n_formulas": N,
        "sqrt_2lnN": round(math.sqrt(2 * math.log(N)), 3),
        "track_a": ameta,
        "formulas": F,
    }
    json.dump(res, open(os.path.join(OUT, "INVENT_R3_dealer_positioning.json"), "w"),
              indent=1)
    for f in F:
        print(f"{f['name']:28s} D S={f['design']['sharpe']:+.2f} t={f['design']['t']:+.2f} "
              f"n={f['design']['n']:5d} | H S={f['holdout']['sharpe']:+.2f} "
              f"t={f['holdout']['t']:+.2f} n={f['holdout']['n']:5d}")
    print(f"\nN={N}  sqrt(2 ln N)={math.sqrt(2*math.log(N)):.2f}")


if __name__ == "__main__":
    main()
