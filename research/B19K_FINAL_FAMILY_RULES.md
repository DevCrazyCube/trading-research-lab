# The final family — take-profit × abandon-at-deadline, frozen before any outcome

**Status.** EXPLORATORY, BURNED corpus. Frozen and committed **before** any P&L under it was
computed. **This is the last family either seat runs on burned data**, by prior agreement, whatever
it returns. Its only real test would be a preregistered fresh-window pass — and per the owner's
decision, the conversation about what it would mean to trade this happens **before** that
preregistration is written, not after the numbers read well.

## Why this shape, and why it is no longer fitting

The same class was ruled **fitting** earlier, correctly: its only justification then was one row of
a searched table. Every component now derives from a **rule-free measurement** taken without
reference to any rule's performance:

1. **Profit arrives early.** Time to first profitable state on selected tail curves: median **3
   slots**, p75 **10**. The latency table independently puts ~85% of the attainable mean within 500
   slots and two-thirds within 100.
2. **The windows are wide enough to act inside.** 100% of selected tail curves hold a profitable
   standing state for ≥2 slots — the minimum for a provable observe-at-s, act-at-s+1 capture.
   Median longest window **68 slots**, p75 **207**, p90 **746**. Reproduced independently; the peer
   seat's own run gives 98.5% / 23 / 140 / 441 under stricter span accounting. Either way: wide.
3. **The non-firing mass is the killer, not the timing.** Every one of the 26 rules tested held
   non-firing curves to the end, which the campaign has repeatedly measured as the worst available
   disposition. The +10% near-miss was positive on the 58 that fired and destroyed by the 49 held.

So: take the profit early because that is where it is, and **cut** what does not fire rather than
holding it. That is the shape the measurements specify, and nothing in it was read off a P&L table.

## The grid

Selection: launch-transaction deposit ≥ 3 SOL. Entry: first observation in a slot strictly after
t0. Position 100,000,000 lamports, B19D base scenario, b10a kernel, exact integers. Burned corpus,
held-out test split.

**Take-profit levels, set from the ceiling's own quantiles on selected profitable curves** —
measured before this freeze and stated here: p10 **+6%**, p25 **+17%**, median **+40%**, p75
**+82%**. Not round numbers, not swept.

**Deadlines**, from the latency knee and the window widths: **50, 100, 250, 500 slots** after
entry.

**Rule:** exit at the first observation whose net ≥ the take-profit level; if none has occurred by
`entry_slot + deadline`, **abandon** — exit at the state in force at the deadline, whatever it is.

**Declared comparison count: 16** (4 levels × 4 deadlines). One family, counted, no additions.

## Baselines, mandatory

Exit at first observation (the incumbent, −7,289,855 mean / −4,760,019 median pessimistic on
selected), and the same 16 cells on the **unselected** population as control.

## Stuck positions

A cell whose exit is unpriceable at the chosen coordinate is valued **both** ways and both
reported: **(a)** total loss of outlay; **(b)** sell-back into one's own deposit, deposit-adjusted.
Neither is quoted alone.

## The bar, unchanged

n ≥ 50 fired, mean **> 0** AND median **> 0**, under **both** conventions, beating the frozen
incumbent. A rule positive only in the mean is not a result.

## What happens either way

- **Clears:** exactly **one** candidate is carried forward — the single best cell, named in
  advance as the selection rule — and it goes no further than a preregistration draft until the
  ethics conversation has happened.
- **Misses:** the trading search closes. Twenty-six rules across two channels, plus a family whose
  shape the venue's own structure specified, all failing, is a closed question rather than an
  unfinished one.

---

# RESULT — zero of sixteen clear. The trading search closes.

Grid exactly as frozen at `31d5878`. Burned test split, 107 selected curves. Nothing added,
dropped or retuned.

**Zero cells clear the bar.** The best cells by median are the +6% take-profits, which are
**positive in median under both conventions** (+6,149,652 to +6,770,507) and **negative in mean**
(≈ −11.2M to −11.6M) — the exact shape the bar was written to reject, and the same shape as the
earlier near-miss.

| TP | deadline | hits | sel. mean (pess) | sel. median (pess) | sel. mean (sellback) |
|---|---|---|---|---|---|
| 6% | 100 | 57 | −11,619,208 | **+6,252,299** | −8,266,839 |
| 6% | 500 | 61 | −11,224,676 | **+6,770,507** | −7,872,307 |
| 17% | 500 | 53 | −9,441,706 | −3,426,698 | −6,089,336 |
| 40% | 100 | 35 | −7,611,125 | −20,438,451 | −4,258,756 |
| 82% | 100 | 9 | −13,927,967 | −24,977,757 | −10,575,597 |

## The decomposition, which is the whole answer

For the best cell (+6%, deadline 100):

- **53% hit the target**, each worth about **+6,000,000** (+6%)
- **47% are abandoned**, each worth about **−31,705,105** (−32%)

You win small more than half the time and lose roughly **six times as much** on the rest. A +6%
target against a 4.75% toll leaves about **1.25% of real edge per win**, and **one abandoned
position erases about five wins**.

Raising the target does not fix it: the hit rate collapses faster than the payoff grows (82%
target hits 9 of 107). Extending the deadline does not fix it: it adds a few late hits while the
abandoned positions decay further.

## What is now closed

Twenty-six exit rules across two independent information channels, then a sixteen-cell family
**whose shape the venue's own structure specified** — profit arrives early, windows are wide
enough to act inside, the non-firing mass must be cut. All fail.

This is no longer "we picked the wrong rule". The measurements said what shape a working rule
would have; that shape was built, frozen and run; and the arithmetic that defeats it is not timing
or selection but the **asymmetry between a capped win and an uncapped loss** on an asset whose
median outcome is a total drain.

The identified tail is real. The windows are real. The profit is real and reachable. And capturing
it requires being right about *which* curves, not merely *when* — because the ones you are wrong
about cost six times what the ones you are right about pay.

**The trading search is closed.** What remains true and worth keeping is the map: the toll is
arithmetic, the liquidity wall is a cliff that replicates, selection is real at 2x lift, creator
persistence is real at rho 0.51, the ceiling exists and its shape is known, and every channel that
fails now fails for a stated mechanical reason rather than for want of trying.
