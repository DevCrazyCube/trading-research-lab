# The graduated market is a different venue, and its arithmetic is different

**Status.** DESCRIPTIVE MEASUREMENT on data already collected. No pass spent, no ledger entry, no
strategy proposed. Incidental data: our collection followed bonding-curve addresses, and these
PumpSwap trades were caught only because they touched the same transactions.

**Why it exists.** Every negative result in this programme measures the **bonding-curve phase** —
where the toll is 5.4% and the median book is 20 lamports. 2.1% of curves graduate off that curve
onto a real AMM, and **we had never looked at it**. It turns out we did not need a new collection
to look: the corpus already holds 2,954 PumpSwap instructions in the fresh window and 1,778 in the
burned one.

## The measured fee schedule, from 765 real trades

| lp | protocol | creator | per leg | round trip | trades |
|---|---|---|---|---|---|
| **20** | **5** | **0** | **25 bps** | **0.50%** | 197 |
| 20 | 5 | 95 | 120 bps | 2.40% | 139 |
| 2 | 93 | 0 | 95 bps | 1.90% | 175 |
| 2 | 93 | 30 | 125 bps | 2.50% | 196 |

The bonding curve charges **125 bps per leg, universally** — every one of its 3,196 priceable
curves. The graduated market has a **25 bps tier**, five times cheaper, and it is not rare: 197 of
765 observed trades.

## Trade sizes that actually execute there

| p25 | median | p75 | p90 | max |
|---|---|---|---|---|
| 0.043 SOL | 0.180 SOL | 0.600 SOL | 2.61 SOL | **39.9 SOL** |

Against a bonding curve whose **median external capacity is 20 lamports**. A 39.9 SOL trade is
2,000,000,000× the median bonding-curve book.

## What that does to the toll

Round trip, including rent, network fees and constant-product slippage:

| position | bonding curve | graduated AMM |
|---|---|---|
| 0.1 SOL | 22.9% | **2.98%** |
| 0.5 SOL | 69.6% | **2.12%** |
| 1 SOL | 102.7% | **3.05%** |

*(Slippage priced against the ~1 SOL median bonding-curve reserve and the ~85 SOL graduation
threshold respectively. The bonding-curve column is why B19G measured a cliff: at 0.5 SOL the
position is larger than the book.)*

**The hurdle falls from >20% to about 2%, and it has a minimum around 0.5 SOL** rather than
degrading monotonically.

## What this does NOT establish

- **No strategy is proposed and none is implied.** A lower toll is a lower hurdle, not an edge. The
  whole programme's finding is that a low hurdle without a signal is still a loss.
- **765 trades is a fragment**, caught incidentally. It is enough to establish that a 25 bps tier
  exists and that multi-SOL trades execute; it is not a market study.
- **We do not know which tier applies to which pool**, or what determines it. Four schedules appear
  and the mechanism selecting them is unmeasured.
- **Selection into graduation is not random.** 2.1% of curves graduate, and they are the ones that
  already worked. Anything measured on graduated pools is conditioned on that.
- **None of the B19 results transfer.** They measured a different venue. This is not evidence that
  trading graduated pools works — it is evidence that the *reason* bonding-curve trading fails does
  not obviously apply there.

## The honest next step

A proper collection of the graduated market, preregistered before it runs, with the same discipline
as B11A/B11M. That is a new pipeline — different program, different accounts, different pool
addresses — not a parameter change to the existing one. It is the first genuinely new place to look
that this programme has surfaced since the trading search closed.

---

# What selects the fee tier — evidence, and an unresolved answer

The 25 bps tier is worth 5× the 125 bps bonding-curve rate, so whether it is **reachable by choice
or only by luck** is the question that decides whether the cheap tier means anything. Our fragment
does not settle it. What it rules out is worth as much as what it suggests.

## Ruled out

**Not a time-based change.** Both splits span essentially the whole window — `lp 20 / protocol 5`
over slots 435,570,135–436,930,575 and `lp 2 / protocol 93` over 435,571,919–437,180,811. A
protocol upgrade would have shown a clean boundary.

**Not purely a user tier.** 49 of 309 distinct users (15.9%) are observed on *both* splits. A
per-user tier would put that near zero.

**Not purely a pool property.** 27 of 343 pools charge both splits, and among users trading more
than one pool the evidence splits 34 (one split) against 36 (several) — as close to uninformative
as a test can land.

**Not simple trade size.** Median trade on the cheap tier is 191,504,283 lamports against
159,235,353 on the expensive one — overlapping distributions, not a threshold. If `fee_tiers` were
keyed on the size of a single trade, the cheap tier would sit at one end of the range.

## The leading hypothesis, stated as unconfirmed

**A cumulative user-volume tier.** The pinned IDL carries `FeeConfig { flat_fees, fee_tiers,
stable_fee_tiers }` and the corpus carries `InitUserVolumeAccumulatorEvent` (43),
`CloseUserVolumeAccumulatorEvent` (230) and `ClaimCashbackEvent` (264). A tier keyed on
*accumulated* volume fits every observation above: a user crosses a boundary mid-window (explaining
the 15.9% seen on both), the same pool serves users at different tiers (explaining the 27), and a
single trade's size does not determine it (explaining the overlap).

A weak corroborating detail, and it is weak: in all three pools examined that charge both splits,
the cheap-tier trades had the higher median size — consistent with larger, more active traders
sitting in a better tier. Three pools is not evidence, and it is recorded as a lead rather than a
result.

**If this hypothesis is right it is directly actionable** — the cheap tier would be earned by
accumulating volume rather than granted by luck, and the toll difference is 5×. **If it is wrong,
the 25 bps tier may be unreachable** and the graduated market's advantage shrinks toward the 95 bps
figure, which is still under the bonding curve's 125 but far less interesting.

## How it would be settled

Decode `UserVolumeAccumulator` account state alongside the trades and test whether the split is a
function of accumulated volume at trade time. That needs the accounts, which this corpus does not
carry — it followed bonding-curve addresses. It is a bounded question with a definite answer, and
it is the first thing a graduated-market collection should be designed to resolve.
