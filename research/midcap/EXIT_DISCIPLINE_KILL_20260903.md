# The memecoin KILL, and the two findings worth more than the strategy (2026-09-03)

Four independent measurement tracks, ~340 rules, adversarial verification armed. **Zero tradeable.**
0 of 35 preregistered exit arms, 0 of 272 grid exit rules, 0 of 30 entry-timing cells, 0 of ~20 segments
cleared net>0 AND median>0 AND ci_low>0. No claim reached the refutation round because none claimed a pass.

## The exit-discipline thesis was mine, and it is falsified three ways
The premise: median trade positive, mean negative => cut the left tail with stops and it turns positive.
1. **The tail is not concentrated.** Worst 5% of trades carry 18.9% of total loss vs a 7% uniform null.
   Once any stop is applied: 8% vs an 8% null — literally zero concentration. Nothing to cut.
2. **Perfect foresight doesn't clear the toll.** An oracle deleting the worst **20%** of trades still
   leaves **-2.4% net**.
3. **Any survivable stop fires on the median trade.** Median MAE within 60m is **-31.6%**; 71.9% of
   trades breach -20%. Stop-fire rates 50-94%, toll charged on every fire.

**The structural reason, and it kills stops permanently:** 65.1% of graduates have a single traded
minute of **<= -90%**. That is an LP pull, not a slide. **34-67% of all stop fires are UNEXITABLE** —
you get the collapse bar's close, not your stop price. A stop is a hope, not a fill.

## The entry everyone reaches for is NEGATIVE alpha
Random-bar control on the same 24 mints: the +30%/15m momentum entry **destroys 3.6-12.2pp of gross
return versus a random minute in the same names** (random 15m +0.63% gross; momentum 15m -9.05%).
Buying the thing that just went vertical is worse than buying blind.

## Finding 1 — the toll is 3x what we pay, and it is the largest lever measured anywhere
PumpSwap venue fee decoded from 41 Buy/SellEvent records over 10 pools: **30 bps/side** (lp 20 +
protocol 5 + creator 5), not the 100-125 bps the docs imply. Round trip at $60 notional:

| route | round trip |
|---|---|
| GMGN terminal | **4.19%** |
| Axiom terminal | **3.57%** |
| repo's inherited assumption | 3.00% |
| **direct (own tx, own tips)** | **1.14%** |

Direct routing saves **243 bps per round trip**. Size is NOT the problem: base+priority is 0.4 bps on
$60 and price impact 3.3 bps. The cost is **terminal tip defaults** — GMGN's auto-sell recommendation
alone is 210 bps round trip. It flips no verdict here, but it is the one lever that is real.

## Finding 2 — noise exceeds every signal ever found
The identical unconditional arm measured **-1.68% gross** in one 39-min session and **+2.33%** in the
adjacent one. **Session-to-session swing 4.01pp**; every "edge" found across two months is 1-3pp.
More minutes inside one session buy nothing. Session is the cluster unit.

## Two methodological traps that manufactured false passes here
- **Conditioning on bar count is a survivorship filter that INVERTS the answer.** On a >=60-bar subset,
  M=1/H=15 reads ci_low **+7.1% (clean PASS)**; on the full 44-coin panel the identical cell reads
  ci_low **-21.4% (fail)**. Deep-loss coins have few bars *because they died*. Median minutes-to-peak:
  68 filtered vs **13** unfiltered.
- **Dropout bias is strongest in exactly the segments that look best.** Vanished mints' last observed
  3-min move: **-19.21%**; survivors' -0.03%. The two highest-mean segments had the two worst
  resolution rates (73.6%, 71.1% vs 94-98%) and were 7-of-8 the same coins — one artifact, not two.

## The one reproducible directional result
Buying at/near ATH (mcap/ath >= 0.95) is **negative against its own universe**: -0.97% at 15m
(median -1.68%), -1.54% at 30m, consistent across both sessions. **Do not buy the top.**

## What survives
Nothing tradeable. One untested cell remains because the exit sweep used a momentum entry while the
motivating observation came from the snapshot universe — two distributions never crossed. That test is
preregistered in AGE2H_SESSION_PREREGISTRATION.md (sha 9549ecc6) at a stated 75-85% prior of being an
artifact, and it needs >=5 sessions on >=5 separate days. Sample-size warning: the graduate crawl had
covered 65 of 1,075 mints; the sign is uniform across every arm, robustness cut, and a leave-one-mint-out
jackknife that never crosses zero, so the KILL is safe, but nothing here is powered to support a bot.
