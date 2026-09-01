#!/usr/bin/env python3
"""Virality forward paper-decider (Gate B) — measures, honestly and $0, whether the virality thesis is +EV.

Each cycle: pull the DexScreener attention universe (boosted Solana tokens — a coin-mapped proxy for
"getting pushed right now"), fetch each pair's live trading data, keep a per-mint unique-buyer HISTORY,
and PAPER-ENTER a coin the instant its buyer breadth INFLECTS (the crowd is arriving) WHILE it is
exitable (screen PASS) and past the t0 dev-casino (age gate). Then track forward and exit by a convex
rule (tight all-cost stop, let winners run on a widening trail). Every resolved trade is appended to a
hash-chained ledger with its realized return. NO wallet, no orders, no spend — a pure forward
measurement toward the pre-registered N=120 decision.

Run detached:  python -m scripts.trading_bot.memebot.virality_tracker
Read the result any time:  python -m scripts.trading_bot.memebot.virality_tracker --report
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys
import time

from . import net
from . import screen
from .virality_probe import SPEC

ROOT = pathlib.Path(__file__).resolve().parents[3]
DATA = ROOT / "research" / "data" / "virality"
STATE = DATA / "tracker_state.json"
LEDGER = DATA / "paper_trades.jsonl"
GENESIS = "0" * 64

POLL_SECONDS = 150
MIN_AGE_MIN = 60                 # past the t0 dev/sniper casino
BREADTH_INFLECT_MIN = 0.15       # unique buyers up >= 15% vs the prior observation = crowd arriving
HARD_STOP = 0.12                 # −12% all-cost stop (the honest, toll-doubled memecoin stop)
TOLL = 0.03                      # ~3% round-trip toll charged on every resolved trade
TARGET_N = 120                   # pre-registered decision sample
HISTORY = 6


def _sha(v) -> str:
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value))
    tmp.replace(path)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _universe() -> list[str]:
    mints = []
    for url in ("https://api.dexscreener.com/token-boosts/latest/v1",
                "https://api.dexscreener.com/token-boosts/top/v1"):
        try:
            d = net.http_get_json(url)
            for x in (d if isinstance(d, list) else d.get("data") or []):
                if str(x.get("chainId")) == "solana" and x.get("tokenAddress"):
                    mints.append(x["tokenAddress"])
        except Exception:  # noqa: BLE001
            continue
    return list(dict.fromkeys(mints))


def _pair(mint: str) -> dict | None:
    """Best (deepest, actively-traded) Solana pair for a token."""
    try:
        d = net.http_get_json("https://api.dexscreener.com/latest/dex/tokens/" + mint)
    except Exception:  # noqa: BLE001
        return None
    best = None
    for p in (d.get("pairs") or []):
        if str(p.get("chainId")) != "solana":
            continue
        liq = _f((p.get("liquidity") or {}).get("usd")) or 0
        if best is None or liq > best[0]:
            best = (liq, p)
    if best is None:
        return None
    p = best[1]
    tx = (p.get("txns") or {}).get("h1") or (p.get("txns") or {}).get("h24") or {}
    created = p.get("pairCreatedAt")
    return {
        "mint": mint, "symbol": (p.get("baseToken") or {}).get("symbol"),
        "price": _f(p.get("priceUsd")), "reserve_usd": _f((p.get("liquidity") or {}).get("usd")),
        "fdv_usd": _f(p.get("fdv")) or _f(p.get("marketCap")),
        "age_minutes": ((time.time() * 1000 - created) / 60000.0) if created else None,
        "buys": int(tx.get("buys") or 0), "sells": int(tx.get("sells") or 0),
        "dex": p.get("dexId"),
    }


def _screen_ok(c: dict) -> bool:
    coin = dict(c, buyers=c["buys"], sellers=c["sells"])
    return screen.screen_coin(coin, {"screen": SPEC}).get("verdict") == "PASS"


def _append_ledger(row: dict) -> None:
    prev = GENESIS
    if LEDGER.exists():
        try:
            last = LEDGER.read_text().splitlines()[-1]
            prev = json.loads(last).get("record_hash", GENESIS)
        except (OSError, ValueError, IndexError):
            prev = GENESIS
    body = {**row, "prev_hash": prev}
    line = json.dumps({**body, "record_hash": _sha(body)}, separators=(",", ":"))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(line + "\n")


def run_once() -> dict:
    st = _load(STATE, {"hist": {}, "open": {}})
    now = int(time.time())
    universe = _universe()
    entered = closed = 0

    for mint in universe:
        c = _pair(mint)
        if c is None or c["price"] is None or c["price"] <= 0:
            continue
        h = st["hist"].setdefault(mint, [])
        h.append({"t": now, "buys": c["buys"], "price": c["price"]})
        del h[:-HISTORY]
        # --- entry: breadth inflection + exitable + past the t0 casino + not already open ---
        if mint not in st["open"] and len(h) >= 2 and (c["age_minutes"] or 0) >= MIN_AGE_MIN:
            prev_b = h[-2]["buys"]
            inflect = prev_b > 0 and (c["buys"] - prev_b) / prev_b >= BREADTH_INFLECT_MIN
            if inflect and _screen_ok(c):
                st["open"][mint] = {"entry": c["price"], "peak": c["price"], "t0": now,
                                    "symbol": c["symbol"]}
                entered += 1

    # --- service open positions: mark, convex exit ---
    for mint, pos in list(st["open"].items()):
        c = _pair(mint)
        price = c["price"] if c and c["price"] else None
        if price is None:
            continue
        pos["peak"] = max(pos["peak"], price)
        gain = price / pos["entry"] - 1.0
        peak_gain = pos["peak"] / pos["entry"] - 1.0
        # widening trail: let winners run — the wider the peak, the looser the give-back allowed
        trail = 0.18 if peak_gain < 0.5 else (0.25 if peak_gain < 1.5 else 0.35)
        exit_now = reason = None
        if gain <= -HARD_STOP:
            exit_now, reason = True, "HARD_STOP"
        elif peak_gain >= 0.12 and price <= pos["peak"] * (1 - trail):
            exit_now, reason = True, "TRAIL"
        elif now - pos["t0"] > 12 * 3600:
            exit_now, reason = True, "HORIZON"
        if exit_now:
            r = gain - TOLL   # all-cost realized return
            _append_ledger({"kind": "resolved", "mint": mint, "symbol": pos.get("symbol"),
                            "entry": pos["entry"], "exit": price, "gross_return": round(gain, 5),
                            "net_return": round(r, 5), "reason": reason, "held_s": now - pos["t0"],
                            "resolved_unix": now})
            del st["open"][mint]
            closed += 1

    st["hist"] = {m: h for m, h in st["hist"].items() if h and now - h[-1]["t"] < 6 * 3600}
    _save(STATE, st)
    return {"universe": len(universe), "open": len(st["open"]), "entered": entered, "closed": closed}


def report() -> dict:
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()] if LEDGER.exists() else []
    res = [r for r in rows if r.get("kind") == "resolved"]
    n = len(res)
    if not n:
        return {"resolved": 0, "message": "no resolved paper trades yet"}
    rets = [r["net_return"] for r in res]
    mean = sum(rets) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / n) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    wins = sum(1 for x in rets if x > 0)
    st = _load(STATE, {"open": {}})
    return {"resolved": n, "target": TARGET_N, "open": len(st.get("open", {})),
            "mean_net_R": round(mean, 4), "ci95_lo": round(mean - 1.96 * se, 4),
            "ci95_hi": round(mean + 1.96 * se, 4), "win_rate": round(wins / n, 3),
            "verdict": ("PASS_so_far" if mean - 1.96 * se > 0 else
                        "KILL_so_far" if mean + 1.96 * se < 0 else "UNDECIDED"),
            "note": f"pre-registered decision at N={TARGET_N}"}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--report" in argv:
        print(json.dumps(report(), indent=2))
        return 0
    once = "--once" in argv
    print(f"virality tracker: forward paper decider (poll {POLL_SECONDS}s, target N={TARGET_N})", flush=True)
    while True:
        try:
            r = run_once()
            print(json.dumps({"ts": int(time.time()), **r, **report()}, separators=(",", ":")), flush=True)
        except Exception as exc:  # noqa: BLE001 — a bad cycle must not kill the collector
            print(json.dumps({"cycle_error": str(exc)[:160]}), flush=True)
        if once:
            break
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
