#!/usr/bin/env python3
"""INVENT_0823 exotic-tether round: daily bar fetch for four hard-tether families.

Families and why each has a HARD PUBLISHED / MECHANICAL tether:

  C  same-coin ETP wrappers  -- 11 US spot-bitcoin ETPs and 8 spot-ether ETPs all hold the
     SAME physical coin and publish coins-per-share daily. The tether between two wrappers is
     exact up to the fee differential; no fitted hedge ratio is needed.
  H  currency-hedged sibling -- the iShares/Xtrackers hedged fund HOLDS the unhedged sibling
     (or its index) plus a rolling FX forward. r_unhedged = r_hedged + r_FX + carry is a
     mechanical identity. The FX leg is taken from a US-listed currency ETF so all three legs
     print on the SAME 16:00 ET clock (this removes the FX-close timing mismatch entirely).
  L  leveraged/inverse complex -- the fund's prospectus promises m x the base's DAILY return.
     The k-day theoretical NAV path is therefore a deterministic function of the base's path.
  F  fund-of-funds        -- iShares Core Allocation ETFs hold a published set of iShares ETFs
     at published target weights.

Everything is daily, adjustment='all' (total return: correct for a tether identity that must
hold on total returns, since the legs pay very different dividends).
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from trading_bot.data import load_bars  # noqa: E402
from trading_bot.frozen import Refused  # noqa: E402

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "exo0823_cache"

BTC_WRAPPERS = ["IBIT", "FBTC", "BITB", "ARKB", "BTCO", "HODL", "BRRR", "BTCW", "EZBC",
                "GBTC", "BTC"]
ETH_WRAPPERS = ["ETHA", "FETH", "ETHW", "ETHV", "QETH", "EZET", "ETHE", "ETH"]

FX_TRIANGLES = [
    # (unhedged, hedged, fx_etf, label)
    ("EZU", "HEZU", "FXE", "eurozone_ishares"),
    ("EWG", "HEWG", "FXE", "germany_ishares"),
    ("EWJ", "HEWJ", "FXY", "japan_ishares"),
    ("EWU", "HEWU", "FXB", "uk_ishares"),
    ("EWJ", "DBJP", "FXY", "japan_xtrackers"),
    ("EWG", "DBGR", "FXE", "germany_xtrackers"),
    ("EFA", "HEFA", "BASKET", "eafe_ishares"),
    ("EFA", "DBEF", "BASKET", "eafe_xtrackers"),
]
FX_ETFS = ["FXE", "FXY", "FXB", "FXF", "FXC", "FXA", "UUP"]

LEVERED = [
    ("SSO", "SPY", 2.0), ("UPRO", "SPY", 3.0), ("SPXL", "SPY", 3.0),
    ("SH", "SPY", -1.0), ("SDS", "SPY", -2.0), ("SPXU", "SPY", -3.0), ("SPXS", "SPY", -3.0),
    ("QLD", "QQQ", 2.0), ("TQQQ", "QQQ", 3.0), ("PSQ", "QQQ", -1.0),
    ("QID", "QQQ", -2.0), ("SQQQ", "QQQ", -3.0),
    ("UWM", "IWM", 2.0), ("TNA", "IWM", 3.0), ("TWM", "IWM", -2.0), ("TZA", "IWM", -3.0),
    ("TMF", "TLT", 3.0), ("TMV", "TLT", -3.0),
    ("UGL", "GLD", 2.0), ("GLL", "GLD", -2.0),
    ("NUGT", "GDX", 2.0), ("DUST", "GDX", -2.0),
    ("SOXL", "SOXX", 3.0), ("SOXS", "SOXX", -3.0),
    ("FAS", "XLF", 3.0), ("FAZ", "XLF", -3.0),
    ("ERX", "XLE", 2.0), ("ERY", "XLE", -2.0),
]

# iShares Core Allocation ETFs.  Target allocations are published by the sponsor; the
# replication basket below uses the sponsor's own building blocks and the stated
# equity/bond split, with the equity sleeve split at the fund's published regional weights.
FOF = {
    "AOA": {"IVV": 0.464, "IDEV": 0.240, "IEMG": 0.080, "IJH": 0.088, "IJR": 0.048,
            "IUSB": 0.056, "IAGG": 0.024},
    "AOR": {"IVV": 0.348, "IDEV": 0.180, "IEMG": 0.060, "IJH": 0.066, "IJR": 0.036,
            "IUSB": 0.224, "IAGG": 0.096},
    "AOM": {"IVV": 0.232, "IDEV": 0.120, "IEMG": 0.040, "IJH": 0.044, "IJR": 0.024,
            "IUSB": 0.392, "IAGG": 0.168},
    "AOK": {"IVV": 0.174, "IDEV": 0.090, "IEMG": 0.030, "IJH": 0.033, "IJR": 0.018,
            "IUSB": 0.462, "IAGG": 0.198},
}
FOF_COMPONENTS = ["IVV", "IDEV", "IEMG", "IJH", "IJR", "IUSB", "IAGG", "AGG", "EFA"]

START = "2014-01-01"
END = "2026-08-20"


def all_symbols() -> list[str]:
    syms = set(BTC_WRAPPERS) | set(ETH_WRAPPERS) | set(FX_ETFS) | set(FOF) | set(FOF_COMPONENTS)
    for u, h, x, _ in FX_TRIANGLES:
        syms |= {u, h}
        if x != "BASKET":
            syms.add(x)
    for lev, base, _m in LEVERED:
        syms |= {lev, base}
    syms |= {"SPY", "QQQ", "IWM", "TLT", "GLD", "GDX", "SOXX", "XLF", "XLE"}
    return sorted(syms)


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    report = {}
    for sym in all_symbols():
        try:
            bars, man = load_bars(sym, START, END, "1Day", cache_dir=CACHE)
            report[sym] = {"n": len(bars), "src": man.get("source")}
            print(f"{sym:6s} {len(bars):6d} {man.get('source')}", flush=True)
        except Refused as exc:
            report[sym] = {"n": 0, "error": str(exc)[:140]}
            print(f"{sym:6s} REFUSED {str(exc)[:90]}", flush=True)
        except Exception as exc:  # noqa: BLE001
            report[sym] = {"n": 0, "error": f"{type(exc).__name__}: {exc}"[:140]}
            print(f"{sym:6s} ERROR {type(exc).__name__} {exc}", flush=True)
        time.sleep(0.05)
    (CACHE / "_fetch_report.json").write_text(json.dumps(report, indent=1))
    ok = sum(1 for v in report.values() if v["n"] > 0)
    print(f"\n{ok}/{len(report)} symbols fetched")


if __name__ == "__main__":
    main()
