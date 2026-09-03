# Exogenous paid-attention events — PRE-REGISTRATION
Frozen 2026-09-04, BEFORE any event is collected. $0. The last untried information class.

## Why this and nothing else
248 hypotheses were generated and 72 tested. ALL of them conditioned on something ENDOGENOUS to
the tape: price, volume, wallet flow, venue mechanics. All of them inverted or vanished. The
universe's GROSS 15m drift is -1.8% before costs, so no endogenous rule can win.

A DexScreener paid boost, a claimed token profile, or a pump.fun live stream is different in kind:
a THIRD PARTY SPENDING REAL DOLLARS AT A KNOWN TIMESTAMP. It is costly, exogenous, dollar-
denominated commitment that does not come from the price series. That is the only untried class.

Honest prior it passes: 10-12%.

## Events collected (all free, no key)
 - api.dexscreener.com/token-boosts/latest/v1   (paid boost, has an amount)
 - api.dexscreener.com/token-boosts/top/v1      (cumulative boost leaders)
 - api.dexscreener.com/token-profiles/latest/v1 (paid/claimed profile)
 - frontend-api-v3.pump.fun/coins + is_currently_live (creator streaming = attention spend)
Record FIRST-SEEN timestamp per tokenAddress, the boost amount, and the price at first sight.

## Outcome
Forward return of priceUsd at +15m, +1h, +6h from FIRST SIGHT of the event.

## Control -- this is the whole test
A time-matched, mcap-matched, age-matched non-boosted token drawn from the SAME snapshot.
Without the matched control this measures "boosted coins are coins that move", which is
circular. The estimand is the DIFFERENCE, boosted minus matched control.

## MANDATORY harness contract (measured tonight; violating any one invalidates the result)
 A. ENTRY BAR: enter at the FIRST REAL observation strictly AFTER the event timestamp. Entering
    at the event's own print inflated a random-bar 15m mean from -2.92% to +34.33% (+37.25pp of
    fiction) and is INVISIBLE in the median.
 B. NO OVERLAP: one position at a time per mint. Overlap pooling inflated a median by +6.5pp.
 C. MINT-EQUAL WEIGHTING: never pool by trade. Pooling moved a cell by 5.3pp (+0.47 -> -4.81%)
    by silently re-weighting toward long-lived (surviving) coins.
 D. Charge dropouts at -30%, -50% AND -100%; report the resolution rate beside every horizon.
 E. Toll 1.14% (direct routing). Report a 2.5% sensitivity -- the on-chain decode says the true
    all-in venue cost is ~2.5% round trip (95 bps/side protocol + 132-155 bps tips/rent).

## Benchmark (canonical, measured n=50,177 k=453 res 95.8%)
Random-bar 15m net: -2.92% at -30% dropout charge, -3.75% at -50%, -5.83% at -100%.
Beat THAT, not zero.

## PASS (frozen, all four required)
 1. mint-equal-weighted mean net > +1.14% ABOVE the matched control
 2. no-overlap book
 3. replicated in >= 3 DISJOINT 48h windows
 4. cluster-bootstrapped BY SESSION with ci_low > 0
Anything less is decision-support at most, never a bot.

## Declared kill-risks
 1. Boosts are BOUGHT BY THE DEPLOYER at the top, making them an exit signal, not an entry one.
    This is the most likely outcome and the matched control is what will reveal it.
 2. Selection: boosted coins are already-moving coins. Only the matched control separates these.
 3. Latency: by the time a boost appears in the API, the move is done.
 4. Boost volume may be too low to reach adequate power in a week.
