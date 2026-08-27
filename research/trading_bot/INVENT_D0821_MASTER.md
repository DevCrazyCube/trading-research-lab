# INVENT D0821 — MASTER SYNTHESIS

**202 formulas. Four fresh-angle themes. Zero promotions.**

The round's largest correctly-signed design t-statistic is **+3.08**. The expected maximum
under the pooled null is **+3.26**. A search of 202 pure-noise formulas would, on average, have
produced a *better* winner than the one this round actually found. That is the whole result, and
it is not a close call dressed up as one.

Three of the four themes declared themselves noise on their own within-theme bars. The fourth
(seasonality-with-a-mechanism) found one signal that clears its *panel-local* correlation-aware
null (joint p = 0.026) and is positive out of sample net of cost — and it still fails the pooled
bar. It is **not promoted**. It goes to the forward log at **zero size**.

Date: 2026-08-21. Synthesised from four independent theme agents.
Basket unchanged: **T3 overnight reversal, ETF-sibling RV, dual-class RV, T7 ex-open,
T12 CEF discount tilt, XS_GLSR_Z (decaying, logging-only)**. No leg added, no leg removed.

---

## 1. The pooled multiple-testing bar

| convention | N | bar (t-units) |
|---|---|---|
| **D0821 pooled, analytic** | 202 | **3.258** ← headline |
| D0821 pooled, sign-agnostic (sign fit on design ⇒ 2N) | 404 | 3.465 |
| programme-cumulative (863 through round 3 + 202) | 1065 | 3.734 |

`E[max |t|] ≈ sqrt(2 ln N)`. The four searches were commissioned together, run on the same
weekend, and are being read together — so the pooled bar is the one that binds, not the
within-theme bar each agent computed for itself (2.66–2.98 analytic).

Converted to Sharpe units on each theme's own design window (`bar / sqrt(years)`):

| theme | design span | years | Sharpe SE | within-theme bar | **pooled bar (N)** | pooled (2N) |
|---|---|---|---|---|---|---|
| XS equity factor | 2016-02 … 2021-10 | 5.60 | 0.423 | 1.26 | **1.38** | 1.46 |
| Vol term structure → direction | 2010 … 2019-12 | 8.88 | 0.336 | 0.95 (bootstrap) | **1.09** | 1.16 |
| Seasonality, ETF panel | 2003-05 … 2013-12 | 10.66 | 0.306 | 0.91 | **1.00** | 1.06 |
| Seasonality, stock panel | 2016-01 … 2021-12 | 6.00 | 0.408 | 1.21 | **1.33** | 1.41 |
| Crypto spot XS | 2019-01 … 2023-01 | 4.00 | 0.500 | 1.45 | **1.63** | 1.73 |

---

## 2. What the round actually produced

| theme | N | best design t (correct sign) | held-out | verdict |
|---|---|---|---|---|
| XS equity factor, fresh structures | 84 | **+0.78 net** (+2.32 gross) | best net SR +0.28 (t 0.60) | **NOISE** |
| Vol term structure as directional timing | 43 | **+2.63** (bootstrap p 0.63) | +0.27 SR (t 0.69) | **NOISE** |
| Seasonality with a mechanism | 41 | **+3.08** (P02, gross) | +0.37 net SR (t 1.33) | 5 of 6 mechanisms noise; 1 sub-bar candidate |
| Crypto spot cross-section | 34 | **+2.86 net** | +0.03 SR (t 0.07) | **NOISE** |
| **pooled** | **202** | **+3.08** | — | **max < E[max under null] = 3.26** |

The single largest |t| anywhere in the round is **3.21** — and it carries the **wrong sign**
(tax-loss-harvesting: prior-year losers kept *losing* in January, the opposite of the mechanism
that was pre-registered). By the programme's sign rule that is a failed prediction, not a finding.

Three of the four themes never even reached their own within-theme bar, so no pooled correction
was needed to kill them. Pooling only mattered for one formula, and it killed that one too.

---

## 3. The one candidate, and why it is not promoted

**P02_PENSION_MEQ_MAG** — balanced-mandate month-end rebalance fade.
A fixed-weight 60/40 plan document *obliges* the manager to sell whatever outperformed inside the
period before the period boundary. So the signal is not a date: it is minus the month-to-date
divergence between the equity and bond sleeves (z-scored on a causal 750-session trailing scale,
clipped at 2.5 SD), expressed as a vol-scaled SPY-vs-IEF spread held **only over the last 4
sessions of the month**. ~0.46× gross notional, active on 19% of sessions, two trades a month.

**Evidence for:**
- Design gross Sharpe 0.94 (t = 3.08) — observed max of the 22-formula ETF panel, whose
  correlation-aware joint null (20k replicates, sign drawn once per 21-session block and shared
  across formulas) gives **joint p = 0.026**.
- Held-out 2014-01 … 2026-08, **12.6 untouched years**: net Sharpe **+0.37** (t = 1.33),
  **+0.29 at 2× measured cost**, gross +0.46. Positive net of realistic cost.
- Passes four kill questions: not one crisis (design SR 0.80 ex-2008/09, net-positive in 9 of 11
  design years); it is the *deadline* not the lookback (fair placebo: the same 15-session signal
  held in five different month positions gives 0.75/0.49 in the last-4 bucket vs −0.31…+0.16
  mid-month and 0.23/0.23 every-session base rate); it is not a bare calendar effect
  (unconditional month-end SPY is 0.26/0.26 either way — the flow conditioning does the work);
  family-coherent (6 of 7 members keep their sign into held-out gross).
- Leg attribution (post-hoc): almost all of it is the **equity** leg. SPY-only design 0.60
  (t 2.74), held-out 0.69 (t 2.46), stable to 1- and 2-session signal lag (0.61/0.64) and 3× cost.

**Why it is still not promoted:**
- Design t **3.08 < pooled bar 3.258** (and < 3.465 sign-agnostic, and far below the
  programme-cumulative 3.73). It clears its *panel* null by a hair and the *round* null not at all.
- Held-out t 1.33 is individually indistinguishable from zero.
- The theme as a whole lost **91% of its design Sharpe out of sample** (mean net design +0.205 →
  +0.018), 22 of 41 design-selected signs survived out of sample (a coin flip), and
  corr(design, held-out) = 0.335. That is the base rate this candidate sits inside.

**Disposition:** forward-log only, **zero size**, against `BASKET_FORWARD_LOG`. Design and
held-out are both spent; the only uncontaminated evidence left is forward. Revisit at
**60 rebalance events** (≈5 years at two trades a month) — with the honest acknowledgement that
this is a slow, low-information clock and the realistic outcome is that it is never promoted.

**Guard if it were ever sized (it is not, this round):** SPY-vs-IEF only, ≤0.5× gross, last 4
sessions of the month only, z clipped at 2.5 SD, hard kill if the SPY-only leg's trailing
12-month Sharpe goes negative or the design sign flips over 12 consecutive rebalances.

**Diversification vs BASKET1:** yes, genuinely. Every alive leg is a relative-value or
short-horizon reversal book on US single names / ETF pairs / perps (T3 overnight reversal,
ETF-sibling RV, dual-class RV, T7 ex-open, T12 CEF discount, XS_GLSR_Z). P02 is a **directional
equity-vs-duration overlay on a monthly cadence driven by mandated asset-allocation flow** —
different instrument set (SPY/IEF), different holding clock (4 sessions/month, 19% duty cycle),
different economic driver. Its overlap with the basket is close to structural zero. That is
exactly why it was tempting, and it is not a reason to override the bar.

---

## 4. Three honest zeros, stated as findings rather than absences

**(a) US equity cross-section — 216 cells now, nothing alive.** 84 new cells here (28 signals ×
h∈{1,3,5}) pooled with the 132-cell NEWTERR xs_equity sweep on the same panel, universe, cost
model and fills. Best net t across all of it: **+0.89**. The durable output is a *measured cost
wall*, not a null: factor-neutralisation buys Sharpe by cutting variance, not by earning more per
unit of turnover, and the economics get **worse** as you neutralise. Ladder at h=1
(gross SR / gross bp-per-day / break-even one-way):

| variant | gross SR | bp/day | break-even |
|---|---|---|---|
| raw REV1 | +0.78 | 4.41 | 2.68 bp |
| market-beta residual | +0.69 | 2.74 | 1.70 bp |
| statistical-sector demeaned | +0.77 | 3.20 | 1.93 bp |
| full multi-factor residual (FR_REV1) | **+1.04** | 3.71 | 2.23 bp |
| risk-normalised | +0.97 | 2.54 | 1.44 bp |
| peer-basket relative | +0.38 | 1.25 | 0.76 bp |

FR_REV1 has the best gross Sharpe in the study (+33% over raw REV1) and a *lower* break-even than
the signal it improves on. Against 5.0 bp modelled effective half spread + 0.5 bp fees (~11 bp
round trip on a $20M+ ADV universe) every variant is under water by 2–7×. 66/84 design and 61/84
held-out cells have positive gross t: **the gross alpha is systematically present and
systematically smaller than the spread.**

The tightest statement the programme has produced, measured on virgin data: at h=5 the
factor-neutral reversal gross alpha *fully persisted* out of sample (0.89 → 0.86, break-even
5.36 → 5.13 bp) and is still net −0.29, because its break-even sits **exactly at the modelled half
spread**. The edge is worth ~5 bp/side and the spread is ~5 bp/side.

**(b) Vol term structure as a directional equity timer — dead, and blocked by data not ideas.**
0 of 43 above bootstrap E[max]; best bootstrap p = 0.63; median design Sharpe −0.04. **Plain
buy-and-hold SPY (design 0.94, held-out 0.82) beats all 43 in both windows**, and the best alpha-t
against SPY is +1.11 against a 2.74 bar. The largest raw effect in the theme —
log(VVIX/VIX) at −4.27 bp/σ, t −2.50 over 16 years — has the *opposite* sign to its pre-declared
mechanism and is ~0.2 gross Sharpe on a daily-turnover book. Logged so it is not rediscovered as
a near-miss. Re-opening this theme requires **real VX futures settlements** (the CBOE
constant-maturity indices are synthetic interpolations that smooth away exactly the roll-date and
expiry-cycle structure a curve signal would trade) or intraday curve sampling. Neither is on a
free keyless endpoint from this host — the same wall the 2026-08-20 ETP sweep hit.

**(c) Crypto spot cross-section — the free-data cost wall replicates on a second asset class.**
34 formulas, 0 survivors. Best design net Sharpe 1.43 clears only bootstrap E[max] (1.148), i.e.
exactly the winner a 34-formula noise search is expected to produce, and dies held-out (+0.03).
The strongest-gross fast formulas (1-day reversal, cross-quote, cross-venue dispersion) break even
at **1–3 bp/side against a 10 bp fee**; the slow low-turnover formulas break even at 20–200 bp but
have no Sharpe. 26 of 34 keep gross sign across both windows — faint persistent structure, wholly
eaten by the fee. **This one will not be fixed by buying data**: the effect is measured, it is
just smaller than the fee. Two families closed for good: cross-quote (TRY premium, USDC-vs-USDT)
and cross-venue (Coinbase-vs-Binance) daily dispersion are arbitraged flat.

*Reusable asset built:* first spot panel in the repo — 677 Binance USDT pairs × 3307 days
(2017-08 → 2026-07), **survivorship-bias-free** (BCC/FTT/LUNA/SRM/MATIC all present, verified),
with trade counts and taker-buy quote volume; plus 367 TRY + 333 USDC cross-quote pairs and 91
Coinbase USD products. Six of the nine years are calendar-virgin for this programme.

---

## 5. Two rejected composites, recorded so nobody rediscovers them

- **Crypto low-turnover composite** (design-only rule `turnover ≤ 0.30/day`, equal-risk, 13
  members, zero fitted parameters, mean pairwise corr 0.077): design 1.19, held-out **1.37
  (t 2.60)**, stable across thresholds 0.15–0.50 and leave-one-out. **Rejected** because
  (1) design-fitted signs give E[design SR] = 1.04 under a pure null, so 1.19 explains nothing;
  (2) a one-day-lag placebo takes held-out 1.37 → 0.85, which a genuinely slow book should not
  feel; (3) market beta flips +0.89 design → −1.73 held-out; (4) worst design day −15.1σ, which
  fails the owner's controlled-tail requirement outright.
- **Vol-term holdout maxima**: the two best held-out numbers in that theme are two of its
  *weakest* design results (G4_UNINVERSION_10D: design 0.36 → holdout 1.42, t +3.65, design
  bootstrap p 1.00, design alpha-t vs SPY −2.08). Promoting either is selecting on the holdout.
  Design→holdout rank correlation of +0.35 in that theme is **beta, not skill**: 19 of 43 books
  are long-biased and SPY was +0.94/+0.82 across the two windows.

---

## 6. Method corrections worth propagating (these changed answers, not just numbers)

1. **Test on gross, size on net.** Cost is sign-invariant: reversing a book flips gross P&L but
   not cost, so the best achievable net is `sign·gross − cost`. Ranking on net t manufactured four
   false hits with large *negative* net t (−2.73, −1.94, −1.92, −1.83) whose true |gross t| were
   1.46, 0.47, 0.55, 0.74. The hypothesis test runs on gross; tradability on the correctly-signed
   net.
2. **Never freeze a sign before charging cost.** Doing so lets a *shocked* cost assumption *raise*
   net Sharpe, and it manufactured a fake "design 2.86 / held-out 2.72, t 5.16" winner in the
   crypto sweep. Add `assert net_shock <= net <= gross` to every sweep self-test (asserted this
   round, 0 violations).
3. **Raw dividend-unadjusted price panels manufacture alpha.** One formula first printed design
   t = **−13.97**; entirely fake, from the ex-date price drop inside the realised return plus an
   off-by-one that held *across* the drop. Fixing both moved it to t = −0.19. Any future work on
   the inv3 stock panel must neutralise ex-date returns.
4. **Coverage is part of the self-test.** A conditional up/down-day beta silently had 0.000
   coverage because a 250-day window with default `minobs = W//2` can never qualify. Per-signal
   coverage now prints in the self-test output and should stay there.
5. **Exclude zero-notional days rather than scoring them as zero returns**, or long group warm-ups
   silently deflate t-stats.

---

## 7. Dead-ledger discipline

Zero formulas spent on regime conditioners or gates, per round 3's 0/107 meta-result. Nothing in
this round multiplies an alive basket leg by a condition; all 202 are standalone books. No
re-tests of REV1/2/5/10 and their residual/std variants, CLOSE_LOC, AMIHUD, SIZE_ILLIQ, ZERORET,
the LOW* family, MOM20*, HI52, the RegSHO forms, the REV1_*_UNIV conditioners, VRP harvesting,
vol-ETP roll carry, standalone carry, the box trade, Orphan Flush, Coiled Leverage, the 18 SIZE
candidates, or the four noise-sweep themes. Where a named brief angle existed in the dead ledger
in textbook form it was rebuilt in a structurally different form (e.g. sector-relative required
data-driven PIT correlation clustering because the panel carries no industry labels — validated,
not noise: 39 quarterly refits, median 1533 names labelled, 91.2% pair-level cluster agreement
between consecutive quarters).

Declared **untested** rather than reported negative: ETF creation/redemption seasonality (no
share-count feed) and index add/delete reconstitution (no point-in-time membership data).

---

## 8. Recommendation

1. **Promote nothing.** Basket unchanged.
2. **Log P02_PENSION_MEQ_MAG forward at zero size** in `BASKET_FORWARD_LOG.jsonl`; revisit at 60
   rebalance events. Do not size it on a 3.08 against a 3.26 bar.
3. **Stop re-mining the daily US equity cross-section on free data.** 216 cells, two independent
   searches, one clean out-of-sample persistence result that still loses to the spread. The
   binding constraint is execution cost, not signal discovery.
4. **Stop re-mining daily crypto spot cross-section.** Same wall, and buying data does not move it
   because the effect is already measured and is smaller than the fee.
5. The vol-term theme is **data-blocked, not idea-blocked** — it is the only one of the four worth
   re-opening, and only with real VX futures settlements or intraday curve sampling.
6. Three cheap, no-price-feed tests that would settle P02 if anyone wants closure: ICI monthly
   target-date-fund AUM (does the effect scale with obliged AUM?); does the impact print in the
   **closing auction** of the last session (answerable from `t3_cache` minute bars +
   `auctions.json.gz`); and a pre-committed forward window, since design and held-out are spent.

---

## 9. Files

Theme deliverables (all absolute under `/home/anont/meme`):

- `research/trading_bot/INVENT_D0821_xsfactor.{md,json}`, `_PREREG.md`, `_SELFTEST.json`,
  `_DESIGN.json`, `_HOLDOUT.json`; `scripts/trading_bot/invent_d0821_xsfactor.py`
- `research/trading_bot/INVENT_D0821_volterm.{md,json}`,
  `INVENT_D0821_volterm_dir_{DESIGN,HOLDOUT,SELFTEST,DIAG}.json`;
  `scripts/trading_bot/invent_d0821_volterm_dir.py`, `scripts/trading_bot/volts_fetch.py`
- `research/trading_bot/INVENT_D0821_seasonality_mechanism.{md,json}`;
  `scripts/d0821_season_{lib,etf,stock,fix,eval2,diag,diag2}.py`;
  `research/data/d0821_cache/`
- `research/trading_bot/INVENT_D0821_crypto_spot_xs.{md,json}`, `_PLACEBO.json`, `_pnl.npz`;
  `scripts/trading_bot/xspot_{enumerate,fetch2,panel,coinbase,lib,sweep,sweep2}.py`;
  `research/data/xspot_cache/`
- This file: `research/trading_bot/INVENT_D0821_MASTER.md` (+ `.json`)
