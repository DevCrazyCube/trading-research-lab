#!/usr/bin/env python3
"""INVENT R3 -- MECHANICAL FLOW / STRUCTURE. Data collection only.

Pulls free Alpaca SIP daily bars (raw + split/div adjusted) and official auction
prints for the leveraged-ETF / sibling-ETF / bond-ETF / EM-ETF universe,
2016-01-04 .. 2026-08-14, and caches them under research/data/invr3_cache/.

No formula is evaluated here.
"""
from __future__ import annotations

import gzip
import json
import pathlib
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3  # noqa: E402

CACHE = ROOT / "research" / "data" / "invr3flow_cache"
CACHE.mkdir(parents=True, exist_ok=True)

START = "2016-01-04"
END = "2026-08-14"

# --- universe -------------------------------------------------------------
# leveraged / inverse families keyed by their reference underlying
LETF_FAMILIES = {
    "SPY": [("SSO", 2), ("UPRO", 3), ("SPXL", 3), ("SH", -1), ("SDS", -2),
            ("SPXU", -3), ("SPXS", -3)],
    "QQQ": [("QLD", 2), ("TQQQ", 3), ("PSQ", -1), ("QID", -2), ("SQQQ", -3)],
    "IWM": [("UWM", 2), ("TNA", 3), ("RWM", -1), ("TWM", -2), ("TZA", -3)],
    "TLT": [("UBT", 2), ("TMF", 3), ("TBT", -2), ("TMV", -3), ("TBF", -1)],
    "SOXX": [("SOXL", 3), ("SOXS", -3), ("USD", 2), ("SSG", -2)],
    "XBI": [("LABU", 3), ("LABD", -3)],
    "GDX": [("NUGT", 2), ("DUST", -2), ("JNUG", 2), ("JDST", -2)],
    "XLF": [("FAS", 3), ("FAZ", -3)],
    "XLE": [("ERX", 2), ("ERY", -2), ("GUSH", 2), ("DRIP", -2)],
    "FXI": [("YINN", 3), ("YANG", -3)],
    "EEM": [("EDC", 3), ("EDZ", -3)],
    "IYR": [("DRN", 3), ("DRV", -3)],
    "KRE": [("DPST", 3), ("WDRW", -3)],
    "USO": [("UCO", 2), ("SCO", -2)],
    "UNG": [("BOIL", 2), ("KOLD", -2)],
}

SIBLING_GROUPS = {
    "sp500": ["SPY", "IVV", "VOO", "SPLG"],
    "nasdaq100": ["QQQ", "QQQM"],
    "r2000": ["IWM", "VTWO"],
    "midcap": ["IJH", "MDY", "IVOO"],
    "totalus": ["VTI", "ITOT", "SCHB"],
    "emerging": ["EEM", "IEMG", "VWO", "SPEM"],
    "eafe": ["EFA", "IEFA", "VEA", "SPDW"],
    "agg": ["AGG", "BND", "SPAB"],
    "hy": ["HYG", "JNK", "USHY", "SPHY"],
    "ig": ["LQD", "VCIT", "IGIB", "SPIB"],
}

BOND_ETFS = ["LQD", "HYG", "JNK", "AGG", "BND", "TLT", "IEF", "SHY", "TIP",
             "EMB", "MUB", "VCIT", "VGLT", "VGSH", "BKLN", "SRLN", "PFF",
             "VCSH", "IGSB", "SJNK", "SHYG", "USHY", "ANGL", "EMLC", "IGIB",
             "HYD", "PCY", "VWOB", "FLOT", "STIP", "SCHP", "GOVT", "BIV",
             "BLV", "MBB", "CMBS", "SPAB", "SPIB", "SPHY", "BSV", "IEI",
             "TLH", "SHV", "BIL"]

INTL_ETFS = ["EEM", "IEMG", "VWO", "EFA", "IEFA", "VEA", "EWJ", "EWZ", "FXI",
             "EWY", "EWT", "EWG", "EWU", "EWA", "EWC", "EWH", "EWS", "EWW",
             "EPP", "VGK", "ILF", "EPI", "INDA", "ASHR", "EZU", "SCZ", "MCHI",
             "EWL", "EWP", "EWI", "EWN", "EWD", "EIS", "TUR", "EZA", "THD",
             "SPEM", "SPDW", "IXUS", "ACWX", "VEU", "VSS", "DXJ", "HEDJ"]

CORE = ["SPY", "QQQ", "IWM", "DIA", "RSP", "MDY", "IJH", "IJR", "VTI", "ITOT",
        "SCHB", "IVV", "VOO", "SPLG", "QQQM", "VTWO", "IVOO", "GLD", "SLV",
        "IAU", "UUP", "FXE", "FXY", "USO", "UNG", "DBC", "VNQ", "IYR", "KRE",
        "SOXX", "SMH", "XBI", "IBB", "GDX", "GDXJ", "XLF", "XLE", "XLK",
        "XLV", "XLI", "XLP", "XLU", "XLY", "XLB", "XLC", "XLRE", "VXX"]


def universe():
    syms = set(CORE) | set(BOND_ETFS) | set(INTL_ETFS)
    for u, kids in LETF_FAMILIES.items():
        syms.add(u)
        for s, _ in kids:
            syms.add(s)
    for g in SIBLING_GROUPS.values():
        syms.update(g)
    return sorted(syms)


def _cache(name, build):
    path = CACHE / f"{name}.json.gz"
    if path.exists():
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    obj = build()
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as fh:
        json.dump(obj, fh)
    tmp.rename(path)
    return obj


def daily_bars(symbols, adjustment):
    def build():
        out = defaultdict(dict)

        def work(chunk):
            local = defaultdict(dict)
            for block in t3.paged("/v2/stocks/bars",
                                  {"symbols": ",".join(chunk), "start": START, "end": END,
                                   "timeframe": "1Day", "adjustment": adjustment,
                                   "limit": t3.PAGE, "feed": "sip"}, "bars"):
                for sym, rows in block.items():
                    for r in rows:
                        local[sym][r["t"][:10]] = [r["o"], r["h"], r["l"], r["c"],
                                                   r["v"], r.get("vw"), r.get("n")]
            return local

        with ThreadPoolExecutor(max_workers=6) as pool:
            for local in pool.map(work, list(t3.chunks(symbols, 40))):
                for sym, rows in local.items():
                    out[sym].update(rows)
        return dict(out)

    return _cache(f"daily_{adjustment}", build)


def auctions(symbols):
    def build():
        out = defaultdict(dict)

        def work(chunk):
            local = defaultdict(dict)
            for block in t3.paged("/v2/stocks/auctions",
                                  {"symbols": ",".join(chunk), "start": START, "end": END,
                                   "limit": t3.PAGE, "feed": "sip"}, "auctions"):
                for sym, days in block.items():
                    for d in days:
                        rec = {}
                        for leg, code in (("o", "O"), ("c", "6")):
                            prints = [p for p in (d.get(leg) or []) if p.get("c") == code]
                            if prints:
                                best = max(prints, key=lambda p: p.get("s", 0))
                                rec[leg] = [best["p"], best.get("s", 0)]
                        if rec:
                            local[sym][d["d"]] = rec
            return local

        with ThreadPoolExecutor(max_workers=6) as pool:
            for local in pool.map(work, list(t3.chunks(symbols, 40))):
                for sym, rows in local.items():
                    out[sym].update(rows)
        return dict(out)

    return _cache("auctions", build)


if __name__ == "__main__":
    syms = universe()
    print(f"universe {len(syms)} symbols", flush=True)
    raw = daily_bars(syms, "raw")
    print("raw daily:", len(raw), "symbols,",
          sum(len(v) for v in raw.values()), "rows", flush=True)
    adj = daily_bars(syms, "all")
    print("adj daily:", len(adj), "symbols,",
          sum(len(v) for v in adj.values()), "rows", flush=True)
    au = auctions(syms)
    print("auctions:", len(au), "symbols,",
          sum(len(v) for v in au.values()), "rows", flush=True)
    missing = sorted(s for s in syms if len(raw.get(s, {})) < 200)
    print("thin/missing:", missing, flush=True)
