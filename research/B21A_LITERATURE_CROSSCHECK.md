# B21A — this programme's findings against the published literature

**Why.** Two years of work on a market nobody in this project had checked against the academic record.
This is that check: what the literature already knows, where our numbers agree, where they disagree,
and — the useful part — **which of our findings sit in a gap the literature explicitly excludes.**

Searched across six angles rather than accepting the first result: pump.fun profitability, rug-pull
detection, holder concentration, bonding-curve microstructure, sniper/early-buyer behaviour, and
arXiv empirical work. Papers were downloaded and read rather than summarised from abstracts.

---

## 1. Where independent work CONFIRMS us

**The graduation deposit.** We measured it from `CreatePoolEvent` at **84.990359056 – 84.990364132
SOL** across all 82 graduations, and corrected an earlier claim that it was exactly 85. Marino et al.
independently define graduation as accumulating *"approximately 85 SOL (~$69,000 market cap)"*. Our
decode is confirmed to the tenth of a SOL by a completely separate pipeline.

**The toll finding.** Our central negative — that costs exceed anything the price process offers — has
a direct analogue. The same paper reports that **all** their predictive features *"remained below the
economic breakeven curve"* except at advanced bonding-curve stages. Independently derived, same
conclusion: signals exist, none of them clear the cost of acting on them.

**The pump-and-dump base rate.** They find **92.22% of tokens with ≥30 swaps exhibit at least one
detected price dump**, and that concentrated selling occurs *pre-graduation, particularly by
creators*. Consistent with our 45%-win/55%-lose asymmetry and with B19N's finding that graduation
selects the tokens that already pumped.

## 2. Where we DISAGREE, and it needs explaining

| | graduation rate | population | period |
|---|---|---|---|
| Marino et al. | 0.63% | 655,770 tokens | Sep–Oct 2025 |
| Kamat (survival) | **0.198%** | 832,941 tokens | May–Jun 2026 |
| **this project, window 1** | **2.09%** | 3,932 tokens | ~22.6-hour window |

**We are ~11× the most recent published rate.** Three candidate explanations, and the honest answer is
that this is unresolved:

- **Regime.** Our launch window is **22.6 hours**; theirs are 34 days and one month. The survival
  paper itself documents a **3.18× decline over eight months**, so day-to-day variation of this size
  is not implausible — but 11× is a lot to attribute to regime alone.
- **Censoring direction.** The survival study measures **24-hour** graduation. Our median
  time-to-graduate is 49 slots (~20 seconds) but the maximum is 686,257 slots (~76 hours), so we
  count late graduations they would censor. This pushes our rate *up* relative to theirs.
- **Population.** Both count `CreateEvent`s, so the denominators should be comparable. No obvious
  filter explains an order of magnitude.

**This matters beyond bookkeeping.** If our window is genuinely atypical, then every rate measured on
it — including the deadness screen's 35% base rate — is a property of that window rather than of the
venue. The window-2 pass now running is the direct test: it is a different 22.6-hour window, and its
graduation rate will say whether window 1 was unusual.

## 3. Where our work sits in a gap the literature EXCLUDES

This is the part worth having.

**The Solana rug-pull paper excludes our entire population.** From its methodology:

> *"we exclude **Pump.fun-only tokens that never establish liquidity pools** from our large-scale
> dataset construction"*

Only 82 of our 3,932 tokens (2.09%) ever established a pool. **~98% of the population we studied is
outside the scope of the published Solana rug-pull work.**

**And the exclusion is structural, not incidental.** The EVM rug-pull literature — RPHunter (95.3%
precision), LROO — defines a rug pull around **liquidity withdrawal**. On a pump.fun bonding curve
*there is no liquidity pool to withdraw*: the reserve is the curve itself, and extraction happens by
insiders selling into it. LROO states its own scope plainly: *"The dataset covers Ethereum and BSC,
both EVM-compatible. Generalization to non-EVM chains remains untested."*

So the dominant detection frameworks are built on a mechanism that **does not exist** on the venue we
measured.

**Two specific things the literature does not measure:**

| | status in the literature |
|---|---|
| early-buyer concentration as a predictor | *"The paper doesn't directly measure early-buyer concentration as a feature"* (Marino et al.). A targeted search returned nothing linking early holder concentration to token death. |
| what fraction of tokens become **untradeable** | *"provides no explicit metrics on what fraction becomes illiquid or untradeable post-creation"* |

**Those are precisely B20B's two contributions**: early-buyer concentration at t0+60 as the feature,
and unexitability as the label. The label is the more novel of the two — the literature measures
*price collapse* and *liquidity withdrawal*, both of which we showed are broken or inapplicable on a
bonding curve.

## 4. Where the literature is ahead of us

**LROO independently identifies our central methodological concern**, and got there first:

> *"a pervasive methodological flaw in existing work: temporal data leakage. Many studies extract
> features without enforcing strict causal ordering."*

It also uses a **Token Concentration Ratio** whose stated rationale — *"higher concentration
correlates with exit-risk exposure"* — is close to our finding. So the *idea* is not novel; the
contribution is measuring it leakage-free on the bonding-curve population that everyone else excludes.

**A caution on their headline.** LROO reports **ROC AUC 0.981–0.997** on 1,000 hand-labelled projects.
Numbers that high in a paper whose thesis is that the field leaks warrant scepticism about the
negative class: separating known rugs from established legitimate projects is a much easier problem
than early detection within a population of fresh launches. We should not benchmark against 0.99 AUC
without knowing how the negatives were drawn.

**On profitability**, the industry data is consistent with everything we found: of 13.55M pump.fun
wallets, **~0.41% realised profits above $10,000**, and ~96% either lost money or made under $500 —
with the explicit caveat that it counts **realised** PnL only and *"excludes bagholders who never sold
even if it crashes to zero."* That caveat is our unexitability finding seen from the other side: the
losses are understated because unsellable positions never register as losses.

## 5. What this changes

- **Nothing is retracted.** No published result contradicts a measurement of ours.
- **The 85 SOL decode and the below-breakeven conclusion are independently corroborated.**
- **The graduation-rate discrepancy is an open question**, and window 2 is the test.
- **B20B's label is the novel part** and should be described that way: not "we detect rug pulls" —
  the literature does that better on EVM — but *"we measure unexitability on the bonding-curve-only
  population that rug-pull datasets exclude by construction."*

---

*Sources are listed with the handoff. Papers were downloaded and text-extracted rather than read from
abstracts; where a claim rests on a single line of a methodology section, that line is quoted verbatim
above so it can be checked.*
