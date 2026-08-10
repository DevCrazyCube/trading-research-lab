# The ceiling: what perfect timing would have earned

**Status.** POST-HOC DESCRIPTIVE MEASUREMENT on the evaluation window, computed after B19D, B19F
and B19G were spent and read. It is **not** a preregistered result, it has no frozen document, no
pass and no ledger entry, and no strategy may be justified by it. It exists to answer one question
the three studies did not: *is the failure a shortage of opportunity, or a shortage of skill?*

**Why it was computed.** The owner objected that launches visibly rise before they die, so a bot
should be able to capture the rise. The three studies measured what specific *rules* achieved. None
measured what was *available*. Those are different quantities and only the second answers the
objection.

## Method

Buy 0.1 SOL at each curve's first observation. Sell at the single best moment in that curve's
entire observed life — **with knowledge of the future**. Full costs and real reserve constraints
enforced by the same kernel the studies used: protocol fees, rent, network fees, slippage, and the
refusal to price proceeds the observed reserves cannot pay.

Population: every curve with a decodable fee schedule and a path (3,154 of 3,932). **Curves that
could never be sold at any point are counted as a total loss of the full outlay**, not excluded —
797 curves are in that state and excluding them would flatter the result by roughly a third.

## The ceiling

| | lamports | as a multiple of the position |
|---|---|---|
| min | −103,394,280 | −1.03x |
| p10 | −103,394,280 | −1.03x |
| p25 | −103,394,280 | −1.03x |
| **median** | **+18,041,206** | **+0.18x** |
| p75 | +94,109,341 | +0.94x |
| p90 | +231,820,225 | +2.32x |
| max | +1,324,701,585 | +13.25x |

**63.1% profitable. Mean +0.643x per trade.** A quarter of curves are total losses.

## What this changes

| | median outcome |
|---|---|
| B19D, best signal, primary cell | −26,928,909 (−0.27x) |
| B19F, best exit rule | −5,155,732 (−0.05x) |
| **perfect foresight** | **+18,041,206 (+0.18x)** |

The opportunity is real and large. Every rule tested captured **none** of it. The entire distance
between +64% mean and −5% median is **timing and selection**, not costs and not liquidity.

**This corrects an overstatement.** The B19G finding — median external capacity of 20 lamports —
was reported, including to the project owner, as "there was nothing to trade against". That
conclusion does not follow. B19G measures capacity at a *fixed* early coordinate: entry at
`t0 + delay`, exit at a fixed horizon. Curves **accumulate** real reserves over their life, and at
their best moment many hold enough to exit into. Both facts are true and they answer different
questions:

- at a fixed early horizon, the median book is 20 lamports — B19G, correct as measured;
- across a curve's whole life, the median best exit is worth +0.18x — measured here.

The venue is not untradeable. **We failed to find the rule.** Those diagnoses call for different
next steps, and the second is the honest one.

## What it does NOT say

- **Perfect foresight is unachievable by construction.** This is a ceiling, not a forecast. No
  strategy can reach it and none should be sized against it.
- It does not show a profitable rule exists. It shows the ceiling is high enough that one is not
  arithmetically excluded — which is strictly weaker, and is the whole of the claim.
- The gap between this ceiling and the best *achievable* rule is unmeasured. Every rule tried so
  far sits below zero, and five signals and eight exit rules is a small search.
- 25% of curves are total losses. Any real strategy must survive them, and a rule that improves the
  median by taking on tail risk may be worse than the median suggests.
- This is post-hoc on a window whose outcomes were already read, so it is exposed to every bias a
  preregistration exists to prevent. It is a diagnostic, and any strategy it suggests needs its own
  frozen document before it goes anywhere near data.
- The peak-vs-fixed-horizon distinction cuts both ways: exiting near the peak requires identifying
  the peak, and B19F's drawdown rules — the family designed to do exactly that — were the *worst*
  performers in the study.
