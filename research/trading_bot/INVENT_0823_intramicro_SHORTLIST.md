# Frozen shortlist — INVENT_0823 intraday microstructure

Written after the design + null stages, **before** the held-out window was read.

## Design outcome: nothing cleared

| bar | value |
|---|---|
| bootstrap best-of-28 **net** p95 (block=5d, 2000 resamples) | **+1.41** |
| bootstrap best-of-28 **gross** p95 | **+1.40** |
| analytic sqrt(2 ln 28)/sqrt(years) | (reported in `_null.json`, sanity check only) |
| best design **net@1.0bp** of 28 | `E4_PDPOC_MAGNET` **+0.21** |
| best design **gross** of 28 | `F2_LD_REV` **+1.34** |

Zero configs clear rule 1 (net > +1.41). Zero clear rule 4 (gross > +1.40). The single
net-positive config, `E4_PDPOC_MAGNET`, additionally **fails the §3 gap gate**: its net Sharpe
falls from +0.21 (fill at bar s+1) to **−0.03** (fill at bar s+2), i.e. below the required
0.5× and below zero. Per §7 of the pre-registration the theme is therefore reported as
**NOISE** and nothing may be promoted.

## What still runs out of sample, and why

Per §7 the top 3 by design net Sharpe run on the held-out window as a **documented negative
control**, not as candidates:

1. `E4_PDPOC_MAGNET` — design net@1bp +0.21, gap net −0.03, gross +1.12
2. `A5_DRIVE_EX_GAP` — design net@1bp −0.18, gap net −0.42, gross +0.60
3. `G3_LD500_CONT_TOP150` — design net@1bp −0.33, gross +1.11

One extra config is added **explicitly labelled as an addition**, not as a top-3 candidate, to
test whether the *before-cost* signal itself persists (the prior RV sweep's most informative
column was exactly this):

4. `F2_LD_REV` — highest design gross of the 28 (+1.34), design net@1bp −1.54

Panel-B pre-sample (2016-01-04 → 2020-12-31), declared in §1/§2 of the pre-registration, is run
for `G1_LD500_CONT`, `G2_LD500_REV`, `G3_LD500_CONT_TOP150` only, and may not promote or demote
anything.

## Disclosed redundancy

`A2_OD30_FADE` = −`A1_OD30_CONT`, `B2` = −`B1`, `C2` = −`C1`, `D2` = −`D1`, `E2` = −`E1`,
`F2` = −`F1`, `G2` = −`G1` — seven sign-flipped pairs, declared as such in §5 of the
pre-registration and counted as 14 of the 28 draws. They are genuinely two hypotheses each
(continuation vs fade) and the block bootstrap prices their anti-correlation correctly, so the
effective N is not reduced. No two configs returned numerically identical series.
