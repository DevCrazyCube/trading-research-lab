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

## The cashback mechanism — unit settled, concentration retracted

`ClaimCashbackEvent` fires **3,172 times on pump and 264 on PumpSwap** in window 1, alongside a
`UserVolumeAccumulator` that tracks trading volume. It is the only mechanism in this venue that pays
the trading side rather than charging it. Two questions had to be settled: what unit it pays in, and
whether anyone is collecting it at scale.

### The unit — SETTLED. Both programs pay SOL, on two different rails

| program | rail | evidence |
|---|---|---|
| PumpSwap | **wrapped SOL** | `amount` == an inner SPL transfer in **264 of 264**; accounts run `user_volume_accumulator_wsol_token_account → user_wsol_token_account` |
| pump (v1) | **native SOL** | `amount` == an inner **system-program** transfer in **384 of 600**; **0 of 600** match any token transfer |

pump carries two claim instructions — `claim_cashback` (v1), whose accounts are `user`,
`user_volume_accumulator`, `system_program` with no token program, moving native lamports; and
`claim_cashback_v2`, on the WSOL rail. **Both are SOL. Neither is ever a token.** Amounts are
directly summable across both programs.

Sanity check on magnitude: median claim **0.000468 SOL**, max 0.595 SOL — coherent as lamports and
not as a token count.

The `total_claimed_tokens` / `total_unclaimed_tokens` fields on the volume accumulator are **volume
bookkeeping**, never the payout. Reading the payout's unit off them was the original error.

> **Two failed checks of mine, and why each failed — both are instrument errors, not data errors.**
> Reconciling against the claimant's *native balance* matched 4 of 600 on PumpSwap, because WSOL
> lands in a **token** account; the four that matched were unwrap-in-transaction cases. Then testing
> pump for an *SPL transfer* matched 0 of 300, because pump v1 uses the **native** rail. And checking
> whether any account's **net balance delta** equalled `amount` matched 6 of 400 — because a net
> delta absorbs every other lamport movement in the transaction. The peer seat matched inner
> **instruction** amounts, which are exact, and got 384. Same data, three wrong instruments and one
> right one.

### Concentration — retracted; there is none in the window

B19P originally reported *"one entity is 97% of all cashback, 204× the second."* **That was the
wrong field**, and the peer seat was right to challenge it even though their diagnosis (a decode
error) was not the cause.

| measure | pump | PumpSwap |
|---|---|---|
| sum of `amount`, **in-window** | top **12%**, 1× | top **19%**, 1× |
| max `total_cashback_earned`, **lifetime** | top 97%, 204× | top 99%, 1169× |

`total_cashback_earned` is a **lifetime running total** carried in each event, mostly accrued before
the window opened. So "97%" meant: *among accounts that happened to claim during this window, one
account's all-time accrual is 97% of their all-time accruals* — a survivorship statement about
lifetime balances, not a measurement of activity in the window.

**On the right field, there is no concentration.** The largest in-window claimer takes 12% on pump
and is barely ahead of the second. **The 97% and the 204× are retracted.**

> The disagreement that produced this correction was itself a mismatch: the peer scanned **PumpSwap**
> (2,954 instructions, 264 claims) and B19P reports **pump** (703,234 instructions, 3,172 claims).
> Both counts were correct for their own program and were never the same measurement. Chasing that
> apparent contradiction is what surfaced the field error underneath it.

### The largest lifetime accruer, and what its trading looks like

`ARu4n5mFdZogZAravu7CcizaojWnS6oqka37gdLT5SZn` holds the largest *lifetime* cashback balance. It is
**not** the dominant in-window claimer — see the retraction above — but its trading is worth
recording on its own terms, because those figures are in SOL and are not affected by any of the
above. Observed in window 1: 3,027 trades, 1,597 buys and 1,430 sells, 951.77 SOL of volume, 409
distinct mints, median 2 trades per mint, **median trade size 0.0979 SOL** — almost exactly the
position B19K used.

| | |
|---|---|
| round-tripped (≥95% sold) | 186 mints: **+27.46 SOL**, median **−0.014 SOL**, **35% winners** |
| never closed | 123 mints, 79.02 SOL sunk |
| fees paid | 10.24 SOL |
| **net observed trading** | **−51.56 SOL** |
| lifetime cashback accrued | **1,159.99 SOL** (lifetime, mostly pre-window) |

**Its price prediction is no better than anything this programme measured — 35% winners and a
negative median round trip.** What it has is a rebate.

### Why this is not a strategy we can copy

**The rebate does not fund the trading loss on any reading now that the unit is settled.** Its
in-window claims total a fraction of a SOL against a −51.56 SOL observed trading result, and its
1,159.99 SOL lifetime accrual is mostly pre-window and cannot be attributed to activity measured
here. What stands:

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
