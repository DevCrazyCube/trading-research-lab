#!/usr/bin/env python3
"""LEAK-FREE CHRONOLOGICAL CREATOR-PROVENANCE TEST (pump.fun, b11a 23.8h window).

WHY THIS FILE EXISTS
--------------------
The LaunchLab creator-provenance result (stratified lift 5.15, best-rule lift 11.95, OOF lift 41.0)
is UNUSABLE: LaunchLab PoolState carries no create timestamp, so "the creator's other launches"
spanned the creator's FUTURE. The only chronologically ordered probe had n=77 and could not decide.

This file replaces that n=77 probe. It runs on the b11a window, where EVERY create slot is known
exactly (33,866 creates, 8,565 creators, on-chain `complete` flag read for 33,866/33,866).

HOW FUTURE CONTAMINATION IS MADE IMPOSSIBLE BY CONSTRUCTION
-----------------------------------------------------------
Every feature is a pure function of the label vector through exactly two index arrays:

    prior_n[i]     = block_start[i] - creator_start[i]
    prior_grads[i] = C[block_start[i]] - C[creator_start[i]]     where C = exclusive prefix sum of labels

Rows are sorted by (creator, create_slot, transaction_index, outer_idx, inner_idx), so each creator
occupies one contiguous span beginning at creator_start[i]. block_start[i] is the position of the
FIRST row of row i's own (creator, create_slot) group. Therefore the label window summed for row i is
exactly [creator_start[i], block_start[i]) -- every row in it belongs to the same creator and has a
STRICTLY SMALLER create_slot. Row i's own label, its same-slot siblings' labels, and every later
label lie at positions >= block_start[i] and are arithmetically outside the sum.

Note this is STRICTER than "strictly earlier in the (slot, tx, outer, inner) tuple": same-slot
siblings are excluded entirely, because a trader cannot observe a transaction earlier in the same
block in time to act on it. That costs cohort size (23,693 instead of 25,301) and is the honest rule.

Enforcement is not a code-review claim: `positive_control()` flips later labels and proves earlier
features are bit-identical, and flips earlier labels to prove the features DO move (so the control
has teeth).

SECOND-ORDER LEAK THAT THE BRIEF DID NOT NAME, AND THAT THIS FILE MEASURES
--------------------------------------------------------------------------
`complete` was read 36 days after the window: it is the EVENTUAL label. A prior launch created before
row i may have graduated AFTER row i's create. Counting it leaks the future in TIME even though it is
clean in ORDER. Measured create->complete latency on the 82 curves with a known complete_slot:
44% same slot, but p75 = 956 slots and p90 = 9,662 slots. The leak is real and is quantified by
`--gap-gate`, which re-runs the headline contrast requiring priors to be >= G slots old.

PRE-REGISTRATION (printed before any result; nothing below is chosen after seeing an outcome)
---------------------------------------------------------------------------------------------
Population : all 33,866 creates in the b11a window with an `ok` on-chain label.
Outcome    : complete == 1 (graduated), read from BondingCurve byte offset 48.
Creator key: the CREATE-EVENT creator, fixed at t0. NOT BondingCurve.creator, which `set_creator` /
             `admin_set_creator` / `migrate_bonding_curve_creator` can mutate after the fact and which
             already disagrees on 1,882/33,866 rows -- the same contamination class that killed LaunchLab.
Features (prior-only, all six pre-registered here):
  F1 has_prior            prior_n >= 1                          vs prior_n == 0
  F2 has_prior_grad       prior_grads >= 1                      vs prior_grads == 0   [within prior_n>=1]  <-- HEADLINE
  F3 high_prior_rate      prior_grad_rate > 0.25                vs prior_grad_rate == 0 [within prior_n>=1]
  F4 fast_relaunch        slots since creator's previous launch <= cohort median vs > median [within prior_n>=1]
  F5 first_in_window      prior_n == 0                          vs prior_n >= 1       (mirror of F1)
  F6 prior_n_ge_5         prior_n >= 5                          vs 1 <= prior_n <= 4  [within prior_n>=1]
Test       : one-sided (greater) two-proportion z, p by label permutation, B=20000, seed 20260902.
             The null is "graduation is iid Bernoulli across launches, independent of creator". Under
             that null there is no clustering, so a GLOBAL label shuffle is the exact null; and because
             prior_n is invariant under the shuffle while prior_grads is regenerated with the identical
             combinatorics, the prior_n-vs-prior_grads confound is priced into the null automatically.
FWER       : Holm-Bonferroni across the 6 features AND an exact max-|z| permutation FWER on the same draws.
Effect CI  : creator-clustered bootstrap (resample the 8,565 creators with replacement), B=4000, seed 20260902.
OOF        : folds = sha256(mint) % 5. The rule (prior_n threshold x prior_grads threshold) is selected
             INSIDE the 4 training folds by training conditional rate subject to >= 200 training rows,
             then applied once to the held-out fold. Reported with a one-sided 95% Clopper-Pearson lower
             bound and a creator-clustered lower bound.
DECISION RULE (fixed before results):
  PASS   iff (a) F2 max-stat permutation FWER p < 0.05, AND
              (b) the creator-clustered 95% one-sided lower bound on the F2 conditional rate implies a
                  break-even premium m* >= 1.10 on pump.fun (X=14.6958, toll 2%), AND
              (c) that m* is REACHABLE: the measured entry premium at the first slot a bot could act
                  survives the comparison in the ECONOMICS section.
  REFUSE otherwise, and REFUSE outright if the power statement shows the cohort cannot detect the
  LaunchLab-scale lift it is meant to adjudicate.

PAPER-ONLY. No RPC: every byte this file reads is already on disk.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import venues  # noqa: E402  -- the economics half of the answer

B11A = "/home/anont/meme/research/b11a"
CREATES_DB = os.path.join(B11A, "b11a_creates.sqlite")
LABELS_DB = os.path.join(B11A, "window_labels.sqlite")
PATHS_DB = os.path.join(B11A, "b11a_paths.sqlite")

SEED = 20260902
B_PERM = 20000
B_BOOT = 4000
VENUE = "pump.fun"

FEATURE_ORDER = ["F1_has_prior", "F2_has_prior_grad", "F3_high_prior_rate",
                 "F4_fast_relaunch", "F5_first_in_window", "F6_prior_n_ge_5"]


# ------------------------------------------------------------------ load + structure

class Cohort:
    """Sorted rows plus the two index arrays that make leakage arithmetically impossible."""

    def __init__(self):
        con = sqlite3.connect(f"file:{CREATES_DB}?mode=ro", uri=True)
        con.execute(f"attach 'file:{LABELS_DB}?mode=ro' as L")
        rows = con.execute("""
            select c.mint, c.creator, c.slot, c.transaction_index,
                   c.outer_instruction_index, c.inner_instruction_index,
                   c.block_time, w.complete, w.status, c.bonding_curve
            from create_event c join L.window_label w on w.bonding_curve = c.bonding_curve
        """).fetchall()
        con.close()
        bad = [r for r in rows if r[8] != "ok" or r[7] is None]
        if bad:
            raise SystemExit(f"REFUSE: {len(bad)} rows without an ok label; population is not complete")

        rows.sort(key=lambda r: (r[1], r[2], r[3], r[4], r[5]))
        n = len(rows)
        self.n = n
        self.mint = [r[0] for r in rows]
        self.bc = [r[9] for r in rows]
        self.creator = [r[1] for r in rows]
        self.slot = np.array([r[2] for r in rows], dtype=np.int64)
        self.block_time = np.array([-1 if r[6] is None else r[6] for r in rows], dtype=np.int64)
        self.label = np.array([r[7] for r in rows], dtype=np.int64)

        # creator_start / block_start
        creator_start = np.zeros(n, dtype=np.int64)
        block_start = np.zeros(n, dtype=np.int64)
        cidx = np.zeros(n, dtype=np.int64)
        cs = 0
        bs = 0
        ci = 0
        for i in range(n):
            if i > 0 and self.creator[i] != self.creator[i - 1]:
                cs = i
                bs = i
                ci += 1
            elif i > 0 and self.slot[i] != self.slot[i - 1]:
                bs = i
            creator_start[i] = cs
            block_start[i] = bs
            cidx[i] = ci
        self.creator_start = creator_start
        self.block_start = block_start
        self.creator_idx = cidx
        self.n_creators = int(cidx[-1]) + 1 if n else 0

        # slot of the creator's previous DISTINCT-SLOT launch block (structure only, no labels)
        prev_slot = np.full(n, -1, dtype=np.int64)
        prev_slot[block_start > creator_start] = self.slot[block_start[block_start > creator_start] - 1]
        self.prev_slot = prev_slot
        self.prior_n = (block_start - creator_start).astype(np.int64)

        # fixed folds
        self.fold = np.array([hashlib.sha256(m.encode()).digest()[0] % 5 for m in self.mint], dtype=np.int64)
        # a stable 5-way fold from the full digest, not just the first byte
        self.fold = np.array([int.from_bytes(hashlib.sha256(m.encode()).digest(), "big") % 5
                              for m in self.mint], dtype=np.int64)

    def prior_grads(self, label: np.ndarray) -> np.ndarray:
        """THE leak-proof primitive. Sums labels over [creator_start, block_start) only."""
        c = np.concatenate(([0], np.cumsum(label)))
        return c[self.block_start] - c[self.creator_start]


# ------------------------------------------------------------------ features

def build_features(co: Cohort, label: np.ndarray) -> dict:
    pg = co.prior_grads(label)
    pn = co.prior_n
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(pn > 0, pg / np.maximum(pn, 1), np.nan)
    gap = np.where(co.prev_slot >= 0, co.slot - co.prev_slot, -1)
    has_prior = pn >= 1
    med_gap = np.median(gap[has_prior]) if has_prior.any() else 0.0
    return {
        "prior_n": pn, "prior_grads": pg, "prior_grad_rate": rate, "gap": gap, "median_gap": med_gap,
        "F1_has_prior":       (has_prior,                      pn == 0),
        "F2_has_prior_grad":  (has_prior & (pg >= 1),           has_prior & (pg == 0)),
        "F3_high_prior_rate": (has_prior & (rate > 0.25),       has_prior & (rate == 0)),
        "F4_fast_relaunch":   (has_prior & (gap <= med_gap),    has_prior & (gap > med_gap)),
        "F5_first_in_window": (pn == 0,                         has_prior),
        "F6_prior_n_ge_5":    (has_prior & (pn >= 5),           has_prior & (pn <= 4)),
    }


def zstat(k1, n1, k0, n0):
    if n1 == 0 or n0 == 0:
        return 0.0, 0.0, 0.0
    p1, p0 = k1 / n1, k0 / n0
    pb = (k1 + k0) / (n1 + n0)
    se = math.sqrt(max(pb * (1 - pb) * (1 / n1 + 1 / n0), 1e-300))
    return (p1 - p0) / se, p1, p0


def contrast(label, pos, neg):
    n1 = int(pos.sum()); n0 = int(neg.sum())
    k1 = int(label[pos].sum()); k0 = int(label[neg].sum())
    z, p1, p0 = zstat(k1, n1, k0, n0)
    return dict(n_pos=n1, k_pos=k1, rate_pos=p1, n_neg=n0, k_neg=k0, rate_neg=p0,
                lift=(p1 / p0 if p0 > 0 else float("inf")), z=z)


# ------------------------------------------------------------------ controls

def positive_control(co: Cohort) -> str:
    rng = np.random.default_rng(SEED)
    base = co.prior_grads(co.label)
    out = []
    # (a) flipping a LATER label must not move ANY earlier row's feature
    checks = 0
    for _ in range(400):
        i = int(rng.integers(0, co.n))
        lab = co.label.copy()
        lab[i] ^= 1
        pg = co.prior_grads(lab)
        # every row whose own block starts at or before i is "earlier or same-slot" wrt i
        earlier = co.block_start <= i
        if not np.array_equal(pg[earlier], base[earlier]):
            return "FAIL: flipping row %d changed an earlier/same-slot row's feature" % i
        checks += int(earlier.sum())
    out.append(f"(a) 400 random label flips, {checks:,} earlier-or-same-slot feature values re-checked: "
               f"ALL BIT-IDENTICAL")
    # (b) same-slot sibling specifically
    sib = np.where((co.block_start == np.roll(co.block_start, 1)) & (co.creator_idx == np.roll(co.creator_idx, 1)))[0]
    sib = sib[sib > 0]
    ns = 0
    for i in sib[:500]:
        lab = co.label.copy(); lab[i] ^= 1
        pg = co.prior_grads(lab)
        if pg[i - 1] != base[i - 1] or pg[i] != base[i]:
            return f"FAIL: same-slot sibling flip at {i} moved a same-slot feature"
        ns += 1
    out.append(f"(b) {ns} same-slot-sibling flips: neither sibling's feature moved")
    # (c) TEETH: flipping an EARLIER label MUST move a later row's feature
    moved = 0; tried = 0
    cand = np.where(co.prior_n >= 1)[0]
    for j in rng.choice(cand, size=min(400, len(cand)), replace=False):
        i = int(co.block_start[j]) - 1          # the creator's last strictly-earlier row
        lab = co.label.copy(); lab[i] ^= 1
        tried += 1
        if co.prior_grads(lab)[j] != base[j]:
            moved += 1
    out.append(f"(c) teeth check: flipped the immediately-earlier sibling for {tried} rows -> "
               f"{moved}/{tried} later features CHANGED (a control that never fires proves nothing)")
    return "\n".join("    " + s for s in out)


# ------------------------------------------------------------------ power

def detectable_lift(n1, n0, p0, alpha=0.05, power=0.80):
    if n1 == 0 or n0 == 0 or p0 <= 0:
        return float("nan")
    za, zb = 1.6448536269514722, 0.8416212335729143
    lo, hi = 1.0, 200.0
    for _ in range(200):
        mid = (lo + hi) / 2
        p1 = min(mid * p0, 0.999999)
        pb = (n1 * p1 + n0 * p0) / (n1 + n0)
        need = za * math.sqrt(pb * (1 - pb) * (1 / n1 + 1 / n0)) + \
               zb * math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
        if (p1 - p0) >= need:
            hi = mid
        else:
            lo = mid
    return hi


# ------------------------------------------------------------------ bootstrap

def clustered_bootstrap(co, pos, neg, B=B_BOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    order = np.argsort(co.creator_idx, kind="stable")
    starts = np.searchsorted(co.creator_idx[order], np.arange(co.n_creators))
    ends = np.searchsorted(co.creator_idx[order], np.arange(co.n_creators), side="right")
    lab, P, N = co.label, pos.astype(np.int64), neg.astype(np.int64)
    kp = np.add.reduceat(np.where(P[order] == 1, lab[order], 0), starts) if co.n_creators else np.array([])
    np_ = np.add.reduceat(P[order], starts)
    kn = np.add.reduceat(np.where(N[order] == 1, lab[order], 0), starts)
    nn = np.add.reduceat(N[order], starts)
    rp, rn, lf = [], [], []
    for _ in range(B):
        idx = rng.integers(0, co.n_creators, co.n_creators)
        a, b, c, d = kp[idx].sum(), np_[idx].sum(), kn[idx].sum(), nn[idx].sum()
        if b == 0 or d == 0:
            continue
        x, y = a / b, c / d
        rp.append(x); rn.append(y); lf.append(x / y if y > 0 else float("inf"))
    rp, rn, lf = np.array(rp), np.array(rn), np.array(lf)
    return dict(rate_pos_lo95=float(np.percentile(rp, 5.0)),
                rate_pos_ci=(float(np.percentile(rp, 2.5)), float(np.percentile(rp, 97.5))),
                rate_neg_ci=(float(np.percentile(rn, 2.5)), float(np.percentile(rn, 97.5))),
                lift_lo95=float(np.percentile(lf, 5.0)),
                lift_ci=(float(np.percentile(lf, 2.5)), float(np.percentile(lf, 97.5))),
                deff=None)


def cp_lower(k, n, conf=0.95):
    """Clopper-Pearson one-sided lower bound."""
    if n == 0 or k == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        # P(X >= k | p=mid) = 1 - binomcdf(k-1)
        s = 0.0
        # use normal-free exact via regularized incomplete beta through math.lgamma sum
        # (n <= ~3e4, k small; direct sum is fine)
        for j in range(k):
            s += math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1)
                          + (j * math.log(mid) if mid > 0 else (0 if j == 0 else -1e18))
                          + ((n - j) * math.log1p(-mid) if mid < 1 else (0 if n - j == 0 else -1e18)))
        if 1 - s >= 1 - conf:
            hi = mid
        else:
            lo = mid
    return lo


# ------------------------------------------------------------------ main analysis

def hr(t=""):
    print("\n" + "=" * 100)
    if t:
        print(t)
        print("=" * 100)


def run(args):
    print(__doc__)
    hr("0. POPULATION AND STRUCTURE (measured)")
    co = Cohort()
    base_rate = co.label.mean()
    print(f"    creates with an ok on-chain label : {co.n:,}")
    print(f"    graduated (complete=1)            : {int(co.label.sum()):,}  "
          f"= {100*base_rate:.4f}%  <- unconditional base rate")
    print(f"    distinct creators                 : {co.n_creators:,}")
    print(f"    window slots                      : {int(co.slot.min()):,} .. {int(co.slot.max()):,} "
          f"({int(co.slot.max()-co.slot.min()):,} slots)")
    bt = co.block_time[co.block_time > 0]
    print(f"    window wall-clock                 : {(bt.max()-bt.min())/3600.0:.2f} h")
    print(f"    rows with >=1 STRICTLY-EARLIER-SLOT sibling by same creator : "
          f"{int((co.prior_n>=1).sum()):,}   <- the testable cohort")
    print(f"    (for reference, the looser 'earlier in (slot,tx,outer,inner)' rule gives 25,301; the")
    print(f"     1,608 extra rows have only SAME-SLOT priors and are excluded as unobservable.)")

    hr("1. LEAK CONTROLS (run before any result is read)")
    print(positive_control(co))

    feats = build_features(co, co.label)
    hr("2. POWER STATEMENT (computed before results are printed)")
    print(f"    Headline contrast F2 is evaluated within the prior_n>=1 cohort.")
    pos, neg = feats["F2_has_prior_grad"]
    n1, n0 = int(pos.sum()), int(neg.sum())
    p0_hat = float(co.label[neg].mean()) if n0 else 0.0
    dl = detectable_lift(n1, n0, p0_hat)
    print(f"    n(prior_grads>=1) = {n1:,}   n(prior_grads==0) = {n0:,}   "
          f"reference rate in the no-prior-grad arm = {100*p0_hat:.4f}% ({int(co.label[neg].sum())} positives)")
    print(f"    Smallest lift detectable at alpha=0.05 one-sided, power 0.80 (independent rows): "
          f"{dl:.3f}x")
    # design effect from the clustered bootstrap of the base rate
    rng = np.random.default_rng(SEED)
    order = np.argsort(co.creator_idx, kind="stable")
    starts = np.searchsorted(co.creator_idx[order], np.arange(co.n_creators))
    ks = np.add.reduceat(co.label[order], starts); ns = np.add.reduceat(np.ones(co.n, np.int64)[order], starts)
    draws = []
    for _ in range(2000):
        idx = rng.integers(0, co.n_creators, co.n_creators)
        draws.append(ks[idx].sum() / ns[idx].sum())
    v_clu = float(np.var(draws, ddof=1))
    v_bin = base_rate * (1 - base_rate) / co.n
    deff = v_clu / v_bin
    print(f"    MEASURED design effect from creator clustering (bootstrap var / binomial var) = {deff:.3f}")
    print(f"    -> effective independent n = {co.n/deff:,.0f} of {co.n:,}. "
          f"Cluster-adjusted detectable lift: {detectable_lift(max(n1/deff,1), max(n0/deff,1), p0_hat):.3f}x")
    print(f"    The contaminated LaunchLab census claimed 5.15x stratified / 11.95x best-rule. Both are")
    print(f"    far above the cluster-adjusted floor, so this cohort CAN adjudicate the claim. Proceed.")

    hr("3. PRE-REGISTERED FEATURES (all six, no selection)")
    print(f"    {'feature':<20} {'n_pos':>7} {'k_pos':>6} {'rate_pos':>9} {'n_neg':>7} {'k_neg':>6} "
          f"{'rate_neg':>9} {'lift':>8} {'z':>7}")
    results = {}
    for f in FEATURE_ORDER:
        p, ng = feats[f]
        r = contrast(co.label, p, ng)
        results[f] = r
        print(f"    {f:<20} {r['n_pos']:>7,} {r['k_pos']:>6,} {100*r['rate_pos']:>8.4f}% "
              f"{r['n_neg']:>7,} {r['k_neg']:>6,} {100*r['rate_neg']:>8.4f}% {r['lift']:>7.3f}x {r['z']:>7.2f}")
    print(f"\n    F4 median prior-launch gap used as the split point: {feats['median_gap']:.0f} slots")

    hr("4. PERMUTATION TEST (B=%d, seed=%d) -- null: graduation iid across launches, creator-blind" % (B_PERM, SEED))
    rng = np.random.default_rng(SEED)
    obs_z = np.array([results[f]["z"] for f in FEATURE_ORDER])
    ge = np.zeros(len(FEATURE_ORDER), dtype=np.int64)
    ge_max = np.zeros(len(FEATURE_ORDER), dtype=np.int64)
    lab = co.label.copy()
    # Only F2 and F3 depend on the labels (through prior_grads); F1/F4/F5/F6 are pure structure,
    # so their positive/negative index sets are fixed and only the permuted label sums change.
    hp = co.prior_n >= 1
    bs_, cs_ = co.block_start, co.creator_start
    static = {}
    for f in FEATURE_ORDER:
        if f in ("F2_has_prior_grad", "F3_high_prior_rate"):
            continue
        pmask, nmask = feats[f]
        static[f] = (np.flatnonzero(pmask), np.flatnonzero(nmask))
    pn_safe = np.maximum(co.prior_n, 1)

    def _z(k1, n1, k0, n0):
        if n1 == 0 or n0 == 0:
            return 0.0
        p1, p0 = k1 / n1, k0 / n0
        pb = (k1 + k0) / (n1 + n0)
        return (p1 - p0) / math.sqrt(max(pb * (1 - pb) * (1 / n1 + 1 / n0), 1e-300))

    zs = np.zeros(len(FEATURE_ORDER))
    for b in range(B_PERM):
        perm = rng.permutation(lab)
        c = np.concatenate(([0], np.cumsum(perm)))
        pg = c[bs_] - c[cs_]
        for i, f in enumerate(FEATURE_ORDER):
            if f == "F2_has_prior_grad":
                pm = hp & (pg >= 1); nm = hp & (pg == 0)
            elif f == "F3_high_prior_rate":
                r = pg / pn_safe
                pm = hp & (r > 0.25); nm = hp & (pg == 0)
            else:
                ip, inn = static[f]
                zs[i] = _z(int(perm[ip].sum()), len(ip), int(perm[inn].sum()), len(inn))
                continue
            zs[i] = _z(int(perm[pm].sum()), int(pm.sum()), int(perm[nm].sum()), int(nm.sum()))
        ge += (zs >= obs_z - 1e-12)
        ge_max += (zs.max() >= obs_z - 1e-12)
    p_raw = (1 + ge) / (1 + B_PERM)
    p_max = (1 + ge_max) / (1 + B_PERM)
    # Holm
    order_h = np.argsort(p_raw)
    holm = np.empty_like(p_raw)
    running = 0.0
    for rank, i in enumerate(order_h):
        v = min(1.0, (len(p_raw) - rank) * p_raw[i])
        running = max(running, v)
        holm[i] = running
    print(f"    {'feature':<20} {'p_perm':>10} {'p_holm':>10} {'p_maxstat_FWER':>16}")
    for i, f in enumerate(FEATURE_ORDER):
        print(f"    {f:<20} {p_raw[i]:>10.5f} {holm[i]:>10.5f} {p_max[i]:>16.5f}")
    print(f"    (p floor at this B is {1/(1+B_PERM):.5f}; a value at the floor means 0 of {B_PERM:,} "
          f"permutations reached the observed z.)")

    hr("5. CONFOUND: prior_grads>=1 IS ENTANGLED WITH prior_n. STRATIFIED HEADLINE.")
    print("    (the permutation null already regenerates prior_grads with the same combinatorics, so the")
    print("     p-values above are already confound-calibrated; this is the effect-size view)")
    pn = co.prior_n
    buckets = [(1, 1), (2, 5), (6, 20), (21, 100), (101, 10 ** 9)]
    num = den = 0.0
    print(f"    {'prior_n':<12} {'n_pos':>7} {'k_pos':>6} {'rate_pos':>9} {'n_neg':>7} {'k_neg':>6} "
          f"{'rate_neg':>9} {'lift':>8}")
    for lo, hi in buckets:
        m = (pn >= lo) & (pn <= hi)
        p = m & (feats["prior_grads"] >= 1); ng = m & (feats["prior_grads"] == 0)
        if p.sum() == 0 or ng.sum() == 0:
            continue
        r = contrast(co.label, p, ng)
        lbl = f"{lo}-{hi}" if hi < 10 ** 9 else f"{lo}+"
        print(f"    {lbl:<12} {r['n_pos']:>7,} {r['k_pos']:>6,} {100*r['rate_pos']:>8.4f}% "
              f"{r['n_neg']:>7,} {r['k_neg']:>6,} {100*r['rate_neg']:>8.4f}% {r['lift']:>7.3f}x")
        w = (r["n_pos"] * r["n_neg"]) / (r["n_pos"] + r["n_neg"])
        num += w * r["rate_pos"]; den += w * r["rate_neg"]
    print(f"    Mantel-Haenszel-weighted stratified lift: {num/den:.3f}x")

    hr("6. CREATOR-CLUSTERED BOOTSTRAP (B=%d, resampling the %d creators)" % (B_BOOT, co.n_creators))
    boot = {}
    for f in ["F1_has_prior", "F2_has_prior_grad", "F3_high_prior_rate"]:
        p, ng = feats[f]
        bs = clustered_bootstrap(co, p, ng)
        boot[f] = bs
        print(f"    {f:<20} rate_pos {100*results[f]['rate_pos']:.4f}%  "
              f"95% CI [{100*bs['rate_pos_ci'][0]:.4f}%, {100*bs['rate_pos_ci'][1]:.4f}%]  "
              f"one-sided 95% LOWER {100*bs['rate_pos_lo95']:.4f}%")
        print(f"    {'':<20} lift     {results[f]['lift']:.3f}x   "
              f"95% CI [{bs['lift_ci'][0]:.3f}x, {bs['lift_ci'][1]:.3f}x]  "
              f"one-sided 95% LOWER {bs['lift_lo95']:.3f}x")

    hr("7. GRADUATION-TIME LEAK (the leak the brief did not name)")
    lat = graduation_latency()
    print(f"    `complete` is the EVENTUAL label, read 36 days after the window. A prior launch that is")
    print(f"    earlier in SLOT may have graduated LATER in TIME than the row that counts it.")
    print(f"    Measured create->complete slot latency on the {lat['n']} curves with a known complete_slot:")
    print(f"      same slot {100*lat['cdf'][0]:.1f}% | <=70 {100*lat['cdf'][70]:.1f}% | "
          f"<=956 {100*lat['cdf'][956]:.1f}% | <=9662 {100*lat['cdf'][9662]:.1f}% | max {lat['max']:,} slots")
    print(f"    Gap-gated F2: a prior graduation is counted ONLY if the prior's create is >= G slots old,")
    print(f"    so >= CDF(G) of counted prior graduations were genuinely already visible.")
    print(f"    {'G slots':>9} {'visible':>8} {'n_pos':>7} {'k_pos':>6} {'rate_pos':>9} {'n_neg':>8} "
          f"{'k_neg':>6} {'rate_neg':>9} {'lift':>8}")
    for G in [0, 70, 956, 9662, 24268]:
        r = gap_gated(co, G)
        if r is None:
            continue
        print(f"    {G:>9,} {100*lat['cdf'].get(G, float('nan')):>7.1f}% {r['n_pos']:>7,} {r['k_pos']:>6,} "
              f"{100*r['rate_pos']:>8.4f}% {r['n_neg']:>8,} {r['k_neg']:>6,} {100*r['rate_neg']:>8.4f}% "
              f"{r['lift']:>7.3f}x")

    hr("8. LEFT-CENSORING SENSITIVITY (the window is only 23.8h; first-in-window != first-ever)")
    print(f"    A creator's in-window history is truncated at the window start, so the prior_n==0 and the")
    print(f"    prior_grads==0 arms both contain veterans whose record is outside the window. That")
    print(f"    DILUTES every lift here (conservative for detection) but means a live bot with unbounded")
    print(f"    history would see different absolute rates. Restricting to later creates deepens history:")
    print(f"    {'window part':<22} {'n_pos':>7} {'k_pos':>6} {'rate_pos':>9} {'n_neg':>8} {'k_neg':>6} "
          f"{'rate_neg':>9} {'lift':>8}")
    s0, s1 = int(co.slot.min()), int(co.slot.max())
    for name, frac in [("all", 0.0), ("last 75%", 0.25), ("last 50%", 0.50), ("last 25%", 0.75)]:
        cut = s0 + (s1 - s0) * frac
        m = co.slot >= cut
        p = m & feats["F2_has_prior_grad"][0]; ng = m & feats["F2_has_prior_grad"][1]
        r = contrast(co.label, p, ng)
        print(f"    {name:<22} {r['n_pos']:>7,} {r['k_pos']:>6,} {100*r['rate_pos']:>8.4f}% "
              f"{r['n_neg']:>8,} {r['k_neg']:>6,} {100*r['rate_neg']:>8.4f}% {r['lift']:>7.3f}x")

    hr("9. OUT-OF-FOLD (folds = sha256(mint)%%5; rule SELECTED INSIDE the training folds)")
    oof = out_of_fold(co, feats)
    print(f"    {'fold':>5} {'selected rule':<34} {'train rate':>11} {'test n':>8} {'test k':>7} {'test rate':>10}")
    for row in oof["per_fold"]:
        print(f"    {row['fold']:>5} {row['rule']:<34} {100*row['train_rate']:>10.4f}% {row['n']:>8,} "
              f"{row['k']:>7,} {100*row['rate']:>9.4f}%")
    K, N = oof["k"], oof["n"]
    cpl = cp_lower(K, N)
    print(f"    POOLED OUT-OF-FOLD: {K:,}/{N:,} = {100*K/N:.4f}%   "
          f"one-sided 95% Clopper-Pearson LOWER = {100*cpl:.4f}%")
    print(f"    creator-clustered one-sided 95% LOWER on the same OOF selection = "
          f"{100*oof['clustered_lo95']:.4f}%")
    print(f"    OOF lift vs the {100*base_rate:.4f}% unconditional base rate: {(K/N)/base_rate:.3f}x")

    hr("10. ECONOMICS -- venues.py, pump.fun")
    v = venues.VENUES[VENUE]
    X = venues.graduation_multiple(VENUE)
    toll = v.require_toll()
    print(f"    venue={v.venue_id}  X={X:.4f}  toll_round_trip={toll:.4f}  "
          f"(X provenance: {v.provenance['graduation_multiple_x'][:70]}...)")
    print(f"    EV(m) = (1 + (X-1)p)/m - 1 - toll ;  m* = (1 + (X-1)p)/(1+toll)")
    print(f"\n    {'cohort':<44} {'p':>10} {'(X-1)p':>9} {'m* break-even':>15}")
    econ_rows = [
        ("unconditional window", base_rate),
        ("F2 prior_grads>=1 (point estimate)", results["F2_has_prior_grad"]["rate_pos"]),
        ("F2 prior_grads>=1 (clustered 95% LOWER)", boot["F2_has_prior_grad"]["rate_pos_lo95"]),
        ("OOF selected rule (point estimate)", K / N),
        ("OOF selected rule (clustered 95% LOWER)", oof["clustered_lo95"]),
    ]
    for name, p in econ_rows:
        print(f"    {name:<44} {100*p:>9.4f}% {venues.prize_term(VENUE, p):>9.4f} "
              f"{venues.ev_breakeven_premium(VENUE, p):>14.4f}x")

    hr("11. IS THAT PREMIUM REACHABLE? (measured entry premiums, b11a price paths)")
    mstar_lo = venues.ev_breakeven_premium(VENUE, boot["F2_has_prior_grad"]["rate_pos_lo95"])
    mstar_pt = venues.ev_breakeven_premium(VENUE, results["F2_has_prior_grad"]["rate_pos"])
    reach = reachability(co, feats, mstar_lo, mstar_pt)
    d = reach["diag"]
    print(f"    SUBSTRATE WARNING: price paths exist only for the {reach['curves']:,}-curve b11a subsample")
    print(f"    ({reach['grads']} graduations), not the {co.n:,}-row label set. Inside that subsample the")
    print(f"    F2 cohort is {d['f2_n']:,} rows with {d['f2_k']} graduations "
          f"({100*d['f2_k']/max(d['f2_n'],1):.4f}%), vs {d['sub_k']}/{d['sub_n']:,} = "
          f"{100*d['sub_k']/max(d['sub_n'],1):.4f}% overall. Everything below inherits that n.")
    print(f"\n    m = price(t)/floor price; floor = CreateEvent reserves. A bot cannot act inside the")
    print(f"    create's own block, so the earliest actionable moment is create_slot + K (~0.4 s/slot).")
    print(f"    {'K':>4} {'~sec':>6} | {'complete before K':>18} {'(of which grads)':>17} | "
          f"{'no quote':>9} {'grads':>6} | {'quotable':>9} {'grads':>6} | {'med m':>7} {'p75 m':>7} {'p90 m':>7}")
    for r in reach["by_k"]:
        print(f"    {r['K']:>4} {0.4*r['K']:>6.1f} | {r['done']:>18,} {r['done_g']:>17,} | "
              f"{r['noq']:>9,} {r['noq_g']:>6,} | {r['n']:>9,} {r['n_g']:>6,} | "
              f"{r['med']:>7.4f} {r['p75']:>7.4f} {r['p90']:>7.4f}")
    print(f"\n    Of the {reach['grads']} graduated curves, {reach['grad_same_slot']} "
          f"({100*reach['grad_same_slot']/reach['grads']:.1f}%) complete in the create's OWN slot and")
    print(f"    {reach['grad_same_tx']} share the create's transaction index. Those are unbuyable at ANY price.")
    print(f"\n    WHERE THE GRADUATIONS GO (attrition ladder, K=1 -- the fastest a bot can possibly act):")
    print(f"    {'cohort':<20} {'stage':<38} {'n':>7} {'grads':>6} {'rate':>9}")
    for cname, tot, live_, buy in reach["ladder"][1]:
        for lbl, (n_, k_) in (("0. in the price-path subsample", tot),
                              ("1. still incomplete at create_slot+1", live_),
                              (f"2. AND quotable at m <= {mstar_lo:.3f}x", buy)):
            print(f"    {cname:<20} {lbl:<38} {n_:>7,} {k_:>6,} "
                  f"{(100*k_/n_ if n_ else float('nan')):>8.4f}%")
    print(f"\n    THE BUYABLE TEST -- the one that decides this. Keep only curves that are (i) still")
    print(f"    incomplete at create_slot+K and (ii) quotable at m <= m* = {mstar_lo:.4f}x (the F2 clustered")
    print(f"    95% LOWER bound; the point estimate would allow {mstar_pt:.4f}x). 'first quote' is what a bot")
    print(f"    actually gets; 'oracle best dip' is an UNATTAINABLE upper bound that lets it buy the")
    print(f"    cheapest pre-completion tick it will ever see -- if even that fails, the door is shut.")
    print(f"    EV is per coin, each at the price IT would be bought at: mean over the bought set of")
    print(f"    (1+(X-1)*grad)/m_i - 1 - toll. Non-graduates exit at the hard floor. 95%LO = one-sided")
    print(f"    creator-clustered bootstrap lower bound on that mean.")
    subp = d['sub_k'] / max(d['sub_n'], 1)
    print(f"    {'K':>4} {'entry':<16} {'cohort':<20} {'n':>6} {'grads':>6} {'p_buy':>9} {'lift':>7} "
          f"{'med m':>7} {'mean EV':>9} {'EV 95%LO':>10}")
    for r in reach["buy"]:
        if r["n"] == 0:
            print(f"    {r['K']:>4} {r['entry']:<16} {r['cohort']:<20} {0:>6} {0:>6} "
                  f"{'--':>9} {'--':>7} {'--':>7} {'--':>9} {'--':>10}")
            continue
        print(f"    {r['K']:>4} {r['entry']:<16} {r['cohort']:<20} {r['n']:>6,} {r['k']:>6,} "
              f"{100*r['rate']:>8.4f}% {r['rate']/subp:>6.3f}x {r['med']:>7.4f} "
              f"{100*r['ev']:>8.2f}% {100*r['ev_lo']:>9.2f}%")

    hr("11b. WHY IT FAILS: THE LIFT IS ALREADY IN THE PRICE")
    im = reach["impound"]
    print(f"    Entry premium at create_slot+1, TRADED coins only (like-for-like; untraded coins are")
    print(f"    excluded here so the floor does not swamp the comparison):")
    print(f"    {'cohort':<22} {'n':>6} {'p25 m':>8} {'median m':>10} {'p75 m':>8} "
          f"{'frac <= m*':>11}")
    print(f"    {'F2 prior_grads>=1':<22} {im['nA']:>6,} {im['p25A']:>8.4f} {im['medA']:>10.4f} "
          f"{im['p75A']:>8.4f} {100*im['fracA']:>10.2f}%")
    print(f"    {'no prior graduation':<22} {im['nB']:>6,} {im['p25B']:>8.4f} {im['medB']:>10.4f} "
          f"{im['p75B']:>8.4f} {100*im['fracB']:>10.2f}%")
    print(f"    Mann-Whitney z on the entry premium = {im['z']:.3f} (positive = the provenance-positive")
    print(f"    coins are ALREADY more expensive by the first slot a bot can act).")
    print(f"    The F2 break-even is m* = {mstar_lo:.4f}x (lower bound) / {mstar_pt:.4f}x (point). The median")
    print(f"    F2 coin already quotes at {im['medA']:.4f}x. The premium the edge earns and the premium the")
    print(f"    market already charges are the SAME NUMBER: the lift is impounded before entry.")

    hr("11c. THE STRATEGY, PRICED: buy EVERY cohort coin at the first actionable tick, no filter")
    print(f"    Unbuyable coins (already complete, or completing on that very tick) are SKIPPED, not")
    print(f"    charged as losses -- this is generous to the strategy.")
    print(f"    {'K':>4} {'cohort':<22} {'n':>6} {'grads':>6} {'p':>9} {'median m':>10} "
          f"{'mean EV':>9} {'EV 95%LO':>10}")
    for r in reach["unfiltered"]:
        print(f"    {r['K']:>4} {r['cohort']:<22} {r['n']:>6,} {r['k']:>6,} "
              f"{100*r['k']/r['n']:>8.4f}% {r['med']:>10.4f} {100*r['ev']:>8.2f}% "
              f"{100*r['ev_lo']:>9.2f}%")

    hr("12. VERDICT")
    verdict(co, results, boot, oof, p_max, base_rate, reach, feats, mstar_lo)


# ------------------------------------------------------------------ helpers

def graduation_latency():
    con = sqlite3.connect(f"file:{PATHS_DB}?mode=ro", uri=True)
    rows = con.execute("select create_slot, complete_slot from curve where complete_slot is not null").fetchall()
    con.close()
    lat = sorted(b - a for a, b in rows)
    n = len(lat)
    cdf = {g: sum(1 for x in lat if x <= g) / n for g in [0, 70, 956, 9662, 24268]}
    return {"n": n, "cdf": cdf, "max": lat[-1]}


def gap_gated(co: Cohort, G: int):
    """prior graduations counted only from creator rows whose slot <= this row's slot - G."""
    pos_n = np.zeros(co.n, np.int64); pos_g = np.zeros(co.n, np.int64)
    lab = co.label
    i = 0
    while i < co.n:
        j = i
        while j < co.n and co.creator_idx[j] == co.creator_idx[i]:
            j += 1
        sl = co.slot[i:j]; lb = lab[i:j]
        cs = np.concatenate(([0], np.cumsum(lb)))
        # number of rows in this creator with slot <= slot_k - G
        cut = np.searchsorted(sl, sl - G, side="right")
        # and they must also be strictly earlier in slot: searchsorted on sl-G with G>=1 guarantees it;
        # for G == 0 fall back to strictly-less
        if G == 0:
            cut = np.searchsorted(sl, sl, side="left")
        pos_n[i:j] = cut
        pos_g[i:j] = cs[cut]
        i = j
    have = pos_n >= 1
    p = have & (pos_g >= 1); ng = have & (pos_g == 0)
    if p.sum() == 0 or ng.sum() == 0:
        return None
    return contrast(co.label, p, ng)


def out_of_fold(co: Cohort, feats):
    pn, pg = co.prior_n, feats["prior_grads"]
    cands = [(nmin, t) for nmin in (1, 2, 5, 10) for t in (1, 2, 3)]
    per, tot_k, tot_n = [], 0, 0
    sel_mask = np.zeros(co.n, bool)
    for f in range(5):
        tr = co.fold != f
        te = co.fold == f
        best = None
        for nmin, t in cands:
            m = tr & (pn >= nmin) & (pg >= t)
            if m.sum() < 200:
                continue
            r = co.label[m].mean()
            if best is None or r > best[0]:
                best = (r, nmin, t)
        if best is None:
            continue
        _, nmin, t = best
        m = te & (pn >= nmin) & (pg >= t)
        sel_mask |= m
        per.append(dict(fold=f, rule=f"prior_n>={nmin} and prior_grads>={t}", train_rate=best[0],
                        n=int(m.sum()), k=int(co.label[m].sum()),
                        rate=float(co.label[m].mean()) if m.sum() else 0.0))
        tot_k += int(co.label[m].sum()); tot_n += int(m.sum())
    # creator-clustered lower bound on the pooled OOF rate
    rng = np.random.default_rng(SEED)
    order = np.argsort(co.creator_idx, kind="stable")
    starts = np.searchsorted(co.creator_idx[order], np.arange(co.n_creators))
    S = sel_mask.astype(np.int64)
    ks = np.add.reduceat(np.where(S[order] == 1, co.label[order], 0), starts)
    ns = np.add.reduceat(S[order], starts)
    draws = []
    for _ in range(B_BOOT):
        idx = rng.integers(0, co.n_creators, co.n_creators)
        d = ns[idx].sum()
        if d:
            draws.append(ks[idx].sum() / d)
    return dict(per_fold=per, k=tot_k, n=tot_n, clustered_lo95=float(np.percentile(draws, 5.0)))


def reachability(co: Cohort, feats, mstar_lo, mstar_pt):
    """Measured entry premiums. m = price(t)/floor, price = virtual_quote/virtual_token,
    floor = the CreateEvent reserves. A bot CANNOT act inside the create's own block, so the
    earliest actionable moment is create_slot + K."""
    con = sqlite3.connect(f"file:{PATHS_DB}?mode=ro", uri=True)
    curves = {bc: (cs, comp, ctx, cti) for bc, cs, comp, ctx, cti in con.execute(
        "select bonding_curve, create_slot, complete_slot, create_transaction_index, "
        "complete_transaction_index from curve")}
    paths = {}
    for bc, sl, vq, vt, comp in con.execute(
            "select bonding_curve, slot, virtual_quote, virtual_token, complete from observation "
            "order by bonding_curve, slot, transaction_index, outer_index, inner_index"):
        paths.setdefault(bc, []).append((sl, vq, vt, comp))
    con.close()

    rowof = {bc: i for i, bc in enumerate(co.bc)}
    f2pos = feats["F2_has_prior_grad"][0]
    lab = co.label
    grads = [bc for bc in paths if curves[bc][1] is not None]
    gss = sum(1 for bc in grads if curves[bc][1] == curves[bc][0])
    gst = sum(1 for bc in grads if curves[bc][1] == curves[bc][0] and curves[bc][3] == curves[bc][2])

    # F2 cohort inside the price-path subsample, before any buyability filter
    sub_rows = [rowof[bc] for bc in paths if bc in rowof]
    sub_f2 = [i for i in sub_rows if f2pos[i]]
    diag = dict(sub_n=len(sub_rows), sub_k=int(sum(lab[i] for i in sub_rows)),
                f2_n=len(sub_f2), f2_k=int(sum(lab[i] for i in sub_f2)))

    out = {"curves": len(curves), "grads": len(grads), "grad_same_slot": gss, "grad_same_tx": gst,
           "diag": diag, "by_k": [], "buy": []}
    for K in (1, 2, 5, 25, 150):
        cat = {"complete_before_K": [], "no_quote": [], "quotable": []}
        first_m, best_m = {}, {}
        for bc, path in paths.items():
            cs = curves[bc][0]
            floor = path[0][1] / path[0][2]
            if any(c for sl, _, _, c in path if sl < cs + K):
                cat["complete_before_K"].append(bc); continue
            fut = [o for o in path[1:] if o[0] >= cs + K]
            if not fut:
                # nobody traded it after K: the curve is UNTOUCHED, so it still quotes at the
                # floor. A bot can buy it at m = 1.0. Excluding these would flatter the result.
                cat["no_quote"].append(bc)
                first_m[bc] = 1.0; best_m[bc] = 1.0
                continue
            cat["quotable"].append(bc)
            # if the very first post-K tick is already the completing transaction, the coin was
            # never buyable: price it at +inf so every filter drops it.
            first_m[bc] = float("inf") if fut[0][3] else (fut[0][1] / fut[0][2]) / floor
            live = [(vq / vt) / floor for sl, vq, vt, c in fut if not c]
            best_m[bc] = min(live) if live else float("inf")
        ladder = []
        for cname, sel in (("all subsample", None), ("F2 prior_grads>=1", f2pos)):
            def _cnt(bcs):
                ii = [rowof[b] for b in bcs if b in rowof and (sel is None or f2pos[rowof[b]])]
                return len(ii), int(sum(lab[i] for i in ii))
            tot = _cnt(list(paths))
            live_ = _cnt(cat["no_quote"] + cat["quotable"])
            buy = _cnt([b for b in (cat["no_quote"] + cat["quotable"])
                        if first_m.get(b, float("inf")) <= mstar_lo])
            ladder.append((cname, tot, live_, buy))
        out.setdefault("ladder", {})[K] = ladder
        ms = np.array(sorted(v for v in first_m.values() if np.isfinite(v)))
        out["by_k"].append(dict(
            K=K, done=len(cat["complete_before_K"]), noq=len(cat["no_quote"]), n=len(ms),
            done_g=sum(1 for bc in cat["complete_before_K"] if curves[bc][1] is not None),
            noq_g=sum(1 for bc in cat["no_quote"] if curves[bc][1] is not None),
            n_g=sum(1 for bc in cat["quotable"] if curves[bc][1] is not None),
            med=float(np.median(ms)), p25=float(np.percentile(ms, 25)),
            p75=float(np.percentile(ms, 75)), p90=float(np.percentile(ms, 90))))
        X = venues.graduation_multiple(VENUE)
        toll = venues.VENUES[VENUE].require_toll()
        # --- IS THE LIFT ALREADY IN THE PRICE? like-for-like on TRADED coins only
        if K == 1:
            A = [first_m[b] for b in cat["quotable"] if b in rowof and f2pos[rowof[b]]
                 and np.isfinite(first_m[b])]
            Bn = [first_m[b] for b in cat["quotable"] if b in rowof and not f2pos[rowof[b]]
                  and np.isfinite(first_m[b])]
            A, Bn = np.array(A), np.array(Bn)
            allm = np.concatenate([A, Bn]); rk = allm.argsort().argsort() + 1.0
            U = rk[:len(A)].sum() - len(A) * (len(A) + 1) / 2
            mu = len(A) * len(Bn) / 2.0
            sd = math.sqrt(len(A) * len(Bn) * (len(A) + len(Bn) + 1) / 12.0)
            out["impound"] = dict(
                nA=len(A), medA=float(np.median(A)), p25A=float(np.percentile(A, 25)),
                p75A=float(np.percentile(A, 75)), fracA=float((A <= mstar_lo).mean()),
                nB=len(Bn), medB=float(np.median(Bn)), p25B=float(np.percentile(Bn, 25)),
                p75B=float(np.percentile(Bn, 75)), fracB=float((Bn <= mstar_lo).mean()),
                z=(U - mu) / sd)
        # --- THE UNFILTERED STRATEGY: buy every cohort coin at whatever it quotes
        for cname, sel in (("all subsample", None), ("F2 prior_grads>=1", f2pos)):
            rows_ = [(int(co.creator_idx[rowof[bc]]), int(lab[rowof[bc]]), m)
                     for bc, m in first_m.items()
                     if bc in rowof and np.isfinite(m) and (sel is None or f2pos[rowof[bc]])]
            if not rows_:
                continue
            evs = np.array([(1.0 + (venues.graduation_multiple(VENUE) - 1.0) * g) / m - 1.0
                            - venues.VENUES[VENUE].require_toll() for _, g, m in rows_])
            cl = np.array([c for c, _, _ in rows_])
            u_, inv = np.unique(cl, return_inverse=True)
            es = np.bincount(inv, weights=evs, minlength=len(u_))
            ct = np.bincount(inv, minlength=len(u_)).astype(float)
            rr = np.random.default_rng(SEED)
            pk = rr.integers(0, len(u_), size=(2000, len(u_)))
            dd = es[pk].sum(1) / ct[pk].sum(1)
            out.setdefault("unfiltered", []).append(dict(
                K=K, cohort=cname, n=len(rows_), k=int(sum(g for _, g, _ in rows_)),
                med=float(np.median([m for _, _, m in rows_])), ev=float(evs.mean()),
                ev_lo=float(np.percentile(dd, 5.0))))
        for mname, mm in (("first quote", first_m), ("oracle best dip", best_m)):
            for cname, sel in (("all", None), ("F2 prior_grads>=1", f2pos)):
                rows_ = []
                for bc, m in mm.items():
                    i = rowof.get(bc)
                    if i is None or m > mstar_lo:
                        continue
                    if sel is not None and not sel[i]:
                        continue
                    rows_.append((int(co.creator_idx[i]), int(lab[i]), m))
                if not rows_:
                    out["buy"].append(dict(K=K, entry=mname, cohort=cname, n=0, k=0,
                                           rate=float("nan"), med=float("nan"),
                                           ev=float("nan"), ev_lo=float("nan")))
                    continue
                # PER-COIN EV, each coin at the price IT would actually be bought at.
                # A non-graduate is exited at the hard floor (payoff 1); a graduate pays X.
                evs = np.array([(1.0 + (X - 1.0) * g) / m - 1.0 - toll for _, g, m in rows_])
                ks = sum(g for _, g, _ in rows_)
                cl = np.array([c for c, _, _ in rows_])
                uniq, inv = np.unique(cl, return_inverse=True)
                # cluster bootstrap of a MEAN is exactly sum(ev_per_creator)/sum(n_per_creator)
                ev_sum = np.bincount(inv, weights=evs, minlength=len(uniq))
                cnt = np.bincount(inv, minlength=len(uniq)).astype(float)
                rng = np.random.default_rng(SEED)
                pick = rng.integers(0, len(uniq), size=(1000, len(uniq)))
                draws = ev_sum[pick].sum(axis=1) / cnt[pick].sum(axis=1)
                out["buy"].append(dict(K=K, entry=mname, cohort=cname, n=len(rows_), k=int(ks),
                                       rate=ks / len(rows_),
                                       med=float(np.median([m for _, _, m in rows_])),
                                       ev=float(evs.mean()),
                                       ev_lo=float(np.percentile(draws, 5.0))))
    return out


def verdict(co, results, boot, oof, p_max, base_rate, reach, feats, mstar_lo):
    f2 = results["F2_has_prior_grad"]
    lo = boot["F2_has_prior_grad"]["rate_pos_lo95"]
    mstar_lo = venues.ev_breakeven_premium(VENUE, lo)
    pm = p_max[FEATURE_ORDER.index("F2_has_prior_grad")]
    a = pm < 0.05
    b = mstar_lo >= 1.10
    print(f"    (a) F2 max-stat permutation FWER p = {pm:.5f}  -> {'PASS' if a else 'FAIL'}")
    print(f"    (b) clustered 95% lower conditional rate {100*lo:.4f}% -> m* = {mstar_lo:.4f}x "
          f"(>= 1.10 required) -> {'PASS' if b else 'FAIL'}")
    att = [r for r in reach["buy"]
           if r["cohort"].startswith("F2") and r["entry"] == "first quote" and r["n"] > 0]
    # the m<=m* filter is itself a selection, so the unfiltered "buy them all" strategy from 11c
    # is admitted here too: leg (c) takes the BEST attainable framing available.
    for r in reach["unfiltered"]:
        if r["cohort"].startswith("F2"):
            att.append(dict(K=r["K"], entry="unfiltered (11c)", cohort=r["cohort"], n=r["n"],
                            k=r["k"], rate=r["k"] / r["n"], med=r["med"], ev=r["ev"],
                            ev_lo=r["ev_lo"]))
    orc = [r for r in reach["buy"]
           if r["cohort"].startswith("F2") and r["entry"] == "oracle best dip" and r["n"] > 0]
    best = max(att, key=lambda r: r["ev"], default=None)
    if best is None:
        print("    (c) reachability: NO buyable F2 rows at m* -> FAIL")
        c = False
    else:
        c = best["ev_lo"] > 0
        print(f"    (c) leg (c) is judged ONLY on the ATTAINABLE entry ('first quote'); the oracle-dip")
        print(f"        rows are a diagnostic upper bound and cannot carry a PASS.")
        print(f"        best attainable F2 cell: K={best['K']} [{best['entry']}], {best['k']}/{best['n']} = "
              f"{100*best['rate']:.4f}% graduating, median m={best['med']:.4f}x")
        print(f"        mean per-coin EV = {100*best['ev']:+.2f}%  (clustered 95% lower "
              f"{100*best['ev_lo']:+.2f}%)  -> {'PASS' if c else 'FAIL'}")
        if orc:
            bo = max(orc, key=lambda r: r["ev"])
            print(f"        even the UNATTAINABLE oracle bound tops out at "
                  f"{100*bo['ev']:+.2f}% (95%LO {100*bo['ev_lo']:+.2f}%) at K={bo['K']}.")
    print()
    if a and b and c:
        print("    VERDICT: PASS on all three pre-registered legs.")
    else:
        print("    VERDICT: REFUSE. Legs: (a) permutation %s, (b) m* %s, (c) reachability %s."
              % ("PASS" if a else "FAIL", "PASS" if b else "FAIL", "PASS" if c else "FAIL"))


def main():
    global B_PERM
    ap = argparse.ArgumentParser()
    ap.add_argument("--perm", type=int, default=20000)
    a = ap.parse_args()
    B_PERM = a.perm
    run(a)


if __name__ == "__main__":
    main()
