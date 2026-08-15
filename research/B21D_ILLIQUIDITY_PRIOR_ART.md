# B21D — our unexitability label has a name, and it is twenty years old

**The question.** B20B's contribution was claimed to be the *label* — measuring unexitability rather
than price collapse. Before claiming novelty, does traditional finance already have this? It does,
under two names, and one of them describes our construct precisely.

**The answer in one line:** our label independently reinvented **Liu (2006)'s "lock-in risk"**, and the
artifact that broke our first label design is the exact quantity **Lesmond, Ogden & Trzcinka (1999)**
use as their measure.

---

## 1. The standard estimator does not work here, and the literature knows why

**Amihud (2002)** is the field's default illiquidity measure — |return| ÷ dollar volume, used in over
120 papers in the top three finance journals between 2009 and 2015 alone. It measures **price impact
per unit of volume**.

**It is undefined when volume is zero.** The literature is explicit: *"the average spread and Amihud's
ratio cannot be calculated in non-trading days."* And non-trading is not a corner case for thin
assets — 21.6% of NYSE/AMEX and 22.9% of NASDAQ days in the smallest capitalisation decile have zero
volume.

**This is our problem exactly.** On a bonding curve the price only moves when someone trades, so a
token nobody touches has no return and no volume. Amihud would be undefined for precisely the
population we most need to classify.

## 2. Liu (2006) named what we measured

**LM12: the standardized turnover-adjusted number of zero daily trading volumes over the prior 252
days.** Its stated purpose:

> *"The zero-trading-volume days specifically capture **'lock-in risk,' reflecting the danger that
> the stock cannot be sold in extreme cases.**"*

**That is our label.** We defined a token as unexitable when a 0.1 SOL position could not recover half
its cost from external money at any point after the decision. Liu defines illiquidity by counting the
days on which selling was not possible. Same construct, different venue, twenty years apart.

The literature also states directly why Liu is preferred over Amihud for our situation: it is *"more
appropriate to assess liquidity risk than average spread and illiquidity ratio of Amihud (2002) when
the sample includes shares with high trading activity and shares with low trading activity"* —
because it *"includes the effect of non-trading"* rather than being undefined by it.

## 3. LOT (1999) is the sharper embarrassment

**Lesmond, Ogden & Trzcinka (1999)** measure illiquidity as the **proportion of zero-RETURN days**, on
the reasoning:

> *"If transactions costs are high, then investors will not trade on a given day, and so the stock
> return will be zero."*

**A flat price is their signal of illiquidity.** In B20B's first label design, a flat price was read as
*"the token held its value"* — and that inversion is what broke it. We rediscovered LOT's premise as a
bug before recognising it as a measure.

Recorded because the lesson generalises: **when a measurement artifact keeps appearing, check whether
someone else has already made it the measurement.**

## 4. The feature is prior art too — in two literatures

Concentration → illiquidity is established in equities, not just crypto:

> *"An increase in the concentration of shareholding increases information asymmetry, which leads to
> reduced liquidity"* — with a substantial literature: Heflin & Shaw (2000), Gaspar & Massa (2007),
> Rubin (2007), Brockman, Chung & Yan (2009), Agarwal (2010).

And the effect is *stronger where information asymmetry is worse* — smaller firms, less analyst
coverage. Combined with MemeTrans's crypto finding (17pp separation on early-buyer concentration),
**both halves of B20B — feature and label — have prior art.**

## 5. What is actually ours, stated at the right size

Not the feature. Not the label construct. **The venue, the mechanism, and the population.**

| | traditional finance | pump.fun bonding curve |
|---|---|---|
| relationship | concentration → illiquidity | concentration → unexitability |
| **mechanism** | **adverse selection**: informed holders create information asymmetry, market makers widen spreads, liquidity falls | **absence of a counterparty**: high concentration means *nobody else bought*, so there is no external money to sell into |
| market state | exists, but is expensive | **does not exist at all** |
| measure | LM12 / LOT, counting non-trading days | external reserve never reaching half the position |

**The relationship survives a change of mechanism**, and that is the finding worth stating. In
equities, concentration makes trading *costly* through informed-trader risk. On a bonding curve there
are no market makers to widen a spread — concentration means the counterparty is *mechanically
absent*. Same direction, entirely different cause.

**And the population remains genuinely unstudied**: every published Solana rug-pull dataset excludes
bonding-curve-only tokens by construction (`B21C`), which is ~98% of what we measured.

## 6. What this changes in how we describe B20B

**Weaker claim, better grounded.** Not *"we discovered that concentration predicts unexitability"* but:

> *"Concentration→illiquidity (Heflin & Shaw 2000 onward) and zero-trading lock-in risk (Liu 2006)
> both hold on pump.fun bonding curves, where the mechanism is mechanical counterparty absence rather
> than adverse selection, on a population every existing rug-pull dataset excludes."*

**And a practical consequence:** if we ever build a v2 of the screen, **Liu's turnover adjustment is
the obvious improvement we have not made.** LM12 normalises zero-volume counts by turnover so that two
tokens with the same silence but different activity are distinguished. Our label is binary — reserve
above or below a threshold — and a turnover-adjusted continuous version has twenty years of validation
behind it.

*The frozen window-2 rule is not changed by this. It is what it is, pinned and blind, and this is
context for interpreting the result rather than a reason to touch it.*
