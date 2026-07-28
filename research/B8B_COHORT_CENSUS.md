# B8b — Cohort census

> **STATUS: DRAFT SKELETON — NO RESULTS. The scan is still running and no number below is filled in.**
> Every `«…»` is an unfilled placeholder. **This document must not be quoted, cited, or treated as a
> result in this state.** It exists so that the framing, the limitations and the prohibited
> inferences are fixed **before** any number can shape them — the same discipline that froze the
> sample (`B8B_SUBSAMPLING_PREREGISTRATION.md`) and pre-specified the analysis (`b8b_census.py`).
> Drafted by Claude 2; to be audited by Claude 1, who wrote the freeze this is judged against.

**Frozen rule:** `research/B8B_SUBSAMPLING_PREREGISTRATION.md`, sha256
`56d8a83b8cbc0821fabb5e5b8e098728caa2d7775d46f0c9fb55e673cf848374`.
**Owner authorisation:** `agent_discussion.md` Seq 121 — 4 minutes/hour.
**Window:** `[433,894,233, 434,097,833]`, 203,601 slots, 24.000 h, pinned by the Seq-123 pre-flight
against finalized tip 435,741,966.
**Artifact:** `research/b8b_cohort_433894233_434097833.sqlite`, sha256 `«artifact»`.
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
| sampled blocks | «24» |
| sampled slots | «n_sampled» |
| retrieved / skipped | «retrieved» / «skipped» |
| skips verified absent by `getBlocks` | «verified» |
| slots unaccounted for | «missing» |
| decode errors | «decode_errors» |
| members outside every sampled block | «outside» |

**Partial completion is FAIL, not a smaller result** (freeze §5). A truncated run is a
time-of-day-biased sample wearing the label of a stratified one.

## Cohort size and the precision it actually supports

> **«n» members, and at that `n` the 95% interval at p ≈ 1% is ±«hw» pp.**

Stated in one sentence deliberately, per **owner decision A** (`DECISIONS.md`, 2026-07-28):
separating a proportion from its interval is how a reader ends up quoting the first without the
second.

The design was sized against a **±0.5 pp bar at p ≈ 1%**, assuming ~25,700 launches/day
extrapolated from B8a's single 13.6-minute window. **The freeze fixed the sampling *fraction*, not
a target count** — *"the realised `n` falls where it falls and is reported, whatever it is"* — so a
realised `n` below the assumption is a **reported outcome, not a defect and not grounds to resize
the sample after the fact.**

- bar met at p ≤ «max_p» — «met/missed» at p = 1%
- `n` that would have been required for the bar at p = 1%: «n_required»

## Per-stratum yield

Stratification only means something if every hour actually contributed.

«per-hour table»

Two different things must not be conflated, and the census separates them:

- **observed, zero launches** — an observation, reported as a NOTE. Failing on it would conflate
  *"we looked and found nothing"* with *"we did not look"*.
- **zero retrieved slots** — no observation power in that hour, and a **failure**.

## Quote regime — reported split, never pooled

«regime table»

**`sol_amount` must branch on `quote_mint` or fail closed** (B7k). And `quote_mint` itself has two
representations for SOL — event-derived `111…111` versus account-derived `So111…112` (B7l) — so a
filter written against the wrong one returns **zero** SOL members and reads as *"no SOL launches"*
rather than as a bug.

## Regime covariates — recorded, not filtered

«mayhem / cashback table»

Mayhem is a **covariate excluded at decision time**, never a sampling step. Excluding it is a
**change in creator composition**, not a row filter — in B8a it removed the most concentrated block
of the cohort, which is why tradable leakage read *lower* than raw.

## Actor leakage under the frozen `creator ∪ user` key

«leakage table: all vs tradable»

The split key is `creator ∪ user`, **never token and never time**, and **an actor group is never
split across folds**. Two figures are reported separately and must not be swapped:

- **members belonging to a repeat actor** — the exposed share.
- **surplus beyond one-each** — a different quantity. B8a's first census quoted the surplus (35.1%)
  as if it were the exposed share (50.4%), and the correction is why both are labelled here.

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
| **C2** launch window must end ≥ `D_dead` before the observation window ends | **satisfied by construction** — the window was pinned 8.000 days before tip. |
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
python3 scripts/b8b_census.py --json «out».json  # read-only; exits non-zero unless COMPLETE
```

The artifact is self-describing: `metadata` carries the freeze hash, the IDL hash, the rule string,
stride, modulus, block length and the window bounds, and `sampled_block` holds all 24 resolved
ranges — so the sample can be re-derived without trusting this document.
