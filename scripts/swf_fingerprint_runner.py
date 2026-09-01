#!/usr/bin/env python3
"""SWF — Sniper-Wall Fingerprint test. Invention-round survivor #1; tested honestly on burned window-1.

Claim: among launches you would actually enter (they PASS B20B, largest wallet < 0.95 at t0+60), the
first K buys arrive in one of two mechanically distinguishable regimes — a BOT-BUNDLE (buys clumped into
1-2 slots, you are the designated exit liquidity) or ORGANIC (buys spread across slots). SWF reads the
cheap, $0, in-corpus fingerprint (slot-span + create-slot share of the first K buys) and asks whether the
bot-bundle end realizes WORSE net return under a fixed 10% trailing exit — i.e. whether it is a usable
pre-entry TOXICITY screen distinct from B20B (which is about unexitability, not dump-risk).

Three kill-checks in one pass, DEAD if any fails:
  1. VARIANCE  — the fingerprint is non-degenerate (not >95% one class).
  2. SIGNED SEPARATION — bundle-like launches realize significantly WORSE net-R than organic (permutation,
     both tails, to catch a sign-flip where bundle-like is actually MORE profitable).
  3. PAIRED LIFT — on a held-out half, screening OUT the bundle tail raises mean net-R vs not screening.

Reuses B20B's exact extraction; adds a bonding-curve price series from the paths DB. $0, no RPC.

    python scripts/swf_fingerprint_runner.py --bodies research/b11a/b11a_bodies.sqlite \
      --paths research/b11a/b11a_paths.sqlite --identity research/b11a/b11a_identity.sqlite \
      --out research/SWF_WINDOW1_DEV.json
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import math
import pathlib
import random
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B20B = _load("b20b_deadness_screen_runner", "b20b_deadness_screen_runner.py")
K_SLOTS = B20B.K_SLOTS
CONCENTRATION_THRESHOLD = B20B.CONCENTRATION_THRESHOLD

FINGERPRINT_K = 6          # first K buys define the fingerprint (invention: K=5-8)
TRAIL = 0.10               # 10% trailing exit (the invention's fixed exit)
TOLL = 0.03                # ~3% round-trip memecoin toll
BUNDLE_SLOT_SPAN = 2       # bundle-like = first-K buys occupy <= 2 distinct slots (fixed, no tuning)


def price_series(paths_db):
    """Bonding-curve marginal price per mint from the paths DB: virtual_quote / virtual_token, ordered by
    slot. Units cancel in the return ratio, so any consistent proxy is fine."""
    db = sqlite3.connect(f"file:{pathlib.Path(paths_db).resolve()}?mode=ro&immutable=1", uri=True)
    series = collections.defaultdict(list)
    for mint, slot, vq, vt in db.execute(
            "SELECT mint, slot, virtual_quote, virtual_token FROM observation "
            "ORDER BY slot, transaction_index, outer_index, inner_index"):
        if vt and vt > 0 and vq and vq > 0:
            series[mint].append((slot, vq / vt))
    db.close()
    return series


def _b20b_passes(window):
    """True iff this launch PASSES B20B (largest single wallet < 0.95 of net tokens bought) — the coins we
    would actually consider entering. Uses B20B's exact per-wallet rule."""
    held = collections.Counter()
    for _slot, user, is_buy, amount in window:
        held[user] += amount if is_buy else -amount
    total = sum(v for v in held.values() if v > 0)
    if total <= 0:
        return None
    top = max(held.values())
    return not (top * 100 >= total * CONCENTRATION_THRESHOLD)


def _fingerprint(window):
    """(slot_span, create_slot_share) of the first K buys. bundle-like => small slot_span, high share."""
    buys = sorted([e for e in window if e[2]], key=lambda e: e[0])[:FINGERPRINT_K]
    if len(buys) < FINGERPRINT_K:
        return None
    slots = [b[0] for b in buys]
    t0_slot = slots[0]
    return len(set(slots)), sum(1 for s in slots if s == t0_slot) / len(slots)


def _realized_net_r(series, entry_slot):
    """Enter at the first price at/after entry_slot, exit on a 10% trailing stop; net of toll."""
    fwd = [p for s, p in series if s >= entry_slot]
    if len(fwd) < 2 or fwd[0] <= 0:
        return None
    entry, peak, exit_p = fwd[0], fwd[0], fwd[-1]
    for p in fwd[1:]:
        peak = max(peak, p)
        if p <= peak * (1 - TRAIL):
            exit_p = p
            break
    return (exit_p / entry - 1.0) - TOLL


def score(trades, prices, t0_slots):
    rows, census = [], collections.Counter()
    for mint, events in trades.items():
        if mint not in t0_slots or mint not in prices:
            census["no_t0_or_price"] += 1
            continue
        t0 = t0_slots[mint]
        window = [e for e in sorted(events) if t0 <= e[0] <= t0 + K_SLOTS]
        passes = _b20b_passes(window)
        if passes is None:
            census["no_net_bought"] += 1
            continue
        if not passes:
            census["b20b_flagged_skip"] += 1        # we only trade B20B-PASS launches
            continue
        fp = _fingerprint(window)
        if fp is None:
            census["fewer_than_K_buys"] += 1
            continue
        slot_span, create_share = fp
        buys = sorted([e for e in window if e[2]], key=lambda e: e[0])[:FINGERPRINT_K]
        net_r = _realized_net_r(prices[mint], buys[-1][0])
        if net_r is None:
            census["no_forward_price"] += 1
            continue
        rows.append({"mint": mint, "slot_span": slot_span, "create_share": create_share,
                     "net_r": net_r, "bundle_like": slot_span <= BUNDLE_SLOT_SPAN})
        census["scored"] += 1
    return rows, census


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _perm_p(rows, seed=20260901, iters=2000):
    """Permutation p for 'bundle-like realizes worse net-R': shuffle the bundle labels, both tails."""
    bl = [r["net_r"] for r in rows if r["bundle_like"]]
    org = [r["net_r"] for r in rows if not r["bundle_like"]]
    if not bl or not org:
        return None
    obs = _mean(bl) - _mean(org)
    allr = [r["net_r"] for r in rows]
    nb = len(bl)
    rng = random.Random(seed)
    ge = 0
    for _ in range(iters):
        rng.shuffle(allr)
        diff = _mean(allr[:nb]) - _mean(allr[nb:])
        if abs(diff) >= abs(obs) - 1e-12:
            ge += 1
    return {"mean_bundle": _mean(bl), "mean_organic": _mean(org), "diff_bundle_minus_organic": obs,
            "permutation_p_two_tail": (ge + 1) / (iters + 1), "n_bundle": nb, "n_organic": len(org)}


def _paired_lift(rows):
    """Held-out half (hash split): does dropping bundle-like launches raise mean net-R vs keeping all?"""
    held = [r for r in rows if int(hashlib.sha256(r["mint"].encode()).hexdigest(), 16) & 1]
    if not held:
        return None
    keep_all = _mean([r["net_r"] for r in held])
    screened = _mean([r["net_r"] for r in held if not r["bundle_like"]])
    return {"n_holdout": len(held), "mean_net_r_all": keep_all, "mean_net_r_screened": screened,
            "lift": (screened - keep_all) if (screened is not None and keep_all is not None) else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bodies", required=True)
    parser.add_argument("--paths", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--out", default=str(ROOT / "research" / "SWF_WINDOW1_DEV.json"))
    args = parser.parse_args(argv)

    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    rows, census = score(B20B.trade_events(args.bodies, b9d), price_series(args.paths),
                         B20B.launch_slots(args.identity))

    n = len(rows)
    spans = collections.Counter(r["slot_span"] for r in rows)
    top_class_share = (max(spans.values()) / n) if n else 1.0
    sep = _perm_p(rows) if n else None
    lift = _paired_lift(rows) if n else None

    # frozen verdict
    if n < 50:
        verdict = "DEAD_TOO_FEW"
    elif top_class_share > 0.95:
        verdict = "DEAD_DEGENERATE_FINGERPRINT"
    elif not sep or sep["diff_bundle_minus_organic"] >= 0:
        verdict = "DEAD_WRONG_SIGN_OR_NO_SEP"     # bundle-like NOT worse (or better)
    elif sep["permutation_p_two_tail"] > 0.05:
        verdict = "DEAD_NOT_SIGNIFICANT"
    elif not lift or (lift["lift"] or -1) <= 0:
        verdict = "DEAD_NO_HOLDOUT_LIFT"
    else:
        verdict = "SURVIVES_WORTH_FORWARD"

    report = {
        "study": "SWF_SNIPER_WALL_FINGERPRINT_WINDOW1_DEV",
        "note": "DEV on burned window-1 — NOT frozen OOS. Universe = B20B-PASS launches only. Label = "
                "realized net-R under a 10% trailing exit (bonding-curve price), net of 3% toll.",
        "runner_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
        "params": {"fingerprint_k": FINGERPRINT_K, "trail": TRAIL, "toll": TOLL,
                   "bundle_slot_span_max": BUNDLE_SLOT_SPAN},
        "coverage": dict(census),
        "n_scored": n,
        "fingerprint_distribution_slot_span": dict(spans),
        "top_class_share": top_class_share,
        "signed_separation": sep,
        "held_out_paired_lift": lift,
        "verdict": verdict,
        "not_claimed": {"edge": "a toxicity screen at best avoids losses; it is not a return oracle.",
                        "oos": "window-1 is burned; a real verdict needs a frozen forward pass."},
    }
    pathlib.Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": args.out, "verdict": verdict, "n": n,
                      "signed_separation": sep, "lift": lift}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
