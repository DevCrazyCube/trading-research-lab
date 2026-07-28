# B8b — Cohort census

> **STATUS: PUBLISHED — owner-authorised 2026-07-28.** The run is complete, every figure below is
> reproducible from the artifact named in this header, and both agents have verified it
> independently.
>
> **How it was written, because it constrains what may be read from it.** The sampling rule was
> frozen (`B8B_SUBSAMPLING_PREREGISTRATION.md`) before any window existed; the analysis was
> pre-specified (`scripts/b8b_census.py`) before the scan finished; and **this document's framing,
> limitations and prohibited inferences were written while every number was still an unfilled
> placeholder**, so no result could shape how it reads. Numbers were then substituted mechanically
> (`scripts/b8b_fill_census.py`) rather than retyped. Drafted by Claude 2, audited by Claude 1, who
> wrote the freeze it is judged against.
>
> **Two claims in an earlier draft were wrong and were corrected before publication** — see N1 and
> N2 below. Both were caught by the other agent, neither by the author.

**Frozen rule:** `research/B8B_SUBSAMPLING_PREREGISTRATION.md`, sha256
`56d8a83b8cbc0821fabb5e5b8e098728caa2d7775d46f0c9fb55e673cf848374`.
**Owner authorisation:** `agent_discussion.md` Seq 121 — 4 minutes/hour.
**Window:** `[433,894,233, 434,097,833]`, 203,601 slots, 24.000 h, pinned by the Seq-123 pre-flight
against finalized tip 435,741,966.
**Artifact:** `research/b8b_cohort_433894233_434097833.sqlite`, sha256 `10fa3d6d608d2b4515de9f92d5aa8e4063ace4b72cda3300a7df0353e5cea0b8`.
**Analysis:** `scripts/b8b_census.py`, written before the scan completed.

## What this cohort is

The launch window is **not** a contiguous 24 hours. It is the **union of 24 four-minute blocks**,
one per clock hour, block `h` beginning at `offset(h) = (27h mod 59)` minutes into that hour.
Enumeration inside each block is **exhaustive** — every `CreateEvent`, no filtering on any
attribute — which is what keeps C4 intact while sampling 6.67% of the span.

**Membership is decided by when a token launched**, which is outside anyone's control and unrelated
to how the token turned out. The rejected alternative — keeping a subset of the *launches* — is a
member-level filter and is exactly what C4 forbids.

## Completeness

Exhaustiveness is the claim everything else rests on, so it is reported before anything else.

| | |
|---|---:|
| sampled blocks | 24 |
| sampled slots | 13,533 |
| retrieved / skipped | 13,524 / 9 |
| skips verified absent by `getBlocks` | 9 |
| slots unaccounted for | 0 |
| decode errors | 0 |
| members outside every sampled block | 0 |

**Partial completion is FAIL, not a smaller result** (freeze §5). A truncated run is a
time-of-day-biased sample wearing the label of a stratified one.

## Disjointness from every burned range (freeze §6.1)

Exhaustiveness says the cohort contains everything it should. Disjointness says it contains nothing
it should not. **This section was absent from the first draft (A3, Seq 145)** — a reader could not
tell whether the window overlapped a burned range, including B8a's.

Window `[433,894,233, 434,097,833]` versus all six burned ranges, checked individually, failing
closed on any overlap:

| range | origin | result |
|---|---|---|
| `[429,998,000, 430,000,000)` | B7e mature cohort | disjoint |
| `[430,000,000, 430,000,500)` | B7d pilot | disjoint |
| `[433,302,364, 433,304,364)` | **B8a cohort** | disjoint |
| `[435,564,885, 435,565,324)` | B7j/B7k positive-control envelope | disjoint |
| `435,566,652 – 435,566,690` | B7b `D_dead` throwaway sample | disjoint |
| `435,569,119 – 435,569,149` | B7c trade-only gap sample | disjoint |

**All six disjoint.** The window also sits entirely inside one program regime: the last loader
`Upgrade` was slot **433,095,571**, which is **798,662 slots (~3.9 days) before** the window opens,
and no upgrade has landed since — confirmed live against `ProgramData` at pre-flight.

## Stratification properties (freeze §2)

The freeze argues these at length and the scanner asserts them at runtime; **the first draft
asserted that stratification works without showing the reader why (A5, Seq 145).** All are derived
from `sampled_block` in the artifact:

| property | why it matters | measured |
|---|---|---|
| 24 offsets **all distinct** | a repeated minute-of-hour would alias with hourly-periodic launchers | **yes** |
| minutes-of-hour reachable | the first schedule (`7h mod 54`) could never sample minute 59 of any hour | **60 / 60** |
| no block straddles an hour | a straddling block would put one stratum's slots in the next hour | **max offset 56 + 4 = 60** |
| offsets match `(27h mod 59)` | the schedule is the sample definition | **yes, all 24** |
| min consecutive-hour offset gap | scatter, not a slow drift across the day | **27 minutes** |

## This window is burned by this document

Freeze §7 burns B8a **because its composition was inspected**. This census does exactly that to
B8b — quote split, Mayhem breakdown, per-stratum yield, creator concentration. **On the freeze's
own §7 logic, `[433,894,233, 434,097,833]` is therefore burned for future cohort *selection* from
the moment this document exists (A4, Seq 145).**

It remains valid as the cohort it was authorised to be. It is no longer available as a window
someone chooses later, because by then they will have read these numbers. Recorded here rather than
left implied, since the next window will be chosen by whoever reads this.

## Cohort size and the precision it actually supports

> **1,601 members, and at that `n` a proportion near 1% carries a 95% Wilson interval of
> 0.617–1.618 %.**

Stated in one sentence deliberately, per **owner decision A** (`DECISIONS.md`, 2026-07-28):
separating a proportion from its interval is how a reader ends up quoting the first without the
second.

**Two intervals are reported, and they are not interchangeable (A1, Seq 145).** The frozen ±0.5 pp
bar was defined on the **Wald normal approximation**, which is unreliable exactly here: at p ≈ 1%
the expected count `np` is ~13, near the threshold where Wald is usable at all. Verified by **exact
binomial enumeration**, not simulation:

| n | p | `np` | Wald coverage | Wilson coverage |
|---:|---:|---:|---:|---:|
| 1,300 | 1.0% | 13.0 | **93.9%** | 96.5% |
| **2,572** (the design's assumed n) | 1.0% | 25.7 | **94.2%** | 95.3% |
| 1,300 | 3.3% | 42.9 | 95.2% | 94.8% |

**A sentence that says "95%" and delivers 93.9% is the kind of number that gets quoted for years.**
Note the second row: the under-coverage is **not** an artifact of the realised `n` falling short —
the frozen bar was going to under-deliver at p ≈ 1% even at its own assumed sample size. The defect
is in the estimator the bar was written on, and it predates this run.

**The frozen bar is reported as-is and is NOT recomputed with a better estimator.** Changing the
formula of a success criterion after learning it would be missed is the same move as resizing the
sample after seeing the shortfall. So: the Wald figure is reported **against the frozen bar, which
was defined on the normal approximation**, and the **Wilson interval is the one a reader should
quote.**

The design was sized against a **±0.5 pp bar at p ≈ 1%**, assuming ~25,700 launches/day
extrapolated from B8a's single 13.6-minute window. **The freeze fixed the sampling *fraction*, not
a target count** — *"the realised `n` falls where it falls and is reported, whatever it is"* — so a
realised `n` below the assumption is a **reported outcome, not a defect and not grounds to resize
the sample after the fact.**

- frozen (Wald) bar met at p ≤ 1.05% — met at p = 1%
- `n` that would have been required for the Wald bar at p = 1%: 1,522
- Wald half-width at p = 1%: ±0.487 pp — **reported against the criterion, not as the interval
  to quote**

## Per-stratum yield

Stratification only means something if every hour actually contributed.

| hour | offset (min) | retrieved | skipped | members |
|---|---|---|---|---|
| 0 | 0 | 577 | 0 | 50 |
| 1 | 27 | 575 | 0 | 63 |
| 2 | 54 | 557 | 0 | 52 |
| 3 | 22 | 566 | 0 | 44 |
| 4 | 49 | 564 | 0 | 73 |
| 5 | 17 | 562 | 1 | 78 |
| 6 | 44 | 574 | 0 | 53 |
| 7 | 12 | 576 | 0 | 70 |
| 8 | 39 | 572 | 0 | 79 |
| 9 | 7 | 561 | 4 | 95 |
| 10 | 34 | 556 | 0 | 122 |
| 11 | 2 | 561 | 1 | 65 |
| 12 | 29 | 557 | 0 | 72 |
| 13 | 56 | 551 | 1 | 84 |
| 14 | 24 | 566 | 0 | 64 |
| 15 | 51 | 568 | 0 | 52 |
| 16 | 19 | 567 | 0 | 47 |
| 17 | 46 | 557 | 0 | 65 |
| 18 | 14 | 563 | 2 | 44 |
| 19 | 41 | 555 | 0 | 60 |
| 20 | 9 | 558 | 0 | 47 |
| 21 | 36 | 566 | 0 | 76 |
| 22 | 4 | 556 | 0 | 43 |
| 23 | 31 | 559 | 0 | 103 |

Two different things must not be conflated, and the census separates them:

- **observed, zero launches** — an observation, reported as a NOTE. Failing on it would conflate
  *"we looked and found nothing"* with *"we did not look"*.
- **zero retrieved slots** — no observation power in that hour, and a **failure**.

## Quote regime — reported split, never pooled

| quote mint | regime | members | share |
|---|---|---|---|
| `11111111111111111111111111111111` | SOL (native sentinel) | 1,577 | 98.50% |
| `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | USDC | 24 | 1.50% |

**No change in the USDC share is demonstrated (N3, Seq 157).** B8a was 8/242 = **3.31%**, 95%
Wilson **[1.68%, 6.39%]**; B8b is 24/1,601 = **1.50%**, Wilson **[1.01%, 2.22%]**. **The intervals
overlap**, so these two cohorts are not distinguishable on USDC share and no decline may be read
from them. Two points are not a trend.

**`sol_amount` must branch on `quote_mint` or fail closed** (B7k). And `quote_mint` itself has two
representations for SOL — event-derived `111…111` versus account-derived `So111…112` (B7l) — so a
filter written against the wrong one returns **zero** SOL members and reads as *"no SOL launches"*
rather than as a bug.

## Regime covariates — recorded, not filtered

| covariate | value | members | share |
|---|---|---|---|
| `is_mayhem_mode` | 0 | 1,136 | 71.0% |
| `is_mayhem_mode` | 1 | 465 | 29.0% |
| `is_cashback_enabled` | 0 | 980 | 61.2% |
| `is_cashback_enabled` | 1 | 621 | 38.8% |

Mayhem is a **covariate excluded at decision time**, never a sampling step. Excluding it is a
**change in creator composition**, not a row filter.

**And in this cohort that change runs the opposite way to B8a — the inherited intuition is wrong
here (N2, Seq 157).** In B8a the largest actor group was 10 members, **all 10 Mayhem**, so the
exclusion removed the most concentrated block and tradable leakage read *lower* than raw. In B8b:

| | B8a | **B8b** |
|---|---:|---:|
| largest actor group | 10 | **51** |
| of which Mayhem | **10 of 10** | **0 of 51** |
| effect of excluding Mayhem | removed it entirely | **leaves it wholly intact** |
| its share: whole cohort → tradable population | — | **3.19% → 4.49%** |

**The single most concentrated actor here is entirely tradable.** Excluding Mayhem does not remove
the concentration; it makes it proportionally **worse** in the population actually used for
modelling. **One actor group is 4.49% of the tradable set**, and that is the figure that matters
when folds are built — a fold that happens to receive that group receives one actor's behaviour as
4.5% of its data.

## Actor leakage under the frozen `creator ∪ user` key

| population | n | actor groups | repeat actors | members from a repeat actor | surplus beyond one-each | largest group |
|---|---|---|---|---|---|---|
| all | 1,601 | 824 | 232 | 1,009 (63.0%) | 777 (48.5%) | 51 |
| tradable (Mayhem excluded) | 1,136 | 673 | 161 | 624 (54.9%) | 463 (40.8%) | 51 |

The split key is `creator ∪ user`, **never token and never time**, and **an actor group is never
split across blocks or across folds**. Two figures are reported separately and must not be swapped:

- **members belonging to a repeat actor** — the exposed share.
- **surplus beyond one-each** — a different quantity. B8a's first census quoted the surplus (35.1%)
  as if it were the exposed share (50.4%), and the correction is why both are labelled here.

**What the union key actually did in this cohort: nothing (N1, Seq 157).** 16 rows have
`creator != user`; 7 of those name a `user` who is also a creator — but those 7 encode **one
distinct identity link**, not seven. Its effect:

| grouping | actor groups | members from a repeat actor |
|---|---:|---:|
| `creator` alone | 825 | 1,009 (63.02%) |
| **`creator ∪ user`** | **824** | **1,009 (63.02%)** |

One group merged; **not one published figure moved.** The union key remains the correct default —
it is free insurance, and B8a's audit argued for it correctly — but **this cohort supplies no
evidence for it**, and a reader must not take "7 bridge rows" as seven independent confirmations.

## What this does not establish

- **One 24-hour window is one day.** It carries a day-of-week and market-conditions confound that
  this design does not remove and does not claim to.
- **One program regime.** The window sits inside the regime opened at slot 433,095,571; nothing
  here generalises across an upgrade boundary.
- **Funding-cluster leakage is unmeasured** and is a **superset** of creator leakage — two creator
  pubkeys funded from one source are one actor, and nothing in this design detects that. Creator
  grouping removes *creator* leakage and no more.
- **No labels, no features, no model, no threshold.** Cohort membership only. **C2** — T2 labels are
  not valid until 8 days after the launch window opens (`W_obs`) — and T2 is **not absorbing**: a
  resumption was observed at 450.8 h, so a T2 member that trades again is a recorded **re-entry**.
- **No rate or distribution may be quoted from an incomplete run.**

## Censoring rules, and which of them this document can speak to

Named by identifier so conformance is checkable rather than a matter of reading for tone.

| rule | status in this census |
|---|---|
| **C1** right-censoring — members still in T3 at the end of `W_obs` are censored, not dropped | **not yet applicable.** No lifetime has been observed; this document is enumeration only. |
| **C2** launch window must end ≥ `D_dead` before the **observation window** ends | **not yet demonstrable** — `W_obs` is 8 days and `D_dead` is 7, so C2 holds for the *design*, but it constrains the observation phase and no observation has run. Cited correctly here after A1/A2 review: the 8-day figure below is **freeze §6.2** (ends ≥ `W_obs` before the **tip**), which is a different constraint. |
| **C3** no left-truncation; membership fixed at launch, nothing enters later | **satisfied** — membership is exactly the `CreateEvent`s inside the 24 blocks. |
| **C4** exhaustive within the launch window, no attribute filtering | **the central claim**, evidenced in *Completeness* above. |
| **C5** a recorder `gap` overlapping a member's lifetime marks that member **incomplete** | **binds the observation phase, not this one.** B8b enumerates historical blocks via `getBlock`; there is no recorder gap register involved in drawing the cohort. **It is recorded here because it will bind whatever follows**, and a later document that reconstructs member histories must honour it rather than discovering it. |

**C5 was missing from the first draft of this section.** It was caught by checking the skeleton
against the freeze clause by clause — and the automated keyword check I first used reported it as
*covered*, matching the unrelated phrase "incomplete run". A conformance check can be vacuous in
exactly the way a test can.

## Reproduction

```
python3 scripts/b8b_cohort_scanner.py            # resumable; partial completion exits FAIL
python3 scripts/b8b_census.py --json OUT.json    # read-only; exits non-zero unless COMPLETE
```

The artifact is self-describing: `metadata` carries the freeze hash, the IDL hash, the rule string,
stride, modulus, block length and the window bounds, and `sampled_block` holds all 24 resolved
ranges — so the sample can be re-derived without trusting this document.
