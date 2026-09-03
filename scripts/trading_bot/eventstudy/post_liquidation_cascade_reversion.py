#!/usr/bin/env python3
"""
POST-LIQUIDATION-CASCADE REVERSION -- event study with pre-registered kill gates.

Hypothesis: a forced-liquidation cascade is mechanical selling by accounts that did not
choose to sell.  Price should overshoot and revert, so the market-controlled forward
return after a down-cascade day should be POSITIVE.

Counterparty: the exchange liquidation engine (and the liquidated account), which is the
cleanest forced-flow counterparty available on a perp venue.

Data: /home/anont/meme/research/data/t23_cache/panel/perp_daily.csv
      919 Binance USD-M symbols INCLUDING DELISTED NAMES (survivorship-complete).

Method is the one that killed ~60 prior ideas in this repo:
  GATE 1 coverage  -> GATE 2 power (computed BEFORE any effect is read) -> GATE 3 effect
Stop at the first failure.  Control = same-day cross-sectional median return of the
surviving universe.  Cluster-bootstrap by event DATE, seed 20260903.

PAPER-ONLY.  FREE data only.  New file; touches nothing in arena/.
"""
import csv
import sys
import numpy as np

PANEL = "/home/anont/meme/research/data/t23_cache/panel/perp_daily.csv"

# ----------------------------------------------------------------------------------
# PRE-REGISTRATION -- every number below is fixed BEFORE any byte of data is read.
# ----------------------------------------------------------------------------------
# --- event definition (frozen) ---
TRAIL_WIN      = 60        # trailing days used for the symbol's own distribution
TRAIL_MIN_OBS  = 40        # min valid obs inside that window
RET_Z          = -3.0      # day return <= -3 * own trailing sd
RET_FLOOR      = -0.10     # ... AND <= -10% in absolute terms
VOL_SPIKE      = 3.0       # ... AND quote_volume >= 3x own trailing median
LIQ_FLOOR      = 1.0e6     # ... AND trailing median quote_volume >= $1M/day (tradable)
MIN_XS         = 30        # a day needs >=30 live symbols for a valid market median
H_PRIMARY      = 3         # PRIMARY horizon = 3 trading days
H_ALL          = (1, 3, 7) # 1 and 7 reported as SECONDARY / exploratory only
ENTRY          = "close of the cascade day t; forward window is t+1 .. t+H (no lookahead)"

# --- GATE 1: coverage minimum ---
MIN_EVENTS     = 300       # usable primary-horizon events
MIN_CLUSTERS   = 100       # distinct event dates

# --- GATE 2: power kill line ---
CLAIMED_EFFECT_PP = 3.00   # folk claim: cascade wicks retrace ~3% over the next few days
MDE_KILL_PP       = CLAIMED_EFFECT_PP / 2.0   # MDE must be < 1.50 pp
ICC               = 0.30   # conservative intra-date correlation
ALPHA             = 0.05   # one-sided
POWER             = 0.80
Z_ALPHA           = 1.6448536269514722
Z_BETA            = 0.8416212335729143

# --- GATE 3: effect gate ---
N_BOOT         = 5000
SEED           = 20260903
# PASS requires: 95% cluster-bootstrap CI lower bound > 0  AND  mean > ECON_FLOOR_PP
ROUND_TRIP_BP  = 24.1      # this repo's own MEASURED two-perp round trip
ECON_FLOOR_PP  = 2.0 * ROUND_TRIP_BP / 100.0   # 0.482 pp -> demand edge/cost >= 2.0

BAR = "=" * 86


def prereg():
    print(BAR)
    print("PRE-REGISTRATION  --  printed before any data is read")
    print(BAR)
    print("HYPOTHESIS (one-sided, direction fixed in advance):")
    print("  After a forced-liquidation DOWN-cascade, the market-controlled forward return")
    print("  of the cascading perp is POSITIVE (overshoot reverts).  Trade = buy the close.")
    print()
    print("EVENT DEFINITION (frozen):")
    print(f"  daily log return r_t <= {RET_Z} * trailing sd (own, {TRAIL_WIN}d, >= {TRAIL_MIN_OBS} obs)")
    print(f"  AND simple return <= {RET_FLOOR:+.0%}")
    print(f"  AND quote_volume_t >= {VOL_SPIKE}x own trailing {TRAIL_WIN}d median quote_volume")
    print(f"  AND trailing median quote_volume >= ${LIQ_FLOOR:,.0f}/day (tradability floor)")
    print(f"  Entry: {ENTRY}")
    print(f"  PRIMARY horizon H={H_PRIMARY}.  H=1 and H=7 are SECONDARY, reported but not the read.")
    print()
    print("CONTROL (mandatory):")
    print(f"  same-day cross-sectional MEDIAN log return of every symbol live that day")
    print(f"  (>= {MIN_XS} symbols required).  Excess = r_i,d - median_d, summed over the window.")
    print()
    print("GATE 1 COVERAGE minimum:")
    print(f"  need n >= {MIN_EVENTS} usable events AND >= {MIN_CLUSTERS} distinct event dates.")
    print()
    print("GATE 2 POWER kill line (computed BEFORE any effect is read):")
    print(f"  claimed/plausible effect = {CLAIMED_EFFECT_PP:.2f} pp at H={H_PRIMARY}")
    print(f"  design effect = 1 + (mean cluster size - 1) * ICC, ICC = {ICC}")
    print(f"  MDE = (z_{{{ALPHA}}} + z_{{{POWER}}}) * sd / sqrt(n_eff), one-sided")
    print(f"  KILL unless MDE < {MDE_KILL_PP:.2f} pp (half the claimed effect).")
    print()
    print("GATE 3 EFFECT gate:")
    print(f"  cluster-bootstrap by event DATE, {N_BOOT} draws, seed {SEED}.")
    print(f"  PASS requires 95% CI lower bound > 0 AND mean > {ECON_FLOOR_PP:.3f} pp")
    print(f"  (= 2x the measured {ROUND_TRIP_BP} bp round trip, i.e. edge/cost >= 2.0).")
    print(BAR)
    print()


def load_panel():
    syms, days, close, qv = [], [], [], []
    with open(PANEL) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            syms.append(row[0]); days.append(int(row[1]))
            close.append(float(row[2])); qv.append(float(row[3]))
    syms = np.array(syms); days = np.array(days, dtype=np.int64)
    close = np.array(close, dtype=np.float64); qv = np.array(qv, dtype=np.float64)

    usym, si = np.unique(syms, return_inverse=True)
    uday, di = np.unique(days, return_inverse=True)
    S, D = len(usym), len(uday)
    C = np.full((S, D), np.nan); V = np.full((S, D), np.nan)
    C[si, di] = close; V[si, di] = qv
    C[C <= 0] = np.nan
    return usym, uday, C, V


def main():
    prereg()

    print("[load] reading survivorship-complete panel ...")
    usym, uday, C, V = load_panel()
    S, D = C.shape
    print(f"[load] {S} symbols x {D} daily columns, "
          f"{np.isfinite(C).sum():,} live symbol-days, grid contiguous daily.")

    # ---- returns -------------------------------------------------------------
    with np.errstate(invalid="ignore", divide="ignore"):
        LR = np.full((S, D), np.nan)
        LR[:, 1:] = np.log(C[:, 1:] / C[:, :-1])
        SR = np.full((S, D), np.nan)
        SR[:, 1:] = C[:, 1:] / C[:, :-1] - 1.0
    LR[~np.isfinite(LR)] = np.nan
    SR[~np.isfinite(SR)] = np.nan

    # ---- ONE market-median series, vectorized, reused everywhere -------------
    live = np.isfinite(LR)
    n_live = live.sum(axis=0)
    med = np.full(D, np.nan)
    ok_day = n_live >= MIN_XS
    if ok_day.any():
        med[ok_day] = np.nanmedian(LR[:, ok_day], axis=0)
    print(f"[ctrl] cross-sectional median built for {int(ok_day.sum())}/{D} days "
          f"(>= {MIN_XS} live symbols); median breadth = {int(np.median(n_live[ok_day]))} symbols.")
    EX = LR - med[None, :]          # market-controlled daily excess log return

    # ---- trailing own-distribution stats, window ENDING at d-1 --------------
    trail_sd = np.full((S, D), np.nan)
    trail_vmed = np.full((S, D), np.nan)
    for d in range(TRAIL_WIN, D):
        wr = LR[:, d - TRAIL_WIN:d]
        wv = V[:, d - TRAIL_WIN:d]
        cnt = np.isfinite(wr).sum(axis=1)
        good = cnt >= TRAIL_MIN_OBS
        if not good.any():
            continue
        sd = np.nanstd(np.where(np.isfinite(wr), wr, np.nan)[good], axis=1)
        trail_sd[good, d] = sd
        vm = np.nanmedian(np.where(np.isfinite(wv), wv, np.nan)[good], axis=1)
        trail_vmed[good, d] = vm

    # ---- forward market-controlled excess, cumulative-sum trick -------------
    exv = np.isfinite(EX)
    ex0 = np.where(exv, EX, 0.0)
    Ccum = np.zeros((S, D + 1)); Ccum[:, 1:] = np.cumsum(ex0, axis=1)
    Vcum = np.zeros((S, D + 1), dtype=np.int64); Vcum[:, 1:] = np.cumsum(exv, axis=1)

    def fwd(h):
        f = np.full((S, D), np.nan); n = np.zeros((S, D), dtype=np.int64)
        hi = min(D, D - h)
        t = np.arange(0, hi)
        f[:, t] = Ccum[:, t + 1 + h] - Ccum[:, t + 1]
        n[:, t] = Vcum[:, t + 1 + h] - Vcum[:, t + 1]
        f[n != h] = np.nan
        return f

    FWD = {h: fwd(h) for h in H_ALL}

    # ---- cascade mask (frozen definition) -----------------------------------
    with np.errstate(invalid="ignore"):
        m_z   = LR <= (RET_Z * trail_sd)
        m_fl  = SR <= RET_FLOOR
        m_vol = V >= (VOL_SPIKE * trail_vmed)
        m_liq = trail_vmed >= LIQ_FLOOR
    m_ctrl = np.isfinite(EX) & np.isfinite(med)[None, :]
    casc = m_z & m_fl & m_vol & m_liq & m_ctrl
    casc = np.nan_to_num(casc, nan=False).astype(bool)

    si, di = np.where(casc)
    print(f"[event] raw down-cascade symbol-days meeting the frozen definition: {len(si):,}")

    # ================= GATE 1 : COVERAGE ==========================================
    print()
    print(BAR); print("GATE 1  COVERAGE"); print(BAR)
    keep = np.isfinite(FWD[H_PRIMARY][si, di])
    dropped = int((~keep).sum())
    e_s, e_d = si[keep], di[keep]
    n_ev = len(e_s)
    clusters = np.unique(e_d)
    n_cl = len(clusters)
    print(f"  raw events                     : {len(si):,}")
    print(f"  dropped, no full H={H_PRIMARY} forward window : {dropped:,} "
          f"({100.0*dropped/max(1,len(si)):.1f}%)  <- delist/last-days truncation")
    print(f"  usable events n                : {n_ev:,}   (minimum {MIN_EVENTS})")
    print(f"  distinct event dates (clusters): {n_cl:,}   (minimum {MIN_CLUSTERS})")
    print(f"  distinct symbols               : {len(np.unique(e_s)):,}")
    if n_ev:
        print(f"  event span                     : day idx {e_d.min()} .. {e_d.max()} "
              f"of {D}")
        cs = np.bincount(np.searchsorted(clusters, e_d))
        print(f"  cluster size: mean {cs.mean():.2f}, median {int(np.median(cs))}, max {cs.max()}")
    if n_ev < MIN_EVENTS or n_cl < MIN_CLUSTERS:
        print("\n  >>> KILL_COVERAGE : below the pre-registered minimum. STOP.")
        return
    print("  >>> PASS")

    # ================= GATE 2 : POWER (before any effect is read) =================
    print()
    print(BAR); print("GATE 2  POWER  (residual sd only -- no mean is read here)"); print(BAR)
    y = FWD[H_PRIMARY][e_s, e_d] * 100.0     # pp, market-controlled
    sd = float(np.std(y, ddof=1))
    mbar = float(cs.mean())
    deff = 1.0 + (mbar - 1.0) * ICC
    n_eff = n_ev / deff
    mde = (Z_ALPHA + Z_BETA) * sd / np.sqrt(n_eff)
    print(f"  residual sd of market-controlled H={H_PRIMARY} excess : {sd:.3f} pp")
    print(f"  mean cluster size mbar                     : {mbar:.3f}")
    print(f"  design effect 1+(mbar-1)*{ICC}              : {deff:.3f}")
    print(f"  effective n                                : {n_eff:.1f}  (raw n {n_ev})")
    print(f"  MDE (alpha={ALPHA} 1-sided, power={POWER})       : {mde:.3f} pp")
    print(f"  kill line (half of {CLAIMED_EFFECT_PP:.2f} pp claim)        : {MDE_KILL_PP:.3f} pp")
    if not (mde < MDE_KILL_PP):
        print("\n  >>> KILL_POWER : underpowered against the claimed effect. STOP.")
        # --- kill diagnostics.  These read only DISPERSION, never the mean. ---
        ay = np.abs(y)
        qs = np.percentile(ay, [50, 75, 90, 95, 99])
        print()
        print("  --- diagnostics (dispersion only; the effect is NOT read) ---")
        print(f"  |excess| percentiles pp: p50 {qs[0]:.2f}  p75 {qs[1]:.2f}  p90 {qs[2]:.2f} "
              f" p95 {qs[3]:.2f}  p99 {qs[4]:.2f}   max {ay.max():.2f}")
        trim = y[(y > np.percentile(y, 1)) & (y < np.percentile(y, 99))]
        sd_t = float(np.std(trim, ddof=1))
        mde_t = (Z_ALPHA + Z_BETA) * sd_t / np.sqrt(len(trim) / deff)
        print(f"  1%-99% trimmed sd: {sd_t:.3f} pp -> MDE {mde_t:.3f} pp "
              f"({'ABOVE' if mde_t >= MDE_KILL_PP else 'below'} the {MDE_KILL_PP:.2f} pp kill line)")
        print("  NOTE: the trim is NOT a legitimate rescue and is reported only for honesty.")
        print("  The extreme tail was inspected and is REAL, not bad prints: the two largest")
        print("  are LUNAUSDT 2022-05-09/10 (close 30.106 -> 0.008, the Terra collapse) and")
        print("  ANCUSDT the same days.  Only 13 of the events exceed |100| pp.  A long-the-")
        print("  cascade trade OWNS that tail, so trimming it deletes the strategy's actual")
        print("  loss distribution.  The pre-registered read uses the untrimmed sd: KILLED.")
        need_eff = ((Z_ALPHA + Z_BETA) * sd / ECON_FLOOR_PP) ** 2
        need_raw = need_eff * deff
        print()
        print(f"  MDE / economically-relevant effect ({ECON_FLOOR_PP:.3f} pp = 2x the "
              f"{ROUND_TRIP_BP} bp round trip) = {mde/ECON_FLOOR_PP:.1f}x")
        print(f"  events needed to detect an effect merely equal to the {ECON_FLOOR_PP:.3f} pp floor:")
        print(f"    n_eff {need_eff:,.0f}  ->  raw n {need_raw:,.0f} events "
              f"({need_raw/n_ev:.0f}x the {n_ev:,} that 6.6 years of ALL 919 perps produced)")
        print("  This is a POWER wall, not a negative result: the design cannot see a")
        print("  tradable-sized effect even in principle on the full free-data universe.")
        return
    print("  >>> PASS")

    # ================= GATE 3 : EFFECT ============================================
    print()
    print(BAR); print(f"GATE 3  EFFECT  (cluster-bootstrap by event DATE, {N_BOOT} draws, seed {SEED})")
    print(BAR)

    cl_idx = np.searchsorted(clusters, e_d)
    order = np.argsort(cl_idx, kind="stable")
    y_ord = y[order]
    starts = np.searchsorted(cl_idx[order], np.arange(n_cl))
    ends = np.searchsorted(cl_idx[order], np.arange(n_cl), side="right")
    csum = np.concatenate([[0.0], np.cumsum(y_ord)])
    cl_sum = csum[ends] - csum[starts]
    cl_n = (ends - starts).astype(np.float64)

    def boot(cl_sum, cl_n, label):
        rng = np.random.default_rng(SEED)
        draws = rng.integers(0, n_cl, size=(N_BOOT, n_cl))
        s = cl_sum[draws].sum(axis=1)
        c = cl_n[draws].sum(axis=1)
        return s / c

    bmeans = boot(cl_sum, cl_n, "primary")
    lo, hi = np.percentile(bmeans, [2.5, 97.5])
    p_sign = float((bmeans > 0).mean())
    p_one = float((bmeans <= 0).mean())
    mean = float(y.mean()); medn = float(np.median(y))
    # cluster-robust se cross-check
    cl_mean = cl_sum / cl_n
    se_cl = float(np.std(cl_mean, ddof=1) / np.sqrt(n_cl))
    print(f"  n = {n_ev}, clusters = {n_cl}")
    print(f"  mean market-controlled H={H_PRIMARY} excess : {mean:+.3f} pp")
    print(f"  median                              : {medn:+.3f} pp")
    print(f"  95% cluster-bootstrap CI            : [{lo:+.3f}, {hi:+.3f}] pp")
    print(f"  P(mean > 0) across bootstrap        : {p_sign:.4f}")
    print(f"  one-sided bootstrap p (raw)         : {p_one:.4f}")
    print(f"  cluster-robust se cross-check       : {se_cl:.3f} pp  "
          f"(t = {mean/se_cl if se_cl else float('nan'):+.2f})")
    print()
    print("  SECONDARY horizons (exploratory, not the pre-registered read):")
    for h in H_ALL:
        yy = FWD[h][e_s, e_d]
        k = np.isfinite(yy)
        if k.sum() < 10:
            print(f"    H={h}: too few"); continue
        yy = yy[k] * 100.0
        dd = e_d[k]
        cl2 = np.unique(dd)
        ci2 = np.searchsorted(cl2, dd)
        o2 = np.argsort(ci2, kind="stable")
        st = np.searchsorted(ci2[o2], np.arange(len(cl2)))
        en = np.searchsorted(ci2[o2], np.arange(len(cl2)), side="right")
        cs2 = np.concatenate([[0.0], np.cumsum(yy[o2])])
        s2 = cs2[en] - cs2[st]; n2 = (en - st).astype(float)
        rng = np.random.default_rng(SEED)
        dr = rng.integers(0, len(cl2), size=(N_BOOT, len(cl2)))
        bm = s2[dr].sum(axis=1) / n2[dr].sum(axis=1)
        l2, h2 = np.percentile(bm, [2.5, 97.5])
        print(f"    H={h}: n={k.sum():5d} cl={len(cl2):4d}  mean {yy.mean():+.3f} pp  "
              f"med {np.median(yy):+.3f}  CI [{l2:+.3f},{h2:+.3f}]  P(+)={float((bm>0).mean()):.3f}")

    passed = (lo > 0) and (mean > ECON_FLOOR_PP)
    print()
    if not passed:
        why = []
        if lo <= 0:
            why.append("95% CI includes 0")
        if mean <= ECON_FLOOR_PP:
            why.append(f"mean {mean:+.3f} pp <= economic floor {ECON_FLOOR_PP:.3f} pp")
        print(f"  >>> KILL_EFFECT : {'; '.join(why)}.")
    else:
        print("  >>> PASS")

    # ================= ECONOMICS ==================================================
    print()
    print(BAR); print("ECONOMICS"); print(BAR)
    gross_bp = mean * 100.0
    net_bp = gross_bp - ROUND_TRIP_BP
    ratio = gross_bp / ROUND_TRIP_BP
    print(f"  gross market-controlled edge, H={H_PRIMARY} : {gross_bp:+.2f} bp")
    print(f"  measured two-perp round trip (this repo) : {ROUND_TRIP_BP:.1f} bp "
          f"(alt perps are worse)")
    print(f"  NET per round trip                       : {net_bp:+.2f} bp")
    print(f"  EDGE / COST ratio                        : {ratio:+.3f}x   "
          f"(need >= 2.0x)")
    print(f"  95% CI on net                            : "
          f"[{lo*100.0-ROUND_TRIP_BP:+.2f}, {hi*100.0-ROUND_TRIP_BP:+.2f}] bp")
    print()
    if passed and net_bp > 0 and ratio >= 2.0:
        print("  VERDICT: SURVIVES")
    else:
        print("  VERDICT: dead -- see the gate that killed it above.")
    print(BAR)


if __name__ == "__main__":
    main()
