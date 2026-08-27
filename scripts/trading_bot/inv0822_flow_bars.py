#!/usr/bin/env python3
"""INVENT_0822 forced-flow: batched daily-bar fetch for the event universe.

Uses the same credentials and the same DATA-ONLY host guard as scripts/trading_bot/data.py
(imported, not retyped).  Stores one compact .npz per symbol:
    d  : int32 yyyymmdd
    o,h,l,c : float32 adjusted OHLC
    v  : float32 volume
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trading_bot.data import assert_data_host, load_env_credentials  # noqa: E402
from trading_bot.frozen import ALPACA_DATA_HOST  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
BARS = ROOT / "research" / "data" / "inv0822_flow" / "bars"
START, END = "2015-10-01", "2026-08-14"


def _page(params, key, secret, tries=5):
    url = f"{assert_data_host(ALPACA_DATA_HOST)}/v2/stocks/bars?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 ** i)
                continue
            raise
        except Exception:
            if i < tries - 1:
                time.sleep(2 ** i)
                continue
            raise
    raise RuntimeError("unreachable")


def fetch_batch(symbols, key, secret):
    acc: dict[str, list] = {s: [] for s in symbols}
    token = None
    while True:
        p = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": START, "end": END,
             "limit": 10000, "feed": "sip", "adjustment": "all"}
        if token:
            p["page_token"] = token
        pay = _page(p, key, secret)
        for sym, rows in (pay.get("bars") or {}).items():
            acc.setdefault(sym, []).extend(rows)
        token = pay.get("next_page_token")
        if not token:
            break
    return acc


def save(sym, rows):
    if not rows:
        return 0
    d = np.array([int(r["t"][:4] + r["t"][5:7] + r["t"][8:10]) for r in rows], dtype=np.int32)
    o = np.array([r["o"] for r in rows], dtype=np.float32)
    h = np.array([r["h"] for r in rows], dtype=np.float32)
    lo = np.array([r["l"] for r in rows], dtype=np.float32)
    c = np.array([r["c"] for r in rows], dtype=np.float32)
    v = np.array([r["v"] for r in rows], dtype=np.float32)
    order = np.argsort(d, kind="stable")
    BARS.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(BARS / f"{sym.replace('/', '_')}.npz",
                        d=d[order], o=o[order], h=h[order], l=lo[order], c=c[order], v=v[order])
    return len(d)


def main():
    ev = json.loads((ROOT / "research" / "data" / "inv0822_flow" / "raw"
                     / "index_changes.json").read_text())
    syms = {e["ticker"] for e in ev if e["date"] >= "2015-10-01"}
    syms |= {"SPY", "MDY", "IJH", "IJR", "IWM", "IWB", "RSP", "VOO", "QQQ"}
    extra = ROOT / "research" / "data" / "inv0822_flow" / "raw" / "extra_symbols.json"
    if extra.exists():
        syms |= set(json.loads(extra.read_text()))
    have = {p.stem for p in BARS.glob("*.npz")} if BARS.exists() else set()
    todo = sorted(s for s in syms if s.replace("/", "_") not in have)
    print(f"universe {len(syms)}, cached {len(have)}, to fetch {len(todo)}", flush=True)
    key, secret = load_env_credentials()
    B = 100
    got = 0
    for i in range(0, len(todo), B):
        batch = todo[i:i + B]
        try:
            acc = fetch_batch(batch, key, secret)
        except Exception as exc:  # noqa: BLE001
            print(f"batch {i}: FAILED {exc}", flush=True)
            continue
        n = 0
        for s in batch:
            rows = acc.get(s) or []
            if rows:
                n += 1
                save(s, rows)
            else:
                # mark as empty so we do not refetch forever
                np.savez_compressed(BARS / f"{s.replace('/', '_')}.npz",
                                    d=np.zeros(0, np.int32), o=np.zeros(0, np.float32),
                                    h=np.zeros(0, np.float32), l=np.zeros(0, np.float32),
                                    c=np.zeros(0, np.float32), v=np.zeros(0, np.float32))
        got += n
        print(f"batch {i//B}: {n}/{len(batch)} symbols with bars (total {got})", flush=True)
    print("done")


if __name__ == "__main__":
    main()
