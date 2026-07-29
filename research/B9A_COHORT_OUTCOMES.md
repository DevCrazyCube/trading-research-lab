# B9a — The first outcome measurement: graduation base rate for the B8b cohort

**Run:** 2026-07-29. Author: Claude 1. Read-only; 17 `getMultipleAccounts` requests.
**Audited:** 2026-07-29 by Claude 2 (`agent_discussion.md` Seq 178) — **zero additional requests**,
entirely from the published artifact. Every headline figure reproduced exactly. **F2's wording is
corrected below, F3 gains a stated limitation, and F5 is new.**
**Rules frozen before the first request:** `agent_discussion.md` Seq 176.
**Cohort:** `research/b8b_cohort_433894233_434097833.sqlite`, the published, preregistered,
exhaustively-enumerated B8b cohort — **n = 1,601**, window `[433,894,233, 434,097,833]`.
**Artifact:** `research/b9a_outcomes.sqlite`.

> **This is a label, not a feature.** `BondingCurve.complete` read ≥8 days after launch is the
> end-of-observation outcome that `W_obs` was defined to permit. Using it as a model input would be
> the most direct leakage possible.

> **Graduation is not profit.** This measures whether a curve completed. It measures **no return**,
> and a graduated token can still lose money while a non-graduated one can be exited profitably.
> Nothing here is a strategy result.

## The headline

| | n | graduated | rate | 95% Wilson |
|---|---:|---:|---:|---|
| **whole cohort** | 1,601 | 43 | **2.69%** | [2.00%, 3.60%] |
| **tradable (non-Mayhem)** — the population the project trades | **1,136** | **16** | **1.41%** | **[0.87%, 2.28%]** |
| Mayhem (excluded by frozen policy) | 465 | 27 | 5.81% | [4.02%, 8.32%] |
| SOL-quoted | 1,577 | 40 | 2.54% | [1.87%, 3.44%] |
| USDC-quoted | 24 | 3 | 12.50% | [4.34%, 31.00%] |

**Every one of the 1,601 bonding-curve accounts was present.** Zero absent, so the freeze's separate
"missing account" category is empty and nothing had to be assumed about it.

## F1 — The tradable population graduates at 1.41%

That is the number that matters, because it describes the population the project has decided to
trade. A strategy that takes every tradable launch needs a winner returning **~71×** merely to break
even, before fees, slippage, priority tips, and failed transactions.

That is not a claim that no strategy works — it is the base rate any strategy must beat, and it is
the first time this project has had one.

### Audit of the denominator (Seq 178)

**The base is sound.** The cohort holds **1,601 rows, 1,601 distinct mints, 1,601 distinct bonding
curves, and 0 decode errors**; all 1,601 accounts resolved. Nothing was silently lost or collapsed,
so the denominator is not inflated or deflated by enumeration artefacts.

**The one alternative denominator that could be argued is immaterial.** "Tradable" is defined as
non-Mayhem, which still contains **10 USDC-quoted** launches (0 graduated). Restricting to
SOL-quoted as well gives **16 / 1,126 = 1.42%** against 1.408%. The choice does not move the number
and does not change any conclusion.

**1.41% is the correct denominator for the claim it makes** — *take every tradable launch* — and is
the wrong denominator for any filtered strategy, exactly as the handoff states. **Right-censoring
also makes it a lower bound**: graduation is observed at ≥8 days, later graduations are invisible,
and this artifact cannot measure how many, because it records no graduation *time*.

> ⚠️ **The audit has contaminated the obvious filter candidates for this cohort.** Answering the F3
> confound question required cross-tabulating outcome against the t=0 covariates. `is_cashback_enabled`
> in particular separates the tradable population (**1.83% vs 0.93%**). **That is not reported as a
> finding and must not be used as one** — it was found by looking at outcomes, which is precisely
> the move the preregistration exists to prevent. Any filter built on a covariate examined here has
> to be frozen and then measured on a **fresh cohort**, never on B8b. Recorded so the contamination
> is on the record rather than rediscovered later as a "result".

**One sharpening of the 71×.** It is exactly `1 / 0.0141`, so it is the break-even multiple only
under the assumption that graduation is the sole payoff and every non-graduate is a total loss.
The document already states graduation is not profit; the 71× should be read as *an illustration of
how thin the tail is*, not as a strategy result, and F2's correction above weakens the "total loss"
half of that assumption.

## F2 — Exit liquidity is nearly absent for non-graduates, and this may matter more than F1

`real_quote_reserves` is the SOL actually sitting in the curve, i.e. what an exit could draw against.
For the 1,558 non-graduates:

| | |
|---|---:|
| median | **0.0000 SOL** |
| exactly zero | 159 (**10.2%**) |
| **under 0.01 SOL** | **1,474 (94.6%)** |
| under 0.1 SOL | 1,535 (98.5%) |
| p99 / max | 0.1811 / 34.3368 SOL |

**94.6% of non-graduates hold under 0.01 SOL *at the end of observation*.** As of ≥8 days after
launch, for most of this cohort there is no counterparty to sell back to at any size.

> **Corrected at audit (Seq 178).** This finding originally read "94.6% **never accumulated** 0.01
> SOL". That is a claim about the *path*, and this artifact is a single terminal *snapshot* — the
> two are not interchangeable, and the curve mechanics make the gap unusually wide:
>
> `real_quote_reserves` **falls when holders sell**, and a curve's state is one-dimensional in it —
> `vqr = vqr₀ + rqr` and the token side follows, verified across all 1,110 non-Mayhem incomplete SOL
> curves with zero exceptions. **A curve that ran to 30 SOL and fully round-tripped returns to
> exactly its launch state**, indistinguishable from one that was never bought. So the 94.6% is a
> lower bound on *peak* liquidity, and how much lower is not measurable from this artifact.
>
> Only the **159 (10.2%) at exactly zero with token reserves still at launch** are provably never
> traded. The other 1,315 did accumulate something; the snapshot cannot say how much.

**What survives the correction, and what does not.** The claim that *these positions cannot be
closed today* stands — it is a statement about current state, which is what was measured. The
stronger inference that **"a backtest assuming exits fill measures a market that does not exist"
does not follow from this table**, because a backtest exits *during* the holding window, not at
t+8 days, and the reserves available then are exactly what is unmeasured. F2 is a strong reason to
build the Phase 2 simulator with a constrained-exit model; it is **not yet evidence of what that
constraint's magnitude should be**. That requires the trade-level reconstruction listed below.

## F3 — Mayhem graduates 4.12× more often, and this does NOT mean the exclusion was wrong

| | rate | |
|---|---:|---|
| Mayhem | 5.81% | 27 / 465 |
| non-Mayhem | 1.41% | 16 / 1,136 |
| **rate ratio** | **4.12×** | Fisher exact two-sided **p = 3.6 × 10⁻⁶** |

**It is not driven by a few actors** — the obvious confound, checked before drawing any conclusion.
The 27 Mayhem graduations come from **22 distinct `creator ∪ user` actor groups** (largest single
actor: 3, i.e. 11%), and non-Mayhem's 16 from 15 groups. Measured **per actor group** with ≥3
launches, the gap widens rather than closes: **6.83% versus 0.31%.**

**Audit (Seq 178): the effect also survives stratification by creator prolificacy**, a third-way
difference not checked in the original run — and it is monotone in every stratum:

| creator's launches in window | non-Mayhem | Mayhem |
|---|---:|---:|
| 1 | 2.37% (12/506) | **12.79%** (11/86) |
| 2–5 | 1.03% (4/389) | **6.49%** (10/154) |
| 6+ | 0.00% (0/241) | **2.67%** (6/225) |

**But a real limitation the original entry did not state:** the two populations are launched by
**almost disjoint creator sets** — 160 Mayhem creators, 674 non-Mayhem, **overlap of 9**. Mayhem
mode is therefore inseparable from "launched by a Mayhem-associated creator" in this cohort, and no
stratification can undo that. "Not driven by a *few* actors" is established; "not a property of a
*different population of* actors" is not, and cannot be from observational data of this shape.

**And yet the frozen exclusion stands, for a reason already in the record.** `B7A_LIFECYCLE_AND_MAYHEM.md`
F44 established that `set_mayhem_virtual_params` lets the operator **mutate a Mayhem curve's virtual
reserves outside trading**. So:

- A Mayhem curve's price math can be changed by a counterparty **between entry and exit**.
- Its "graduation" may be **administratively produced** rather than market-produced — which would
  explain this rate difference directly.

**So F3 is best read as evidence *for* the exclusion, not against it.** The higher rate is what a
mutable curve would look like, and a higher chance of completion is worthless if the operator sets
the terms of your exit. Recorded because it would be easy to read this table backwards and conclude
the project excluded its best population.

## F5 — The operator does not merely *have* the power to mutate Mayhem curves. It used it, on 425 of 427. *(audit, Seq 178)*

F3 rested on B7a F44 establishing that `set_mayhem_virtual_params` **can** change a Mayhem curve's
virtual reserves. The audit set out to break that reading and instead measured the thing itself, at
zero additional RPC cost, from the artifact as published.

A pump curve prices along a constant product `k = virtual_token × virtual_quote`. Trading moves
*along* it; only an out-of-band parameter change moves the product itself. Three steps:

| | |
|---|---|
| **1. Trading conserves k** | All **1,110 / 1,110** non-Mayhem incomplete SOL curves sit within 1% of the launch product `k₀ = 3.219 × 10²⁵`. Zero exceptions. |
| **2. Mayhem curves launch at the same k₀** | Exactly **2** Mayhem curves sit at `k₀` — and both are untouched: **1 and 3 lamports** of real quote, token reserves still *exactly* at launch. So Mayhem curves start where every other curve starts. |
| **3. The rest have left it** | **425 / 427** are off `k₀`, spanning **0.0006× to 33.8×**. Median **0.245×**. |

Trading cannot produce that (1) and they did not begin elsewhere (2). **The virtual parameters of
essentially every traded Mayhem curve in this cohort were changed outside trading.**

**This settles F3's reading rather than weakening it.** The original entry argued the exclusion was
justified because a Mayhem curve's price math *could* change between entry and exit. It does change,
for 99.5% of them, by up to four orders of magnitude in the product that sets the price. The
4.12× graduation advantage is the visible surface of a curve whose terms are set by a counterparty.

**The frozen Mayhem exclusion should be treated as confirmed by measurement, not by inference.**

> **What F5 still does not establish:** *when* each mutation happened relative to any trade, or
> whether any individual graduation was administratively produced. That needs the same trade-level
> reconstruction F2 needs. F5 shows the curves are mutated; it does not reconstruct the sequence.

## F4 — USDC's 12.5% is not established

3 of 24, Wilson **[4.34%, 31.00%]** — an interval wide enough to contain both the SOL rate and three
times it. Two of the three could be chance. **No USDC effect may be claimed from this**, and the
B8b census already recorded that USDC share itself is not distinguishable between cohorts.

## What this does not establish

- **No return, no profit, no strategy.** Graduation only.
- **One 24-hour window, one program regime**, carrying the day-of-week and market-conditions
  confounds the B8b census already states.
- **Nothing about timing.** When a token graduated, how far it ran before dying, or whether an early
  exit was available — none of that is here. It requires trade-level reconstruction.
- **Nothing about the 34.3 SOL outlier** or the shape of the upper tail, which is where any
  positive expectancy would have to come from.

## Decode verification (audit, Seq 178)

The handoff asked for the `BondingCurve` decode to be re-derived independently, since a wrong offset
would yield a plausible `complete` flag rather than an error. **It is correct**, confirmed five ways:

1. **IDL field order** matches the hardcoded `<QQQQQ?` exactly, and Borsh is unpadded so `complete`
   is the byte at offset 48. The IDL's declared discriminator also equals
   `sha256("account:BondingCurve")[:8]` = `17b7f83760d8ac60`.
2. **`token_total_supply` = 1,000,000,000,000,000 for all 1,601** — the 5th u64, so every preceding
   offset is right or this constant would be garbage.
3. **`complete` ⟺ `real_token_reserves = 0`, 43 / 1,558, zero exceptions.** A bool read from a wrong
   offset could not track a u64 at a different offset perfectly.
4. **`virtual_quote_reserves = 30 SOL + real_quote_reserves`, and the token side agrees**, across
   all 1,110 non-Mayhem incomplete SOL curves — four fields mutually consistent.
5. **`owner` is the pump program for all 1,601.**

Two robustness gaps were closed rather than left: the script defined `PUMP` but **never asserted the
account owner**, and **never checked the discriminator** — so a wrong address that happened to be
pump-owned would have decoded silently. Both now refuse. `tests/test_b9a_cohort_outcomes.py` (16
tests) was added; B9a shipped without any, and it is the only B-script that had none.

## Reproduction

```
python3 scripts/b9a_cohort_outcomes.py     # read-only, resumable, ~17 requests
python3 -m pytest tests/test_b9a_cohort_outcomes.py -q    # 16 tests, no network
```

The artifact records the cohort it measured, that cohort's freeze hash, and that the measurement is
a label rather than a feature.
