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

---

# RESULT — the bar is not cleared

Run on the burned corpus, test split, selection = launch deposit ≥ 3 SOL, 107 selected curves.
Grid exactly as frozen above: nothing added, nothing dropped, nothing retuned.

**No rule clears the bar.** Not one of the thirteen is positive in mean *and* median under *both*
stuck-position conventions.

| rule | fired | sel. mean (pess) | sel. median (pess) | sel. mean (sellback) | sel. median (sellback) | unsel. mean |
|---|---|---|---|---|---|---|
| take_profit +10% | 58 | −38,736,667 | **+10,279,477** | −8,489,522 | **+10,279,477** | −85,341,752 |
| take_profit +25% | 49 | −42,027,018 | −103,394,280 | −6,282,742 | −6,507,134 | −88,306,153 |
| take_profit +50% | 35 | −51,368,837 | −103,394,280 | −7,617,102 | −29,011,660 | −92,651,591 |
| take_profit +100% | 15 | −73,875,209 | −103,394,280 | −19,026,310 | −38,234,695 | −95,391,065 |
| trail 10% | 64 | −35,090,055 | −9,908,216 | −8,213,706 | −4,749,281 | −77,556,933 |
| trail 20% | 64 | −35,856,116 | −9,908,216 | −8,979,767 | −4,977,960 | −77,692,368 |
| trail 33% | 64 | −36,582,229 | −9,908,216 | −9,705,880 | −4,977,960 | −78,827,270 |
| tp+25% trail10% | 64 | −33,883,389 | −4,977,960 | −7,007,040 | −4,749,281 | −77,906,265 |
| tp+50% trail10% | 64 | −31,905,496 | −4,977,960 | −5,029,147 | −4,749,281 | −77,636,555 |
| timebox 100 slots | 69 | −37,345,875 | −43,645,195 | −12,353,961 | −25,616,092 | −72,615,323 |
| timebox 500 slots | 34 | −67,893,499 | −103,394,280 | −22,585,675 | −37,246,305 | −87,082,119 |
| **BASE first observation** | 104 | **−7,289,855** | −4,760,019 | **−4,524,107** | −4,749,281 | −53,251,939 |

## What the table says

**1. Selection works and is not enough.** Every rule does far better on selected curves than
unselected — first-observation exit is −7.3M selected against −53.3M unselected, a 46-million-lamport
improvement. Selection is doing real work. It does not reach zero.

**2. Waiting is punished, without exception.** The least-bad rule in the entire grid is the one that
does not wait at all. Every rule that holds for a target, a stop or a clock ends up worse, and the
longer it waits the worse it gets (timebox 100 → 500 slots: −37M → −68M). This is the same shape
B19F found and the mechanism now explains it: a held position is exposed to the dump, and the
deposit that would have floored the loss is drained by the earlier buyers exiting through it.

**3. The one near-miss, named as a hypothesis and not a result.** `take_profit +10%` is the only
rule with a **positive median under both conventions** (+10,279,477). It fires on 58 of 107 — more
than half of selected curves do reach +10% at some point. Its mean is destroyed by the 49 that never
fire and are then held to the end. **This is not a result and must not be quoted as one**: a rule
that wins on the majority and loses more on the minority is the classic shape of something that
looks tradeable and is not.

It does isolate the remaining question precisely: *what should be done with the ~46% of selected
curves that never reach the target?* A "take profit at +10%, otherwise abandon at a deadline" rule
is **not in this frozen grid**, and running it now — after seeing this table — would be exactly the
fitting the grid was frozen to prevent. It is a candidate for a future frozen test, on its own
document, and nothing more than that today.

## The honest headline

The tail is identifiable at entry. It is **not harvestable** by any of thirteen simple exits,
including the four take-profits and three tight trailing stops that B19F never tested. The question
this document was written to answer is answered, and the answer is no.
