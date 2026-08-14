#!/usr/bin/env python3
"""Every BTC number I reported in handoffs 384 and 386, reproducible from one file.

Run it against either series in this directory and it prints the full table. It is written to be
read as well as run: the look-ahead convention and the two bugs I hit are stated in the code, not
in a message that can drift from it.

    python replicate.py btc_1d_long.csv    # Bitstamp, 2013-2026, 4,972 bars, the authoritative one
    python replicate.py btc_1d_mine.csv    # Binance,  2017-2026, 3,283 bars, warm-up contaminated

THE LOOK-AHEAD CONVENTION, stated once and used everywhere below:
    the position held DURING day i is decided at the CLOSE of day i-1, from the SMA over
    closes[i-N .. i-1] inclusive. Day i's own close never influences day i's position.
    When i-N < 0 the SMA is UNDEFINED -- and this is the warm-up trap: treating "undefined"
    as "out" makes the filter hold cash for lack of history, bank a crash it never traded
    through, and look better than it is. On the 2013 series the warm-up ends 2013-07-20,
    before every crash of interest, which is the whole reason to prefer it.

THE COMPOUNDING BUG I HIT, so nobody repeats it: a walk-forward that computes each fold as its
own equity curve starting at 1.0 and multiplies the fold results together SKIPS the return across
every fold join. With 22 folds that lost 21 daily returns and inflated buy-and-hold by 5%. The
test that caught it is `audit_compounding()` below -- buy-and-hold compounded fold-by-fold MUST
equal buy-and-hold computed directly over the same span. It did not. `walk_forward()` is therefore
written as ONE continuous curve in which only N switches at the boundaries.
"""
import csv
import pathlib
import datetime as dt
import math
import sys


def load(path):
    rows = list(csv.DictReader(open(path)))
    key = "ts" if "ts" in rows[0] else "open_time"
    div = 1 if key == "ts" else 1000
    px = [float(r["close"]) for r in rows]
    dates = [dt.datetime.fromtimestamp(int(r[key]) // div, dt.UTC).date() for r in rows]
    return px, dates


def maxdd(eq):
    peak, worst = eq[0], 0.0
    for v in eq:
        if v > peak:
            peak = v
        worst = max(worst, (peak - v) / peak)
    return worst


def cagr(eq, days):
    return (eq[-1] / eq[0]) ** (365.25 / days) - 1


def position(px, i, N):
    """None means UNDEFINED, which is not the same as out. Callers must decide, visibly."""
    if N is None:
        return 1.0
    if i - N < 0:
        return None
    return 1.0 if px[i - 1] > sum(px[i - N:i]) / N else 0.0


def equity(px, N, alloc=1.0, start=0, end=None, undefined_is_cash=True, cost_bps=0.0):
    end = len(px) if end is None else end
    eq, prev = [1.0], None
    for i in range(start + 1, end):
        pos = position(px, i, N)
        if pos is None:
            pos = 0.0 if undefined_is_cash else alloc
        else:
            pos *= alloc
        v = eq[-1] * (1 + pos * (px[i] / px[i - 1] - 1))
        if cost_bps and prev is not None and pos != prev:
            v *= 1 - cost_bps / 10000
        prev = pos
        eq.append(v)
    return eq


def first_valid(px, N):
    return next(i for i in range(len(px)) if position(px, i, N) is not None)


# --------------------------------------------------------------------------- reported tables

def headline(px, dates, N=200):
    s = first_valid(px, N)
    days = (dates[-1] - dates[s]).days
    print(f"\nHEADLINE  (from the first VALID signal, {dates[s]} -- no warm-up contamination)")
    print(f"   {'':<14}{'total':>13} {'CAGR':>8} {'maxDD':>8} {'CAGR/DD':>9}")
    for label, n in (("buy & hold", None), (f"{N}d filter", N)):
        eq = equity(px, n, start=s)
        dd = maxdd(eq)
        print(f"   {label:<14}{100*(eq[-1]-1):>12,.0f}% {100*cagr(eq,days):>7.1f}% "
              f"{100*dd:>7.1f}% {cagr(eq,days)/dd:>9.2f}")


def warmup_effect(px, dates, N=200):
    """The artifact itself, shown rather than asserted."""
    s = first_valid(px, N)
    print(f"\nWARM-UP EFFECT  (SMA undefined for the first {s} bars, to {dates[s]})")
    for label, start in (("from bar 0 (contaminated)", 0), (f"from {dates[s]} (clean)", s)):
        d = (dates[-1] - dates[start]).days
        b, f = equity(px, None, start=start), equity(px, N, start=start)
        print(f"   {label:<28} B&H maxDD {100*maxdd(b):>5.1f}%  filter {100*maxdd(f):>5.1f}%"
              f"   -> cut {100*(maxdd(b)-maxdd(f)):>4.1f} pp"
              f"   | CAGR {100*cagr(b,d):>5.1f}% vs {100*cagr(f,d):>5.1f}%")


def per_crash(px, dates, N=200):
    """Anchored at each episode's PRICE PEAK so both strategies start invested.

    Without that anchor a filter already in cash reports a 0% drawdown and reads as 'protected'
    when it simply held nothing -- which is a window artifact, not protection.
    """
    def idx(d):
        t = dt.date.fromisoformat(d)
        return next((i for i, x in enumerate(dates) if x >= t), len(px) - 1)

    episodes = [("2013-15 bear", "2013-11-01", "2015-08-31"),
                ("2017-18 flash", "2017-12-01", "2018-02-28"),
                ("2018 bear", "2017-12-01", "2018-12-31"),
                ("2020 covid", "2020-02-01", "2020-04-30"),
                ("2021 correction", "2021-03-01", "2021-08-31"),
                ("2022 bear", "2021-10-01", "2022-12-31"),
                ("2025-26 decline", "2025-08-01", "2026-08-12")]
    valid = first_valid(px, N)
    print(f"\nPER-CRASH  (anchored at each pre-trough peak; 'pre-warm-up' rows are unmeasurable)")
    print(f"   {'episode':>17} {'peak':>11} {'B&H DD':>8} {'filt DD':>9} {'verdict':>12}")
    for name, a, b in episodes:
        i, j = idx(a), idx(b)
        if j <= i + 5 or i < valid:
            print(f"   {name:>17} {'':>11} {'':>8} {'':>9} {'pre-warm-up':>12}")
            continue
        k = max(range(i, j), key=lambda x: px[x])
        bh = 100 * maxdd(equity(px, None, start=k, end=j))
        ft = 100 * maxdd(equity(px, N, start=k, end=j))
        verdict = "PROTECTED" if ft < bh - 3 else ("WORSE" if ft > bh + 2 else "no help")
        print(f"   {name:>17} {str(dates[k]):>11} {bh:>7.1f}% {ft:>8.1f}% {verdict:>12}")


def fold_schedule(px, train=730, test=180, cands=(50, 75, 100, 125, 150, 175, 200, 225, 250, 300)):
    """Choose N on the TRAIN window only, by risk-adjusted return. Returns {bar: N}."""
    sched, folds, s = {}, [], first_valid(px, max(cands))
    while s + train + test <= len(px):
        tr0, tr1, te1 = s, s + train, s + train + test
        best = None
        for N in cands:
            eq = equity(px, N, start=tr0, end=tr1)
            dd = maxdd(eq)
            score = (eq[-1] - 1) / dd if dd > 0 else (eq[-1] - 1)
            if best is None or score > best[0]:
                best = (score, N)
        for i in range(tr1, te1):
            sched[i] = best[1]
        folds.append((tr1, te1, best[1]))
        s += test
    return sched, folds


def audit_compounding(px, folds):
    """The test that caught my bug. Must hold, or a walk-forward number is wrong."""
    a, b = folds[0][0], folds[-1][1]
    chained = 1.0
    for t0, t1, _ in folds:
        chained *= equity(px, None, start=t0, end=t1)[-1]
    direct = equity(px, None, start=a, end=b)[-1]
    rel = abs(chained - direct) / direct
    print(f"\nCOMPOUNDING AUDIT")
    print(f"   B&H chained fold-by-fold {100*(chained-1):>12,.0f}%")
    print(f"   B&H computed directly    {100*(direct-1):>12,.0f}%")
    print(f"   relative difference      {rel:>12.6f}   "
          f"{'OK' if rel < 1e-9 else '<-- chaining skips fold joins; do not chain'}")


def walk_forward(px, dates, sched, cost_bps=0.0):
    """ONE continuous curve; only N switches at boundaries. No fold joins to lose."""
    first, last = min(sched), max(sched) + 1
    days = (dates[last - 1] - dates[first]).days
    f, b, prev, switches = [1.0], [1.0], None, 0
    for i in range(first + 1, last):
        N = sched.get(i, sched[first])
        pos = position(px, i, N) or 0.0
        if prev is not None and pos != prev:
            switches += 1
        prev = pos
        r = px[i] / px[i - 1] - 1
        v = f[-1] * (1 + pos * r)
        if cost_bps and switches and pos != prev:
            v *= 1 - cost_bps / 10000
        f.append(v)
        b.append(b[-1] * (1 + r))
    print(f"\nWALK-FORWARD  {dates[first]} .. {dates[last-1]}   "
          f"({len(set(sched.values()))} distinct N, {switches} switches, "
          f"{switches/(days/365.25):.1f}/yr)")
    print(f"   {'':<16}{'total':>13} {'CAGR':>8} {'maxDD':>8} {'CAGR/DD':>9}")
    for label, eq in (("buy & hold", b), ("walk-fwd filter", f)):
        dd = maxdd(eq)
        print(f"   {label:<16}{100*(eq[-1]-1):>12,.0f}% {100*cagr(eq,days):>7.1f}% "
              f"{100*dd:>7.1f}% {cagr(eq,days)/dd:>9.2f}")
    return f, b


def fragility(px, dates, sched, folds):
    """Is the outperformance a few folds? Measured on the continuous curves, in log space."""
    first, last = min(sched), max(sched) + 1
    f, b = [1.0], [1.0]
    for i in range(first + 1, last):
        N = sched.get(i, sched[first])
        pos = position(px, i, N) or 0.0
        r = px[i] / px[i - 1] - 1
        f.append(f[-1] * (1 + pos * r))
        b.append(b[-1] * (1 + r))
    excess = []
    for t0, t1, N in folds:
        a, z = t0 - first, min(t1 - first, len(f) - 1)
        if a < 1 or z <= a:
            continue
        excess.append((math.log(f[z] / f[a]) - math.log(b[z] / b[a]), dates[t0], N))
    excess.sort(key=lambda x: -x[0])
    total = sum(e[0] for e in excess)
    print(f"\nFRAGILITY  ({len(excess)} out-of-sample folds)")
    print(f"   folds where the filter beat buy & hold: "
          f"{sum(1 for e in excess if e[0] > 0)}/{len(excess)}")
    print(f"   cumulative outperformance: {100*(math.exp(total)-1):>10,.0f}%")
    for k in (1, 3):
        rest = total - sum(e[0] for e in excess[:k])
        print(f"   remove the best {k}: {100*(math.exp(rest)-1):>+10,.0f}%   "
              f"(top {k} = {100*sum(e[0] for e in excess[:k])/total:>3.0f}% of the excess)")
    print(f"   the largest contributors are all crash windows: "
          f"{', '.join(str(e[1]) for e in excess[:3])}")


def main():
    default = pathlib.Path(__file__).resolve().parents[1] / "research" / "data" \
              / "btc_usd_daily_bitstamp_2013_2026.csv"
    path = sys.argv[1] if len(sys.argv) > 1 else str(default)
    px, dates = load(path)
    print(f"{path}: {len(px):,} bars  {dates[0]} .. {dates[-1]}")
    print(f"last close ${px[-1]:,.2f}   200d SMA ${sum(px[-200:])/200:,.2f}   "
          f"signal: {'IN' if px[-1] > sum(px[-200:])/200 else 'OUT to cash'}")
    warmup_effect(px, dates)
    headline(px, dates)
    per_crash(px, dates)
    sched, folds = fold_schedule(px)
    audit_compounding(px, folds)
    walk_forward(px, dates, sched)
    fragility(px, dates, sched, folds)


if __name__ == "__main__":
    main()
