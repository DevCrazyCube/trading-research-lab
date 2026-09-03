#!/usr/bin/env python3
"""
NEW PERP LISTING EFFECT — pre-registered event study on the survivorship-complete
Binance USD-M daily panel (919 symbols incl. delisted names).

HYPOTHESIS
  A Binance USD-M perp listing is a mechanical access event on a fixed date. The perp is
  the first time the token can be SHORTED with leverage and no borrow. Under a
  short-sale-constraint-relief mechanism (Miller 1977), the pre-listing price is set by
  the most optimistic holders only; listing admits the pessimists, so the market-controlled
  return AFTER the listing should be NEGATIVE.

  Direction declared: NEGATIVE (short the new perp at the day-0 close).
  Entry is the day-0 CLOSE — the listing-day candle itself is NOT tradable and is excluded.

METHOD (frozen order, stops at first failing gate)
  GATE 1 coverage -> GATE 2 power (computed BEFORE any effect is read) -> GATE 3 effect
  -> economics. Control = same-day cross-sectional MEDIAN log return of the surviving
  universe (mandatory: this control is what inverted the unlock-cliff result).
  Clustering = by event DATE, ICC 0.3. Bootstrap = cluster bootstrap, 5000 draws, seed 20260903.

CLOSURE: new file only. Reads the panel read-only. Writes nothing.
"""
import csv, sys, datetime
import numpy as np

PANEL = "/home/anont/meme/research/data/t23_cache/panel/perp_daily.csv"
DAY_MS = 86_400_000
SEED = 20260903

# ----------------------------------------------------------------------------------
# PRE-REGISTRATION — printed BEFORE any data is read. Nothing below is tuned afterwards.
# ----------------------------------------------------------------------------------
HORIZONS = [1, 3, 7, 30]
PRIMARY_H = 30            # constraint relief needs time to act; the short-horizon reads are secondary
PLAUSIBLE = {1: 3.0, 3: 5.0, 7: 7.0, 30: 10.0}   # pp, generous to the hypothesis
MIN_EVENTS = 200          # coverage kill line
MIN_CLUSTERS = 100        # distinct listing-date clusters
ICC = 0.30
ALPHA_Z = 1.6449          # one-sided alpha=0.05
POWER_Z = 0.8416          # power=0.80
COST_BP = 24.1            # this repo's own MEASURED two-perp round trip; alt/new perps are WORSE
MIN_EDGE_COST_RATIO = 3.0
INCEPTION_GUARD_DAYS = 7  # drop symbols whose first bar is within this of the panel's global start

def prereg():
    print("=" * 88)
    print("PRE-REGISTRATION  (frozen before any data is read)")
    print("=" * 88)
    print("HYPOTHESIS   : market-controlled return after a Binance USD-M perp listing is NEGATIVE.")
    print("               Mechanism: the listing is the first shortable access to the token;")
    print("               short-constraint relief removes the optimists-only price.")
    print("ENTRY        : day-0 CLOSE (listing candle excluded — it is not tradable).")
    print(f"HORIZONS     : day0 -> +{HORIZONS} ; PRIMARY = +{PRIMARY_H}d (family of {len(HORIZONS)} tests).")
    print("CONTROL      : same-day cross-sectional MEDIAN log return of the surviving universe,")
    print("               excluding names inside their own [0,+30] event window; >=30 names/day required.")
    print()
    print(f"GATE 1 COVERAGE kill line : n_events >= {MIN_EVENTS} AND clusters >= {MIN_CLUSTERS}")
    print("               Symbols present at panel inception are DROPPED (data-start artifact, not a listing).")
    print(f"GATE 2 POWER kill line    : MDE (alpha=0.05 one-sided, power=0.80, ICC={ICC}, clustered by")
    print("               event date) must be < HALF the plausible effect, per horizon:")
    for h in HORIZONS:
        print(f"                 +{h:>2}d : plausible {PLAUSIBLE[h]:.1f} pp  ->  MDE must be < {PLAUSIBLE[h]/2:.2f} pp")
    print("GATE 3 EFFECT gate        : on the PRIMARY horizon, ALL THREE must hold:")
    print("                 (a) cluster-bootstrap 95% CI upper bound < 0  (declared short side)")
    print("                 (b) |mean| net of the round trip >= 3x cost, i.e. |mean| >= 0.72 pp")
    print("                 (c) MEDIAN has the SAME SIGN as the MEAN  (short-gamma guard — a")
    print("                     right-skewed loser is what killed the unlock-cliff short)")
    print(f"ECONOMICS    : net = |mean| - {COST_BP:.1f} bp round trip; require edge/cost >= {MIN_EDGE_COST_RATIO:.0f}x.")
    print("STOP RULE    : first failing gate ends the study. No horizon/threshold is re-picked after seeing data.")
    print("=" * 88)
    print()

# ----------------------------------------------------------------------------------
def load_panel():
    syms, days, closes = [], [], []
    with open(PANEL) as f:
        r = csv.reader(f); next(r)
        for row in r:
            syms.append(row[0]); days.append(int(row[1])); closes.append(float(row[2]))
    sym_arr = np.array(syms); day_arr = np.array(days, dtype=np.int64)
    close_arr = np.array(closes, dtype=np.float64)
    usyms, sidx = np.unique(sym_arr, return_inverse=True)
    gmin = day_arr.min(); gmax = day_arr.max()
    didx = ((day_arr - gmin) // DAY_MS).astype(np.int64)
    ndays = int(didx.max()) + 1
    M = np.full((len(usyms), ndays), np.nan)
    M[sidx, didx] = close_arr
    return usyms, M, gmin, gmax, ndays

def ds(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).strftime("%Y-%m-%d")

def main():
    prereg()
    print("Loading panel (read-only) ...")
    usyms, M, gmin, gmax, ndays = load_panel()
    print(f"  panel: {len(usyms)} symbols x {ndays} days, {ds(gmin)} .. {ds(gmax)}")

    # log returns, vectorized, ONE pass
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.log(M[:, 1:] / M[:, :-1])           # R[:, t] is the return INTO day t+1
    R = np.hstack([np.full((len(usyms), 1), np.nan), R])   # align: R[:, t] = return of day t
    R[~np.isfinite(R)] = np.nan

    have = np.isfinite(M)
    first_idx = np.argmax(have, axis=1)
    first_idx = np.where(have.any(axis=1), first_idx, -1)
    last_idx = ndays - 1 - np.argmax(have[:, ::-1], axis=1)

    # ---------------- GATE 1: COVERAGE ----------------
    print()
    print("-" * 88); print("GATE 1 — COVERAGE"); print("-" * 88)
    total = len(usyms)
    inception = first_idx <= INCEPTION_GUARD_DAYS
    print(f"  symbols in panel                                   : {total}")
    print(f"  DROP present at/near panel inception (<= day {INCEPTION_GUARD_DAYS}) : {int(inception.sum())}"
          f"   {list(usyms[inception])}")
    # need +PRIMARY_H days of PANEL (not of the symbol) to avoid right-censoring by data end
    room = first_idx + PRIMARY_H <= ndays - 1
    print(f"  DROP listed < {PRIMARY_H}d before panel end (right-censored) : {int((~room & ~inception).sum())}")
    ok = (~inception) & room & (first_idx >= 0)
    ev_sym = np.where(ok)[0]
    ev_day = first_idx[ev_sym]
    clusters = np.unique(ev_day)
    print(f"  USABLE LISTING EVENTS                              : {len(ev_sym)}")
    print(f"  distinct listing-date clusters                     : {len(clusters)}")
    print(f"  listing dates span                                 : {ds(gmin + int(ev_day.min())*DAY_MS)} .. "
          f"{ds(gmin + int(ev_day.max())*DAY_MS)}")
    sizes = np.bincount(np.searchsorted(clusters, ev_day))
    print(f"  cluster size: mean {sizes.mean():.2f}, max {sizes.max()}")
    # integrity spot-check: a handful of listings against known Binance USD-M launch dates
    print("  integrity spot-check (first panel bar per symbol):")
    for s in ["1000PEPEUSDT", "SUIUSDT", "WLDUSDT", "APTUSDT", "BTCUSDT", "ETHUSDT"]:
        w = np.where(usyms == s)[0]
        if len(w):
            print(f"    {s:<14} first bar {ds(gmin + int(first_idx[w[0]])*DAY_MS)}"
                  f"  last bar {ds(gmin + int(last_idx[w[0]])*DAY_MS)}")
    g1 = len(ev_sym) >= MIN_EVENTS and len(clusters) >= MIN_CLUSTERS
    print(f"  VERDICT: {'PASS' if g1 else 'KILL'}  (line: n>={MIN_EVENTS}, clusters>={MIN_CLUSTERS})")
    if not g1:
        print("\n*** KILLED AT GATE 1 — COVERAGE. STOP. ***"); sys.exit(0)

    # ---------------- market control, built ONCE, vectorized ----------------
    # mask out every symbol inside its own [0, +PRIMARY_H] window from the control universe
    ctrl_mask = np.ones_like(R, dtype=bool)
    for si, d0 in zip(ev_sym, ev_day):
        ctrl_mask[si, d0:min(d0 + PRIMARY_H + 1, ndays)] = False
    Rc = np.where(ctrl_mask, R, np.nan)
    with np.errstate(invalid="ignore"):
        med = np.nanmedian(Rc, axis=0)
    breadth = np.sum(np.isfinite(Rc), axis=0)
    med = np.where(breadth >= 30, med, np.nan)
    print(f"\n  control series built once: {int(np.isfinite(med).sum())}/{ndays} days with >=30 names "
          f"(median daily breadth {int(np.median(breadth))})")

    # abnormal cumulative log return, day0 close -> day0+h close (entry AT day-0 close)
    A = np.where(np.isfinite(R), R - med[None, :], np.nan)
    CA = np.nancumsum(np.nan_to_num(A), axis=1)        # cumulative abnormal, cell-safe
    valid = np.isfinite(A)

    def window_ret(si, d0, h):
        """abnormal log return over (d0, d0+h], truncated at the symbol's LAST bar (delisting kept)."""
        end = min(d0 + h, int(last_idx[si]))
        if end <= d0:
            return np.nan, 0
        seg = A[si, d0 + 1:end + 1]
        good = np.isfinite(seg)
        if good.sum() == 0:
            return np.nan, 0
        return float(np.nansum(seg)), int(end - d0)

    results = {}
    for h in HORIZONS:
        vals, dates, truncs = [], [], 0
        for si, d0 in zip(ev_sym, ev_day):
            if d0 + h > ndays - 1:            # right-censored by panel end for this horizon
                continue
            v, held = window_ret(si, d0, h)
            if not np.isfinite(v):
                continue
            if held < h:
                truncs += 1
            vals.append(v); dates.append(d0)
        results[h] = (np.array(vals), np.array(dates), truncs)

    # ---------------- GATE 2: POWER (before any effect is read) ----------------
    print()
    print("-" * 88); print("GATE 2 — POWER  (computed BEFORE reading any effect)"); print("-" * 88)
    print(f"  {'h':>4} {'n':>6} {'clusters':>9} {'avg_sz':>7} {'resid sd pp':>12} {'DEFF':>6} "
          f"{'n_eff':>8} {'MDE pp':>8} {'line pp':>8}  verdict")
    power = {}
    for h in HORIZONS:
        vals, dates, truncs = results[h]
        pct = (np.expm1(vals)) * 100.0          # residual return in pp (already market-controlled)
        n = len(pct); cl = len(np.unique(dates))
        sd = float(np.std(pct, ddof=1))
        avg = n / cl
        deff = 1 + (avg - 1) * ICC
        neff = n / deff
        mde = (ALPHA_Z + POWER_Z) * sd / np.sqrt(neff)
        line = PLAUSIBLE[h] / 2
        ok_h = mde < line
        power[h] = (n, cl, sd, deff, neff, mde, line, ok_h, truncs)
        print(f"  +{h:>3} {n:>6} {cl:>9} {avg:>7.2f} {sd:>12.2f} {deff:>6.3f} {neff:>8.1f} "
              f"{mde:>8.3f} {line:>8.2f}  {'PASS' if ok_h else 'KILL'}")
    print(f"  (truncated-at-delisting events kept, not dropped: "
          f"{ {h: power[h][8] for h in HORIZONS} })")
    g2 = power[PRIMARY_H][7]
    print(f"  PRIMARY horizon +{PRIMARY_H}d VERDICT: {'PASS' if g2 else 'KILL'}")
    if not g2:
        print("\n*** KILLED AT GATE 2 — POWER. STOP. ***"); sys.exit(0)

    # ---------------- GATE 3: EFFECT ----------------
    print()
    print("-" * 88); print(f"GATE 3 — EFFECT  (cluster bootstrap by event DATE, 5000 draws, seed {SEED})")
    print("-" * 88)
    rng = np.random.default_rng(SEED)
    eff = {}
    print(f"  {'h':>4} {'n':>6} {'cl':>5} {'mean pp':>9} {'median pp':>10} {'CI2.5':>9} {'CI97.5':>9} "
          f"{'P(mean<0)':>10}")
    for h in HORIZONS:
        vals, dates, _ = results[h]
        pct = np.expm1(vals) * 100.0
        ucl = np.unique(dates)
        groups = [pct[dates == c] for c in ucl]
        k = len(ucl)
        boot = np.empty(5000)
        for b in range(5000):
            pick = rng.integers(0, k, k)
            boot[b] = np.concatenate([groups[i] for i in pick]).mean()
        lo, hi = np.percentile(boot, [2.5, 97.5])
        m, md = float(pct.mean()), float(np.median(pct))
        p_neg = float((boot < 0).mean())
        eff[h] = (m, md, lo, hi, p_neg, len(pct), k)
        star = "  <== PRIMARY" if h == PRIMARY_H else ""
        print(f"  +{h:>3} {len(pct):>6} {k:>5} {m:>9.2f} {md:>10.2f} {lo:>9.2f} {hi:>9.2f} {p_neg:>10.4f}{star}")

    m, md, lo, hi, p_neg, n, k = eff[PRIMARY_H]
    cost_pp = COST_BP / 100.0
    a = hi < 0
    b = abs(m) >= MIN_EDGE_COST_RATIO * cost_pp
    c = (np.sign(md) == np.sign(m)) and md != 0
    print(f"\n  effect gate (a) CI upper < 0 ............... {hi:>8.2f} pp   {'PASS' if a else 'FAIL'}")
    print(f"  effect gate (b) |mean| >= 3x cost ({3*cost_pp:.2f} pp) . {abs(m):>8.2f} pp   {'PASS' if b else 'FAIL'}")
    print(f"  effect gate (c) median sign == mean sign ... mean {m:+.2f} / median {md:+.2f}   "
          f"{'PASS' if c else 'FAIL'}")
    g3 = a and b and c
    print(f"  VERDICT: {'PASS' if g3 else 'KILL'}")

    # ---------------- ECONOMICS ----------------
    print()
    print("-" * 88); print("ECONOMICS"); print("-" * 88)
    gross = abs(m)
    net = gross - cost_pp
    print(f"  gross |mean| market-controlled edge, +{PRIMARY_H}d : {gross:.3f} pp")
    print(f"  measured two-perp round trip (this repo)          : {cost_pp:.3f} pp ({COST_BP:.1f} bp) "
          f"— a FLOOR; a day-0 new listing is the widest book on the venue")
    print(f"  NET per trade                                    : {net:+.3f} pp")
    print(f"  EDGE / COST RATIO                                : {gross/cost_pp:.2f}x "
          f"(require >= {MIN_EDGE_COST_RATIO:.0f}x)")
    print(f"  sign of the trade as declared (SHORT)            : realised {'+' if m>0 else '-'}"
          f"{abs(m):.2f} pp -> short P&L {-m:+.2f} pp gross")
    if not g3:
        print("\n*** KILLED AT GATE 3 — EFFECT. ***")
    else:
        print("\n*** SURVIVES ALL GATES ***" if net > 0 else "\n*** KILLED AT ECONOMICS ***")

if __name__ == "__main__":
    main()
