#!/usr/bin/env python3
"""
VOLUME-SPIKE EXHAUSTION -- pre-registered event study on the survivorship-complete
Binance USD-M perp daily panel (919 symbols incl. delisted names, 2020-01-01..2026-07-31).

HYPOTHESIS
  An extreme symbol-relative volume spike on an UP day marks distribution / exhaustion,
  so the market-controlled forward return over the next few days is NEGATIVE (short edge).

METHOD (fixed order, stop at first failure)
  GATE 1 COVERAGE  -> GATE 2 POWER (computed BEFORE any effect is read) -> GATE 3 EFFECT
  -> ECONOMICS.

CONTROL (mandatory): same-day cross-sectional MEDIAN log return of the surviving universe
is subtracted from every symbol-day. This is the control that inverted the unlock-cliff
result on 2026-09-03; it removes alt-sector beta, which is the usual explanation for a
"chart rule" that looks like it works.

PAPER-ONLY RESEARCH. FREE DATA ONLY. New file; edits nothing in arena/.
"""
import csv
import os
import sys
import numpy as np

PANEL = "/home/anont/meme/research/data/t23_cache/panel/perp_daily.csv"

# ----------------------------------------------------------------------------------
# PRE-REGISTRATION -- printed and frozen BEFORE a single byte of data is read.
# ----------------------------------------------------------------------------------
SEED = 20260903
BOOT = 5000

# -- event definition (frozen)
Z_THRESH        = 3.0      # trailing volume z-score threshold
VOL_WINDOW      = 30       # trailing calendar days for the volume baseline (STRICTLY t-30..t-1)
VOL_MIN_OBS     = 25       # min valid obs inside that window
MIN_MED_QVOL    = 1_000_000.0   # min trailing-median quote volume (USD/day) -> tradeable names only
MIN_UNIVERSE    = 30       # min symbols alive on a day for its cross-sectional median to be usable
HORIZONS        = (1, 3, 7)
PRIMARY_H       = 3        # ONE primary endpoint; 1d and 7d are secondary/robustness
PRIMARY_ARM     = "UP"     # same-day RAW return > 0  (what a chart rule actually sees)
PRIMARY_DIR     = -1       # predicted sign of the market-controlled forward return

# -- GATE 1
MIN_EVENTS      = 500
MIN_CLUSTERS    = 100      # distinct event DATES

# -- GATE 2
CLAIMED_EFFECT  = 0.020    # 2.00% = the plausible 3-day exhaustion reversal being claimed
MDE_KILL_LINE   = CLAIMED_EFFECT / 2.0   # MDE must be < 1.00% or the test cannot see the claim
ICC             = 0.30     # conservative intra-date correlation
ALPHA           = 0.05     # one-sided
POWER           = 0.80
Z_ALPHA, Z_BETA = 1.6449, 0.8416

# -- GATE 3
PSIGN_GATE      = 0.975    # cluster-bootstrap one-sided; equivalently 95% CI excludes 0

# -- ECONOMICS
ROUND_TRIP_BP   = 24.1     # this repo's own MEASURED two-perp round trip; alt perps are worse
EDGE_COST_MIN   = 2.0      # net edge must be >= 2x the toll to be worth carrying


def banner(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def print_prereg():
    banner("PRE-REGISTRATION (frozen before any data is read)")
    print(f"""HYPOTHESIS
  Volume-spike exhaustion. Event = trailing volume z >= {Z_THRESH} over a strictly-causal
  {VOL_WINDOW}d window (t-{VOL_WINDOW}..t-1, >= {VOL_MIN_OBS} obs), on a symbol whose trailing MEDIAN quote
  volume >= ${MIN_MED_QVOL:,.0f}/day. Events split by SAME-DAY RAW return sign.
  PRIMARY endpoint: arm = {PRIMARY_ARM} (same-day return > 0), horizon = {PRIMARY_H}d,
  predicted direction = {'NEGATIVE' if PRIMARY_DIR < 0 else 'POSITIVE'} market-controlled forward return.
  Horizons {HORIZONS} and the DOWN arm are SECONDARY (reported, not gated -- family size 6).

CONTROL
  Every symbol-day log return has the SAME-DAY CROSS-SECTIONAL MEDIAN log return of the
  surviving universe subtracted (universe must have >= {MIN_UNIVERSE} live symbols that day).
  Forward h-day effect = sum of the next h daily EXCESS log returns; an event is dropped
  if ANY of its h forward days is missing (delisting / halt) -- that count is reported.

GATE 1 COVERAGE  (declared BEFORE counting)
  PASS requires the PRIMARY arm to have >= {MIN_EVENTS} events across >= {MIN_CLUSTERS} distinct event DATES.
  Otherwise KILL_COVERAGE.

GATE 2 POWER  (computed BEFORE any effect is read)
  Claimed / plausible exhaustion effect = {CLAIMED_EFFECT*100:.2f}% over {PRIMARY_H}d.
  KILL LINE: MDE (alpha={ALPHA} one-sided, power={POWER}) must be < {MDE_KILL_LINE*100:.2f}%.
  Residual sd = sd of the market-controlled {PRIMARY_H}d forward returns of the event sample.
  Design effect = 1 + (m_bar - 1) * ICC, ICC = {ICC}, m_bar = sum(m_i^2)/sum(m_i)
  (size-weighted mean cluster size -- conservative under unequal date clusters).
  n_eff = n / deff.   MDE = (z_a + z_b) * sd / sqrt(n_eff).
  If MDE >= the kill line -> KILL_POWER, and the effect is NOT read.

GATE 3 EFFECT  (only if 1 and 2 pass)
  Cluster bootstrap by event DATE, {BOOT} draws, fixed seed {SEED}.
  PASS requires P(mean has the predicted sign) >= {PSIGN_GATE} (95% CI excludes 0 in that
  direction). Otherwise KILL_EFFECT.

ECONOMICS
  Net = |gross effect| - {ROUND_TRIP_BP} bp measured round trip. edge/cost = |gross| / {ROUND_TRIP_BP} bp.
  Requires net > 0 AND edge/cost >= {EDGE_COST_MIN:.1f}. Otherwise KILL_ECONOMICS.

NO THRESHOLD IS TUNED AFTER SEEING RESULTS. A single run, confirmatory.""")


# ----------------------------------------------------------------------------------
def load_panel():
    syms, days = set(), set()
    rows = []
    with open(PANEL) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            s, d = row[0], int(row[1])
            try:
                c, q = float(row[2]), float(row[3])
            except ValueError:
                continue
            if not (c > 0):
                continue
            syms.add(s); days.add(d)
            rows.append((s, d, c, q))
    sl = sorted(syms)
    d0, d1 = min(days), max(days)
    D = (d1 - d0) // 86_400_000 + 1
    si = {s: i for i, s in enumerate(sl)}
    S = len(sl)
    C = np.full((S, D), np.nan)
    Q = np.full((S, D), np.nan)
    for s, d, c, q in rows:
        i = si[s]; j = (d - d0) // 86_400_000
        C[i, j] = c
        Q[i, j] = q
    return sl, d0, C, Q


def ms_to_date(ms):
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()


def cluster_bootstrap(vals, dates, direction, rng):
    """Resample event DATES with replacement; recompute the mean over all events on the
    sampled dates. Returns (boot means array)."""
    uniq, inv = np.unique(dates, return_inverse=True)
    K = len(uniq)
    order = np.argsort(inv, kind="stable")
    inv_s = inv[order]
    vals_s = vals[order]
    starts = np.searchsorted(inv_s, np.arange(K), side="left")
    ends = np.searchsorted(inv_s, np.arange(K), side="right")
    csum = np.concatenate([[0.0], np.cumsum(vals_s)])
    sums = csum[ends] - csum[starts]
    cnts = (ends - starts).astype(np.float64)
    idx = rng.integers(0, K, size=(BOOT, K))
    bs = sums[idx].sum(axis=1)
    bc = cnts[idx].sum(axis=1)
    return bs / bc


def main():
    print_prereg()

    banner("DATA")
    syms, d0, C, Q = load_panel()
    S, D = C.shape
    print(f"panel: {S} symbols x {D} contiguous days, first day {ms_to_date(d0)}, "
          f"last {ms_to_date(d0 + (D-1)*86_400_000)}")
    print(f"non-null symbol-days: {int(np.isfinite(C).sum()):,}")

    # ---- daily log returns (consecutive days only) -------------------------------
    R = np.full((S, D), np.nan)
    R[:, 1:] = np.log(C[:, 1:] / C[:, :-1])
    R[~np.isfinite(R)] = np.nan

    # ---- MANDATORY CONTROL: same-day cross-sectional median, built ONCE, vectorized
    alive = np.isfinite(R).sum(axis=0)
    with np.errstate(all="ignore"):
        med = np.nanmedian(np.where(np.isfinite(R), R, np.nan), axis=0)
    med[alive < MIN_UNIVERSE] = np.nan
    usable_days = int(np.isfinite(med).sum())
    print(f"cross-sectional median control: {usable_days} usable days "
          f"(>= {MIN_UNIVERSE} live symbols); median universe size = "
          f"{int(np.median(alive[np.isfinite(med)]))}")

    E = R - med[None, :]                      # market-controlled (excess) daily log return
    valid = np.isfinite(E)
    Ez = np.where(valid, E, 0.0)

    # forward h-day excess sums, vectorized: F_h[s,t] = sum_{k=1..h} E[s,t+k]
    cs = np.concatenate([np.zeros((S, 1)), np.cumsum(Ez, axis=1)], axis=1)     # cs[:,j]=sum E[:, :j]
    cv = np.concatenate([np.zeros((S, 1)), np.cumsum(valid, axis=1)], axis=1)
    FWD = {}
    for h in HORIZONS:
        f = np.full((S, D), np.nan)
        # window t+1 .. t+h  -> cs[:, t+h+1] - cs[:, t+1]
        hi = D - h
        s_ = cs[:, 1 + h: 1 + h + hi] - cs[:, 1: 1 + hi]
        n_ = cv[:, 1 + h: 1 + h + hi] - cv[:, 1: 1 + hi]
        s_ = np.where(n_ == h, s_, np.nan)
        f[:, :hi] = s_
        FWD[h] = f

    # ---- trailing volume z-score, strictly causal (t-VOL_WINDOW .. t-1) ----------
    LV = np.where(np.isfinite(Q) & (Q > 0), np.log(Q), np.nan)
    lv_ok = np.isfinite(LV)
    lvz = np.where(lv_ok, LV, 0.0)
    c1 = np.concatenate([np.zeros((S, 1)), np.cumsum(lvz, axis=1)], axis=1)
    c2 = np.concatenate([np.zeros((S, 1)), np.cumsum(lvz ** 2, axis=1)], axis=1)
    cn = np.concatenate([np.zeros((S, 1)), np.cumsum(lv_ok, axis=1)], axis=1)
    W = VOL_WINDOW
    lo = np.maximum(np.arange(D) - W, 0)
    hi_ = np.arange(D)                        # window is [lo, t) -> excludes t
    n_w = cn[:, hi_] - cn[:, lo]
    s_w = c1[:, hi_] - c1[:, lo]
    q_w = c2[:, hi_] - c2[:, lo]
    with np.errstate(all="ignore"):
        mu = s_w / n_w
        var = (q_w - n_w * mu ** 2) / np.maximum(n_w - 1, 1)
        sd = np.sqrt(np.maximum(var, 0.0))
        Z = (LV - mu) / sd
    Z[(n_w < VOL_MIN_OBS) | (sd <= 0) | ~np.isfinite(Z)] = np.nan

    # trailing median quote volume over the same window -> liquidity screen.
    # (rolling median has no cumsum trick; do it once with a strided view, vectorized.)
    Qpad = np.concatenate([np.full((S, W), np.nan), Q], axis=1)
    win = np.lib.stride_tricks.sliding_window_view(Qpad, W, axis=1)[:, :D, :]
    with np.errstate(all="ignore"):
        medq = np.nanmedian(win, axis=2)
    liquid = np.isfinite(medq) & (medq >= MIN_MED_QVOL)

    # ---- events ------------------------------------------------------------------
    same_day_ok = np.isfinite(R) & np.isfinite(med)[None, :]
    ev_mask = np.isfinite(Z) & (Z >= Z_THRESH) & liquid & same_day_ok
    ev_s, ev_t = np.where(ev_mask)
    raw_ret = R[ev_s, ev_t]
    arm_up = raw_ret > 0

    n_all = ev_s.size
    print(f"\nraw events (z >= {Z_THRESH}, liquid, same-day return computable): {n_all:,} "
          f"across {len(np.unique(ev_t)):,} distinct dates, {len(np.unique(ev_s))} symbols")
    print(f"  split by same-day RAW return sign: UP {int(arm_up.sum()):,} / "
          f"DOWN {int((~arm_up).sum()):,}")

    arms = {"UP": arm_up, "DOWN": ~arm_up}

    # ================================ GATE 1 =====================================
    banner("GATE 1  COVERAGE")
    sel = arms[PRIMARY_ARM]
    p_s, p_t = ev_s[sel], ev_t[sel]
    fwd_p = FWD[PRIMARY_H][p_s, p_t]
    keep = np.isfinite(fwd_p)
    dropped = int((~keep).sum())
    n_ev = int(keep.sum())
    clusters = int(np.unique(p_t[keep]).size)
    print(f"PRIMARY arm = {PRIMARY_ARM}, horizon = {PRIMARY_H}d")
    print(f"  events with the {PRIMARY_H}d forward window fully observed : n = {n_ev:,}")
    print(f"  dropped for a missing forward day (delist/halt)            : {dropped:,} "
          f"({dropped/max(sel.sum(),1)*100:.2f}% of the arm)")
    print(f"  distinct event DATES (clusters)                            : {clusters:,}")
    print(f"  declared minimum                                           : "
          f"n >= {MIN_EVENTS}, clusters >= {MIN_CLUSTERS}")
    if n_ev < MIN_EVENTS or clusters < MIN_CLUSTERS:
        print("\n>>> KILL_COVERAGE -- not enough usable events. STOP.")
        return
    print("  --> PASS")

    vals = fwd_p[keep]
    dts = p_t[keep]

    # ================================ GATE 2 =====================================
    # Computed BEFORE the effect. Only the SPREAD of the outcome is touched here.
    banner("GATE 2  POWER (computed before any effect is read)")
    resid_sd = float(np.std(vals, ddof=1))
    uniq, cnts = np.unique(dts, return_counts=True)
    m_bar = float((cnts.astype(float) ** 2).sum() / cnts.sum())
    deff = 1.0 + (m_bar - 1.0) * ICC
    n_eff = n_ev / deff
    mde = (Z_ALPHA + Z_BETA) * resid_sd / np.sqrt(n_eff)
    print(f"  residual sd of market-controlled {PRIMARY_H}d forward log return : "
          f"{resid_sd:.4f}  ({resid_sd*100:.2f}%)")
    print(f"  clusters K = {len(uniq):,}, size-weighted mean cluster size m_bar = {m_bar:.2f}")
    print(f"  design effect = 1 + ({m_bar:.2f}-1)*{ICC} = {deff:.2f}")
    print(f"  effective n = {n_ev:,} / {deff:.2f} = {n_eff:.1f}")
    print(f"  MDE (alpha={ALPHA} one-sided, power={POWER}) = "
          f"({Z_ALPHA}+{Z_BETA}) * {resid_sd:.4f} / sqrt({n_eff:.1f}) = "
          f"{mde:.4f}  ({mde*100:.2f}%)")
    print(f"  declared kill line: MDE < {MDE_KILL_LINE*100:.2f}% "
          f"(half the claimed {CLAIMED_EFFECT*100:.2f}% effect)")
    print(f"  MDE as a multiple of the {ROUND_TRIP_BP} bp round trip: "
          f"{mde*10000/ROUND_TRIP_BP:.1f}x")
    if mde >= MDE_KILL_LINE:
        print("\n>>> KILL_POWER -- the test cannot resolve the claimed effect. "
              "Effect NOT read. STOP.")
        return
    print("  --> PASS")

    # ================================ GATE 3 =====================================
    banner("GATE 3  EFFECT (cluster bootstrap by event DATE)")
    rng = np.random.default_rng(SEED)
    boots = cluster_bootstrap(vals, dts, PRIMARY_DIR, rng)
    mean = float(vals.mean())
    medn = float(np.median(vals))
    lo_ci, hi_ci = np.percentile(boots, [2.5, 97.5])
    p_sign = float((boots < 0).mean()) if PRIMARY_DIR < 0 else float((boots > 0).mean())
    print(f"  n = {n_ev:,}  clusters = {clusters:,}  draws = {BOOT}  seed = {SEED}")
    print(f"  mean   market-controlled {PRIMARY_H}d fwd log return = "
          f"{mean:+.5f}  ({mean*100:+.3f}%,  {mean*10000:+.1f} bp)")
    print(f"  median                                    = {medn:+.5f}  ({medn*100:+.3f}%)")
    print(f"  cluster-bootstrap 95% CI                  = "
          f"[{lo_ci*100:+.3f}%, {hi_ci*100:+.3f}%]")
    print(f"  P(sign = {'negative' if PRIMARY_DIR<0 else 'positive'}) = {p_sign:.4f}"
          f"   (gate: >= {PSIGN_GATE})")

    banner("SECONDARY / ROBUSTNESS (not gated -- family of 6, report raw p only)")
    print(f"  {'arm':5s} {'h':>2s} {'n':>7s} {'clus':>5s} {'mean%':>9s} {'med%':>9s} "
          f"{'CI95_lo%':>9s} {'CI95_hi%':>9s} {'P(neg)':>7s}")
    for aname, amask in arms.items():
        a_s, a_t = ev_s[amask], ev_t[amask]
        for h in HORIZONS:
            fv = FWD[h][a_s, a_t]
            k = np.isfinite(fv)
            if k.sum() < 30:
                continue
            v, t = fv[k], a_t[k]
            b = cluster_bootstrap(v, t, -1, np.random.default_rng(SEED))
            l, u = np.percentile(b, [2.5, 97.5])
            print(f"  {aname:5s} {h:2d} {k.sum():7,d} {np.unique(t).size:5,d} "
                  f"{v.mean()*100:+9.3f} {np.median(v)*100:+9.3f} "
                  f"{l*100:+9.3f} {u*100:+9.3f} {(b<0).mean():7.4f}")

    if p_sign < PSIGN_GATE:
        print("\n>>> KILL_EFFECT -- the predicted sign is not established. STOP.")
        return
    print("\n  --> GATE 3 PASS")

    # ================================ ECONOMICS ==================================
    banner("ECONOMICS")
    gross_bp = abs(mean) * 10000.0
    net_bp = gross_bp - ROUND_TRIP_BP
    ratio = gross_bp / ROUND_TRIP_BP
    print(f"  gross edge per event  = {gross_bp:.1f} bp")
    print(f"  measured round trip   = {ROUND_TRIP_BP} bp (two-perp, this repo; alts worse)")
    print(f"  net per event         = {net_bp:+.1f} bp")
    print(f"  EDGE / COST RATIO     = {ratio:.2f}x   (gate: >= {EDGE_COST_MIN:.1f}x)")
    if net_bp <= 0 or ratio < EDGE_COST_MIN:
        print("\n>>> KILL_ECONOMICS -- cannot clear the toll. STOP.")
        return
    print("\n>>> SURVIVES all gates.")


if __name__ == "__main__":
    main()
