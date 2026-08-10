# The ceiling: what perfect timing would have earned

**Status.** POST-HOC DESCRIPTIVE MEASUREMENT. **AMENDED TWICE — read the amendment history at the
bottom before quoting any figure.** The table below is the third version; the first two were both
wrong, in opposite directions, and both were reported to the project owner before being corrected.

**Original status line:** POST-HOC DESCRIPTIVE MEASUREMENT on the evaluation window, computed after B19D, B19F
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


---

# AMENDMENT 2 — the unsellable positions were mispriced, and the ceiling is positive

Found by the peer seat on being handed this note to attack, and reproduced here to the lamport
before being accepted.

## The error

Every figure above scores a position with no external buyer as a **total loss of the full outlay**,
−103,394,280 lamports. That is wrong, and the reason is a convention being used outside its scope.

`b10a.price_exit` prices a sale against the **observed** reserves, and its docstring says why:
pricing an exit against liquidity our own entry supplied would let the position pay for itself. For
the *studies* that is exactly right — B19D, B19F and B19G ask whether **external demand** pays you
out, and the answer must not be contaminated by our own deposit.

For a **wealth ceiling** it is the wrong measurement, because it answers a wealth question with a
demand measurement. On a bonding curve your `quote_in` sits in the curve's real reserves until
graduation. A sell-back into your own deposit is **always payable by arithmetic** —
`quote_out <= quote_in <= real_quote + quote_in`, no counterparty required. Verified directly on a
launch-fresh curve holding zero real quote: the observed-state exit is refused, and the sell-back
into the post-buy state prices at exactly **−4,749,281 lamports (−4.75%)**, the round-trip toll.

A curve nobody ever buys is not −103%. It is minus the toll.

## The corrected ceiling — fresh window, achievable entry, one pass

| | value |
|---|---|
| positions | 2,821 |
| **floor binds** (best exit ever = withdrawing your own deposit) | **1,588 — 56%** |
| min / p25 / **median** | −4,749,281 (**−0.047x**) |
| p75 | +15,267,736 (+0.153x) |
| p90 | +83,625,677 (+0.836x) |
| max | +1,155,777,450 (+11.56x) |
| **mean** | **+29,646,062 (+0.2965x)** |
| profitable | 35.9% |

Reproduced independently from the peer's figures: mean, median, profitable share and the floor
count all agree (1,588 vs their 1,587, one boundary case).

## What it means

1. **"Even omniscient timing loses" is FALSE for the mean and TRUE for the median.** Perfect
   foresight earns +0.30x mean. The median position's best possible outcome is getting its own
   money back minus the toll, because the median launch never offers a better exit than your own
   deposit.
2. **B19F's result lands harder, not softer.** Its best rule returned −0.05x; the floored median
   ceiling is −0.047x. **At the median there was nothing left to capture** — the rules were already
   at the ceiling, which is why eight of them failed by near-identical margins.
3. **Therefore the tradeable question is not exit timing. It is SELECTION.** All remaining value
   sits in the ~36% of curves that ever offer better than your deposit back. Identifying
   tail-membership *at entry* is the only place the money can be. B19D's five signals were tested
   against fixed-horizon outcomes, not against tail-membership, which is a different target.

## The caveat that must travel with the +0.30x

**The floor is valid inside a ceiling and does not convert into a bounded-loss strategy.** Perfect
foresight knows which curves die and sells back *immediately*, capping each loss at the toll. A real
strategy that waits does not keep that floor: earlier buyers can exit into your deposit while you
hold, and the sell-back then returns less. **The +0.30x mean may not be quoted without this
sentence.**

A second unknown bounds it further: entry priority. Entering at the raw launch state gives a median
of +0.027x on the burned corpus; entering at the state in force at t0+1, where everyone beats you,
gives −0.062x. **The sign of the median lives inside sub-slot execution priority**, which this
project has always refused to invent parameters for and cannot measure offline.

## Amendment history

- **v1** reported mean +0.643x, median +0.18x, 63.1% profitable. Wrong: it entered at `path[0]`,
  the CreateEvent — the **launch price**, in the launch slot — which B19D refuses outright as
  `N_SAME_SLOT_UNPROVABLE`. In 934 of 1,136 burned curves the "exit" was in the entry's own slot.
- **v2** reported mean −0.045x, median −0.057x. The entry was fixed, but unsellable positions were
  scored as total losses. Reported to the owner as "even perfect timing loses".
- **v3**, above. Both previous versions were reported to the owner before correction; v1 in the
  direction the owner hoped for, v2 against it. Neither was caught by me.
