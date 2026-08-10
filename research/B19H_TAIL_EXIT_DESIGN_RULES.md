# Exit design on the selected tail — rules frozen before any outcome was computed

**Status.** EXPLORATORY, on the BURNED development corpus only. Frozen and committed **before**
any P&L under these rules was calculated. Nothing here may be reported as an evaluation result;
the fresh window's passes are spent and a fresh-window claim needs its own preregistration.

**Why this exists.** The selection test established that the tail is identifiable at entry (creator
launch deposit ≥ 3 SOL: 59.8% ever profitable vs 23.6% control, reproduced independently) and that
**none of B19F's eight frozen exit rules monetises it** — every selection × exit cell negative. The
mechanism found was: selection concentrates curves that pump **and dump**, while excluding the dead
curves whose own deposit returns nearly whole. So selection buys upside and sells downside
protection.

The one question left: **does an implementable exit exist for the identified tail?**

## Why B19F's exits could not have answered this

Its three drawdown rules fire at `realizable ≤ peak/10`, `peak/4`, `peak/2` — exits after a **90%,
75% and 50% fall from peak**. Its horizons were 1,000 and 10,000 slots. Nothing in the frozen set
was a **take-profit**, and nothing was a **tight** trailing stop. The rules below are chosen to
cover exactly that gap, and they are derived from the mechanism above rather than from any table.

## The grid, frozen

Entry: first observation in a slot strictly after t0. Selection: launch-transaction deposit
≥ 3 SOL. Position 100,000,000 lamports, B19D base cost scenario, b10a kernel, exact integers.

**A. Take-profit.** Exit at the first observation whose net ≥ the target. Rationale: a pump is a
transient, and a target converts it before it reverses. Targets: **+10%, +25%, +50%, +100%**.

**B. Tight trailing stop.** Track peak realizable net; exit when it falls to `(1 − Y)` of that peak.
Rationale: B19F's loosest-in-the-world stops rode every dump to the floor. Y: **10%, 20%, 33%**.

**C. Take-profit with a trailing stop.** Whichever fires first, from A × B at
**{+25%, +50%} × {10%, 20%}**. Rationale: the target captures the pump, the stop bounds the case
where the pump never comes.

**D. Short time-box.** Exit at the first observation at or after `entry_slot + N`. N: **100, 500**.
Rationale: B19F's shortest horizon was 1,000 slots; if pumps are transient the relevant scale may
be an order of magnitude shorter.

**E. Baselines, mandatory.** Unconditional-selection with the same rule, and B19F's
`E_FIRST_OBSERVATION`, so any improvement is measured against something already known.

Total: 4 + 3 + 4 + 2 = **13 rules**, each on selected and unselected curves. No rule may be added,
dropped or retuned after results are seen. If a rule fails, it is reported as failing.

## Stuck positions

A position whose rule never triggers, or whose exit is never payable, is valued **both** ways and
both are reported:
- **(a) pessimistic:** total loss of outlay.
- **(b) sell-back:** sold into one's own deposit at the final observed state, deposit-adjusted
  `(vq+q_in, vt−tokens, rq+q_in, rt−tokens)`.

Truth lies between. Neither is quoted alone.

## The success bar, frozen

A rule is interesting only if, **on the held-out test split**, with **n ≥ 50** fired:

1. mean net **> 0**, and
2. median net **> 0**, and
3. both hold under **both** stuck-position conventions, and
4. it beats the same rule applied to the **unselected** population.

Anything less is reported as a failure to clear the bar. A rule that is positive under only one
convention, or only in the mean, is **not** a result — the mean alone is a tail artefact and this
project has already been fooled once by exactly that.

## What a negative result would mean

That the tail is identifiable but not harvestable by any simple exit — which closes the question
rather than leaving it open, and is worth as much as a positive.
