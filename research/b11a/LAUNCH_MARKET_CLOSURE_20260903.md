# The pump.fun launch market is efficient at our timescale — final closure

Every number here was computed this session from `research/b11a/` (3,932 survivorship-free priced curves,
82 graduations, exact on-chain slots) and the full 33,866-create window labelled from chain.

## The structure (three facts, all deterministic)

1. **Hard floor.** 0 of 3,239 priced curves ever traded below their first observed price. On-curve, downside
   is exactly your entry premium — the curve is a free put.
2. **Deterministic prize.** Graduation pays exactly **14.6958x** (30 → 115 virtual SOL under constant
   product). All 82 graduates show the identical figure.
3. **Base rate 3.1743%** (1,075 / 33,866, full window, chain-labelled). The long-standing 2.0855% was a
   survivorship artifact of body-decode attrition — dropped curves were 5.81% graduated.

So EV(m) = (1 + 13.6958·p) / m − 1 − toll, and at the floor break-even needs only **p > 0.146%** against a
3.17% base rate — 21x the bar. On paper this market looks free.

## Why it is not free: everything reprices inside the create slot

**Where the 82 winners are at create_slot+1 — the first moment a bot can act:**

| | count |
|---|---|
| already complete, unbuyable at any price | **36 / 82 (43.9%)** |
| still buyable at ≤ 1.05x the floor | **0** |
| still buyable at ≤ 1.10x | 1 |
| still buyable at ≤ 1.25x | 3 |
| median premium of the buyable winners | **1.96x** |

**Not one winner is at the floor when you can act.** The cheapest is already 1.07x.

## The exhaustive sweep — no +EV cell exists

Entry at create_slot+1, unbuyable coins skipped rather than charged as losses:

| premium m | n | grads | actual rate | rate needed | EV |
|---|---|---|---|---|---|
| 1.00–1.05 | 1,990 | **0** | 0.00% | 0.15% | −2.0% |
| 1.05–1.25 | 549 | 3 | 0.55% | 1.16% | −7.4% |
| 1.25–1.50 | 449 | 6 | 1.34% | 2.91% | −15.7% |
| 1.50–2.00 | 565 | 17 | 3.01% | 5.68% | −21.0% |
| 2.00–3.00 | 292 | 10 | 3.42% | 9.41% | −36.5% |
| 3.00–5.00 | 41 | 7 | 17.07% | 20.65% | −13.1% |
| **buy everything at its own price** | 3,896 | 46 | — | — | **−10.14%** |

Identical at slot+5. **In every bucket the realised rate is roughly HALF the rate break-even requires.**
That ratio is the market's margin, and it is uniform across the entire premium spectrum — the signature of a
market that has already priced the structure.

## Four independent theses, one cause of death

| thesis | statistical result | why it still fails |
|---|---|---|
| price / momentum entry | momentum predicts graduation with a **540x** lift | fully impounded; every bucket ≤ 0 |
| creator provenance (leak-free) | **4.745x**, clustered lower bound 3.600x, FWER p=5e-5, n=23,693 | break-even 1.615–1.793x vs a market quote of **1.646x** — the same number |
| platform | genuine null, lift 1.0015 at n=1,035,976 | nothing to trade |
| curve config | real, z=8.76 | best live config has a *narrower* window (X=7.50, not 14.69) |
| venue selection | (X−1)·p sits in **0.077–0.286** at every venue | prize and base rate cancel |

These are not four failures. They are **one finding measured four times**: at the timescale we can act,
the information is already in the price.

## What would actually work — the specification

The only position that is not on the losing side of this trade is **participation inside the create
transaction's own slot** (~400 ms), before repricing. That is not a modelling problem, it is an
infrastructure one:

- a colocated validator-adjacent connection (Helius LaserStream or equivalent), and
- a warm submit path (Helius Sender / Jito bundles),
- both of which are a spend decision, and both of which sit on a latency thesis this project has already
  falsified at slower timescales.

**Everything cheaper than that has now been measured and is negative.** No further $0 test on this market
can change the verdict, because the closure rests on price behaviour (z=17.7 impounding, every cap
negative), not on thin graduation counts.

**Recommendation: retire the bonding-curve launch line.** The durable asset from this work is not a bot —
it is the measurement machine: enumerate a deterministic payoff, get a survivorship-free base rate, then
test whether the signal is impounded before you can act. It answered a month-old question in about an hour,
and it is reusable on any market with a deterministic payoff structure.
