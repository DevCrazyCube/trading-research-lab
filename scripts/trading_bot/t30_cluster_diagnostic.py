#!/usr/bin/env python3
"""T30 CLUSTER DIAGNOSTIC -- a companion read of T30_BORROW_VERDICT.json.

Pre-registered and sha256-pinned 2026-09-07 00:00 CEST (CHUNK A), on clean day 14 of 30,
BEFORE any pair-level FEERATE or AVAILABLE figure has been read by anyone.  Everything this
file relies on comes from the FROZEN design cache (the 113-pair record), not from the forward
borrow panel.

WHY THIS EXISTS
---------------
The frozen T30 kill-condition counts PAIRS:

    after 30 clean days, if <10 of the 113 pairs have both legs borrowable at fee < that
    pair's measured gross edge, preferred-series RV is PERMANENTLY DEAD.

The 113 pairs are drawn from only 103 legs across 38 issuer roots, and they are all
within-issuer combinations, so the count is NOT a count of independent borrow decisions:

    PSA  21 pairs (7 series)      AHT 10      BAC 10      MS 10      BML 6      CIM 6
    ... 9 roots with 3 pairs, 23 roots with 1 pair.

A single issuer whose preferred ladder is easy to borrow therefore clears the >=10 threshold
by itself -- PSA alone supplies 21 of 113.  A "BORROW_WALL_PASSED" carried by one issuer is
one borrow decision, not ten, and is not evidence that the borrow wall is gone across the
strategy's cross-section.  This is the T60 defect shape (an i.i.d. count over a correlated
book = a scheduled fake pass) sitting on the gate that drives the ~09-22 pay-or-stop fork.

WHAT THIS FILE DOES AND DOES NOT DO
-----------------------------------
It does NOT move, soften or override the frozen rule.  t30_borrow_evaluate.py runs unchanged
and pin-verified on day 30 and its verdict stands as written; this script is a strictly
additive READ of the verdict it produces.  Changing the evaluator would break its pin and make
--evaluate refuse, which is the correct behaviour and is left intact.

PRE-COMMITTED INTERPRETATION RULE (frozen here, blind, 2026-09-07):

  * verdict PERMANENTLY_DEAD          -> unaffected.  Clustering can only INFLATE the alive
                                         count, never deflate it, so a death is a death.
  * BORROW_WALL_PASSED, alive pairs spanning >= 3 distinct issuer roots
                                      -> BROAD_PASS.  Report as the frozen rule reports it.
  * BORROW_WALL_PASSED, alive pairs spanning <= 2 distinct issuer roots
                                      -> CLUSTERED_PASS.  Reported to the owner as NOT
                                         fork-relevant survival: the frozen rule passed on
                                         <= 2 independent borrow decisions.

Three roots is chosen now, blind, as the smallest span at which the count is not dominated by
one issuer's series ladder plus a single companion; no forward number informed it.

Research only.  No network.  No orders.  Reads two files.  Never touches the t4 path.
"""
import collections
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RT = os.path.join(ROOT, "research", "trading_bot")
VERDICT = os.path.join(RT, "T30_BORROW_VERDICT.json")
EDGES = os.path.join(RT, "T30_B01_PAIR_EDGES.json")
OUT = os.path.join(RT, "T30_CLUSTER_DIAGNOSTIC.json")

MIN_ROOTS_FOR_BROAD_PASS = 3


def root_of(sym):
    return sym.split(".")[0]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record_structure():
    """Clustering of the 113-pair RECORD itself -- frozen design cache, no forward data."""
    e = json.load(open(EDGES))
    roots = collections.Counter(p["root"] for p in e["pairs"])
    legs = {p["ibkr_a"] for p in e["pairs"]} | {p["ibkr_b"] for p in e["pairs"]}
    top = sorted(roots.values(), reverse=True)
    s = k = 0
    for v in top:
        s += v
        k += 1
        if s >= 10:
            break
    return dict(n_pairs=e["n_pairs"], n_distinct_legs=len(legs), n_distinct_roots=len(roots),
                pairs_per_root=dict(roots.most_common()),
                min_roots_that_alone_clear_threshold=k)


def main():
    struct = record_structure()
    if not os.path.exists(VERDICT):
        print("T30 cluster diagnostic: no verdict yet (day-30 gate not reached).")
        print("record structure: %d pairs / %d legs / %d issuer roots; "
              "%d root(s) alone can clear the >=10 threshold"
              % (struct["n_pairs"], struct["n_distinct_legs"], struct["n_distinct_roots"],
                 struct["min_roots_that_alone_clear_threshold"]))
        json.dump(dict(state="PENDING_VERDICT", record_structure=struct), open(OUT, "w"),
                  indent=1, sort_keys=True)
        return 0

    v = json.load(open(VERDICT))
    alive = [p for p in v["pairs"] if p.get("alive")]
    borrowable = [p for p in v["pairs"] if p.get("borrowable")]
    alive_roots = sorted({root_of(p["a"]) for p in alive})
    alive_legs = sorted({p["a"] for p in alive} | {p["b"] for p in alive})
    per_root = collections.Counter(root_of(p["a"]) for p in alive)

    if v["verdict"] == "PERMANENTLY_DEAD":
        cluster_verdict = "DEAD_UNAFFECTED"
    elif len(alive_roots) >= MIN_ROOTS_FOR_BROAD_PASS:
        cluster_verdict = "BROAD_PASS"
    else:
        cluster_verdict = "CLUSTERED_PASS"

    out = dict(
        diagnostic_pinned="2026-09-07 (clean day 14 of 30, blind)",
        frozen_verdict=v["verdict"],
        n_alive_pairs=len(alive),
        n_alive_distinct_issuer_roots=len(alive_roots),
        n_alive_distinct_legs=len(alive_legs),
        alive_roots=alive_roots,
        alive_pairs_per_root=dict(per_root.most_common()),
        n_borrowable_pairs=len(borrowable),
        n_borrowable_distinct_issuer_roots=len(
            {root_of(p["a"]) for p in borrowable}),
        min_roots_for_broad_pass=MIN_ROOTS_FOR_BROAD_PASS,
        cluster_verdict=cluster_verdict,
        interpretation={
            "DEAD_UNAFFECTED": "Frozen rule killed it. Clustering can only inflate the alive "
                               "count, so the death stands.",
            "BROAD_PASS": "Frozen rule passed on >=3 independent issuers. Report as passed.",
            "CLUSTERED_PASS": "Frozen rule passed, but on <=2 independent borrow decisions. "
                              "NOT fork-relevant survival; report to owner as clustered.",
        }[cluster_verdict],
        record_structure=struct,
        verdict_sha256=sha256(VERDICT),
    )
    json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
    print("T30 frozen verdict: %s (%d/%d alive)" % (v["verdict"], len(alive), v["n_pairs"]))
    print("cluster diagnostic: alive pairs span %d issuer root(s) / %d legs -> %s"
          % (len(alive_roots), len(alive_legs), cluster_verdict))
    print(out["interpretation"])
    print("written %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
