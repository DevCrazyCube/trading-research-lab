# The last untested memecoin space: post-graduation. Measured, and empty.

Every prior test in this repo ran on the bonding curve and stopped at graduation. The traders in the 48
fomo.family articles all describe something else — buying **days-old, based, uncrowded coins in the
200K–1M market-cap band**, which is *post*-graduation territory. That cohort had never been measured here.

It has now. Data: our survivorship-complete label set (33,866 enumerated creates from one 23-hour window,
1,075 graduations confirmed on-chain), joined to DexScreener's free token endpoint 37 days later. The
endpoint was control-tested first (WSOL and BONK both return 30 pairs), so a null result means dead, not
broken.

## The complete funnel

| stage | count | share of launches |
|---|---|---|
| launches enumerated | **33,866** | 100% |
| graduated the bonding curve | **1,075** | 3.17% |
| still have ANY live pair 37 days later | **~94** (8.7% of graduates, 95% CI ±4.5pp, n=150 sampled) | **0.28%** |
| in the 200K–1M mcap band | **0 of 13 sampled survivors** | ~0% |

**91.3% of coins that graduated are completely gone 37 days later.**

## The survivors are not tradeable

| statistic | median | max |
|---|---|---|
| liquidity | **$3,067** | $12,035 |
| FDV / market cap | **$2,696** | $11,522 |
| 24-hour volume | **$4** | $294 |

One of 13 survivors has more than $10k of liquidity. **Zero** are in the 200K–1M band. At the arena's own
5%-of-pool exit rule, the maximum position in a median survivor is **$153**.

So the post-graduation thesis fails on two independent grounds, either of which is fatal:
1. **Survival** — graduation is not a durable outcome, it is a waypoint to zero.
2. **Capacity** — even a perfect selector of survivors is trading $3k pools at $153 a clip.

## What this does and does not say

It does **not** say the traders in those articles are lying. Pump.fun runs ~44,836 creates/day; even a
1-in-10,000 rate yields a few genuinely tradeable coins daily. **The opportunity is real — it is just a
needle in ten thousand haystacks, and the entire game is the selection.**

And selection is precisely what this repo has now closed, five independent ways, each with a measurement
rather than an opinion:

| signal | result |
|---|---|
| price / momentum at entry | 540× lift, **fully impounded** before the first actionable slot |
| creator provenance (leak-free) | real **4.745×** effect, p=5e-5 — priced at 1.646× against a 1.615–1.793× break-even |
| the hard floor as a free put | **zero** of 82 winners available at ≤1.05× the floor when you can act |
| every entry-premium bucket at slot+1 | uniformly negative; realised rate ≈ **half** the break-even rate |
| **post-graduation survivorship** | **91.3% dead in 37 days; capacity $153** |

**Verdict: the memecoin launch game is closed to us, end to end — curve and post-curve.** Not because the
money isn't there, but because every observable that could select the needle is either absent or already in
the price before we can act, and what survives is too small to trade.

**Caveat, stated plainly:** this is one 23-hour launch window followed for 37 days. The survival rate is
measured with n=150 and a ±4.5pp interval; the capacity figures rest on 13 survivors. A different regime
could show a higher survival rate — but it would have to be ~40× higher to put a median survivor in the
tradeable band, and nothing here suggests that.
