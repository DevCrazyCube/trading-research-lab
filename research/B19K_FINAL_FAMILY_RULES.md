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
