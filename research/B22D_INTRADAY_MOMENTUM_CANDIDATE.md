# B22D — market intraday momentum: the first candidate whose costs are structurally small

**Why this is different from everything else in this programme.** Four domains have now produced the
same result: the gross edge is real and the friction eats it. Memecoins (95 bps toll), Binance
practitioners (19 of 20 lost with fees, 12 of 20 profitable without), MNQ futures (gross ceiling
0.07–1.50 points against 2.0 points of friction), and individual US equities (per-trade edge ~1.6¢/share
against 7–46 bps of measured retail execution cost).

**This candidate is the first one where the cost is not the binding constraint, and the reason is
structural rather than fortunate.**

**Status.** External literature. **Nothing here has been measured by us.** The test that would make it
ours is specified in §6 and has not been run.

---

## 1. The rule

Gao, Han, Li & Zhou, *Market Intraday Momentum*, **Journal of Financial Economics 129(2), 2018,
394–414**. SPY, 1993–2013, high-frequency data.

> Let `r1` = the return from the previous day's close to **10:00 ET** (the first half-hour).
> At **15:30 ET**, go **long** SPY if `r1 > 0`, **short** if `r1 < 0`.
> Exit at the **16:00 close**.

That is the entire rule. One trade per day. Thirty minutes of exposure.

**It has zero free parameters.** Not a threshold, not a lookback, not a stop — just the *sign* of a
return. This matters more than any performance number in this document: **a rule with nothing to tune
cannot be overfit.** Every negative result in this programme has been contaminated by the question
"how many things did you try before this one worked?" Here the answer is structurally one.

## 2. Reported performance

| strategy | ann. return | ann. vol | Sharpe | success rate |
|---|---|---|---|---|
| **timing on sign(r1)** | **6.67%** | 6.19% | **1.08** | 54.37% |
| SPY buy & hold | 6.04% | 20.57% | 0.29 | 50.42% |
| always long, last half-hour only | **−0.74%** | — | negative | 50.93% |

**The third row is the most important one in the table.** Being long during the last half-hour
*unconditionally* loses money. So the timing is doing real work — the strategy is not a disguised
long position harvesting the equity premium. That is exactly the check that killed several of our own
earlier results, and this one passes it.

**Net of transaction costs**, measured by the authors rather than assumed:

| period | before costs | **after costs** |
|---|---|---|
| post-decimalisation (2001+) | 6.93% | **4.46%** |
| post-2005 | 7.96% | **6.52%** |

At ~6.1% volatility, the post-2005 net figure is a **Sharpe of roughly 1.07**.

Also reported: significant **out of sample**; present in **ten other actively traded ETFs**; stronger
on high-volatility days, high-volume days, recession days and major macro-news days.

## 3. Why the cost is structurally small — the actual mechanism

Two independent reasons, and neither depends on our being clever:

**The exit is free.** SPY's closing price is set in the **closing auction**, a single market-clearing
price for all buys and sells. A market-on-close order pays **no bid-ask spread**. The authors state
this directly: *"Since the closing of the SPY is uniquely traded at the market clearing price for all
the buys and sells, there will be no bid/ask spread effect for the price at 4:00pm."* Half the
round-trip cost is eliminated by market design.

**The entry is in the cheapest instrument that exists.** The authors measure SPY's proportional spread
as stabilising at **~1.2 basis points after 2005**. They charge the full half-spread on entry, taken
conservatively from the ask for longs and the bid for shorts. 252 entries × ~0.6 bps ≈ **1.5 pp per
year**, which is exactly the haircut they report.

Set that against what killed everything else:

| venue | round-trip friction |
|---|---|
| pump.fun | ~9,500 bps |
| individual US equities, retail market order | 7–46 bps |
| MNQ futures, 5-min bars | 2.0 points vs a 0.07–1.50 point gross ceiling |
| **SPY, this rule** | **~0.6 bps, entry only** |

**That is a factor of roughly 10 to 15,000 depending on which comparison you take.** A signal far too
weak to survive anywhere else survives here — not because it is stronger, but because almost nothing
is taken from it.

**A third structural advantage:** the position is flat overnight, so Reg T intraday margin (4×) is
available and **costs no overnight interest**. At 6.1% volatility the unlevered strategy is far below
SPY's 20.6%; the leverage headroom is real and cheap. Leverage does not change the Sharpe — it changes
whether the Sharpe is worth collecting.

## 4. Why it should exist at all

Two mechanisms, one of them with its own top-journal paper:

**Infrequent rebalancing** — Bogousslavsky, *Infrequent Rebalancing, Return Autocorrelation, and
Seasonality*, **Journal of Finance 71(6), 2016**. Institutions with slow-moving capital rebalance at
the open and at the close rather than continuously. Trading in the last half-hour in the same
direction as the first mechanically produces the pattern.

**Late-informed traders** — participants who process the morning's information slowly trade it in the
last half-hour, when liquidity is highest and overnight risk can be avoided.

This matters because it is the opposite of a mined pattern. It predicts *where* the effect should be
strongest — high-volume, high-volatility, macro-news days — and that is where the paper finds it.

## 5. What would kill it, stated before testing

**Post-publication decay is the live risk.** McLean & Pontiff, *Does Academic Research Destroy Stock
Return Predictability?*, **Journal of Finance 71(1), 2016**: portfolio returns are **26% lower out of
sample and 58% lower post-publication**, with the decay largest for predictors that had the highest
in-sample returns.

This paper's data ends in **2013** and it published in **2018**. It is now 2026 — twelve years past
the data, eight past publication.

| scenario | net return | Sharpe |
|---|---|---|
| no decay | ~6.5% | ~1.07 |
| McLean–Pontiff decay (−58%) | ~2.7% | ~0.45 |

**A power calculation, done before the test rather than after.** Over twelve out-of-sample years
(~3,000 trading days), a true Sharpe of 1.07 gives t ≈ 3.7 — decisive. A true Sharpe of 0.45 gives
**t ≈ 1.56 — not significant.**

> **So the test can prove the effect is intact, and it can prove it is dead. It cannot certify a
> decayed-but-alive version.** That is the same wall we hit before: at these sample sizes you can rank
> shapes but not certify levels. Knowing it now stops us reading an ambiguous result as a positive one.

**Secondary concern — the commercial replication.** Zarattini, Aziz & Barbon (SSRN 4824172, May 2024)
report an *enhanced* version at 19.6% annualised, Sharpe 1.33, 2007 to early 2024, and their sample
covers the post-publication years. Two reasons to discount it rather than lean on it: it is the **same
team as the ORB paper** in [B22A](B22A_EQUITY_DAYTRADING_PIVOT.md), one of whom sells day-trading
education and runs a prop firm; and their stated friction is **$0.0035/share commission plus
$0.001/share slippage**, where the SPY **half-spread alone is ~$0.005/share** — a five-fold
understatement of the entry cost, on a strategy that trades far more often than Gao's one-a-day. Their
result is a reason to run the test, not a substitute for it.

## 6. The decisive test

> Run **Gao's original, unmodified rule** on SPY from **1 Jan 2014** (the day after their sample ends)
> to the present. Twelve years fully out of sample, eight of them post-publication. Charge the full
> half-spread on entry and nothing on the MOC exit. Report the t-statistic against zero, the Sharpe,
> and the year-by-year breakdown.

Properties that make this the right test:

- **Zero parameters**, so there is no search and no multiple-testing exposure. The deflated Sharpe
  haircut at N=1 trial is negligible — unlike every prior candidate in this programme.
- **Tiny data.** Four prices per day: prior close, 10:00, 15:30, 16:00. ~3,000 days.
- **The falsifier is pre-committed** by §5's power calculation, so an ambiguous result gets read as
  ambiguous.
- **Year-by-year is the real diagnostic**, not the aggregate — the Mesfin study's most common failure
  mode was one strong year masking flat ones, and it is the failure mode our own crash-filter result
  died of (9 of 10 lengths lost).

Also worth running at no extra cost: the same rule on the ten other ETFs the paper names, which turns
one test into a cross-sectional consistency check that no amount of curve-fitting could fake.

**Blocked on the same Alpaca key as [B22B](B22B_SLIPPAGE_PREREGISTRATION.json).** One credential
unlocks both tests.

## 7. The finding that should change how we think about day trading generally

Lou, Polk & Skouras, *A Tug of War: Overnight Versus Intraday Expected Returns*, **JFE 2019**, and a
literature going back to the early 1990s: **essentially the entire long-run equity risk premium is
earned overnight, between the close and the next open. Intraday returns are on average slightly
negative.**

Gao et al.'s own "always long the last half-hour" row (**−0.74%/yr**) is an independent instance of
exactly this.

> **A day trader is flat overnight by definition, and therefore operates entirely inside the window
> where the market's expected return is negative.** That is a measured decomposition, not an opinion,
> and it is a mechanical explanation for why ~80% of day traders lose: they are fighting a structural
> headwind before skill enters the picture.

The implication is not "don't day trade." It is sharper than that: **an intraday strategy must have a
real edge, because it cannot borrow one from the market's drift the way buy-and-hold can.** Intraday
momentum qualifies precisely because its timing component is what produces the return — the
unconditional version loses money.

---

*Every number above is someone else's measurement, cited so it can be checked. This programme has
measured nothing in equities. See [FINDINGS.md](FINDINGS.md) for what we have actually established.*
