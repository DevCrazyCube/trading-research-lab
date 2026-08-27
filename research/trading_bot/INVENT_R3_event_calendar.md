# INVENT-R3 — EVENT-CONDITIONAL SIGNALS ON A PREDICTABLE CATALYST CALENDAR

**36 formulas tried, 34 with usable statistics, zero survivors. The theme is noise at the
bar this search earns.** Written 2026-08-21.

Machinery: `scripts/inv3_build_panel.py`, `inv3_event_calendar.py`, `inv3_run.py`,
`inv3_run2.py`, `inv3_run3.py`, `inv3_null.py`.
Numbers: `INVENT_R3_event_calendar.json`, `research/data/inv3_cache/{all_results,null,power}.json`.

---

## 0. THE ONE-PARAGRAPH ANSWER

The question was *which event windows carry a real, executable, OOS-positive edge*. Across
six event calendars — earnings (with 8-K item codes and second-resolution filing timestamps),
FOMC statement days, payroll Fridays, monthly OPEX and triple witching, month/quarter-end
index-rebalance closes, and the Russell June recon — **not one gated formula clears the
noise bar on the design window**. The largest design statistic in the whole family is
|t| = 3.11 and it belongs to a **control**: the *ungated*, every-session close-location
reversal, which is a known effect that is net-negative at 3 bp/side. The largest
**event-gated** statistic is |t| = 2.44 (quarter-end close fade, n = 20) against a
correlation-aware joint-null E[max] of **2.40** and an analytic sign-agnostic bar of
**2.88** — i.e. the best thing the search found is exactly what a null search of this size
is expected to produce. The direct question "what does the gate buy" is answered explicitly
in §4: across five calendars the incremental value of the gate is statistically zero and its
**sign is not even consistent**. The one place the earnings calendar clearly matters, it
matters with the wrong sign for a trader: the alive cross-sectional reversal is **weakest**
near a scheduled print (+11.7 bp/event with no event within ±20 sessions, +4.5 bp before a
predicted print, **−2.3 bp** after a realised one). The catalyst calendar is a set of dates
to **exclude** from the alive mechanisms, not a source of new ones — which is what basket
leg L1 already does via `T03_p10_annnight_excl`.

---

## 1. WHAT WAS ACTUALLY NEW HERE

Rounds 1–2 and the 380/367-formula sweeps tested calendar effects at the **index level**
(`ETF_PREFOMC_24H`, `ETF_AUCTION_CONCESSION`, `SESS_OPEXDAY_INTRADAY`, `XE_MONTHSTART_CONT`)
and tested earnings as **PEAD** (t27's D01–D17, all dead). Neither is repeated. Round 3
went at the theme through three doors that had never been opened in this repo:

1. **8-K metadata as the conditioner, not the EPS number.** The t15 cache carries the item
   code set (`2.02,5.02,9.01`) and the acceptance timestamp to the second for 70,406
   filings. That supports conditioners no price database has: *which* items the release
   carried, whether the firm shifted its release time versus its own trailing-4-quarter
   median hour, and how its reporting lag moved versus the same quarter a year earlier.
   Family A, 13 formulas.
2. **The calendar as a gate on an ALIVE mechanism, always paired with its own ungated
   control.** Every gated book in families C/D/E/F has a twin that is identical except the
   gate is removed. That turns "is there an effect" (answer: sometimes, and it is already
   in the basket) into "does the *event* add anything" (answer: no).
3. **Institutional-plumbing events that are not price patterns.** The buyback blackout
   window derived from point-in-time predicted announcement dates (B03), and peer-sympathy
   in non-announcers whose top-10 trailing-correlated peers report tonight (B01/B02, peer
   sets refit each January from the prior calendar year only).

Two calendars in the brief could **not** be tested and are declared untested rather than
reported as negative: **crypto token-unlock cliffs** (no vesting-schedule feed is cached and
network crawls are barred inside an agent) and **index add/delete reconstitution** proper
(no point-in-time membership data; C01/C05 only approximate the effective *date*).
**Treasury auctions** were not re-run: `NEWTERR_flowcal` already killed
`ETF_AUCTION_CONCESSION` / `ETF_AUCTION_RELIEF` at the ETF level and no new mechanism was
available without an auction-date feed.

---

## 2. THE BAR

* **Analytic.** N = 32 in the joint null → `sqrt(2 ln 32)` = **2.63**. The search was
  sign-agnostic (E03/E04 and F04/F05 are one hypothesis tested twice), so the defensible
  count is 2N = 64 → **2.88**. Headline bar: **2.88**.
* **Empirical, correlation-aware.** 20,000 replicates. Each formula's per-event gross
  return series is re-signed with a sign drawn **once per trading day and shared by every
  formula that has an event on that day**, so contemporaneous cross-formula correlation
  survives. Statistic = max |t| over all 32. Result: **E[max] 2.40**, p50 2.34,
  **p95 3.33**, p99 3.90.
* **Programme-cumulative.** 598 distinct formulas across rounds 1–2 plus these 36 → 634 →
  `sqrt(2 ln 634)` = **3.60**. Nothing here is within 1.1 SE of that.

Observed max over everything: **3.11**, joint-null p = **0.088** — and it is a control.
Observed max over event-gated formulas: **2.44**, i.e. *below* the analytic bar and at the
empirical E[max].

---

## 3. THE FULL DESIGN + HOLDOUT TABLE (nothing dropped)

Design 2016–2021, holdout 2022-01→2026-08. `gross` = bp per event on a gross-1.0 book;
`tg` = Newey-West(h−1) t on gross; `tnet3` = the same at 3 bp/side; `BE` = breakeven
bp/side. Sorted by design tg.

| formula | n | gross bp | tg | tnet3 | BE bp | H gross | H tg | H tnet3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C04_CLV_FADE_ALLDAYS_**CTRL** | 1251 | 5.1 | **3.11** | −0.62 | 2.53 | 2.8 | 1.45 | −1.73 |
| C03_QEND_CLV_FADE | 20 | 21.6 | 2.44 | 1.75 | 10.81 | 8.7 | 0.51 | 0.16 |
| F01_REBAL_CLV_FADE_POOLED | 80 | 10.5 | 2.17 | 0.92 | 5.27 | 8.5 | 1.26 | 0.36 |
| E04_EARN_GAP_OC_CONT | 487 | 11.9 | 1.99 | 0.99 | 5.96 | 17.6 | 2.48 | 1.64 |
| B02_PEER_SYMPATHY_FADE_3 | 584 | 12.2 | 1.85 | 0.92 | 6.11 | −5.3 | −0.63 | −1.38 |
| C02_MONTHEND_CLV_FADE | 60 | 10.1 | 1.85 | 0.74 | 5.06 | 9.6 | 1.24 | 0.46 |
| E01_CROWDED_CAL_XS_FADE | 242 | 7.9 | 1.77 | 0.42 | 3.97 | 3.5 | 0.45 | −0.32 |
| A05_ITEM_701_REGFD_5 | 413 | 8.6 | 1.39 | 0.37 | 4.29 | 13.5 | 2.04 | 1.09 |
| B01_PEER_SYMPATHY_FADE_1 | 584 | 5.6 | 1.31 | −0.11 | 2.80 | −2.0 | −0.41 | −1.62 |
| C06_OPEXWEEK_RET_FADE | 60 | 39.0 | 1.22 | 1.03 | 19.48 | 16.5 | 0.75 | 0.46 |
| C01_WITCH_CLV_FADE | 20 | 11.8 | 1.00 | 0.49 | 5.88 | 5.1 | 0.32 | −0.06 |
| D04_XS_FADE_QUIETDAYS_**CTRL** | 1075 | 2.5 | 1.00 | −1.44 | 1.24 | 3.2 | 0.96 | −0.85 |
| F10_REV5_NOEVENT_**CTRL** | 1231 | 11.7 | 0.97 | 0.45 | 5.83 | 21.7 | 1.82 | 1.29 |
| E02_QUIET_CAL_XS_FADE_**CTRL** | 649 | 3.1 | 0.94 | −0.90 | 1.55 | 4.7 | 1.03 | −0.29 |
| F05_MACRO_POOLED_XS_CONT | 98 | 8.8 | 0.62 | 0.19 | 4.40 | 19.2 | 1.71 | 1.17 |
| A10_TIMEMIG_XS_5 | 471 | 3.5 | 0.47 | −0.38 | 1.74 | 12.6 | 1.70 | 0.85 |
| A08_TIMEMIG_LATE_5 | 114 | 6.8 | 0.38 | 0.03 | 3.41 | 42.9 | 1.54 | 1.31 |
| F08_REV5_PRE_EARN | 551 | 4.5 | 0.34 | −0.14 | 2.23 | 31.5 | 2.09 | 1.67 |
| D01_FOMCDAY_XS_FADE | 39 | 6.0 | 0.32 | −0.00 | 2.99 | −20.6 | −0.99 | −1.28 |
| A04_ITEM_801_OTHER_5 | 189 | 2.0 | 0.21 | −0.44 | 1.01 | 0.2 | 0.02 | −0.50 |
| A01_ITEM_EXTRA_5 | 276 | 1.9 | 0.19 | −0.44 | 0.94 | 1.5 | 0.16 | −0.53 |
| A07_ITEM_EXTRA_21 | 276 | 3.2 | 0.16 | −0.21 | 1.58 | 8.0 | 0.50 | 0.05 |
| A09_TIMEMIG_EARLY_5 | 131 | −0.8 | −0.05 | −0.48 | −0.39 | 7.9 | 0.40 | 0.08 |
| F09_REV5_POST_EARN | 956 | −2.3 | −0.17 | −0.64 | −1.15 | 1.5 | 0.14 | −0.48 |
| A06_ITEM_COUNT_XS_5 | 487 | −1.8 | −0.26 | −1.14 | −0.91 | −15.0 | −2.00 | −2.84 |
| A11_LAGDELTA_XS_5 | 467 | −1.7 | −0.28 | −1.32 | −0.86 | −15.5 | −1.79 | −2.52 |
| A12_LAGDELTA_XS_21 | 466 | −4.3 | −0.35 | −0.95 | −2.14 | −14.0 | −1.17 | −1.78 |
| B03_BUYBACK_WINDOW | 1251 | −0.4 | −0.48 | −8.20 | −0.19 | −1.5 | −1.46 | −7.36 |
| F04_MACRO_POOLED_XS_FADE | 98 | −8.8 | −0.62 | −1.04 | −4.40 | −19.2 | −1.71 | −2.26 |
| A02_ITEM_502_OFFICER_5 | 26 | −20.0 | −0.76 | −1.00 | −10.01 | 16.0 | 0.46 | 0.28 |
| D03_NFPDAY_XS_FADE | 59 | −18.6 | −0.92 | −1.22 | −9.29 | −18.2 | −1.17 | −1.56 |
| A13_AMC_VS_BMO_5 | 459 | −7.7 | −1.27 | −2.30 | −3.87 | 13.5 | 2.09 | 1.12 |
| D02_FOMCEVE_LOWBETA | 39 | −25.7 | −1.37 | −1.70 | −12.84 | −48.9 | −1.42 | −1.60 |
| E03_EARN_GAP_OC_FADE | 487 | −11.9 | −1.99 | −2.99 | −5.96 | −17.6 | −2.48 | −3.33 |

Dropped for too few events (counted in the 36, not in the null): `A03_ITEM_205_RESTRUCT_5`,
`C05_RUSSELL_RECON_CLV_FADE`.

---

## 4. THE GATE-VALUE TEST — the part that actually answers the brief

The one-day close-location fade is run on **every** session (the C04 control, 1251 design
events, gross +4.8 to +5.3 bp). Then each calendar is entered as a dummy and the question is
whether gated sessions differ. This is a two-sample difference of means on the *same*
signal, so it is immune to "the signal itself works".

| gate | n gated | mean gated | n ungated | mean ungated | diff | t |
|---|---:|---:|---:|---:|---:|---:|
| quarter-end | 20 | +21.6 bp | 1231 | +4.8 bp | **+16.8** | 1.70 |
| triple witching | 20 | +11.8 bp | 1231 | +4.9 bp | +6.8 | 0.56 |
| month-end | 60 | +10.1 bp | 1191 | +4.8 bp | +5.3 | 1.01 |
| FOMC statement day | 39 | +3.7 bp | 1212 | +5.1 bp | −1.4 | −0.12 |
| monthly OPEX Friday | 60 | −0.7 bp | 1191 | +5.3 bp | **−6.1** | −0.99 |

Not one gate reaches |t| = 2 on its own, let alone the 2.88 family bar, and the sign flips
across calendars that share the same alleged mechanism (witching **is** an OPEX Friday, and
the two disagree by 12.5 bp). The rebalance story — index MOC prints push the close away
from the day's midpoint and it comes back — is *directionally* present in all three
rebalance gates and absent or reversed in the two that have no rebalance. That is the single
most encouraging pattern in the round and it is still, at 1.70 on its best cut, indis-
tinguishable from noise.

The same test run through the earnings calendar on the 5-session reversal (F08/F09/F10) is
unambiguous and points the other way:

| window | n | gross bp/event |
|---|---:|---:|
| no print within ±20 sessions (control) | 1231 | **+11.7** |
| 1–5 sessions before a predicted print | 551 | +4.5 |
| 1–10 sessions after a realised print | 956 | **−2.3** |

Reversal is monotonically destroyed by proximity to the catalyst. This replicates t27's
`T01_p10_quiet` / `T03_p10_annnight_excl` at a different rail and different horizon, and it
is the actionable content of this round: the calendar's value to this programme is as an
**exclusion mask** on legs the basket already owns.

---

## 5. WHY "NO EDGE" IS NOT THE SAME AS "NO POWER" — and where it is

Minimum detectable effect at the 2.88 bar, per formula, converted to a true annualised
Sharpe:

| formula | n | events/yr | sd bp | min detectable mean | min detectable Sharpe |
|---|---:|---:|---:|---:|---:|
| C03_QEND_CLV_FADE | 20 | 4.2 | 43.6 | 28.1 bp | 1.32 |
| C01_WITCH_CLV_FADE | 20 | 4.2 | 54.4 | 35.1 bp | 1.32 |
| F01_REBAL_CLV_FADE_POOLED | 80 | 16.3 | 42.9 | 13.8 bp | 1.30 |
| A05_ITEM_701_REGFD_5 | 413 | 70.8 | 133.9 | 19.0 bp | 1.19 |
| B01_PEER_SYMPATHY_FADE_1 | 584 | 118.5 | 105.4 | 12.6 bp | 1.30 |
| C04 control | 1251 | 252.0 | 57.3 | 4.7 bp | 1.29 |

**Median minimum-detectable annualised Sharpe: 1.30**, and it is 1.19–1.32 for every single
formula regardless of how rare the event is. That flatness is not a coincidence: with a
~5-year design window the floor is `bar / sqrt(years)` = 2.88 / 2.2 ≈ 1.3 no matter how the
events are distributed. Pooling four-a-year calendars into a 16-a-year one (F01) buys
*nothing* in detectability — it only makes the estimate less lucky.

So the honest scope of the negative is: **no event window in this set carries a true
annualised Sharpe of 1.3 or better.** A true Sharpe-0.6 rebalance-close edge is *not*
excluded by this work and cannot be excluded by any 5-year window. Chasing it would need
either a longer panel (the t17 cache starts 2016; the t3 monthly/auction caches reach back
further and could extend a close-location study to ~1993 the way `SESS_OPEXDAY` did) or a
much lower-variance rail (MOC-legal execution in the auction itself, where the cost is
~0.5 bp/side rather than 3, which raises the *net* but not the *t*).

---

## 6. NEAR-MISSES, AND WHY EACH IS REJECTED

* **C03_QEND_CLV_FADE** — the family maximum, design t 2.44, net Sharpe 0.73 at 3 bp/side,
  breakeven 10.8 bp/side. Rejected on three counts: it is below the 2.88 bar; **n = 20**;
  and it is the luckiest 20-event subset of F01, whose 80-event pooled version reads 2.17.
  Its holdout collapses to t 0.51 / net Sharpe 0.08.
* **F01_REBAL_CLV_FADE_POOLED** — the honest version of the same idea, and the only formula
  in the round whose sign, mean and mechanism all survive into the holdout (design +10.5 bp
  / t 2.17 / net SR 0.42; holdout +8.5 bp / t 1.26 / net SR 0.16). Still fails G1, and at
  6 bp/side it is net **negative** in both windows. Breakeven 5.3 bp/side on design, 4.2 on
  holdout — a book that only works if execution is genuinely cheaper than assumed. **Logged,
  not promoted; the one candidate worth re-testing on a longer panel and an MOC rail.**
* **E04_EARN_GAP_OC_CONT** — earnings-reaction-session gap *continuation*, design t 1.99 →
  holdout t 2.48, positive net in both. Rejected on mechanism, not statistics: it is
  intraday momentum, and `B22E` killed intraday momentum out of sample in this programme.
  Reporting it as new would be re-proposing a dead edge under a calendar mask.
* **A05_ITEM_701_REGFD_5** — long announcers who furnish a Reg-FD deck (item 7.01) with the
  release. Design t 1.39 → holdout t 2.04, +8.6 → +13.5 bp, same sign, growing. Promoting
  it would be selecting on the holdout, which is the exact failure mode this round exists to
  avoid. It is 1 of 34 and the second-best holdout number in a family whose design
  distribution is centred on zero. **No.**
* **A13_AMC_VS_BMO_5** — design t −1.27, holdout **+2.09**. A clean sign flip across
  windows; listed only because it is the round's best illustration of why the design gate
  comes first.
* **B03_BUYBACK_WINDOW** — the most mechanically appealing idea in the round (long the
  post-print open-repurchase window, short the predicted pre-print blackout) and the most
  decisively dead: gross −0.4 bp/day on 1251 design days, net −8.2 t. It rebalances daily
  with high turnover and captures nothing to pay for it. The blackout constraint is real;
  its price impact at this horizon is not measurable.

---

## 7. VERDICT

**Theme is noise.** Zero promotions, zero new legs, nothing to pre-register. The round's
deliverables are three:

1. A **dead-ledger extension**: 8-K item-code composition, release-time migration, reporting-
   lag delta, buyback blackout windows, peer-sympathy fade, attention-crowding gates, FOMC/
   NFP cross-sectional day fades, OPEX/witching/month-end/quarter-end close-location fades —
   all tested, all noise, none to be re-proposed without a new mechanism.
2. A **confirmed exclusion rule**: proximity to a scheduled earnings print monotonically
   degrades the alive cross-sectional reversal (+11.7 → +4.5 → −2.3 bp). Legs L1/T3 already
   exclude announcers; this independently re-derives why they should.
3. One **logged, unpromoted candidate**, `F01_REBAL_CLV_FADE_POOLED`, and a specific,
   cheap way to settle it — extend the close-location study back to the 1990s on the t3
   monthly/auction caches and re-run it on an MOC-legal rail. If the rebalance gate is real
   at ~0.6 Sharpe, a 30-year panel is the only instrument in this repo that can see it.

Untested and declared: crypto token-unlock cliffs (no cached vesting feed), index add/delete
reconstitution (no point-in-time membership), CPI release dates (no BLS schedule cached; the
"second Wednesday" proxy was judged too crude to count as a known schedule).
