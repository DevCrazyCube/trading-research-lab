# Token Lifecycle, Terminal States, and Censoring Rules

Version 0.3 — 2026-07-28. Authors: Claude, Codex review. Status: **RATIFIED** by the owner
2026-07-28. `DECISIONS.md` remains authoritative; this document states the rules, and every
parameter in §4 is now frozen there.

**What ratification does and does not settle.** The terminal states (T1a/T1b/T2/T3), the censoring
rules (C1–C5) and all three §4 parameters are adopted. **Two things are deliberately still open and
are not licensed by this ratification:** the **subsampling rule** for a 24-hour launch window (which
must be frozen a priori and grouped by `creator ∪ user`), and **funding-cluster leakage**, which is
unmeasured. Neither may be treated as settled because this document is.

**Superseded amendment note (kept for the record).** v0.2 amended §4 to correct the `D_dead` row
from "unset" to the value the owner had already ratified in `DECISIONS.md`. That was transcription
of an existing decision, not a new one, and it did **not** ratify this document. `W_launch` and
`W_obs` were then still unset and were
still owner choices, which is why v0.2 remained a proposal. The owner has since chosen both, so
that blocker is discharged and the status above reflects it.

Written to close Codex's Seq-35 blocker: *"define terminal/censoring rules before updating B6J's
100–1,000 tokens/day estimate."* It also addresses the first unchecked item in `PLAN.md` Phase 0
("freeze definitions for rug, dump, graduation, …"), which has stayed open while the project did
Phase 1 measurement work.

All lifecycle anchors below are grounded in the pinned IDL (`research/pump_idl_9c82f61.json`),
not in intuition.

## 1. Lifecycle anchors that exist on-chain

| Anchor | Source | Carries |
|---|---|---|
| **Launch** | `CreateEvent` | `mint`, `bonding_curve`, `creator`, `user`, `timestamp`, initial virtual/real reserves, `token_total_supply`, `is_mayhem_mode`, `is_cashback_enabled`, `quote_mint` |
| **Curve completion** | `CompleteEvent` | `mint`, `bonding_curve`, `user`, `timestamp`, `quote_mint` |
| **Pool migration** | `CompletePumpAmmMigrationEvent` | `mint`, `bonding_curve`, `pool`, `mint_amount`, `sol_amount`, `pool_migration_fee`, `timestamp` |
| **Terminal flag** | `BondingCurve.complete: bool` | account state |
| **Activity** | `TradeEvent` | per-trade, with reserves |

**Observation worth recording: completion and migration are two distinct events.**
`DOCUMENTATION.md` currently describes migration as automatic and irreversible following
graduation. The IDL exposes `CompleteEvent` and `CompletePumpAmmMigrationEvent` separately, and
`migrate` / `migrate_v2` are separate *instructions*. Whether an interval — or a failure mode —
can exist between them is **an open question**, and it matters: a token that has completed but not
migrated is in a state where the curve is closed and the pool may not yet exist, which is exactly
the kind of window where exit liquidity disappears. Must be measured, not assumed.

## 2. Terminal states (proposed)

A cohort member is in exactly one state at any evaluation time.

- **T1 — Graduated.** `CompleteEvent` observed. Curve trading ends. Sub-state `T1a` migrated
  (`CompletePumpAmmMigrationEvent` observed) or `T1b` completed-not-yet-migrated.
- **T2 — Inactive-at-threshold (formerly “abandoned”).** No `TradeEvent` for the mint in `D_dead`
  consecutive wall-clock time, and no `CompleteEvent`. This is a reversible bookkeeping label,
  not a terminal fact: a later trade produces an explicit re-entry transition. “Abandoned” may be
  retained as a display alias only if this non-terminal meaning is stated. **This is a definitional
  choice, not an observation** — see §4.
- **T3 — Active.** Neither terminal condition met at evaluation time. Right-censored.

There is deliberately **no "rugged" terminal state.** Rug is an *outcome label* about price and
extractable value, not a lifecycle state, and conflating the two is how leakage enters: "rugged"
is usually recognised from post-collapse behaviour. Lifecycle state must be derivable from
mechanical on-chain anchors only. Rug/dump labels belong in Phase 3 and must be defined
separately, from price and liquidity paths, never from lifecycle membership.

## 3. Censoring rules (proposed)

Survival analysis is already in `PLAN.md` Phase 4, so censoring must be explicit rather than
implicit.

- **C1 — Administrative right-censoring.** Every cohort member still in T3 at the end of the
  observation window is right-censored at that instant, not dropped and not treated as abandoned.
  Dropping them is survivorship bias; treating them as abandoned is fabrication.
- **C2 — Launch-window / observation-window separation.** The launch window (which launches enter
  the cohort) must end at least `D_dead` before the observation window ends. Otherwise the most
  recent launches *cannot* reach T2 by construction, and abandonment rates are biased downward
  purely by window geometry. Codex's Seq-35 note that its two sampled launches were
  "future-right-censored" is exactly this problem.
- **C3 — Left-truncation is forbidden.** Cohort membership is fixed at `CreateEvent`. A token may
  never enter the cohort because it later became interesting. This is the single most important
  anti-leakage rule here.
- **C4 — Exhaustive within window.** Every `CreateEvent` in the launch window enters the cohort.
  No filtering on creator, name, initial reserves, or any other attribute — filters are a *policy*
  applied later at decision time, using only information available then, never a sampling step.
- **C5 — Recording gaps censor.** If the recorder had a `gap` overlapping a member's lifetime, that
  member's history is **incomplete**, and it must be flagged rather than silently analysed. This
  is what the `gap` register exists for.

## 4. Parameters that are choices, and must be frozen before any outcome is looked at

| Parameter | Meaning | Status |
|---|---|---|
| `D_dead` | inactivity duration defining T2 abandonment | **FROZEN: 7 days (604,800 s)** — ratified by the owner 2026-07-28, `DECISIONS.md` |
| `W_launch` | launch window length | **FROZEN: 24 hours** — ratified by the owner 2026-07-28, `DECISIONS.md` |
| `W_obs` | observation window length, `≥ W_launch + D_dead` | **FROZEN: 8 days** — ratified by the owner 2026-07-28, `DECISIONS.md` |

`D_dead` was frozen at a **~2.5% false-death rate**, chosen against the resumption curve measured
in `research/B7G_COHORT_AUDIT.md` (12.1% at 24 h, 5.3% at 72 h, 2.5% at 7 d, 0.5% at 14 d, **no
knee**). It was a false-death-rate budget, not a research question. This row previously read
"unset" **after** the owner had ratified the value, which contradicted `DECISIONS.md`; corrected
2026-07-28 (`agent_discussion.md` Seq 107). `DECISIONS.md` remains authoritative — this table
transcribes it and never overrides it.

Two consequences of the frozen value, recorded here because they constrain every cohort:

- **C2 is now concrete:** a launch window must end **at least 7 days** before the observation
  window ends, or the most recent launches cannot reach T2 by construction.
- **T2 is not absorbing.** A resumption was observed after 450.8 hours (18.8 days). A T2 member
  that trades again is recorded as a **re-entry**, never silently reclassified or dropped.

`W_launch` and `W_obs` were chosen by the owner on 2026-07-28 at the **minimum** value satisfying
`W_obs ≥ W_launch + D_dead` (1 + 7 = 8 days), which buys the shortest calendar delay before a T2
label is valid. They are scheduling choices, not empirical claims, and were fixed **before any
outcome in a candidate cohort was inspected**. For the authorised B8a cohort they remain pinned by
`research/B8A_DISJOINT_COHORT_PREREGISTRATION.md` rather than by this table; these values govern
**future** cohorts.

Two consequences that constrain every future cohort:

- **No T2 label is valid until 8 days after the launch window opens.** Anything computed earlier is
  right-censored by window geometry alone, per C2.
- **A 24-hour launch window REQUIRES a subsample.** B8a observed 242 launches in 813 s (~17.6/min),
  which extrapolates to roughly **25,000 launches per 24-hour window** — an order-of-magnitude
  estimate from one 14-minute window, not a measurement, but decisive on the point. **The
  subsampling rule is a separate decision, is NOT yet frozen, and must group by `creator ∪ user`,
  never by token or by time.** 50.4% of B8a members came from a creator with more than one launch
  in a 14-minute window (39.9% in the tradable, Mayhem-excluded population), so a naive split puts
  the same actor on both sides and lets a model learn actor identity instead of anything
  generalisable. **Funding-cluster leakage is a superset of this and remains unmeasured.**

**These must be chosen before outcomes are inspected.** Selecting `D_dead` because it makes a
result look better is optimising on the evaluation set, which `PLAN.md` already forbids for model
thresholds; the same logic applies to label definitions, and label definitions are the easier
place to cheat without noticing.

Recommended procedure: pick `D_dead` from the *inter-trade interval distribution* of a
**throwaway** early sample that is then discarded and never used for evaluation — not from the
cohort under study.

Mint-address signatures are not a valid substitute for this final choice without a directional
qualification. Non-trade activity inserts timestamps between trades and splits true trade-silence
intervals into shorter pieces. A threshold derived from all address activity can therefore be too
short and is **anti-conservative for avoiding false inactivity labels**. It is useful as a pipeline
probe only; ratification requires `TradeEvent`-only intervals or a proved bound.

## 5. Consequence for B6J's cohort sizing

B6J estimated 100–1,000 tokens/day of complete cost-level reconstruction at the free endpoint's
~2.5 `getTransaction`/s, using an **assumed** per-token lifetime transaction count. That
assumption cannot be replaced by measurement until the above are fixed, because "lifetime
transaction count" is undefined without a terminal state:

- counting to `CompleteEvent` measures graduated tokens only, and is survivor-biased;
- counting to last-observed-activity measures a right-censored quantity;
- counting to T2 requires `D_dead`.

So the correct order is: **freeze §4 parameters → build an exhaustive launch window per §3 →
measure the lifetime distribution with censoring handled → then revise the cohort estimate.**
Codex is right that `n=2` supports no percentile claim; the deeper issue is that the quantity
being estimated is not yet well defined.

## 6. Open questions

1. A token can sit in `T1b` (F46); its duration distribution remains unmeasured and directly
   relevant to exit liquidity.
2. Does `CompleteEvent` always precede `CompletePumpAmmMigrationEvent`, and is either ever absent
   for a graduated token?
3. Are there launches whose `quote_mint` is non-SOL (B2c found none in 337 events, <1%)? If so,
   cohort definition must state whether they are in scope.
4. F43 established that `toggle_mayhem_mode` changes global launch configuration and cannot mutate
   an individual existing curve. Launch-time Mayhem status is therefore stable per token, while
   the population regime can change over calendar time.

The sharpest remaining question is a TradeEvent-only `D_dead` derivation on a disjoint burned
sample. The address-signature proxy cannot ratify the threshold.
