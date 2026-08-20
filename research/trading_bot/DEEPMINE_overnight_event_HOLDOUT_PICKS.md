# T27 / DEEPMINE overnight-event — hold-out pick list, frozen before the test window is read

Written 2026-08-20, **after** the design sweep and the joint null were written to disk and
**before** `t27_event_overnight.py heldout` had ever been run. The held-out window
(2022-01-03 .. 2026-08-14) has not been evaluated for any config in this family.

## The selection rule

Judge each config on its **tradeable-direction** net statistic. A config whose design
result is negative is traded the other way round, and the mirror pays the same costs
rather than earning them:

    net_mirror = -gross - cost      (not  -(gross - cost))

`t` is the Sharpe measured in its own standard-error units, so `t` is the statistic that
goes against the joint-null bar; the raw max-Sharpe null is inflated by the configs that
trade only 48-300 nights.

**Bar:** the empirical two-sided joint null, 400 within-day permutation replicates, one
permutation shared by all 53 configs so their correlation is preserved, max |t| across the
53 recorded per replicate. Running p95 at rep 125 is **3.31**; final value in
`research/data/t27_cache/null_results.json`.

## Group A — clears the bar (promote to hold-out)

| config | tradeable dir | design t | note |
|---|---|---|---|
| `T03_p10_annnight_excl` | as-specified | +5.43 | T3 with tonight's announcers removed — a T3 restatement, kept as the reference |
| `T01_p10_quiet` | as-specified | +4.92 | T3 on names with no print within ±10 sessions — also a T3 restatement |
| `N07_ann_p10_fade` | as-specified | +3.54 | **the only structurally new formula clearing the bar**: T3's pressure fade run inside tonight's announcer set only |

## Group B — does NOT clear the bar, held out anyway so the report can state the number

These are the structurally new leaders. They are reported as **failures at the design
stage**; their held-out numbers are disclosed rather than hidden, and none of them may be
promoted on a held-out number alone.

| config | tradeable dir | design SR | design t | why disclosed |
|---|---|---|---|---|
| `M03_spy_fomc_eve` | as-specified | +4.71 | +2.06 | highest design Sharpe in the sweep, but only 48 nights |
| `R02_rankpromote_p10` | as-specified | +2.33 | +2.53 | T3 inside the index-add proxy |
| `M02_spy_tom_last` | as-specified | +2.30 | +1.74 | turn-of-month overnight, single instrument |
| `D13_post15_long_vs_xs` | **mirror** | +0.62 | +1.08 | the largest *gross* event effect in the family (short recently-reported names overnight); dies on cost |
| `T02_p10_post15` | as-specified | +1.97 | +2.56 | T3 inside the post-print window |

## What "survives" means

A formula is promotable only if **all** of:

1. its design |t| clears the empirical joint-null p95, **and**
2. its held-out net mean is positive under the T3/M0 cost conventions
   (1.43 bp half-spread on a marketable 15:59 entry, 0.50 bp per auction print,
   30 bp/yr borrow on the short notional), **and**
3. it still clears at 2× spread, 2× auction and 3× borrow, **and**
4. it is not a restatement of T3 — its P&L must carry residual alpha over the
   T3 book on the held-out window, not only on the design window.

`T01` and `T03` fail (4) by construction and are carried only as references.
