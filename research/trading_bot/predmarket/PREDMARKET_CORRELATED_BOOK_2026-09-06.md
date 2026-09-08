# PREDMARKET1: the open book is not 74 observations, it is ~1 bet

**Date:** 2026-09-06 (predmarket tick, hour 09)
**Status:** DEFECT FOUND in our own instrument. Not a market finding. No spec was edited.
**Verdict:** the PREDMARKET1 kill switch as frozen will deliver its FIRST verdict on a single
world-state draw and will report an i.i.d. standard error for it. That is a fake pass by
construction. It must be corrected BEFORE 2026-12-31.

## What was measured

Read-only over `PREDMARKET_PREREGISTRATION_LOG.jsonl` (107 records, 74 carrying a `q_agent`).

**1. The book is one trade, repeated.**

| slice | n | share |
|---|---|---|
| open estimates with a `q_agent` | 74 | 100% |
| `q_agent < p_market` (fade the market) | 61 | 82% |
| fade of a longshot, `p_market < 0.25` | **51** | **69%** |
| fade of a deep longshot, `p_market < 0.10` | 44 | 59% |
| everything that is NOT a longshot fade | 23 | 31% |

Mean edge on the 51 longshot fades: **-0.0382**. So the modal estimate in this instrument is
"this p=0.05 tail event is really p=0.012." That is not 51 forecasts. It is one position --
short the favourite-longshot bias -- expressed 51 times.

**2. The resolutions land in one lump, on one world-state.**

Close dates of the 74 open estimates, cumulative:

```
2026-09-20  n=12   cum=14
2026-11-03  n=11   cum=36
2026-12-31  n=24   cum=60   <-- N_min=50 is crossed HERE, in a single day
2027-01-01  n= 7   cum=67
2027-01-02  n= 5   cum=72
```

`kill_switch.N_min = 50` is not reached at 2026-11-03 (cum=36). It is crossed only when the
2026-12-31 block of 24 settles at once. Those 24 are overwhelmingly year-end "did anything
happen in 2026" questions (leader-out markets, invasion-by markets, Nobel markets, *Nothing
Ever Happens: 2026*). They do not resolve independently -- they resolve on one draw of one
variable: **was 2026 a quiet year?**

**3. The scorer assumes independence anyway.**

`scripts/trading_bot/predmarket/scoring.py:23` -- `_mean_se` returns `stdev/sqrt(n)`, a plain
i.i.d. standard error, and `kill_check` feeds it straight into
`lower95 = mean - 1.645*se` at `N_min=50`.

## Why this is the programme's known failure mode

If 2026 ends quiet, all ~44 deep-longshot fades resolve NO together, the agent's Brier beats
the market's on every one of them simultaneously, `se` is computed as if those were 44
independent draws, `one_sided_lower_95_bound` goes positive, and the instrument prints
**"ALIVE -- agent Brier significantly below market Brier."** It would have proven nothing
except that one year was quiet. With ~69% of the book in one cluster the effective sample is
plausibly n_eff ~ 10-15, so the reported `se` is understated by roughly `sqrt(74/12) ~ 2.5x`.

This is the same fake-pass shape already in the dead-ledger elsewhere in the programme
(`memecoin-structural-kills`: "the two filters that fake a pass"), and it is the direct
counterpart of the standing rule that *distance from zero matters more than sample size*.
Here the sample size is the lie.

## Required correction (NOT applied this tick -- editing a frozen spec is an owner decision)

1. **Cluster the standard error.** Score `d_i = brier_market_i - brier_agent_i` at the level of
   the *cluster*, not the market: group by (resolution date x thesis family), take the cluster
   mean, and compute the SE over clusters. `N_min` must then count **clusters, not markets** --
   under which today's book is worth roughly n=10-15, i.e. nowhere near 50.
2. **Report the concentration alongside the verdict.** `status_line` should print the
   largest-cluster share; a verdict computed on a book that is 69% one trade is not a verdict.
3. **Diversify the intake, or say plainly what is being tested.** Either the proposer stops
   accepting a longshot fade once that family passes a share cap, or PREDMARKET1 is honestly
   relabelled as what it currently is: a single forward test of the favourite-longshot bias,
   with n=1-ish power, not an agent-vs-crowd calibration tracker.

## Kill-condition for the corrected instrument

After the correction, PREDMARKET1 is DEAD if, at >= 50 **clusters** resolved, the
cluster-level one-sided 95% lower bound on mean Brier edge is <= 0. On the current intake rate
(~74 estimates and ~12 clusters in 14 days) that bar is months away, and it should be. The
present configuration would have declared a result in January on evidence worth one coin flip.

## This tick's action

Abstained from proposing (logged as `no_trade`). Two reasons: the agent's knowledge ends
May 2026 while every liquid mid-band market on today's board turns on post-cutoff events
(Israel-Iran ceasefire / Hormuz blockade, Brazil first round, Russian Duma, the Dec FOMC
path), so any `q_agent` there would be manufactured; and a 52nd longshot fade would deepen
the degeneracy documented above rather than add an observation.

---

# Appendix A — T47 standing duty: wide-book coherence screen, 2026-09-06

**Result: ZERO actionable flags. Retire-counter 2 of 6.**

Pull: `n_markets=28,891`, `n_selectable=28,353`, display-capped to the **volume-ranked top 3,000**.
`data_path_warnings` read before screening, as the task requires: **both venues report TRUNCATED**
(Kalshi 12,000 events / 13,943 markets; Polymarket 2,384 / 14,948), and two declared Polymarket tags
(`policy`, `us-current-affairs`) returned 0 events.

*Universe-completeness check (new, worth keeping):* the minimum volume inside the displayed 3,000 is
**$15,690**, which sits **below** the screen's own $20k floor. Because the display is volume-ranked,
every market above the floor is therefore inside the screened set — the screen is complete **with
respect to the fetched book**. It is *not* complete with respect to the true book, because the page
cap truncates before ranking and the unfetched remainder is ordered by the venue, not by volume.
That is the honest boundary of every "the book is arbitrage-free" claim made here.

Screened: close ≤ +120d, volume ≥ $20k, price 3–97c, spread ≤ 6c → **1,036 candidates** (60 already
frozen).

| test | families | raw flags | actionable after reading resolution criteria |
|---|---|---|---|
| 1. date-ladder monotonicity (sign per "by DATE" vs "continues through DATE") | 41 | 1 | **0** |
| 2. winner-take-one family sums | 68 | 52 | **0** |
| 3. complement pairs P(X)+P(¬X) vs 1 | 13 | 2 | **0** |

**Every raw flag dissolved, and three of them dissolved into a screen defect worth writing down:**

- **Test 2 is invalid as I first wrote it and its 52 "violations" are mostly my own artifact.** Two
  separate bugs. (a) *Multi-select fields are not winner-take-one*: "who will leave their role in the
  Trump administration in 2026?" (17 legs, Σ=3.495), "which states will redistrict before the
  midterms?" (7 legs, Σ=2.225), "which cities will Russia enter by December" (7 legs, Σ=2.034) — many
  legs can resolve YES, so Σ>1 is *correct*. (b) *Σ<1 flags are self-inflicted*: the screen's own
  vol/price/spread filter drops legs, so a partial family necessarily sums below 1. Nobel 2026
  (Σ=0.218), Xi-purge (Σ=0.207), US–Iran nuclear deal (Σ=0.177) are all truncated families, not
  underrounds.
  **Correction adopted for future ticks:** flag **only Σ > 1 + cost, only on a set that is mutually
  exclusive, and only when no leg was dropped by the filter.** Σ>1 on an exclusive set is an arb by
  selling every leg *whether or not* the set is exhaustive; Σ<1 requires exhaustiveness, which the
  filter destroys. Under that corrected rule the tick's Σ>1 survivors are the ceasefire-continues-
  through ladder (Σ=2.845), Xi-visits-US-before-DATE (Σ=2.83) and US–Iran-ceasefire-begins-by
  (Σ=2.345) — all **nested date ladders, not exclusive sets**, i.e. catalogued trap (b). Zero real.
- **Test 1's single flag** ("will Elon Musk post ⟨N⟩ tweets from ⟨D⟩ to ⟨D⟩?", 0.315 → 0.085) is a
  stem collapse: these are disjoint *count brackets over different windows*, not a nested tenor
  ladder. Also a novelty market, outside scope ranks 1–3. Dissolved.
- **Test 3's 2 flags** are one RBA pair double-counted, and the two legs are *different meeting
  dates* whose month my stemmer stripped — not complements. Dissolved.

**Verdict.** Second consecutive wide-book zero. Retire-counter **2/6** (1/6 credited 09-03 21:00).
Four more wide-book zero-flag ticks retire the screen on its pre-registered terms. Consistent with
the 09-02 clean audit and the 09-03 depth-kill: the liquid near-dated political book keeps testing
internally arbitrage-free at the fee/spread floor.

# Appendix B — the 09-06 first settlement did NOT fire (and this is not a defect)

The 09-05 tick pre-committed today's ticks to read the first settlement. Read live:
`resolution_pass = {n_open_before: 74, n_newly_resolved: 0, n_unique_markets_checked: 71}`,
`resolved_total = 0`, and `PREDMARKET_RESOLUTION_LOG.jsonl` does not yet exist.
`status` → `resolved 0/50 → NO VERDICT | kill ALIVE | open 74`.

**This is expected, not a fault.** The named first settlement is Sachsen-Anhalt (`2244513`,
q_agent 0.180 vs market 0.255), close 2026-09-06 — the vote is *today*; at 07:06Z it cannot have
resolved. The resolver ran and individually checked 71 unique ids, so the path is exercised.

**One watch item, logged not escalated:** `2244513` is no longer present in the pull's open book
while still unresolved in our ledger. Settling it therefore depends on the resolver's **per-market**
query path, not on the market still appearing in the listing. If it is still `open` in our ledger at
the 09-07 ticks with the result publicly called, that is a real wiring defect and should be filed —
today it is simply too early to say.

# Appendix C — relation to the 09-05 carry kill

The 09-05 tick killed the favourite–longshot thesis on **economics**: below `b > rT/(1+rT)` a
longshot short is dominated by cash however correct the view (trap g). This tick kills the same 51
estimates a **second, independent way** — on **statistics**: even granting the thesis, those 51
observations carry roughly one bet's worth of information and the scorer would report an i.i.d.
standard error for them. Two unrelated kills on one position is about as clear as this programme's
evidence gets. The book should be left to settle (it is already frozen and costs nothing), but its
eventual verdict must be read at cluster level or not at all.
