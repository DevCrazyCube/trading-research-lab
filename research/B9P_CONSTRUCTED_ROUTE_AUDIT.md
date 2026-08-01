# B9p — causal audit of every direct-route residual against the transaction we would construct

Measured 2026-08-01 over the **full frozen population, all 94,985 transactions**. No sampling.
Artifact read-only, **zero network calls**, collector not restarted, **no simulator implementation
started**.

Reproduce with:

```
python scripts/b9p_constructed_route.py research/b9d_transaction_bodies.sqlite
```

## Result

```
audited 92    A_outside_constructed_route 92    B_inside_trade_subtree 0    C_insufficient 0
```

**Every one of the 92 residuals is caused by an instruction our constructed transaction would not
contain, and each reconciles to the exact lamport.** Zero lie inside the Pump trade subtree, so
**no Phase 1 cost-divergence blocker remains on the route we would execute.**

## Why B9n's predicate was too loose

B9n called a transaction "direct route" when every program in it was pinned. That admits two things
it should not, and both mattered:

1. **Transactions containing no Pump trade at all.** A creator harvesting fees touches only pinned
   programs. One such transaction was in the 92, and its 11.115 SOL residual was 18× the combined
   total of the other 91 — it dominated a *trade*-cost diagnostic while not being a trade.
2. **Companion instructions bundled alongside the trade.** The observed trader closes accumulators,
   claims cashback, tips, and transfers tokens in the same transaction. We would submit none of it.

`is_constructed_route` now requires **exactly one** Pump trade at outer level. Shape is decided by
the trade, not by the program set.

## The transaction we would construct

| role | instructions |
| --- | --- |
| **constructed** | compute-budget; optional ATA creation; **exactly one** Pump trade + its CPI subtree; optionally closing our own token account on exit |
| **companion** | everything else — and the default for anything unrecognised |

Defaulting the unknown to *companion* is deliberate. The opposite default silently adopts a
stranger's lamport movement as our cost, which is the exact error this audit exists to find.

## The cause: `close_user_volume_accumulator`

It appears in **91 of the 92** transactions. From the pinned Pump IDL its accounts are
`[0] user` (writable, signer — receives) and `[1] user_volume_accumulator` (writable — closed). It
sends the accumulator's **entire balance** to the user, and nothing in a trade records it.

**The credit is the balance at close, not the pre-transaction balance.** 32 of the 92 have an
accumulator with a pre-balance of **zero** — created and closed inside the same transaction — and
still refund full rent. Reading the pre-balance reports zero credit for every one of them. This is
the same trap that made SPL `CloseAccount` rent wrong when it was first read from pre-balances.

Balance at close is reconstructed entirely from pinned semantics, and order-independently:

```
credit = accumulator pre-balance
       + System lamports credited to it   (amount from the decoded System instruction)
       + trade cashback paid into it      (amount from the pinned TradeEvent field)
```

**One double-count had to be resolved from evidence, not smoothed with a tolerance.** On 3 of the 92
the cashback reaches the accumulator by an explicit System transfer, so it appears both as a decoded
System credit and as the `TradeEvent.cashback` field. It arrives by exactly one mechanism per
transaction, so counting it twice overstates the credit. Adding both leaves those 3 unreconciled;
the guard resolves it and all 92 land exactly.

The second and only other credit source is a creator harvesting accrued PumpSwap fees:
`CollectCoinCreatorFeeEvent.coin_creator_fee`, which states its amount. It accounts for the
11.115 SOL row to the lamport. We are not the creator of tokens we trade and PumpSwap is not an
entry venue, so it is doubly outside our route.

## Progression of the reconciliation, including what failed

Recorded because three of these were wrong and the wrongness was informative:

| attempt | result |
| --- | --- |
| accumulator **pre-balance** alone | 4 of 91 — fails on every accumulator created in-transaction |
| account-**set** separation (companion-only accounts) | fails — the accumulator is touched by the trade *and* the companions, so it is never companion-only |
| pre-balance + cashback + extension rent | 3 of 91 |
| pre-balance + **trade cashback** | 59 of 91 — remainder all `pre = 0`, all short by exactly 1,844,400 |
| **balance at close** from pinned semantics | 88 of 91 — remainder double-counted cashback |
| + double-count guard | **91 of 91** |
| + `CollectCoinCreatorFeeEvent` | **92 of 92** |

An observation, not a dependency: the closed accumulators hold **1,844,400** lamports, the
rent-exempt minimum for a **137-byte** account under `890880 + 6960·size`, while the pinned IDL's
`UserVolumeAccumulator` serialises to **106 bytes**. `extend_account` exists in the IDL and appears
in this artifact, which would explain deployed accounts having grown. The reconciliation never uses
the constant — it reads balances — so this is recorded as an open observation, not a conclusion.

## Verification

Seven mutants, all killed, covering both classes the brief named:

| mutant | outcome |
| --- | --- |
| unrecognised instruction adopted as ours | killed |
| every Pump instruction treated as a trade (adopts close/claim) | killed |
| route shape accepts any number of trades | killed |
| **case A granted whenever any companion credit exists** — hides an in-subtree divergence | killed |
| credit read from pre-balance only | killed |
| double-count guard removed | killed |
| outer token transfer adopted as ours | killed |

A near-miss is explicitly **not** case A: one lamport out is unexplained, and is reported as a
blocker. `assert`-style exhaustiveness fails the run if the cases do not account for every residual.

## What this does and does not establish

- **Does:** on the transaction we would construct, every lamport of every observed residual is
  attributable to instructions we would not submit. There is no unexplained cost divergence on our
  route.
- **Does not:** say anything about routed transactions, where 4,870 unattributed and 1,654
  undecodable remain. Those are not our route and are not claimed to be explained.
- **Does not** filter the evaluation population. Eligibility remains a point-in-time predicate on
  the token; this module only decides which lamport movements are ours.
- **Does not** close the unmeasured execution terms — landing, contention, tips, slippage. Those
  need forward observation and remain the binding constraint on calling any return *executable*.

No profitability claim is made and nothing here is a trading recommendation.
