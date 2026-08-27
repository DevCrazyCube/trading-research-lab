#!/usr/bin/env python3
"""NEW TERRITORY: rates / credit / bond RV -- data fetch.

Free daily data only:
  * Yahoo chart API, adjclose (TOTAL RETURN -- essential here, because for a bond ETF most of
    the return IS the coupon; a price-only series would understate carry and manufacture a
    fake short-side edge in every high-yielding leg).
  * FRED fredgraph.csv for the yield / spread / breakeven / CPI series that carry the CARRY
    signals. No API key needed.

POINT-IN-TIME NOTE, recorded rather than assumed:
  * DGS*/T10Y2Y/T10YIE (H.15 / Treasury par curve) publish ~3:30-4:15pm ET for the SAME day.
  * BAML OAS series (BAMLH0A0HYM2, BAMLC0A0CM) publish the NEXT business day.
  * CPIAUCNS publishes ~2 weeks after month end.
  The backtest lags EVERY FRED input by one extra business day beyond the ETF closes, and the
  lag-kill stage adds another, so nothing here rests on the publish schedule being generous.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "ratescredit_cache"
CACHE.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-daily-fetch"}

ETFS = [
    # Treasuries by maturity bucket
    "BIL", "SHV", "SHY", "IEI", "IEF", "TLH", "TLT", "GOVT", "EDV", "ZROZ",
    "VGSH", "VGIT", "VGLT", "SCHO", "SCHR", "SPTL",
    # aggregate / MBS
    "AGG", "BND", "MBB", "VMBS",
    # investment-grade credit
    "LQD", "VCSH", "VCIT", "VCLT", "IGSB", "IGIB", "USIG", "SPIB",
    # high yield / loans
    "HYG", "JNK", "SJNK", "SHYG", "USHY", "ANGL", "BKLN", "SRLN", "HYLB",
    # EM debt
    "EMB", "PCY", "EMLC",
    # TIPS
    "TIP", "SCHP", "VTIP", "STIP", "LTPZ", "TDTT",
    # muni
    "MUB", "TFI", "HYD", "SUB", "SHM", "ITM",
    # preferred / hybrid / convert
    "PFF", "PGX", "PSK", "PFXF", "CWB", "ICVT",
    # floating rate
    "FLOT", "USFR",
    # risk reference legs (used only as hedge legs / conditioning, never as the edge)
    "SPY", "IWM", "XLF", "KRE", "XLU", "GLD", "UUP",
]

FRED = [
    "DGS1MO", "DGS3MO", "DGS2", "DGS5", "DGS10", "DGS30",
    "T10Y2Y", "T10Y3M", "T10YIE", "T5YIE",
    "BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A0HYM2EY",
    "DFF", "CPIAUCNS", "MORTGAGE30US",
]


def fetch_yahoo(sym: str) -> dict | None:
    u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         f"?period1=0&period2=1790000000&interval=1d&events=div%2Csplit")
    try:
        raw = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
    except Exception as e:                                    # noqa: BLE001
        print(f"  {sym}: FETCH FAIL {e}", flush=True)
        return None
    d = json.loads(raw)
    res = (d.get("chart") or {}).get("result")
    if not res:
        print(f"  {sym}: no result", flush=True)
        return None
    r = res[0]
    ts = r.get("timestamp") or []
    q = r["indicators"]["quote"][0]
    ac = r["indicators"].get("adjclose", [{}])[0].get("adjclose")
    if ac is None:
        print(f"  {sym}: no adjclose", flush=True)
        return None
    return {"t": ts, "adjclose": ac, "close": q.get("close"), "volume": q.get("volume")}


def fetch_fred(sid: str) -> dict | None:
    u = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1990-01-01"
    try:
        txt = urllib.request.urlopen(
            urllib.request.Request(u, headers=UA), timeout=30).read().decode()
    except Exception as e:                                    # noqa: BLE001
        print(f"  {sid}: FETCH FAIL {e}", flush=True)
        return None
    out = {}
    for line in txt.strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            out[parts[0]] = float(parts[1])
        except ValueError:
            continue                                          # "." = missing, keep it missing
    return out


def main() -> None:
    px_path = CACHE / "etf_daily.json"
    px = json.loads(px_path.read_text()) if px_path.exists() else {}
    for i, s in enumerate(ETFS):
        if s in px:
            continue
        d = fetch_yahoo(s)
        if d:
            px[s] = d
            print(f"[{i+1}/{len(ETFS)}] {s}: {len(d['t'])} rows", flush=True)
        time.sleep(0.7)
        if i % 10 == 9:
            px_path.write_text(json.dumps(px))
    px_path.write_text(json.dumps(px))

    fr_path = CACHE / "fred_daily.json"
    fr = json.loads(fr_path.read_text()) if fr_path.exists() else {}
    for sid in FRED:
        if sid in fr:
            continue
        d = fetch_fred(sid)
        if d:
            fr[sid] = d
            print(f"FRED {sid}: {len(d)} rows", flush=True)
        time.sleep(0.7)
    fr_path.write_text(json.dumps(fr))
    print("done", flush=True)


if __name__ == "__main__":
    main()
