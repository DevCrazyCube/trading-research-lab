# B15Q — the 0.1 SOL direct-RPC launch snipe, priced on a population with no closed recorder

**Artifact:** `research/b15q/replication.json`, sha256
`45644bc852d8ab15640bb852ee862e311167f58ea0b589ffb2d35410742c0f6b`, written once.
**Freeze:** `research/B15Q_CLEAN_REPLICATION_PREREGISTRATION.json`, committed alone at `b116f0f`
before any figure below was computed.
**Label:** `CLEAN_CLOSED_REPLICATION`. `executable=false`, `performance_status=not_evaluated`,
`execution_status=never_executed`.

B15L and B15M, unchanged, re-run on B15O's frozen 5,000 consecutive launches, with each launch's fee
basis points decoded from its **own launch transaction**. B15O produced zero priced cells because its
fee schedules descended from a closed recorder; that artifact stands and is not edited. This is a new
one beside it.

## What was measured

A hypothetical 100,000,000-lamport (0.1 SOL) buy at 1, 2 or 4 slots after the launch, and a sale of
exactly the tokens acquired at a checkpoint 1,000 or 10,000 slots later, priced against B9I's and
B10a's pinned arithmetic under three frozen cost scenarios. Exact integers throughout; no mean is
published, because a mean over a censored set invites reading it as an expectation.

## Coverage

| | |
|---|---|
| members in the frozen population | 5,000 |
| entry checkpoints (B15i) | 14,485 |
| exit checkpoints (B15N) | 27,586 |
| exit checkpoints withheld pending chain confirmation | 0 |
| fee schedules decoded from launch transactions (B15P) | 4,096 |
| members whose launch transaction published no fee basis points | **904 (18.08%)** |
| priced cells across 18 scenario×horizon×delay groups | 53,919 |

Refusals, every cell accounted for: `L_NO_FEE_SCHEDULE` 13,650, `L_MAYHEM` 11,277,
`L_NO_ENTRY_CHECKPOINT` 2,979, `L_COMPLETE_BY_EXIT` 417, `L_COMPLETE_AT_ENTRY` 381,
`L_NON_NATIVE_QUOTE` 135. Priced + refused = 82,758 = 27,586 exits × 3 scenarios, exactly.

Four distinct fee schedules occur among the 4,096 (`fee_bps` 95 throughout; creator/cashback/buyback
differ). No constant would have fitted any of them, which is why a decoded schedule is required and a
member without one is refused rather than priced at an assumed rate.

## Result 1 — the round trip is negative at the median in all eighteen groups

Base scenario:

| group | cells | median net (lamports) | at or below zero |
|---|---|---|---|
| h_1000_slots, delay 1 | 2,762 | −10,933,986 | 2,670 (96.67%) |
| h_1000_slots, delay 2 | 2,726 | −10,933,986 | 2,634 (96.63%) |
| h_1000_slots, delay 4 | 2,702 | −10,933,986 | 2,607 (96.48%) |
| h_10000_slots, delay 1 | 3,273 | −11,192,651 | 3,225 (98.53%) |
| h_10000_slots, delay 2 | 3,258 | −11,184,778 | 3,210 (98.53%) |
| h_10000_slots, delay 4 | 3,252 | −11,007,580 | 3,202 (98.46%) |

Across all three scenarios the median runs from −10,735,986 (optimistic) to −15,002,651 (stressed) on
a 100,000,000-lamport position, and the nonpositive share from 96.48% to 98.81%. Scenarios are
alternative assumptions, not samples, so nothing is averaged over them.

## Result 2 — the observed book cannot absorb the position at all, on most cells

External liquidity capacity is the largest buy whose exit the **observed** book could pay for,
excluding whatever reserves our own purchase would have added.

| group | cells | min | p25 | median | p75 | p90 | reached the 0.1 SOL ceiling |
|---|---|---|---|---|---|---|---|
| h_1000_slots, delay 1 | 2,762 | 3 | 4 | **15** | 9,883,039 | 100,000,000 | 482 (17.5%) |
| h_1000_slots, delay 2 | 2,726 | 3 | 4 | **15** | 9,883,049 | 100,000,000 | 485 (17.8%) |
| h_1000_slots, delay 4 | 2,702 | 3 | 4 | **15** | 9,883,049 | 100,000,000 | 483 (17.9%) |
| h_10000_slots, delay 1 | 3,273 | 3 | 4 | **13** | 9,878 | 96,407,428 | 325 (9.9%) |
| h_10000_slots, delay 2 | 3,258 | 3 | 4 | **13** | 9,878 | 100,000,000 | 327 (10.0%) |
| h_10000_slots, delay 4 | 3,252 | 3 | 4 | **12** | 9,878 | 96,407,428 | 323 (9.9%) |

The median cell's book absorbs an exit of **twelve to fifteen lamports**. The tested position is
roughly seven million times larger. On the frozen size grid the median net is negative at *every*
size and worsens monotonically with it — at 1,000,000 lamports only 18.9% of cells are even
liquidity-executable, with 4 of 3,273 non-negative; at 100,000,000 lamports, 9.9% executable and 47
non-negative.

Consistency check across the two studies: the count of cells whose naive observed-book exit can be
priced equals the cap-hit count in all six groups (482/485/483 and 325/327/323). Two quantities
computed by different routes that must coincide by construction, and do.

## The figures are already generous to the strategy

The counterfactual credits our own buy's contribution to the exit reserves. The naive comparison — a
sale into the observed book with no self-impact — can be formed on only **7,275 of 53,919 cells
(13.5%)**; on the other 86.5% the observed curve cannot pay for the sale at all. Where both exist,
the median self-impact is 420,584–429,712 lamports at h_10000_slots and 514,207–523,681 at
h_1000_slots.

## What this licenses

**Reject the current tested configuration** — a 0.1 SOL direct-RPC launch snipe entered 1/2/4 slots
after launch and exited at 1,000 or 10,000 slots — **on cost and liquidity grounds.** No estimate of
landing probability is needed to reach that conclusion: landing probability scales exposure to an
opportunity that is negative at the median and, on ~90% of cells, not executable at this size at all.
A higher landing rate makes this configuration worse, not better.

## What this does not license

- **No generalization** to a different position size, venue, entry delay, exit horizon, or strategy.
  Other sizes were measured only on the frozen grid against the observed book, and no size was
  selected or recommended.
- **Nothing about a reactive book.** The assumption is `UNREACTING_ORDER_FLOW`: the observed external
  delta is transported in unchanged. A real book reacts. The self-impact diagnostic above is a *lower
  bound* on that error, not a correction for it, and it can be formed on only 13.5% of cells.
- **Landing probability: unmeasured.** Every cell assumes the entry executed at the checkpointed
  reserves in the intended slot.
- **Competitor response: unmeasured.**
- **No return, expected value, profit or probability of any outcome is claimed**, and no figure here
  is a performance result. Nothing was signed, simulated, submitted or spent.
- **Conditioned population.** 904 of 5,000 members published no fee basis points at t0 and are absent
  — coverage, not failure, and never filled from a later trade, which would price an entry with a
  number knowable only afterwards. `L_MAYHEM` removed 11,277 cell-instances.
- **The two horizons are not the same population.** h_10000_slots is complete at 5,000 cells per
  delay; h_1000_slots carries 4,163–4,229, the gap being `N_TARGET_ALREADY_PASSED` (1,459 refused,
  137 never scheduled) concentrated in the earliest launches — 71% in the first 1,000 by t0 — because
  the shorter target had already passed when B15N began and scheduling is prospective-only, never
  backfilled. The difference between the two horizons' medians must not be read as a horizon effect.

## Provenance

Every input descends from B15i's own observations, B15N's exit checkpoints and B15P's
launch-transaction decodes. A runtime path guard over a complete materialization records **zero**
opens under `research/b15a`, `research/b15b` or `research/b15f`. `B15L.fee_schedules` — the closed
recorder read that caused B15O's empty result — is never called.

Independently audited (handoff 154): every published figure recomputed from the stored evidence with
separate loaders, refusal cascade, bisection and order statistics — **0 mismatching fields** across
all 18 B15L groups and all 18 B15M grid groups, refusal censuses identical, denominators balancing
exactly, roster element-identical to the bound `member_set_sha256`
`661f953a3aa995abe9a013e69da080f71bad212666a40610d859764b2855a296`, and the artifact replaying
byte-identically. The artifact carries no credential and no provider hostname.
