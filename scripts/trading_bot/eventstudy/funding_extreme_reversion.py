#!/usr/bin/env python3
"""
FUNDING-EXTREME REVERSION (the FADE, not the carry).

CLAIM UNDER TEST
    When perp funding reaches a cross-sectional extreme, the crowded leveraged side is
    paying to hold and is vulnerable to an unwind.  Fading it (SHORT the top-decile
    funding names, LONG the bottom-decile funding names) should earn a positive
    market-controlled return over the following 1 / 3 / 7 days.

EXPLICIT NON-RESURRECTION
    This is NOT naive funding carry.  Funding carry is already dead in this repo (T23:
    MDE 15.25 pp/yr against a 2.20 pp/yr claim) and cross-venue basis is dead (T25).
    Carry collects the funding print; this test IGNORES the funding print entirely as a
    P&L source and measures only the PRICE reversion of the crowded side.  A positive
    result here would not revive carry, and the carry kill does not by itself kill this.

METHOD (identical to the protocol that killed the unlock-cliff short, 20260903)
    GATE 1 COVERAGE -> GATE 2 POWER (computed BEFORE any effect is read) -> GATE 3 EFFECT
    -> ECONOMICS.  Stop at the first failure.

CONTROL
    Same-day cross-sectional MEDIAN log return of the surviving tradeable universe,
    subtracted day by day.  This control is what inverted the unlock result and is
    mandatory here.  It is built ONCE as a daily series and reused (vectorized).

DATA (free, on disk, survivorship-complete -- includes delisted names)
    research/data/t23_cache/panel/perp_daily.csv   symbol,day_ms,close,quote_volume,trades
    research/data/t23_cache/panel/funding.csv      symbol,funding_time_ms,interval_hours,funding_rate
"""

import csv
import os
import sys
import numpy as np

ROOT = "/home/anont/meme"
PERP = os.path.join(ROOT, "research/data/t23_cache/panel/perp_daily.csv")
FUND = os.path.join(ROOT, "research/data/t23_cache/panel/funding.csv")

DAY_MS = 86_400_000
SEED = 20260903
N_BOOT = 5000

# ---------------------------------------------------------------------------
# DESIGN CONSTANTS -- all fixed here, before any data is read.
# ---------------------------------------------------------------------------
MIN_QUOTE_VOLUME = 1_000_000.0   # USD notional on the signal day; tradeability filter
MIN_XSECTION     = 30            # symbols needed that day to form deciles at all
DECILE           = 0.10          # top/bottom 10% of the daily funding cross-section
HORIZONS         = (1, 3, 7)
PRIMARY_H        = 3             # the pre-registered primary horizon
ROUND_TRIP_BP    = 24.1          # this repo's OWN measured two-perp round trip; alts worse

# ---------------------------------------------------------------------------
# PRE-REGISTRATION -- printed before a single byte of data is read.
# ---------------------------------------------------------------------------
PLAUSIBLE_EFFECT_PP = 1.00       # pp per event at the primary horizon
POWER_KILL_MDE_PP   = 0.50       # = PLAUSIBLE_EFFECT_PP / 2
ICC                 = 0.30
MIN_EVENTS          = 2000
MIN_CLUSTERS        = 200
EFFECT_CI_RULE      = "cluster-bootstrap 95% CI lower bound > 0 AND P(sign>0) >= 0.95"
ECON_RATIO_MIN      = 2.0


def print_prereg():
    print("=" * 78)
    print("PRE-REGISTRATION  (declared BEFORE any data is read)")
    print("=" * 78)
    print("HYPOTHESIS (one sentence, directional):")
    print("  After a perp's daily funding enters the TOP decile of that day's cross-section")
    print("  (crowded longs paying), SHORTing it -- and after it enters the BOTTOM decile")
    print("  (crowded shorts paying), LONGing it -- earns a POSITIVE market-controlled")
    print("  return over the following 1/3/7 days.")
    print()
    print("NOT CARRY: the funding print itself is excluded from P&L. Carry is repo-dead")
    print("  (T23 MDE 15.25pp/yr vs a 2.20pp/yr claim; T25 cross-venue basis). This tests")
    print("  PRICE reversion of the crowded side only, and does not resurrect carry.")
    print()
    print("SIGNAL CONSTRUCTION (fixed):")
    print(f"  daily funding rate = SUM of all funding prints in UTC day t (normalises the")
    print(f"    1h/2h/4h/8h cadence mix). Signal known at close of day t; entry at close t.")
    print(f"  Eligible on day t: finite close, finite quote_volume >= ${MIN_QUOTE_VOLUME:,.0f},")
    print(f"    >=1 funding print that day. Deciles formed only if >= {MIN_XSECTION} eligible symbols.")
    print(f"  Decile width: {DECILE:.0%} each tail. Fade sign: top decile -> SHORT (-1),")
    print("    bottom decile -> LONG (+1). Legs POOLED into one signed sample (primary).")
    print()
    print("OUTCOME (fixed):")
    print("  signed fade return = sign * SUM_{k=1..h} ( logret[s,t+k] - median_logret[t+k] )")
    print("  where median_logret[t] is the same-day cross-sectional MEDIAN log return of the")
    print("  surviving tradeable universe (built once, reused). Reported in pp (100*log).")
    print("  Delisting: accumulation truncates naturally at a symbol's last day (>=1 fwd day")
    print("  required). Delisted names are KEPT -- the panel is survivorship-complete.")
    print()
    print("GATE 1 COVERAGE minimum:")
    print(f"  >= {MIN_EVENTS} signed fade events AND >= {MIN_CLUSTERS} distinct event-date clusters")
    print(f"  at the primary horizon h={PRIMARY_H}. Otherwise KILL_COVERAGE.")
    print()
    print("GATE 2 POWER kill line (computed BEFORE the effect is read):")
    print(f"  Plausible/claimed effect E = {PLAUSIBLE_EFFECT_PP:.2f} pp per event")
    print(f"    (= {PLAUSIBLE_EFFECT_PP*100/ROUND_TRIP_BP:.1f}x the repo-measured {ROUND_TRIP_BP} bp round trip; below E the")
    print("     trade cannot pay for itself at any realistic turnover).")
    print(f"  residual sd = sd of the signed, median-controlled fade return across events.")
    print(f"  design effect = 1 + (mean cluster size - 1) * ICC, ICC = {ICC}")
    print(f"  MDE = (z_0.05_1s + z_0.80) * sd / sqrt(n_eff), n_eff = n / design effect")
    print(f"  KILL LINE: MDE must be < {POWER_KILL_MDE_PP:.2f} pp (= E/2). Otherwise KILL_POWER.")
    print()
    print("GATE 3 EFFECT gate (only if 1-2 pass):")
    print(f"  Cluster-bootstrap by event DATE, {N_BOOT} draws, fixed seed {SEED}.")
    print(f"  PASS requires: {EFFECT_CI_RULE}. Otherwise KILL_EFFECT.")
    print()
    print("ECONOMICS gate:")
    print(f"  net = mean - {ROUND_TRIP_BP} bp round trip. Requires net > 0 AND")
    print(f"  edge/cost ratio > {ECON_RATIO_MIN}. Otherwise KILL_ECONOMICS.")
    print()
    print(f"MULTIPLE COMPARISONS: family = {len(HORIZONS)} horizons {HORIZONS}; primary is h={PRIMARY_H}.")
    print("  The raw uncorrected p / P(sign) is reported for family-wise correction.")
    print("=" * 78)
    print()


# ---------------------------------------------------------------------------
# LOADERS
# ---------------------------------------------------------------------------
def load_panel():
    syms, days = {}, {}
    rows = []
    with open(PERP) as f:
        r = csv.reader(f)
        next(r)
        for s, d, c, qv, _tr in r:
            si = syms.setdefault(s, len(syms))
            di = int(d) // DAY_MS
            days[di] = None
            rows.append((si, di, float(c), float(qv)))
    day_idx = {d: i for i, d in enumerate(sorted(days))}
    S, T = len(syms), len(day_idx)
    close = np.full((S, T), np.nan)
    qvol = np.full((S, T), np.nan)
    for si, di, c, qv in rows:
        ti = day_idx[di]
        close[si, ti] = c
        qvol[si, ti] = qv
    return syms, day_idx, close, qvol


def load_funding(syms, day_idx):
    S, T = len(syms), len(day_idx)
    fsum = np.zeros((S, T))
    fcnt = np.zeros((S, T), dtype=np.int32)
    with open(FUND) as f:
        r = csv.reader(f)
        next(r)
        for s, t, _iv, rate in r:
            si = syms.get(s)
            if si is None:
                continue
            ti = day_idx.get(int(t) // DAY_MS)
            if ti is None:
                continue
            fsum[si, ti] += float(rate)
            fcnt[si, ti] += 1
    return fsum, fcnt


# ---------------------------------------------------------------------------
def main():
    print_prereg()

    print("Loading panel ...", flush=True)
    syms, day_idx, close, qvol = load_panel()
    S, T = close.shape
    print(f"  panel: {S} symbols x {T} days (survivorship-complete, delisted names included)")
    fsum, fcnt = load_funding(syms, day_idx)
    print(f"  funding: {int(fcnt.sum())} prints mapped onto the daily grid")
    print()

    # --- daily log returns, aligned so lr[:, t] is the return EARNED on day t -------
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.full((S, T), np.nan)
        lr[:, 1:] = np.log(close[:, 1:] / close[:, :-1])
    lr[~np.isfinite(lr)] = np.nan

    liquid = np.isfinite(qvol) & (qvol >= MIN_QUOTE_VOLUME)

    # --- THE CONTROL, built ONCE: same-day cross-sectional median log return --------
    # universe = symbols with a finite return that day AND liquid that day.
    ctrl_mask = np.isfinite(lr) & liquid
    lr_ctrl = np.where(ctrl_mask, lr, np.nan)
    with np.errstate(invalid="ignore"):
        med = np.nanmedian(lr_ctrl, axis=0)          # shape (T,)
    n_univ = ctrl_mask.sum(axis=0)
    med[n_univ < MIN_XSECTION] = np.nan
    print(f"CONTROL: daily cross-sectional median log return built once for {int(np.isfinite(med).sum())} days "
          f"(median universe width {int(np.median(n_univ[np.isfinite(med)]))} symbols)")

    # --- excess return matrix + cumulative sums (vectorized, no per-event loop) -----
    x = lr - med[None, :]
    avail = np.isfinite(x)
    xz = np.where(avail, x, 0.0)
    cum = np.zeros((S, T + 1))
    cnt = np.zeros((S, T + 1))
    np.cumsum(xz, axis=1, out=cum[:, 1:])
    np.cumsum(avail, axis=1, out=cnt[:, 1:])

    # --- eligibility for the SIGNAL day --------------------------------------------
    elig = np.isfinite(close) & liquid & (fcnt > 0)

    # --- form deciles per day (loop over 2404 days only; O(T), not O(T*S) python) ---
    ev_sym, ev_day, ev_sign = [], [], []
    days_used = 0
    for t in range(T):
        idx = np.flatnonzero(elig[:, t])
        if idx.size < MIN_XSECTION:
            continue
        vals = fsum[idx, t]
        order = np.argsort(vals, kind="stable")
        k = int(np.floor(idx.size * DECILE))
        if k < 1:
            continue
        days_used += 1
        lo = idx[order[:k]]      # most NEGATIVE funding -> crowded shorts -> fade = LONG
        hi = idx[order[-k:]]     # most POSITIVE funding -> crowded longs  -> fade = SHORT
        ev_sym.append(lo); ev_day.append(np.full(k, t)); ev_sign.append(np.full(k, 1.0))
        ev_sym.append(hi); ev_day.append(np.full(k, t)); ev_sign.append(np.full(k, -1.0))
    ev_sym = np.concatenate(ev_sym); ev_day = np.concatenate(ev_day)
    ev_sign = np.concatenate(ev_sign)
    print(f"SIGNAL: {days_used} days had a formable cross-section; "
          f"{ev_sym.size} raw (symbol,day) decile entries before forward-return filtering")
    print()

    results = {}
    for h in HORIZONS:
        # cum[:, j] = sum over days 0..j-1, so window (t, t+h] = cum[t+h+1] - cum[t+1]
        end = np.minimum(ev_day + h + 1, T)
        s_ = cum[ev_sym, end] - cum[ev_sym, ev_day + 1]
        c_ = cnt[ev_sym, end] - cnt[ev_sym, ev_day + 1]
        keep = c_ >= 1
        r = ev_sign[keep] * s_[keep] * 100.0     # pp
        d = ev_day[keep]
        trunc = int((c_[keep] < h).sum())
        results[h] = (r, d, trunc, int(keep.size - keep.sum()))

    # =====================================================================
    # GATE 1  COVERAGE
    # =====================================================================
    print("=" * 78); print("GATE 1  COVERAGE"); print("=" * 78)
    for h in HORIZONS:
        r, d, trunc, dropped = results[h]
        print(f"  h={h}d : n={r.size:7d} events | clusters(dates)={np.unique(d).size:5d} | "
              f"truncated-by-delisting={trunc} | dropped(no fwd day)={dropped}")
    r_p, d_p, trunc_p, drop_p = results[PRIMARY_H]
    n_p = r_p.size; k_p = np.unique(d_p).size
    ok = (n_p >= MIN_EVENTS) and (k_p >= MIN_CLUSTERS)
    print(f"  PRIMARY h={PRIMARY_H}: n={n_p} vs min {MIN_EVENTS}; clusters={k_p} vs min {MIN_CLUSTERS}")
    if not ok:
        print("  -> KILL_COVERAGE"); sys.exit(0)
    print("  -> PASS")
    print()

    # =====================================================================
    # GATE 2  POWER   (computed BEFORE any effect is read)
    # =====================================================================
    print("=" * 78); print("GATE 2  POWER  (no effect has been read yet)"); print("=" * 78)
    Z = 1.6448536269514722 + 0.8416212335729143   # alpha=.05 one-sided + power .80
    power = {}
    for h in HORIZONS:
        r, d, _, _ = results[h]
        sd = float(r.std(ddof=1))
        nclus = np.unique(d).size
        mbar = r.size / nclus
        deff = 1.0 + (mbar - 1.0) * ICC
        neff = r.size / deff
        mde = Z * sd / np.sqrt(neff)
        power[h] = (sd, mbar, deff, neff, mde)
        print(f"  h={h}d : residual sd={sd:8.3f} pp | mean cluster size={mbar:6.2f} | "
              f"design effect={deff:7.2f} | n_eff={neff:9.1f} | MDE={mde:6.3f} pp")
    sd_p, mbar_p, deff_p, neff_p, mde_p = power[PRIMARY_H]
    print(f"  PRIMARY h={PRIMARY_H}: MDE={mde_p:.3f} pp vs kill line {POWER_KILL_MDE_PP:.2f} pp "
          f"(plausible effect {PLAUSIBLE_EFFECT_PP:.2f} pp)")
    if mde_p >= POWER_KILL_MDE_PP:
        print("  -> KILL_POWER  (cannot resolve the claimed effect; stop here)")
        sys.exit(0)
    print("  -> PASS")
    print()

    # =====================================================================
    # GATE 3  EFFECT
    # =====================================================================
    print("=" * 78); print(f"GATE 3  EFFECT  (cluster-bootstrap by event date, {N_BOOT} draws, seed {SEED})")
    print("=" * 78)
    eff = {}
    for h in HORIZONS:
        r, d, _, _ = results[h]
        udays, inv = np.unique(d, return_inverse=True)
        K = udays.size
        csum = np.bincount(inv, weights=r, minlength=K)
        ccnt = np.bincount(inv, minlength=K).astype(float)
        rng = np.random.default_rng(SEED)
        pick = rng.integers(0, K, size=(N_BOOT, K))
        boot = csum[pick].sum(axis=1) / ccnt[pick].sum(axis=1)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        psign = float((boot > 0).mean())
        eff[h] = (float(r.mean()), float(np.median(r)), lo, hi, psign, boot)
        tag = "PRIMARY" if h == PRIMARY_H else "       "
        print(f"  {tag} h={h}d : mean={r.mean():+7.4f} pp | median={np.median(r):+7.4f} pp | "
              f"95% CI [{lo:+7.4f}, {hi:+7.4f}] | P(mean>0)={psign:.4f}")
    # descriptive leg split at the primary horizon (not a gate)
    r, d, _, _ = results[PRIMARY_H]
    # rebuild signs for the kept primary events
    end = np.minimum(ev_day + PRIMARY_H + 1, T)
    c_ = cnt[ev_sym, end] - cnt[ev_sym, ev_day + 1]
    keep = c_ >= 1
    sg = ev_sign[keep]
    print(f"  [descriptive, not a gate] short-leg (top-decile funding) n={int((sg<0).sum())} "
          f"mean={r[sg<0].mean():+.4f} pp | long-leg (bottom-decile) n={int((sg>0).sum())} "
          f"mean={r[sg>0].mean():+.4f} pp")

    mean_p, med_p, lo_p, hi_p, psign_p, _ = eff[PRIMARY_H]
    passed = (lo_p > 0) and (psign_p >= 0.95)
    print(f"  PRIMARY gate: CI-lo={lo_p:+.4f} pp (needs >0), P(sign>0)={psign_p:.4f} (needs >=0.95)")
    if not passed:
        print("  -> KILL_EFFECT")
    else:
        print("  -> PASS")
    print()

    # =====================================================================
    # ECONOMICS
    # =====================================================================
    print("=" * 78); print("ECONOMICS"); print("=" * 78)
    cost_pp = ROUND_TRIP_BP / 100.0
    for h in HORIZONS:
        m = eff[h][0]
        net = m - cost_pp
        ratio = m / cost_pp
        print(f"  h={h}d : gross mean={m:+7.4f} pp | round trip={cost_pp:.3f} pp | "
              f"NET={net:+7.4f} pp | edge/cost={ratio:+6.3f}x")
    m_p = eff[PRIMARY_H][0]
    net_p = m_p - cost_pp
    ratio_p = m_p / cost_pp
    print(f"  PRIMARY h={PRIMARY_H}: net={net_p:+.4f} pp, edge/cost={ratio_p:+.3f}x "
          f"(needs >{ECON_RATIO_MIN})")
    econ_ok = (net_p > 0) and (ratio_p > ECON_RATIO_MIN)
    print()
    print("=" * 78)
    if not passed:
        print("VERDICT: KILL_EFFECT")
    elif not econ_ok:
        print("VERDICT: KILL_ECONOMICS")
    else:
        print("VERDICT: SURVIVES")
    print("=" * 78)


if __name__ == "__main__":
    main()
