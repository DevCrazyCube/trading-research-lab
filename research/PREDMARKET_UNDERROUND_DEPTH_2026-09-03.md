# PREDMARKET — full-family underround screen + depth kill (2026-09-03, CHUNK D)

**Status: SCREEN RUN, ONE CANDIDATE FOUND, KILLED ON MEASURED DEPTH + CARRY.**
No estimate frozen; logged as an abstention in
`research/trading_bot/predmarket/PREDMARKET_PREREGISTRATION_LOG.jsonl`.

## 1. Method upgrade over the 2026-09-02 audit

The 09-02 coherence audit keyed families by `category` and compared **mid** prices. Two
defects, both fixed here:

* `category` is a tag soup, not an event key. Keying on **`url_ref` (the event slug)**
  recovers the true exclusive-and-exhaustive family, including the cheap legs the
  09-02 candidate filter (`volume >= 20k`, `0.03 <= p <= 0.97`) had silently dropped.
  **Dropping a cheap leg manufactures a phantom underround** — that filter is exactly
  what makes a complete family look sub-1.0.
* Mid-price sums are not tradeable. The only sum that means anything is
  **sum of best ASKS**: buying every leg of an exclusive+exhaustive family at ask for a
  guaranteed $1 payout is an arbitrage iff `sum(ask) < 1`, and Polymarket charges 0%
  trading fee, so no fee term hides in it.

Screen: 4,627 selectable markets -> families keyed by `url_ref`, `n >= 3`, every leg
two-sided, all closes <= 2026-12-31, family volume >= $50k. **15 families qualified.**

## 2. Result: exactly one sub-1.0 family, and it is not a date ladder

| family | sum(ask) | verdict |
|---|---|---|
| Iran-Oman Hormuz agreement by <date> | 0.706 | **NOT a violation** — nested cumulative ladder, legs are subsets, the sum is meaningless. Monotonicity checks out (0.04/0.07/0.12/0.18/0.30, increasing). Trap (b) from the 09-02 catalogue, restated. |
| **Balance of Power: 2026 Midterms** | **0.993** | exclusive + exhaustive (4 chamber combos + `Other`), $10.97M volume, closes 2026-11-03. RC confirms exhaustiveness. **The one genuine candidate.** |
| 13 others | 1.010 – 2.068 | overround (normal vig) or k-winner families (Brazil runoff = 2.0 target). No edge. |

## 3. The kill: depth-walk, not top-of-book

Top-of-book says +0.7c per $1 set. The live CLOB books (`clob.polymarket.com/book`,
per-leg, free) say the underround is **a top-of-book artifact**:

| sets ($1 notional each) | avg cost per $1 set |
|---|---|
| 1,000 | 0.9930 |
| 5,000 | 0.9978 |
| **10,000** | **1.0020  <- underwater** |
| 25,000 | 1.0144 |
| 50,000 | 1.0608 |

The binding leg is `R Senate, D House`: only **2,644 units** at 0.36, then the book jumps
to 0.37. Maximum profitable size is **~$5,000 notional, for +0.22c/set = ~$11 gross**.

Then the capital cost finishes it. The set locks **$4,989 for 61 days** to 2026-11-03.
At the T-bill rate this programme already measured in T32 (**3.71%**), that is
**~$31 of carry** — nearly **3x the entire gross edge** — before gas/relayer, before any
adverse-selection on resting size, before resolution lag past 11-03.

**Verdict: DEAD at the friction floor. Net ~ -$20 on the maximum executable size.**
This is the programme's standard result and it is now *measured*, not asserted: the
distance from zero is what kills it, not the sample.

## 4. Generalisable lesson (trap catalogue entry f)

**A prediction-market underround is a depth question, not a price question.** Every free
price feed (gamma `bestAsk`, our own pull digest) reports top-of-book only. On Polymarket
the vig lives in the *slope* of the book, not the touch: the touch is priced at ~0.7c
underround precisely because the size behind it is ~$2.6k. Any future flag of the form
"sum of asks < 1" is **not a finding until it has been depth-walked and charged for the
holding-period carry to resolution.** The depth-walk is ~5 free queries; run it before
writing anything down.

Corollary for the screen: keep the `url_ref` keying and the ask-sum (both strictly better
than 09-02), but drop the volume/price candidate filter when *summing a family* — it is
the filter itself that fabricates underrounds.

## 5. Resolver data-path verification (the actually load-bearing item)

The first settlement of the 66-estimate ledger is **2026-09-06 (Sachsen-Anhalt)**. A green
`selftest` says nothing about the input surface, so this tick verified the *real* path:
`resolve.fetch_settlement("polymarket", ...)` was run against **12 genuinely resolved live
Polymarket markets** pulled from `gamma?closed=true`. **12/12 read correctly**, including
one true YES (`3244600`, outcome=1) and eleven NOs — so both branches of the
`outcomePrices` decode are exercised on real venue data, not fixtures.

`selftest` ALL_PASSED; `resolve` pass ran clean over all 66 open estimates, every one
PENDING as expected (earliest close is 3 days out). **The 09-06 harvest is wired and
verified end-to-end.**

## 6. Standing state

`resolved 0/50 -> NO VERDICT | kill ALIVE | open 66`. `N_min = 50` is unmet; per
prereg §8 **no calibration verdict is licensed** and nothing here is evidence about the
agent's edge. Marginal value of forcing a thin estimate remains negative with 14 legs
settling inside 30 days — abstention is the disciplined move for a fifth consecutive tick.
