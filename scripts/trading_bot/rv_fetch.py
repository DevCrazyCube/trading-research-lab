#!/usr/bin/env python3
"""Fetch 5-minute SIP bars for the intraday relative-value sweep (theme: ETF/equity RV).

One symbol at a time, written straight to an .npz so peak RSS stays at one symbol's history
(the repo OOM'd before on a 33 GB in-memory load; this never holds more than ~100k bars).

Bars are adjustment=all (split+dividend). For a PAIR SPREAD that is the right choice: both legs
get the same retroactive treatment, an ex-div step becomes a constant offset in the log ratio,
and the rolling z-score absorbs it. Price LEVELS from this cache are NOT point-in-time and must
never be used for a level filter (see trading_bot/data.py).

RTH only: bars are converted to US/Eastern and kept for 09:30 <= t < 16:00.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trading_bot.data import load_env_credentials  # noqa: E402

ET = ZoneInfo("America/New_York")
_EPOCH_CACHE: dict[str, int] = {}
_ET_OFFSET: dict[str, int] = {}
CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "rv_cache"
START = "2021-01-01T00:00:00Z"
END = "2026-08-16T00:00:00Z"
TF = "5Min"

UNIVERSE = [
    # broad-market same-claim clusters
    "SPY", "IVV", "VOO", "SPLG", "VTI", "ITOT", "SCHB",
    "QQQ", "QQQM", "IWM", "VTWO", "IWB", "DIA", "MDY", "IJH", "IJR", "VB",
    # style
    "IWF", "IWD", "VUG", "VTV", "SPYG", "SPYV", "MTUM", "USMV", "QUAL", "VLUE",
    # commodities / metals
    "GLD", "IAU", "GLDM", "SLV", "SIVR", "USO", "UNG",
    # international
    "EFA", "IEFA", "VEA", "EEM", "IEMG", "VWO", "EWJ", "FXI", "EWZ",
    # fixed income
    "AGG", "BND", "LQD", "VCIT", "HYG", "JNK", "TLT", "VGLT", "IEF", "SHY", "VGSH", "TIP",
    # sectors (SPDR + Vanguard siblings)
    "XLK", "VGT", "XLF", "VFH", "XLE", "VDE", "XLV", "VHT", "XLI", "VIS",
    "XLY", "VCR", "XLP", "VDC", "XLU", "VPU", "XLB", "VAW", "XLRE", "VNQ", "XLC",
    "SMH", "SOXX", "KRE", "IBB", "XBI", "ITB", "XHB", "GDX", "GDXJ",
    # leveraged / inverse (same-claim, different beta)
    "SSO", "SDS", "UPRO", "SPXU", "SH", "QLD", "SQQQ", "TQQQ", "PSQ", "TNA", "TZA", "TMF", "TMV",
    # mega-cap single names (basket vs ETF, lead-lag)
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "BRK.B",
    "JPM", "XOM", "UNH", "JNJ", "V", "PG", "HD", "MA", "COST", "WMT", "BAC", "CVX",
    "LLY", "ABBV", "MRK", "PEP", "KO", "ORCL", "CRM", "AMD", "INTC", "NFLX", "ADBE", "CSCO",
]


def fetch_symbol(sym: str, key: str, sec: str) -> dict[str, np.ndarray] | None:
    rows_t, rows_o, rows_h, rows_l, rows_c, rows_v, rows_w, rows_n = ([] for _ in range(8))
    token = None
    pages = 0
    while True:
        params = {
            "symbols": sym, "timeframe": TF, "start": START, "end": END,
            "limit": 10000, "adjustment": "all", "feed": "sip", "sort": "asc",
        }
        if token:
            params["page_token"] = token
        url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        last_exc = None
        for attempt in range(10):
            try:
                with urllib.request.urlopen(req, timeout=120) as fh:
                    payload = json.load(fh)
                break
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (429, 500, 502, 503, 504):
                    time.sleep(min(60, 3 * 2 ** attempt))
                    continue
                if exc.code == 404:
                    return None
                raise
            except Exception as exc:               # noqa: BLE001
                # a swallowed exception here is how "exhausted retries" became an unreadable
                # failure on the first wave; keep the last one and print it
                last_exc = exc
                time.sleep(min(60, 3 * 2 ** attempt))
        else:
            raise RuntimeError(f"{sym}: exhausted retries; last error was {last_exc!r}")
        bars = (payload.get("bars") or {}).get(sym) or []
        for b in bars:
            s = b["t"]
            # "2024-03-01T14:30:00Z" -- fixed-width, so slice rather than strptime (strptime
            # plus a zoneinfo conversion on 350k bars per symbol is a real cost here)
            ts = _EPOCH_CACHE.get(s[:10])
            if ts is None:
                ts = int(datetime(int(s[:4]), int(s[5:7]), int(s[8:10]),
                                  tzinfo=timezone.utc).timestamp())
                _EPOCH_CACHE[s[:10]] = ts
            utc_min = int(s[11:13]) * 60 + int(s[14:16])
            off = _ET_OFFSET.get(s[:10])
            if off is None:
                off = int(datetime(int(s[:4]), int(s[5:7]), int(s[8:10]), 12,
                                   tzinfo=timezone.utc).astimezone(ET).utcoffset().total_seconds() // 60)
                _ET_OFFSET[s[:10]] = off
            mins = utc_min + off
            if mins < 570 or mins >= 960:      # RTH only: [09:30, 16:00)
                continue
            ts = ts + utc_min * 60
            rows_t.append(ts)
            rows_o.append(b["o"]); rows_h.append(b["h"]); rows_l.append(b["l"])
            rows_c.append(b["c"]); rows_v.append(b["v"]); rows_w.append(b.get("vw") or b["c"])
            rows_n.append(b.get("n") or 0)
        token = payload.get("next_page_token")
        pages += 1
        if not token:
            break
    if not rows_t:
        return None
    return {
        "t": np.asarray(rows_t, dtype=np.int64),
        "o": np.asarray(rows_o, dtype=np.float32),
        "h": np.asarray(rows_h, dtype=np.float32),
        "l": np.asarray(rows_l, dtype=np.float32),
        "c": np.asarray(rows_c, dtype=np.float32),
        "v": np.asarray(rows_v, dtype=np.float64),
        "vw": np.asarray(rows_w, dtype=np.float32),
        "n": np.asarray(rows_n, dtype=np.int32),
    }


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    shard = int(os.environ.get("RV_SHARD", "0"))
    nshards = int(os.environ.get("RV_NSHARDS", "1"))
    key, sec = load_env_credentials()
    manifest_path = CACHE / f"manifest_{shard}.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    order = list(reversed(UNIVERSE)) if os.environ.get("RV_REVERSE") else UNIVERSE
    mine = [s for i, s in enumerate(order) if i % nshards == shard]
    for i, sym in enumerate(mine):
        out = CACHE / f"{sym.replace('.', '_')}.npz"
        if out.exists():
            continue
        t0 = time.time()
        try:
            arrs = fetch_symbol(sym, key, sec)
        except Exception as exc:               # noqa: BLE001
            print(f"[{i+1}/{len(mine)}] {sym} FAILED {exc}", flush=True)
            manifest[sym] = {"status": "failed", "error": str(exc)}
            manifest_path.write_text(json.dumps(manifest, indent=1))
            continue
        if arrs is None:
            print(f"[{i+1}/{len(mine)}] {sym} EMPTY", flush=True)
            manifest[sym] = {"status": "empty"}
            manifest_path.write_text(json.dumps(manifest, indent=1))
            continue
        # atomic: two shards may race on the same symbol at the wave boundary, and a
        # half-written .npz that a later run treats as "already cached" is a silent data bug
        tmp = out.with_suffix(f".npz.tmp{os.getpid()}")
        np.savez_compressed(tmp, **arrs)
        os.replace(tmp, out)
        manifest[sym] = {
            "status": "ok", "n_bars": int(arrs["t"].size),
            "first": int(arrs["t"][0]), "last": int(arrs["t"][-1]),
            "timeframe": TF, "adjustment": "all", "feed": "sip",
            "survivorship": "symbols that exist today; delisted names absent",
        }
        manifest_path.write_text(json.dumps(manifest, indent=1))
        print(f"[{i+1}/{len(mine)}] {sym} {arrs['t'].size} bars in {time.time()-t0:.1f}s", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
