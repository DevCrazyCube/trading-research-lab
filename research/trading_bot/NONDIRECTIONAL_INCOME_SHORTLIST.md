# T21 — the ranked NON-DIRECTIONAL income shortlist

**What this is.** A survey and ranking of **14 retail-accessible income mechanisms that do not
require predicting price**, across crypto and equities/ETFs. The programme is 0-for-8 on
directional prediction; this document asks whether the *other* family — getting paid to bear a
risk or supply a service — is any better, and answers it with first-party measurement wherever
free data allowed.

**Status.** Survey **plus first-party measurement**. §3 (crypto perp funding carry), §4 (the
equity variance risk premium) and §2 (the accessibility audit) are our own numbers, taken
2026-08-19 against the Binance public API, Hyperliquid, Kraken, CBOE, FRED and the Alpaca SIP /
paper account. Everything attributed to the literature or to a fee schedule is cited, not
verified, and is marked.

**Nothing here is a certified result.** Every number in §3 and §4 was computed *after* looking at
the data, with rules chosen *after* seeing earlier passes fail. Two of them carry leakages I
found in my own work and state below. They are **scoping and power estimates**, exactly the
artefact `T15_RESULT.md` says should precede a harness — not a backtest anybody may act on.

---

## 0. The one rule this document is organised around

> **Every income mechanism is payment for a risk or a service. There is no free income.**
> A mechanism whose risk cannot be named and sized is not a candidate; it is a mechanism whose
> risk has not been found yet.

So each entry below names the risk in the same sentence as the yield, and the ranking is
**net income per unit of the risk it bears, times testability** — never gross yield.

The second organising fact, which reorders half the list and which no prior document here states:

> **Most crypto income mechanisms are not legally available to a US retail person.** Binance.com
> perpetuals — the venue holding the data this programme owns — do not serve US persons.
> Binance.US has no perpetual market. This is an accessibility constraint of the same kind as
> `EDGE_SHORTLIST.md` §5's "Alpaca will not lend you the name", and it is scored as `A`, not
> waved away.

---

## 1. The rubric

Each candidate scores **1–5, higher is better**:

- **N — genuinely non-directional.** 5 = delta-neutral by construction and the neutrality was
  checked. 1 = "market-neutral" in the marketing sense only.
- **I — realistic NET income per unit of the risk borne**, after measured fees, measured spreads,
  and after the specific tail is priced. Not gross yield.
- **A — retail accessibility**, including legal availability to a US person and custody form.
- **D — data we ACTUALLY hold or can get free today**, per §2. A 403 scores 1.
- **T — testability**: can a leakage-free, survivorship-complete, adequately powered frozen test
  be built from `D`?

Total is the unweighted sum. **Ties break on D then T** — the programme's earned ordering, and
`T15`'s rule applies throughout: *a candidate whose minimum detectable effect exceeds the effect
it is looking for is dead before it is tested.*

---

## 2. What we actually hold — probed live, 2026-08-19

| capability | probe result |
|---|---|
| **Binance USDT perpetual funding history** | free, no key. **527 perps TRADING**, 357 with a Binance USDT **spot** leg. History to **2019-09-10** (BTC). ~1.07 M funding prints pulled for this document |
| **Binance funding for DELISTED perps** | **still served.** `LUNAUSDT`, `FTTUSDT`, `SRMUSDT`, `AGIXUSDT`, `BLZUSDT` all return history |
| **Binance historical dumps** (`data.binance.vision`) | **920 funding-rate symbol folders**, *including* every delisted name probed. **A survivorship-complete perp panel is constructible for $0** |
| Binance spot klines, order books, exchangeInfo | free, no key |
| **Hyperliquid** (self-custody perp DEX) | free `POST /info`. **232 perps**, 206 also on Binance. Current funding + open interest per asset |
| Kraken public OHLC / AssetPairs | free. `USDTZUSD`, `USDCUSD` daily, 721 bars |
| Coinbase public product feed | free |
| **CBOE index history** (`PUT`, `BXM`, `VIX`) | **free CSV**, daily, PUT usable from 2004-03-16 |
| **FRED** (`DGS3MO`, `DTB3`, `VIXCLS`) | free CSV. 3-month T-bill trailing 12m = **3.843 %**, latest **3.87 %** |
| Alpaca SIP equities/ETF, auctions, corporate actions | as `EDGE_SHORTLIST.md` §2b |
| **Alpaca options (OPRA)** | SPY chains and daily bars confirmed working. **~Feb 2024 → present ≈ 2.5 yr** |
| **Alpaca INDEX options (SPX/SPXW)** | ✗ **404 Not Found.** Only American-style ETF options — see §6.8 |
| **Alpaca crypto** | spot only. `marginable: false`, `margin_requirement: 100`. **No short leg, no perps, no borrow.** The carry trade cannot be expressed at our broker |
| **Solana RPC** (`.env` `SOLANA_RPC_URL`) | ✗ **HTTP 403.** Every on-chain yield/staking/DeFi mechanism scores `D=1` until the owner refreshes it |
| CME futures quotes | ✗ **HTTP 403** on the public quote endpoint |
| Borrow fees / short interest | free FINRA panels only (T16); no borrow *fee* history anywhere free |

**Two entries do most of the reordering.** Alpaca cannot express any crypto carry (no short, no
margin, no perp), and the Solana RPC is dead — so the two data assets the task named as held are
in practice *one* asset (Binance's public API, which is free to anyone) plus a broker that cannot
trade it.

> ### ⚠ CORRECTION, 2026-08-19 — two rows of the table above are WRONG, and both were re-probed by `T25_RESULT.md` §6
>
> | this table says | probed again, same credentials, read-only |
> |---|---|
> | **Alpaca INDEX options (SPX/SPXW) — ✗ 404 Not Found. Only American-style ETF options** | ✗ **WRONG.** `GET /v2/options/contracts?underlying_symbols=SPX` returns `"style": "european"`, `"tradable": true`, **55 expirations out to 2031-12-19**; snapshots and historical daily bars both serve; the paper account is options **level 3**. Only `SPXW` is genuinely empty |
> | **Solana RPC (`.env` `SOLANA_RPC_URL`) — ✗ HTTP 403** | ✗ **WRONG today.** `getHealth` returns **200 `ok`** |
>
> **What this changes.** §6.8 scores the box spread `I = 1, A = 3` **because an American box carries
> early-assignment risk** — on a European, cash-settled SPX box that risk does not exist, so `D`
> 2→4 and `A` 3→4. §6.9 (hedged staking) and §6.11 (DEX LP) are both ranked on the dead RPC.
> **What it does NOT change:** `T25_RESULT.md` §6a then probed the box directly and it still scores
> `I = 1` — at mid the 1-year SPX box lends **+0.37 pp over T-bills**, and at the four-leg
> executable price **+0.06 %/yr, i.e. 3.65 pp BELOW T-bills**. Right score, wrong reason.
>
> **The method point, which is the reason this box is here rather than a silent edit:** a `D` score
> is a *measurement with a date on it*, and this document's own §8 says the accessibility claims
> should be confirmed before they are relied on. Two of them decayed in eleven days.

---

## 3. Crypto perp funding carry — measured first, because the task asks and the data is free

### 3a. What the programme already concluded, and why it needed revisiting

`FINDINGS.md` §5d records **funding carry: dead — below risk-free forward, −0.46 pp vs T-bills,
needs +1.47 pp for tail risk** (`agent_discussion.md` Seq 670–672). That work was correct and it
is not overturned here. But it tested exactly one thing: **BTC, always in carry, unconditionally.**
It never asked whether *choosing which perp to carry* changes the answer. That is the gap this
section closes.

### 3b. The cross-section, 12 months, 345 perps with a spot leg

Annualised realised funding (a short-perp/long-spot carrier **receives** this):

| p1 | p5 | p10 | p25 | **p50** | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|
| −154.0 % | −82.8 % | −59.4 % | −25.4 % | **−5.2 %** | +2.0 % | +5.7 % | +7.3 % | +10.4 % |

Mean **−18.1 %/yr**; only **34.2 %** of perps had positive 12-month funding. BTC **+3.29 %**,
ETH **+2.32 %**, SOL **−1.60 %**.

> **The first finding, and it inverts the folk story.** The alt-perp complex has been paying
> **longs**, not shorts, for a year. The naive "sell the funding, it's positive" picture is a
> BTC/ETH fact that does not generalise: on the median altcoin perp the carry trade **pays out**.

### 3c. Chasing high funding is NEGATIVELY selected — the decisive negative

Walk-forward, monthly: rank on trailing-1-month realised funding, hold equal-weight one month,
gross of all costs, 22 months (2024-10 → 2026-07).

| book | gross %/yr | ann. sd | worst month |
|---|---|---|---|
| **top 1** | **−70.67** | 73.99 % | −88.31 % |
| top 5 | −11.87 | 15.99 % | −18.58 % |
| top 10 | −2.35 | 8.86 % | −9.47 % |
| top 20 | −0.46 | 5.46 % | −4.61 % |
| top 100 | +1.08 | 2.33 % | −1.24 % |
| **all 357, equal weight** | **−9.67** | 3.61 % | −3.03 % |
| **BTC only** | **+5.01** | 1.22 % | −0.18 % |

**Ranking on funding and taking the richest name loses 70 %/yr gross.** Rich funding on a small
perp is not a payment you collect; it is the *market pricing an imminent reversal*, and one-month
persistence at that end of the distribution is negative. Cross-sectional funding persistence over
a **year** is real (Spearman ρ = **+0.481**, prior 12 m vs next 12 m, n = 253) and it does not
survive being pushed to the extreme tail at monthly horizon.

### 3d. A liquidity screen reverses the sign — and it is where my own leakage lives

Restricting to the **44** perps quoting ≥ \$20 M/day:

| book | gross %/yr | ann. sd | worst month | next-month funding **negative** on |
|---|---|---|---|---|
| liq, top 3 | **+9.67** | 3.08 % | −2.54 % | 4.5 % of picks |
| liq, top 5 | +7.27 | 2.35 % | −1.19 % | 9.1 % |
| liq, top 10 | +5.58 | 2.16 % | −1.32 % | 7.7 % |
| liq, top 20 | +4.26 | 1.68 % | −0.61 % | 11.4 % |

The monotone decline in `topN` is the shape of a real gradient rather than one lucky name. But:

> **⚠ LEAKAGE 1, mine, and I am reporting it because it flatters the result.** The \$20 M screen
> was applied using **today's** 24-hour volume to a **two-year-old** history. Every name that was
> liquid then and is illiquid or delisted now is invisible. `exchangeInfo` currently shows **127
> perps in `SETTLING`** — actively being delisted. Their trailing-180-day funding is **median
> −23.6 %/yr, mean −32.0 %**, only 33 % positive — *and the richest of them (`HFT` +25 %,
> `ATA` +17 %) would have ranked into a top-3 book.* The bias runs toward the conclusion.
>
> **⚠ LEAKAGE 2, also mine.** The threshold (\$20 M), the horizon (1 month) and `topN` = 3 were
> all chosen *after* seeing §3c fail. This is a search-max result of unknown trial count and
> `FINDINGS.md` §5c says exactly what to do about that: it needs DSR against a **declared** trial
> count, on a held-out window, and it has neither.

### 3e. Net, with measured execution cost — the arithmetic that decides it

Cost measured on the 24 names the top-3 book actually held, from live order books:

| | spot spread | perp spread | thinner-leg top-20 depth |
|---|---|---|---|
| median of the held names | **5.2 bp** | **1.7 bp** | **\$52,862** |
| worst (`BANKUSDT`, `ALPINEUSDT`) | 27.7 bp | 2.8 bp | \$17k–72k |
| BTCUSDT for scale | 0.00 bp | 0.02 bp | \$201k |

| step | value |
|---|---|
| gross | **+9.67 %/yr** |
| turnover | **55 % of the book per month** |
| round trip charged | 30 bp published fees + 5.2 spot + 1.7 perp = **36.8 bp** |
| friction drag | −2.41 %/yr |
| net | **+7.26 %/yr** |
| ÷ 1.2 (capital is committed **twice** — spot notional **and** perp margin) | **+6.05 %/yr on capital** |
| less 3-month T-bill (FRED DGS3MO, trailing 12 m) | −3.84 |
| **EDGE OVER RISK-FREE** | **+2.20 pp** |
| in-sample ann. Sharpe / t | 3.14 / **+4.26** on 22 months |

### 3f. And the tail that prices it, which is the whole story

**The breakeven annual venue-failure probability is 2.20 %.** The loss mode is **total**, not
partial — FTX took this exact trade to −100 %. Base rate for venues holding customer crypto:
Mt Gox 2014, QuadrigaCX 2019, Celsius / Voyager / BlockFi / FTX 2022 — **six total-loss events in
twelve years**. Even generously assuming fifty venues ever mattered, that is **~1 %/yr per
venue** — *the same order of magnitude as the breakeven*, exactly as Seq 670 found for BTC-only.

Three further risks, each measured:

1. **Delisting is not a soft exit.** The worst single 8-hour funding print in the currently-
   condemned pool is **−2.00 % of notional** — one interval erasing roughly three months of the
   whole book's carry, while the delisting forces the unwind.
2. **Funding flips.** 4.5 % of top-3 picks had negative funding the following month, and the one
   bad month in 22 (**2026-07, −30.4 %/yr annualised**) is what that looks like.
3. **Capacity is a hard wall.** \$33 k per name — a \$100 k book across three names — is **63 %
   of the visible top-20 depth** on the thinner leg. The 5.2 bp median spread is a **floor**, not
   the cost, at this size. **A \$100 k account is already too large for the top-3 form.**

### 3g. What this changes, honestly

The BTC-only close stands. The cross-sectional form is **better than it — and not enough better**:
`+2.20 pp` over T-bills against `−0.46 pp`, on a venue tail priced at ~1 %/yr, with two known
leakages both running toward the result, and a capacity wall at roughly one third of the account.

**It is the best-scoring mechanism in this document and it is nowhere near a decision.** What it
*is* is the only candidate here that is **fully and cheaply testable**: §2 establishes a
survivorship-complete, 7-year, free panel. See §6 and §7.

---

## 4. The equity side's best non-directional premium — measured, and it dies on our own null

**The variance risk premium is the largest, most stable non-directional premium this programme
has ever measured.** VIX minus the *subsequent* 21-day realised volatility of the S&P 500,
1990-01-02 → 2026-08-14, 9,197 daily observations:

| period | mean VRP | median | share > 0 | worst |
|---|---|---|---|---|
| **full 1990–2026** | **+4.09 vol pts** | +4.71 | **85.8 %** | −71.96 |
| 1990–2000 | +5.44 | +5.50 | 92.5 % | −16.01 |
| 2000–2010 | +3.35 | +4.00 | 81.5 % | −49.91 |
| 2010–2020 | +3.68 | +4.53 | 84.3 % | −28.33 |
| 2020–2026 | +3.65 | +4.64 | 83.7 % | **−71.96** |

On **non-overlapping** monthly windows (the count the estimator actually uses, per the T15 rule):
n = 438, mean **+4.00 pts**, **t = +13.14**, MDE(80 %) 0.85 pts. Held out 2022+: n = 54, **+3.21
pts, t = +3.95**. *The premium is not decayed, not regime-dependent, and is powered.*

**And the tail is the product.** The ten worst readings are all **February–March 2020**: VIX 13.68
on 14 Feb against **84.19** realised over the next 21 sessions. −70 vol points.

### 4b. Harvesting it: CBOE PUT (cash-secured SPX put write), 2004-03-16 → 2026-08-14, 4,936 days

| | CAGR | vol | Sharpe (ex-cash) | max DD |
|---|---|---|---|---|
| **PUT** — SPX put write | **+8.76 %** | 15.72 % | **+0.51** | −37.09 % |
| S&P 500 total return | +12.87 % | 21.15 % | +0.60 | −55.25 % |
| **N1 null** — 0.743 × SPXTR + 0.257 cash, vol-matched | **+10.30 %** | 15.72 % | **+0.60** | −43.58 % |
| 3-month T-bill | +1.53 % | — | — | — |

> **PUT minus the de-risked buy-and-hold null: −1.53 pp/yr of CAGR, Sharpe −0.090, paired daily
> t = −0.93.** It buys **+6.48 pp** of maximum drawdown and pays 1.53 pp/yr for it. And
> `β(PUT, SPXTR) = 0.674` — **the standard retail expression of "market-neutral income" is 67 %
> long equity.**

This is the **third** family `t13_risk_shaping.py`'s N1 null has killed (crash filter, vol
overlay, now put-write), and it is the exact shape of `FINDINGS.md` §5b: *the premium is real and
harvesting it is not an edge.* Its worst months are worse than the null's in five of six
(2008-10: PUT −17.65 % vs N1 −12.28 %; 2020-03: −13.42 % vs −8.67 %) — **it delivers its
drawdown protection everywhere except where drawdown protection is wanted.**

**What is NOT settled by this:** the *delta-hedged* short straddle, which is the genuinely
neutral expression and isolates variance from direction. PUT does not measure it. Its own problem
is data — §2 gives us **2.5 years** of OPRA option bars, which cannot certify anything at the
Sharpe this family plausibly carries (`T10`'s arithmetic: S = 0.8 needs 12.2 held-out years) —
and the literature's own finding that continuous delta-hedging costs consume most of the premium
at retail size. Ranked accordingly.

---

## 5. The ranked shortlist

| # | mechanism | what is being PAID FOR | N | I | A | D | T | **tot** |
|---|---|---|---|---|---|---|---|---|
| **1** | **Crypto perp funding carry, cross-sectional, liquidity-screened** (long spot / short perp) | supplying the short side to leveraged longs; bearing venue, delisting and funding-flip risk | 5 | 3 | **2** | **5** | **5** | **20** |
| **2** | **Crypto perp funding carry, BTC/ETH only** | same, on the two names with real depth | 5 | 2 | 2 | 5 | 5 | **19** |
| 3 | **Cross-venue perp funding differential** (perp/perp, no spot leg) — **DEAD by insufficient power, `T25_RESULT.md`** | bearing *two* venues' failure risk to collect the gap between them | 5 | 2 | 2 | 4 | 3 | 16 |
| 4 | **Delta-hedged short variance, SPY/ETF options** | selling crash insurance; bearing gamma and jump risk | 4 | 3 | 5 | 2 | 2 | 16 |
| 5 | **Stablecoin depeg reversion** | bearing the risk the depeg is *terminal* (UST 2022 → 0) | 4 | **1** | 3 | 3 | 3 | 14 |
| 6 | **Cash-and-carry basis on CME crypto futures** | same carry, custody replaced by CFTC-segregated FCM risk | 5 | 2 | 4 | **1** | 2 | 14 |
| 7 | **Negative-funding harvest** (long perp / short spot) | supplying the *long* side when funding is negative — the majority regime, §3b | 5 | 2 | **1** | 3 | 2 | 13 |
| 8 | **Box-spread / synthetic financing** on ETF options | lending above T-bill; bearing **American early-assignment** risk | 5 | 1 | 3 | 2 | 2 | 13 |
| 9 | **Hedged staking yield** (stake SOL/ETH, short perp) | protocol service + slashing + lockup + venue risk | 4 | 2 | 2 | **1** | 2 | 11 |
| 10 | **Securities lending income** (fully-paid lending) | lending your shares; bearing counterparty + recall risk | 5 | 1 | **1** | 1 | 1 | 9 |
| 11 | **DEX liquidity provision / AMM fee income** | fee income against **adverse selection** ("impermanent loss") | 3 | 1 | 2 | 1 | 1 | 8 |
| — | **Put-write / covered-call "income"** | equity *direction* plus variance — **not neutral, β = 0.674** | — | — | — | — | — | **DEAD — §4b, this document** |
| — | **CEF discount / NAV arbitrage** | discount convergence | — | — | — | — | — | **DEAD — `T12_RESULT.md`** |
| — | **Cash-merger arbitrage spread** | deal-break risk, and it is correctly priced | — | — | — | — | — | **DEAD — `T11_RESULT.md`** |

**Ranks 3/4 and 5/6 are ties broken on `D` then `T`, per §1** — which promotes the cross-venue
differential above delta-hedged variance, and depeg reversion above the CME rail, on data
availability alone. **A rank is not a recommendation:** §7 recommends the CME probe at rank 6 and
recommends *against* rank 5. The rubric orders candidates by what can be tested; the
recommendation orders them by what is worth testing.

---

## 6. The candidates in detail

### 1. Cross-sectional perp funding carry — 20, and the recommendation

**Mechanism.** A perpetual swap has no expiry, so the exchange forces convergence to spot by
making one side pay the other every 8 hours (4 hours on high-volatility listings). When leveraged
longs dominate, **you are paid to be the short they need**, and you neutralise the price exposure
by holding the spot. **The service is inventory provision to a levered crowd; the risk is that
the crowd flips, the venue fails, or the listing dies.**

**Truly neutral?** **Yes**, and it is one of the few here that is. Long spot X and short perp X
are the same asset; the delta cancels to the basis, which converges by construction. The residual
exposures are basis-at-entry vs basis-at-exit, and liquidation of the short leg if the margin is
not cross-collateralised.

**Realistic net.** §3e: **+6.05 %/yr on capital, +2.20 pp over T-bills**, before pricing a
venue-failure tail whose breakeven is **2.20 %/yr** against a **~1 %/yr** base rate. Both
leakages in §3d run toward the result.

**Data.** **The best in this document.** Free, keyless, **survivorship-complete** (§2: 920
funding-rate symbol folders on `data.binance.vision`, delisted names included; the live endpoint
still serves `LUNAUSDT`), **7 years** (2019-09 → present), with spot klines and order books on the
same rail. A clean design/held-out split is available and has not been burned.

**Capacity. \$30–60 k in the top-3 form**, hard. §3f. This is the "too small for a whale" corner
the task names — and our account is already at its edge.

**Accessibility — the flag.** `A = 2`. **Binance.com perpetuals do not serve US persons; Binance.US
has no perpetual market; and Alpaca's crypto is spot-only, non-marginable (§2), so our own broker
cannot express either leg of the short.** Testing this costs nothing and touches no venue.
*Trading* it requires a venue decision that is **squarely the owner's**, and every custodial
option re-imports the FTX tail that prices the trade. The non-custodial alternative (Hyperliquid,
§2 — reachable, 232 perps) does not remove the tail so much as **change its name from custody risk
to smart-contract and bridge risk**, for which no comparable base rate exists here. **The
availability claims in this paragraph are regulatory/legal facts asserted from general knowledge,
not probed** — see §8.

### 2. BTC/ETH-only funding carry — 19

Same mechanism, on the only two names with genuine depth (BTC spot spread **0.00 bp**, top-20
depth \$201 k; ETH 0.1 bp). Gross **+5.01 %/yr** (BTC) and **+4.90 %** (ETH) over the same 22
months, with worst months of **−0.18 %** and **−0.31 %** annualised — an order of magnitude
quieter than the cross-sectional book.

**And it is the version the programme already closed** (`FINDINGS.md` §5d): net of fees it sits
at or below T-bills and misses its own tail bar by ~1.9 pp. §3b shows why it looked better here
(+5.01 % gross vs the −0.46 pp net conclusion) — **gross is not net, and by-year T-bills matter
enormously**: the fabled +12 % lived in 2019–21 when Treasuries paid ~0. Kept on the list at rank
2 because it is the **capacity-unconstrained** and **depth-safe** version of #1, and because a
frozen test of #1 gets it as a free control.

### 3. Cross-venue perp funding differential — 16

**Mechanism.** The same asset's perp funds differently on different venues. Long the cheap-funding
venue's perp, short the rich one's: **delta is exactly zero, no spot leg, no borrow**, and you
collect the difference. **What you are paid for is bearing the failure of TWO venues instead of
one**, plus the margin-call correlation between them.

**Measured, 2026-08-19 snapshot**, 206 assets on both Hyperliquid and Binance: median
|differential| **2.06 pp/yr**, p75 **11.41**, p90 **32.37**.

**Why it is not higher.** (a) The median differential does **not** cover round-trip friction on
two venues at monthly rotation. (b) **A large share of Hyperliquid readings sit at exactly
+10.95 %/yr — the protocol's baseline rate — so much of the raw "differential" is a clamp, not a
dislocation.** (c) The custody tail is *doubled*, not diversified: you need collateral at both
venues simultaneously, and either failing takes the whole position. (d) One snapshot is not a
carry; persistence is unmeasured.

**Data `D = 4`, `T = 3`.** Hyperliquid's API is free and its historical funding is retrievable,
but building a matched two-venue panel is real work and the snapshot does not justify it yet.

> **STATUS: DEAD BY INSUFFICIENT POWER — `T25_RESULT.md` (2026-08-19), gate `3cc5759d…` frozen
> first, held-out window NOT spent.** The matched panel was built (106 coins, **2,340,613**
> Hyperliquid hourly prints, 41 of 41 delisted names recovered) and it cannot see the effect:
> MDE **6.30 pp/yr** held out and **2.85 pp/yr on the entire joint history of both venues**, against
> a 1.07 pp/yr claim — **22.5 years needed, 3.3 available**, because Hyperliquid is 3.3 years old.
>
> **And §6.3's snapshot was the wrong instrument, measured against itself.** Realised *monthly*
> `|differential|` is p50 **5.04** / p75 **8.66** / p90 **16.16** pp/yr, against the single-interval
> snapshot's 2.06 / 11.41 / 32.37 — the snapshot **overstates the p90 by 2.0×** and **understates
> the median by 2.4×**. A one-interval cross-section is not a month's carry.
>
> **What survives:** the trailing differential calls next month's **sign 79–84 %** of the time and
> is genuinely persistent (Spearman **+0.391**, the opposite of T23's finding for funding *levels*)
> — and in the burned window **not one of the four declared `topN` clears the +1.00 pp/yr bar**
> (best +0.738, t 0.53; `topN=20` **−1.47, t −2.43**). Halving the differential for collateral at
> two venues and then subtracting a 3.84 % T-bill is what does it. **The signal works and loses to
> Treasury bills.** Capacity is the second wall: measured Hyperliquid top-20 depth is a median
> **\$33,309**, so at 10 % of depth per name the `topN=3` book caps at **\$10 k** and `topN=20` at
> **\$67 k** — below the account.

### 4. Delta-hedged short variance, SPY/ETF options — 16

**Mechanism.** §4 measures the premium at **+4.09 vol points**, positive in **85.8 %** of months
and stable across four decades. **You are paid to sell crash insurance.** The delta-hedged short
straddle isolates that payment from direction — which is what makes it, unlike the put-write
killed in §4b, a genuine
candidate.

**Truly neutral?** Neutral to *direction*, by construction and continuously re-hedged. **Not**
neutral to volatility-of-volatility or to jumps: the hedge is exact only in the limit of
continuous, costless trading, and gaps are precisely when it is needed.

**Realistic net.** Unknown to us, and the honest answer is that the two forces are the same size:
the premium is ~4 vol points; hedging costs at retail size on a 21-day straddle are a
literature-cited (not measured) majority of it.

**Why `D = 2` and `T = 2` sink it.** Alpaca gives **2.5 years** of OPRA bars. `T10`'s resolution
arithmetic — `(2.80/S)²` years to certify Sharpe `S` — says 2.5 years certifies nothing below
`S = 1.77`. **A power census, not a harness, is the first move here**, and it will very probably
return `DEAD-BY-INSUFFICIENT-HISTORY`. §2's SPX/SPXW 404 also means the cheap, European-style,
cash-settled instrument is unavailable to us.

### 5. Stablecoin depeg reversion — 14

**Mechanism.** Buy the stablecoin below peg, hold to repeg. **You are paid for bearing the risk
that the depeg is real** — that the reserve does not exist, which is the terminal state.

**Measured, Kraken daily, 721 bars (2024-08 → 2026-08):** `USDT` low **0.95179**, `USDC` low
**0.98580**. Deviations exceeding 50 bp on **3.2 %** of days (USDT) and **4.0 %** (USDC).

**Why `I = 1`.** ~11–15 exploitable events a year at ~50 bp each is **~6–7 %/yr gross at 100 %
deployment**, against retail taker fees on a stablecoin pair that are of *the same order as the
dislocation itself* — and a tail that is not a drawdown but a **zero** (Terra/UST, May 2022). The
payoff is a short put on a private company's reserve attestation. **This is a friction-floor
death with a solvency tail bolted on**, and it wants no further work.

### 6. CME crypto-futures cash-and-carry — 14

**The same mechanism with the FTX risk removed** — a CFTC-regulated exchange, segregated customer
funds at an FCM, US-legal for retail, micro contracts sized for a \$100 k account. It is the
*right* answer to §3f's venue tail, and it is ranked fifth solely on `D = 1`: **the public CME
quote endpoint returns 403** (§2), we hold no futures broker, and the basis history is not free
to us. Worth a single bounded probe — *is there a free CME settlement-price history* — before it
is written off, because if the answer is yes it inherits #1's entire mechanism at `A = 4`.

### 7. Negative-funding harvest (long perp / short spot) — 13

**§3b's finding taken seriously:** the median alt perp paid **−5.2 %/yr** and the mean **−18.1 %**
over the last year, i.e. **shorts paid longs**. The mirror trade — long the perp, short the spot —
collects that. **`A = 1` is what sinks it:** the spot short requires a margin borrow, alt-coin
borrow rates on a crypto venue are unpublished, punitive and recallable, and no free history of
them exists. **A carry whose funding cost is the unmeasured leg is not a measurable carry** — the
same defect that made `EDGE_SHORTLIST.md` #9 unrankable.

### 8. Box spread / synthetic financing — 13

Sell a box (long call spread + short put spread at the same strikes) and you have **borrowed** at
the implied rate; buy one and you have **lent** — a pure financing trade with zero delta. Retail
level-3 approved on our paper account. **`I = 1` and `A = 3`, and the reason is §2's 404:** with
no SPX/SPXW, only **American-style ETF options** are available, and an American box carries
**early-assignment risk** that converts a "riskless" financing trade into an unhedged stub at the
worst moment. The spread over T-bills on the retail-accessible version is tens of basis points,
which is not worth an assignment tail.

### 9. Hedged staking yield — 11

Stake SOL/ETH for the protocol's issuance, short the perp to remove the price exposure.
**Paid for:** validating (a real service), and bearing slashing, unbonding-lockup and validator
risk **on top of** the perp venue's. The lockup is the specific killer: the hedge must be
maintained through an unbonding period during which the staked leg cannot be sold. **`D = 1`:
our Solana RPC returns 403** (§2), so even the issuance rate is not currently queryable from held
credentials.

### 10. Securities lending income — 9

The purest "get paid for a service" on the list: lend your shares, receive part of the borrow fee.
**Risk:** counterparty, collateral, and recall at the worst time. **`A = 1`, `D = 1`:** Alpaca
runs no fully-paid lending programme available to us, and no free borrow-fee history exists
(`T16_FREE_PANELS.md` measured ρ(days-to-cover, borrow fee) = **−0.40** — the free proxy is
*anti*-correlated with the thing). Recorded, not pursued.

### 11. DEX liquidity provision — 8

Fee income for quoting both sides of an AMM. **What is actually being paid for is adverse
selection** — "impermanent loss" is the polite name for systematically selling the winner and
buying the loser to informed flow, and it is the same mechanism `FINDINGS.md` §7 identifies as
causing illiquidity in equities. `D = 1` (Solana RPC 403), `T = 1`, and the honest prior from the
literature is that fee income and adverse selection roughly cancel for passive LPs. Last.

### The three DEAD entries, kept so the survey is complete

**Put-write / covered-call "income" — DEAD, killed in §4b of this document.** On this programme's
own N1 null it loses **1.53 pp/yr of CAGR at matched volatility**, with Sharpe **−0.090** and
paired **t = −0.93**, and it is **β = 0.674 long equity**. It is not non-directional and it is not
income; it is a levered-down equity position with the right tail sold off, and its worst months are
*worse* than the null's. Listed so the family is closed by measurement rather than by opinion, and
so nobody re-proposes a JEPI/QYLD-shaped "monthly income" product here again.

**CEF NAV convergence and cash-merger arbitrage — DEAD, and already dead before this survey.**
`T12_RESULT.md`:
held-out **−0.27 bp/week**, DSR **0.1542**, and a measured CEF half-spread of **11.53 bp** —
99× SPY. `T11_RESULT.md`: **DEAD on all five frozen gates**, and it is the one candidate in this
programme killed by a **tail rather than by friction** — on the cleanest 317 deals the spread is
a genuine **+6.66 %/yr over T-bills** with a **break-even deal-failure rate of 6.68 %**, inside
the 5–10 % quoted band. **`T11` is the exact template for how every entry above should be read:
the spread was real, and it was correctly priced.**

---

## 7. Recommendation

### Primary — freeze and test #1, the cross-sectional perp funding carry

**Not because it is likely to pay.** Because it is the only mechanism in this document where a
**leakage-free, survivorship-complete, adequately-powered frozen test can be built for \$0**, and
because my own quick pass contains two leakages that both flatter it, so the honest number is
unknown rather than known-good.

The test that should be pre-registered:

1. **Power census FIRST, before a line of harness** — the mandatory gate `T15_RESULT.md` earned.
   Compute the MDE on **the estimator that will actually be used** (a `topN` monthly book uses
   `n_months`, not `n_funding_prints`). At the in-sample Sharpe of 3.14 the requirement is under a
   year; at a more believable 1.0 it is 7.8 held-out years, and we can obtain **7**. **If the
   census fails, stop there** — two candidates have now died for one afternoon this way.
2. **Survivorship-complete universe** — built from the **920** `data.binance.vision` symbol
   folders, *including delisted names*, never from live `exchangeInfo`. This is the fix for
   Leakage 1 and it is the single most important design element.
3. **Point-in-time liquidity screen** — computed from that month's own klines, never from today's
   volume.
4. **Declared trial count and DSR ≥ 0.95**, with the `topN`, the horizon and the threshold all
   frozen in the pre-registration. Fix for Leakage 2.
5. **Charge measured spread and fees**, not published fees alone — §3e. And **charge the funding
   cap on any position held into a delisting**: −2.00 % of notional in one interval is measured,
   not hypothetical.
6. **A capacity gate declared first:** the rule is dead at any book size where the required
   per-name notional exceeds the measured depth. At \$100 k that is already 63 %.
7. **Benchmark = T-bills by year (FRED DGS3MO), not a flat rate** — Seq 670 shows this single
   choice moves the verdict.
8. **And the gate that outranks all of them:** even a clean pass yields ~2 pp over risk-free
   against a ~1 %/yr venue-failure base rate. **The pre-registration should state the required
   edge — including the tail charge — before the number exists**, exactly as Seq 670 did with
   +1.47 pp. If the frozen bar is not cleared, it is dead regardless of significance.

### Secondary — one bounded probe, hours not days: is free CME crypto-futures settlement history obtainable?

Because #6 is **#1's mechanism with the tail that prices it removed** — US-legal, CFTC-regulated,
segregated, and expressible for retail — and its only weakness is `D = 1`. If a free settlement
series exists, #6 leapfrogs #1 and the venue question resolves itself. If it does not, we have
lost an afternoon and #1 stands. This has the M0/B22A shape the programme keeps rewarding: bounded,
a measurement rather than a search, and **either outcome is worth having.**

### What I recommend AGAINST, and why

- **Any equity option-writing income strategy.** §4b closes the directional form on this
  programme's own null, and the neutral form is power-blocked by 2.5 years of data.
- **Stablecoin depeg and DEX LP.** Friction floor plus a solvency tail, and a dead RPC.
- **Chasing high funding without a liquidity screen.** −70.67 %/yr gross. §3c.

### The owner-facing decision, stated plainly and not decided here

**Every custodial crypto mechanism on this list re-imports the FTX tail, and that tail is roughly
the same size as the entire edge.** Testing costs nothing and touches no venue. **Trading requires
choosing a custody model — custodial exchange, self-custody DEX, or a US-regulated futures
rail — and that is a scope and risk call for the owner, not a technical one.** Per
`MEMORY.md`, it is put here with a recommendation (the CME rail, if the data exists) rather than
inferred from the fact that the carry is measurable.

---

## 8. What this document does not claim

- **No mechanism here has passed a frozen test.** §3 and §4 are scoping measurements taken after
  looking at the data, with rules chosen after earlier passes failed.
- **§3d contains two leakages I found in my own work**, both running toward the result, and they
  are stated in the same section as the number rather than in a footnote.
- **Fee schedules are cited, not verified.** The 30 bp published-fee round trip in §3e is
  Binance's stated VIP-0 tier; the *spreads* beside it are our own live measurement.
- **The US-accessibility claims are asserted from general knowledge, not probed** — that
  Binance.com perpetuals do not serve US persons, that Binance.US lists no perpetual, that CME
  crypto futures are retail-accessible through an FCM, and that Hyperliquid's frontend is
  geo-restricted. **They are load-bearing for the `A` column and for the whole recommendation in
  §7, so they should be confirmed against each venue's own terms before any venue decision.**
  What *was* probed is narrower and firmer: **Alpaca's own crypto assets are non-marginable with a
  100 % margin requirement**, so our broker cannot express the short leg regardless of venue law.
- **Snapshots are not carries.** §6.3's cross-venue differential is one funding interval.
- **`N`, `I` and `A` are judgements; `D` and `T` are measured** — which is why ties break on them.
- **No purchase, no order, no custody action, no account was created**, and nothing here
  authorises real-money execution, which remains owner-gated.

---

*First-party measurements taken 2026-08-19 against the Binance public REST API (1,074,296 funding
prints across 357 perps, plus live order books), Hyperliquid `POST /info`, Kraken public OHLC,
CBOE index history, FRED (`DGS3MO`, `DTB3`, `VIXCLS`), this repository's `t13_cache` S&P series,
and read-only GETs against the Alpaca SIP and paper endpoints. No order was placed and no venue
account exists.*
