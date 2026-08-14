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

## 2. The graduation-rate discrepancy — RESOLVED, and it validates us

Our 2.09% initially looked like **11× the most recent published rate**, which would have meant window
1 was atypical and every rate measured on it — including the deadness screen's base rate — was a
property of that window rather than the venue. It is not.

**Window 1 is 27–28 July 2026**, dated from on-chain `block_time`: first block 2026-07-27 16:07:12
UTC, last 2026-07-28 15:57:21 UTC, 23.8 hours. Against the reported rate history:

| period | graduation rate | source |
|---|---|---|
| Sep–Oct 2025 | 0.63% | Marino et al., n=655,770 |
| Jan 2026 | >1% | daily launches |
| May 8 – Jun 10 2026 | **0.198%** | Kamat survival, n=832,941 |
| mid-Jun 2026 | 0.26% | DEXTools |
| **week before late-July** | **2.5%** | The Block |
| **our window, 27–28 Jul** | **2.09%** | this project, n=3,932 |
| late Jul 2026, 4-day avg | 4.7% | The Block |
| late Jul 2026, peak day | 6.7% | The Block |

**Our measurement lands exactly where independent reporting says that specific week should be.** The
comparison was against the wrong regime: pump.fun's BOOST incentive changes drove graduation up an
order of magnitude in July 2026, and we collected during the ramp. The rate moved 0.198% → 6.7%
within about seven weeks.

This is now an **independent validation** of our count, from a completely different data source
(industry reporting versus our own on-chain enumeration), rather than an unresolved discrepancy.

**One consequence worth carrying:** graduation rate on this venue is *wildly* regime-dependent — a
25× range inside eight months. Any rate we quote must name its window, and window 2 (a different
day) may legitimately differ from window 1 without either being wrong.

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

**CORRECTION to an earlier version of this document.** I first wrote that the literature does not
measure early-buyer concentration. **That was wrong, and deeper reading found it.** MemeTrans
(arXiv 2602.13480) measures it directly:

> *"First 10 buyers of high-risk tokens hold **17 percentage points more** of supply than low-risk
> equivalents"*

It carries an explicit `early_top10_hold_pct` feature, plus sniper holdings, developer holdings and
bundle clustering across 122 features on 41,470 tokens. It also enforces temporal separation —
features strictly pre-migration, post-migration data used only for annotation. **So early-buyer
concentration as a rug signal is established prior art, and our finding is a replication of it, not a
discovery.**

What remains distinct is narrower and should be stated that way:

| | status in the literature |
|---|---|
| early-buyer concentration as a predictor | **established** — MemeTrans, 17pp separation, on 41,470 tokens |
| …on **bonding-curve-only** tokens | **absent** — MemeTrans covers *"only graduated tokens… bonding-curve-only tokens that never migrated are excluded by design"* |
| what fraction of tokens become **untradeable** | **absent** — *"no explicit metrics on what fraction becomes illiquid or untradeable post-creation"* |

**So B20B's contribution is the LABEL and the POPULATION, not the feature.** MemeTrans predicts
post-migration *price collapse* on tokens that graduated; we predict *unexitability* on the ~98% that
never do. Their base rate is 84% high-risk; ours is 35% unexitable — different labels on different
populations, and neither number is comparable to the other.

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
