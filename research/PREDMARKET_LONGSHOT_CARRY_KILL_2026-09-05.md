# PREDMARKET — the longshot tail is structurally unshortable (2026-09-05, CHUNK D)

**Status: THESIS KILLED, ARITHMETICALLY, BEFORE ANY VIEW WAS TAKEN.** No estimate frozen;
logged as an abstention in `research/trading_bot/predmarket/PREDMARKET_PREREGISTRATION_LOG.jsonl`.

## 1. Why this thesis was the natural next one

Two mechanical edge sources are already dead in this instrument:
* cross-market **coherence violations** — screened 2026-09-02, zero exploitable, five
  false positives catalogued (traps a–e);
* **family underround** — screened 2026-09-03, one genuine candidate (Balance of Power,
  sum(ask)=0.993), killed on a depth-walk + carry (net ≈ −$20 at max executable size).

That leaves the one remaining non-news, non-memory-contaminated edge in a prediction book:
the **favourite–longshot bias**. It needs no post-cutoff fact — the claim is only that
2-tenths-of-a-cent legs like *"Will Kim Kardashian win the 2028 Democratic presidential
nomination?"* are worth less than they are priced. That claim is almost certainly TRUE.
It is also worthless, and this tick shows why in one line of arithmetic.

## 2. The general rule

Shorting YES at bid `b` on a binary market posts `1 − b` as collateral and receives `b`.
If it resolves NO, the return over the holding period `T` (years to close) is `b / (1 − b)`.
The collateral is dead money for the whole of `T`. So the short beats simply holding cash iff

> **b / (1 − b)  >  r · T**    ⇔    **b  >  rT / (1 + rT)**

with `r` = the risk-free rate this programme already measured in T32, **3.71%**.

| holding period T | minimum bid for the NO side to beat cash |
|---|---|
| 0.04 y (2 weeks) | 0.15c |
| 0.25 y | 0.92c |
| 0.50 y | 1.82c |
| 1.00 y | 3.58c |
| 1.50 y | 5.27c |
| **2.40 y (a 2028 market)** | **8.18c** |
| 3.00 y | 10.02c |

**Read that last rows carefully: on a 2028-dated market, any leg priced below ~8c is
unshortable-for-profit even if its true probability is exactly zero.** Being completely,
provably right earns less than a T-bill. No amount of longshot bias can be harvested,
because the bias lives entirely *below* the carry threshold.

## 3. The concrete measurement

The 2028 Democratic-nomination field has **48 legs**; **32 of them bid ≤ 0.6c**
(MrBeast, Kim Kardashian, LeBron James, Oprah, Dwayne Johnson, Hunter Biden, …).
Horizon **T = 2.17 y**, breakeven bid **7.46c** — every one of the 32 is an order of
magnitude below it. Shorting the whole tail, at $100 notional per leg:

| | |
|---|---|
| premium received (sum of bids) | **+$6.20** |
| collateral locked | **$3,194** |
| carry at 3.71% over 2.17 y | **−$257.58** |
| **net, if all 32 resolve NO (i.e. we are 100% right)** | **−$251.38** |

A **guaranteed −7.9% on capital for a perfect forecast.** The trade loses by ~40x.
This is the programme's standard verdict in its purest form: *distance from zero* is what
kills it, and here the edge is not merely small, it is the wrong sign after carry.

## 4. Scope of the kill — how much of the book this removes

Applying `b > rT/(1+rT)` to the full pull (**2,825** selectable two-sided markets):
**673 (23.8%) are structurally sub-cash on the NO side.** Nearly a quarter of the
political book cannot be profitably shorted at any accuracy. Those legs are not
mispriced *to us*: at a 0.1c tick, 0.2c is the market's floor for "approximately zero",
and the floor sits below the carry threshold, so nobody can arbitrage it away. **The
longshot bias on long-dated markets is not an inefficiency, it is a structural artifact
of the tick size meeting the discount rate.**

## 5. Trap-catalogue entry (g)

> **A longshot short is a carry trade in disguise.** Before writing down any "this is
> obviously overpriced at 0.3c" view, compute `rT/(1+rT)`. If the bid is below it, the
> position is dominated by cash no matter how right the view is. Correctness is not the
> binding constraint; the collateral clock is.

Corollary, and it is the useful one: **this instrument should confine itself to
near-dated markets.** At T = 2 weeks the threshold is 0.15c — essentially the whole book
is live — and near-dated markets are also the ones that generate calibration evidence
inside this programme's horizon. The two constraints point the same way.

## 6. Ledger state (verified this tick)

`status`: **resolved 0/50 → NO VERDICT, kill ALIVE, open 71.** The log holds **102 rows =
71 estimates + 31 abstentions.** Horizon composition of the 71 estimates:
**17 close ≤ 30 d, 19 at 31–90 d, 35 at 91–180 d** — i.e. **36 of 71 settle inside 90 days**,
so a real Brier verdict is reachable this autumn without any new freezing.

The **first settlement is 2026-09-06 (Sachsen-Anhalt, `2244513`, q_agent 0.180 vs market
0.255)** — tomorrow. The resolver's real data path was verified 12/12 on live resolved
markets by the 09-03 tick, so nothing is blocking it.

**Nothing needs to be added to this ledger. It needs to be left alone and allowed to
settle** — the same discipline the BASKET1 clock lock exists to enforce.
