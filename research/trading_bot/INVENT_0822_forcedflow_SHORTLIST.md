# DESIGN-WINDOW SHORTLIST — frozen before the held-out was evaluated

**Written 2026-08-22, after the design pass (2016-01-04 … 2021-12-31) and BEFORE any
2022-2026 number was computed.** These are the only formulas whose held-out results are
allowed to count as confirmation; everything else in the 47 is already a design-window
failure and its held-out number is reported for completeness only.

| rank | formula | design mean/event | design clustered t | design SR | tradable? |
|---|---|---:|---:|---:|---|
| 1 | `F12_SP600ADD_RUNUP5` | +936 bp | **+7.45** | 3.99 | **NO** — entry at R−5 presumes the S&P announcement is already public |
| 2 | `F15_PROMOTE_RUNUP5` | −377 bp | **−6.76** | −2.27 | **NO** — same, and sign-flipped |
| 3 | `F37_PROMOTE_REB5` | +136 bp | **+3.09** | 1.32 | yes (entry at the R close) |
| 4 | `F20_ALLADD_LAST1` | −105 bp | −2.71 | −1.10 | mild (entry at R−1) |
| 5 | `F42_MIG_400to500_R5` | −80 bp | −2.62 | −1.01 | yes |
| 6 | `F44_MIG_600to400_R5` | +264 bp | +2.39 | 1.89 | yes, but n=27 |
| 7 | `F35_MIGPAIR_REB5` | +172 bp | +2.04 | 0.61 | yes |
| 8 | `F16_PROMOTE_REV20` | −247 bp | −2.01 | −0.91 | yes |

**Added after the corporate (EDGAR) families landed, still before any held-out evaluation:**

| rank | formula | design mean/event | design clustered t | design SR | tradable? |
|---|---|---:|---:|---:|---|
| A | `F27_SEC424B5_REB5` | **−98 bp** | **−5.86** | −1.79 | yes — but the sign is FLIPPED: the trade is to **SHORT** after the takedown, n=3336 |
| B | `F29_SEC424B5_PRE` | −194 bp | −6.02 | −2.24 | **NO** — the filing date is not knowable ex ante |
| C | `F28_SEC424B5_REB20` | −141 bp | −4.35 | −1.65 | yes, same flipped sign |
| D | `F24_LOCKUP_PRE` | +79 bp | +1.90 | +1.00 | yes, and the pre-registered sign was RIGHT |

`F27` is the only candidate in the whole theme that clears the pooled 3.28 bar on design gross.
Four things must be said about it **before** the held-out is looked at:

1. **The sign is flipped.** I predicted a post-placement rebound as the overhang clears. The data
   says the opposite — a shelf takedown is followed by five more days of underperformance. Two-
   sided bar applies.
2. **`424B5` is not a pure equity-offering signal.** The form covers every shelf takedown,
   including investment-grade note issuance and MTN programmes that dilute nobody. The sample is
   a mixture, so the measured effect is *diluted*, not inflated.
3. **`F29` shows the stock is already falling before the filing** (−194 bp over F−5…F−1). So the
   post-filing move may be plain continuation of a name in decline rather than placement
   pressure. That is a competing explanation the held-out cannot settle on its own.
4. **Survivorship runs in the conservative direction here.** The CIK→ticker map is today's SEC
   file, so issuers that went bankrupt after diluting are missing; their absence biases measured
   post-offering returns *up*, i.e. against the short.
5. **It is a SHORT in small caps.** Borrow availability and borrow cost are not in this data at
   all, and the `B22G_BORROW_COST` work in this repo exists precisely because that is where such
   signals die. No promotion is possible without it.

**Bars:** one-sided `sqrt(2 ln 47)` = **2.78**; two-sided `sqrt(2 ln 94)` = **3.02** (the
relevant one for every sign-flipped candidate, which is most of this list); pooled cross-round
bar carried in from earlier rounds = **3.28**.

**Read before the held-out:** exactly one tradable formula (`F37`, t = 3.09) is above the
two-sided within-theme bar, and **nothing is above the pooled bar**. The two enormous t-stats
are both in the pre-effective window, where the entry date presumes knowledge of an
announcement whose date this data does not contain — they are mechanism evidence, not signals.

**Design-window stability of `F37`** (checked before the held-out): positive in all six years
(2016 +0.61%, 2017 +0.82%, 2018 +0.77%, 2019 +2.98%, 2020 +2.61%, 2021 +0.88%) and positive in
both transition types (`400→500` +0.80% n=62, `600→400` +2.64% n=27). It is not one year and
not one sub-type.

**The mechanism problem with `F37`, stated before the held-out:** F37 is the pooled
"promotions" book, and block 4 shows the pooling mixes a huge mandated NET BUY (`400→500`, the
new index owns ~20% of float vs ~4% in the old) with a modest mandated NET SELL (`600→400`).
Temporary price pressure predicts these two carry OPPOSITE post-R signs. They do not — both are
positive. So whatever F37 measures, **it is not the reversal of a mandated flow**; it looks like
post-migration drift. A held-out confirmation would make it a real but *misattributed* effect,
and it would then have to be re-examined against the already-dead momentum family rather than
promoted as forced-flow alpha.
