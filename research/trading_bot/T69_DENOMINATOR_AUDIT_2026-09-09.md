# T69 — the denominator lens applied to the remaining forward instruments (2026-09-09, CHUNK B)

Read-only audit. Nothing patched, no frozen text moved, no gate date changed.

**The lens (from T67).** For every gate: is its DENOMINATOR derived from a calendar/schedule,
or only from units the instrument happened to OBSERVE? An observed-unit denominator cannot
represent its own absence, so it can only ever fake a PASS, never a fail. T67 covered T31 and
T33. This covers the rest.

| Instrument | Gate | Denominator | Direction of the error | Verdict |
|---|---|---|---|---|
| **T30_BORROW** | 30 **clean days** | absolute count, no ratio | a lost day DELAYS the read one-for-one | **SAFE** |
| **T45_ETF_LIQ** | K1 = <4 events with data by day 21; PASS at N≥30 events | observed events, against a **calendar** day-21 clock | a shortfall FIRES K1 (BLOCKED_ON_DATA) | **SAFE** on the gate; see D1 below |
| **BASKET1** | per-leg kill at `n_L ≥ N_min = 40` settled obs; retirement at `N_max = 500` | observed **firings** | see B1 — a dormant leg is immortal | **DEFECT (B1)** |
| **NEWSDESK1** | HALT at `n ≥ N_min = 30` resolved setups | observed resolutions | currently exact (2 setups, 2 resolved, 0 open) | **SAFE today, structurally exposed** |
| **PREDMARKET1** | HALT/verdict at `n ≥ N_min = 50` resolved markets | observed resolutions, and resolution is a function of `close_time` | see P1 | **DEFECT (P1)** |
| **T35 convexity** | N_min ≥ 40 clusters **and ≤10 % of trades dropped** for missing expiry-day snapshots | observed clusters, with an explicit drop-rate cap that forces UNDECIDED | the drop cap is the correct construction; see C1 caveat | **GUARDED — the template** |

## B1 — BASKET1: "ALIVE" is printed for legs that have produced zero evidence

Both §7a (`N_min = 40`) and §7b (`N_max = 500`) are denominated in **settled observations**, and
a leg only accrues an observation when its signal FIRES. There is no calendar backstop anywhere
in the prereg for a leg that never fires. Measured on the newest ledger row (12 sessions,
2026-08-20 → 09-04):

```
T3 n=10   ETFRV n=1   CEFMUNIEQ CRYPTO_LOWVOL DUALCLASS DUALCLASS_EXIT10 ETFRV_Z20 ORB
SKEW_TILT SKEW_TILT_CRUDE T12CEF T7 XS_GLSR_Z XS_SMART  = n=0
```

**12 of 14 legs sit at n=0 and every one of them reports `verdict: ALIVE`.** In the report
`ALIVE` is textually identical for a leg that survived 40 observations and for a leg that has
never traded. A never-firing leg can be neither killed (needs n≥40) nor retired (needs n≥500):
it is immortal by non-observation, and it keeps counting in `declared_trials_now`, so it inflates
the multiple-testing cost of the legs that *do* fire without ever being at risk itself.

This is **not** a reason to touch BASKET1 — the clock is locked (hard rule 2026-08-24) and the
kill switch is frozen. It is a reason to stop reading `ALIVE` as information. The honest reading
of the current basket is: **one leg (T3, n=10) is accumulating evidence, one (ETFRV, n=1) has
barely started, and twelve are unmeasured.** Any future basket-shaped instrument must carry a
calendar-denominated dormancy rule ("a leg that has not fired in K sessions is WITHDRAWN, not
alive") declared before day 0.

## P1 — PREDMARKET1: 20 % of the frozen book can never enter the verdict, and the exclusion is
known at freeze time

Measured over the 76 frozen estimates (39 further records are abstentions):

```
close_time by month: 2026-09 15 | 2026-10 12 | 2026-11 11 | 2026-12 24 | 2027-01 12 | 2029 2
closes on/before 2026-12-31: 61        closes AFTER 2026-12-31: 15  (19.7 %)
resolved so far: 1 of 76   (2244513 Sachsen-Anhalt, closed 09-06)
```

The correlated-book note (2026-09-06) already established that `N_min = 50` is crossed only when
a 24-market lump settles on 2026-12-31. The additive point here is the **other** side of that
denominator: **15 of 76 estimates cannot be in it at all**, because they close in 2027 or 2029,
and their exclusion is fully determined by `close_time`, a field known when the estimate was
frozen. So the sample the verdict is computed on is not the sample that was pre-registered — it
is the short-dated subset of it, selected on horizon. Horizon is not plausibly independent of
calibration skill (a stale-knowledge agent is differently wrong on a two-week election than on a
three-year one), so this is a selection, not a random thinning. Nothing in the ledger marks those
15 records as excluded-by-construction.

Second, smaller: settlement LAGS close. 24 estimates close ON 2026-12-31, so a verdict read on
that date sees fewer than 60 resolutions and may sit below `N_min` while appearing to have
crossed it.

## C1 — the convexity caveat (does not change its GUARDED verdict)

T35's `≤10 % dropped` cap is denominated in **trades the panel generated**, and a trade only
exists if its ENTRY-day snapshot exists. A date on which the collector never ran produces no
trade at all, so it is invisible to the drop ratio; it shrinks N instead (→ UNDECIDED, the safe
direction). The drop statistic therefore understates total data loss. T67's calendar gate at
~09-23 / ~10-06 and T72's gap reader are the compensating measurements; the cap itself is sound.

## D1 — T45 keeps no per-date attendance record at all

`research/data/etf_liquidation_forward/state.json` holds `last_scan` (one scalar) and
`seen_accessions`. There is **no per-date scan record**, so T45 scan attendance cannot be
reconstructed for any past date — T72 reports it `UNMEASURABLE` rather than complete. This is
the same fact as T62_t45_d1 (an attempt proxy), now stated as an absence of evidence rather than
a weak proxy. It does not endanger K1 (a shortfall fires the block), but it means "T45 was
scanning" is not a claim we can ever verify after the fact.

## What was NOT re-litigated
The T31/T33 `len(days)` defect (T67, closed), the predmarket i.i.d. SE over a correlated book
(T60, open), the free-data convexity wall.
