# Exogenous paid-attention — RESULT

Pre-registration: `EXOGENOUS_ATTENTION_PREREGISTRATION.md` (frozen 2026-09-04, prior 10-12%). Evaluated 2026-09-09 by Claude
on `research/midcap/attention.jsonl` (1,424 EVENT + 290,136 TICK rows, 09-03 22:31 -> 09-07 03:23 UTC, 6.0 h tracking per token,
90 s cadence). Feeds: DexScreener token-profiles 1,209 events, token-boosts/latest 153, token-boosts/top 12. First event per mint
(no overlap), entry = first tick strictly after the event (harness A), mint-equal, toll 1.14%, dropouts -30/-50/-100%.

## Verdict: FAIL on the frozen criteria. Boosted coins lose money at every horizon; they merely lose LESS than fresh-coin controls.

Post-hoc adjustments forced by data defects (NOT in the prereg, reported transparently):
- Price-feed glitches in the tail: top event shows +464,751% in 15 min with liquidity only doubling ($76k -> $154k); second +13,419%.
  Uncapped means are meaningless (15m DIFF "+357%" with median +1.6%). Returns capped at +300% per position.
- 455 ticks carry a different control than the event's; pairs are required to have the same control at entry and horizon.
- Liquidity at entry >= $10k (executable subset, n=636 of 1,374).

| horizon | boosted mean (net) | control mean | DIFF mean | DIFF median | trimmed 2% | 95% CI by 6h session |
|---|---|---|---|---|---|---|
| 15m | **-9.9%** | -25.4% | +15.4% | +3.0% | +14.0% | [+7.1%, +24.1%] |
| 1h  | **-29.6%** | -37.9% | +8.3%  | +0.3% | +7.4%  | [-1.6%, +19.3%] |
| 3h  | **-39.6%** | -46.5% | +6.9%  | +0.0% | +5.1%  | [-3.7%, +17.9%] |

Paid-boost feed only (real dollars, n=101, liq>=10k): 15m boosted mean +1.5% (median +2.0%), 1h -8.3%, 3h -19.0%.
At the prereg's 2.5% toll sensitivity every boosted-side figure is lower by a further ~1.4 pp.

## Why the difference is not an edge
1. **Placebo:** re-pairing each boosted coin with a RANDOM other event's control gives DIFF +10.0% vs +8.3% matched (1h).
   Matching adds nothing => the gap is selection (kill-risk #2 in the prereg): coins someone paid for are coins that are alive,
   and fresh-coin controls die fast. It is not an exogenous causal lift.
2. **Not replicated:** disjoint 36h windows, 1h DIFF: window 1 **-10.8%** [-24.2%, +3.0%], window 2 +21.4% [+6.9%, +32.3%],
   window 3 +11.1% [-0.1%, +30.5%]. Sign flips. Criterion 3 (>= 3 disjoint 48h windows) cannot be met on 3.2 days of data
   and is failed on what exists.
3. **Absolute returns negative:** buying every boosted coin and selling at 15 min loses 9.9% on average (median +3%: many small
   wins, heavy left tail). Kill-risk #1 (boost/profile paid at the top = exit signal) is consistent with -30% by 1 h.

## Criteria scorecard
1. mean net > +1.14% above matched control: 15m yes, 1h/3h not significant.   2. no-overlap: yes.
3. replicated in >= 3 disjoint 48h windows: **NO** (one window negative).   4. ci_low > 0 by session: 15m only.
=> Not a bot. Not decision-support either, because the placebo shows the estimand is selection.

## Status
NO_TRADE. This was the last untried FREE information class named in the closure of 2026-09-04. It is now tested and dead.
