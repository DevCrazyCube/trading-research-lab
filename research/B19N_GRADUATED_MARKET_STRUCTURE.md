# B19N — the graduated market's structure, measured

**Status.** Findings about the venue, established on window 1's burned corpus. **No trading claim is
made here and no rule is evaluated.** Every figure is a description of the venue; the study that
reads any of it for an outcome does not exist yet and must be preregistered and frozen first.

**Why burned data is the right place for this.** Window 1 is spent, so nothing measured on it can be
an out-of-sample result. That is exactly what makes it the correct corpus for *designing* the
instrument — the arithmetic below determines what a collector must fetch, and settling that on
burned data costs nothing that a future test would need.

---

## 1. The fee decode, verified by the events' own arithmetic

Every figure about this venue rests on reading fee basis points off decoded events. Rather than
trust the IDL's field names, the decode was checked against the identity the events must satisfy —
each carries both the basis points and the lamport fee charged, so `fee == ceil(base * bps / 10000)`
has to hold:

| base reproducing `lp_fee` | events |
|---|---|
| `quote_amount_in` | 167 |
| `user_quote_amount_in` | 125 |
| `quote_amount_in_with_lp_fee` | 9 |
| **none** | **1** |

**301 of 302 reconcile exactly.** Three instruction variants compute the fee on different bases. A
first check against a single base showed 139 "disagreements" — a 46% failure rate that was a base
mismatch, not a decode error. Reported without the follow-up it would have buried a correct decode.

**The field names are therefore confirmed.** Both errors below are errors of AGGREGATION, not of
decoding — which is worth separating, because a decode error would have required recollection and
an aggregation error is repairable from the corpus already in hand.

### The rate — corrected twice, and the correction matters more than the original claim

An earlier version of this section reported "27–28 bps on 78 trades, 0.54% round trip, a 4.5×
reduction against the bonding curve." **That was wrong in two independent ways**, one found by the
peer seat and one found while checking their finding.

**Error 1 — the cheap tier is a minority, reported as the venue.** The distribution was printed
sorted ascending and truncated to its first rows, so the cheap tail was read as the market. The full
per-leg distribution across all **765** trade events — one per instruction coordinate, see the note
on counting below:

| total bps per leg | trades | share | |
|---|---|---|---|
| 25 | 197 | 25% | the "cheap tier" |
| 95 | 180 | 23% | **median** |
| 120 | 139 | 18% | |
| 125 | 196 | 25% | identical to the bonding curve |
| 100 / 105 / 115 | 42 | 5% | all creator-fee-bearing |

**The median graduated leg pays 95 bps, not 25.** A creator fee is present on **391 of 765 = 51%**
of trades. A
quarter of trades get the real break; three-quarters pay 95–125, the same order as the bonding
curve's 125. This was found independently by the peer seat, whose decode reproduces these counts
exactly from the same pinned IDL.

**Error 2 — the buyback fee was double-counted.** The first effective-rate figure summed
`lp + protocol + coin_creator + buyback` against notional. But `buyback_fee` is a *split of the
protocol fee*, not an additional charge on the trader: `buyback_fee == protocol_fee * bps / 10000`
holds on **all** events, with `buyback_fee_basis_points` equal to 5000 (50%) on 766 of 769 decodes
and 0 on 3. Money already counted was counted again.

**Error 3 — the denominator itself.** The first two versions of this section reported 769 and 787
events for the same quantity, and the peer seat reported 765. All three came from the same corpus;
the divergence was mine. Iterating every PumpSwap envelope in a transaction and de-duplicating on a
composite of field VALUES counts an event twice whenever the chosen fields collide, and differently
for each choice of key. **The canonical count is 765** — 302 `BuyEvent` plus 463 `SellEvent`
instruction rows, each a distinct `(slot, transaction_index, outer_index, inner_index)` coordinate
with a stored body, matched to its envelope by that coordinate rather than by its contents. Every
figure in this document has been recomputed against it. The lesson is the project's own: an
ordering-or-identity key made of values is not an identity, and canonical coordinates exist
precisely so that counting does not depend on what a row happens to contain.

### What actually drives the difference — and it is not the fee

At the median 95 bps against the curve's 125, the fee difference is **0.6% of a round trip**. It is
not the story. The gap between a ~4% graduated toll and the bonding curve's ~22.9% is almost
entirely **slippage and rent**: a 0.1 SOL order against ~85 SOL of pool depth barely moves the
price, while the same order against a ~1 SOL bonding-curve reserve *is* the slippage term, and the
2 M lamport rent is 2% of the position on the curve.

So the correct statement is **"depth is ~85× greater," not "the fee is 4.5× cheaper."** The second
is false at the median. The first does not depend on the fee tier at all.

> **This makes the depth caveat load-bearing rather than incidental.** The 85 SOL is a graduation
> *threshold*, not measured post-listing depth — and it is now carrying the entire finding instead
> of sharing it with a fee advantage that mostly is not there. **If pools drain after listing, the
> slippage term rises and the toll climbs back toward the curve's.** That is the first thing any
> graduated-market collection must measure, and §4 explains why this corpus cannot.

## 1b. The cheap tier is NOT reachable by choice — the crux question, closed negatively

Both seats flagged the same crux: at a 25% share, whether the 25-bps tier is *selectable* decides
whether it is an addressable market or merely the trades that happened to carry a waived creator
fee. It is the second. Four candidate selection mechanisms were tested on the canonical 765 and all
four fail.

**There are two base structures, not a continuum.** Decomposing every leg into its components:

| base | lp | protocol | + creator | trades |
|---|---|---|---|---|
| **25** | 20 | 5 | 0 → 95 | 197 at creator 0, 139 at 95, 42 spread |
| **95** | 2 | **93** | 0 → 30 | 175 at creator 0, 196 at 30 |

**Not the venue.** Our 82 graduated pools see *both* structures, near 50/50 — 100 trades
protocol-heavy against 99 lp-heavy. Graduating does not put a pool in either camp.

**Not the instruction.** `buy`, `sell` and `buy_exact_quote_in` each show both structures in similar
proportion. There is no cheap call to make.

**Not the clock.** The structures fully coexist across the window (slots 435,570,135–436,930,575 and
435,571,919–437,180,811). By decile the protocol-heavy share bounces 34%→76%→35% with no trend, so
this is not a protocol change with a before and an after.

**Not the pool, which is the one that looked promising.** The structure *is* fixed per pool in 316
of 343 pools, so a trader could in principle read a pool's structure off its history and trade only
the cheap ones. Tested directly on the 122 pools with at least two trades:

- the first trade's base predicts later trades **77%** of the time (27 pools vary);
- 72 of 122 pools (59%) open on the cheap 25-bps base;
- **but the total actually paid on those very pools has a median of 100 bps.**

The full distribution on cheap-base pools is 25 bps on 120 legs and 95–125 bps on 154 of them. The
base is only half the price: the creator fee, 0 to 95 bps, is stacked on top and is neither fixed
per pool (92% predictive, so it does move) nor anything a counterparty controls. **Selecting on the
cheap base does not buy a cheap trade.**

So the 25-bps tier is not a tier anyone can opt into. It is the residue of trades whose creator fee
happened to be zero, and the honest median for a trader who cannot choose is **95–100 bps per leg,
about 2% round trip.** Against the bonding curve's 125 bps that is a saving of roughly 0.5% on a
round trip — real, and far too small to matter to any of the asymmetries this programme has
measured.

*Observation on burned data, not a preregistered test. It is reported because it CLOSES a question
rather than opening one: no study should now be written on the premise that the cheap tier is
addressable.*

## 2. The pool's invariant, determined exactly

Trade events carry `pool_base_token_reserves`, `pool_quote_token_reserves` **and**
`virtual_quote_reserves`. Testing both candidate invariants on all 765 canonical trade events with
exact integer arithmetic:

| invariant | exact | grows | **breaks** |
|---|---|---|---|
| `quote * base` | 0 | 422 | **343** |
| `(quote + virtual) * base` | 0 | **765** | **0** |

**The virtual term is not optional.** Any simulator that prices this venue on plain `quote * base`
is wrong on 45% of trades.

**But state it precisely: `virtual_quote_reserves` is a per-pool CONSTANT, not a dynamic term.** It
holds one value throughout the pool's life in **340 of 343** pools, moving in only 3, and takes 183
distinct values across the population including 0. So the finding is not "the pool has a second
moving reserve"; it is that **the pool prices against quote plus a fixed per-pool offset**, and a
simulator must therefore learn that offset per pool and may then treat it as constant. This
qualification was requested by the peer seat, whose concern was that a constant term could make the
invariant trivially satisfiable. It does not — plain `quote * base` still breaks on 343 events, so
the offset is doing real work — but the original phrasing implied a dynamic quantity it is not.

**The carried reserves are PRE-trade.** Chaining trade *N*'s reserves through trade *N*'s own
amounts reproduces trade *N+1*'s reserves — exactly, on 30 of 61 consecutive pairs in the deepest
pool. Exact integer equality on 30 independent pairs does not happen by coincidence; the 31 failures
are missing trades, which is the point of §4.

**Consequence for collection.** Window 1 needed an account snapshot at every observation because a
bonding-curve trade event does not carry reserves. Here the price path rebuilds from the event
stream alone. That deletes the entire account-polling stage — the expensive part of window 1.

## 3. Graduation is real, rare, and too fast to anticipate

| | |
|---|---|
| launches in window 1 (`CreateEvent`) | 3,932 |
| graduations (`CompleteEvent`) | 82 |
| graduations belonging to window 1's **own** cohort | **82 of 82** — zero drift-in |
| **graduation rate** | **2.09%** |
| slots from launch to graduation | min 0, **median 49**, max 686,257 |

**The median graduation completes 49 slots after its own launch — 19.6 seconds.** 51% complete
within 100 slots (~40 s). The distribution is severely bimodal: half are effectively instantaneous,
a tail runs for days.

> **Checked against a double-counting attack from the peer seat, and it holds.** Completion is
> emitted under TWO event names — `CompleteEvent` and `CompletePumpAmmMigrationEvent`, 82 each,
> **164 canonical events for 82 graduations**, with every one of the 82 mints carrying both names.
> So the double-count is real in the event stream. It does not reach the figures above, because the
> population is keyed by MINT and not by event: 82 distinct mints, each timed from its earliest
> completion coordinate. Recorded rather than waved away — the same class of key error did corrupt
> the event counts in §1, where the key was made of field values instead of coordinates.

This closes one strategy on structure rather than on backtest. "Detect a token climbing toward
graduation and ride it" cannot be implemented against a median of 20 seconds — by the time a curve
is observably heading there, half the population has already arrived. What remains open is the
*other* side: the pool exists after graduation, and that venue is the cheap one.

**The graduation deposit does not vary meaningfully.** 53 distinct values spanning 5,076 lamports,
from 84,990,359,056 to 84,990,364,132 — a spread under 1 ppm. Every pool opens at effectively one
size, so **there is no size signal to select on at graduation.**

> **Correction, recorded because the error is instructive.** This was first read as "exactly 85.0
> SOL for all 82, min = median = max," and written down as a protocol constant. It was an artifact
> of printing lamports through a float at one decimal place. The substantive conclusion survives —
> the spread is negligible — but *equality* was false. In a project whose first rule is no float
> anywhere, the float was in a display string, and it manufactured a constant that was never there.
> `assert_deposit_uniform` now tests a spread against a stated tolerance in exact integer
> arithmetic, and it is what caught this.

## 4. Why window 1 cannot answer the trading question — and what can

Of the 82 graduated pools, **49 show zero trades**. The naive reading is that most graduated tokens
die instantly. That reading is not available:

- the observation tail after graduation runs a **median of 171 hours**, so the window was open;
- but window 1's PumpSwap coverage is **incidental**. It targeted bonding curves, and a trade on a
  graduated pool touches no bonding curve. Those trades were captured only when they happened to
  share a transaction with something in scope.

So the 49 zeros are consistent with *never traded* and with *never looked at*, and this corpus
cannot separate them. Under this project's standing rule — absence is refusal, and a silence that
was never queried carries no information — **no figure may be computed over those 49 either way.**

Only 3 pools have ≥10 trades and only 10 have ≥4. **A panel of 3 cannot test an exit rule**, which
is the direct answer to whether the graduated market can be evaluated from data already in hand: it
cannot.

**`scripts/b19n_graduated_collector.py` resolves exactly this.** It walks each pool's *own*
signature history, so a pool with no trades becomes a pool *observed* to have no trades. Its census
reports `pools_observed_to_have_no_activity` separately from `pools_not_yet_walked`, because those
are different quantities and collapsing them is the error this whole section exists to avoid.

Cohort built and verified offline: **82 pools, 79 distinct creators**, slots 435,578,072–436,255,707.
The collector refuses to write into `research/b11a` or `research/b11m_window2` (checked *before*
`mkdir`, so a mistyped path creates nothing), and refuses to run without `SOLANA_RPC_URL`.

**It has made no chain query.** The endpoint is not set in this environment and the collection has
not started.

## 5. What is open

- **Does the graduated market trade at all, for most pools?** Unanswerable from window 1; the
  collector is built and needs an endpoint.
- **Does the depth advantage survive listing?** This is now the crux. The ~85× depth claim rests on
  a graduation THRESHOLD, not on measured post-listing depth, and after the fee correction above it
  carries the finding alone. If pools drain, the toll climbs toward the curve's.
- **Is a lower toll enough to change any outcome?** Unknown, and not implied by being lower. The
  bonding-curve close rested on a 24.4%-incidence asymmetry where one abandoned position erases
  five wins — a toll reduction does not by itself repair that shape, and claiming otherwise would
  repeat the reasoning this programme has spent the whole night retiring.
- **Does `UserVolumeAccumulator` state determine the fee tier?** Sharper now that 25 bps is known to
  be a 25% minority: whether that tier is reachable BY CHOICE decides whether the cheap quarter is
  an addressable market or merely the trades that happened to carry a waived creator fee. The
  corpus does not carry the accumulator state, so this is part of the same collection decision.
