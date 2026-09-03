# The memecoin programme, closed with a number (2026-09-04)

248 hypotheses generated across 8 domains, 193 testable, **72 tested** in a parallel fleet with
adversarial refutation. **Zero edges. Zero survivors.** Plus a separate 10-agent on-chain forensic
audit of 329,956 trades / 39,064 wallets whose flow reconciles to reserve_observation with **max
error 0 lamports on all 3,239 curves**.

## The finding: unprofitable BY CONSTRUCTION, not for lack of looking
The universe's **GROSS** 15-minute drift is negative **before any cost**: about **-1.8% gross**,
-2.92% net (n=50,177 entries, k=453 mints, survivorship-free, no-lookahead, res 95.8%).
Combined with the earlier proof that stripping every rug with PERFECT foreknowledge leaves +0.78%
gross against a 1.14% toll: the median coin drifts down, the mean coin drifts down, a perfect rug
screen still loses, and the toll is 1.14-2.5% round trip. There is no arrangement of entry, exit,
sizing, venue or instrument that turns a negative gross drift positive.

## The ledger, measured: it is a closed zero-sum box
One 23h chain-enumerated window:
| | SOL | USD |
|---|---|---|
| Deployers, net realized | **+2,072** | +$217,580 |
| Everyone else, net realized | **-9,683** | **-$1,016,738** |
| Venue fees | +2,175 | +$228,000 |
| SOL trapped in curves | +7,110 | - |
| **Sum** | **0.0** | |

The ONLY role with a positive median is **issuance** -- and 97.9% of deployer profit is conditional
on a same-block co-buyer, which is 69.6% of the time the deployer's own bundle. Consolidated, true
external extraction is **$30k-$47k, not $218k**. Cold deploys (nobody else traded): **0 of 923
profitable**. The deployer edge is not speed or skill, it is owning supply with a zero cost basis
and selling it to buyers within a median of ~6 seconds.

## Size makes it strictly worse (the "be the whale" question, answered)
| single-position size | n | median P&L | profitable |
|---|---|---|---|
| >= 5 SOL | 1,823 | -0.125 SOL | 45.5% |
| >= 10 SOL | 481 | -0.249 SOL | 43.2% |
| **>= 25 SOL (~$2,600)** | **73** | **-1.315 SOL** | **32.9%** (CI entirely below zero) |
| >= 50 SOL | 10 | **-516 SOL on 813 deployed = -63.5%** | |

Of 181,226 buys, NINE were >= $4,000 and FOUR >= $8,000. **Eight of the nine lost.** The four who
bought the entire 85-SOL curve capacity in one transaction ended holding ~100% of supply at
realized -86 SOL; their coins went **-99.9% / -98.9% / -86.7%**. Nobody bought their top.
Even for deployers the best dev-buy is 5-10 SOL ($525-$1,050); at **76+ SOL: 0% profitable**.

## THE HARNESS CONTRACT -- the durable asset, and I violated all three tonight
| error | measured inflation |
|---|---|
| entering at the SIGNAL bar's own open instead of the next REAL bar | **+37.25pp** (random bars read +34.33% instead of -2.92%) |
| pooling OVERLAPPING positions in one mint | **+6.5pp** (a median went -2.01% -> +4.50%) |
| pooling by TRADE instead of MINT-EQUAL weighting | **+5.3pp** (+0.47% -> -4.81%) |

The entry-bar error is **invisible in the median**, which is why it survives casual checking.
Canonical benchmark from now on (n=50,177, k=453): random-bar 15m net **-2.92%** at -30% dropout
charge, **-3.75%** at -50%, **-5.83%** at -100%. Beat that, not zero.

## Positive medians are an artifact signature, not a payoff shape
Three mechanisms manufacture a positive median out of a negative-mean process:
1. **overlap pooling** (above);
2. **take-profit truncation** -- a +5% TP on RANDOM bars with NO signal lifts the median from
   -2.32% to **+2.00%** (n=5,165, k=425) while the mean barely moves;
3. **loss-cap truncation** (isolated margin's -100% floor).
A bet structure cannot create drift. Every positive median chased this session came from one of these.

## What was killed tonight, in one line each
momentum entry (negative alpha vs a random bar) - stops/brackets (0 of 272; death is a -90% JUMP,
34-67% of stop fires unexitable) - mean reversion (0 of 100; deeper drop = worse) - cross-pool arb
(0 of 188 Jupiter round trips) - rug screens (perfect foreknowledge still loses) - second leg (1.7%
ever print a new high) - graduation timing (-17.99pp vs random) - wash trading (matched-pair effect
-2.64 SOL, washers' median -$5) - slot-0 sniping (cohort -$173k; 112 professionals made +16 SOL in
182 hours) - size/whale entry (above) - and finally the session's own last survivor.

## Live confirmation
The armed paper bot traded the last survivor for 76 trades: **-$37.80, mean -9.95%, median -0.35%**,
degrading monotonically as n grew (+0.75% at n=11 -> -7.91% at n=31 -> -9.95% at n=76). Disarmed.

## What remains, at $0
Every one of the 72 tested hypotheses conditioned on something ENDOGENOUS to the tape. The one
untried information class is **exogenous**: a third party spending real dollars at a known timestamp
(DexScreener paid boosts, claimed profiles, pump.fun live streams). Collector running with a
mcap/age-matched control; prereg frozen at sha cf7e51c6; honest prior **10-12%**.
Declared kill-risk #1: boosts are bought by the deployer AT THE TOP, making them an exit signal.

**Spend recommendation: buy nothing.** The structural deficit is ~2.9pp of adverse drift plus
1.14pp of toll; the largest cost term any purchasable dataset could recover is ~1.1pp. A perfect
result still leaves a ~1.8pp/trade hole.
