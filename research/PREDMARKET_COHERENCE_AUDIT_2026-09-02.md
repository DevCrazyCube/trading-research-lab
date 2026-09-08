# PREDMARKET — mechanical cross-market coherence audit (2026-09-02)

**Status: RUN, CLEAN, NO EDGE FOUND.** Logged as an abstention in
`research/trading_bot/predmarket/PREDMARKET_PREREGISTRATION_LOG.jsonl`
(`proposed_utc` 2026-09-02T19:06:15Z). No estimate was frozen. This is a method note plus
a **trap catalogue**, so later ticks do not re-trip the same four false positives.

## Why this method

PREDMARKET1's whole honesty problem (prereg §2) is that an LLM's view on a political
outcome is contaminated by memory, and its knowledge stops in May 2026 — so on any
September-2026 event the crowd strictly dominates it on information. Every tick from
2026-08-31 onward has therefore abstained, with the abstention reason amounting to
"I have no news you don't."

A **cross-market coherence violation** is the one edge source that escapes both problems:
it is arithmetic over *contemporaneous* prices, needs no post-cutoff fact, and cannot be
memory-contaminated. If two markets on the same underlying event are priced such that no
probability measure satisfies both, one of them is wrong regardless of who wins. That is a
defensible, statable reason to disagree with the crowd — exactly the bar prereg §6 sets.

This tick ran that audit for the first time.

## What was screened

Prior ticks reasoned over the 40-row pull digest. This tick used `pull --limit 3000`
(3000 selectable markets) and screened to **146 fresh candidates**: close ≤ 2026-12-31,
volume ≥ $20k, price in 3–97c, spread ≤ 6c, not already in the ledger. The near-dated
liquid book is roughly 3.6x richer than the digest view the 08-31/09-01/09-02-09h ticks
were working from. **That alone is a process fix worth keeping.**

Three tests, all mechanical:

1. **Date-ladder monotonicity** — nested `"X by <date>"` families must be non-decreasing in
   date; nested `"X continues through <date>"` families must be non-*increasing*.
2. **Winner-take-one sums** — an exclusive-and-exhaustive candidate family must sum to 1.0
   (or to *k* for a k-advance field), net of overround.
3. **Nested implication** — `P(qualify for runoff) ≥ P(finish 2nd)`, `P(most seats)` vs the
   seat-bucket distribution, marginals vs a balance-of-power grid.

## Result: zero exploitable violations

Every flagged anomaly dissolved on reading the resolution-criteria text. The catalogue:

| # | Apparent violation | Why it is NOT one |
|---|---|---|
| a | Russia Duma: `1130012` "United Russia **gains** the most seats" 70.5c (vol $9.0M) vs `1129894` "United Russia **wins** the most seats" 98.9c (vol $0.89M) — looks like a 28pp arbitrage | RC: *"gains"* = largest seat **delta vs the pre-election Duma**, a different question. UR already holds ~324/450 so it has little room to grow; that is precisely why New People prices **23.3c to post the largest gain** while pricing **0.3c to win**. Coherent. |
| b | "Israel × Iran ceasefire continues through Sep30/Oct31/Nov30/Dec31" = 82.5/72.5/66.5/61.5c — flagged by test 1 | "Continues **through** a later date" is a *subset* of the earlier one, so a **decreasing** ladder is correct. The test's sign convention was wrong, not the market. |
| c | Brazil presidential runoff family sums to **2.021** across 8 legs | **Two** candidates advance, so the target is 2.0, not 1.0. The 2.1% overround is spread-consistent. |
| d | `902977`/`902978` "shutdown by Jan 31 **and** House winner" sum to 0.993 ⇒ implied P(shutdown) ≥ 99.3% | Priced at the standalone House marginals (85.8/13.5 vs 88.5/12.0), consistent with the **Jan-31-2026 leg having already settled** — these are House markets in disguise. The residual 2.7pp discount on a duplicate contract is real but **declined**: confirming it requires *recalling* whether a specific shutdown happened, which is the memory-not-calibration failure prereg §2 forbids as the basis of a frozen estimate. |
| e | Venezuela: "leader end of 2026" (Maduro 83.6c, Delcy 10.0c; vol $2.8M/$1.8M) vs "**de facto** leader" (Delcy 91.5c; vol $93k) — contradict on Delcy by 81pp | Same shape as (a): "de facto" vs formal head of state is a genuine distinction, the de-facto book is **20x thinner**, and adjudicating it needs post-cutoff Venezuela facts we do not have. |

**The generalisable lesson: on Polymarket, near-duplicate question wording is load-bearing,
not sloppy.** Four of five flags were a real semantic distinction the naive price comparison
erased. Any future coherence flag must read both RC texts *before* it is called an edge.
The honest read of (a) is also that the 9.0M-volume leg is the price-setter and the thin
bucket market is the follower — trusting a $36k book against a $9M book is backwards.

## Honest verdict on the method

The audit is **cheap, mechanical, repeatable, and it found nothing.** That is a real negative
and it is worth having: it says the liquid near-dated Polymarket political book is
*internally arbitrage-free at the 1–3pp fee/spread floor*, which is what an efficient book
should look like. It does **not** license "there is never a violation" — it licenses
"there was none on 2026-09-02 in the 146-market near-dated liquid screen."

Keep it as a **standing cheap screen** on CHUNK D ticks (it is ~4 bounded queries), but do
not expect it to carry the instrument. It is a filter, not a thesis.

## The clock — the actually important fact this tick

The ledger is **66 frozen estimates / 0 resolved**, but the drought is about to break
without any new proposals:

- **14** frozen estimates close within 30 days, **25** within 60.
- First settlements: **2026-09-06** (Sachsen-Anhalt), **09-13** (Sweden), a block of **9 on
  09-20** (Berlin, Mecklenburg-Vorpommern, Russian Duma), then **09-30** and **10-04**
  (Brazil, Quebec).

So the marginal value of forcing a thin estimate now is **negative** — it adds Brier noise
to a sample that is days from starting to pay out. The resolution wiring was pinned by
**T43** ahead of the 09-06 close; the next real event is that resolver firing, not another
proposal round.

Flagged for the resolver: estimate `2046123` (KPRF second-most seats) was frozen at
`p_market=0.845` against `q_agent=0.760` (NO); it now trades **0.920** — the crowd moved
7.5pp *against* our read before its 09-20 settlement. No action; it scores as frozen. It is
an early, unblinded reminder that the honest base case here (prereg §9) is that the agent is
calibration-competitive at best.

**Nothing in this document is evidence about the calibration edge.** `N_min = 50` resolved
is unmet (n = 0); per prereg §8 no verdict is licensed.
