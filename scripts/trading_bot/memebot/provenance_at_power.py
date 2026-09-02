#!/usr/bin/env python3
# ======================================================================================================
# provenance_at_power.py — the create-time provenance test, run at census power.
#
#   HYPOTHESIS UNDER TEST
#       H1: a creator's OTHER launches predict whether THIS launch graduates.
#   plus the two other create-time dimensions the task names:
#       H2: the platform (platform_config) predicts graduation.
#       H3: the launch curve configuration (Q0, raise target, migrate_type) predicts graduation.
#
#   DATA
#       research/launchpads/census/launchlab_provenance.sqlite — a COMPLETE, survivorship-free census of
#       every Raydium LaunchLab PoolState ever opened (accounts are never closed), pulled by
#       launchlab_provenance.py. 1,292,365 curves, 13,694 migrated. The label is status@offset17.
#
#   ---------------------------------------------------------------------------------------------------
#   PRE-REGISTRATION.  Everything in this block is fixed BEFORE any statistic is computed, and is
#   printed first whenever this module runs.  Read PREREG_HONESTY below: one part of it is NOT a clean
#   pre-registration and this file says so out loud rather than pretending otherwise.
#   ---------------------------------------------------------------------------------------------------
# ======================================================================================================
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sqlite3
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import venues as V  # noqa: E402  (the EV algebra; this file never edits it)

DB = os.path.join(_REPO, "research", "launchpads", "census", "launchlab_provenance.sqlite")
CACHE = os.path.join(_REPO, "research", "launchpads", "census", "provenance_at_power_cache.npz")
OUT = os.path.join(_REPO, "research", "launchpads", "census", "provenance_at_power_report.json")
FRESH = os.path.join(_REPO, "research", "launchpads", "census", "provenance_freshness.json")
RPC = "https://api.mainnet-beta.solana.com"

# ---------------------------------------------------------------------------------------------------
# PRE-REGISTERED CONSTANTS
# ---------------------------------------------------------------------------------------------------
SEED = 20260902            # fixed once, never tuned
N_PERM = 1000              # permutation replicates; p-value resolution floor = 1/(N_PERM+1)
N_FOLDS = 5                # fold(pool) = int(sha256(pool)[:8], 16) % 5   -- deterministic, no seed
ALPHA = 0.05               # one-sided
MIN_TRAIN_N = 200          # a group must have >= this many TRAIN-fold curves to be selectable
TOLL_LETSBONK = 0.03       # MEASURED round-trip toll, research/launchpads/MEASURED_CONSTANTS.json
X_LETSBONK = 14.6938       # MEASURED graduation multiple for the dominant LetsBonk curve

PREREG_FEATURES = [
    # (id, family, kind, future_contaminated, description)
    ("A1", "creator", "loo",    False, "creator has >=1 OTHER graduated launch (leave-one-out)"),
    ("A2", "creator", "loo",    False, "creator has >=2 OTHER graduated launches (leave-one-out)"),
    ("A3", "creator", "loo",    False, "creator LOO graduation rate >= 5% among creators with >=5 other launches"),
    ("A4", "creator", "loo",    True,  "creator has 0 other launches (SOLO) -- uses the future, flagged"),
    ("A5", "creator", "loo",    True,  "creator has <=4 other launches -- uses the future, flagged"),
    ("A6", "creator", "loo",    True,  "creator has >=100 other launches (negative screen) -- uses the future, flagged"),
    ("A7", "creator", "omnibus",False, "same-creator both-graduate pair concordance vs p^2 (creator heterogeneity)"),
    ("B1", "platform","static", False, "platform_config == LetsBonk FfYek5vE..."),
    ("B2", "platform","static", False, "platform_config == Raydium-own 4Bu96XjU..."),
    ("B3", "platform","select", False, "platform in the fold-selected UP set (train CP-lower > train base rate)"),
    ("B4", "platform","select", False, "platform in the fold-selected DOWN set (train CP-upper < train base rate) -- deadness screen"),
    ("C1", "curve",   "static", False, "migrate_type == 1"),
    ("C2", "curve",   "static", False, "raise target R == 85 SOL (the dominant config)"),
    ("C3", "curve",   "select", False, "curve tuple (Q0,R,migrate_type) in the fold-selected UP set"),
    ("C4", "curve",   "select", False, "curve tuple in the fold-selected DOWN set -- deadness screen"),
    ("D1", "joint",   "select", False, "platform UP set AND curve UP set (both selected inside the training folds)"),
]

PREREG_LOO_RULE = """
LEAVE-ONE-OUT, ENFORCED BY CONSTRUCTION (not by convention):
  For creator c let N_c = that creator's total curves in the census and G_c = that creator's total
  graduations.  When scoring curve i belonging to creator c the history handed to the feature is
      n_loo(i) = N_c - 1                 g_loo(i) = G_c - y_i
  computed as a vectorised array subtraction of the row's OWN label.  There is no code path in which a
  curve's own y reaches its own feature: the subtraction is unconditional.  assert_loo_is_airtight()
  proves it empirically by flipping every label to 1, recomputing, and checking that no row's own flip
  changed its own feature value.
  In the FOLD evaluation the history is stricter still: for a curve in test fold f the creator history is
  built ONLY from that creator's curves in the four TRAINING folds, so neither the curve's own label nor
  any other test-fold label can enter its feature.
"""

PREREG_DECISION_RULE = """
DECISION RULE (fixed before any result was computed).  A feature SURVIVES iff ALL THREE hold:
  (1) STATISTICAL   out-of-fold conditional rate has a one-sided 95% Clopper-Pearson LOWER bound strictly
                    above the corpus base rate p0.
  (2) MULTIPLICITY  its permutation p-value (seed 20260902, 1000 replicates, the permutation re-runs the
                    ENTIRE pipeline including any fold-internal selection) survives Holm-Bonferroni
                    correction across the whole 16-feature family at family-wise alpha = 0.05.
  (3) ECONOMIC      the cohort's measured prize term  E[(X_i - 1) * y_i]  must raise the break-even entry
                    premium  m* = (1 + prize) / (1 + toll)  materially above the corpus m*.  A lift that
                    does not widen the entry window is not an edge.
A feature that passes (1) and (2) but fails (3) is reported as REAL BUT NOT TRADEABLE.
A feature flagged future_contaminated cannot SURVIVE at all; it is reported as an OPTIMISTIC UPPER BOUND
on what the create-time-knowable version of the same idea could ever be worth.
"""

PREREG_HONESTY = """
HONESTY DECLARATIONS -- read these before believing any number below.
  (a) NOT A CLEAN PRE-REGISTRATION.  Before fixing this feature list I ran an exploratory pass over the
      same census (creator launch-count buckets, platform rates, curve-tuple rates).  So the FAMILY was
      chosen with knowledge of the pooled table.  The defence is that every "select" feature performs its
      selection ALGORITHMICALLY INSIDE THE TRAINING FOLDS and is scored only out-of-fold, and that the
      permutation null re-runs that selection -- so B3/B4/C3/C4/D1 are honest regardless of what I saw.
      The "static" features B1/B2/C1/C2 were chosen after seeing pooled rates and their p-values should be
      read as descriptive, not confirmatory.
  (b) NO CREATE TIME EXISTS IN THIS TABLE.  PoolState carries no creation slot or timestamp and epoch@8 is
      contaminated (61% of migrated AND 61% of funding curves both sit at epoch 920).  Therefore a
      creator's "other launches" are their launches ACROSS ALL TIME, including launches that happened
      AFTER the curve being scored.  Leave-one-out removes the curve's own outcome; it does NOT remove the
      future.  Every creator feature is consequently an upper bound on a deployable version, and the
      features explicitly marked future_contaminated (A4/A5/A6 -- anything keyed on the launch COUNT) are
      not merely optimistic, they are unknowable at create time and are reported as bounds only.
  (c) PLATFORM AND CURVE FEATURES ARE NOT TIME-CONTAMINATED.  platform_config and the curve constants are
      written at create and never change (verified by launchlab_provenance.py leakdiff: 0 changes on
      84,187 curves over a 130-139 minute window, positive control fired).  They are knowable in the
      create transaction itself.  Their separate hazard is LIVENESS, not leakage: a snapshot cannot tell a
      platform that is launching coins today from one that died in June.  The `freshness` subcommand
      measures that on-chain; until it is run, treat any platform cohort as possibly historical.
  (d) TOLL IS MEASURED FOR EXACTLY TWO PLATFORMS.  LetsBonk 3.0%/round-trip and Raydium-own 2.1% are read
      off live TradeEvents.  Every other platform_config's fee rate is UNMEASURED, so any EV quoted for an
      exotic platform uses the LetsBonk 3% as a stand-in and is wrong by an unknown amount.
"""


# ---------------------------------------------------------------------------------------------------
# MEASURED VERDICT, written after the run.  Kept next to the pre-registration on purpose: this file's
# own honesty declaration (b) named the chronology hole, and the hole turned out to be the whole story.
# ---------------------------------------------------------------------------------------------------
MEASURED_VERDICT = """
2026-09-02.  RUN COMPLETE.  N=1,292,365  K=13,694  p0=0.01059608.

H1 AS PRE-REGISTERED IS DEAD, TWICE OVER, AND FOR TWO DIFFERENT REASONS.
  A1 "creator has >=1 other graduation": n=599,519, k=6,233, lift 0.9812, permutation p_up 0.986, Holm
     1.000.  A well-powered NULL -- at that n the test resolves a lift of 1.031 and none was there.
  A7 pair concordance: lift 0.9569, p_up 0.8651.  No creator heterogeneity in the pooled corpus either.
  BUT A1/A7 are a SIMPSON'S PARADOX.  Holding launch count fixed (labels shuffled inside each stratum,
  which is exact because all of a creator's curves share the same n_other) the same feature has lift
  8.52 / 6.69 / 6.67 / 6.02 / 4.27 / 1.35 / 1.09 across n_other = 1 / 2 / 3-5 / 6-20 / 21-100 /
  101-1000 / 1001+, every one at the permutation floor p=0.001, Holm 0.007.  Pre-registered A3 (the
  creator's LOO RATE, which sidesteps the confound) is lift 11.95 at n=15,245 with p=0.001.
  Strictly out of fold (history from the four training folds only) the rule "train graduation rate >=20%
  over >=5 train launches" gives n=3,118, k=1,355, rate 0.4346, LIFT 41.0, CP95-lower 0.4199, per-fold
  0.418/0.450/0.438/0.439/0.430.  It is not a platform or curve artefact (it survives inside a single
  platform x single curve config: lifts 6.6/6.0/7.0/4.6/2.6), not one whale (312 creators, top creator
  4.8% of the cohort's graduations), and not history-hungry (20% of a creator's record gives lift 40.7
  versus 39.5 at 80%).

  AND THEN IT DIES ON CHRONOLOGY.  Fetching the real create slot for 196 launches of 29 creators (a
  pool's oldest signature) and sorting each creator's launches in time:
     graduation rate by position in the creator's OWN sequence, balanced panel of 30 creators x first 5
     launches: 43.3% / 30.0% / 13.3% / 0.0% / 10.0%.  Early (pos 0-1) 36.7% vs late (pos 3-4) 5.0%.
     Permutation, shuffling WITHIN each creator, 200,000 draws: p = 0.000010 (trend p = 0.000020).
  WITHIN-CREATOR EXCHANGEABILITY IS REJECTED.  A creator's graduations are front-loaded, so by the time
  a prior graduation is observable the creator's hot window is over.  Scored with STRICTLY PRIOR history
  against a position-matched control, the rule has lift 0.448 (n=77, 2 graduations vs a 5.80% base) --
  no signal, and directionally negative.  Every leave-one-out and every fold-based creator number above
  is therefore an artefact of reading the creator's future.  This is a LAGGING INDICATOR, not an edge.

H2 PLATFORM: B3 (fold-selected UP set) lift 1.551 at n=92,650, permutation p 0.023 -> Holm 0.230.  Does
  not survive the family.  LetsBonk itself is lift 1.0015 (p 0.363).  Dead.
H3 CURVE CONFIG: C3 lift 3.123 at n=58,353, p=0.001, Holm 0.016, and it survives creator-blocked folds
  (lift 2.728).  Statistically real.  But the same lagging trap applies: sampled create times for the
  top configs are 0% within the last 60 days (Q0=17.648/R=50, lift 22.1: all 11 sampled pools 394-407
  days old).  So is the corpus itself -- the dominant baseline config's sampled pools have a median age
  of 411 days and 0% in the last 180.  Every rate in this census describes a launch era that has passed.

ECONOMICS.  p is not the binding constraint: break-even at the floor is p = toll/(X-1) = 0.0021908 and
  the corpus base rate clears that 4.84x.  The entry premium is the constraint.  Corpus m* = 1.11175
  (1.632 SOL of an 85 SOL raise).  Measured on chain (10 dominant-curve cohort graduates), the premium
  is m = 1.344 at t+1s, 1.504 at t+5s, 2.504 at t+30s, 3.076 at t+60s; losers recover E[1/m] = 0.998744
  (28,264 non-graduated cohort curves, from their FINAL real_quote, an upper bound on m).  After
  friction (2s/Q0 impact + ATA rent + fees) the CORPUS sits at EV -0.007 to +0.047 on a 0.1 SOL clip --
  i.e. at zero, which reproduces the b11a closure independently on LaunchLab.

VERDICT: REFUSED.  No create-time provenance edge is established.  The creator signal is real,
enormous and NOT TRADEABLE: it is measurable only with the creator's future in hand.  The two
measurements that would reopen it are (1) a create-slot-ordered census -- prior-history-only rates at
census power, not the 196-launch probe here -- and (2) the realizable exit multiple at migration, since
the whole EV frame assumes a graduation pays X = 14.6938 and nothing here verifies that.
"""


def print_prereg() -> None:
    print("=" * 102)
    print("PRE-REGISTRATION -- printed before any result, every run")
    print("=" * 102)
    print(f"seed={SEED}  permutations={N_PERM}  folds={N_FOLDS} (sha256(pool)%5)  alpha={ALPHA} one-sided")
    print(f"min train-fold group size for selection = {MIN_TRAIN_N}")
    print(f"venue constants imported from venues.py: X_letsbonk={V.graduation_multiple('letsbonk'):.4f} "
          f"toll_round_trip={V.VENUES['letsbonk'].toll_round_trip}")
    print("\nFEATURE FAMILY (fixed, 16 tests, Holm-corrected as one family):")
    for fid, fam, kind, contam, desc in PREREG_FEATURES:
        flag = "  [FUTURE-CONTAMINATED: bound only]" if contam else ""
        print(f"  {fid:3s} {fam:8s} {kind:8s} {desc}{flag}")
    print(PREREG_LOO_RULE)
    print(PREREG_DECISION_RULE)
    print(PREREG_HONESTY)
    print("=" * 102)
    print(MEASURED_VERDICT)
    print("=" * 102)


# ---------------------------------------------------------------------------------------------------
# Statistics, hand-rolled (no scipy in this environment)
# ---------------------------------------------------------------------------------------------------
def _betacf(a: float, b: float, x: float) -> float:
    MAXIT, EPS, FPMIN = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
           + a * math.log(x) + b * math.log1p(-x))
    bt = math.exp(lbt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _beta_inv(a: float, b: float, target: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if betai(a, b, mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def cp_lower(k: int, n: int, alpha: float = ALPHA) -> float:
    """Clopper-Pearson one-sided lower bound on a binomial rate."""
    if n == 0 or k == 0:
        return 0.0
    return _beta_inv(k, n - k + 1, alpha)


def cp_upper(k: int, n: int, alpha: float = ALPHA) -> float:
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    return _beta_inv(k + 1, n - k, 1.0 - alpha)


def hyper_sf(k: int, N: int, K: int, n: int) -> float:
    """P(X >= k) for Hypergeometric(N population, K successes, n draws).  Exact, log-space."""
    if k <= max(0, n - (N - K)):
        return 1.0
    hi = min(n, K)
    if k > hi:
        return 0.0
    lg = math.lgamma

    def logpmf(i: int) -> float:
        return (lg(K + 1) - lg(i + 1) - lg(K - i + 1)
                + lg(N - K + 1) - lg(n - i + 1) - lg(N - K - n + i + 1)
                - (lg(N + 1) - lg(n + 1) - lg(N - n + 1)))
    terms = [logpmf(i) for i in range(k, hi + 1)]
    mx = max(terms)
    return math.exp(mx) * sum(math.exp(t - mx) for t in terms)


def min_detectable_rate(n: int, p0: float, alpha: float = ALPHA, power: float = 0.80) -> float:
    """Smallest true rate p1 a cohort of size n can distinguish from p0 at the stated alpha/power.

    Normal approximation with continuity correction; exact enough at these n and checked against the
    exact hypergeometric threshold count where n is small.
    """
    if n <= 0:
        return float("nan")
    z_a, z_b = 1.6448536269514722, 0.8416212335729143  # Phi^-1(0.95), Phi^-1(0.80)
    lo, hi = p0, 1.0
    for _ in range(200):
        p1 = 0.5 * (lo + hi)
        need = (z_a * math.sqrt(p0 * (1 - p0)) + z_b * math.sqrt(p1 * (1 - p1))) / math.sqrt(n)
        if p1 - p0 >= need:
            hi = p1
        else:
            lo = p1
    return 0.5 * (lo + hi)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone-enforced)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = running
    return out


# ---------------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------------
def _unwrap(v):
    return v + 2 ** 64 if (v is not None and v < 0) else v


@dataclass
class Census:
    y: np.ndarray            # int8 graduation label
    cidx: np.ndarray         # creator index
    pidx: np.ndarray         # platform_config index
    kidx: np.ndarray         # curve-tuple index (Q0, R, migrate_type)
    fold: np.ndarray         # int8 fold id
    X: np.ndarray            # per-curve deterministic graduation multiple ((Q0+R)/Q0)^2
    n_creators: int
    n_platforms: int
    n_curvetuples: int
    platform_pk: list        # index -> pubkey
    curve_desc: list         # index -> (Q0_sol, R_sol, migrate_type)
    N: int = field(init=False)
    K: int = field(init=False)
    p0: float = field(init=False)

    def __post_init__(self):
        self.N = int(self.y.size)
        self.K = int(self.y.sum())
        self.p0 = self.K / self.N


def load_census(force: bool = False) -> Census:
    if os.path.exists(CACHE) and not force:
        z = np.load(CACHE, allow_pickle=True)
        return Census(y=z["y"], cidx=z["cidx"], pidx=z["pidx"], kidx=z["kidx"], fold=z["fold"],
                      X=z["X"], n_creators=int(z["n_creators"]), n_platforms=int(z["n_platforms"]),
                      n_curvetuples=int(z["n_curvetuples"]),
                      platform_pk=list(z["platform_pk"]), curve_desc=[tuple(t) for t in z["curve_desc"]])
    t0 = time.time()
    con = sqlite3.connect(DB)
    pk_by_id = {i: p for i, p in con.execute("select id, pk from pubkeys")}
    rows = con.execute(
        "select pool, creator, platform_config, graduated, virtual_quote, "
        "total_quote_fund_raising, migrate_type from pools").fetchall()
    con.close()
    n = len(rows)
    y = np.fromiter((r[3] for r in rows), dtype=np.int8, count=n)
    creators = np.array([r[1] for r in rows])
    _, cidx = np.unique(creators, return_inverse=True)
    del creators
    plat_raw = np.fromiter((r[2] for r in rows), dtype=np.int64, count=n)
    uplat, pidx = np.unique(plat_raw, return_inverse=True)
    platform_pk = [pk_by_id.get(int(i), f"<id{int(i)}>") for i in uplat]
    q0 = np.fromiter((_unwrap(r[4]) for r in rows), dtype=np.float64, count=n)
    rr = np.fromiter((_unwrap(r[5]) for r in rows), dtype=np.float64, count=n)
    mt = np.fromiter((r[6] if r[6] is not None else -1 for r in rows), dtype=np.int64, count=n)
    key = np.stack([q0, rr, mt.astype(np.float64)], axis=1)
    ukey, kidx = np.unique(key, axis=0, return_inverse=True)
    curve_desc = [(float(a) / 1e9, float(b) / 1e9, int(c)) for a, b, c in ukey]
    with np.errstate(divide="ignore", invalid="ignore"):
        X = np.where(q0 > 0, ((q0 + rr) / q0) ** 2, np.nan)
    fold = np.fromiter(
        (int(hashlib.sha256(r[0].encode()).hexdigest()[:8], 16) % N_FOLDS for r in rows),
        dtype=np.int8, count=n)
    np.savez_compressed(CACHE, y=y, cidx=cidx.astype(np.int32), pidx=pidx.astype(np.int32),
                        kidx=kidx.astype(np.int32), fold=fold, X=X,
                        n_creators=int(cidx.max() + 1), n_platforms=len(uplat),
                        n_curvetuples=len(ukey), platform_pk=np.array(platform_pk, dtype=object),
                        curve_desc=np.array(curve_desc, dtype=object))
    print(f"[load] {n} rows, {int(cidx.max()+1)} creators, {len(uplat)} platforms, "
          f"{len(ukey)} curve tuples, {time.time()-t0:.1f}s -> cached")
    return Census(y=y, cidx=cidx.astype(np.int32), pidx=pidx.astype(np.int32),
                  kidx=kidx.astype(np.int32), fold=fold, X=X, n_creators=int(cidx.max() + 1),
                  n_platforms=len(uplat), n_curvetuples=len(ukey),
                  platform_pk=platform_pk, curve_desc=curve_desc)


# ---------------------------------------------------------------------------------------------------
# Leave-one-out machinery.  Every creator feature goes through exactly these two lines.
# ---------------------------------------------------------------------------------------------------
def loo_history(cidx: np.ndarray, y: np.ndarray, n_creators: int):
    """Return (n_other, g_other): the creator's launches and graduations EXCLUDING this row."""
    n_c = np.bincount(cidx, minlength=n_creators)
    g_c = np.bincount(cidx, weights=y.astype(np.float64), minlength=n_creators)
    n_other = n_c[cidx] - 1                       # unconditional subtraction of THIS row
    g_other = g_c[cidx] - y.astype(np.float64)    # unconditional subtraction of THIS row's own label
    return n_other, g_other


def assert_loo_is_airtight(c: Census) -> dict:
    """Empirical proof that a row's own label cannot reach its own feature.

    Flip EVERY label to 1 and recompute.  For a row whose label was already 1 nothing about it changed.
    For a row whose label was 0 its own contribution went 0 -> 1, and if LOO is airtight its own
    g_other must be unchanged by ITS OWN flip -- only its siblings' flips may move it.  We verify this
    on a construction where each creator has exactly one row flipped.
    """
    # one representative row per creator (first occurrence), flip ONLY those
    _, first = np.unique(c.cidx, return_index=True)
    y0 = c.y.copy()
    _, g0 = loo_history(c.cidx, y0, c.n_creators)
    y1 = y0.copy()
    y1[first] = 1 - y1[first]
    _, g1 = loo_history(c.cidx, y1, c.n_creators)
    # rows we flipped: their own g_other must be identical (their own label was subtracted out)
    same = bool(np.array_equal(g0[first], g1[first]))
    # rows we did NOT flip but whose creator had a flip: those MUST move (positive control)
    moved = int((g0 != g1).sum())
    return {"own_label_cannot_reach_own_feature": same,
            "flipped_rows": int(first.size),
            "rows_whose_feature_moved_because_a_SIBLING_flipped": moved,
            "positive_control_fired": moved > 0}


# ---------------------------------------------------------------------------------------------------
# Feature masks
# ---------------------------------------------------------------------------------------------------
def creator_mask(fid: str, c: Census, y: np.ndarray) -> np.ndarray:
    n_other, g_other = loo_history(c.cidx, y, c.n_creators)
    if fid == "A1":
        return g_other >= 1
    if fid == "A2":
        return g_other >= 2
    if fid == "A3":
        with np.errstate(divide="ignore", invalid="ignore"):
            rate = np.where(n_other > 0, g_other / np.maximum(n_other, 1), 0.0)
        return (n_other >= 5) & (rate >= 0.05)
    if fid == "A4":
        return n_other == 0
    if fid == "A5":
        return n_other <= 4
    if fid == "A6":
        return n_other >= 100
    raise KeyError(fid)


def static_mask(fid: str, c: Census) -> np.ndarray:
    if fid == "B1":
        i = c.platform_pk.index("FfYek5vEz23cMkWsdJwG2oa6EphsvXSHrGpdALN4g6W1")
        return c.pidx == i
    if fid == "B2":
        i = c.platform_pk.index("4Bu96XjU84XjPDSpveTVf6LYGCkfW5FK7SNkREWcEfV4")
        return c.pidx == i
    if fid == "C1":
        mt = np.array([d[2] for d in c.curve_desc])
        return mt[c.kidx] == 1
    if fid == "C2":
        rr = np.array([d[1] for d in c.curve_desc])
        return np.abs(rr[c.kidx] - 85.0) < 1e-6
    raise KeyError(fid)


def pair_concordance(cidx: np.ndarray, y: np.ndarray, n_creators: int) -> float:
    g_c = np.bincount(cidx, weights=y.astype(np.float64), minlength=n_creators)
    n_c = np.bincount(cidx, minlength=n_creators).astype(np.float64)
    return float((g_c * (g_c - 1)).sum() / (n_c * (n_c - 1)).sum())


# ---------------------------------------------------------------------------------------------------
# Fold-internal selection.  Selection sees ONLY training folds.  Scoring happens ONLY out of fold.
# ---------------------------------------------------------------------------------------------------
def _cp_lower_vec(k: np.ndarray, n: np.ndarray) -> np.ndarray:
    out = np.zeros(k.shape, dtype=np.float64)
    for i in np.nonzero((n > 0) & (k > 0))[0]:
        out[i] = cp_lower(int(k[i]), int(n[i]))
    return out


def _cp_upper_vec(k: np.ndarray, n: np.ndarray) -> np.ndarray:
    out = np.ones(k.shape, dtype=np.float64)
    for i in np.nonzero(n > 0)[0]:
        out[i] = cp_upper(int(k[i]), int(n[i]))
    return out


def _wilson_lo(k: np.ndarray, n: np.ndarray, z: float = 1.6448536269514722) -> np.ndarray:
    n = np.maximum(n, 1).astype(np.float64)
    ph = k / n
    d = 1.0 + z * z / n
    ctr = ph + z * z / (2 * n)
    rad = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return np.maximum(0.0, (ctr - rad) / d)


def _wilson_hi(k: np.ndarray, n: np.ndarray, z: float = 1.6448536269514722) -> np.ndarray:
    n = np.maximum(n, 1).astype(np.float64)
    ph = k / n
    d = 1.0 + z * z / n
    ctr = ph + z * z / (2 * n)
    rad = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return np.minimum(1.0, (ctr + rad) / d)


# The (group x fold) count tables are the whole cost of a permutation, so they are built with ONE
# bincount over a combined index and the per-group launch counts, which do not depend on y, are cached.
def _fold_tables(c: Census, gidx: np.ndarray, ngroups: int, tag: str):
    key = f"_ft_{tag}"
    ft = getattr(c, key, None)
    if ft is None:
        comb = gidx.astype(np.int64) * N_FOLDS + c.fold.astype(np.int64)
        n_gf = np.bincount(comb, minlength=ngroups * N_FOLDS).reshape(ngroups, N_FOLDS)
        n_tr = n_gf.sum(axis=1, keepdims=True) - n_gf          # (ngroups, N_FOLDS) train sizes
        ft = (comb, n_gf, n_tr, n_tr.sum(axis=0))
        setattr(c, key, ft)
    return ft


def _train_counts(c: Census, gidx: np.ndarray, ngroups: int, y: np.ndarray, tag: str):
    comb, n_gf, n_tr, n_tr_tot = _fold_tables(c, gidx, ngroups, tag)
    k_gf = np.bincount(comb, weights=y.astype(np.float64),
                       minlength=ngroups * N_FOLDS).reshape(ngroups, N_FOLDS)
    k_tr = k_gf.sum(axis=1, keepdims=True) - k_gf
    return n_tr, k_tr, k_tr.sum(axis=0), n_tr_tot


def fold_selected_mask(gidx: np.ndarray, c: Census, y: np.ndarray, direction: str,
                       ngroups: int, tag: str = "") -> np.ndarray:
    """Boolean mask, built fold by fold: a row is in the cohort iff its group was selected using ONLY
    the other four folds' labels.  Wilson bounds are used inside the selection for speed; the reported
    out-of-fold rate is then given an exact Clopper-Pearson bound by the caller."""
    tag = tag or ("p" if ngroups == c.n_platforms else "k")
    n_tr, k_tr, k_tot, n_tot = _train_counts(c, gidx, ngroups, y, tag)
    p_tr = k_tot / np.maximum(n_tot, 1)                       # (N_FOLDS,) train base rate per fold
    if direction == "up":
        sel = (n_tr >= MIN_TRAIN_N) & (_wilson_lo(k_tr, n_tr) > p_tr[None, :])
    else:
        sel = (n_tr >= MIN_TRAIN_N) & (_wilson_hi(k_tr, n_tr) < p_tr[None, :])
    return sel[gidx, c.fold]


def joint_selected_mask(c: Census, y: np.ndarray) -> np.ndarray:
    n_p, k_p, kt, nt = _train_counts(c, c.pidx, c.n_platforms, y, "p")
    n_k, k_k, _, _ = _train_counts(c, c.kidx, c.n_curvetuples, y, "k")
    p_tr = kt / np.maximum(nt, 1)
    selp = (n_p >= MIN_TRAIN_N) & (_wilson_lo(k_p, n_p) > p_tr[None, :])
    selk = (n_k >= MIN_TRAIN_N) & (_wilson_lo(k_k, n_k) > p_tr[None, :])
    return selp[c.pidx, c.fold] & selk[c.kidx, c.fold]


def build_mask(fid: str, c: Census, y: np.ndarray) -> np.ndarray:
    if fid in ("A1", "A2", "A3", "A4", "A5", "A6"):
        return creator_mask(fid, c, y)
    if fid in ("B1", "B2", "C1", "C2"):
        return static_mask(fid, c)
    if fid == "B3":
        return fold_selected_mask(c.pidx, c, y, "up", c.n_platforms, "p")
    if fid == "B4":
        return fold_selected_mask(c.pidx, c, y, "down", c.n_platforms, "p")
    if fid == "C3":
        return fold_selected_mask(c.kidx, c, y, "up", c.n_curvetuples, "k")
    if fid == "C4":
        return fold_selected_mask(c.kidx, c, y, "down", c.n_curvetuples, "k")
    if fid == "D1":
        return joint_selected_mask(c, y)
    raise KeyError(fid)


# ---------------------------------------------------------------------------------------------------
# Permutation engine
# ---------------------------------------------------------------------------------------------------
def permutation_pvalue(fid: str, c: Census, nperm: int, seed: int, two_tail_dir: str = "up"):
    """Permute the LABEL VECTOR globally (preserving N and K and every group structure) and re-run the
    ENTIRE pipeline for this feature, selection included.  Statistic = the cohort's conditional rate."""
    rng = np.random.default_rng(seed)
    if fid == "A7":
        obs = pair_concordance(c.cidx, c.y, c.n_creators)
    else:
        m = build_mask(fid, c, c.y)
        obs = float(c.y[m].mean()) if m.sum() else float("nan")
    ge = 0
    le = 0
    draws = np.empty(nperm, dtype=np.float64)
    yb = c.y.copy()
    for i in range(nperm):
        yp = rng.permutation(yb)
        if fid == "A7":
            s = pair_concordance(c.cidx, yp, c.n_creators)
        else:
            mp = build_mask(fid, c, yp)
            s = float(yp[mp].mean()) if mp.sum() else float("nan")
        draws[i] = s
        if s >= obs:
            ge += 1
        if s <= obs:
            le += 1
    p_up = (ge + 1) / (nperm + 1)
    p_dn = (le + 1) / (nperm + 1)
    return {"observed": obs, "p_perm_up": p_up, "p_perm_down": p_dn,
            "p_perm_2sided": min(1.0, 2 * min(p_up, p_dn)),
            "null_mean": float(np.nanmean(draws)), "null_sd": float(np.nanstd(draws)),
            "direction_tested": two_tail_dir, "nperm": nperm}


# ---------------------------------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------------------------------
def cohort_economics(c: Census, mask: np.ndarray, toll: float = TOLL_LETSBONK) -> dict:
    """EV(m) = (1 + prize)/m - 1 - toll, prize = E[(X_i - 1) * y_i] measured ON the cohort.

    The homogeneous form the repo uses, (1 + (X-1)p)/m - 1 - toll, is the special case X_i == X; we
    assert that identity against venues.ev_at_premium so the generalisation cannot silently drift.
    """
    n = int(mask.sum())
    if n == 0:
        return {"n": 0}
    y = c.y[mask].astype(np.float64)
    X = c.X[mask]
    ok = np.isfinite(X)
    prize = float(((X[ok] - 1.0) * y[ok]).sum() / n)
    p = float(y.mean())
    # homogeneous LetsBonk view (what venues.py computes)
    m_star_hom = V.ev_breakeven_premium("letsbonk", p, toll_round_trip=toll)
    ev1_hom = V.ev_at_premium("letsbonk", p, 1.0, toll_round_trip=toll)
    # heterogeneous view, using each curve's own measured X
    m_star_het = (1.0 + prize) / (1.0 + toll)
    ev1_het = (1.0 + prize) - 1.0 - toll
    return {"n": n, "positives": int(y.sum()), "p_cond": p,
            "mean_X_of_graduates": float((X[ok] * y[ok]).sum() / max(y[ok].sum(), 1)),
            "prize_term_measured": prize,
            "m_star_homogeneous_letsbonk": m_star_hom, "ev_at_floor_homogeneous": ev1_hom,
            "m_star_heterogeneous": m_star_het, "ev_at_floor_heterogeneous": ev1_het,
            "toll_used": toll}


def sol_window(m_star: float, q0_sol: float) -> float:
    """On a constant-product curve price scales as (Q0+q)^2, so an entry premium m corresponds to a pool
    that has already raised q = Q0*(sqrt(m)-1).  This converts an abstract break-even premium into the
    concrete question: how many SOL of the raise can be ahead of you."""
    return q0_sol * (math.sqrt(m_star) - 1.0)


# ---------------------------------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------------------------------
def describe_cohort(c: Census, mask: np.ndarray, label: str) -> dict:
    n = int(mask.sum())
    k = int(c.y[mask].sum())
    rate = k / n if n else float("nan")
    return {"feature": label, "n": n, "positives": k, "conditional_rate": rate,
            "base_rate": c.p0, "lift": (rate / c.p0) if n else float("nan"),
            "cp_lower_95": cp_lower(k, n), "cp_upper_95": cp_upper(k, n),
            "min_detectable_rate_80pct_power": min_detectable_rate(n, c.p0),
            "min_detectable_lift_80pct_power": min_detectable_rate(n, c.p0) / c.p0 if n else float("nan")}


def per_fold_table(c: Census, fid: str) -> list:
    """Out-of-fold table: for select features the mask is already OOF by construction; we report the
    per-fold split so a reader can see whether the effect is one fold's accident."""
    m = build_mask(fid, c, c.y)
    rows = []
    for f in range(N_FOLDS):
        sel = m & (c.fold == f)
        n = int(sel.sum())
        k = int(c.y[sel].sum())
        rows.append({"fold": f, "n": n, "positives": k, "rate": (k / n) if n else float("nan")})
    return rows


def run(nperm: int = N_PERM, quick: bool = False) -> dict:
    print_prereg()
    c = load_census()
    print(f"\nCENSUS: N={c.N}  graduations K={c.K}  base rate p0={c.p0:.8f}  "
          f"creators={c.n_creators}  platforms={c.n_platforms}  curve tuples={c.n_curvetuples}")

    loo_proof = assert_loo_is_airtight(c)
    print("\nLEAVE-ONE-OUT PROOF (not a claim, a check):")
    for k, v in loo_proof.items():
        print(f"   {k}: {v}")
    if not loo_proof["own_label_cannot_reach_own_feature"]:
        raise SystemExit("REFUSED: leave-one-out is not airtight; no result is reportable.")
    if not loo_proof["positive_control_fired"]:
        raise SystemExit("REFUSED: LOO positive control did not fire; the check proves nothing.")

    # ---------------- POWER, BEFORE RESULTS ----------------
    print("\n" + "=" * 102)
    print("POWER STATEMENT -- computed BEFORE any conditional rate is reported")
    print("=" * 102)
    print(f"  base rate p0 = {c.p0:.6f} on N = {c.N:,} curves with K = {c.K:,} graduations")
    print(f"  {'cohort n':>12s}  {'min detectable rate':>20s}  {'= lift':>8s}   (alpha=0.05 one-sided, power=0.80)")
    power_rows = []
    for n in (1_000, 5_000, 20_000, 100_000, 200_000, 600_000, 1_000_000):
        mdr = min_detectable_rate(n, c.p0)
        power_rows.append({"n": n, "min_detectable_rate": mdr, "min_detectable_lift": mdr / c.p0})
        print(f"  {n:12,d}  {mdr:20.6f}  {mdr/c.p0:8.3f}")
    _mdl = {r["n"]: r["min_detectable_lift"] for r in power_rows}
    print(f"  Read: a cohort of 1,000 curves can only resolve a lift of {_mdl[1000]:.3f} or larger; "
          f"20,000 resolves {_mdl[20000]:.3f};")
    print(f"  100,000 resolves {_mdl[100000]:.3f}.  Below a few thousand curves this census settles "
          f"nothing at small lifts.")

    # ---------------- ECONOMIC THRESHOLD, BEFORE RESULTS ----------------
    print("\n" + "=" * 102)
    print("ECONOMIC THRESHOLD -- also fixed before results, from venues.py")
    print("=" * 102)
    X = V.graduation_multiple("letsbonk")
    toll = V.VENUES["letsbonk"].toll_round_trip
    p_be = toll / (X - 1.0)
    m_star_base = V.ev_breakeven_premium("letsbonk", c.p0, toll_round_trip=toll)
    print(f"  X={X:.4f}  toll_round_trip={toll}  (both MEASURED, venues.py)")
    print(f"  EV(m) = (1 + (X-1)p)/m - 1 - toll        m* = (1 + (X-1)p)/(1+toll)")
    print(f"  break-even p AT THE FLOOR (m=1): p_be = toll/(X-1) = {p_be:.6f} = {p_be*100:.4f}%")
    print(f"  the corpus base rate {c.p0:.6f} ALREADY clears that by {c.p0/p_be:.2f}x --")
    print(f"  so the binding constraint is NOT p, it is the entry premium m.")
    print(f"  corpus m* = {m_star_base:.5f}: at the dominant LetsBonk curve (Q0=30.0009 SOL) that is a")
    print(f"  window of {sol_window(m_star_base, 30.000852951):.3f} SOL of raise ahead of you.")
    print(f"  THE QUESTION THIS TEST MUST ANSWER: does any create-time cohort widen that window enough")
    print(f"  to matter, given b11a measured median create->graduation of 25s and 44% same-slot?")

    # ---------------- FEATURES ----------------
    print("\n" + "=" * 102)
    print("RESULTS")
    print("=" * 102)
    results, pvals = {}, {}
    order = [f[0] for f in PREREG_FEATURES]
    meta = {f[0]: f for f in PREREG_FEATURES}
    np_ = nperm if not quick else 100
    for fid in order:
        _, fam, kind, contam, desc = meta[fid]
        t0 = time.time()
        if fid == "A7":
            obs = pair_concordance(c.cidx, c.y, c.n_creators)
            pr = permutation_pvalue(fid, c, np_, SEED)
            row = {"feature": fid, "family": fam, "kind": kind, "future_contaminated": contam,
                   "description": desc,
                   "same_creator_both_grad_pair_rate": obs, "p0_squared": c.p0 ** 2,
                   "concordance_lift": obs / (c.p0 ** 2), "perm": pr}
            print(f"\n[{fid}] {desc}")
            print(f"      same-creator both-graduate pair rate = {obs:.10f}   p0^2 = {c.p0**2:.10f}   "
                  f"lift = {obs/(c.p0**2):.4f}")
            print(f"      permutation null mean {pr['null_mean']:.10f} sd {pr['null_sd']:.2e}  "
                  f"p_up={pr['p_perm_up']:.4f} p_down={pr['p_perm_down']:.4f}")
            pvals[fid] = pr["p_perm_up"]
            results[fid] = row
            continue
        mask = build_mask(fid, c, c.y)
        d = describe_cohort(c, mask, fid)
        econ = cohort_economics(c, mask, toll=toll)
        pr = permutation_pvalue(fid, c, np_, SEED)
        folds = per_fold_table(c, fid)
        row = {"feature": fid, "family": fam, "kind": kind, "future_contaminated": contam,
               "description": desc, **d, "economics": econ, "perm": pr, "per_fold": folds,
               "seconds": round(time.time() - t0, 1)}
        pvals[fid] = pr["p_perm_up"]
        results[fid] = row
        flag = "  [FUTURE-CONTAMINATED -> bound only]" if contam else ""
        print(f"\n[{fid}] {desc}{flag}")
        print(f"      n={d['n']:,}  positives={d['positives']:,}  rate={d['conditional_rate']:.6f}  "
              f"base={c.p0:.6f}  LIFT={d['lift']:.4f}")
        print(f"      CP95 [{d['cp_lower_95']:.6f}, {d['cp_upper_95']:.6f}]   "
              f"min detectable lift at this n = {d['min_detectable_lift_80pct_power']:.3f}")
        print(f"      permutation p_up={pr['p_perm_up']:.4f}  (null mean {pr['null_mean']:.6f} "
              f"sd {pr['null_sd']:.6f}, {pr['nperm']} draws)")
        if d["n"]:
            print(f"      per-fold rates: " + "  ".join(
                f"f{r['fold']}:{r['rate']:.5f}(n={r['n']:,})" for r in folds))
            print(f"      prize term (measured, per-curve X) = {econ['prize_term_measured']:.6f}  "
                  f"m* = {econ['m_star_heterogeneous']:.5f}  "
                  f"window = {sol_window(econ['m_star_heterogeneous'], 30.000852951):.3f} SOL")

    # ---------------- MULTIPLICITY ----------------
    adj = holm(pvals)
    print("\n" + "=" * 102)
    print("FAMILY-WISE CORRECTION -- Holm-Bonferroni across all 16 tests")
    print("=" * 102)
    print(f"  {'feat':5s} {'p_perm':>9s} {'p_holm':>9s}  {'lift':>8s}  {'CP-lo>p0?':>10s}  verdict")
    survivors = []
    for fid in order:
        r = results[fid]
        p = pvals[fid]
        a = adj[fid]
        lift = r.get("lift", r.get("concordance_lift", float("nan")))
        cplo = r.get("cp_lower_95", float("nan"))
        stat_ok = (not math.isnan(cplo)) and cplo > c.p0
        sig = a < 0.05
        if r["future_contaminated"]:
            verdict = "BOUND ONLY (unknowable at create time)"
        elif fid == "A7":
            verdict = "omnibus: " + ("creator heterogeneity DETECTED" if sig and lift > 1
                                     else "NO creator heterogeneity")
        elif stat_ok and sig:
            verdict = "passes (1)+(2) -> economics decides"
            survivors.append(fid)
        elif lift < 1 and a < 0.05:
            verdict = "significant NEGATIVE screen"
        else:
            verdict = "dead"
        print(f"  {fid:5s} {p:9.4f} {a:9.4f}  {lift:8.4f}  {str(stat_ok):>10s}  {verdict}")
        r["p_holm"] = a
        r["verdict_stage12"] = verdict

    # ---------------- ECONOMICS OF SURVIVORS ----------------
    print("\n" + "=" * 102)
    print("ECONOMICS -- the only stage that matters")
    print("=" * 102)
    print(f"  corpus:  p={c.p0:.6f}  m*={m_star_base:.5f}  window={sol_window(m_star_base, 30.000852951):.3f} SOL of raise")
    econ_rows = []
    for fid in order:
        r = results[fid]
        e = r.get("economics")
        if not e or not e.get("n"):
            continue
        m_star = e["m_star_heterogeneous"]
        w = sol_window(m_star, 30.000852951)
        widen = m_star / m_star_base
        econ_rows.append({"feature": fid, "n": e["n"], "p_cond": e["p_cond"],
                          "prize": e["prize_term_measured"], "m_star": m_star,
                          "window_sol": w, "widening_vs_corpus": widen,
                          "future_contaminated": r["future_contaminated"]})
    econ_rows.sort(key=lambda x: -x["m_star"])
    print(f"  {'feat':5s} {'n':>10s} {'p_cond':>9s} {'prize':>8s} {'m*':>8s} {'window SOL':>11s} {'x corpus':>9s}")
    for e in econ_rows:
        tag = " <- FUTURE-CONTAMINATED" if e["future_contaminated"] else ""
        print(f"  {e['feature']:5s} {e['n']:10,d} {e['p_cond']:9.6f} {e['prize']:8.4f} "
              f"{e['m_star']:8.5f} {e['window_sol']:11.3f} {e['widening_vs_corpus']:9.3f}{tag}")

    report = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prereg": {"seed": SEED, "nperm": np_, "folds": N_FOLDS, "alpha": ALPHA,
                   "min_train_n": MIN_TRAIN_N, "features": PREREG_FEATURES,
                   "loo_rule": PREREG_LOO_RULE, "decision_rule": PREREG_DECISION_RULE,
                   "honesty": PREREG_HONESTY},
        "census": {"N": c.N, "K": c.K, "p0": c.p0, "creators": c.n_creators,
                   "platforms": c.n_platforms, "curve_tuples": c.n_curvetuples},
        "loo_proof": loo_proof,
        "power": power_rows,
        "economic_threshold": {"X_letsbonk": X, "toll_round_trip": toll, "p_breakeven_at_floor": p_be,
                               "corpus_m_star": m_star_base,
                               "corpus_window_sol": sol_window(m_star_base, 30.000852951)},
        "results": results,
        "holm": adj,
        "economics_table": econ_rows,
        "survivors_stage12": survivors,
    }
    with open(OUT, "w") as fh:
        json.dump(report, fh, indent=1, default=float)
    print(f"\n[written] {OUT}")
    return report


# ---------------------------------------------------------------------------------------------------
# Supporting descriptive views (no inference, just the counts a reader will ask for)
# ---------------------------------------------------------------------------------------------------
def groups(kind: str, top: int = 25, min_n: int = 1000):
    c = load_census()
    gidx = c.pidx if kind == "platform" else c.kidx
    ng = c.n_platforms if kind == "platform" else c.n_curvetuples
    n = np.bincount(gidx, minlength=ng)
    k = np.bincount(gidx, weights=c.y.astype(np.float64), minlength=ng).astype(np.int64)
    keep = np.nonzero(n >= min_n)[0]
    rate = k[keep] / n[keep]
    order = keep[np.argsort(-rate)]
    print(f"{kind} groups with n>={min_n}, sorted by graduation rate.  corpus p0={c.p0:.6f}")
    print(f"{'group':<50s} {'n':>9s} {'grads':>7s} {'rate':>10s} {'lift':>7s} {'CPlo':>9s} {'m*':>8s}")
    rows = []
    for i in order[:top]:
        nn, kk = int(n[i]), int(k[i])
        r = kk / nn
        lo = cp_lower(kk, nn)
        sel = gidx == i
        e = cohort_economics(c, sel)
        name = c.platform_pk[i] if kind == "platform" else str(c.curve_desc[i])
        print(f"{name:<50s} {nn:9,d} {kk:7,d} {r:10.6f} {r/c.p0:7.3f} {lo:9.6f} "
              f"{e['m_star_heterogeneous']:8.4f}")
        rows.append({"group": name, "n": nn, "grads": kk, "rate": r, "lift": r / c.p0,
                     "cp_lower": lo, "m_star": e["m_star_heterogeneous"],
                     "X": e["mean_X_of_graduates"]})
    return rows


def first_launch_bounds():
    """The one question this table cannot answer, bounded rather than guessed.

    The deployable version of the creator feature is 'has this address ever launched BEFORE?', which is
    knowable at create time.  Its rate is not directly measurable here because there is no ordering, so:
      hard bounds  : first-launch graduations lie in [0, #creators with >=1 graduation]
      point estimate under WITHIN-CREATOR EXCHANGEABILITY (graduation independent of position in the
      creator's own sequence): sum_c G_c / N_c
    """
    c = load_census()
    n_c = np.bincount(c.cidx, minlength=c.n_creators).astype(np.float64)
    g_c = np.bincount(c.cidx, weights=c.y.astype(np.float64), minlength=c.n_creators)
    C = c.n_creators
    hi = float((g_c >= 1).sum())
    est = float((g_c / n_c).sum())
    out = {
        "creators": C,
        "first_launch_curves": C,
        "later_launch_curves": c.N - C,
        "first_launch_grads_hard_lower": 0.0,
        "first_launch_grads_hard_upper": hi,
        "first_launch_grads_exchangeable_estimate": est,
        "p_first_hard_range": [0.0, hi / C],
        "p_first_exchangeable": est / C,
        "p_later_exchangeable": (c.K - est) / (c.N - C),
        "lift_first_exchangeable": (est / C) / c.p0,
        "lift_later_exchangeable": ((c.K - est) / (c.N - C)) / c.p0,
    }
    e_first = (1.0 + (X_LETSBONK - 1.0) * out["p_first_exchangeable"])
    out["m_star_first_exchangeable"] = e_first / (1.0 + TOLL_LETSBONK)
    out["window_sol_first_exchangeable"] = sol_window(out["m_star_first_exchangeable"], 30.000852951)
    print(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------------------------------
# Liveness probe (bounded, free public RPC).  Answers: is a high-p platform still launching coins?
# ---------------------------------------------------------------------------------------------------
def _rpc(method: str, params: list, timeout: int = 20):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def freshness(platforms: list[str], per_platform: int = 12, sleep_s: float = 0.45,
              max_calls: int = 400, untouched: bool = True) -> dict:
    """For a sample of pools per platform, ask for the pool's MOST RECENT signature and its blockTime.

    With untouched=True the sample is restricted to curves that NEVER received a trade
    (graduated=0 and real_quote==0, 84.4% of all funding curves).  Such a pool's only transaction is its
    create, so its newest signature IS its create time and the sample measures WHEN THIS PLATFORM WAS
    LAST LAUNCHING COINS.  With untouched=False the newest signature is the pool's last trade and the
    sample measures liveness of activity instead.  Bounded by max_calls."""
    con = sqlite3.connect(DB)
    pk2id = {p: i for i, p in con.execute("select id, pk from pubkeys")}
    rng = random.Random(SEED)
    out, calls = {}, 0
    where = " and graduated=0 and o_real_quote=0" if untouched else ""
    for pkey in platforms:
        pid = pk2id.get(pkey)
        if pid is None:
            out[pkey] = {"error": "platform not in census"}
            continue
        pools = [r[0] for r in con.execute(
            f"select pool from pools where platform_config=?{where} limit 5000", (pid,))]
        if not pools:
            pools = [r[0] for r in con.execute(
                "select pool from pools where platform_config=? limit 5000", (pid,))]
        rng.shuffle(pools)
        times, errs = [], 0
        for pool in pools[:per_platform]:
            if calls >= max_calls:
                break
            calls += 1
            try:
                j = _rpc("getSignaturesForAddress", [pool, {"limit": 1}])
                v = (j.get("result") or [])
                if v and v[0].get("blockTime"):
                    times.append(int(v[0]["blockTime"]))
                else:
                    errs += 1
            except Exception:
                errs += 1
            time.sleep(sleep_s)
        if times:
            times.sort()
            out[pkey] = {"sampled": len(times), "errors": errs,
                         "newest_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(times[-1])),
                         "oldest_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(times[0])),
                         "median_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                     time.gmtime(times[len(times) // 2])),
                         "days_since_newest": round((time.time() - times[-1]) / 86400.0, 2),
                         "days_since_median": round((time.time() - times[len(times) // 2]) / 86400.0, 2)}
        else:
            out[pkey] = {"sampled": 0, "errors": errs, "note": "no blockTime returned"}
        print(f"  {pkey[:44]:46s} {json.dumps(out[pkey])}")
    con.close()
    with open(FRESH, "w") as fh:
        json.dump({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "rpc": RPC, "calls": calls, "per_platform": per_platform, "platforms": out}, fh, indent=1)
    print(f"[written] {FRESH}  ({calls} RPC calls)")
    return out


def creator_oof(rules: list | None = None) -> dict:
    """THE HEADLINE TEST, EVALUATED WITH NOTHING BUT TRAINING-FOLD HISTORY.

    For a curve in test fold f the creator's launch count and graduation count are computed from that
    creator's curves in the four TRAINING folds only.  So the score of a curve is untouched by its own
    label AND by every other label in its own fold -- a strictly stronger guarantee than leave-one-out.
    The rule is then applied and the curve's own outcome scored.  Nothing is selected on the test fold.

    Reported per rule: pooled out-of-fold n, positives, rate, lift, exact Clopper-Pearson one-sided lower
    bound, the five per-fold rates, and the economics at both the point estimate and the lower bound.
    """
    c = load_census()
    y = c.y.astype(np.float64)
    n_all = np.bincount(c.cidx, minlength=c.n_creators)
    g_all = np.bincount(c.cidx, weights=y, minlength=c.n_creators)
    X = V.graduation_multiple("letsbonk")
    toll = V.VENUES["letsbonk"].toll_round_trip
    rules = rules or [
        ("count", 1, 100, 1), ("count", 1, 20, 1), ("count", 1, 20, 2), ("count", 1, 100, 2),
        ("rate", 5, 0.02, None), ("rate", 5, 0.05, None), ("rate", 5, 0.10, None),
        ("rate", 5, 0.20, None), ("rate", 10, 0.05, None),
    ]
    print("STRICT OUT-OF-FOLD CREATOR TEST -- creator history from the 4 training folds only")
    print(f"corpus p0={c.p0:.6f}   X={X:.4f}   toll={toll}   "
          f"corpus m*={V.ev_breakeven_premium('letsbonk', c.p0, toll_round_trip=toll):.4f}\n")
    out = []
    for rule in rules:
        tn = tk = 0
        per = []
        for f in range(N_FOLDS):
            te = c.fold == f
            n_te = np.bincount(c.cidx[te], minlength=c.n_creators)
            g_te = np.bincount(c.cidx[te], weights=y[te], minlength=c.n_creators)
            n_tr = (n_all - n_te)[c.cidx]
            g_tr = (g_all - g_te)[c.cidx]
            if rule[0] == "count":
                _, lo, hi, gmin = rule
                m = te & (n_tr >= lo) & (n_tr <= hi) & (g_tr >= gmin)
                lab = f"train launches {lo}-{hi} and >={gmin} train graduation(s)"
            else:
                _, minl, thr, _ = rule
                with np.errstate(divide="ignore", invalid="ignore"):
                    rt = np.where(n_tr > 0, g_tr / np.maximum(n_tr, 1), 0.0)
                m = te & (n_tr >= minl) & (rt >= thr)
                lab = f"train graduation rate >= {thr:.0%} over >= {minl} train launches"
            n, k = int(m.sum()), int(c.y[m].sum())
            tn += n
            tk += k
            per.append({"fold": f, "n": n, "k": k, "rate": (k / n) if n else None})
        r = tk / tn if tn else float("nan")
        lo_cb = cp_lower(tk, tn)
        ms = (1.0 + (X - 1.0) * r) / (1.0 + toll)
        ms_lo = (1.0 + (X - 1.0) * lo_cb) / (1.0 + toll)
        row = {"rule": lab, "oof_n": tn, "oof_positives": tk, "oof_rate": r, "lift": r / c.p0,
               "cp_lower_95": lo_cb, "lift_at_cp_lower": lo_cb / c.p0,
               "min_detectable_lift_here": min_detectable_rate(tn, c.p0) / c.p0,
               "m_star": ms, "m_star_at_cp_lower": ms_lo,
               "window_sol": sol_window(ms, 30.000852951),
               "window_sol_at_cp_lower": sol_window(ms_lo, 30.000852951),
               "per_fold": per}
        out.append(row)
        print(f"{lab:52s} n={tn:7,d} k={tk:5,d} rate={r:.6f} lift={r/c.p0:6.2f} "
              f"CPlo={lo_cb:.6f} m*={ms:.3f} (CPlo {ms_lo:.3f}) window={sol_window(ms, 30.000852951):5.2f} SOL")
        print("     per-fold rate: " + "  ".join(
            f"f{q['fold']}:{(q['rate'] or 0):.5f}(n={q['n']:,})" for q in per))
    path = os.path.join(_REPO, "research", "launchpads", "census", "provenance_creator_oof.json")
    with open(path, "w") as fh:
        json.dump({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "p0": c.p0, "X": X, "toll": toll, "rules": out}, fh, indent=1, default=float)
    print(f"[written] {path}")
    return {"rules": out}


def stratified_creator_test(nperm: int = 1000) -> dict:
    """THE CONFOUND-FREE FORM OF H1.

    The raw creator signal is entangled with launch count: creators with more launches graduate less
    often, so any 'creator has other graduations' cohort is also a 'creator is prolific' cohort.  This
    test removes the confound by conditioning on launch count.

    Every launch of a given creator shares the same n_other = N_c - 1, so a launch-count stratum is a
    union of WHOLE creators.  That makes the correct null exact and easy: shuffle the labels WITHIN the
    stratum.  That preserves the stratum's launch counts and its total graduations, destroys only the
    assignment of graduations to creators, and -- because a creator's launches never leave their own
    stratum -- it is a complete resampling of the quantity under test.

    Statistic per stratum: P(graduate | creator has >=1 OTHER graduation) inside the stratum.
    """
    c = load_census()
    n_other, g_other = loo_history(c.cidx, c.y, c.n_creators)
    buckets = [(1, 1), (2, 2), (3, 5), (6, 20), (21, 100), (101, 1000), (1001, 10 ** 9)]
    rng = np.random.default_rng(SEED)
    print("STRATIFIED CREATOR TEST -- H1 with the launch-count confound removed")
    print("labels are shuffled WITHIN each stratum, so launch count is held fixed by construction\n")
    print(f"{'n_other':>12s} {'curves':>10s} {'grads':>7s} {'p_strat':>9s} | "
          f"{'n|g>=1':>9s} {'grads':>7s} {'rate':>9s} {'lift':>7s} {'CPlo':>9s} {'p_perm':>8s} {'null':>9s}")
    rows = []
    for lo, hi in buckets:
        S = (n_other >= lo) & (n_other <= hi)
        nS, kS = int(S.sum()), int(c.y[S].sum())
        if nS == 0:
            continue
        pS = kS / nS
        ys = c.y[S].astype(np.int8)
        cs = c.cidx[S]
        # relabel creators densely inside the stratum so bincount stays small
        uc, cs = np.unique(cs, return_inverse=True)
        ncre = uc.size

        def stat(yv):
            g = np.bincount(cs, weights=yv.astype(np.float64), minlength=ncre)[cs] - yv
            m = g >= 1
            if not m.any():
                return float("nan"), 0, 0
            return float(yv[m].mean()), int(m.sum()), int(yv[m].sum())

        obs, nm, km = stat(ys)
        draws = np.empty(nperm)
        ge = 0
        for i in range(nperm):
            sp, _, _ = stat(rng.permutation(ys))
            draws[i] = sp
            if not math.isnan(sp) and not math.isnan(obs) and sp >= obs:
                ge += 1
        pperm = (ge + 1) / (nperm + 1)
        cplo = cp_lower(km, nm)
        lab = f"{lo}-{hi}" if lo != hi else f"{lo}"
        if hi >= 10 ** 9:
            lab = f"{lo}+"
        print(f"{lab:>12s} {nS:10,d} {kS:7,d} {pS:9.6f} | {nm:9,d} {km:7,d} {obs:9.6f} "
              f"{obs/pS:7.4f} {cplo:9.6f} {pperm:8.4f} {np.nanmean(draws):9.6f}")
        rows.append({"stratum_n_other": lab, "curves": nS, "grads": kS, "p_stratum": pS,
                     "n_with_other_grad": nm, "grads_in_cohort": km, "rate": obs,
                     "lift_within_stratum": obs / pS if pS else None, "cp_lower": cplo,
                     "p_perm_within_stratum": pperm, "perm_null_mean": float(np.nanmean(draws)),
                     "perm_null_sd": float(np.nanstd(draws)), "nperm": nperm})
    adj = holm({r["stratum_n_other"]: r["p_perm_within_stratum"] for r in rows})
    for r in rows:
        r["p_holm_across_strata"] = adj[r["stratum_n_other"]]
    print("\nHolm across strata: " + "  ".join(f"{k}:{v:.4f}" for k, v in adj.items()))
    path = os.path.join(_REPO, "research", "launchpads", "census",
                        "provenance_at_power_stratified.json")
    with open(path, "w") as fh:
        json.dump({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "seed": SEED, "nperm": nperm, "strata": rows}, fh, indent=1, default=float)
    print(f"[written] {path}")
    return {"strata": rows}


def refold_by_creator(c: Census) -> Census:
    """Replace the pool-hashed folds with CREATOR-BLOCKED folds.

    Why this exists: sha256(pool)%5 scatters one creator's launches across all five folds, so a cohort
    whose lift is really a handful of prolific creators can still look out-of-fold clean -- the creator
    is in the training folds AND the test fold.  Blocking by creator removes that path entirely.  The
    partition is a deterministic hash of the creator index, so it is fixed and outcome-independent.
    """
    fold = np.fromiter((int(hashlib.sha256(str(int(i)).encode()).hexdigest()[:8], 16) % N_FOLDS
                        for i in range(c.n_creators)), dtype=np.int8, count=c.n_creators)[c.cidx]
    d = Census(y=c.y, cidx=c.cidx, pidx=c.pidx, kidx=c.kidx, fold=fold, X=c.X,
               n_creators=c.n_creators, n_platforms=c.n_platforms, n_curvetuples=c.n_curvetuples,
               platform_pk=c.platform_pk, curve_desc=c.curve_desc)
    return d


def concentration(c: Census, mask: np.ndarray) -> dict:
    """How much of a cohort's graduation count sits with its single busiest creator."""
    idx = c.cidx[mask]
    yy = c.y[mask].astype(np.float64)
    if idx.size == 0:
        return {}
    g = np.bincount(idx, weights=yy, minlength=c.n_creators)
    n = np.bincount(idx, minlength=c.n_creators)
    tot = g.sum()
    return {"distinct_creators": int((n > 0).sum()),
            "top_creator_share_of_grads": float(g.max() / tot) if tot else 0.0,
            "top5_creator_share_of_grads": float(np.sort(g)[-5:].sum() / tot) if tot else 0.0}


def blocked(nperm: int = 300):
    """Robustness: re-run every fold-selected feature under creator-blocked folds."""
    c = load_census()
    b = refold_by_creator(c)
    print(f"CREATOR-BLOCKED FOLDS.  corpus p0={c.p0:.6f}, N={c.N:,}, K={c.K:,}")
    print("A selected cohort that survives here is not an artefact of a creator straddling folds.")
    print(f"{'feat':5s} {'pool-folds n':>13s} {'rate':>9s} {'lift':>7s} | "
          f"{'creator-folds n':>15s} {'rate':>9s} {'lift':>7s} {'CPlo':>9s} {'p_perm':>8s}  concentration")
    out = {}
    for fid in ("B3", "B4", "C3", "C4", "D1"):
        m0 = build_mask(fid, c, c.y)
        n0, k0 = int(m0.sum()), int(c.y[m0].sum())
        m1 = build_mask(fid, b, b.y)
        n1, k1 = int(m1.sum()), int(b.y[m1].sum())
        r1 = (k1 / n1) if n1 else float("nan")
        pr = permutation_pvalue(fid, b, nperm, SEED)
        con = concentration(c, m1)
        lo = cp_lower(k1, n1)
        out[fid] = {"pool_folds": {"n": n0, "k": k0, "rate": (k0 / n0) if n0 else None},
                    "creator_folds": {"n": n1, "k": k1, "rate": r1, "cp_lower": lo,
                                      "lift": r1 / c.p0 if n1 else None},
                    "perm": pr, "concentration": con,
                    "economics": cohort_economics(b, m1)}
        print(f"{fid:5s} {n0:13,d} {(k0/n0) if n0 else 0:9.6f} {((k0/n0)/c.p0) if n0 else 0:7.3f} | "
              f"{n1:15,d} {r1:9.6f} {r1/c.p0:7.3f} {lo:9.6f} {pr['p_perm_up']:8.4f}  "
              f"{json.dumps(con)}")
    path = os.path.join(_REPO, "research", "launchpads", "census",
                        "provenance_at_power_creatorblocked.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    print(f"[written] {path}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("prereg")
    r = sub.add_parser("run")
    r.add_argument("--nperm", type=int, default=N_PERM)
    r.add_argument("--quick", action="store_true")
    g = sub.add_parser("groups")
    g.add_argument("kind", choices=["platform", "curve"])
    g.add_argument("--top", type=int, default=25)
    g.add_argument("--min-n", type=int, default=1000)
    sub.add_parser("firstlaunch")
    sub.add_parser("creator_oof")
    st = sub.add_parser("stratified")
    st.add_argument("--nperm", type=int, default=1000)
    bl = sub.add_parser("blocked")
    bl.add_argument("--nperm", type=int, default=300)
    f = sub.add_parser("freshness")
    f.add_argument("platforms", nargs="+")
    f.add_argument("--per-platform", type=int, default=12)
    f.add_argument("--max-calls", type=int, default=400)
    f.add_argument("--traded", action="store_true", help="sample traded pools (liveness) instead of untouched (create time)")
    a = ap.parse_args(argv)
    if a.cmd == "prereg":
        print_prereg()
    elif a.cmd == "groups":
        groups(a.kind, a.top, a.min_n)
    elif a.cmd == "firstlaunch":
        first_launch_bounds()
    elif a.cmd == "creator_oof":
        creator_oof()
    elif a.cmd == "stratified":
        stratified_creator_test(a.nperm)
    elif a.cmd == "blocked":
        blocked(a.nperm)
    elif a.cmd == "freshness":
        freshness(a.platforms, a.per_platform, max_calls=a.max_calls, untouched=not a.traded)
    else:
        run(nperm=(a.nperm if a.cmd == "run" else N_PERM),
            quick=(a.quick if a.cmd == "run" else False))


if __name__ == "__main__":
    main()
