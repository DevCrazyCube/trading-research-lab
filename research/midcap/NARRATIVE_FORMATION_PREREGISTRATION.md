# Narrative formation as a LEADING signal — PRE-REGISTRATION
Frozen 2026-09-04 at n=228 young coins (underpowered on purpose: the gate is set before the data).

## The owner's insight, which is the reason this exists
He held MEME at $137k mcap BEFORE its 641x god candle and sold. His point: "we have to be there
before the narrative is visible -- I was, I just didn't know it was a narrative."

That is a different question from the one already killed. NARRATIVE_THEME_KILL_20260904.md shows an
OBSERVABLE theme is worse than useless (MEMESTOCK -96.42% at 6h, median -100%). It is lagging: the
theme is visible BECAUSE the coin already ran. This tests whether narrative FORMATION is detectable
before any price move.

## Why this is the first leading candidate in the programme
Everything killed so far is observed after the fact: momentum, ATH distance, visible themes, paid
boosts, breadth. LAUNCH RATE is observable at CREATION, before a price exists. When a narrative
forms, multiple coins on that theme appear within hours of each other. That clustering is knowable
at t=0.

## Signal (frozen)
Themes are DATA-DRIVEN, never a hand-written regex (the live meta rotates faster than any regex --
tonight's was fake financial institutions: fund/oil/world/trust/united/global/asset, which no
prewritten pattern caught).
  words(name+symbol), drop a fixed stoplist, keep tokens shared by >= 4 distinct coins
  wave_score(coin) = number of OTHER coins sharing >=1 theme word, created in the 6h BEFORE it
Buckets: 0 / 1 / 2-3 / 4-7 / 8+.

## Universe
Coins FIRST SEEN under $300k market cap -- the owner's actual entry situation. Not the whole
universe: the question is about coins that have not moved yet.

## Outcome
SIMPLE return from first sighting to +6h (and +1h, +24h reported). Dropouts charged -100%.
Toll 2.5%. Cluster-bootstrap by mint. Report mean AND median AND peak/entry multiple AND the
fraction exceeding 5x -- the tail fraction is the thing that would actually pay.

## Harness contract (mandatory; each measured, each violated at least once already)
 A. enter at the next REAL observation after the signal, never the signal's own print
    (signal-bar entry inflated a random-bar mean by +37.25pp and is INVISIBLE in the median)
 B. one position per mint, no overlap (+6.5pp inflation)
 C. mint-equal weighting for every headline (+5.3pp inflation)
 D. dropouts charged -30/-50/-100%, resolution rate reported beside each horizon
 E. never condition on bar/trade count or continued listing (it INVERTS results here)

## POWER — computed BEFORE reading any effect
~114 young coins/day. Need >=60 per bucket for a weak read (~2.1 days), >=150 for a real one
(~5.3 days). DO NOT READ THE EFFECT before >=60/bucket in at least 3 buckets.

## PASS (frozen)
Monotone increase in mean SIMPLE return across wave buckets, AND the top bucket's
cluster-bootstrap ci_low > the bucket-0 mean, AND median > bucket-0 median, AND it replicates in
>= 3 disjoint 24h windows (narratives are daily events; one window is one narrative).

## Declared kill-risks
 1. A wave of same-theme launches is COPYCATS chasing a coin that already ran -- i.e. still lagging,
    just at one remove. The 6h lookback must be checked against whether the ORIGINAL theme coin had
    already pumped at the time the copycats launched. THIS IS THE MOST LIKELY OUTCOME.
 2. Deployers spam a theme precisely because it is spent.
 3. Current thin data already leans wrong: wave 2-3 scored -89.24% vs wave 0 at -69.97% (n=19 vs 143).
 4. Theme words from a 24h window may be coin-specific noise (pons/wofi/rst are single-coin names,
    not themes) -- require >=4 DISTINCT creators, not just 4 coins.
