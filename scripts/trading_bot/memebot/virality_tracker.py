#!/usr/bin/env python3
"""Virality forward paper-decider — Gate B, V2. Measures, honestly and $0, whether the virality thesis
is +EV as a cheap directional screen.

V2 supersedes V1 (retired 2026-09-01, `RETIREMENT_20260901.json`): an adversarial audit correctly found
two real *signal* bugs that made the V1 ledger invalid — (1) it read DexScreener's rolling h1 trade
count as "unique-buyer breadth", a count that can FALL as the window ages, and (2) it re-picked the
"deepest pair" each cycle, so it compared counts/prices across DIFFERENT pools. V2 fixes both:

  * PAIR IDENTITY IS PINNED. A mint's pair is chosen once (deepest at first sight) and every later
    observation re-fetches THAT exact pair address — the count and price series are one market.
  * BREADTH = the m5 (5-minute) buy RATE on that pinned pair, not a cumulative rolling count. Entry
    fires only on m5-buy acceleration WITH net demand (buys > sells) AND a confirming price rise —
    three independent conditions, so a lone rolling-window wobble cannot trigger it.

What V2 deliberately does NOT fix (and does not hide): fills use the observed pair price with a flat
toll, not a causal decision-to-landing execution path with exact costs. So V2 is an OPTIMISTIC BOUND and
a cheap FILTER: a KILL is decisive (real execution only makes it worse); a PASS is necessary-but-not-
sufficient — it would justify building the causal-fill V3, never a claim of live money. The ledger is
hash-chained for tamper-EVIDENCE; the real external append-only anchor is committing it to git (a local
self-hash is not a security boundary for a single-operator paper log — do not pretend otherwise).

Run:    python -m scripts.trading_bot.memebot.virality_tracker
Report: python -m scripts.trading_bot.memebot.virality_tracker --report
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

INSTRUMENT = "VIRALITY_GATE_B_V2"
ROOT = pathlib.Path(__file__).resolve().parents[3]
DATA = ROOT / "research" / "data" / "virality"
STATE = DATA / "tracker_state_v2.json"
LEDGER = DATA / "paper_trades_v2.jsonl"
PREREG = DATA / "PREREGISTRATION_V2.md"
RETIREMENT = DATA / "RETIREMENT_V2.json"
GENESIS = "0" * 64

POLL_SECONDS = 150
MIN_AGE_MIN = 60                 # past the t0 dev/sniper casino
M5_BUYS_FLOOR = 10               # ignore micro-counts where a delta is pure noise
BREADTH_INFLECT_MIN = 0.40       # m5 buy-rate up >= 40% vs the prior observation on the SAME pair
HARD_STOP = 0.12                 # -12% all-cost stop (the honest, toll-doubled memecoin stop)
TOLL = 0.03                      # ~3% round-trip toll charged on every resolved trade (optimistic bound)
TARGET_N = 120                   # pre-registered decision sample
HISTORY = 6


def _sha(v) -> str:
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_sha(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _require_not_retired() -> None:
    """Kept from V1's hardening: if a valid retirement authority is dropped for THIS instrument, refuse."""
    if not RETIREMENT.exists():
        return
    try:
        row = json.loads(RETIREMENT.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError("virality V2 retirement authority is unreadable") from exc
    if isinstance(row, dict) and row.get("instrument") == INSTRUMENT:
        raise RuntimeError(f"{INSTRUMENT} is retired: {row.get('status')}")


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


def _shape(p: dict) -> dict:
    """Normalise one DexScreener pair dict into the fields the screen + signal need."""
    tx5 = (p.get("txns") or {}).get("m5") or {}
    tx1 = (p.get("txns") or {}).get("h1") or {}
    created = p.get("pairCreatedAt")
    return {
        "mint": (p.get("baseToken") or {}).get("address"),
        "pair": p.get("pairAddress"),
        "symbol": (p.get("baseToken") or {}).get("symbol"),
        "price": _f(p.get("priceUsd")),
        "reserve_usd": _f((p.get("liquidity") or {}).get("usd")),
        "fdv_usd": _f(p.get("fdv")) or _f(p.get("marketCap")),
        "age_minutes": ((time.time() * 1000 - created) / 60000.0) if created else None,
        "m5_buys": int(tx5.get("buys") or 0), "m5_sells": int(tx5.get("sells") or 0),
        # the exitability screen wants the coarse cumulative counts (its wash / honeypot proxies)
        "buys": int(tx1.get("buys") or 0), "sells": int(tx1.get("sells") or 0),
        "dex": p.get("dexId"),
    }


# --- CLOSURE-SAFE mark fallback --------------------------------------------------------------------
# The pinned DexScreener pairs endpoint goes dark for >=60-min-old boosted pump.fun bonding-curve coins
# within a few cycles, which sent 100% of VIRALITY_ARRIVAL_V2_2's finalized positions to MEASUREMENT_VOID
# (the coin was still ALIVE on-chain; only the free price feed abandoned it). When that happens we price
# the open position from OUR OWN local trade tape instead of letting the mark go None. This module is in
# NO arena arm's code_sha256() closure, so editing it drifts NO arm -> plain restart, no re-epoch.
_PAIR_MINT: dict[str, str] = {}                 # pairAddress -> mint, learned from healthy observations
_PAIR_MINT_LOADED = False
_PAIR_MINT_PATH = ROOT / "research" / "data" / "memebot_cache" / "arena_pair_mint.json"
_TAPE_MARK_MAX_AGE_S = 330.0                     # a tape trade must be this fresh to mark a position
_TAPE_TAIL_BYTES = 4 * 1024 * 1024               # reverse-read only this much tail (bounds cost)


def _load_pair_mint() -> None:
    global _PAIR_MINT_LOADED
    if _PAIR_MINT_LOADED:
        return
    _PAIR_MINT_LOADED = True
    try:
        stored = json.loads(_PAIR_MINT_PATH.read_text())
    except (OSError, ValueError):
        return
    if isinstance(stored, dict):
        _PAIR_MINT.update({k: v for k, v in stored.items() if isinstance(k, str) and isinstance(v, str)})


def _remember(shape: dict | None) -> None:
    """Learn a pairAddress->mint mapping from a HEALTHY DexScreener shape and persist it (survives restart)."""
    if not shape:
        return
    pair, mint = shape.get("pair"), shape.get("mint")
    if not (isinstance(pair, str) and isinstance(mint, str) and pair and mint):
        return
    _load_pair_mint()
    if _PAIR_MINT.get(pair) == mint:
        return
    _PAIR_MINT[pair] = mint
    try:
        _PAIR_MINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PAIR_MINT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_PAIR_MINT, separators=(",", ":")))
        tmp.replace(_PAIR_MINT_PATH)
    except OSError:
        pass


def _tape_mark(mint: str) -> float | None:
    """Most-recent pump.fun bonding-curve trade for `mint` on our local tape -> USD price, or None.

    Reverse-reads only the fresh tail of the tape and converts the on-chain reserves with a FRESH SOL/USD.
    Fail-closed: any missing/stale/parse problem returns None so the next fallback (or unpriced) runs."""
    try:
        from . import ws_data
        from ..aftershock import solusd_recorder
    except Exception:  # noqa: BLE001 -- optional deps; degrade to no tape mark
        return None
    now_ns = time.time_ns()
    floor_ns = now_ns - int(_TAPE_MARK_MAX_AGE_S * 1e9)
    try:
        with ws_data.TRADE_BUFFER_PATH.open("rb") as fh:
            size = fh.seek(0, 2)
            fh.seek(max(0, size - _TAPE_TAIL_BYTES))
            tail = fh.read()
    except OSError:
        return None
    best = None
    for raw in reversed(tail.split(b"\n")):        # newest-first
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue                                # a partial first line, or corruption — skip
        rn = row.get("received_unix_nanos")
        if type(rn) is not int:
            continue
        if rn < floor_ns:
            break                                   # everything older is outside the freshness window
        if (row.get("mint") == mint and row.get("pool") == "pump"
                and row.get("tx_type") in ("buy", "sell")):
            best = row
            break                                   # first hit scanning backwards == most recent
    if best is None:
        return None
    try:
        v_sol = float(best["virtual_sol"]); v_tok = float(best["virtual_tokens"])
        obs = solusd_recorder.latest_observation(
            decision_unix_nanos=now_ns, max_local_age_nanos=120_000_000_000)
        sol_usd = float(obs.value_str)
    except Exception:  # noqa: BLE001
        return None
    if v_sol > 0 and v_tok > 0 and sol_usd > 0:
        return (v_sol / v_tok) * sol_usd
    return None


def _deepest_pair(mint: str) -> dict | None:
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
    shape = _shape(best[1]) if best else None
    _remember(shape)                                # pin the pair->mint mapping at first sight
    return shape


def _pinned_pair(pair_addr: str) -> dict | None:
    """Re-fetch ONE specific pair by address — this is what pins market identity across observations.

    If the pinned pairs endpoint goes dark (the coin drops off DexScreener's pair index while still alive
    on-chain), fall back to a mark from our own local trade tape so an OPEN position gets a real mark
    instead of a MEASUREMENT_VOID. Market identity stays pinned (same pair_addr + learned mint)."""
    shape = None
    try:
        d = net.http_get_json("https://api.dexscreener.com/latest/dex/pairs/solana/" + pair_addr)
    except Exception:  # noqa: BLE001
        d = None
    if d:
        pairs = d.get("pairs") or ([d["pair"]] if d.get("pair") else [])
        shape = _shape(pairs[0]) if pairs else None
    if shape and shape.get("price"):
        _remember(shape)
        return shape
    # pinned endpoint dark -> tape fallback for the still-alive coin (only the price is needed to mark/exit)
    _load_pair_mint()
    mint = _PAIR_MINT.get(pair_addr)
    if mint:
        price = _tape_mark(mint)
        if price:
            return {"mint": mint, "pair": pair_addr, "symbol": None, "price": price,
                    "reserve_usd": None, "fdv_usd": None, "age_minutes": None,
                    "m5_buys": 0, "m5_sells": 0, "buys": 0, "sells": 0, "dex": "pumpfun-tape"}
    return shape


def _screen_ok(c: dict) -> bool:
    coin = dict(c, buyers=c["buys"], sellers=c["sells"])
    return screen.screen_coin(coin, {"screen": SPEC}).get("verdict") == "PASS"


def _ledger_head() -> str:
    if not LEDGER.exists():
        return GENESIS
    try:
        return json.loads(LEDGER.read_text().splitlines()[-1]).get("record_hash", GENESIS)
    except (OSError, ValueError, IndexError):
        return GENESIS


def _append_ledger(row: dict) -> None:
    body = {**row, "prev_hash": _ledger_head()}
    line = json.dumps({**body, "record_hash": _sha(body)}, separators=(",", ":"))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(line + "\n")


def _ensure_genesis() -> None:
    """Bind the ledger to this code + prereg once, up front (tamper-EVIDENCE; git is the real anchor)."""
    if LEDGER.exists():
        return
    _append_ledger({"kind": "genesis", "instrument": INSTRUMENT,
                    "code_sha256": _file_sha(pathlib.Path(__file__)),
                    "prereg_sha256": _file_sha(PREREG),
                    "spec_sha256": _sha(SPEC), "created_unix": int(time.time())})


def run_once() -> dict:
    _require_not_retired()
    _ensure_genesis()
    st = _load(STATE, {"hist": {}, "open": {}})
    now = int(time.time())
    universe = _universe()
    entered = closed = 0

    for mint in universe:
        h = st["hist"].get(mint)
        # observe the SAME pinned pair once we've chosen one; otherwise pick the deepest and pin it
        c = _pinned_pair(h[-1]["pair"]) if (h and h[-1].get("pair")) else _deepest_pair(mint)
        if c is None or c["pair"] is None or not c["price"] or c["price"] <= 0:
            continue
        h = st["hist"].setdefault(mint, [])
        h.append({"t": now, "pair": c["pair"], "m5_buys": c["m5_buys"],
                  "m5_sells": c["m5_sells"], "price": c["price"]})
        del h[:-HISTORY]
        # entry: m5-buy acceleration + net demand + confirming price rise, on the SAME pinned pair,
        # past t0, exitable, not already open. Three conditions guard the rolling-window artifact.
        if mint not in st["open"] and len(h) >= 2 and h[-1]["pair"] == h[-2]["pair"] \
                and (c["age_minutes"] or 0) >= MIN_AGE_MIN:
            prev = h[-2]
            accel = (prev["m5_buys"] > 0 and c["m5_buys"] >= M5_BUYS_FLOOR
                     and (c["m5_buys"] - prev["m5_buys"]) / prev["m5_buys"] >= BREADTH_INFLECT_MIN)
            net_demand = c["m5_buys"] > c["m5_sells"]
            price_up = c["price"] > prev["price"]
            if accel and net_demand and price_up and _screen_ok(c):
                st["open"][mint] = {"entry": c["price"], "peak": c["price"], "t0": now,
                                    "pair": c["pair"], "symbol": c["symbol"]}
                entered += 1

    # service open positions on their pinned pair: mark, convex exit
    for mint, pos in list(st["open"].items()):
        c = _pinned_pair(pos["pair"])
        price = c["price"] if c and c["price"] else None
        if price is None:
            continue
        pos["peak"] = max(pos["peak"], price)
        gain = price / pos["entry"] - 1.0
        peak_gain = pos["peak"] / pos["entry"] - 1.0
        trail = 0.18 if peak_gain < 0.5 else (0.25 if peak_gain < 1.5 else 0.35)
        exit_now = reason = None
        if gain <= -HARD_STOP:
            exit_now, reason = True, "HARD_STOP"
        elif peak_gain >= 0.12 and price <= pos["peak"] * (1 - trail):
            exit_now, reason = True, "TRAIL"
        elif now - pos["t0"] > 12 * 3600:
            exit_now, reason = True, "HORIZON"
        if exit_now:
            r = gain - TOLL
            _append_ledger({"kind": "resolved", "mint": mint, "symbol": pos.get("symbol"),
                            "pair": pos["pair"], "entry": pos["entry"], "exit": price,
                            "gross_return": round(gain, 5), "net_return": round(r, 5),
                            "reason": reason, "held_s": now - pos["t0"], "resolved_unix": now})
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
        return {"instrument": INSTRUMENT, "resolved": 0, "message": "no resolved paper trades yet"}
    rets = [r["net_return"] for r in res]
    mean = sum(rets) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / n) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    wins = sum(1 for x in rets if x > 0)
    st = _load(STATE, {"open": {}})
    return {"instrument": INSTRUMENT, "resolved": n, "target": TARGET_N, "open": len(st.get("open", {})),
            "mean_net_R": round(mean, 4), "ci95_lo": round(mean - 1.96 * se, 4),
            "ci95_hi": round(mean + 1.96 * se, 4), "win_rate": round(wins / n, 3),
            "verdict": ("PASS_so_far" if mean - 1.96 * se > 0 else
                        "KILL_so_far" if mean + 1.96 * se < 0 else "UNDECIDED"),
            "note": f"optimistic-bound cheap filter; decision at N={TARGET_N}"}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--report" in argv:
        print(json.dumps(report(), indent=2))
        return 0
    once = "--once" in argv
    print(f"virality tracker {INSTRUMENT}: forward paper decider (poll {POLL_SECONDS}s, N={TARGET_N})",
          flush=True)
    while True:
        try:
            r = run_once()
            print(json.dumps({"ts": int(time.time()), **r, **report()}, separators=(",", ":")), flush=True)
        except Exception as exc:  # noqa: BLE001 — a bad cycle must not kill the collector
            print(json.dumps({"cycle_error": str(exc)[:200]}), flush=True)
        if once:
            break
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
