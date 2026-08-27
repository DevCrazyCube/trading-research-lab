# SIZE round — synthesis verdict

**Date:** 2026-08-20
**Round mandate:** propose only mechanisms that could plausibly be *life-changing* in magnitude —
either (a) a large per-trade edge with real capacity, or (b) genuine long-convexity that compounds.
Round-1 survivors at 0.4–0.9 %/yr were declared automatic kills.
**Inputs:** 6 adversarial lenses × 3 theories = **18 candidates**, each with a first-party
adversarial critique.

---

## 0. Headline

**ZERO candidates survive. `top_picks` is empty, deliberately.**

All 18 critiques returned `overall: KILL`. Not one theory carries `PROMISING`, so the round-1
filter (`PROMISING ∧ magnitude_ok ∧ free_data_available`) admits nobody. I am not promoting a
runner-up. The mandate explicitly permits zero and explicitly forbids substituting a small edge, and
the strongest near-miss has a **first-party measured prior of ~10 bp gross where it needs ~150 bp**.

The round is not, however, a null result. It produced one structural finding that is worth more than
any of the eighteen theories, and it is stated in §3.

---

## 1. The census — all eighteen, with the flags that decide admission

| # | lens | theory | verdict | `magnitude_ok` | `free_data` | power (mo) | primary cause of death |
|---|---|---|---|---|---|---|---|
| 1 | cascade capture | Leverage-Fuel Convexity | KILL | ✅ | ❌ | 294 | power; expired-option prices not free |
| 2 | cascade capture | **Cascade Relay** | KILL | ✅ | ✅ | **7** | payoff-vs-exit + friction (0.83R) |
| 3 | cascade capture | The Named Ladder | KILL | ❌ | ❌ | 47 | capacity 25–100× overstated; `l2Book` 20-level truncation |
| 4 | catalyst convexity | Mandated Overwrite Discount | KILL | ❌ | ❌ | 124 | premise falsified by NPORT-P; parity estimator ≡ 0 |
| 5 | catalyst convexity | Unhedged Unlock | KILL | ❌ | ✅ | 100 | event rate overstated 3–8×; 1.2–3.0 %/yr |
| 6 | catalyst convexity | Above the Pin | KILL | ❌ | ❌ | 680 | flow sign **inverted** (fund writes a call spread) |
| 7 | positive-skew trend | Lookback Exile | KILL | ✅ | ✅ | 228 | close-only prior was an artifact; 2023-26 expectancy −0.038R |
| 8 | positive-skew trend | Unlevered Ascent | KILL | ✅ | ✅ | 1512 | baseline sign-flips on real OHLC; 126 yr to resolve |
| 9 | positive-skew trend | Regime Ignition | KILL | ✅ | ✅ | 240 | **its own Gate 0 fired**, with the sign inverted |
| 10 | forced flow | Passive Float Delta | KILL | ❌ | ❌ | 65 | elasticity; buys the net-issuance anomaly backwards |
| 11 | forced flow | Vertical Float | KILL | ❌ | ❌ | 240 | trigger selects for 4 documented negative predictors |
| 12 | forced flow | The Benchmark Hour | KILL | ❌ | ✅ | ∞ | **regime abolished 2025-07-29** (SEC in-kind) |
| 13 | stress dislocation | Par-Claim Ladder | KILL | ❌ | ✅ | 128 | biggest cascade ever pays +5.3 %; written solvency put |
| 14 | stress dislocation | Cascade Basis Snap | KILL | ❌ | ✅ | 148 | 3 clusters in 4.6 yr against a self-declared gate of 22 |
| 15 | stress dislocation | The Queue Is The Stop | KILL | ❌ | ❌ | 21 | fire rate 5–15× over; free route *manufactures* 1,760 bp |
| 16 | cheap convexity | Clamp Excess | KILL | ❌ | ✅ | 80 | switch never thrown: 12 clamps in 34,280 prints |
| 17 | cheap convexity | Pin Release | KILL | ❌ | ❌ | 20 | **measured EV negative**: −57 to −80 %/yr |
| 18 | cheap convexity | Roll Shadow | KILL | ❌ | ❌ | 64 | mechanism non-sequitur; zero break-even margin |

Admitted by the flag filter alone (`magnitude_ok ∧ free_data`): **#2, #7, #8, #9** — four of
eighteen. All four are nonetheless KILL, and three of the four (#7, #8, #9) were killed **by direct
measurement on real OHLC during the critique**, not by argument. §2 handles #2, the only one whose
death rests on reasoning rather than on a number produced this round.

---

## 2. Why the best candidate still does not get funded

**Cascade Relay** (ride the liquidation cascade with-trend on real signed tape) is the strongest
artifact this round produced and deserves the credit its critique gave it. Its estimator is the real
one at every point that killed round 1: the trigger denominator is the actual trailing ±1 %
`bookDepth` notional — the exact quantity that inverted Orphan Flush from +42 bp to −11 bp — the
numerator is signed taker notional from `aggTrades` via `is_buyer_maker` rather than the
non-identifying metrics taker ratio, fills walk real prints capped at 10 % of printed volume, and
the spread charged is the `bookTicker` quote at the entry timestamp. It carries the mandatory
volume-denominator control arm. It has **real power** — ~1 independent cascade episode/day against
n ≈ 196, i.e. ~7 months, covered several times by 3.25 years of archive already on disk. It is the
only candidate in eighteen that is simultaneously large-magnitude, free-data, and resolvable inside
this programme's budget.

It still dies, on three independent grounds, two of them arithmetic:

1. **The exhaustion exit is a ratchet wearing a state-based costume.** "Flat when consumption falls
   below 0.5× its rolling 3-bar peak for two consecutive bars" terminates on the first lull of a
   punctuated process. The claimed 10 % of winners at 10R requires ~90 minutes of consumption never
   pausing below half a 3-bar rolling peak — an event the exit rule itself forbids. This is
   *precisely* Coiled Leverage Expansion's corpse: `COILED_GATE0_RESULT.json` measured W = 1.088
   against an assumed 3.0. The theory even pre-registers the correct kill ("DEAD if mean win falls
   within 0.3R of mean loss, which would mean the exhaustion exit is behaving like a ratchet") — and
   that is the gate that fires.
2. **The stop is inside one bar's noise by construction.** R = 0.9 × the 1-hour ATR *frozen at
   t−12*, i.e. 40–80 bp, in a state where 5-minute realised range is 3–5× the pre-cascade ATR by
   definition. A 60 bp resting stop in a name printing 100 bp+ bars gaps as the rule, not the
   exception: L ≈ 1.8–2.5R, not the asserted 1.35R.
3. **Friction is charged at a calm-market rate to the widest-spread instant the instrument has.**
   This repo's own frozen number for this exact order shape (marketable limit at the far touch, no
   maker path on either leg) is 25 bp central / **50 bp at the honest cascade moment**
   (`ORIGINAL_STRATEGY_SHORTLIST.md` §5.7). The theory charges 12–20 bp. At 50 bp against a 60 bp R
   that is **0.83R per trade**.

Recomputed: gross EV ≈ 0.55 × 1.4 − 0.45 × 2.1 = **−0.18R before friction**.

And the decisive prior is first-party. The mirror-image fade, on the *same* real depth denominator,
returned **−10.99 bp per cluster on 521 clusters at t = −0.53**
(`ORPHANFLUSH_DEPTHQ_DESIGN_RESULT.json`). It is not a strict mirror — different trigger, timing and
hold — but the gross magnitude available *in this state, on this instrument* has now been measured at
~10 bp, against the ~150 bp (2.44R × 60 bp) this candidate requires. **That is an order of magnitude,
and it is ours.**

**Disposition:** not a pick, not an allocation. The single cheapest number in this round is a
design-window, zero-cost, cluster-level **gross** census of the with-trend cascade state on data
already on disk — an afternoon, no held-out window spent, and it settles the family. Recorded in §5
as a measurement, not a strategy.

---

## 3. The structural finding — and it is the real output of this round

Sort the eighteen by `power_months_to_resolve`:

```
7, 20, 21, 47, 64, 65, 80, 100, 124, 128, 148, 228, 240, 240, 294, 680, 999, ∞
```

Median **126 months = 10.5 years**. Three of eighteen (17 %) resolve inside a 36-month
design-plus-held-out budget. And of those three, exactly **one** (#2, Cascade Relay) also clears
`magnitude_ok`.

That is not coincidence, and the mechanism is now legible:

> **Convexity you can BUY is not measurable on free data. Convexity you can MEASURE on free data is
> not real convexity.**

Every candidate with *contractual* convexity — bounded premium, uncapped payoff, no stop, no
liquidation path — was an options structure: #1, #4, #6, #16, #17, #18. Every one of those cleared
the tail bar cleanly, and every one of them then died on the same wall: **there is no free archive
of expired-instrument prices or quotes.** Measured this round, first-party: Deribit
`get_tradingview_chart_data` → `no_data`; `get_last_trades_by_instrument` with `include_old=true` →
`[]`; `get_book_summary_by_instrument` on an expired series → error −32602 "instrument is not open";
`get_instruments?expired=true` returns 56 instruments, all from the single most recent expiry. On the
equity side, OPRA history behind Alpaca starts ≈2024-02 and the *flow* half (issuer daily holdings)
has zero archived months. So the deciding P&L or the deciding conditioner must be **collected
forward** — which converts the crypto pivot's one structural advantage (compute time instead of
calendar time) straight back into calendar time.

Every candidate with *free, deep, tick-resolution* data — perps and spot: #2, #5, #7, #8, #9, #12,
#13, #14, #16 — had to **synthesise** convexity out of a stop plus a trail. And every single time,
the synthesised convexity was falsified by the same argument: **a path-dependent exit cannot pay an
MFE-derived win.** Three theories independently used `W = MFE/R − giveback`; a 25-session-low ratchet
exits a trade that touches +40R at +3.2R if it first retraces to a 25-session low. Measured
consequences this round: Lookback Exile's quoted W = 10.97R became **5.45R** on real OHLC (and 3.16R
in 2023-26, below its own 3.5R floor); Unlevered Ascent's 6.11R baseline became **2.20R** with the
expectancy sign flipping to −0.162R; Regime Ignition's breadth gate moved mean win **−1.47R** when
its own blocking rule required **+1.00R**, and truncated max trade from +146R to +31R.

This is failure-mode-2 from the brief, generalised. Round 1 stated it as "a trailing stop caps wins
at ~1.1R." The correct general statement is stronger:

> **Convexity is a property of an INSTRUMENT, not of an exit rule. An exit rule that produces a right
> tail in backtest is producing it from path luck, and the MFE it is scored against is not
> achievable. If the payoff is not bounded below by contract, it is not convex — it is a directional
> position with a stop attached.**

The corollary is uncomfortable and should be stated plainly: **the two properties this round demanded
— life-changing magnitude via genuine convexity, and resolvability on free data — are close to
mutually exclusive on the instruments this programme can reach.** That is a finding about the
opportunity set, not about the eighteen theories, and it is why the honest pick count is zero.

---

## 4. Method rules this round earns

Candidates for `FINDINGS.md` §8. Each is backed by a measurement taken during this round.

1. **The assumed arrival rate is the single most-inflated number in a candidate write-up — census it
   before writing the harness.** Measured overstatements this round: Unhedged Unlock claimed ~1,000
   archived events / 150–250 per year, measured **123–308 total across 370 protocols and all of
   2021-2026**, and 6–15/yr tradeable. Par-Claim Ladder asserted 120–150 clusters, measured **14**.
   Cascade Basis Snap needed 11 clusters and self-declared DEAD below 22, measured **3 in 4.6
   years**. The Queue Is The Stop assumed 15–40 fires/yr, measured **2.8/yr** on the nearest real
   instrument. Clamp Excess assumed 40–70 episodes/yr; the frozen rule fires **zero times in 166
   days** (12 clamped symbol-windows in 34,280 prints, peak cross-sectional breadth 2.5 % against a
   rule needing 50 pp). This is §5j's rule paying out for the **eighth through twelfth** time.
2. **When the mean is carried by an assumed tail decile, normal-theory SE understates by 1.5–2× and
   effective n is the count of TAIL events, not of trades.** Vertical Float's entire +9.8 %/event is
   one invented decile at +95 %; strip it and its own arithmetic gives +0.014R ≈ 0. Lookback Exile's
   top 5 % of trades contribute 118 % of total R — so its effective n is ~1–1.7 forty-R trades per
   year in the modern regime, not 147 trades/yr. **Bootstrap the SE of any tail-carried mean.**
3. **A "model-free" estimator that is an arbitrage identity returns zero by construction.** Mandated
   Overwrite Discount priced its concession as `(parity_synthetic − paid)/parity_synthetic`. Put-call
   parity is enforced by conversion/reversal desks; a 12 % call-only discount is a riskless
   conversion, not a mispricing. The scissors is inescapable: the model-free estimator measures ~0 by
   arbitrage, and the estimator that could see the effect (fitted-smile IV) is the archetypal
   artifact the design correctly bans.
4. **Read the filing before theorising about the flow.** TSLY's NPORT-P (Tidal Trust II, CIK
   1924868, acc 0002000324-26-002714, totAssets $922,071,883) shows the fund short 21,819 calls
   across 380/382.5/385/387.5/390 **and long 21,819 across 397.5/400/402.5/405/407.5, same expiry**.
   It writes a **call spread**, net premium sold 0.53 % of NAV — which inverts the dealer's inventory
   sign and kills the entire "covered-call-ETF front-running" family (#4 and #6) at one stroke. The
   per-line supply ratio is **0.37–1.01×** OI, not the claimed 2–5×, and part of the flow is FLEX
   (strikes 405.01/410.01) that never prints on the lit book.
5. **An API's level cap is a denominator, and it biases per side.** Hyperliquid `l2Book` returns
   exactly **20 levels per side**, all inside ±1 %, so "±1 % band notional" is truncated by the cap,
   not the band — measured asymmetry 2.3× on BTC ($9.47M bid / $4.19M ask) and 5.2× on SOL. This is
   Orphan Flush's depth-denominator hole re-opened on a new venue. **Probe the level count before
   using a book-derived denominator.**
6. **Check whether the venue still runs the mechanism.** The Benchmark Hour harvests spot-ETF **cash**
   creations; the SEC permitted in-kind creation/redemption for spot BTC/ETH ETPs on **2025-07-29**
   (release 2025-101) and IBIT has flipped. The write-up names in-kind approval as its own retire
   trigger — it had fired thirteen months earlier. Its entire 490-session design window sits inside a
   dead regime and no out-of-sample period will ever accrue.
7. **A daily snapshot joined across two independent sources manufactures edge.** DefiLlama daily
   stETH vs WETH over 812 days shows a sane median deviation of −5.5 bp and a tail of **−1,760 bp**,
   −1,309 bp, −1,209 bp. Those discounts did not exist; they are timestamp mismatch on an asset that
   moves 5–15 %/day. The free historical route for that candidate is a pure artifact generator.
8. **Correction to be landed: `B22B_SLIPPAGE_RESULT.json` is being misused across the programme.**
   Three separate theories this round named it as their stop-fill distribution. Its own
   `scope_limit.does_not_measure` says **"exit slippage (stop-loss market orders, market-on-close)"**
   and it calls itself **"a LOWER BOUND on total friction."** It is also a US large-cap **equity**
   distribution (`notional_bp` p90 = 0 bp, p95 = 2 bp, median 0), and the widely-quoted "233 bp" is
   `r_bp` — basis points **of R** (2.3 %), not price bp. This repo's own coiled harness confirms the
   scale: applying it moved L from 0.5661 to 0.5688, i.e. **+0.0027R**. Annotate the JSON so the
   next candidate cannot repeat this.
9. **Sampling a measured slippage distribution beats assuming the stop fills at its level** — The
   Benchmark Hour did this correctly and it is the one method rule worth copying out of a killed
   candidate.
10. **A control arm whose success falsifies the treatment is the right instinct, and it works.**
    Regime Ignition pre-registered exactly that and its ungated control came in at +0.305R against a
    gated −0.094R. It killed itself for free. Compare Leverage-Fuel Convexity, which declared **no**
    Fuel-off arm — making its originality claim untestable by construction, in violation of
    `ORIGINAL_STRATEGY_SHORTLIST.md` §9.
11. **Set the pre-registered gate ABOVE the fully-costed break-even, and recompute break-even with
    the measured spread and the fee cap.** Leverage-Fuel Convexity pre-registered a +5 pp lift on a
    break-even it computed at 26.2 %; charging the live measured 10–17 % relative wing spread and the
    Deribit 12.5 %-of-premium fee cap (which **binds** on a 15-delta weekly and does **not** bind
    ATM, where the fee is 0.55 % of premium) moves break-even to **30–33 %**. A "pass" would not have
    been a tradeable result.

---

## 5. Salvage register — free measurements worth an afternoon each

None burns a held-out window. Ordered by value per hour.

1. **The cascade gross census (§2).** Design-window, cluster-level, *gross*, with-trend, on the real
   ±1 % depth denominator and real signed `aggTrades`, on data already on disk. Settles the entire
   liquidation-capture family against the −10.99 bp mirror already measured. **If one number is
   bought this round, buy this one.**
2. **The HLP-liquidator tape census.** Retrospective, free, runs today: do large named liquidations
   walk the book, or are they dripped? The live probe already answers it — 2,000 liquidator fills on
   2025-10-11 averaging **$173 each**, carrying a `twapId`, against a `startPosition` of 518,911
   HYPE, with the largest positions assumed by HLP off-book entirely. Record it: **the biggest
   forced-flow events supply the LEAST price impact**, which pre-kills every "ride the named
   liquidation" design.
3. **The covered-call-ETF flow finding (§4.4).** Already measured. Record in `FINDINGS.md` §8 so the
   family is not rediscovered a third time.
4. **The unlock-universe census.** "The free unlock universe contains ~123–308 insider cliff events
   in **total**, not thousands." Script is an afternoon; it pre-kills every future unlock-timing
   candidate.
5. **The funding-cap constants.** Measured: **0.300 %/8h for BTC and ETH, 0.375 % for SOL/XRP/BNB,
   2.000 % for 685 of 760 symbols.** Any design treating the cap as a constant is wrong. Also:
   clamp state is exactly recoverable free as `fundingPrint < premiumTWAP + interest` — it costs
   nothing to compute and is essentially always off.
6. **Reusable estimators worth keeping regardless of verdict.** (a) The par-anchored (not
   market-anchored) resting ladder. (b) `AvailableFloat` as a *stock of shares* (shares outstanding −
   measured passive − measured affiliate) rather than ADV — the correct antidote to the substitution
   that killed Orphan Flush; note the 13F/13G **double-subtraction bug** (BlackRock/Vanguard/State
   Street file 13G on the same shares they report on 13F), which biases the denominator down and the
   trigger up. (c) The closing-cross **printed-size** denominator, code-agnostic over conditions 6
   and M. (d) Lee-Ready-signed ETF-tape flow as an ex-ante instrument, avoiding the Farside /
   premium-discount lookahead. (e) The contract-count-vs-notional OI distinction — standing doctrine,
   not a per-candidate choice. (f) The `aggTrades`-vs-1s-kline attribution discipline, which survived
   re-measurement and was the *only* case this round where the real estimator made a capacity number
   **larger**.
7. **The listing-age distribution-shape fact.** Lookback Exile's age spread is real and
   direction-correct on identical real-OHLC rules: **+0.896R young vs −0.162R mature**, a 1.06R gap,
   with a modern-regime fat-tail ratio (fraction of trades with MFE > 5×) of **0.96 % vs 0.24 %**.
   Per §5h's own lesson — *the surviving results of this programme are distribution-shape claims, not
   mean claims, and that is precisely why they survived* — listing age belongs in **risk shaping or
   as a cross-sectional conditioner**, never as a standalone timing edge this panel can certify.
8. **Reproduction data** from the stress-dislocation lens (full 1h history, 2023-05-12 → 2026-07-31):
   `/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/bz/{WBETHETH,BNSOLSOL,USDEUSDT,USDEUSDC,WBTCBTC}.csv`.
   Copy anything wanted out of the scratchpad before it is reaped.

---

## 6. What a SIZE round would have to look like to succeed

Stated so the next round is not a seventh power census with a different costume. Given §3, a
candidate that could actually clear this mandate must satisfy **all** of:

- **Contractual bounded loss.** Long premium, or a redeemable claim. Not a stop. Failing this, the
  convexity is path luck and the MFE-derived win is unachievable (§3).
- **A deciding P&L that exists in a free archive**, or an explicit acceptance that promotion requires
  **N months of forward quote collection** with N stated up front and the design frozen before
  collection starts. The Deribit live API is free — a daily wing-quote panel started today costs
  calendar time and nothing else, and is the only identified route out of the §3 dilemma. If it is
  ever going to be started, starting it *early* is worth more than choosing which theory it serves.
- **An arrival rate measured in the archive before the harness is written** (§4.1), with the
  observation unit being the **independent episode** (market-wide cascades and roll-weeks collapse to
  one draw, not thirty).
- **A power census computed on the estimator that will actually be used** — the T15 rule. Count what
  the estimator compares, not what the dataset holds. Five theories this round quoted an n from the
  dataset (10 M symbol-bars, 5,400 events) while the estimator compared a few dozen episodes.
- **A magnitude claim whose mean is not carried by an assumed decile** (§4.2).
- **A conditional cost model** — the conditional spread at the entry instant, or none at all.
- **A filter-off control arm**, mandatory for any candidate whose novelty is a conditioner.

If a proposal cannot satisfy the first two, it should not be written up. The first two are where
seventeen of eighteen died this round.

---

## 7. Recommendation to the owner

1. **Allocate nothing.** Zero picks; no strategy from this round reaches a freeze-then-test design.
2. **Spend one afternoon** on salvage item 1 (the cascade gross census) and one hour landing salvage
   items 2–5 into `FINDINGS.md` §8. Together they retire the liquidation-capture, named-liquidation,
   covered-call-ETF-flow, unlock-timing and funding-clamp families permanently, for well under a day.
3. **Land the `B22B` correction** (§4.8) as an annotation on the JSON — it has now been misread by
   three independent candidates in one round and will be misread again.
4. **Decide one thing, and it is the only genuine fork here:** whether to start a **forward Deribit
   wing-quote panel** now. It is free, it is the single identified escape from the §3 dilemma, and
   its cost is exclusively calendar time — which means the cost of *not* starting it compounds. It
   does not commit to any strategy; it buys the option to test the entire long-convexity family in
   12–24 months instead of never. **My recommendation is to start it**, with a plain daily collector
   and no strategy attached.
