# age<2h / 15m hold — the ONE untested cell. PRE-REGISTRATION
Frozen 2026-09-03 after the exit-discipline KILL, BEFORE any multi-session data exists.

## Why this one and nothing else
The exit sweep ran on a MOMENTUM-TRIGGER entry (+30% in 15m). The motivating observation
(positive median, negative mean) came from the SNAPSHOT universe. Those are two different
conditional distributions and they were never crossed. Everything else is dead:
 - 0 of 35 preregistered exit arms, 0 of 272 grid exit rules, 0 of 30 entry cells, 0 of ~20 segments
 - momentum entry is NEGATIVE alpha: -3.6 to -12.2pp of gross vs a random minute in the same names
 - exit discipline falsified 3 ways; 65.1% of graduates have a single traded minute of <=-90%
   (an LP pull), and 34-67% of stop fires are UNEXITABLE. A stop is a hope, not a fill.

## The one honest candidate
age<2h at snapshot, 15-minute hold, equal-weight across names in the cell, direct-routed.
Measured once: +1.70% gross dropout-charged, +0.56% net at the measured 1.14% direct toll,
CI spanning zero, on THREE independent blocks inside ONE uniformly-positive session.
Prior probability this is an artifact, stated in advance: 75-85%.

## Toll (measured on-chain, not assumed)
PumpSwap venue fee decoded from 41 Buy/SellEvent records over 10 pools: 30 bps/side median
(lp 20 + protocol 5 + creator 5). Round trip at $60: terminal 3.57-4.19%, DIRECT 1.14%.
USE 1.14%. Sensitivity REQUIRED at 2.50% (the value if pump.fun's published tier table is
right and the chain decode is wrong) and at 3.00%.
Read fee bps from the event at runtime. NEVER hardcode.

## The gate — session is the cluster unit, not the minute
More minutes inside one session buy NOTHING. The same unconditional arm measured -1.68% gross
in one 39-min session and +2.33% in the adjacent one: a 4.01pp session-to-session swing that
alone exceeds every effect found. Required: >= 5 INDEPENDENT sessions on >= 5 SEPARATE DAYS.

PASS (frozen): dropout-charged net mean > 0 AND net median > 0 AND cluster-bootstrap-BY-SESSION
ci_low > 0, across >=5 sessions, at the 1.14% toll, AND still net>0 at the 2.50% sensitivity.

## Dropouts are charged, never dropped
A mint present at t and absent at t+15m is NOT a non-event. Vanished mints' last observed 3-min
move averages -19.21%; survivors' -0.03%. Charge every dropout at BOTH -30% and -50% and report
both. Resolved-only reporting is how the two best-looking segments turned out to be artifacts
(73.6% and 71.1% resolution vs 94-98% elsewhere).

## Forbidden, because each has already manufactured a false pass here
 1. Conditioning on bar count / trade count / continued listing. The '>=60 bars' filter flips
    M=1/H=15 from ci_low -21.4% (fail) to ci_low +7.1% (clean pass). It is a survivorship filter.
 2. Reporting resolved-only returns.
 3. Treating overlapping 3-min snapshots inside one session as independent clusters.
 4. Searching segments post hoc without correcting for the count searched.

## Second gate before ANY real money
20 live $60 round trips measuring realized slippage against the printed mark. Every number here
is mark-to-snapshot and assumes you can exit at the print — the exact assumption that fails for
a coin dropping off the trending list.
