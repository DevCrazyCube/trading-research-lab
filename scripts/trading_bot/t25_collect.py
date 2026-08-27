#!/usr/bin/env python3
"""T25 — cross-venue perp funding differential: the Hyperliquid collector.

Downloads Hyperliquid hourly funding history for the download universe declared in
research/trading_bot/T25_POWER_GATE.md §2b, and caches it under research/data/t25_cache/.

Free, keyless, read-only.  No order is placed and no account is touched.

Usage:
    python3 scripts/trading_bot/t25_collect.py universe
    python3 scripts/trading_bot/t25_collect.py download [--workers N]
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(REPO, "research", "data", "t25_cache")
HL_DIR = os.path.join(CACHE, "hl")
PANEL = os.path.join(REPO, "research", "data", "t23_cache", "panel")

INFO = "https://api.hyperliquid.xyz/info"
# Gate §1: Hyperliquid's earliest funding print. Gate §3: Binance panel ends 2026-07-31.
START_MS = int(dt.datetime(2023, 5, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END_MS = int(dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
# Gate §2b limb (a) screen window.
SCREEN_LO = int(dt.datetime(2023, 5, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)
SCREEN_HI = int(dt.datetime(2023, 8, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)
SCREEN_MIN_DAYS = 80

_lock = threading.Lock()
# Hyperliquid publishes 1200 request-weight/minute/IP and `fundingHistory` is weight 20,
# i.e. 60 calls/minute.  A shared token bucket keeps every worker inside that jointly.
_rate_lock = threading.Lock()
_next_slot = [0.0]
MIN_INTERVAL = 0.35
_stat = collections.Counter()


def _throttle() -> None:
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next_slot[0])
        _next_slot[0] = slot + MIN_INTERVAL
    delay = slot - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def post(payload: dict, tries: int = 8) -> object:
    body = json.dumps(payload).encode()
    for attempt in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(
                INFO, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=45) as fh:
                return json.load(fh)
        except urllib.error.HTTPError as exc:
            _stat["h%d" % exc.code] += 1
            if exc.code == 429:
                with _rate_lock:  # push every worker's next slot out together
                    _next_slot[0] = max(_next_slot[0], time.monotonic()) + 4.0 * (attempt + 1)
            if attempt == tries - 1:
                raise
        except Exception:  # noqa: BLE001 - retry on anything transport-shaped
            _stat["other"] += 1
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def binance_perp_symbols() -> set[str]:
    syms = set()
    with open(os.path.join(PANEL, "perp_daily.csv")) as fh:
        rd = csv.reader(fh)
        next(rd)
        for row in rd:
            syms.add(row[0])
    return syms


def map_binance(coin: str, syms: set[str]) -> str | None:
    """Hyperliquid coin name -> Binance USD-M symbol.  kX means 1000 X on Binance."""
    cands = [coin + "USDT"]
    if coin.startswith("k"):
        cands += [coin[1:] + "USDT", "1000" + coin[1:] + "USDT"]
    for c in cands:
        if c in syms:
            return c
    return None


def build_universe() -> dict:
    meta = post({"type": "meta"})
    hl = {u["name"]: bool(u.get("isDelisted")) for u in meta["universe"]}
    syms = binance_perp_symbols()
    overlap = {}
    for coin in hl:
        b = map_binance(coin, syms)
        if b:
            overlap[coin] = b

    vol = collections.defaultdict(float)
    days = collections.Counter()
    with open(os.path.join(PANEL, "perp_daily.csv")) as fh:
        rd = csv.reader(fh)
        next(rd)
        for row in rd:
            t = int(row[1])
            if SCREEN_LO <= t < SCREEN_HI:
                vol[row[0]] += float(row[3])
                days[row[0]] += 1

    rows = []
    for coin, b in sorted(overlap.items()):
        liquid = days[b] >= SCREEN_MIN_DAYS
        if liquid or hl[coin]:
            rows.append(
                {
                    "coin": coin,
                    "binance": b,
                    "hl_delisted": hl[coin],
                    "screen_limb": "a_liquid" if liquid else "b_delisted",
                    "screen_adv_usd": (vol[b] / days[b]) if days[b] else 0.0,
                    "screen_days": days[b],
                }
            )
    out = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hl_universe": len(hl),
        "hl_delisted_flagged": sum(1 for v in hl.values() if v),
        "binance_panel_symbols": len(syms),
        "overlap_coins": len(overlap),
        "download_universe": rows,
        "download_universe_n": len(rows),
    }
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, "universe.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return out


def fetch_coin(coin: str) -> int:
    path = os.path.join(HL_DIR, f"{coin}.json")
    if os.path.exists(path):
        with open(path) as fh:
            return len(json.load(fh)["prints"])
    prints: list[list] = []
    seen: set[int] = set()
    cursor = START_MS
    while cursor < END_MS:
        batch = post(
            {"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": END_MS}
        )
        if not batch:
            break
        for rec in batch:
            t = int(rec["time"])
            if t in seen:
                continue
            seen.add(t)
            prints.append([t, rec["fundingRate"], rec.get("premium")])
        last = int(batch[-1]["time"])
        if last <= cursor:
            break
        cursor = last + 1
        if len(batch) < 500:
            break
    prints.sort()
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"coin": coin, "prints": prints}, fh)
    os.replace(tmp, path)
    return len(prints)


def download(workers: int) -> None:
    uni = json.load(open(os.path.join(CACHE, "universe.json")))
    coins = [r["coin"] for r in uni["download_universe"]]
    os.makedirs(HL_DIR, exist_ok=True)
    todo = list(coins)
    done = {"n": 0}

    def worker():
        while True:
            with _lock:
                if not todo:
                    return
                coin = todo.pop(0)
            try:
                n = fetch_coin(coin)
                msg = f"{coin} {n} stats={dict(_stat)}"
            except Exception as exc:  # noqa: BLE001
                msg = f"{coin} FAILED {exc}"
            with _lock:
                done["n"] += 1
                print(f"[{done['n']}/{len(coins)}] {msg}", flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("download complete", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["universe", "download"])
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    if args.cmd == "universe":
        out = build_universe()
        print(json.dumps({k: v for k, v in out.items() if k != "download_universe"}, indent=1))
        limb_a = sum(1 for r in out["download_universe"] if r["screen_limb"] == "a_liquid")
        print(f"limb a (liquid) {limb_a}  limb b (HL-delisted only) "
              f"{out['download_universe_n'] - limb_a}")
    else:
        download(args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
