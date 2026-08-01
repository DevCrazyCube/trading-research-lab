# B9m — causal partition of the unattributed transactions

Measured 2026-08-01 over the **full frozen population, all 94,985 transactions**. No sampling.
Artifact read-only, zero network calls, collector not restarted, no simulator started.

Reproduce with:

```
python scripts/b9m_unattributed_partition.py research/b9d_transaction_bodies.sqlite
```

## What this answers

B9k reconciles 88,369 transactions (93.03%) exactly. 4,962 (5.22%) are `unattributed_movement` —
their lamport arithmetic does not close. The previous handoff described their residuals as "small
and varied … no dominant class", which is true and is not a cause. This partitions them by **why
attribution is impossible**, decided from decoded instruction, event and account-lamport evidence.

Categories are ordered and first-match-wins, which is what makes them mutually exclusive rather
than merely disjoint. A non-native quote cannot be summed into lamports whatever else is true, so it
dominates; a transaction with no trade is not a trade; and so on. `assert_exhaustive` fails the run
if the categories do not account for every transaction, so a dropped row cannot pass silently.

## The partition

| category | count | share | cause |
| --- | ---: | ---: | --- |
| `third_party_program` | **3,694** | 74.4% | ≥1 program outside the pinned set participates |
| `nonnative_quote` | 681 | 13.7% | quote is not native SOL; raw token units are not lamports |
| `no_trade_event` | 477 | 9.6% | no TradeEvent — a pool/liquidity operation, not a trade |
| `multi_trade` | 110 | 2.2% | >1 TradeEvent; one payer delta cannot be split without an invented rule |
| `pinned_only` | **0** | 0.0% | — |

Three of these are **already-explained exclusions rather than failures**. `nonnative_quote` is the
standing constraint that raw token units are never summed into lamports. `no_trade_event` are
liquidity operations this project does not model. `multi_trade` cannot be split without an
allocation rule, and inventing one would fabricate per-trade costs. Together they are 1,268
transactions, 25.6% of the gap, and none of them is a defect.

## The finding that matters: `pinned_only` is empty

**Every one of the 4,962 unattributed transactions contains at least one program whose ABI this
project has not pinned.** Not most — all of them. The gap is therefore not a bug in the
reconciliation arithmetic; it is a boundary of the pinned evidence.

The mechanism is the one already established for sell proceeds: **a program may move lamports on
accounts it owns, and no System instruction records it.** Pinning the curve's own semantics is what
closed 43,044 → 4,955 previously. The same move would be required for each remaining program.

**It is not one missing ABI.** 62 distinct unpinned programs appear across the category:

| program | occurrences |
| --- | ---: |
| `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` | 3,694 |
| `DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH` | 1,467 |
| `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` (Jupiter) | 681 |
| `proVF4pMXVaYqmy4NjniPh4pqKNfMmsihgd4wdkCX3u` | 582 |
| `BBRouter1cVunVXvkcqeKkZQcBK7ruan37PPm3xzWaXD` | 250 |
| `CxvksNjwhdHDLr3qbCXNKVdeYACW8cs93vFqLqtgyFE5` | 250 |
| `BiSoNHVpsVZW2F7rx2eQ59yQwKxzU5NvBcmKshCSUypi` | 213 |
| `AveaiuA1emN71q9mS2QQ9BEWNAAHmp8sHSvwLFHQjufM` | 197 |
| `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` (Raydium) | 162 |
| … 53 more | |

## Hypotheses tested and REFUTED

Recorded because each is the inference the evidence invites, and each is wrong. Sampled agreement
has already misled this project more than once; these were checked against the population.

**1. `pfee` presence is causal — refuted.** It appears in 100% of unattributed transactions, which
looks decisive. The control kills it: it also appears in **98.3% of the exactly-reconciled ones**
(86,867/88,369). Its presence carries essentially no information. This is why `pfee` is named in the
module and deliberately excluded from `PINNED_PROGRAMS`, so nobody re-derives the dead end.

**2. The residuals are rent refunds — refuted.** Four residual classes are *exactly* rent-exempt
minima under `890880 + 6960*size`. Counts below are all measured within the same 3,579-transaction
class (single native-quote trade, no PumpSwap), so they share one denominator: `-1,113,600`
(32 bytes) 164×, `-1,057,920` (24 bytes) 86×, `-2,039,280` (165 bytes = a token account) 32×,
`-1,844,400` (137 bytes) 26×. The arithmetic is
exact and the hypothesis still fails: across 25 sampled transactions in those classes, **none** had
an account closing from exactly that balance. In the narrower pfee-only subpopulation only **4 of
26** did (a 137-byte Pump-owned PDA). The coincidence is not the cause.

**3. A 0.5% router skim — refuted.** Residuals `99,500,000`, `298,500,000`, `497,500,000`,
`995,000,000` are exactly round SOL × 0.995, which reads as a 0.5% fee. Across 25 such
transactions, **no single account gained the residual amount**.

**4. A direction-dependent attribution bug — refuted.** In the dominant class the split is 1,845
buys to 1,734 sells. Near-even, so the gap is not one side of the buy/sell logic.

**5. One dominant residual class remains — refuted.** 2,982 distinct residual values across 3,579
transactions. It is a genuine long tail.

## The tractable residue: 79 transactions

`pinned_only` is empty under the strict definition, but 79 transactions have `pfee` as their **only**
unpinned program — and `pfee` is the one program shown above to be non-discriminating. These are
therefore the closest thing to a case whose cause should lie inside already-pinned semantics, and
they are the right next target. Reported as a sub-count, never as a category, so promoting `pfee` to
pinned status cannot happen by accident.

- 62 sells, 17 buys. (An earlier count of 91 for this class included 12 double-trade transactions,
  which the partition assigns to `multi_trade` first; 62 + 17 = 79.)
- Dominant residual `-1,844,400` (137-byte rent) × 26, but 63 distinct values overall — so even
  here there is no single cause.
- Of the 26, four close a 137-byte Pump-owned PDA at exactly that balance. Twenty-two do not.

## What is NOT claimed

- No lamports are attributed by this module. It explains why they are unattributed.
- No tolerance was introduced, no ceiling chosen, no transaction excluded or reclassified. The
  `exact` count is unchanged at 88,369 / 93.03%.
- That a third-party program is present is **not proof** it caused the discrepancy. Setting `pfee`
  aside as non-discriminating (its 98.3% base rate above), some *other* unpinned program appears in
  **4,871/4,962 = 98.2%** of unattributed transactions but also in **56,138/88,369 = 63.5%** of
  exactly-reconciled ones. The discriminating evidence is that gap together with `pinned_only`
  being empty — not presence alone. Note the two framings differ only in whether `pfee` is set
  aside: under the strict definition the module ships with, `pfee` is unpinned and the
  `third_party_program` share is 100% by construction, which is why the comparison above holds
  `pfee` constant to stay informative.
- No profitability claim is made and nothing here is a trading recommendation.

## Open

- Whether pinning `DF1ow…`, `proVF…` or the Jupiter ABI would close a material share. Untested;
  each needs an authoritative versioned source, and none is vendored.
- The 22 pfee-only transactions with a 137-byte-rent residual and no matching account closure.
- Whether the `multi_trade` allocation problem is worth an explicit rule, which is an owner
  decision because any rule fabricates per-trade costs that the chain does not record.
