# Behavioural exit — rules frozen before any outcome under them was computed

**Status.** EXPLORATORY, BURNED development corpus only. Frozen and committed **before** any P&L
under these rules was calculated, and before this author has seen the headroom table measured by
the peer seat. Nothing here may be reported as an evaluation result.

## The hypothesis, and why it is not another point in a searched grid

Every exit rule tested in this project reads the **price path**: B19F's eight (fixed horizons,
first observation, first externally payable, completion, three drawdowns) and B19H's thirteen
(take-profits, tight trailing stops, combinations, time-boxes). Twenty-one rules, one information
channel.

This grid reads a **different channel**: *who* traded, in *which direction*. Trader identity and
trade direction have never been used by any exit rule here. That is the ground on which this is a
new hypothesis rather than another point in a searched space.

It also follows from the mechanism rather than from any outcome table: the selection test
established that selected curves **pump and dump**, so "watch for the dump" is the direct
consequence and needs no result to motivate it.

**Provenance of the hypothesis, scoped precisely.** It was proposed by the project owner, who has
seen the campaign headlines (selection is real, the mechanism, no exit monetises it) but **not the
exit P&L tables** — which is the contamination that matters for exit design. It is not a claim of
blanket independence.

## Population, entry and selection — all inherited, none re-derived

- **Corpus:** burned (`b10b_observed_paths.sqlite`, `b9d_transaction_bodies.sqlite`).
- **Selection:** launch-transaction deposit ≥ 3 SOL, the rule from the selection test, unchanged.
- **Entry:** first observation in a slot strictly after t0. Same-slot entry is unprovable and is
  excluded, as everywhere in this project.
- **Identity:** `b16a`'s `{creator, create_user}`, the same set b16d's signals use, inherited by
  call and not re-derived.
- **Position:** 100,000,000 lamports, B19D base cost scenario, b10a kernel, exact integers.

## The triggers

Every exit prices at **state-in-force(trigger_slot + 1)** — the first observation at or before one
slot after the trigger. This is deliberate and load-bearing: it prices the exit **after** the
dump's own price impact has landed, so no optimism leaks in from reacting inside the trigger's own
slot, which would be the same unprovable same-slot capture refused everywhere else.

**A. First creator sell.** Exit on the first sell by `{creator, create_user}` strictly after entry.
**B. Any creator sell.** Identical, but re-armed — named separately because it is a different rule
and blurring them would hide which one worked.
**C. Depth-relative sell, three thresholds.** Exit on the first sell, by *anyone*, whose
`quote_amount` is ≥ **10%, 25%, 50%** of the curve's `real_quote` immediately before it. Rationale:
the creator is only 3.4% of sells, so a rug may be run by any large holder; size relative to the
curve's own depth is what makes a sell a rug rather than a trade. The three thresholds are
**conventional round numbers declared here**, not the output of any sweep.

**Declared comparison count: 5 rules**, each run on the selected subset and, as a control, on the
unselected subset. No rule may be added, dropped or retuned after results are seen.

## Why there is no deadline or time-box in this grid

A deadline would import a **second, time-based hypothesis** into a test of a behavioural one, and
its parameters would multiply the comparison count for a mechanism this grid is not testing. The
~10% of curves where no trigger ever fires get a **declared terminal disposition** instead
(below), which is the honest treatment and keeps the hypothesis single. Recorded because the peer
seat deliberately withheld advice here — their headroom run measured the ceiling's latency
structure, so any timing parameter they suggested would have been contaminated. This choice is
mine, from mechanism, before seeing their table.

## Non-firing curves

A curve whose trigger never fires is **held to the end** and valued **both** ways, both reported:
**(a)** pessimistic, total loss of outlay; **(b)** sell-back into one's own deposit at the final
observed state, deposit-adjusted. Truth is between. Neither is quoted alone.

## The benchmark, frozen as a number

The incumbent is **exit at the first observation after entry, on the selected subset**, already
measured at **−7,289,855 mean / −4,760,019 median** (pessimistic) and **−4,524,107 / −4,749,281**
(sell-back). "Beats the incumbent" means beating those figures, which are fixed here and cannot
move.

## The success bar

On the selected subset, with **n ≥ 50** fired: mean **> 0** AND median **> 0**, under **both**
stuck conventions, AND beating the frozen benchmark above. A rule positive only in the mean is not
a result — this project has already been fooled once by a mean carried entirely by a thin tail.

## What each outcome would mean

- **Cleared:** the rug is detectable and actionable one slot late, and a fresh-window
  preregistration becomes the next step — plus the owner conversation about execution, which
  stands before any such document and not after.
- **Not cleared:** the dump cannot be outrun by anyone reacting to it on-chain, which closes the
  exit question across both information channels and is worth as much as a positive.

---

# RESULT — the rug cannot be outrun

Grid exactly as frozen at `6831f01`. Burned test split, 107 selected curves. Nothing added,
dropped or retuned.

**No rule clears the bar. Every rule is worse than the benchmark**, which is exiting immediately
and not reacting to anything.

| rule | fired | sel. mean (pess) | sel. median (pess) | sel. mean (sellback) | unsel. mean |
|---|---|---|---|---|---|
| **BENCHMARK — exit at first observation** | 104 | **−7,289,855** | **−4,760,019** | **−4,524,107** | −53,251,939 |
| A first creator sell | 97 | −13,714,829 | −13,607,519 | −6,055,433 | −73,783,895 |
| B any creator sell | 97 | −13,714,829 | −13,607,519 | −6,055,433 | −73,783,895 |
| C depth sell ≥10% | 101 | −10,036,620 | −11,209,821 | −5,334,219 | −62,689,173 |
| C depth sell ≥25% | 96 | −28,654,516 | −24,381,032 | −21,678,327 | −67,342,549 |
| C depth sell ≥50% | 71 | −58,467,179 | −44,699,401 | −36,846,142 | −81,099,277 |

## What it establishes

**Reacting to the dump is worse than never waiting for it.** Every behavioural trigger loses more
than simply exiting at the first opportunity — first creator sell nearly doubles the loss
(−13.7M against −7.3M), and the larger the sell you wait for, the worse it gets (−10.0M → −28.7M →
−58.5M as the depth threshold rises from 10% to 50%).

The mechanism is not subtle and the design anticipated it without knowing the outcome: the exit
prices at `state-in-force(trigger + 1)`, **after** the dump's own price impact. By the time a rug is
observable on-chain it is already in the price. There is no reaction fast enough, because the
information and the damage arrive in the same event. Waiting for a *bigger* confirming signal
simply means waiting through more of the fall.

**A and B are identical**, as the numbers show. For a single-exit strategy the first creator sell
*is* the trigger under both rules; "any" only differs for a strategy that re-enters. Recorded as a
design observation: the grid should have named that degeneracy in advance, and did not.

## The question this closes

Twenty-one price-path rules (B19F's eight, B19H's thirteen) and five behavioural rules, across two
independent information channels — the chart, and who is trading. **Nothing beats exiting
immediately, and exiting immediately loses the toll.**

The best exit rule found anywhere in this project is *do not hold the position*. That is not a
strategy; it is the absence of one.
