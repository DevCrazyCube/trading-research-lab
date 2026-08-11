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

**Effective rate from the amounts, not the labels.** Summing `lp_fee + protocol_fee +
coin_creator_fee + buyback_fee` against notional: **27–28 bps on 78 trades, 0.54% round trip.** The
labels say 25; the difference is the creator and buyback components. Against the bonding curve's
universal 125 bps per leg this is a **4.5× reduction**, now verified by two independent routes.

## 2. The pool's invariant, determined exactly

Trade events carry `pool_base_token_reserves`, `pool_quote_token_reserves` **and**
`virtual_quote_reserves`. Testing both candidate invariants on all 787 trade events with exact
integer arithmetic:

| invariant | exact | grows | **breaks** |
|---|---|---|---|
| `quote * base` | 0 | 436 | **351** |
| `(quote + virtual) * base` | 0 | 787 | **0** |

**The virtual term is not optional.** Any simulator that prices this venue on plain `quote * base`
is wrong on 45% of trades.

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

**The median graduation completes 49 slots after its own launch — about 20 seconds.** The
distribution is severely bimodal: half are effectively instantaneous, a tail runs for days.

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
- **Is the 4.5× cheaper toll enough to change any outcome?** Unknown, and it is not implied by being
  cheaper. The bonding-curve close rested on a 24.4%-incidence asymmetry where one abandoned
  position erases five wins — a toll reduction does not by itself repair that shape, and claiming
  otherwise would repeat the reasoning this programme has spent the whole night retiring.
- **Does `UserVolumeAccumulator` state determine the fee tier?** Still open; it would explain why
  some trades pay 27 bps and others several times that.
