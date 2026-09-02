## VERDICT UP FRONT

The field is weak. Of ~36 candidates, 14 are self-declared dead, 8 more die on NL venue access or the $10k floor, and of the survivors **exactly one has a measured edge/cost ratio above 1 that the operator can act on this month — and it is a tax-wrapper audit, not a trading strategy.** Every remaining "live" candidate has an UNMEASURED numerator. That is not a failure of the scouts; it is the honest state of the search.

I independently re-ran two of the load-bearing measurements rather than trusting them (HLP portfolio history, box-3 statute + tegenbewijs). One reproduced and one broke. Details in the attacks.

---

## SCORED TABLE — TOP 12 OF 36

Weights: Impounding ×3 (it killed the last month), Edge/Cost ×2, Falsifiability ×1, Capacity ×1, Counterparty ×1. Score /10. **Score measures "worth spending a day on", NOT "will make money" — see #3.**

| # | Candidate | Impound | Edge/Cost | Falsify | Cap | Cparty | **Score** | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | **Box-3 wrapper routing (NL deposits vs securities)** | 10 | 9 | 9 | 7 | 8 | **9.0** | TEST — but see attack, headline is 3.5x too big |
| 2 | **Hyperliquid HLP vault deposit** | 9 | 2 | 9 | 10 | 9 | **7.4** | ALREADY MEASURED → FAILS. Do not fund |
| 3 | **Token unlock cliff short (beta-controlled)** | 7 | 5 | 9 | 8 | 7 | **6.9** | TEST, power-first |
| 4 | **Pendle PT resting limit orders** | 8 | 7 | 6 | 7 | 6 | **6.9** | Gates are mutually exclusive — see attack |
| 5 | **Deribit receive-fixed perp/dated swap** | 8 | 8 | 8 | 7 | 4 | **6.9** | Run the 20-min power census to CLOSE it |
| 6 | **DGS cross-border deposit spread** | 9 | 5 | 9 | 7 | 6 | **6.8** | Not standalone — it is #1's execution venue |
| 7 | **Nordic rights issue tier-2 allotment** | 8 | 4 | 6 | 6 | 8 | **6.0** | Kill via one broker ticket before any scraping |
| 8 | **Micro-cap self-tender (SC TO-I) proration** | 8 | 4 | 8 | 6 | 7 | **5.9** | Run to CLOSE; T11 prior is bad |
| 9 | **Pegged-pair CLMM (stable/LST)** | 7 | 3 | 8 | 9 | 6 | **5.5** | Must beat Aave 3.37% by 200bp; won't |
| 10 | **Token migration deadline swap (ICX→SODA)** | 9 | 3 | 7 | 3 | 9 | **5.8** | Best counterparty in the field, fails capacity floor |
| 11 | **CEX-delisting forced-exit gap** | 5 | 3 | 7 | 3 | 8 | **4.5** | Drop is on announcement = impounding replay |
| 12 | **stETH redemption-queue discount** | 6 | 1 | 10 | 8 | 9 | **4.9** | Measured 0.6bp today vs 20-40bp cost. Dormant alarm only |

**Excluded before scoring** (not close calls): all Polymarket/Kalshi/ForecastEx entries — NL is close-only on Polymarket with a KSA €420k enforcement precedent, Kalshi is unlicensed in NL and 37.8% kansspelbelasting on *gross positive months with no loss carryforward* imposes a Sharpe-0.656 hurdle before any edge; ForecastEx median fill is $10. Perp funding harvest, cash-and-carry, USDT/USDC quote basis, Deribit boxes — all measured below T-bills, and repo-dead four ways (T22/T23/T25). Merger arb and small-market tenders — T11 loses at *literally zero cost* (−0.776%), an economics death that no new geography repairs. Aave Umbrella (−200bp risk premium, slashing fired April 2026), Sky PSM (one block), volatile-pair LP (ratio 0.8, and concentration scales fees and LVR identically so the family closes in one line), maker-rebate tiers (tier-gated + sub-second), points farming (discretionary payoff = forecast in costume).

---

## ATTACKS ON THE TOP 5

### 1. Box-3 wrapper routing — **the headline number is wrong by 3.5x**

The scout computed the edge as forfait-minus-forfait: (6.00% − 1.28%) × 36% = 169.9 bp, then added a 136 bp yield chase for a 306 bp headline. I verified the statute — 1.28% banktegoeden (provisional), 6.00% overige bezittingen (fixed), 2.70% schulden, 36%, €59,357 exemption ([Raisin](https://www.raisin.com/nl-nl/box-3-belasting/forfaitair-rendement/), [Van Lanschot Kempen](https://www.vanlanschotkempen.com/nl-nl/private-banking/inspiratie/beleggen-en-sparen/2026/01/rendementspercentages-box-3), [Stolwijk](https://stolwijkkennisnetwerk.nl/box-3-percentages-vrijstellingen-en-bedragen-in-2026/)) — and then I checked the thing the scout listed as kill-risk #5 and then ignored.

**The tegenbewijsregeling makes the 6.00% forfait a CAP, not a charge.** It is in force for 2026–2027, integrated into the normal return since tax year 2025, and computed on *total* box-3 assets ([Belastingdienst](https://www.belastingdienst.nl/wps/wcm/connect/nl/box-3/content/wat-is-mijn-werkelijk-rendement), [Dirkzwager](https://www.dirkzwager.nl/kennis/artikelen/hoe-werkt-de-tegenbewijsregeling-in-box-3), [EY](https://www.ey.com/nl_nl/technical/tax/tax-updates/voortgang-tegenbewijsregeling-box-3)). You pay min(forfait, actual). So:

- **Forfait-binding regime** (total actual return > forfait, i.e. a good equity year): moving €500k from an MMF to a deposit saves €8,500 of tax and gains €6,800 of yield = **306 bp. Scout is right.**
- **Actual-binding regime** (total actual < forfait — which for a cash-heavy operator is *essentially always*): the wrapper saves nothing, because you were never paying 6% on the MMF. Moving raises actual income by 136 bp and therefore raises tax by 136 × 36% = 49 bp. Net **87 bp. Scout is 3.5x too high.**

Second attack: **136 of the surviving 87–306 bp is not a tax edge at all.** It is chasing 3.46% at BluOr Bank instead of 1.30% at ING — available to anyone in any wrapper, and it is compensation for DGS-jurisdiction quality plus a term lock. That is candidate #6's own honest 30–45 bp over the matched curve, wearing candidate #1's clothes. The scout's own K3 for #6 ("if spread rank-correlates with DGS underfunding at ρ>0.7, declare it fair compensation") should be applied to #1's yield leg too.

Third attack: **this pays nothing unless the operator's capital is actually in the wrong wrapper.** That is a 10-minute balance-sheet read, not a study, and it must be the first thing done. If the money is already in deposits, or already in equities earning >6%, the delta is zero.

Fourth: 16 months of certain life (Wet werkelijk rendement, 1 Jan 2028). Setup must amortise inside that.

**It survives all four.** 87 bp on €500k is €4,350/yr against ~2 bp of one-off cost and provably zero competition. It is still the best edge/cost in the field. It is just not 306 bp and it is not a strategy.

### 2. Hyperliquid HLP — **I reproduced it, and it fails**

One keyless POST to `api.hyperliquid.xyz/info`, `vaultDetails`, 2026-09-03. Scout 2's numbers reproduce almost exactly on my own pull:

- Account value **$189,222,283**; `apr` field **0.0649**; all-time PnL **$137,883,285**; 98 fortnightly points back to 2023-05-10.
- Trailing-12m compounded: **+18.74%** (scout said 17.86% time-weighted).
- **Ex the top two fortnights (2025-10-15 +9.70%, 2026-02-04 +7.00%): +1.16% over 350 days = 1.21%/yr.** Below T-bills. Below Aave USDC. Scout 2 reported 1.16%/yr and was right.

Three attacks:

**(a) The two scouts contradict each other on the same free endpoint, and one of them is wrong.** Scout 5 (microstructure) quotes the `apr` field of 6.55% as the edge and computes "+3.2pp excess over Aave 3.37%". Scout 2 explicitly calls that same field "a trailing-window artifact". Scout 2 is correct: `apr` is a trailing window dominated by one cascade. Scout 5's candidate #3 is a headline read as a measurement — the exact failure mode that retired ~60 prior theses.

**(b) The scout's own kill line K3 cannot fire.** "Any single fortnight worse than −5% of AV → DEAD." The worst fortnight at meaningful scale in the entire 3.3-year history is **−0.80%** (2025-11-12, at $583.8M AV). The −4.42% was December 2023 at $13.2M AV. A gate set where it has never fired and structurally cannot fire is not a gate; it is decoration.

**(c) A fact neither scout reported, which I found in the same call.** Over the trailing month, AV fell **$220.0M → $189.2M while earning +$972,079**. That is **$31.8M of net depositor withdrawals in 30 days — 14.5% of TVL — on top of the 68% decline from November 2025.** The "shrinking TVL means more convexity per dollar" thesis is being sold to us by people who are simultaneously leaving. And the central assumption is the one the scout itself flagged: the cascade windfall almost certainly scales with *venue open interest*, not with HLP's TVL, so a smaller base does not triple the payoff.

Honest counter-reading, stated because the adversarial job cuts both ways: judging a long-convexity book "ex its convexity events" is unfair. Base rate at meaningful scale is ~2 events in 2.5 years ≈ 0.8/yr × ~8% = 6.4%/yr of expected event contribution plus 1.2% carry ≈ 7.6%/yr, or +3.7pp over T-bills. **But that entire case rests on n=2, and it is levered to an uninsured, no-recourse, single-venue tail (JELLY, validator intervention, bridge/custody).** +3.7pp of expected excess with an uncapped left tail on 100% of principal is a bad trade for a personal account. Not shortlisted. It costs $0 to keep watching, and the watch is one cron line.

### 3. Token unlock cliff short — **four attacks, all survivable, which is why it makes the list**

**(a) Look-ahead, and it is not random.** DefiLlama serves the *current* schedule. Projects revise vestings — and they revise them precisely when the token is weak, which is exactly the population with the biggest drawdowns. The backtest will therefore see a cleaner, more favourable calendar than existed ex ante. The scout flags this; the prereg must restrict to cliff dates documented at TGE and *report how many events survive that restriction*, because if it is 200 of 1,329 the power argument collapses.

**(b) Power is the real wall, and it is the T23/T25 wall.** 1,329 events is not n=1,329. Altcoin 44-day returns are dominated by one beta factor; cluster-bootstrap by event date collapses effective n toward the number of distinct market regimes (~40–70 months over the panel). At σ_residual ≈ 35% and n_eff = 100, SE ≈ 3.5 pp and MDE ≈ 9.8 pp — which *fails against a haircut 2–4% capture and barely passes against the 8% headline*. This is why the MDE census must run before the effect is read, exactly as T23 and T25 did.

**(c) The control is contaminated.** "Same-day equal-weight median of the surviving perp universe" includes other tokens that are themselves unlocking — 405 cliffs in the next 90 days alone. The control absorbs part of the effect. Use a same-day median *excluding* names within ±30d of their own ≥1% cliff.

**(d) I verified the data is genuinely on disk and genuinely usable.** `research/data/t23_cache/panel/perp_daily.csv`: **919 symbols, 634,608 rows, 2020-01-01 → 2026-07-31**; `funding.csv` 2,721,204 prints; `manifest.jsonl` 63,801 entries. `defillama-datasets.llama.fi/emissionsProtocolsList` returns HTTP 200 keyless; `api.llama.fi/emissions` returns HTTP 402 (the paid trap is real, the free route works). Note the panel **ends 2026-07-31** — five weeks stale, fine for the backtest, but the 405 upcoming cliffs cannot be validated forward without a fresh pull.

### 4. Pendle PT resting limit orders — **the two gates are mutually exclusive**

The kill lines are "fewer than 4 fills per market-quarter → dead" and "mean 7-day post-fill peg change worse than −1% → dead". These cannot both pass. To survive the November 2025 tail (Stream Finance $93M loss, xUSD −77%, deUSD −98% to ~$0.015, ~$285M of bad debt across Euler/Silo/Morpho/Gearbox) you must restrict to wstETH/sUSDe-class underlyings — where the flow is thin and you die on fill frequency. To get flow you must quote the 13–18% names — where you are short a credit put you cannot price, filled *exactly when it is in the money*. There is no setting of the dial where both gates pass, and the scout says as much in its own kill-risk field without drawing the conclusion. Secondary: "maker fee currently 0" is a governance parameter, not a contract; the whole cost advantage is revocable by a forum post.

### 5. Deribit receive-fixed perp/dated swap — **the sd is the wrong sd, and the census will kill it**

Measured +2.18 pp/yr (SEP26) and +2.56 pp/yr (DEC26) with sd 1.71 pp and 87–98% of windows positive. But **that sd is computed on overlapping daily windows inside a single 250-day regime** — it is the within-regime dispersion, not the cross-regime dispersion, and it is the number that makes the trade look like a 4.4x. In 2021 Binance BTC funding averaged 30.61%/yr against a much smaller term basis; the receive-fixed side would have bled roughly 20–25 pp. The true cross-regime sd is an order of magnitude larger, the effective sample is ~3 independent quarters, and the power census the scout itself demands will return **DEAD BY POWER** — the same wall as T23 (MDE 15.25 vs 2.20 claim) and T25 (MDE 6.30 held-out, 2.85 on the *entire joint history*, i.e. no split of the data can ever work). Separately, the counterparty is "named by inference only" — the scout read the price, not the flow. Run the census to close the family; do not run the strategy.

---

## RECOMMENDED SHORTLIST — 2 to test, 1 to close

### SHORTLIST 1 — Box-3 wrapper + DGS deposit routing (do this today, before any research)
**Why:** the only item in 36 whose edge/cost ratio is *measured* (87–306 bp against ~2 bp), whose competition is provably zero because the benefit accrues per taxpayer with no shared pool, whose data is free and permanent, and which pays inside 16 months without a single order being placed. It also composes candidate #6 (the deposit spread) as its execution venue rather than as a separate bet.

**Cheapest measurement that kills it (1 hour, €0, no code):**
List the operator's actual box-3 composition as of 1 Jan 2026 and last year's actual total box-3 return. Compute net-of-tax return under min(forfait, actual) for three states: current holding, NL big-bank savings, best DGS deposit obtainable with a documented 0%-WHT route.

**Kill if:** the cash/short-duration sleeve is under €150k, OR the actual-return regime binds and the net delta is under 100 bp/yr, OR fewer than 3 banks quote ≥3.00% with a 0%-WHT route for NL residents.
**Keep alive if:** ≥€250k currently sits in a securities wrapper or a sub-2% Dutch savings account and the computed delta clears 100 bp/yr. Then execute — it is one afternoon of forms, not a project.

**Honest caveat, stated plainly:** this is treasury management. It will never produce a trading system, it caps out around €500–800k on strong-DGS jurisdictions, and it legislatively expires 1 Jan 2028.

### SHORTLIST 2 — Token unlock cliff short, POWER-FIRST (the one research test worth a day)
**Why:** it is the only candidate where the clock is weeks (entry 30 days early, zero latency content), the counterparty is named and mandate-driven, the data is already on disk and survivorship-complete, the free calendar is verified working, and the repo's own machinery — power census before effect, alt-beta control, cluster-bootstrap, frozen prereg — applies unmodified. It either opens a lane of 116 tradeable events per 90 days or closes a family with a number.

**Cheapest measurement that kills it — run in this order, stop at the first failure:**
1. **(30 min) Coverage census.** Of the 1,329 ≥1%-of-float cliffs with a live perp, how many fall inside 2020-01-01..2026-07-31 with the perp listed ≥30 days before the cliff *and* a cliff date documented at TGE (not a revised schedule)? **Kill if under 400.**
2. **(2 hours) MDE census, before any effect is read.** Residual sd after subtracting the same-day cross-sectional median *excluding names within ±30d of their own ≥1% cliff*; cluster-bootstrap by event date. **Kill if MDE > 3 pp** (half the claimed 8%).
3. Only then read the effect, against the pre-registered gate: beta-controlled mean ≤ −1.5%, CI-upper < 0, realised funding < 50% of gross.

**Keep alive if:** ≥400 usable TGE-documented events AND MDE < 3 pp. Anything else is the T23/T25 wall in a new suit and should be banked as a documented kill.

### CLOSE, DON'T TEST — Deribit receive-fixed (20 minutes)
Not a shortlist item, an accounting action. Build the non-overlapping quarterly panel (~26 BTC + ETH quarters since 2020), compute the cross-regime sd, and run the MDE. Expect DEAD BY POWER. Record it so the next invention round does not re-propose a 4.4x ratio built on a within-regime standard deviation.

**Also free, also worth one cron line each, neither a project:** the stETH discount alarm (arm only if discount > queue_days × yield/365 + 40 bp; it is 0.6 bp today, dead by 50x) and the HLP observation (already automated by the pull above — watch whether the $31.8M/month outflow continues).

---

**The one sentence:** In thirty-six candidates the only thing that pays you this month is a Dutch tax-wrapper audit you can finish before dinner — and it is worth 87 bp, not the 306 bp on the label — so do that today, spend exactly one day on the unlock power census, and refuse to fund anything whose key number you have not computed yourself, because HLP passed every structural filter in this scan and still returns 1.21%/yr once you take out the two fortnights that made the brochure.