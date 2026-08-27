"""INVENT 0822 -- volatility theme.

Panel builder + structural diagnostics for the VOL-ETP MECHANICAL TETHER family.

Mechanism (one sentence, fixed a priori): several US-listed volatility ETPs track the
SAME published index with a CONTRACTUALLY FIXED daily leverage multiple and a daily
reset, so their daily NAV returns are pinned to each other by prospectus arithmetic --
r_A = k * r_B - fee_drift exactly -- and any daily deviation of MARKET prices from that
identity is a wrapper/liquidity dislocation, not information.

Free data only, all from the already-cached research/data/volterm_cache/raw/*.json
(Yahoo chart v8 adjusted closes). No network call.
"""
import json
import math
import os

RAW = "/home/anont/meme/research/data/volterm_cache/raw"


def load(sym):
    with open(os.path.join(RAW, sym + ".json")) as f:
        d = json.load(f)
    r = d["chart"]["result"][0]
    ts = r["timestamp"]
    adj = r["indicators"]["adjclose"][0]["adjclose"]
    q = r["indicators"]["quote"][0]
    out = {}
    for i, t in enumerate(ts):
        a = adj[i]
        if a is None or a <= 0:
            continue
        # yahoo timestamps are the 09:30 ET open epoch; convert to a yyyymmdd key
        import datetime
        day = datetime.datetime.utcfromtimestamp(t + 4 * 3600).strftime("%Y%m%d")
        out[day] = {
            "adj": float(a),
            "close": float(q["close"][i]) if q["close"][i] else None,
            "vol": float(q["volume"][i]) if q["volume"][i] else 0.0,
        }
    return out


# ---------------------------------------------------------------- pair universe
# k = contractual daily leverage of A relative to B, and the date the multiple changed.
# 2018-02-28 is the announced ProShares change: UVXY 2x -> 1.5x, SVXY -1x -> -0.5x.
PAIRS = [
    # name,        A,      B,       k_before, k_from_20180228, index
    ("VXX_VIXY",   "VXX",  "VIXY",   1.0,  1.0,  "SPVXSTR"),
    ("VXZ_VIXM",   "VXZ",  "VIXM",   1.0,  1.0,  "SPVXMTR"),
    ("UVXY_VIXY",  "UVXY", "VIXY",   2.0,  1.5,  "SPVXSTR"),
    ("SVXY_VIXY",  "SVXY", "VIXY",  -1.0, -0.5,  "SPVXSTR"),
    ("UVXY_VXX",   "UVXY", "VXX",    2.0,  1.5,  "SPVXSTR"),
    ("SVXY_VXX",   "SVXY", "VXX",   -1.0, -0.5,  "SPVXSTR"),
    ("SVIX_VIXY",  "SVIX", "VIXY",  -1.0, -1.0,  "SPVXSTR"),
    ("UVIX_VIXY",  "UVIX", "VIXY",   2.0,  2.0,  "SPVXSTR"),
    ("SVIX_SVXY",  "SVIX", "SVXY",   1.0,  2.0,  "SPVXSTR"),
    ("UVIX_UVXY",  "UVIX", "UVXY",   1.0,  4.0 / 3.0, "SPVXSTR"),
]


def k_for(day, kb, ka):
    return kb if day < "20180228" else ka


def build_pair(name, A, B, kb, ka, dA, dB):
    days = sorted(set(dA) & set(dB))
    rows = []
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        rA = dA[d1]["adj"] / dA[d0]["adj"] - 1.0
        rB = dB[d1]["adj"] / dB[d0]["adj"] - 1.0
        k = k_for(d1, kb, ka)
        rows.append({
            "day": d1,
            "rA": rA,
            "rB": rB,
            "k": k,
            "e": rA - k * rB,              # daily replication residual
            "dvA": dA[d1]["vol"] * (dA[d1]["close"] or 0.0),
            "dvB": dB[d1]["vol"] * (dB[d1]["close"] or 0.0),
        })
    return rows
