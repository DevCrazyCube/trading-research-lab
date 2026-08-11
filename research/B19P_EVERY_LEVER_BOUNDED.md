# B19P — every remaining lever, bounded on data already held

**Status.** Observations on window 1's burned corpus. **No preregistered test, no ledger pass, no
trading claim.** Recorded because each item *closes* a direction rather than opening one, and
because every closure here was computed **without spending a single RPC call**.

**Owner decision, 11 Aug 2026:** do not collect the graduated market; move away from exit rules
entirely. This document is the account of what "away from exit rules" found.

---

## The pattern every failure shares

Three programmes, 26 exit rules, two venues and a 50-agent sweep all failed the same way: a
distribution where roughly 45% win small and 55% lose big. **Every lever below attacks the cost
side of that distribution, and none of them touch its shape.** That is the finding — stated once
here rather than rediscovered each time.

| lever | upper bound on what it buys | still |
|---|---|---|
| perfect liquidity (never-sellable removed) | −18.94% → **−12.78%** | negative |
| infinite size (fixed cost → 0) | −18.94% → **−16.69%** | negative |
| **zero transaction cost** (rent, base, priority, tip all 0) | −18.94% → **−16.89%** | negative |
| optimal position sizing | +0.04 pp on a 3× deeper venue | nothing |
| fee tier selection | not selectable — see B19N §1b | nothing |

Each bound is *generous*: it grants the lever in full and more cheaply than reality allows. **All
remain an order of magnitude on the wrong side of zero.**

## Zero-cost trading, and why it subsumes every rebate scheme

B19K's frozen cell with **all** transaction costs removed — no rent, no base fee, no priority fee,
no tip:

| | real costs | zero cost |
|---|---|---|
| hit rate | 45.42% | 47.03% |
| median win | +9,384,410 | +10,027,641 |
| median abandon | −37,746,043 | −35,348,530 |
| **mean outcome** | **−18.94%** | **−16.89%** |

*(The pinned B19L runner is not modified. Its `build()` loads its own module instance, so the policy
was injected through `_load` — an earlier attempt patched the wrong instance and silently returned
the unchanged number, which is why the check asserts the figure moved.)*

**This closes the entire cost-reduction direction, including cashback**, which is otherwise the most
promising mechanism in the venue: even trading for free leaves −16.89%.

## The cashback mechanism — UNIT NOT ESTABLISHED, figures below are in unknown units

> **Read this before the numbers.** Every cashback figure in this section was first written as SOL,
> on the strength of two indirect signals: `ClaimCashbackEvent` declares `u64` amounts, and the
> `claim_cashback` instruction touches `system_program` with **no token program, no mint and no
> token account** — which is how a native-SOL transfer looks.
>
> **It does not survive a direct check.** Reconciling each claim's `amount` against the user's own
> pre/post lamport balance in the same transaction: **4 of 600 match.** Most show a balance delta of
> exactly **zero**. So the claimed amount does not arrive in the claimant's native balance in that
> transaction, and the SOL denomination is **not established**.
>
> Contradicting it further, `CloseUserVolumeAccumulatorEvent` names its quantities
> `total_claimed_tokens` and `total_unclaimed_tokens` — *tokens*, not lamports.
>
> **Every magnitude below is therefore in an unknown unit and must not be read as SOL.** What
> survives unit-independently is the *distribution*: the ratios, shares and concentration, since
> those divide out whatever the unit is.

`ClaimCashbackEvent` fires 3,172 times on pump and 264 on PumpSwap in window 1, alongside a
`UserVolumeAccumulator` that tracks volume. It is **the only mechanism in this data through which
anyone is demonstrably accruing at scale** — accruing, not necessarily earning, since the unit is
unknown:

- 508 distinct claimers. Median lifetime cashback **5,800,000 units** — the smallest scale present.
- Maximum **1,159,990,000,000 units**. Second largest: 5,674,300,000 — **204× smaller**.
- **One entity is 97% of all cashback in the window.** *(A share, so unit-independent and safe.)*

### What that entity actually does

`ARu4n5mFdZogZAravu7CcizaojWnS6oqka37gdLT5SZn`, observed in window 1: 3,027 trades, 1,597 buys and
1,430 sells, 951.77 SOL of volume, 409 distinct mints, median 2 trades per mint, **median trade size
0.0979 SOL** — almost exactly the position B19K used.

| | |
|---|---|
| round-tripped (≥95% sold) | 186 mints: **+27.46 SOL**, median **−0.014 SOL**, **35% winners** |
| never closed | 123 mints, 79.02 SOL sunk |
| fees paid | 10.24 SOL |
| **net observed trading** | **−51.56 SOL** |
| lifetime cashback earned | **1.16×10¹² units, denomination unknown** |

**Its price prediction is no better than anything this programme measured — 35% winners and a
negative median round trip.** What it has is a rebate.

### Why this is not a strategy we can copy

**The rebate side cannot be priced at all until the unit is known**, so no comparison between its
trading loss and its cashback income is available. What can be said without the unit:

- its observed trading loses **51.56 SOL on 951.77 SOL of volume, about −5.4% of volume**, and that
  figure IS in SOL — it comes from `TradeEvent.sol_amount`, which reconciles against the bonding
  curve's own pricing throughout this project;
- its price selection is **35% winners with a negative median round trip**, which is the same losing
  distribution measured everywhere else in this programme.

**No conclusion about its net profitability is available**, and none is claimed. The corpus only
captures trades touching window-1 cohort curves, so even the trading figure is a partial view.

The 79.02 SOL in unclosed positions is counted as sunk, which is the pessimistic convention this
project uses elsewhere; those positions have some residual value, so −51.56 SOL is a floor and not
an estimate.

## Liquidity provision: closed on volume, not on theory

Being paid the fees instead of paying them is the one genuinely different position, and it fails on
arithmetic rather than on principle:

| | median across 33 graduated pools |
|---|---|
| volume traded through the pool | **0.334 SOL** |
| LP fees earned | **0.00015 SOL** |
| against a deposit of | 84.99 SOL |
| **fees as bps of deposit** | **0 bps** |

**No `deposit` or `withdraw` instruction appears anywhere in window 1.** Nobody outside the protocol
provides liquidity to these pools, and the volume figures show why: there is nothing to earn.

## What this leaves

Every mechanism measurable on this corpus is now bounded, and every bound is negative. The single
consistent explanation is the one this programme reached three times independently and then kept
trying to route around: **the outcome distribution is a property of the asset, and no venue,
size, cost or rebate change reaches it.**

The largest participant visible in this data loses money on price — 35% winners, negative median
round trip, −5.4% of volume — while accruing a protocol rebate whose denomination this corpus cannot
establish. **That is the strongest available evidence that price is not the edge**, and it comes
from a participant with far more capital, speed and coverage than this project has. Whether the
rebate makes it whole is unknown and deliberately left unknown rather than guessed.
