#!/usr/bin/env python3
"""B20C — cluster-collapse exitability gate. A faithful extension of B20B (which it IMPORTS, never edits).

B20B flags a mint unexitable if, at t0+60 slots, the single largest INDIVIDUAL wallet holds >= 0.95 of
net tokens bought. A bundler defeats that trivially by SPLITTING the same supply across N coordinated
wallets — each holds total/N << 0.95, so a genuinely unexitable Sybil-split coin PASSES B20B clean.

B20C closes that hole with a pure-identity pre-step and ZERO price feature: collapse coordinated early
buyers into ONE synthetic entity BEFORE the concentration test, using a FIXED-BIN coordination key built
only from in-corpus fields (first-buy slot + a log-scale bin of the first-buy size — the Jito-bundle
signature: same slot, templated size). Then B20B's own rule/label/contrast run UNCHANGED on entities.
When the coordination key is the identity map, B20C == B20B exactly.

No tunables: the slot key is exact, the amount bin width is fixed. $0, no RPC — runs on the burned
window-1 corpus. The verdict is: among mints B20B PASSED, does collapsing coordinated wallets flag ones
that were actually unexitable (recall lift) WITHOUT degrading precision, and does the lift beat a
grouping permutation? If flat / wrong-signed / permutation-insignificant -> DEAD, B20B stands alone.

    python scripts/b20c_cluster_collapse_runner.py \
      --bodies research/b11a/b11a_bodies.sqlite --paths research/b11a/b11a_paths.sqlite \
      --identity research/b11a/b11a_identity.sqlite --out research/B20C_WINDOW1_DEV.json
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import math
import pathlib
import random
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
EXIT_RECOVERY_LAMPORTS = B20B.EXIT_RECOVERY_LAMPORTS
MIN_BUYERS_TO_SCORE = B20B.MIN_BUYERS_TO_SCORE

# ---------------------------------------------------------------- the fixed-bin coordination key
AMOUNT_BIN_DECIMALS = 1     # FIXED: log10 first-buy-size bucket width ~0.1 dex (~26% size bins). No tuning.


def coordination_key(window):
    """wallet -> synthetic entity id, from in-corpus fields only. The Jito/bundle signature is
    'bought in the same slot at a templated size', so the key is (first_buy_slot, log-bin of first-buy
    size). Wallets that share it collapse into one actor; everyone else stays a singleton. A wallet that
    only sold in the window keeps its own address as key (never merged)."""
    first_slot, first_amt = {}, {}
    for slot, user, is_buy, amount in window:
        if is_buy and user not in first_slot:
            first_slot[user] = slot
            first_amt[user] = amount
    key = {}
    seen = {e[1] for e in window}
    for user in seen:
        if user in first_slot and first_amt[user] > 0:
            key[user] = (first_slot[user], round(math.log10(first_amt[user]), AMOUNT_BIN_DECIMALS))
        else:
            key[user] = ("_nobuy_", user)     # sell-only wallet: never merged
    return key


def _flag(held):
    """B20B's exact rule on a holdings map (wallet OR entity). Returns (flagged, top_share_bps) or None."""
    total = sum(v for v in held.values() if v > 0)
    if total <= 0:
        return None
    top = max(held.values())
    return (top * 100 >= total * CONCENTRATION_THRESHOLD), (top * 10000) // total


def score_both(trades, reserve_series, t0_slots):
    """One pass, both rules on the identical population + label: wallet-level (== B20B) and
    entity-level (B20C). Keeps per-mint holdings so the grouping permutation can run later."""
    rows, census = [], collections.Counter()
    for mint, events in trades.items():
        if mint not in t0_slots:
            census["no_t0"] += 1
            continue
        if mint not in reserve_series:
            census["no_reserve_series"] += 1
            continue
        t0 = t0_slots[mint]
        events = sorted(events)
        window = [e for e in events if t0 <= e[0] <= t0 + K_SLOTS]
        buyers = {e[1] for e in window if e[2]}
        if len(buyers) < MIN_BUYERS_TO_SCORE:
            census["unreadable_fewer_than_2_buyers"] += 1
            continue
        series = reserve_series[mint]
        at_decision = [o for o in series if o[0] <= t0 + K_SLOTS]
        after = [o for o in series if o[0] > t0 + K_SLOTS]
        if not at_decision:
            census["no_state_at_decision"] += 1
            continue

        held = collections.Counter()
        for _slot, user, is_buy, amount in window:
            held[user] += amount if is_buy else -amount
        base = _flag(held)
        if base is None:
            census["no_net_tokens_bought"] += 1
            continue
        flagged_w, top_bps_w = base

        entity_key = coordination_key(window)
        held_e = collections.Counter()
        for user, net in held.items():
            held_e[entity_key[user]] += net
        collapsed = _flag(held_e)
        flagged_e, top_bps_e = collapsed if collapsed else (flagged_w, top_bps_w)

        best_external = max((o[1] for o in after), default=0)
        unexitable = best_external < EXIT_RECOVERY_LAMPORTS

        rows.append({
            "mint": mint, "unexitable": unexitable,
            "flagged_w": flagged_w, "top_share_bps_w": top_bps_w,
            "flagged_e": flagged_e, "top_share_bps_e": top_bps_e,
            "n_wallets": len(held), "n_entities": len(held_e),
            "held_net": [int(v) for v in held.values()],
            "entity_sizes": [int(v) for v in held_e.values()],
        })
        census["scored"] += 1
    return rows, census


def _as_flagged(rows, key):
    return [{"flagged": r[key], "unexitable": r["unexitable"], "top_share_bps": r[key.replace("flagged", "top_share_bps")]}
            for r in rows]


def permutation_pvalue(rows, iters=1000, seed=20260901):
    """Null: the recall gain from collapsing is just an artifact of having fewer buckets. Per mint, keep
    the ENTITY-SIZE structure but randomly repartition the wallet net-holdings into groups of those sizes,
    recompute the collapsed flag, and re-measure recall. p = fraction of permutations whose recall gain
    over B20B >= the observed gain. A real coordination signal beats random regrouping."""
    rng = random.Random(seed)
    base_b = B20B.contrast(_as_flagged(rows, "flagged_w"))
    base_c = B20B.contrast(_as_flagged(rows, "flagged_e"))
    obs_gain = (base_c["recall_pct"] or 0) - (base_b["recall_pct"] or 0)
    ge = 0
    for _ in range(iters):
        perm_rows = []
        for r in rows:
            nets = list(r["held_net"])
            rng.shuffle(nets)
            # regroup shuffled wallet nets into the observed NUMBER of entities (breaks the real
            # slot/size coordination while preserving how much merging happened)
            groups = _chunk_random(nets, len(r["entity_sizes"]), rng)
            held_e = collections.Counter()
            for gi, g in enumerate(groups):
                held_e[gi] = sum(g)
            fl = _flag(held_e)
            flagged_e = fl[0] if fl else r["flagged_w"]
            perm_rows.append({"flagged": flagged_e, "unexitable": r["unexitable"]})
        rec = B20B.contrast(perm_rows)["recall_pct"] or 0
        if (rec - (base_b["recall_pct"] or 0)) >= obs_gain - 1e-9:
            ge += 1
    return {"observed_recall_gain_pp": obs_gain, "permutation_p": (ge + 1) / (iters + 1), "iters": iters}


def _chunk_random(items, k, rng):
    """Randomly partition `items` into exactly k non-empty groups (k <= len(items)); else 1 group each."""
    n = len(items)
    if k >= n:
        return [[x] for x in items]
    if k <= 1:
        return [list(items)]
    cuts = sorted(rng.sample(range(1, n), k - 1))
    groups, prev = [], 0
    for c in cuts + [n]:
        groups.append(items[prev:c])
        prev = c
    return groups


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bodies", required=True)
    parser.add_argument("--paths", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--out", default=str(ROOT / "research" / "B20C_WINDOW1_DEV.json"))
    parser.add_argument("--perm-iters", type=int, default=1000)
    args = parser.parse_args(argv)

    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    rows, census = score_both(B20B.trade_events(args.bodies, b9d), B20B.reserves(args.paths),
                              B20B.launch_slots(args.identity))
    primary_b = B20B.contrast(_as_flagged(rows, "flagged_w"))
    primary_c = B20B.contrast(_as_flagged(rows, "flagged_e"))

    # the money metric: among mints B20B PASSED, what does B20C newly flag, and were they unexitable?
    newly = [r for r in rows if (not r["flagged_w"]) and r["flagged_e"]]
    newly_unexit = sum(1 for r in newly if r["unexitable"])
    merged = [r for r in rows if r["n_entities"] < r["n_wallets"]]

    delta = {
        "recall_gain_pp": (primary_c["recall_pct"] or 0) - (primary_b["recall_pct"] or 0),
        "precision_change_pp": (primary_c["precision_pct"] or 0) - (primary_b["precision_pct"] or 0),
        "lift_change_pp": (primary_c["lift_pp"] or 0) - (primary_b["lift_pp"] or 0),
        "newly_flagged_n": len(newly),
        "newly_flagged_unexitable_pct": (100 * newly_unexit / len(newly)) if newly else None,
        "mints_with_any_merge": len(merged),
        "base_rate_pct": primary_b["base_rate_pct"],
    }
    perm = permutation_pvalue(rows, iters=args.perm_iters) if newly else None

    # frozen verdict: B20C beats B20B only if it catches real rugs B20B missed, keeps precision, and the
    # gain is not a bucket-count artifact.
    if not newly or delta["recall_gain_pp"] <= 0:
        verdict = "DEAD_NO_LIFT"
    elif delta["precision_change_pp"] < -1.0:
        verdict = "DEAD_PRECISION_LOSS"
    elif perm and perm["permutation_p"] > 0.05:
        verdict = "DEAD_PERMUTATION_ARTIFACT"
    elif (delta["newly_flagged_unexitable_pct"] or 0) < (delta["base_rate_pct"] or 0):
        verdict = "DEAD_NEWLY_FLAGGED_NO_BETTER_THAN_BASE"
    else:
        verdict = "IMPROVES_B20B"

    report = {
        "study": "B20C_CLUSTER_COLLAPSE_WINDOW1_DEV",
        "note": "DEV on burned window-1 — NOT a frozen out-of-sample result. B20C == B20B when the "
                "coordination key is identity; this measures whether collapsing coordinated wallets adds lift.",
        "runner_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
        "coordination_key": {"first_buy_slot": "exact", "amount_bin_decimals": AMOUNT_BIN_DECIMALS,
                             "basis": "first-buy size (templated-bundle signature)"},
        "coverage": dict(census),
        "primary_b20b_wallet": primary_b,
        "primary_b20c_entity": primary_c,
        "delta": delta,
        "grouping_permutation": perm,
        "verdict": verdict,
        "not_claimed": {"edge": "this is a loss-avoidance screen; it creates no edge.",
                        "oos": "window-1 is burned; a real verdict needs the frozen window-2 pass."},
    }
    pathlib.Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": args.out, "verdict": verdict, "delta": delta,
                      "permutation": perm}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
