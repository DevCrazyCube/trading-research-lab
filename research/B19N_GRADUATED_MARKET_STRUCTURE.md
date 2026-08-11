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

## 3b. Depth survives listing — but the toll claim built on it was retracted

The depth claim was the load-bearing one after the fee correction, and it rested on a graduation
*threshold* rather than on measured post-listing depth. It can be partly measured after all: trade
events carry `pool_quote_token_reserves`, so for pools that traded, depth is directly observable.

**Depth holds.** Across the 33 graduated pools with at least one observed trade:

| | |
|---|---|
| median last-observed depth | **68.5 SOL — 80% of the graduation deposit** |
| pools ending ABOVE their deposit | 11 of 33 |
| pools ending below half their deposit | 7 of 33 |

**The bias is stated first because it is severe: these are only the 33 pools that traded.** The 49
silent pools are precisely the ones most likely to be dead, and §4 explains why this corpus cannot
distinguish "died" from "never queried". This is evidence that depth survives *conditional on the
pool trading at all*, and it is not evidence about the other 49.

### The round-trip toll — RETRACTED AND REBUILT

An earlier version of this section reported **"1.89% against the bonding curve's 22.9% — a ~12×
reduction"**, and attributed the flatness to depth absorbing slippage. **Both halves were wrong.**
The peer seat attacked it and the numbers below were then reproduced independently here.

**Defect 1 — the comparator was a different instrument.** The 1.89% was a buy-and-sell-back at ONE
state. The 22.9% was fee + *one-way* slippage + rent, i.e. the cost of *holding* a position. An
instantaneous round trip reverses its own price impact, so slippage **cancels by construction**.
Pointing the same instantaneous instrument at the bonding curve, on 3,084 burned curves:

| position | bonding curve, instantaneous |
|---|---|
| 0.01 SOL | 24.99% |
| 0.10 SOL | **4.75%** |
| 1.00 SOL | 2.72% |

The curve's own instantaneous round trip at 0.1 SOL is **4.75%, not 22.9%**.

**Defect 2 — the graduated figure omitted the fixed costs the curve figure charged.** Rent
(2,039,280 lamports), base fee and priority fee — 2,249,280 per round trip — were in the 22.9% and
absent from the 1.89%. Charging both sides identically:

| position | graduated | bonding curve | difference |
|---|---|---|---|
| 0.01 SOL | 24.38% | 24.99% | **0.61 pp** |
| 0.10 SOL | 4.14% | 4.75% | **0.61 pp** |
| 1.00 SOL | 2.12% | 2.72% | **0.60 pp** |

**A constant 0.6 percentage points at every size — which is exactly two legs of the 30 bps fee gap
(125 − 95).** The entire instantaneous-toll advantage is the fee difference and nothing else. There
is no 12×, no 2.5×; there is 0.6 points.

**Defect 3 — the flatness proved the opposite of what was claimed.** "Depth absorbs it, so the toll
is pure fee" reverses the causation. The toll is pure fee *because the instrument cancels slippage*,
and it would read 1.89% against a **1 SOL** pool just as readily. The flatness demonstrates that the
instrument is slippage-**blind**, not that the pool is deep. That the earlier table was flat to four
figures at exactly 1.89% = 2 × 0.945% was itself the tell, and it was missed.

### The depth claim was also wrong — and the corrected version is what depth really buys

Chasing the peer's point that only a HELD position touches depth produced a third correction, this
one to the depth figure itself.

**B19N compared a graduated pool's ~68 SOL quote reserve against "the bonding curve's ~1 SOL
reserve" and called it ~85×. That is the wrong pair of numbers.** A constant-product curve prices
against **virtual + real** reserves, and pump.fun's virtual quote reserve is a protocol constant:

| | median at last observed state |
|---|---|
| bonding curve REAL quote reserve | **0.000 SOL** |
| bonding curve VIRTUAL quote reserve | **30.000 SOL** ← what actually prices a trade |
| graduated pool (quote + virtual) | ~86 SOL |

**The effective pricing-depth ratio is 2.9×, not 85×.** The real reserve was never what a trade was
priced against, so comparing against it overstated the advantage by a factor of ~30.

### One-way entry slippage, measured on both venues

This is the cost an instantaneous round trip cancels and a held position actually pays — so it is
the right instrument, and the one every earlier figure here missed:

| position | graduated pool | bonding curve | ratio |
|---|---|---|---|
| 0.01 SOL | 0.01% | 0.03% | ~3× |
| 0.10 SOL | 0.11% | 0.33% | ~3× |
| 1.00 SOL | 1.14% | 3.22% | 2.8× |
| 5.00 SOL | **5.46%** | **14.28%** | 2.6× |

The measured ratio matches the corrected depth ratio, which is the check that the two agree.

**What this means in practice, and it is the one genuinely useful structural statement in this
document:** at small size the two venues are nearly equivalent — 0.11% against 0.33% is not a
difference any strategy lives or dies on. **The advantage only becomes material with size.** At 5
SOL the gap is 8.8 percentage points, and it widens as position grows. The graduated market is not
a cheaper version of the bonding curve; it is the same kind of market roughly three times deeper,
which matters if and only if you want to trade in size.

### What this leaves, stated as the rebuild it is

- **The fee advantage is real and modest: ~0.6% of a round trip.** Consistent with §1b's finding
  that the payable median is 95–100 bps against the curve's 125.
- **The depth advantage is real and modest: ~2.9× effective, ~3× on slippage** — not the 85×
  first claimed, which compared against a reserve that never priced anything.
- **The 68.5 SOL depth measurement stands but is DECOUPLED from the toll.** It is evidence about
  depth; the toll table is not, because the toll never touched depth at all.
- **A first held-position probe is negative**, and stated as a probe rather than a result: entering
  at each observed state and exiting at the NEXT observed trade, 0.1 SOL, across 166 pairs on 15
  pools, gives a median of −6.34% with 25% positive. Exit-at-next-trade is not an exit RULE — it is
  whenever somebody else happened to trade — so this measures feasibility and cost, not strategy.
- **The genuine structural question is untouched by any of this.** Depth pays off only when a
  position is BOUGHT, HELD while the price moves, and SOLD at a *different* state — entry slippage
  plus exit slippage at moved reserves, which is small in a 68 SOL pool and murderous in a 1 SOL
  one. No figure in this document measures a single lamport of that.
- **The earlier "at 22.9% no exit rule can work, at 1.89% that objection is gone" is withdrawn.** It
  was already in tension with this programme's own conclusion: the bonding-curve close rested on the
  53%/47% outcome asymmetry measured with a *holding* instrument, not on a toll wall. A modestly
  cheaper round trip does not repair a distribution where one abandonment erases five wins.

**The case for collecting is therefore narrower and better than the retracted version.** It does not
rest on a toll multiple that was mostly an instrument artifact. It rests on the one real unknown:
the **held-position** cost and the outcome distribution across the 49 silent pools — the only number
that could reopen the trading question, and the only one this corpus cannot produce.

## 3c. What graduation actually buys: a counterparty that can pay

Three claims about this venue have now been retracted or cut by an order of magnitude — the fee
advantage, the toll multiple, and the depth ratio. This one is different in kind, and it is stated
last because it survived the attacks that killed the others.

**External exit capacity** — the REAL SOL sitting in the venue available to pay a seller. Virtual
reserves price a trade; they do not fund one. This project's own rule: *an exit funded by your own
entry is not liquidity.*

| percentile | bonding curve (n=3,932) | graduated pool (n=33) |
|---|---|---|
| p10 | 0.0000 SOL | 15.68 SOL |
| p25 | 0.0000 SOL | 62.38 SOL |
| **p50** | **0.0000 SOL** | **68.48 SOL** |
| p75 | 0.0000 SOL | 121.36 SOL |
| p90 | 0.0050 SOL | 147.24 SOL |

**91% of bonding curves (3,602 of 3,932) END holding less than 0.01 SOL of real quote. Zero of 33
graduated pools do.**

> **Corrected before publication — the table above is measured at each curve's LAST observed state,
> and read alone it is an endpoint artifact.** Curves are empty *at death*, which is nearly a
> tautology. Measured through a curve's life instead:
>
> | measured at | p10 | p50 | p90 |
> |---|---|---|---|
> | t0 + 10 slots | 0.0000 | **1.8695** | 14.6158 |
> | t0 + 100 slots | 0.0000 | 0.0941 | 13.6913 |
> | t0 + 2000 slots | 0.0000 | 0.0114 | 3.9840 |
> | **peak over the whole life** | 0.0000 | **1.0000** | 23.6047 |
>
> So "the median curve holds no real SOL" is **false as stated**. The median curve holds ~1.9 SOL
> ten slots in, and its p90 holds ~14.6 SOL. This was self-attacked on the peer's prompting before
> the claim went anywhere, and the claim has been rewritten to what the data supports.

### What actually survives, stated at the strength the measurement carries

**The median bonding curve's BEST-EVER external capacity is 1.00 SOL** — that is the peak across its
entire life, not its endpoint. 49% of curves never reach 1 SOL at any point, and **38% never reach
0.1 SOL**. A graduated pool receives ~85 SOL at graduation and the median still holds 68.5 SOL at
last observation.

The consequence is about **room to size**, which is where §3b's hurdle table was heading:

- a 1 SOL position is **100% of the median curve's best-ever capacity** — you would be the entire
  external market, and there is nobody to sell to;
- the same position is **~1.5% of a graduated pool's**;
- and for 38% of curves, even B19K's 0.1 SOL position exceeds the total external capacity the curve
  ever had.

**That is why sizing up was never available on the bonding curve**, and it is the same fact as
B19G's capacity wall seen from the other side. The hurdle nearly halves between 0.1 and 1 SOL — but
on the curve that size cannot be exited at the median, so the cheaper hurdle was unreachable. On a
graduated pool it is reachable. Whether reaching it *helps* is a different question and this does
not answer it.

This is the mechanism behind B19G's result and it was never a fee or slippage problem. B19G measured
the median capacity wall at **20 lamports** under its own frozen admission rules — a stricter and
separate measurement from the one above, and the two agree in direction rather than in magnitude.

**Graduation is the event that creates a payable counterparty**, and it does so by protocol
construction — ~85 SOL of real quote is deposited at graduation whatever the token subsequently
does. That is not a survivorship artifact: the deposit is guaranteed, and §3b shows it is still
~80% present at the last observed trade for pools that traded.

### The limits, which are severe and are why this is not a result

- **33 pools.** The other 49 were never queried (§4), and they are the ones most likely to be empty.
  Whether the deposit *stays* is measured only on pools that traded.
- **The endpoint problem was real and is now corrected above.** The claim rests on PEAK lifetime
  capacity, not on the endpoint, and it is much weaker than the endpoint version: a median peak of
  1.00 SOL rather than zero.
- **A payable counterparty is a necessary condition, not a sufficient one.** It says an exit *can*
  be funded. It says nothing about whether the price ever reaches a level worth exiting at, which
  is the 53%/47% asymmetry and remains untouched.

**This is the collection's actual justification**, and it is narrower and better than the 12× toll
that preceded it: every exit rule this programme measured was tested against a venue where, at the
median, no external money existed to pay it. The graduated market is the first venue in this project
where the exit side is funded by construction — and whether that changes the outcome distribution is
precisely what the 49 silent pools would settle.

## 3d. An upper bound on what liquidity can buy — computed without spending anything

The peer seat's recommendation was to collect, scoped to one question: *does standing liquidity
remove the never-sellable mass and change the asymmetry?* That question has an **upper bound that
can be computed on data already held**, and it should have been computed before anyone proposed
spending on it.

**The bound.** Take B19K's frozen cell on the selected population and simply **delete every position
that was never sellable at any observed point**. That is more generous than standing liquidity could
ever be — it does not merely make those positions exitable, it removes their losses from the
population entirely. Whatever real liquidity could buy, it cannot buy more than this.

| | as measured | with the never-sellable removed |
|---|---|---|
| cells | 927 | 864 |
| hit rate | 45.42% | 48.73% |
| median win | 9,384,410 | 9,384,410 |
| median abandon | −37,746,043 | −37,746,043 |
| **mean outcome** | **−18,935,634** | **−12,777,191** |
| median outcome | −8,949,805 | −1,496,253 |

**It is still deeply negative.** Perfect exitability closes about a third of the loss — 6.2M of
18.9M — and leaves the other two thirds untouched, because the other two thirds is the *shape* of
the outcome distribution and not the plumbing. The median win is unchanged. The median abandonment
is unchanged. Only the frequency shifts, by 3.3 points.

**A correction to the premise as well.** The proposal cited "927 of 2,821 positions unsellable — a
third of the loss." The count is right for the *whole* population but wrong for the one actually
traded: among the **selected** positions B19K used, only **63 of 927 (6.8%)** were never sellable,
and 31 of those 63 are positions with no observation after entry at all — a *coverage gap*, not a
demonstration of unsellability. The genuinely unsellable selected population is **32 positions**.
The selection rule was already filtering out most of the never-sellable mass.

### What this means for the collection decision

**The graduated market's one surviving structural advantage — a counterparty that can pay — does not
reach the outcome.** Granting it in full, and granting it more generously than reality could, the
rule still loses 12.8M lamports per 100M position on average.

This does not prove no rule can work there. It proves that **this rule family cannot be rescued by
liquidity**, which was the specific hypothesis the collection was to test. A collection scoped to
that question would spend RPC hours to measure something already bounded here, and the bound is on
the wrong side of zero.

*Burned data. The bound is exact arithmetic on the frozen cell; the generalisation to "no rule in
this family" is an inference from it, not a measurement.*

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
