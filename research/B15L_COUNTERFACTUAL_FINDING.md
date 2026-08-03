# B15l — the self-impact term, measured

Computed 2026-08-03 under `research/B15L_COUNTERFACTUAL_ROUNDTRIP_PREREGISTRATION.json`, committed
alone before any quantity here existed.

**Nothing below is a return.** Every row carries `COUNTERFACTUAL_UNREACTING_BOOK` and the assumption
`UNREACTING_ORDER_FLOW`, and that assumption is false by construction. `executable=false`,
`landing_probability=unmeasured`, `competitor_response=unmeasured`.

## What was computed

For each admissible cell — a (launch, entry delay, exit horizon) with both an entry and an exit
bonding-curve account read — the hypothetical 0.1 SOL buy is priced against the entry checkpoint
with B10a, our own reserve delta is applied, the observed external delta is carried additively to
the exit, and the sale of exactly the acquired tokens is priced against that transported state.

The transport rests on one rule, and the rule was validated before it was used: a trade moves the
virtual and the real reserve by the same delta on each side. Reproduced over **93,253 consecutive
canonical observations with zero mismatches.**

## Coverage and censoring

| | |
|---|---|
| entry checkpoints available | 34,392 |
| exit checkpoints available | 18,846 |
| fee schedules decoded from launch transactions | 3,074 |
| **priced cells** (18 scenario×horizon×delay groups) | **14,688** |

Refusals, every one counted by its own code:

| code | count |
|---|---|
| L_NO_ENTRY_CHECKPOINT | 29,115 |
| L_MAYHEM | 7,617 |
| L_NO_FEE_SCHEDULE | 4,803 |
| L_COMPLETE_AT_ENTRY | 150 |
| L_COMPLETE_BY_EXIT | 129 |
| L_NON_NATIVE_QUOTE | 36 |

*Conditioned on cells where BOTH an entry and an exit account checkpoint exist; B15f schedules from
B15a, which B15k measured holding 29% of the launches B15i observes, so this population is censored
by the recorders and not by the market.*

## The result this study exists for

**The observed book cannot absorb the exit at all, on the large majority of cells.**

Of 14,688 priced cells, the naive no-self-impact figure exists for only **2,748** — 19%. For the
other 81% the observed curve holds on the order of a single lamport of real quote, so selling the
tokens our buy would have acquired draws more than the curve could pay. Without our own order's
contribution to the reserves there is no exit price to compute.

That is the term B10b declined to model, and it is not a correction. Where both figures exist, the
median self-impact is **401,384 lamports at h_10000_slots and 492,141 at h_1000_slots** on a
100,000,000-lamport position — but the more important number is the 81% where the comparison cannot
be formed.

## Counterfactual net, per group, never aggregated

Two representative groups; all eighteen are in `research/b15l/report.json`. No mean is published,
because a mean over a censored set invites reading it as an expectation and this study publishes no
expectation.

| group | cells | median net (lamports) | cells at or below zero |
|---|---|---|---|
| base, h_1000_slots, delay 1 | 746 | −6,415,619 | 714 (95.7%) |
| base, h_10000_slots, delay 1 | 886 | −9,443,451 | 872 (98.4%) |

The median is negative in **all eighteen** groups, and between 95% and 99% of cells in every group
sit at or below zero. A substantial share have an external delta of exactly zero — no other trade
touched the curve between entry and exit — and for those the round trip is pure cost: two sets of
curve fees, two executions, and the ATA rent that is charged on entry and never refunded.

Figures are not aggregated across horizons or across cost scenarios. The three scenarios are
alternative assumptions, not samples of a distribution, so no average over them exists.

## What this does not establish

- **Not a return.** It is a counterfactual on a book that does not react, and the real book reacts.
- **The assumption is false, not small.** The external deltas carried in were produced by traders
  facing the reserves our order would have moved. Some of their orders would have executed
  differently; some would not have landed at all. The error is not bounded here and its sign is not
  stated, for the reason B10b gave: subsequent order sizes are not invariant to the reserves they
  faced.
- **No landing probability.** Nothing here says our order would have landed at the delay it assumes.
- **No competitor response.** The one effect most likely to dominate at this size is unmodelled.
- **Population censored by our own recorders**, not by the market.

Two defects were found and fixed while producing this, both mine: the native quote mint was
transcribed by hand as the wrapped-SOL mint rather than taken from B9D, which refused 22,620
perfectly native checkpoints on the first run and looked like a data problem; and the
forbidden-word scan used a lookbehind that excluded `net_return`, the exact field name it existed
to catch.
