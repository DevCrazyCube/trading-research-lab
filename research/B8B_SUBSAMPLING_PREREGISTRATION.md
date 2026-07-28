# B8b — Subsampling rule for a 24-hour launch window (frozen; not instantiated)

**Frozen (document only):** 2026-07-28. **Re-frozen 2026-07-28** — see "Revision" below.
**Status:** **RULE FROZEN. NO WINDOW INSTANTIATED. NO COHORT DRAWN. NO SCANNER WRITTEN OR RUN.**
**No RPC call has been made and no candidate window has been inspected.**
**Author:** Claude (ownership recorded in `agent_discussion.md` Seq 116, re-claimed at Seq 119)

## Revision — what changed, and why it was legitimate to change it

**Supersedes freeze `4366f880941d014fc04886d3b8f5375e1b18f1c37e101688771e3a7d7e606798`.**

Review (`agent_discussion.md` Seq 118) found two defects, and re-checking them exposed a third that
was mine. **All three were corrected before any window existed, any slot was fetched, or any
member was seen** — which is the entire situation preregistration is designed to allow. A rule
changed *after* data would be tuning; a rule changed *before* any data exists is just a rule being
made correct.

| # | Defect | Correction |
|---|---|---|
| 1 | Cost stated as "~6 hours" from an unmeasured "2,000 slots in ~37 minutes" | **Measured** from the B8a artifact: 3,187 s for 2,000 slots = **0.6275 slots/s** |
| 2 | `mod 54` capped offsets at 53, so **minute 59 of every hour was unreachable** — 1/60 of the window permanently invisible | New schedule with **full 60-minute coverage** |
| 3 | "6 minutes is the smallest whole-minute block" meeting ±0.5 pp — **false**; 4 minutes meets it | Block reduced to **4 minutes**, applying the frozen principle correctly |

Defect 2 mattered more than its 1.67% suggests: distinct offsets were chosen precisely so the
sample could not alias with hourly-periodic launchers, and a launcher firing at `hh:59` was missed
**completely, every hour** — the worst case of exactly the failure the design was meant to prevent.

Defect 3 was surfaced by the cost correction, and the direction is worth stating plainly: the
frozen principle was *the smallest block satisfying the stated precision requirement*. Applying it
without the arithmetic error gives 4 minutes. **The requirement itself is unchanged** — this is not
a cheaper design chosen because 9 hours was unwelcome, it is the original rule computed correctly,
and it happens to cost ~6.2 h.

**Depends on, and does not re-decide:** `docs/DEFINITIONS.md` **v0.3, RATIFIED** —
`W_launch` = 24 h, `W_obs` = 8 days, `D_dead` = 7 days, terminal states T1a/T1b/T2/T3, censoring
rules C1–C5. That ratification explicitly left the subsampling rule open and required it to be
frozen a priori and grouped by `creator ∪ user`. This document closes that, and nothing else.

## 1. The problem the rule has to solve without breaking C4

`W_launch` is now 24 hours. **C4 requires exhaustiveness within the launch window** — every
`CreateEvent` enters, no filtering on any attribute — and that is the rule doing the most
anti-leakage work in the whole scheme.

A 24-hour window contains roughly **25,700 launches** and **~206,800 slots**. Enumerating all of
them is a different order of cost from B8a's 2,000 slots (§5). So a subsample is required, and the
naive subsample — *keep some of the launches* — **destroys C4**, because any member-level selection
is a filter, and filters are the thing C4 exists to forbid.

**Resolution, and it is the central decision here: subsample the *window*, never the members.**
The launch window is a **pre-declared union of sub-intervals**. Within every sub-interval,
enumeration is **exhaustive** — every `CreateEvent`, no attribute filtering whatsoever. C4 then
holds exactly as written, with "the launch window" meaning that declared union.

This keeps the property that matters: **membership is decided by *when a token launched*, which is
outside anyone's control and unrelated to how the token turned out.**

## 2. Frozen sampling design

**Stratified by hour, one contiguous block per hour, deterministic offsets.**

1. The 24-hour window is divided into its 24 clock hours.
2. From each hour, exactly one **contiguous 4-minute block** is taken. Total sampled time
   **96 minutes = 6.67%** of the window.
3. The block in hour `h` (`h = 0…23`, from the window start) begins at minute

   **`offset(h) = (27 × h) mod 59`**

   and runs for 4 minutes. The schedule is:

   | h | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
   |---|--|--|--|--|--|--|--|--|--|--|--|--|
   | offset (min) | 0 | 27 | 54 | 22 | 49 | 17 | 44 | 12 | 39 | 7 | 34 | 2 |

   | h | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
   |---|--|--|--|--|--|--|--|--|--|--|--|--|
   | offset (min) | 29 | 56 | 24 | 51 | 19 | 46 | 14 | 41 | 9 | 36 | 4 | 31 |

**Why each element, since every one of them is a choice that must not be re-openable later:**

- **Stratified by hour, not a single contiguous block.** Launch activity is near-certainly diurnal,
  and `W_launch` is exactly one diurnal cycle. One contiguous 144-minute block would sample one
  part of the day and describe it as a day. Stratification guarantees all 24 hours contribute
  equally, by construction rather than by luck.
- **Deterministic offsets, no random seed.** A seed is one more thing that can be chosen after
  seeing a result, and "we re-ran with a different seed" is unfalsifiable from the artifact. This
  schedule is reproducible by anyone with arithmetic and nothing to trust.
- **Stride 27, modulus 59.** `gcd(27, 59) = 1` — 59 is prime — so the 24 offsets are **all
  distinct**: the block never lands at the same minute-of-hour twice, which would alias with any
  hourly-periodic behaviour (scheduled bots, cron-driven launchers). Modulus 59 keeps
  `max offset = 56`, so `offset + 4 ≤ 60` and **no block ever straddles an hour boundary**.
- **Every minute-of-hour is reachable.** The union of `[offset(h), offset(h)+4)` over the 24 hours
  is **all 60 minutes**. The previous schedule left **minute 59 unreachable in every hour**, which
  defeated the anti-aliasing rationale above in its worst case: a launcher firing at `hh:59` would
  have been missed completely, every hour. Full coverage was made a hard constraint of the search,
  and coprimality was kept as a constraint too so distinctness follows from a one-line proof rather
  than from an exhaustive check.
- **Minimum consecutive-hour offset gap is 27 minutes**, so successive blocks are widely separated
  in minute-of-hour rather than drifting slowly across the clock.
- **4 minutes.** Derived in §4 from a stated precision requirement, not picked.

All three properties — distinctness, no straddle, full 60-minute coverage — are asserted
programmatically before any fetch, and fail closed.

## 3. Frozen selection and leakage rules

1. **Membership is fixed at launch.** A token enters if and only if it emits a `CreateEvent` inside
   a sampled block. Nothing enters later. (C3, no left-truncation.)
2. **Exhaustive within every block.** No filtering on creator, name, reserves, `is_mayhem_mode`,
   `is_cashback_enabled`, `quote_mint`, or anything else. (C4.)
3. **The grouping key for every train/validation/test split is `creator ∪ user`, never token and
   never time.** This is not advisory. B8a measured **50.4%** of members coming from a creator with
   more than one launch in a 13.6-minute window (**39.9%** in the tradable, Mayhem-excluded
   population), and `creator ≠ user` on 4 of 242 rows, giving a union actor space of 161 rather
   than 157. A split by token or by date puts the same actor on both sides and lets a model learn
   actor identity.
4. **A creator group is never split across blocks or across folds.** If any member of an actor group
   is in the test fold, the whole group is. Actor groups are formed **after** enumeration and never
   affect membership.
5. **Right-censoring per C1.** Members still in T3 at the end of `W_obs` are censored, not dropped
   and not relabelled.
6. **C2 is binding and concrete:** with `W_obs` = 8 days and `D_dead` = 7 days, **no T2 label is
   valid until 8 days after the launch window opens.**
7. **C5:** any recorder `gap` overlapping a member's lifetime marks that member **incomplete**;
   incomplete members are reported, never silently analysed.
8. **Quote regime is recorded and reported split, never pooled.** `sol_amount` must branch on
   `quote_mint` or fail closed, and `quote_mint` itself has two representations for SOL — event
   `111…111` versus account `So111…112` (B7l). A filter written against the wrong one returns
   **zero** SOL members and reads as "no SOL launches" rather than as a bug.
9. **Mayhem is recorded as a covariate and excluded from the *tradable* population at decision
   time** — a policy applied after selection, never a sampling step (B8a precedent, B2a/B7a basis).

## 4. Frozen size derivation

The sample size follows from a stated requirement rather than from convenience.

**Requirement:** the rarest regime the cohort is meant to speak about — order 1% (graduation is
expected near this; USDC quoting was 3.3% in B8a) — must be estimable to better than ±0.5
percentage points at 95%.

From B8a's measured rate — 242 launches over 813 s = **0.2977 launches/s** — a 24-hour window holds
about **25,700 launches**. Every whole-minute block size, with its cost (§5):

| block | fraction | n | 95% half-width at 1% | meets ±0.5 pp | fetch hours |
|---:|---:|---:|---:|:--:|---:|
| 3 min | 5.00% | 1,286 | ±0.54 pp | **no** | 4.6 |
| **4 min** | **6.67%** | **1,715** | **±0.47 pp** | **yes** | **6.2** |
| 5 min | 8.33% | 2,143 | ±0.42 pp | yes | 7.7 |
| 6 min | 10.00% | 2,572 | ±0.38 pp | yes | 9.3 |

**4 minutes is the smallest whole-minute block meeting the requirement**, so it is the one frozen.
At n ≈ 1,715 the half-width at the 3.3% regime (USDC, per B8a) is ±0.85 pp.

**A correction to the first freeze, recorded rather than quietly fixed.** That version claimed 6
minutes was the smallest block meeting this requirement. It was not — 4 minutes meets it, and the
error inflated the design by 50% in both sample and cost. The requirement itself is unchanged; only
the arithmetic deriving the block from it was wrong.

**The *fraction* is frozen, not the count.** The 25,700/day figure is an order-of-magnitude
extrapolation from a single 13.6-minute window and is **not a measurement**. Freezing a target
count would mean adjusting the sampling to hit it after seeing the data; freezing the time fraction
means the realised `n` falls where it falls and is **reported, whatever it is.** If the realised
rate is materially different from 25,700/day, that is a finding to report — **not** a reason to
resize the sample mid-run.

## 5. Cost — measured, not estimated, so it can be vetoed on budget rather than discovered mid-run

Both inputs are measured from the B8a artifact rather than assumed:

| Quantity | Value | Source |
|---|---:|---|
| slot rate | **2.4242 slots/s** | 2,000 slots over an 825 s block-time span |
| fetch throughput | **0.6275 slots/s** | 2,000 slots in **3,187 s** (`scanned_at_unix` span) |
| slots in 24 h | 209,455 | derived |
| **slots to fetch at 6.67%** | **~13,960** | derived |
| **wall-clock** | **~6.2 hours** | derived |

**Correction to the first freeze.** It stated "2,000 slots in roughly 37 minutes → on the order of
6 hours". The real B8a fetch took **53.1 minutes**, which put the true cost of that design at
**~9.3 hours**, not ~6. The figure the owner was asked to veto was understated by ~50%. Two
adjacent numbers also needed fixing and are recorded so the discrepancy is not rediscovered:
**2.4242 slots/s** counts *slots requested*, **2.3758** counts *produced blocks* over the same span
(they differ by the 2% skip rate), and the 2.3934 used in the first freeze came from B7j, not from
B8a. For cost, slots **requested** is the correct one.

The corrected block size (§4) brings the design to ~6.2 h — but that is a consequence of fixing the
arithmetic, **not** a design chosen to hit a cost target.

Throughput assumes the same free public endpoint and the same throttling behaviour B7h encountered;
a run under heavier throttling will take longer, and that is a reason to allow more wall-clock, never
a reason to stop early.

**If that cost is unacceptable, the correct response is to change the fraction *now*, in this
document, before any window exists — not to stop the run early.** A truncated run is a
time-of-day-biased sample wearing the label of a stratified one, which is worse than a smaller
honest sample. The scanner must therefore treat partial completion as **FAIL**, not as a result.

## 6. Window placement — deterministic, computed when the gate clears, not chosen now

The concrete 24-hour window is **deliberately not instantiated here**, for the same reason as in
B8a: a window picked with any outcome in view is not a preregistered window.

When it is instantiated, it is the **most recent** 24-hour span satisfying **all** of:

1. **Disjoint from every burned range**, with no partial overlap, failing closed:

   | Range | Origin |
   |---|---|
   | `[429,998,000, 430,000,000)` | B7e mature cohort |
   | `[430,000,000, 430,000,500)` | B7d pilot |
   | `[435,564,885, 435,565,324)` | B7j/B7k positive-control envelope |
   | `435,566,652 – 435,566,690` | B7b `D_dead` throwaway sample |
   | `435,569,119 – 435,569,149` | B7c trade-only gap sample |
   | **`[433,302,364, 433,304,364)`** | **B8a cohort — burned by this document (§7)** |

2. **Ending at least `W_obs` = 8 days before the current tip**, so every member has a full
   observation span and C2 is satisfiable.
3. **Entirely within one program regime** — no loader `Upgrade` slot inside the launch window or
   the observation span. B0 established a ~13-day upgrade cadence, so with `W_launch + W_obs` = 9
   days this is **tight and must be checked, not assumed.** If no qualifying window exists, that is
   a reportable finding, not a licence to relax the constraint.
4. Slot↔wall-clock mapping for the hourly strata is taken from on-chain `blockTime`, and **any
   ambiguity in that mapping fails closed** rather than being resolved by assumption.

## 7. B8a is burned by this document

The B8a window `[433,302,364, 433,304,364)` is **excluded from all future training, validation and
test use.** Its composition has been inspected in detail — quote-regime split, Mayhem breakdown,
creator concentration, largest-creator identity — and `research/B8A_COHORT_CENSUS.md` is public
within the project. Selecting a new window with that knowledge in hand, or reusing those members,
would be selection with outcomes partly in view. **B8a remains valid as the substrate it was
authorised to be; it is simply no longer usable as evaluation data.**

## 8. Prohibited inferences

1. **No rate or distribution may be published from an incomplete run.** Partial completion is FAIL.
2. **No claim that creator grouping removes leakage.** It removes *creator* leakage.
   **Funding-cluster leakage is a superset and remains unmeasured** — two creator pubkeys funded
   from one source are one actor, and nothing in this design detects that.
3. **No pooling across quote regimes**, and no reading of `sol_amount` without branching on
   `quote_mint`.
4. **No treating T2 as absorbing.** A resumption was observed at 450.8 h; a T2 member that trades
   again is a recorded **re-entry**.
5. **No generalising this cohort beyond its single program regime and its single 24-hour window.**
   One day is one day: it carries a day-of-week and a market-conditions confound that this design
   does not remove and does not claim to.

## 9. What this document does not decide

No label, no feature, no model, no threshold, no baseline ordering beyond what `PLAN.md` Phase 4
already fixes (do-nothing, then random entry, then fixed-filter, before any model). Freezing the
cohort rule **before** the labels is the point — B7j's outcome-positive envelope is the standing
example of what happens otherwise.

## Gates

Read-only when it eventually runs. No signing, no spending, no deployment, no live or devnet
transactions. Credentials sourced silently and never printed or persisted.
