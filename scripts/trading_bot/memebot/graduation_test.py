#!/usr/bin/env python3
"""
graduation_test.py -- the honest test of whether any PROVENANCE feature predicts
pump.fun graduation ABOVE what the price already tells you.

THE QUESTION, STATED SO IT CAN FAIL
-----------------------------------
On the bonding curve, EV = (1 + (X-1)*p)/m - 1 - toll, with X = 14.6958 the
deterministic graduation multiple and m the entry premium over the launch floor.
A trade only pays if the graduation probability p of the coins you actually buy
clears the break-even implied by the premium you pay.  At m = 1.05 with a 3%
round-trip toll that break-even is p* = 0.595%.

    TRADEABLE QUESTION: does any provenance feature lift p above 0.6%
                        inside the floor-priced cohort (m60 <= 1.05)?

Anything that lifts p only in cohorts already priced up is not tradeable: the
price moved first, and you pay for it in m.  So every test here is STRATIFIED ON
m60 and the null hypothesis is permutation of the graduation label WITHIN those
strata.  A feature scores only by adding information the price does not carry.

WHAT MAKES THIS TEST HONEST
---------------------------
(a) The price-only baseline is reported FIRST, before any feature is looked at.
(b) Every feature is tested against that baseline, never against the
    unconditional base rate (which is the standard way to fake a signal here).
(c) Folds are fixed in advance by sha256(bonding_curve) % K, never resampled.
    The whole selection procedure -- rank screens, pick the best, apply it -- is
    run inside the folds so the reported out-of-fold number prices the search.
(d) p-values are exact stratified permutation p-values, and are ALSO reported
    family-wise adjusted by the minP step-down over the entire screen family, so
    "I tried twenty screens" is paid for.
(e) A power gate is evaluated and printed BEFORE any result, and if the positive
    count cannot support the test the script REFUSES A VERDICT and says so.

    Refusal is a valid, expected output.  It is not a failure of the script.

GATE: research/b11a/SPENT.json marks window 1 SPENT.  Everything below is
hypothesis generation on a spent window; it cannot be a verdict on its own even
when the arithmetic is clean.  The sealed holdout research/b11m_window2/ is not
touched by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import statistics
import sys
from collections import defaultdict

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_CACHE = os.path.join(REPO, "research", "b11a", "derived", "provenance_features.sqlite")

# ======================= PRE-REGISTERED CONSTANTS =========================
# Fixed before any result was looked at.  Changing one invalidates the run.
GRADUATION_MULTIPLE = 14.6958      # (115.0054/30)^2, measured on-chain
TOLL_ASSUMED = 0.03                # what arena/fill.py uses today
TOLL_MEASURED = 0.02               # pump.fun Global: 95 + 5 bps, both sides
FLOOR_M = 1.05                     # the tradeable cohort: entry premium <= this
TARGET_P = 0.006                   # the tradeable bar: 0.6% graduation
ALPHA = 0.05                       # one-sided
POWER = 0.80
K_FOLDS = 5
PERM_B = 20000
MIN_SUPPORT = 50                   # a screen selecting fewer coins is not tested
RNG_SEED = 20260902

# Entry-premium strata.  Coarse over the whole cohort, FINE inside the floor
# cohort, so that a feature cannot win by proxying for a sliver of price move.
STRATA_ALL = [(1.0, 1.05), (1.05, 1.25), (1.25, 2.0), (2.0, 5.0), (5.0, float("inf"))]
STRATA_FLOOR = [(1.0, 1.0000001), (1.0000001, 1.01), (1.01, 1.02), (1.02, 1.05)]

# ---- the screen family, declared up front -------------------------------
# kind: ORTHOGONAL  = knowable at t=0, before any trade prints
#       PRICE_VISIBLE = mechanically part of the first price move (dev buys,
#                       sniper flow, arrival) -- stratification is what keeps
#                       these honest, and they are flagged so the reader knows
#       PRE_ENTRY    = observable by t0+60s without being a price move itself
SCREENS = [
    # ---- orthogonal: creator / metadata provenance ----
    ("first_in_window_creator",   "ORTHOGONAL",    lambda r: r["prior_launches"] == 0),
    ("serial_creator_ge20",    "ORTHOGONAL",    lambda r: r["prior_launches"] >= 20),
    ("uri_host_ipfs_io",       "ORTHOGONAL",    lambda r: r["uri_host"] == "ipfs.io"),
    ("uri_host_j7tracker",     "ORTHOGONAL",    lambda r: r["uri_host"] == "metadata.j7tracker.io"),
    ("cashback_enabled",       "ORTHOGONAL",    lambda r: r["is_cashback_enabled"] == 1),
    # ---- pre-entry: competition intensity (failed transactions) ----
    ("fail10_zero_DEADSCREEN", "PRE_ENTRY",     lambda r: r["fail10"] == 0),
    ("fail10_positive",        "PRE_ENTRY",     lambda r: r["fail10"] > 0),
    ("fail60_positive",        "PRE_ENTRY",     lambda r: r["fail60"] > 0),
    ("fail60_ge_median",       "PRE_ENTRY",     lambda r: r["fail60"] >= r["_med_fail60"]),
    # ---- pre-entry: minute-1 arrival ----
    ("uniq_buyers60_ge3",      "PRICE_VISIBLE", lambda r: r["uniq_buyers60"] >= 3),
    ("uniq_buyers60_ge_med",   "PRICE_VISIBLE", lambda r: r["uniq_buyers60"] >= r["_med_buyers"]),
    ("cluster_buyer_ge1",      "PRICE_VISIBLE", lambda r: r["cluster_buyers60"] >= 1),
    ("cluster_buyer_ge3",      "PRICE_VISIBLE", lambda r: r["cluster_buyers60"] >= 3),
    # ---- pre-entry: holder concentration at t0+60s (real balances) ----
    ("top10_conc_low",         "PRE_ENTRY",     lambda r: r["top10_balance_share"] is not None
                                                          and r["top10_balance_share"] <= r["_med_top10"]),
    ("top10_conc_high",        "PRE_ENTRY",     lambda r: r["top10_balance_share"] is not None
                                                          and r["top10_balance_share"] > r["_med_top10"]),
    ("holders60_ge_median",    "PRE_ENTRY",     lambda r: r["n_holders60"] is not None
                                                          and r["n_holders60"] >= r["_med_holders"]),
    # ---- price-visible: bundled supply and sniper share ----
    ("no_dev_buy",             "PRICE_VISIBLE", lambda r: r["n_bundled_buys"] == 0),
    ("dev_buy_gt5pct",         "PRICE_VISIBLE", lambda r: r["bundled_creator_share"] > 0.05),
    ("bundled_ge_median",      "PRICE_VISIBLE", lambda r: r["bundled_share"] >= r["_med_bundled"]),
    ("sniper_s20_ge_median",   "PRICE_VISIBLE", lambda r: r["s20_share"] >= r["_med_s20"]),
    ("sniper_s1_ge_median",    "PRICE_VISIBLE", lambda r: r["s1_share"] >= r["_med_s1"]),
]
# Thresholds are medians of the FEATURE only -- they never touch the label, so
# computing them on the full cohort leaks nothing.  Stated, not hidden.


# ============================ exact statistics =============================
def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else float("-inf")
    if p >= 1.0:
        return 0.0 if k == n else float("-inf")
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k).  Exact sum; k is always small in this problem."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in range(0, k + 1)))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k)."""
    return 1.0 - binom_cdf(k - 1, n, p)


def _bisect(fn, target, lo, hi, iters=100):
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if fn(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def cp_interval(k: int, n: int, alpha: float = 0.05):
    """Two-sided Clopper-Pearson interval."""
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0 if k == 0 else _bisect(lambda p: binom_sf(k, n, p), alpha / 2, 0.0, 1.0)
    hi = 1.0 if k == n else _bisect(lambda p: 1.0 - binom_cdf(k, n, p), 1 - alpha / 2, 0.0, 1.0)
    return (lo, hi)


def cp_lower_one_sided(k: int, n: int, alpha: float = 0.05) -> float:
    """One-sided (1-alpha) lower confidence bound on p.  This is the bound the
    tradeable question must clear -- a point estimate is not an answer."""
    if n == 0 or k == 0:
        return 0.0
    return _bisect(lambda p: binom_sf(k, n, p), alpha, 0.0, 1.0)


def cp_upper_one_sided(k: int, n: int, alpha: float = 0.05) -> float:
    if n == 0:
        return 1.0
    if k == n:
        return 1.0
    return _bisect(lambda p: 1.0 - binom_cdf(k, n, p), 1 - alpha, 0.0, 1.0)


def n_per_arm(p0: float, p1: float, alpha: float, power: float) -> float:
    """Two-proportion, one-sided, normal approximation."""
    nd = statistics.NormalDist()
    za, zb = nd.inv_cdf(1 - alpha), nd.inv_cdf(power)
    pbar = 0.5 * (p0 + p1)
    num = (za * math.sqrt(2 * pbar * (1 - pbar))
           + zb * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2
    return num / (p1 - p0) ** 2


def break_even_p(m: float, toll: float, X: float = GRADUATION_MULTIPLE) -> float:
    """EV = (1 + (X-1)p)/m - 1 - toll = 0."""
    return (m * (1 + toll) - 1) / (X - 1)


# =============================== data =====================================
def load_rows(cache: str):
    con = sqlite3.connect("file:%s?mode=ro" % cache, uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("select * from features")]
    stamp = con.execute("select value from manifest where key='stamp'").fetchone()
    con.close()
    return rows, json.loads(stamp[0]) if stamp else {}


def attach_thresholds(rows):
    def med(col):
        v = [r[col] for r in rows if r[col] is not None]
        return statistics.median(v) if v else 0.0
    t = {
        "_med_fail60": med("fail60"), "_med_buyers": med("uniq_buyers60"),
        "_med_top10": med("top10_balance_share"), "_med_holders": med("n_holders60"),
        "_med_bundled": med("bundled_share"), "_med_s20": med("s20_share"),
        "_med_s1": med("s1_share"),
    }
    for r in rows:
        r.update(t)
    return t


def fold_of(bonding_curve: str, k: int = K_FOLDS) -> int:
    """Fixed in advance, deterministic, never resampled."""
    return int(hashlib.sha256(bonding_curve.encode()).hexdigest(), 16) % k


def stratum_of(m: float, edges) -> int:
    for i, (lo, hi) in enumerate(edges):
        if lo <= m < hi:
            return i
    return len(edges) - 1


def safe(fn, r):
    try:
        return bool(fn(r))
    except (TypeError, KeyError):
        return False


# ========================= stratified permutation =========================
class StratifiedPermuter:
    """Null: the graduation label is exchangeable WITHIN an entry-premium
    stratum.  Permuting y (not the feature) keeps every feature's mutual
    correlation intact, which is what makes the minP family-wise adjustment
    valid across the whole screen family."""

    def __init__(self, strata: np.ndarray, y: np.ndarray, B: int, seed: int):
        order = np.argsort(strata, kind="stable")
        self.order = order
        self.strata = strata[order].astype(np.float64)
        self.y = y[order].astype(np.float64)
        self.B = B
        self.rng = np.random.default_rng(seed)

    def permuted_y(self, chunk: int):
        """Yield (n x chunk) matrices of within-stratum permuted labels."""
        n = self.y.shape[0]
        done = 0
        while done < self.B:
            c = min(chunk, self.B - done)
            r = self.rng.random((n, c))
            # strata are sorted ascending and integer-valued; adding a uniform
            # in [0,1) keeps blocks disjoint, so argsort shuffles only within.
            idx = np.argsort(self.strata[:, None] + r, axis=0, kind="stable")
            yield self.y[idx]
            done += c

    def feature_matrix(self, feats: np.ndarray) -> np.ndarray:
        return feats[:, self.order].astype(np.float64)


def run_permutations(strata, y, feat_mat, B, seed, chunk=1000):
    perm = StratifiedPermuter(strata, y, B, seed)
    F = perm.feature_matrix(feat_mat)                 # (J, n)
    obs = F @ perm.y                                  # (J,)
    cols = []
    for Y in perm.permuted_y(chunk):
        cols.append(F @ Y)
    null = np.concatenate(cols, axis=1)               # (J, B)
    return obs, null


def minp_adjust(obs: np.ndarray, null: np.ndarray):
    """Single-step minP family-wise adjustment.  Discrete counts make the raw
    p-values coarse; minP handles that far better than a z-standardised maxT."""
    J, B = null.shape
    raw = np.empty(J)
    pperm = np.empty((J, B))
    for j in range(J):
        col = np.sort(null[j])
        # P(stat >= x) under the null, add-one smoothed
        raw[j] = (np.sum(null[j] >= obs[j]) + 1.0) / (B + 1.0)
        ge = B - np.searchsorted(col, null[j], side="left")
        pperm[j] = (ge + 1.0) / (B + 1.0)
    minp = pperm.min(axis=0)
    adj = np.array([(np.sum(minp <= raw[j]) + 1.0) / (B + 1.0) for j in range(J)])
    return raw, adj


# =============================== reporting ================================
def hr(c="="):
    print(c * 100)


def baseline_table(rows, edges, label):
    print("\n%s" % label)
    print("  %-16s %8s %8s %10s   %-22s" % ("m60 stratum", "n", "grads", "rate", "exact 95% CI"))
    per = defaultdict(lambda: [0, 0])
    for r in rows:
        s = stratum_of(r["m60"], edges)
        per[s][0] += 1
        per[s][1] += r["graduated"]
    out = {}
    for s in sorted(per):
        n, k = per[s]
        lo, hi = cp_interval(k, n)
        rate = k / n if n else 0.0
        out[s] = rate
        lo_e, hi_e = edges[s]
        name = "[%.4f,%s)" % (lo_e, "inf" if hi_e == float("inf") else "%.4f" % hi_e)
        print("  %-16s %8d %8d %9.4f%%   [%.4f%%, %.4f%%]"
              % (name, n, k, 100 * rate, 100 * lo, 100 * hi))
    return out


def test_family(rows, edges, cohort_name, verbose=True):
    """Returns per-screen results with stratified expected counts and
    permutation p-values."""
    strata = np.array([stratum_of(r["m60"], edges) for r in rows])
    y = np.array([r["graduated"] for r in rows], dtype=np.float64)
    base = {}
    for s in set(strata.tolist()):
        m = strata == s
        base[s] = y[m].sum() / m.sum()

    names, kinds, mats = [], [], []
    for name, kind, fn in SCREENS:
        f = np.array([1.0 if safe(fn, r) else 0.0 for r in rows])
        if f.sum() < MIN_SUPPORT or f.sum() > len(rows) - MIN_SUPPORT:
            if verbose:
                print("  SKIP %-24s support %d outside [%d, %d]"
                      % (name, int(f.sum()), MIN_SUPPORT, len(rows) - MIN_SUPPORT))
            continue
        names.append(name); kinds.append(kind); mats.append(f)
    if not names:
        return []
    F = np.vstack(mats)
    obs, null = run_permutations(strata, y, F, PERM_B, RNG_SEED)
    raw, adj = minp_adjust(obs, null)

    res = []
    for j, name in enumerate(names):
        f = F[j]
        n_sel = int(f.sum())
        k_sel = int(round(obs[j]))
        exp = float(sum(base[s] * ((f == 1) & (strata == s)).sum() for s in base))
        lift = (k_sel / exp) if exp > 0 else float("nan")
        lo1 = cp_lower_one_sided(k_sel, n_sel, ALPHA)
        hi1 = cp_upper_one_sided(k_sel, n_sel, ALPHA)
        res.append({
            "screen": name, "kind": kinds[j], "n": n_sel, "k": k_sel,
            "rate": k_sel / n_sel if n_sel else 0.0,
            "expected": exp, "lift": lift,
            "p_perm": float(raw[j]), "p_fwer": float(adj[j]),
            "p_lcb95": lo1, "p_ucb95": hi1,
            "clears_target": lo1 > TARGET_P,
        })
    res.sort(key=lambda d: (-d["lift"] if d["lift"] == d["lift"] else 0, d["p_perm"]))
    return res


def print_results(res, cohort_name):
    hr("-")
    print("SCREEN FAMILY -- %s   (label permuted WITHIN m60 strata; %d permutations)"
          % (cohort_name, PERM_B))
    hr("-")
    print("  %-24s %-14s %6s %4s %8s %6s %8s %8s %10s" %
          ("screen", "kind", "n", "grad", "expected", "lift", "p_perm", "p_fwer", "p 95%LCB"))
    for d in res:
        print("  %-24s %-14s %6d %4d %8.2f %6.2f %8.4f %8.4f %9.4f%%"
              % (d["screen"], d["kind"], d["n"], d["k"], d["expected"],
                 d["lift"], d["p_perm"], d["p_fwer"], 100 * d["p_lcb95"]))


def kfold_procedure(rows, edges):
    """Fold-honest evaluation of the WHOLE search: on each training split rank
    the screens by stratified lift, take the best, apply it to the held-out
    fold.  What is reported is the pooled out-of-fold performance of the
    procedure, which is what an actual deployment would get."""
    for r in rows:
        r["_fold"] = fold_of(r["bonding_curve"])
    picks, sel_rows = [], []
    for f in range(K_FOLDS):
        train = [r for r in rows if r["_fold"] != f]
        test = [r for r in rows if r["_fold"] == f]
        strata = np.array([stratum_of(r["m60"], edges) for r in train])
        y = np.array([r["graduated"] for r in train], dtype=float)
        base = {}
        for s in set(strata.tolist()):
            m = strata == s
            base[s] = y[m].sum() / m.sum()
        best, best_lift = None, -1.0
        min_sup = max(10, int(MIN_SUPPORT * (K_FOLDS - 1) / K_FOLDS))
        for name, kind, fn in SCREENS:
            sel = np.array([1.0 if safe(fn, r) else 0.0 for r in train])
            if sel.sum() < min_sup:
                continue
            k = float((sel * y).sum())
            exp = float(sum(base[s] * ((sel == 1) & (strata == s)).sum() for s in base))
            lift = (k / exp) if exp > 0 else 0.0
            if lift > best_lift:
                best, best_lift = (name, fn), lift
        if best is None:
            picks.append((f, None, 0.0, 0, 0))
            continue
        name, fn = best
        chosen = [r for r in test if safe(fn, r)]
        picks.append((f, name, best_lift, len(chosen), sum(r["graduated"] for r in chosen)))
        sel_rows.extend(chosen)
    return picks, sel_rows


def ev_panel(rows, label):
    """The money question, computed per coin: enter at px(t0+60s), exit at the
    last on-curve price.  Uses only coins that actually traded by t0+60s."""
    usable = [r for r in rows if r["px60"] and r["last_px"]]
    print("\n%s  (n usable = %d of %d)" % (label, len(usable), len(rows)))
    for toll, tname in ((TOLL_ASSUMED, "3.0% (arena/fill.py)"),
                        (TOLL_MEASURED, "2.0% (measured on-chain)")):
        net = [(r["last_px"] / r["px60"]) * (1 - toll) - 1 for r in usable]
        if not net:
            continue
        mu = statistics.mean(net)
        sd = statistics.pstdev(net) if len(net) > 1 else 0.0
        t = mu / (sd / math.sqrt(len(net))) if sd > 0 else float("nan")
        print("    toll %-24s meanNet %+7.2f%%   median %+6.2f%%   t %+5.2f"
              % (tname, 100 * mu, 100 * statistics.median(net), t))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    a = ap.parse_args()

    rows, stamp = load_rows(a.cache)
    rows = [r for r in rows if r["m60"] is not None]
    attach_thresholds(rows)

    hr()
    print("GRADUATION TEST -- provenance features vs the price-only baseline")
    hr()
    print("cache          : %s" % a.cache)
    print("extractor sha  : %s" % stamp.get("extractor_sha256", "?"))
    print("prereg         : X=%.4f  floor m<=%.2f  target p>%.2f%%  alpha=%.2f (1-sided)"
          " power=%.2f  folds=%d(sha256 mod)  perms=%d  seed=%d"
          % (GRADUATION_MULTIPLE, FLOOR_M, 100 * TARGET_P, ALPHA, POWER,
             K_FOLDS, PERM_B, RNG_SEED))
    print("GATE           : research/b11a/SPENT.json marks window 1 SPENT."
          "  This is hypothesis generation, not a verdict.")

    n = len(rows)
    k = sum(r["graduated"] for r in rows)
    lo, hi = cp_interval(k, n)
    hr()
    print("(a) BASE RATE AND PRICE-ONLY BASELINE")
    hr()
    print("\nunconditional: n=%d graduated=%d  rate=%.4f%%  exact 95%% CI [%.4f%%, %.4f%%]"
          % (n, k, 100 * k / n, 100 * lo, 100 * hi))

    print("\nbreak-even graduation probability p* by entry premium m:")
    print("  %-8s %14s %14s" % ("m", "p* @3% toll", "p* @2% toll"))
    for m in (1.00, 1.01, 1.02, 1.05, 1.10, 1.25):
        print("  %-8.2f %13.4f%% %13.4f%%"
              % (m, 100 * break_even_p(m, TOLL_ASSUMED), 100 * break_even_p(m, TOLL_MEASURED)))

    baseline_table(rows, STRATA_ALL, "PRICE-ONLY BASELINE (whole cohort):")
    floor = [r for r in rows if r["m60"] <= FLOOR_M]
    baseline_table(floor, STRATA_FLOOR, "PRICE-ONLY BASELINE (floor cohort, fine strata):")

    kf = sum(r["graduated"] for r in floor)
    p0 = kf / len(floor) if floor else 0.0
    lo_f, hi_f = cp_interval(kf, len(floor))
    print("\nFLOOR COHORT (m60 <= %.2f): n=%d graduated=%d rate=%.4f%% CI [%.4f%%, %.4f%%]"
          % (FLOOR_M, len(floor), kf, 100 * p0, 100 * lo_f, 100 * hi_f))

    # ---------------- (e) THE POWER GATE, BEFORE ANY FEATURE ----------------
    hr()
    print("(e) POWER GATE -- evaluated BEFORE any feature is examined")
    hr()
    npa = n_per_arm(max(p0, 1e-6), TARGET_P, ALPHA, POWER)
    events_needed = npa * TARGET_P
    print("\nto separate p=%.3f%% (the tradeable bar) from the floor baseline"
          " p0=%.4f%% at alpha=%.2f, power=%.2f:" % (100 * TARGET_P, 100 * p0, ALPHA, POWER))
    print("  required n per arm            : %.0f coins" % npa)
    print("  expected graduations in the treated arm at the alternative : %.1f" % events_needed)
    print("  graduations actually available in the floor cohort         : %d" % kf)
    print("\nsmallest k that clears the %.2f%% bar (one-sided 95%% LCB > target),"
          " by selected-cohort size:" % (100 * TARGET_P))
    print("  %-10s %s" % ("n selected", "min graduations needed"))
    for nsel in (100, 250, 500, 1000, 2000, len(floor)):
        need = None
        for kk in range(0, 40):
            if cp_lower_one_sided(kk, nsel, ALPHA) > TARGET_P:
                need = kk
                break
        print("  %-10d %s" % (nsel, need if need is not None else ">40"))

    refuse = kf < events_needed
    if refuse:
        hr("!")
        print("REFUSAL: the floor-priced cohort holds %d graduations.  The design needs"
              " ~%.0f events" % (kf, events_needed))
        print("in the treated arm to answer the tradeable question at the pre-registered"
              " power.  A %d-event" % kf)
        print("sample cannot rank features, cannot be cross-validated, and cannot support"
              " a verdict.")
        print("NO VERDICT IS ISSUED.  Everything below is reported as descriptive"
              " arithmetic only.")
        hr("!")

    # ---------------- (b)(d) feature lift above the baseline ----------------
    hr()
    print("(b)(d) DOES ANY FEATURE ADD LIFT ABOVE THE PRICE-ONLY BASELINE?")
    hr()
    print("\nlift = observed graduations / graduations expected from the m60 stratum alone.")
    print("lift > 1 means the feature knows something the price does not."
          "  p_fwer is minP-adjusted over the whole family.")
    res_all = test_family(rows, STRATA_ALL, "whole cohort")
    print_results(res_all, "WHOLE COHORT (n=%d, %d graduations)" % (n, k))
    res_floor = test_family(floor, STRATA_FLOOR, "floor cohort")
    print_results(res_floor, "FLOOR COHORT m60<=%.2f (n=%d, %d graduations)"
                  % (FLOOR_M, len(floor), kf))

    # ---------------- (c) fixed folds ----------------
    hr()
    print("(c) FIXED-FOLD EVALUATION OF THE SELECTION PROCEDURE")
    hr()
    print("\nfolds assigned by sha256(bonding_curve) %% %d, fixed before any result."
          "  Per fold: rank screens" % K_FOLDS)
    print("by stratified lift on the 4 training folds, take the best, apply to the"
          " held-out fold.\n")
    picks, sel = kfold_procedure(floor, STRATA_FLOOR)
    print("  %-6s %-24s %10s %10s %8s" % ("fold", "screen picked on train", "train lift",
                                          "n selected", "grads"))
    for f, name, lift, nsel, ksel in picks:
        print("  %-6d %-24s %10.2f %10d %8d" % (f, name or "(none)", lift, nsel, ksel))
    if sel:
        ns, ks = len(sel), sum(r["graduated"] for r in sel)
        lcb = cp_lower_one_sided(ks, ns, ALPHA)
        clo, chi = cp_interval(ks, ns)
        print("\n  POOLED OUT-OF-FOLD: n=%d graduations=%d rate=%.4f%%"
              " exact 95%% CI [%.4f%%, %.4f%%]" % (ns, ks, 100 * ks / ns, 100 * clo, 100 * chi))
        print("  one-sided 95%% lower bound on p = %.4f%%   (bar is %.2f%%)  -> %s"
              % (100 * lcb, 100 * TARGET_P, "CLEARS" if lcb > TARGET_P else "DOES NOT CLEAR"))

    # ---------------- fragility ----------------
    hr()
    print("FRAGILITY -- how many coins is the best cell actually made of?")
    hr()
    if res_floor:
        best = max(res_floor, key=lambda d: d["lift"] if d["lift"] == d["lift"] else -1)
        fn = dict((s[0], s[2]) for s in SCREENS)[best["screen"]]
        cell = [r for r in floor if safe(fn, r)]
        grads = [r for r in cell if r["graduated"]]
        print("\nbest floor screen by lift: %s  (n=%d, graduations=%d, lift=%.2f)"
              % (best["screen"], best["n"], best["k"], best["lift"]))
        usable = [r for r in cell if r["px60"] and r["last_px"]]
        if usable:
            net = [(r["last_px"] / r["px60"]) * (1 - TOLL_ASSUMED) - 1 for r in usable]
            ng = [v for v, r in zip(net, usable) if not r["graduated"]]
            print("  mean net return with all coins        : %+.2f%%" % (100 * statistics.mean(net)))
            if ng:
                print("  mean net return excluding graduates   : %+.2f%%  (n=%d)"
                      % (100 * statistics.mean(ng), len(ng)))
            idx = [i for i, r in enumerate(usable) if r["graduated"]]
            for i in idx:
                kept = [v for j, v in enumerate(net) if j != i]
                print("  drop ONE graduate -> mean            : %+.2f%%" % (100 * statistics.mean(kept)))
        print("  the entire result rests on %d coin(s)." % len(grads))

    ev_panel(floor, "EV PANEL -- floor cohort, enter at px(t0+60s), exit at last on-curve price")

    # ---------------- the tradeable question ----------------
    hr()
    print("THE TRADEABLE QUESTION")
    hr()
    print("\n  Does any feature lift p above %.1f%% inside the floor cohort (m60 <= %.2f)?\n"
          % (100 * TARGET_P, FLOOR_M))
    winners = [d for d in res_floor if d["clears_target"]]
    print("  screens whose one-sided 95%% LOWER bound on p exceeds %.1f%%: %d"
          % (100 * TARGET_P, len(winners)))
    for d in winners:
        print("    %-24s n=%d k=%d LCB=%.4f%% p_fwer=%.4f"
              % (d["screen"], d["n"], d["k"], 100 * d["p_lcb95"], d["p_fwer"]))
    best_pt = max(res_floor, key=lambda d: d["rate"]) if res_floor else None
    if best_pt:
        print("\n  highest POINT estimate in the floor cohort: %s  p=%.4f%%"
              " (95%% CI [%.4f%%, %.4f%%], k=%d)"
              % (best_pt["screen"], 100 * best_pt["rate"],
                 100 * cp_interval(best_pt["k"], best_pt["n"])[0],
                 100 * cp_interval(best_pt["k"], best_pt["n"])[1], best_pt["k"]))
    sig = [d for d in res_floor if d["p_fwer"] < ALPHA]
    print("  screens surviving family-wise correction at alpha=%.2f: %d %s"
          % (ALPHA, len(sig), [d["screen"] for d in sig]))

    print()
    hr()
    if refuse:
        print("ANSWER: REFUSED.  %d graduations in the floor cohort is below the ~%.0f"
              " the design requires." % (kf, events_needed))
        print("        No feature can be honestly ranked, and no verdict is issued."
              "  The binding constraint")
        print("        is LABELS, not features.")
    elif winners and sig:
        print("ANSWER: YES -- %s clears the bar and survives correction."
              % winners[0]["screen"])
    else:
        print("ANSWER: NO.  No screen's lower confidence bound clears %.1f%% while"
              " surviving correction." % (100 * TARGET_P))
    hr()
    return 0


if __name__ == "__main__":
    sys.exit(main())
