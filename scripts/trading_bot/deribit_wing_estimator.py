#!/usr/bin/env python3
"""Bought-convexity wing estimator on FREE Deribit option-chain snapshots.

Strategy under test: "Leverage-Fuel Convexity" (SIZE_STRATEGY_SHORTLIST #1) — buy the
~15-delta weekly BTC/ETH wing (nearest expiry 3-10 DTE, |delta|~0.15 call & put),
expecting a liquidation cascade to gap through the strike. Max loss = premium paid,
uncapped upside.

This harness validates the ENTRY side on real Deribit data (a single month-start
snapshot cannot give expiry-crossing outcomes). For each snapshot it:
  (a) parses the chain, groups by underlying+expiry, and selects the weekly 15-delta wing;
  (b) prices ENTRY at the real ASK (not mark), charges the Deribit options fee
      = min(0.0003 coin, 12.5% of premium) per contract, and reports the fee-cap bite;
  (c) measures the live wing bid/ask SPREAD (relative), the input the pre-registered
      break-even gate depends on.

Deribit conventions honoured:
  * Option prices are quoted in the UNDERLYING COIN. USD premium = price_coin * underlying.
  * Taker fee per option = min(0.0003 * <coin>, 0.125 * option_price_coin). On cheap wings
    the 12.5% cap binds (0.125*price < 0.0003), so the effective fee is 12.5% of premium.
    (Fee is a fraction of premium regardless, so it is unit-free in coin terms here.)

USAGE:
    python3 scripts/trading_bot/deribit_wing_estimator.py                 # all cached snapshots
    python3 scripts/trading_bot/deribit_wing_estimator.py --snapshot <path.csv.gz>
    python3 scripts/trading_bot/deribit_wing_estimator.py --json          # emit RESULT json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import pathlib
import statistics as st

SNAPDIR = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "deribit_free_samples"
RESULT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot" / "DERIBIT_FREE_WING_RESULT.json"

TARGET_DELTA = 0.15
DTE_LO, DTE_HI = 3.0, 10.0        # "weekly" wing window (days to expiry)
FLAT_FEE_COIN = 0.0003            # Deribit per-contract options fee, in coin
FEE_CAP_FRAC = 0.125              # capped at 12.5% of option premium


def _f(v: str):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def load_snapshot(path: pathlib.Path) -> tuple[list[dict], int]:
    with gzip.open(path, "rt") as fh:
        rows = list(csv.DictReader(fh))
    snap_us = 0
    for r in rows:
        t = _f(r.get("timestamp"))
        if t:
            snap_us = max(snap_us, int(t))
    return rows, snap_us


def parse_symbol(sym: str):
    # e.g. BTC-2JUN23-27000-C  /  ETH-9JUN23-2100-P
    parts = sym.split("-")
    if len(parts) != 4:
        return None
    coin, expiry_str, strike, cp = parts
    return coin, expiry_str, strike, cp


def pick_wing(rows: list[dict], coin: str, snap_us: int):
    """Return dict with the selected weekly 15-delta call & put for one coin, or None."""
    snap_s = snap_us / 1e6
    # collect this coin's options with a live two-sided quote and a delta
    opts = []
    for r in rows:
        sym = r.get("symbol", "")
        p = parse_symbol(sym)
        if not p or p[0] != coin:
            continue
        exp = _f(r.get("expiration"))
        delta = _f(r.get("delta"))
        ask = _f(r.get("ask_price"))
        bid = _f(r.get("bid_price"))
        und = _f(r.get("underlying_price"))
        if exp is None or delta is None or ask is None or bid is None or und is None:
            continue
        if ask <= 0 or bid <= 0:
            continue  # need a live two-sided market to price entry + spread honestly
        dte = (exp / 1e6 - snap_s) / 86_400.0
        opts.append({
            "symbol": sym, "type": r.get("type"), "dte": dte, "delta": delta,
            "strike": _f(r.get("strike_price")), "bid": bid, "ask": ask,
            "und": und, "mark": _f(r.get("mark_price")),
            "bid_iv": _f(r.get("bid_iv")), "ask_iv": _f(r.get("ask_iv")),
            "mark_iv": _f(r.get("mark_iv")), "oi": _f(r.get("open_interest")),
            "vega": _f(r.get("vega")), "gamma": _f(r.get("gamma")),
            "theta": _f(r.get("theta")), "exp": exp,
        })
    if not opts:
        return None

    # candidate expiries inside the weekly window
    exps_in = sorted({o["exp"] for o in opts if DTE_LO <= o["dte"] <= DTE_HI})
    used_window = True
    if exps_in:
        target_exp = min(exps_in, key=lambda e: (e / 1e6 - snap_s) / 86400.0)  # nearest within window
    else:
        # no expiry in 3-10 DTE (e.g. only same-day or far) -> nearest expiry with dte>=1
        cand = sorted({o["exp"] for o in opts if o["dte"] >= 1.0})
        if not cand:
            return None
        target_exp = min(cand, key=lambda e: abs((e / 1e6 - snap_s) / 86400.0 - 5.0))
        used_window = False

    chain = [o for o in opts if o["exp"] == target_exp]
    dte = (target_exp / 1e6 - snap_s) / 86400.0

    def nearest(cp: str):
        cands = [o for o in chain if (o["delta"] > 0 if cp == "C" else o["delta"] < 0)]
        if not cands:
            return None
        return min(cands, key=lambda o: abs(abs(o["delta"]) - TARGET_DELTA))

    call = nearest("C")
    put = nearest("P")
    if not call or not put:
        return None
    # ATM implied vol for this expiry: mark_iv of the option nearest |delta|=0.5
    atm = min(chain, key=lambda o: abs(abs(o["delta"]) - 0.5))
    atm_iv = atm["mark_iv"]
    return {"coin": coin, "dte": dte, "expiry_us": target_exp,
            "in_window": used_window, "call": call, "put": put,
            "atm_iv": atm_iv, "n_chain": len(chain), "underlying": chain[0]["und"]}


def wing_metrics(o: dict, atm_iv: float | None) -> dict:
    bid, ask = o["bid"], o["ask"]
    mid = 0.5 * (bid + ask)
    spread_rel = (ask - bid) / mid if mid > 0 else None
    # fee is a fraction of premium; in coin terms fee = min(flat, cap_frac*price)
    fee_coin = min(FLAT_FEE_COIN, FEE_CAP_FRAC * ask)
    fee_frac_of_prem = fee_coin / ask if ask > 0 else None
    cap_binds = (FEE_CAP_FRAC * ask) < FLAT_FEE_COIN
    prem_usd = ask * o["und"]
    fee_usd = fee_coin * o["und"]
    # Break-even underlying move to expiry, buying at ask + fee (Deribit inverse settlement:
    # call value in coin = max(0,S-K)/S ; put value = max(0,K-S)/S). Solve value == entry cost.
    cost = ask + fee_coin  # coin, per contract
    K, S0 = o["strike"], o["und"]
    be_move = None
    if K and S0 and cost < 1.0:
        if o["delta"] > 0:      # call: (S-K)/S = cost -> S* = K/(1-cost)
            be_move = K / (1.0 - cost) / S0 - 1.0
        else:                    # put:  (K-S)/S = cost -> S* = K/(1+cost)
            be_move = K / (1.0 + cost) / S0 - 1.0
    # skew premium the buyer pays: wing IV over ATM IV
    skew_prem = None
    if atm_iv and o["mark_iv"]:
        skew_prem = o["mark_iv"] / atm_iv - 1.0
    return {
        "breakeven_move_pct": round(be_move * 100, 2) if be_move is not None else None,
        "wing_iv": o["mark_iv"], "skew_over_atm": round(skew_prem, 3) if skew_prem is not None else None,
        "symbol": o["symbol"], "delta": round(o["delta"], 4), "strike": o["strike"],
        "bid_coin": bid, "ask_coin": ask, "mid_coin": round(mid, 8),
        "spread_rel": round(spread_rel, 4) if spread_rel is not None else None,
        "premium_usd": round(prem_usd, 2), "fee_coin": round(fee_coin, 8),
        "fee_usd": round(fee_usd, 4), "fee_frac_of_premium": round(fee_frac_of_prem, 4),
        "fee_cap_binds": cap_binds, "entry_cost_usd": round(prem_usd + fee_usd, 2),
        "oi": o["oi"], "mark_iv": o["mark_iv"], "bid_iv": o["bid_iv"], "ask_iv": o["ask_iv"],
        "vega": o["vega"], "gamma": o["gamma"], "theta": o["theta"],
    }


def analyse_snapshot(path: pathlib.Path) -> dict:
    rows, snap_us = load_snapshot(path)
    snap_iso = dt.datetime.fromtimestamp(snap_us / 1e6, dt.timezone.utc).isoformat() if snap_us else None
    out = {"file": path.name, "snapshot_utc": snap_iso, "n_instruments": len(rows), "wings": {}}
    for coin in ("BTC", "ETH"):
        w = pick_wing(rows, coin, snap_us)
        if not w:
            out["wings"][coin] = None
            continue
        out["wings"][coin] = {
            "dte": round(w["dte"], 2), "in_dte_window": w["in_window"],
            "underlying": round(w["underlying"], 2), "n_expiry_chain": w["n_chain"],
            "atm_iv": w["atm_iv"],
            "call": wing_metrics(w["call"], w["atm_iv"]),
            "put": wing_metrics(w["put"], w["atm_iv"]),
        }
    return out


def summarise(results: list[dict]) -> dict:
    spreads, fee_fracs, cap_flags, deltas, skews, be_moves = [], [], [], [], [], []
    for res in results:
        for coin, w in res["wings"].items():
            if not w:
                continue
            for leg in ("call", "put"):
                m = w[leg]
                if m["spread_rel"] is not None:
                    spreads.append(m["spread_rel"])
                fee_fracs.append(m["fee_frac_of_premium"])
                cap_flags.append(m["fee_cap_binds"])
                deltas.append(abs(m["delta"]))
                if m["skew_over_atm"] is not None:
                    skews.append(m["skew_over_atm"])
                if m["breakeven_move_pct"] is not None:
                    be_moves.append(abs(m["breakeven_move_pct"]))

    def q(xs, p):
        if not xs:
            return None
        xs = sorted(xs)
        i = min(len(xs) - 1, int(p * (len(xs) - 1)))
        return round(xs[i], 4)

    n = len(spreads)
    return {
        "n_wing_legs": n,
        "spread_rel_median": round(st.median(spreads), 4) if spreads else None,
        "spread_rel_mean": round(st.mean(spreads), 4) if spreads else None,
        "spread_rel_p10": q(spreads, 0.10), "spread_rel_p90": q(spreads, 0.90),
        "spread_rel_min": round(min(spreads), 4) if spreads else None,
        "spread_rel_max": round(max(spreads), 4) if spreads else None,
        "fee_frac_median": round(st.median(fee_fracs), 4) if fee_fracs else None,
        "fee_cap_binds_share": round(sum(cap_flags) / len(cap_flags), 3) if cap_flags else None,
        "abs_delta_median": round(st.median(deltas), 4) if deltas else None,
        "wing_skew_over_atm_median": round(st.median(skews), 3) if skews else None,
        "breakeven_move_pct_median": round(st.median(be_moves), 2) if be_moves else None,
        "breakeven_move_pct_min": round(min(be_moves), 2) if be_moves else None,
        "breakeven_move_pct_max": round(max(be_moves), 2) if be_moves else None,
        "assumed_spread_range": [0.10, 0.17],
        "assumed_fee_cap": 0.125,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", help="single snapshot csv.gz (default: all cached)")
    ap.add_argument("--json", action="store_true", help="write RESULT json")
    args = ap.parse_args()

    if args.snapshot:
        paths = [pathlib.Path(args.snapshot)]
    else:
        paths = sorted(SNAPDIR.glob("snapshot_*.csv.gz"))
    if not paths:
        raise SystemExit("no snapshots found; run deribit_free_snapshot.py first")

    results = [analyse_snapshot(p) for p in paths]
    summary = summarise(results)

    for res in results:
        print(f"\n=== {res['file']}  ({res['snapshot_utc']})  n={res['n_instruments']} ===")
        for coin in ("BTC", "ETH"):
            w = res["wings"].get(coin)
            if not w:
                print(f"  {coin}: no weekly 15-delta wing (no live two-sided quotes)")
                continue
            tag = "" if w["in_dte_window"] else "  [!] no 3-10 DTE expiry; nearest used"
            print(f"  {coin}  under={w['underlying']}  dte={w['dte']}{tag}")
            for leg in ("call", "put"):
                m = w[leg]
                sk = f"{m['skew_over_atm']*100:+.0f}%" if m['skew_over_atm'] is not None else "n/a"
                print(f"    {leg:4s} {m['symbol']:22s} d={m['delta']:+.3f} K={m['strike']:.0f} "
                      f"spread={m['spread_rel']*100:.1f}% prem=${m['premium_usd']:.0f} "
                      f"fee={m['fee_frac_of_premium']*100:.1f}%{'[cap]' if m['fee_cap_binds'] else '[flat]'} "
                      f"BE_move={m['breakeven_move_pct']:+.1f}% skew_vs_atm={sk} OI={m['oi']}")

    print("\n===== POOLED SUMMARY =====")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if args.json:
        payload = {
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "strategy": "Leverage-Fuel Convexity (SIZE #1) — free-sample entry-side validation",
            "data_source": "Tardis FREE first-of-month deribit options_chain samples (zero spend)",
            "target_delta": TARGET_DELTA, "dte_window": [DTE_LO, DTE_HI],
            "summary": summary, "snapshots": results,
        }
        RESULT.write_text(json.dumps(payload, indent=2))
        print(f"\nwrote {RESULT}")


if __name__ == "__main__":
    main()
