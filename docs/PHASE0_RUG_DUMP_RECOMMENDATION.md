# Phase 0 rug/dump conflict — audit and owner-ready recommendation

Version 1.0 — 2026-07-30. Author: Claude (`agent_discussion.md` Seq 239).
Status: **RECOMMENDATION ONLY. Nothing is edited or ratified.** `PLAN.md` and `docs/DEFINITIONS.md`
are untouched by this document, as instructed. `DECISIONS.md` remains authoritative.

## Recommendation

**Adopt Option A.** Move rug/dump **label construction** to Phase 3 (where `PLAN.md` already puts
it) and freeze the **leakage constraints** in Phase 0.

**Option B — a full leakage-safe Phase 0 specification — cannot be done honestly today**, for a
reason internal to the project rather than a matter of taste. See §4.

## 1. The conflict is narrower than it looks, and the project has already resolved it five times

| document | text |
|---|---|
| `PLAN.md` Phase 0, line 31 | "Freeze **definitions** for rug, dump, graduation, executable return, drawdown, and liquidity failure." |
| `PLAN.md` Phase 3, line 67 | "**Create** executable return, drawdown-first, dump hazard, graduation, and liquidity **labels**." |
| `docs/DEFINITIONS.md` §2 (RATIFIED) | "Rug/dump **labels** belong in Phase 3 and must be defined separately, from price and liquidity paths, never from lifecycle membership." |

**`PLAN.md` already lists the same terms in both phases.** Graduation, executable return, drawdown
and liquidity appear in Phase 0 as *definitions to freeze* and in Phase 3 as *labels to create*.
That is not a contradiction; it is a deliberate two-stage design — **define in Phase 0, construct in
Phase 3** — and the project has already executed it:

- **Graduation** is *defined* in ratified `DEFINITIONS.md` §2 (T1/T1a/T1b) and *listed* as a Phase 3
  label. Nobody has called that a conflict.
- **Executable return, drawdown and liquidity failure** are *defined* in `docs/EXECUTABLE_RETURN.md`
  v0.1 and *listed* as Phase 3 labels.

So `DEFINITIONS.md` §2's "belong in Phase 3" is a statement about **construction**, and it is
consistent with `PLAN.md` Phase 3. The only genuine defect is that **`PLAN.md` line 31 does not
distinguish the two**, and reads as though the rug/dump label itself must be built in Phase 0.

**Option A is therefore not a concession to `DEFINITIONS.md`.** It makes `PLAN.md` say for rug/dump
what it already implies for the other five terms.

## 2. Why no future information becomes a historical decision feature

This is the load-bearing question, and the answer is that **leakage is a plumbing property, not a
definitional one.**

### 2a. Labels are permitted to use future information. Features are not.

`AGENTS.md`: *"Never use future information to construct a historical decision **feature**."* The
prohibition is on features. A label is the quantity being predicted and is by construction measured
after the decision. The project has already ruled on exactly this, in B9a:

> This is the label at end-of-observation, not a point-in-time feature. Current account state read
> ≥8 days after launch is exactly the T1/T2 label `W_obs` was defined to permit. **It must never be
> used as a feature.**

*(Source: the B9a preregistration, `agent_discussion.md` Seq 176 point 3.)*

A rug/dump label recognised from post-collapse behaviour is therefore **not** leakage in itself.
`DEFINITIONS.md` §2's real target is narrower and correct: a rug must not become a **lifecycle
state**, because lifecycle state *is* consumed as point-in-time input, and a "rugged" state would
smuggle post-collapse information into the feature path.

### 2b. Three mechanisms actually cause leakage, and each needs one frozen constraint

**R1 — Label/feature separation (mechanical).** Fix the decision instant `t0` as the feature
vector's timestamp. The label window is `(t0, t0+H]`. **No feature may read any row whose
observation time is > t0.** `AGENTS.md` already requires that features and labels be separable
stores; R1 binds rug/dump to it. This is mechanically auditable and is precisely what Phase 3's gate
audits — *"no post-decision information enters features."*

**R2 — No definition or threshold chosen after seeing outcomes.** This is the failure
`DEFINITIONS.md` is really guarding against, and it has already happened once in this project: Seq
178 disclosed that `is_cashback_enabled` separates the tradable population 1.83% vs 0.93%, found
while auditing outcomes, and was deliberately **not** reported as a finding. The rug/dump definition
and every threshold must be frozen **before** being measured on any cohort.

**R3 — Never on B8b.** `DECISIONS.md` burns the B8b window for future cohort selection, and B9a's
outcome distribution is published. Any rug/dump label must be measured on a **fresh preregistered
window, disjoint from all seven burned ranges**, failing closed per freeze §6.1.

**R4 — Horizon geometry, reusing ratified C1/C2.** A label with horizon `H` requires the launch
window to end at least `H` before the observation window ends, or recent members cannot reach the
label and the rate is biased downward by geometry alone. Members that cannot reach it are
**right-censored (C1), never dropped and never labelled "not rugged."** This is C2 generalised from
`D_dead` to `H`.

**R5 — Actor grouping, not token grouping.** Any train/test split for a rug/dump model must group by
`creator ∪ user`, per `DEFINITIONS.md` §4 — 50.4% of B8a members shared a creator with another
launch in a 14-minute window. **Funding-cluster leakage is a superset of this and remains
unmeasured**, so R5 is a floor, not a solution.

### 2c. What R1–R5 do not require

**None of them needs the reserve path, a threshold, or any outcome.** They are writable and freezable
today, with zero data. That is what makes Option A completable now.

## 3. Exact edits required for Option A

**None of these are applied by this document.**

**Edit 1 — `PLAN.md` line 31.** Replace:

```
- [ ] Freeze definitions for rug, dump, graduation, executable return, drawdown, and liquidity failure.
```

with:

```
- [ ] Freeze definitions for graduation, executable return, drawdown, and liquidity failure.
- [ ] Freeze the leakage constraints (R1-R5) that any rug/dump outcome label must satisfy.
      Rug/dump label CONSTRUCTION is Phase 3, per docs/DEFINITIONS.md section 2 and the Phase 3
      item below; Phase 0 freezes the constraints, not the thresholds.
```

**Edit 2 — `PLAN.md` Phase 3, line 67.** Append `rug/dump` explicitly so the construction site is
unambiguous:

```
- [ ] Create executable return, drawdown-first, dump hazard, rug/dump, graduation, and liquidity
      labels, each satisfying the Phase 0 leakage constraints R1-R5.
```

**Edit 3 — a new `DECISIONS.md` entry** recording: the conflict, that Option A was chosen, R1–R5 as
frozen constraints, and that thresholds are explicitly not frozen.

**Edit 4 — `docs/DEFINITIONS.md`.** *Recommended: no change.* Its §2 is already consistent with
Option A. If the owner prefers symmetry, a one-line pointer to R1–R5 could be added, but amending a
ratified document to restate something it already implies is a cost without a benefit.

**Not required:** no change to the Phase 0 gate. *"Labels, exclusions, and evaluation protocol are
documented before model research"* is satisfied by definitions plus R1–R5, and it does not say
"constructed."

## 4. Why Option B cannot be done honestly today

A leakage-safe Phase 0 *specification* of rug/dump would have to state what counts as one. Every
candidate formulation needs a magnitude and a horizon — "executable exit value fell by X% within
`H`" — and:

- **X and H cannot be calibrated without the reserve path**, which B9d is collecting now and which
  has not published. B9a's F2 correction is precisely the lesson: a terminal snapshot cannot report
  on the path, because a curve that ran to 30 SOL and fully round-tripped returns to its launch
  state, indistinguishable from one nobody ever bought.
- **Choosing X and H today would violate R2 by construction**, because B9a's outcome distribution is
  already published and in view. That is the move the whole preregistration apparatus exists to
  prevent.

So Option B either guesses the thresholds — contaminating them — or defers them, at which point it
*is* Option A with more words. **Option A is B done in the correct order.**

## 5. Remaining open questions

1. **Horizon `H`.** Requires the reserve path. Must be frozen before measurement, on a fresh cohort,
   and derived from a **throwaway** sample per `DEFINITIONS.md` §4's procedure for `D_dead`.
2. **Is "rug" one label or several?** Creator-extraction and organic collapse are different
   phenomena with the same price signature. Separating them needs actor and funding-cluster
   evidence, and **funding-cluster leakage is unmeasured**.
3. **Overlap with liquidity failure.** `docs/EXECUTABLE_RETURN.md` defines L1/L2/L3. A rug may be a
   *cause* of L1 rather than a separate outcome. The relationship must be stated or the two labels
   double-count the same event.
4. **`T1b` is a rug mechanism that is not a price move at all.** A token completed but not migrated
   has a closed curve and possibly no pool — exit is structurally unavailable (L3). Its duration
   distribution is unmeasured (`DEFINITIONS.md` §6.1). A price-based rug definition would miss it
   entirely.
5. **Mayhem is excluded, and it is the clearest case.** B9a measured `set_mayhem_virtual_params`
   moving **425 of 427** Mayhem curves off the launch invariant — administrative mutation of the
   price math, arguably the purest rug mechanism on the platform. The frozen safety exclusion means
   **the rug label will never be exercised on the clearest examples of the thing it names.** That is
   defensible as a *trading* policy and worth stating plainly as a *measurement* limitation.
6. **Does a rug label change any decision?** The tradable population graduates at 1.41% and 94.6% of
   non-graduates hold under 0.01 SOL terminally. If nearly everything ends near zero, a rug label may
   have very little variance to explain, and its cost/benefit should be checked before Phase 3 builds
   it.
