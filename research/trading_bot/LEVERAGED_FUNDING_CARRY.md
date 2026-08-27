# T22 — LEVERAGED crypto funding carry: the max survivable leverage, measured

**Question the owner asked.** T21 ranked crypto perp funding carry #1 among non-directional
income at **+2.20 pp/yr over T-bills**. Coinbase offers ~50x, Hyperliquid 40x, Binance 125x.
*Does leverage turn +2.20 pp into meaningful ~daily income, and what leverage survives the
liquidation / basis-blowout / venue-failure tail?*

**Answer: DEAD at every useful leverage, and it dies twice for two independent reasons.**

> **1. Leverage cannot amplify a cash-and-carry book.** The spot leg is unlevered cash and is
> 83–98 % of the committed capital. Raising the perp leg from 5x to 50x moves book leverage
> `λ = N/C` from **0.833 to 0.980** — a **+17.6 % income uplift, capped, forever** — while raising
> the annual liquidation count on the perp leg from **3.1 to 33.0** and taking the 2023–2026 BTC
> book from **+0.66 pp to −14.18 pp/yr against T-bills**.
>
> **2. To lever the *book* you must borrow, and the thing leverage multiplies is not positive.**
> `income/C = r_b + λ·(f − r_b) − c`. The spread `f − r_b` — perp funding minus the market price
> of leveraged USD financing — is **−0.81 pp/yr since 2024-01-01, t = −4.15 on 942 days, positive
> on only 38.2 % of them**; pooled from 2023 it is **−0.13 pp, t = −0.80**, i.e. zero. The two
> rates have a 30-day-level correlation of **0.934** — they are the same rate. At the pessimistic
> reading every turn of leverage subtracts ~0.8 pp/yr; at the *generous* reading leverage adds
> exactly nothing and still buys the liquidation tail.
>
> **The basis tail is not what kills it.** The measured basis tail permits λ ≈ 8.8–16x. The
> economics bind first, at λ ≈ 1. That is the finding: **the exchange's 50x is not dangerous
> generosity, it is irrelevant generosity — there is nothing to amplify.**

**Best surviving configuration, on the most recent 3.6 years:** Binance BTC cash-and-carry at
**L = 4** on the perp leg → **+0.71 pp/yr over T-bills**, whose **breakeven venue-failure
probability is 0.68 %/yr against a ~1 %/yr base rate**. Full-Kelly sleeve: **0 %**. On a
\$100,000 account that is **\$1.95/day before the tail, and negative after it.**

---

## 0. What is first-party here, and what is not

**Probed live 2026-08-19** (free, keyless, no account, no order, no funds — guardrail 1):

| source | what was taken |
|---|---|
| `data.binance.vision` | **3,433,455 aligned 1-minute bars**, 2020-01-01 → 2026-07-31, of BTCUSDT **perp mark price**, **index price**, **perp last**, and **Binance spot** — the four series needed to model both legs and the maintenance trigger |
| `data.binance.vision` | **23 BTCUSDT quarterly futures** contracts, daily, 2021-02 → 2026-07 (2,127 contract-days) |
| held repo data | `research/data/btc_perp_funding_binance_2019_2026.csv` — 7,586 8-hour funding prints, 2019-09-10 → 2026-08-12 |
| `fapi.binance.com` + `binance.com/bapi` | leverage brackets & **maintenance-margin rates** for 1,007 perps; **multi-asset collateral haircuts**; **cross-margin borrow rates for 467 assets** |
| Hyperliquid `POST /info` | `meta` (232 perps, per-asset max leverage, **margin tables**, collateral token), and **28,115 hourly funding + premium prints per coin** for BTC/ETH/SOL, 2023-05-12 → 2026-08-19 |
| Coinbase International `api.international.coinbase.com` | 264 perps with `base_imf`, position limits, price bands; **29,905 hourly funding prints** for BTC-PERP, 2023-03-22 → 2026-08-19 |
| Coinbase Advanced `api.coinbase.com/api/v3/brokerage/market` | 101 FCM futures products incl. the **US perp-style futures**; 358 daily candles of `BIP-20DEC30-CDE` vs `BTC-USD` |

**Cited, not probed** — and marked wherever used: every **fee schedule**, every **legal
availability** claim, Hyperliquid's **maintenance-margin rule** and **mark-price formula**,
Binance's **Portfolio-Margin eligibility**, and the venue-failure incident history. Guardrail 1
forbids the account that would verify them.

**One deliberate gap, stated up front.** Coinbase's **US-accessible** perpetual-style futures
publish `funding_rate: ""` on every public endpoint reachable without a key. *The only
US-retail-legal perp rail in this document is the one whose funding history cannot be measured.*

---

## 1. VENUE MAP

### 1a. What each venue actually is

| | **Binance USDⓈ-M** | **Hyperliquid** | **Coinbase International** | **Coinbase US (CDE/FCM)** |
|---|---|---|---|---|
| product | perpetual swap | perpetual swap (on-chain CLOB) | perpetual swap | perp-**style** *expiring* future |
| ticker probed | `BTCUSDT` | `BTC` | `BTC-PERP` | `BIP-20DEC30-CDE` |
| **max leverage, BTC** | **125x** (bracket 1 shows `maxOpenPosLeverage 150`) | **40x** | **50x** (`base_imf 0.02`; `default_imf 0.20` = 5x default) | set by the **FCM**, not the venue (`risk_managed_by: MANAGED_BY_FCM`, `max_leverage` empty) |
| max leverage, ETH / SOL | 125x / 100x | **25x / 20x** | 50x / 50x | FCM |
| **maintenance margin, BTC** | **0.40 %** < \$300k notional; 0.50 % to \$800k; 0.65 % to \$3 M; 1.0 % to \$12 M; 2.0 % to \$70 M | **1.25 %** — HL's rule is half the initial margin at max leverage, i.e. `1/(2·40)` *(cited)* | not published on the public API; `base_imf` 2 % is the **initial** requirement | FCM/CFTC SPAN-style |
| funding interval | **8 h** | **1 h** | **1 h** | (mechanism exists, rate not public) |
| margin modes | isolated / cross / **Multi-Assets** / Portfolio Margin *(eligibility cited)* | cross or isolated, **USDC-only collateral** (`collateralToken: 0`, probed) | cross portfolio margin | FCM margin account |
| **spot leg cross-collateralisable?** | **yes** — Multi-Assets mode, at a probed **5 % haircut** | **no** — HL spot lists 490 HIP-1 tokens and **no BTC**; perp collateral is USDC only | partially (USDC-quoted; spot on the same venue) | **no** — spot is at Coinbase Consumer/Advanced, futures at the FCM |
| custody / failure form | **omnibus custodial** | **self-custody + bridge + validator set** | **omnibus custodial** | **CFTC-segregated at an FCM (CEA §4d)** |
| **US retail legal?** | **no** *(cited)* | **no** for the US-blocked front end; the chain is permissionless *(cited)* | **no** *(cited)* | **YES** — the only one |
| taker / maker fee *(cited)* | 0.050 % / 0.020 % | 0.045 % / 0.015 % | 0.060 % / 0.020 % | per-contract, ~\$0.10–0.30 on a \$643 contract |

Probed detail worth naming: Coinbase International runs a **2 % price band** and **±7 % daily
limits** on BTC-PERP (`limit_up 68791.4 / limit_down 59790.8` against a 64,302 mark). Binance
runs none. A price band is a *feature* for a carry book — it caps the basis blowout — and a
*bug* when you need to exit through it.

### 1b. Which venues actually pay, measured

BTC perp funding a short receives, annualised, **first-party**:

| year | Binance (8 h) | Hyperliquid (1 h) | Coinbase Intl (1 h) |
|---|---|---|---|
| 2019 | +7.48 % | — | — |
| 2020 | +17.19 % | — | — |
| **2021** | **+30.61 %** | — | — |
| 2022 | +4.16 % | — | — |
| 2023 | +7.87 % | +15.06 % | −140.30 % *(launch artefact, thin book)* |
| 2024 | +11.92 % | +24.14 % | +12.91 % |
| 2025 | +5.13 % | +10.63 % | +5.99 % |
| **2026 YTD** | **+2.15 %** | **+4.21 %** | **+1.75 %** |
| trailing 365 d | **+3.24 %** | **+6.05 %** | **+2.92 %** |
| trailing 180 d | +1.96 % | +3.87 % | +1.32 % |

**Three independent venues, one monotone decay.** 2026 BTC funding on Binance is **+2.15 %/yr**
against a **3.84 %** 3-month T-bill: *the unlevered BTC carry is currently paying less than cash,
gross of every fee.* 31.0 % of 2026 prints are negative, against 7.3 % in 2021.

On the 28,683-hour window all three overlap (2023-05-12 → 2026-08-19):
**Binance +7.26 %/yr, Hyperliquid +12.72 %, Coinbase Intl +7.56 %.**

> **Hyperliquid is the richest payer by ~5.5 pp/yr and it is not close.** It is also the venue
> where the spot leg **cannot** be cross-collateralised (probed: USDC-only collateral, no BTC
> spot market), i.e. **the highest-paying venue forces the most dangerous margin structure.**
> §3 prices that.

### 1c. What is actually reachable by a US retail person

Probed: `api.coinbase.com/.../products?contract_expiry_type=PERPETUAL` returns **150 products,
every one of them suffixed `-INTX`** and `risk_managed_by: MANAGED_BY_VENUE`. **The 50x perp is
the International product.** The US rail is a separate set of 101 `-CDE` contracts on Coinbase
Derivatives, `risk_managed_by: MANAGED_BY_FCM`:

- `BIP-20DEC30-CDE` "nano BTC Perp", **0.01 BTC** per contract (~\$643), expiry **2030-12-20**,
  listed **2025-07-18**, 24 h notional ~\$263 M.
- `ETP-20DEC30-CDE` nano ETH Perp, 0.1 ETH.
- **The "index perps":** `US5` (US500), `TEK` (Tech100), `CHN` (China), `DEF` (Defense),
  `AIP` (AI) — *equity* index perp-style futures. **`US5-19DEC30-CDE` returned exactly 3 daily
  candles.** They are days old. `D = 1`, `T = 1`: there is no history to test and none will
  exist for years.

I measured the US product's basis directly — 358 daily closes of `BIP` against Coinbase spot
`BTC-USD`:

| | mean | median | p5 | p95 | min | max | share > 0 |
|---|---|---|---|---|---|---|---|
| BIP − spot | **+1.70 bp** | +1.65 | −3.83 | +7.50 | −18.59 | +10.68 | 71.5 % |
| worst adverse widening, any horizon to 63 d | | | | | | **+29.3 bp** | |

**The US contract's basis tail is 29 bp against Binance's 569 bp** — twenty times tighter, which
is what an exchange-listed, price-banded, FCM-margined contract should look like. And a **+1.70 bp**
mean basis on a contract that expires in 2030 means essentially **all** of the carry has to arrive
as funding — the number that is not published. **The one venue a US person may legally use is the
one whose income stream cannot be measured from free data.**

### 1d. Venue-failure risk, named and sized

- **Binance, Coinbase International — omnibus custodial.** The loss mode is **total**, not partial.
  Base rate from T21 §3f, unchanged and not re-derived here: Mt Gox 2014, QuadrigaCX 2019,
  Celsius / Voyager / BlockFi / **FTX** 2022 — six total-loss events in twelve years, **≈1 %/yr per
  venue** on a generous denominator. **FTX took this exact trade to −100 %:** carry desks were long
  spot on FTX and short the FTX perp, perfectly delta-neutral, and lost everything. *Market-neutral
  is a statement about price. It is not a statement about the venue.*
- **Hyperliquid — a different tail with the same shape.** Self-custody removes the "the exchange
  spent your coins" mode and replaces it with: **bridge risk** (the USDC bridge is a smart contract
  holding the entire collateral pool), **validator/consensus risk** (a small permissioned-ish
  validator set), **HLP-vault socialisation** (the protocol's own market-maker vault absorbs
  liquidation losses and has taken large hits), and **governance settlement risk** — in the
  March 2025 `JELLY` episode validators voted to force-settle an open market at an off-market
  price *(cited, not probed)*. **No comparable multi-decade base rate exists for any of these.**
  An unmeasurable tail is not a smaller tail. Hyperliquid's +5.46 pp/yr funding premium over
  Binance is *the market's price for exactly this*, and §5 shows it does not cover it.
- **Coinbase US / CDE — genuinely different.** Customer funds are **segregated at an FCM under
  CEA §4d** and the contract is cleared. This is the FCM tail (MF Global 2011, Peregrine 2012),
  which is real but roughly an order of magnitude smaller than the offshore-crypto tail. **The
  only rail without the FTX tail is the only rail a US person may use — and the only one with no
  free funding data.** That is the whole accessibility knot in one sentence.

> **The 30x–50x offer is adversarial, and the probe shows exactly how.** Coinbase International's
> `default_imf` is **0.20 (5x)** and its `base_imf` is **0.02 (50x)**: the 50x is an opt-in the
> venue must persuade you into. Binance's first bracket carries a **0.40 % maintenance margin
> against 125x initial**, i.e. the position is bankrupt at a **0.80 %** adverse move and the
> venue keeps the remaining margin. §2 measures how often that move happens: **at 125x, 84.7 %
> of one-day windows.** These products are priced to liquidate, and the liquidation is the
> revenue line.

---

## 2. THE BASIS TAIL AND THE MAINTENANCE TRIGGER — modelled on both legs

### 2a. The algebra, stated before the data

Capital `C`. Spot notional `N`, short perp notional `N`. **Two different leverages matter and
conflating them is the entire error this task is about:**

- `L = N / M` — the number the **exchange** advertises. It only sets the size of the margin sliver.
- `λ = N / C` — **book leverage**. It is the only thing that multiplies income.

**Short-perp liquidation, exactly.** For a short of notional `N` entered at mark `P₀`, wallet
balance `M`, at mark `P` with `u = P/P₀`: liquidation when `M + N(1−u) ≤ mmr·N·u`, i.e.

```
u* = (1 + 1/L)/(1 + mmr)          x* = u* − 1 = (1/L − mmr)/(1 + mmr)
```

**Which price moves `u` depends on the margin structure, and that is the whole question:**

| structure | what moves the perp leg's equity | what liquidates it |
|---|---|---|
| **A — two silos** (spot in cash/spot wallet, perp margin isolated; *mandatory* whenever the legs are on different venues, and *mandatory on Hyperliquid*) | the **full mark price** — the spot leg's offsetting gain is in a different account and is **not** credited to the perp margin | a **price rally** of `x*` |
| **C — unified margin** (spot is collateral: Binance Multi-Assets / Portfolio Margin) | only the **basis** `mark/spot` — the legs net inside one equity pool | a **basis divergence** of `b* ≈ 1/λ − mm` |
| **D — perp/perp cross-venue** (no spot leg; both legs on margin) | the **full price**, on **both** legs, in **opposite directions** | a price move of **either sign** past `±x*` |

**`λ` for each:** A → `λ = L/(L+1) ≤ 1`, always. C → `λ = 1` unless you **borrow**. D →
`λ = 1/(1/L_A + 1/L_B)`.

> **The load-bearing consequence, before any data.** In structure A, `λ = L/(L+1)`. At L = 5,
> λ = 0.833; at L = 50, λ = 0.980; at L = ∞, λ = 1.000. **The entire income benefit of going from
> 5x to infinite leverage is +20.0 %, and from 5x to 50x is +17.6 %.** The spot leg is unlevered
> cash and no perp leverage can change that. Everything the exchange is offering above ~5x buys
> you at most a sixth more income and an unbounded amount of liquidation.

### 2b. The measured basis, 3,433,455 minutes

Distribution of the 1-minute basis, 2020-01-01 → 2026-07-31, in bp of price:

| series | p0.1 | p1 | p50 | p99 | p99.9 | p99.99 | min | **max** |
|---|---|---|---|---|---|---|---|---|
| mark − index | −10.46 | −7.10 | −3.16 | +15.60 | +24.75 | +38.23 | −302.59 | **+167.10** |
| **mark − Binance spot** | −14.44 | −7.81 | −3.17 | +15.89 | +25.43 | +45.33 | −467.86 | **+309.82** |
| perp last − Binance spot | −14.63 | −8.21 | −3.71 | +16.95 | +28.31 | +51.94 | −526.22 | **+315.75** |
| index − Binance spot | −11.59 | −4.66 | +0.02 | +4.59 | +11.01 | +31.91 | −404.50 | +306.39 |

The number that matters is not the level but the **adverse forward excursion** from an entry —
`max(mark_t/mark_0 − spot_t/spot_0)` over the holding window, which is exactly the equity loss
per unit notional of a unified book. From **every** 1-minute entry:

| horizon | p50 | p90 | p99 | p99.9 | p99.99 | **max** |
|---|---|---|---|---|---|---|
| 1 h | 2.91 bp | 7.79 | 19.96 | 50.71 | 129.92 | **556.58** |
| 8 h | 6.20 | 15.46 | 43.19 | 119.78 | 294.34 | 556.58 |
| 1 d | 9.23 | 23.62 | 64.08 | 165.24 | 302.72 | **568.97** |
| 7 d | 20.74 | 52.39 | 132.11 | 298.18 | 308.44 | 568.97 |
| 30 d | 38.13 | 101.84 | 296.62 | 310.77 | 315.52 | **568.97 = 5.69 %** |

Conservative intra-minute (mark **high** vs spot **low** in the same minute — the version a
tick-driven liquidation engine sees): median 4.4 bp, p99.9 103.5 bp, **max 1,082.5 bp = 10.83 %**.

**Max survivable book leverage against the measured basis tail** (`mm_u` = 0.5 %):

| tail used | value | `λ_max` |
|---|---|---|
| worst 1-minute-close excursion, 6.6 yr | 5.69 % | **16.2x** |
| worst intra-minute (mark high / spot low) | 10.83 % | **8.8x** |
| p99.99 of 30-day forward excursion | 3.16 % | 27.3x |

And the direct simulation — a unified book walked minute by minute over 3.43 M minutes, notional
re-set to `λ·E` at each event:

| λ | `b*` trigger | P(liquidated in 1 d) | in 7 d | in 30 d |
|---|---|---|---|---|
| 15 | 6.17 % | 0.0000 % | 0.0000 % | 0.0000 % |
| 20 | 4.50 % | 0.0001 % | 0.0001 % | 0.0001 % |
| 25 | 3.50 % | 0.0003 % | 0.0004 % | 0.0005 % |
| **30** | 2.83 % | 0.0420 % | 0.2756 % | **1.2464 %** |
| 50 | 1.50 % | 0.1279 % | 0.8834 % | 3.8193 % |
| 100 | 0.50 % | 1.9062 % | 11.4332 % | 34.0048 % |

> **This is the one place the task's hypothesis is NOT confirmed.** A *genuinely unified-margin*
> carry book is **not** liquidated by basis divergence below λ ≈ 25x. The basis is a well-behaved,
> mean-reverting, exchange-enforced quantity, and Binance's mark price is index-anchored by
> construction, which damps it further. **The basis tail is real but it is not the binding
> constraint.** §5 shows what is.

### 2c. …and the tail arrives in three minutes, so there is no top-up policy

The obvious rebuttal to §2b is "you would just add margin." Measured:

| rise time from basis < 25 bp to the peak | |
|---|---|
| 2021-01-11 08:08 — **+309.8 bp** | **5 min** |
| 2021-12-04 05:26 — +221.9 bp | **2 min** |
| 2021-05-19 12:50 — +169.7 bp | **1 min** |
| 2021-09-07 15:09 — +136.2 bp | 2 min |
| 2020-03-12 10:45 — +129.0 bp | 1 min |
| 2023-10-23 22:42 — +126.8 bp | 1 min |
| *(10 largest events)* | **1–25 min, median ≈ 3.5 min** |

The minute-by-minute anatomy of the worst one is more damning than its size:

```
2021-01-11 08:01   mark 34239.7   spot 34350.4    −32.2 bp
        08:03      mark 34788.6   spot 34350.4   +127.6 bp     <- spot print FROZEN at 34350.4
        08:05      mark 35090.1   spot 34350.4   +215.3 bp
        08:08      mark 35414.6   spot 34350.4   +309.8 bp     <- peak
        08:10      mark 35522.5   spot 35528.1     −1.6 bp     <- spot feed resumes, basis gone
```

**The spot leg's price did not move for eight minutes.** The largest basis event in 6.6 years was
not a market dislocation, it was **a venue outage on the leg that was supposed to be the hedge**.
A liquidation engine that reads a live mark against a frozen hedge will liquidate you, and no
top-up reaches the account in three minutes during the outage that is causing it. **The margin
buffer must be pre-posted. Any leverage number that assumes intervention is fiction.**

### 2d. Structure A — the honest simulation, both legs, every minute

Spot bought with cash, perp short on isolated margin. On liquidation the margin is lost **and the
spot leg keeps its offsetting gain** — modelling only the margin loss would be dishonest in the
other direction. Charged: 5 bp taker each way + 5 bp slippage to re-establish the short. Funding
applied from the held 8-hour series. Notional re-set to `λ·E` after each event. `mmr = 0.40 %`.

**P(the isolated short leg is liquidated), from every 1-minute entry, 2020–2026:**

| L | `x*` | within 1 day | within 7 days | within 30 days |
|---|---|---|---|---|
| 5 | 19.52 % | 0.13 % | 4.83 % | 26.90 % |
| 10 | 9.56 % | 1.87 % | 21.41 % | 55.79 % |
| 20 | 4.58 % | 11.91 % | 49.67 % | 78.26 % |
| **30** | **2.92 %** | **24.90 %** | **65.60 %** | **86.09 %** |
| **40** (Hyperliquid BTC cap) | 2.09 % | 37.06 % | 75.33 % | 89.53 % |
| **50** (Coinbase Intl cap) | 1.59 % | **47.16 %** | 81.13 % | 91.67 % |
| 125 (Binance cap) | 0.40 % | 84.73 % | 95.05 % | 97.74 % |

**Net CAGR of the whole book, after liquidation costs, by regime:**

| L | λ=N/C | `x*` | 2020–2022 | **2023–2026** | full 2020–2026 |
|---|---|---|---|---|---|
| 1 | 0.500 | 99.20 % | +8.59 % | +3.34 % | +5.58 % |
| 2 | 0.667 | 49.40 % | +11.32 % | +4.18 % | +7.33 % |
| 3 | 0.750 | 32.80 % | +12.47 % | +4.49 % | +8.16 % |
| **4** | 0.800 | 24.50 % | +13.13 % | **+4.55 % ← max** | +8.73 % |
| **5** | 0.833 | 19.52 % | **+13.38 % ← max** | +4.50 % | +8.77 % |
| **7** | 0.875 | 13.83 % | +13.19 % | +4.17 % | **+8.82 % ← max** |
| 10 | 0.909 | 9.56 % | +12.55 % | +3.33 % | +8.57 % |
| 20 | 0.952 | 4.58 % | +8.46 % | +0.37 % | +6.39 % |
| **30** | 0.968 | 2.92 % | +3.75 % | **−3.29 %** | +3.74 % |
| **40** | 0.976 | 2.09 % | −1.64 % | **−6.87 %** | +0.60 % |
| **50** | 0.980 | 1.59 % | −6.65 % | **−10.34 %** | −2.40 % |
| 125 | 0.992 | 0.40 % | −50.71 % | −44.14 % | −32.53 % |

**Against the 3.84 % T-bill, 2023–2026: max +0.71 pp at L = 4; −7.13 pp at 30x; −10.71 pp at 40x;
−14.18 pp at 50x; −47.98 pp at 125x.** The curve turns down at **L ≈ 4–7 in every regime** and
crosses zero excess return at **L ≈ 20**.

> **This is the "plot net income vs L and mark where it turns down" deliverable.** It turns down
> at **4–7x**, an order of magnitude below what the venues advertise, and it turns down for a
> reason that has nothing to do with the basis: the perp leg is exposed to the *whole* price move
> because the hedge is in another account.

---

## 3. Hyperliquid specifically, and why its 40x is the worst 40x

HL's published premium index is tight — first-party, 28,115 hourly prints, BTC: p99 +14.5 bp,
p99.9 +24.5 bp, max +52.8 bp; worst 30-day adverse widening **+65.2 bp**. ETH max +43.5 bp;
SOL min **−169.1 bp**.

> **Do not read that as "HL's basis tail is 9x smaller than Binance's."** The `premium` field HL
> returns is the **clamped, funding-purposed premium index**, not the raw mark-vs-oracle deviation
> its liquidation engine uses. HL's mark is a median that includes an HL-book term *(cited)*, so
> the liquidation-relevant deviation is **strictly wider** than the number above. Using the
> published premium as the basis tail would be a leakage running toward the conclusion, so it is
> not used in §5.

**The decisive HL fact is structural, not statistical, and it was probed:** `meta.collateralToken
= 0` (USDC only), and HL's spot universe is 490 HIP-1 tokens **with no BTC**. Therefore **a
Hyperliquid carry is necessarily structure A with the spot leg on a different venue** — the
two-silo case, where the trigger is the **full price move**, not the basis. At HL's 40x cap with
its 1.25 % maintenance margin, `x* = 1.23 %`, and BTC clears a 1.23 % rally in **most 24-hour
windows**. HL's margin tiers were probed and confirm the design: `{lowerBound 0 → 40x,
lowerBound 150,000,000 → 20x}` for BTC; ETH 25x; SOL 20x; the long tail of assets is 5x.

**HL pays +5.46 pp/yr more than Binance and charges for it in a structure that cannot be
hedged inside one margin pool.** That is a coherent price, not a free lunch.

---

## 4. Structure D — cross-venue perp/perp, the only form where leverage genuinely multiplies

This is the one structure where `λ` can exceed 1 without borrowing, because **both** legs are
margin: `λ = 1/(1/L_A + 1/L_B)`. T21 ranked it #3 and flagged that its edge had only ever been
measured on **one funding interval**. Measured properly here, on the 28,683 hours the three
venues overlap:

| pair (short the rich venue, long the cheap one) | mean | mean abs | p1 | p99 |
|---|---|---|---|---|
| **Hyperliquid − Binance** | **+5.46 %/yr** | 13.83 | −81.5 | +83.2 |
| Hyperliquid − Coinbase Intl | +5.16 %/yr | 14.70 | −64.6 | +91.1 |
| Binance − Coinbase Intl | −0.30 %/yr | 6.12 | −21.7 | +22.2 |
| ex-post perfect pair (upper bound) | +17.32 %/yr | | | |
| **ex-ante, chosen on the previous hour** | **+16.14 %/yr**, negative on 4.6 % of hours | | | |

That is a real, persistent, first-party differential — **and it is annihilated by the two-sided
liquidation band.** With the legs in separate venue accounts, a rally kills the short leg and a
fall kills the long leg. Counting first exits from the `±x*` band on the actual 2023–2026 mark
path, re-anchoring at each exit, and charging **0.54 % of notional per event** (0.40 % maintenance
+ 2 × 4.5 bp taker + 5 bp slippage + transfer):

| L per leg | λ = N/C | ±band | **band exits / yr** | rebalance cost / yr |
|---|---|---|---|---|
| 2 | 1.00 | 49.40 % | 1.7 | 0.9 % |
| 3 | 1.50 | 32.80 % | 2.2 | 1.8 % |
| **5** | **2.50** | 19.52 % | **7.5** | **10.2 %** |
| 7 | 3.50 | 13.83 % | 11.4 | 21.6 % |
| 10 | 5.00 | 9.56 % | 25.7 | 69.4 % |
| 20 | 10.00 | 4.58 % | 107.0 | 577.5 % |
| **30** | 15.00 | 2.92 % | **255.2** | **2,067 %** |
| **50** | 25.00 | 1.59 % | **828.2** | **11,181 %** |

Income is `λ × 5.46 %`. Cost crosses it between **L = 5** (income 13.7 %, cost 10.2 %) and
**L = 7** (income 19.1 %, cost 21.6 %). **Structure D dies at L ≈ 5–6 per leg, λ ≈ 2.5–3** —
and that is *before* the fatal operational fact: rebalancing requires **moving collateral between
two venues** (USDC on-chain to Hyperliquid, an internal transfer at Binance) inside the 1–25-minute
window §2c measured, and **it bears both venues' failure probability simultaneously** (~2 %/yr
combined against a ~5.5 pp gross differential). The +16.14 %/yr ex-ante number requires
**switching which venue you are short every hour** and does not survive contact with a fee
schedule at all.

---

## 5. OPTIMAL LEVERAGE — and the measurement that ends the question

### 5a. To lever the book you must borrow, and I measured what borrowing costs

Probed live, Binance cross-margin, VIP 0, 467 assets:

| asset | daily | **annualised** | borrow limit |
|---|---|---|---|
| **USDT** | 0.010914 % | **4.06 %** | 500,000 |
| USDC | 0.014535 % | 5.45 % | 500,000 |
| BTC | 0.001219 % | **0.45 %** | 100 BTC |
| ETH | 0.006366 % | 2.35 % | 2,000 |
| FDUSD | 0.081720 % | 34.74 % | 250,000 |
| **all 467, distribution** | | p5 **2.49 %**, p25 9.28 %, **median 44.48 %**, p75 81.39 %, p95 127.08 %, max 14,245 % | |

Then `income/C = λ(f − c) − (λ−1)·r_b = r_b + λ·(f − r_b) − c`. **The slope in λ is `f − r_b`.**

### 5b. `f − r_b` measured over six years — the result that kills it

`r_b` needs a history, and no free history of Binance margin rates exists. So I built the
**market-implied** one: the **annualised basis of Binance's own quarterly BTCUSDT futures**, which
*is* the price of leveraged USD financing on BTC by no-arbitrage. 23 contracts, 2,127
contract-days, 7–110 days to expiry:

| year | quarterly-futures financing rate |
|---|---|
| 2021 | +17.93 % |
| 2022 | +2.23 % |
| 2023 | +6.34 % |
| 2024 | +12.72 % |
| 2025 | +6.04 % |
| 2026 | +2.67 % |
| **trailing 365 d** | **+3.95 %** |

**The proxy validates itself:** trailing-365-day futures-implied financing **3.95 %** against the
probed live USDT margin borrow **4.06 %** — **11 bp apart**, from two completely independent
sources. So the futures basis is a sound stand-in for the borrow-rate history, and if anything a
*lower bound* on what retail pays.

Now the paired series, daily, 1,975 days:

| year | perp funding `f` | financing `r_b` | **SPREAD `f − r_b`** | t-stat | share > 0 |
|---|---|---|---|---|---|
| 2021 | +27.49 % | +17.82 % | **+9.67 pp** | +7.20 | 66.9 % |
| 2022 | +4.09 % | +2.22 % | +1.87 pp | +4.83 | 69.3 % |
| 2023 | +7.95 % | +6.28 % | +1.66 pp | +6.18 | 65.9 % |
| **2024** | +11.92 % | +12.52 % | **−0.59 pp** | −1.34 | 34.4 % |
| **2025** | +5.13 % | +6.18 % | **−1.06 pp** | −5.88 | 38.1 % |
| **2026** | +1.91 % | +2.68 % | **−0.77 pp** | −2.78 | 45.0 % |
| all 1,975 d | +10.03 % | +8.20 % | +1.83 pp | +6.87 | 53.5 % |
| 2023-01-01 →, 1,300 d | +7.30 % | +7.43 % | −0.13 pp | −0.80 | 45.8 % |
| **2024-01-01 →, 942 d** | **+7.05 %** | **+7.86 %** | **−0.81 pp** | **−4.15** | **38.2 %** |

`corr(f, r_b)` = **0.821** on daily levels, **0.934** on 30-day means.

**Read those last two rows together and do not overstate either.** Pooled from **2023** the spread
is **−0.13 pp, t = −0.80** — *statistically indistinguishable from zero*, because 2023 itself was
+1.66 pp. Pooled from **2024** it is **−0.81 pp, t = −4.15**. The defensible claim is therefore
the weaker one plus the trend: **the spread has been at or below zero for three and a half years,
significantly below zero for two and a half, and it has never recovered.** Even the generous
reading — spread = 0 — makes leverage exactly worthless: `income/C = r_b − c` at every λ, i.e. a
flat line with a liquidation tail bolted to it.

> **This is the finding.** Perp funding, the futures basis, and the margin borrow rate are three
> quotes of **one price: what leveraged long BTC exposure costs.** The carry trade collects one and
> the levered version pays another. The spread between them is what leverage multiplies, and it has
> been **negative in each of 2024, 2025 and 2026, and −0.81 pp pooled at t = −4.15 over those 942
> days**. The whole positive history is 2021, when the spread was +9.67 pp — a regime with T-bills
> at zero that has not recurred.
>
> **A levered funding carry is not a carry. It is a bet that funding exceeds financing, and that
> bet has lost for 942 straight days.**

### 5c. Net income vs λ, four regimes

`c` = 50 bp/yr running friction (BTC-only, low turnover; T21 measured 0.02–5.2 bp spreads and a
30 bp published round trip). Breakeven venue-failure `p* = excess/(1+r_f+excess)`. Kelly sleeve
`w*` maximises `(1−p)·ln((1−w)(1+r_f) + w(1+g)) + p·ln((1−w)(1+r_f))` at `p = 1 %/yr`.

**Regime "TODAY" — `f` = 3.24 %, `r_b` = 4.06 %, both probed, spread −0.82 pp:**

| λ | net %/yr | vs T-bill | breakeven `p*` | Kelly sleeve |
|---|---|---|---|---|
| 1 | +2.74 | **−1.10 pp** | 0 % | **0 %** |
| 2 | +1.42 | −2.42 pp | 0 % | 0 % |
| 5 | −2.54 | −6.38 pp | 0 % | 0 % |
| 10 | −9.14 | −12.98 pp | 0 % | 0 % |
| 20 | −22.34 | −26.18 pp | 0 % | 0 % |
| 50 | −61.94 | −65.78 pp | 0 % | 0 % |

**Regime "2023 → now", the exact paired series — `f` = 7.30 %, `r_b` = 7.43 %, spread −0.13 pp
(the most generous defensible regime):**

| λ | net %/yr | vs T-bill | breakeven `p*` | Kelly sleeve |
|---|---|---|---|---|
| **1** | +6.80 | **+2.96 pp** | **2.77 %** | 64 % |
| 2 | +6.17 | +2.33 pp | 2.19 % | 54 % |
| 3 | +5.54 | +1.70 pp | 1.61 % | 38 % |
| **5** | +4.28 | **+0.44 pp** | 0.42 % | **0 %** |
| 10 | +1.13 | −2.71 pp | 0 % | 0 % |
| 20 | −5.17 | −9.01 pp | 0 % | 0 % |
| 50 | −24.07 | −27.91 pp | 0 % | 0 % |

**Regime "2024 → now" — `f` = 7.05 %, `r_b` = 7.86 %, spread −0.81 pp:**

| λ | net %/yr | vs T-bill | breakeven `p*` | Kelly sleeve |
|---|---|---|---|---|
| **1** | +6.55 | **+2.71 pp** | 2.54 % | 61 % |
| 2 | +5.24 | +1.40 pp | 1.33 % | 25 % |
| **3** | +3.93 | **+0.09 pp** | 0.09 % | **0 %** |
| 5 | +1.31 | −2.53 pp | 0 % | 0 % |
| 10 | −5.24 | −9.08 pp | 0 % | 0 % |
| 50 | −57.64 | −61.48 pp | 0 % | 0 % |

**Even at spread ≈ 0 the Kelly sleeve hits zero by λ = 3–5**, because the venue tail is charged
against capital and the extra leverage adds no excess return to pay for it.

**Regime "full 2020–2026" — `f` = 12.21 %, `r_b` = 8.20 %, spread +4.01 pp** (the only regime with
a positive slope, and it is 2021): λ = 20 gives +74.56 pp over T-bills and `p*` = 41.79 %. *This
row is in the document only so that nobody re-derives it and calls it a result.* It is a single
bull market, its `r_b` is a lower bound, and the three most recent years all point the other way.

### 5d. The optimum, stated plainly

> **`λ* = 1` in every regime measured since 2023, and `λ* < 1` today.**
>
> **In structure A the optimum is `L ≈ 4` on the perp leg** — which is not a leverage decision at
> all, it is the statement *"hold ~20 % of capital as perp margin and 80 % as spot"*, and the 20 %
> is a **buffer**, not leverage. `λ = 0.800`.
>
> **The measured basis tail permits λ ≈ 8.8–16x. The measured economics permit λ ≈ 1.**
> The tail is not the binding constraint. That is the opposite of the hypothesis in the task, and
> it is worse news: a tail can be engineered around, a negative spread cannot.

### 5e. The venue tail closes it

| configuration | excess vs T-bill | breakeven venue-fail `p*` | vs ~1 %/yr base rate | Kelly sleeve |
|---|---|---|---|---|
| **Structure A, L = 4, 2023–2026** | **+0.71 pp** | **0.68 %/yr** | **fails** | **0 %** |
| BTC unlevered, trailing-365-day funding | **−0.60 pp** | — | fails | 0 % |
| T21 cross-sectional book, +6.05 % | +2.21 pp | 2.08 %/yr | marginal | 52 % full / 13 % quarter |

**On a \$100,000 account:** structure A at its optimum pays **\$710/yr = \$1.95/day** of excess
return, against a 1 %/yr chance of losing the **\$100,000**. The expected value is **negative**,
and log-utility sizes the sleeve at **zero**. T21's cross-sectional book pays **\$6.05/day** and
T21 itself caps its capacity at **\$30–60 k**.

**Leverage does raise `p*`** — that is its only genuine argument, and it is worth stating fairly:
in structure A, `p*` rises from 0.68 % at L = 4 toward ~0.9 % at L = 20. But §2d shows the CAGR
falls faster than `p*` rises over that same range, so the argument never pays for itself. And in
structure C, `p*` rises with λ only in the one regime where the spread is positive.

One further exposure, probed and priced: Binance's **Multi-Assets collateral haircut is 5.0 %**
(`assetIndex` `bidBuffer 0.05`, auto-exchange buffer 2.5 %). A unified book therefore carries a
residual **5 % delta**, so its recognised equity falls by `0.05·λ·x` on a rally of `x`. At λ = 20
that needs a ~90 % rally to matter; at λ = 50, ~30 %. Not binding at the leverages that survive
§5c, but it is a second reason the "unified margin is pure basis risk" story is not exactly true.

### 5f. Two adjacent claims this closes for free

- **T21 §6.7, "negative-funding harvest"** (long perp / short spot) was ranked #7 with the note
  *"a carry whose funding cost is the unmeasured leg is not a measurable carry."* **The leg is now
  measured:** the median Binance borrow across 467 assets is **44.48 %/yr** (p75 81.4 %,
  p95 127.1 %), against T21's median alt funding of **−5.2 %/yr**. **Dead by a factor of ~8.** BTC
  itself borrows at 0.45 %/yr, but BTC funding is positive, so the mirror trade is the wrong side
  there. *Rank 7 can be retired.*
- **T21 §6.3, "cross-venue perp funding differential"**, was ranked #3 on a **one-interval
  snapshot**. It now has **28,683 hours**: the differential is real (**HL − Binance +5.46 %/yr**)
  and it dies at λ ≈ 2.5–3 on rebalance costs alone (§4). *Rank 3 should fall behind rank 2.*

---

## 6. VERDICT

**DEAD.** There is no survivable configuration giving meaningful market-neutral daily income, and
the number is **+0.71 pp/yr over T-bills at the best leverage measured on the most recent 3.6
years, against a 0.68 % breakeven venue-failure probability and a ~1 %/yr base rate.**

The four ways it dies, each with its own number, each independently sufficient:

1. **Leverage cannot reach the money.** `λ = L/(L+1)`: 5x → 50x is a **+17.6 %** income uplift,
   maximum, forever, because the spot leg is unlevered cash. **§2a.**
2. **The advertised leverage is priced to liquidate.** At 30x the isolated short leg is liquidated
   within a day **24.90 %** of the time and within a month **86.09 %**; the book CAGR goes from
   +4.55 % at 4x to **−10.34 % at 50x** on 2023–2026. **§2d.**
3. **Levering the book requires borrowing at the same rate the carry pays.** `f − r_b` =
   **−0.81 pp/yr, t = −4.15, 942 days, positive on 38.2 %** since 2024 (**−0.13 pp, t = −0.80**
   pooled from 2023 — zero on the generous reading); `corr` of 30-day levels **0.934**. Leverage
   multiplies something that is at best zero. **§5b.**
4. **The carry itself has decayed below cash.** BTC funding: 30.61 % (2021) → 5.13 % (2025) →
   **2.15 % (2026 YTD)** against a **3.84 %** T-bill, on three independent venues simultaneously.
   **§1b.**

**And one place the hypothesis was wrong, reported because it runs against the verdict:** the
**basis-blowout liquidation is not the killer for a genuinely unified-margin book.** Below
λ ≈ 25x it essentially never fires (P(liq in 30 d) = 0.0000 % at λ = 15). The basis is
exchange-enforced and index-anchored and it behaves. The killer is that the money is not there,
and — for every structure a retail person can actually build — that **the hedge lives in a
different margin account from the position it is hedging**, so the trigger is the price, not the
basis.

**On the specific products the owner named:**

- **Coinbase ~50x perps** are **Coinbase International** (`base_imf 0.02`), **not** US-accessible.
  Their default is 5x. At 50x the book loses **−14.18 pp/yr** vs T-bills on 2023–2026.
- **Coinbase "~50x index perps"** are **US500 / Tech100 / China / Defense / AI perp-style
  futures** on the US CDE rail. `US5-19DEC30-CDE` has **three daily candles**. There is no history
  and no test. Separately, an equity-index perp's funding is a **financing rate**: short the index
  perp, hold the ETF, collect `r − q` plus dividends `q` = `r`. That is a T-bill with tracking
  error and two extra counterparties — the no-arbitrage identity, not an edge.
- **Hyperliquid 40x** pays the most (**+12.72 %/yr** vs Binance's +7.26 % on the overlap) and is
  the *only* venue where the spot leg **cannot** be cross-collateralised (`collateralToken: 0`,
  no BTC spot market), forcing the two-silo structure whose trigger at 40x is a **1.23 %** rally.
  Its custody tail is smart-contract + bridge + validator + HLP-socialisation + governance
  settlement, with **no base rate**, and its funding premium does not cover it.
- **The one US-legal rail — Coinbase CDE perp-style futures, FCM-segregated** — is the only one
  without the FTX tail, has a basis tail **20x tighter** (29 bp vs 569 bp), and **does not publish
  its funding rate on any free endpoint.** It is untestable today for the only reason that matters.

**What would have to change for this to come back**, stated so that it can be checked cheaply
rather than re-litigated: `f − r_b` positive and significant on a **held-out** window (it has been
negative for 942 days at t = −4.15); **and** BTC funding back above T-bills plus the tail premium
(it is 1.7 pp below T-bills today); **and** a rail that is legal for the account holder. A monthly
one-line recomputation of the §5b spread from free data is enough to detect the first two. **No
harness, no freeze-then-test, no paper-forward plan is warranted, because there is no positive
effect to freeze.** Building one would repeat the T15 error: *a candidate whose measured edge is
negative is dead before it is tested.*

---

## 7. Leakages, gaps and the things I could not verify

**Mine, reported because two of them flatter the negative and two do not:**

1. **`r_b` history is a proxy.** The quarterly-futures basis is a *market* financing rate, not
   Binance's posted margin rate. It validates to 11 bp against the live probe **today**, but a
   single-day agreement is not a history. *This runs toward the verdict* — retail borrow sits
   **above** the wholesale rate, so the true `f − r_b` is more negative than measured.
2. **Structure C's simulation applies a fixed `r_b` to a 6.6-year path.** Any levered-carry number
   in the "full 2020–2026" regime is therefore wrong in an unknown direction and is not relied on.
3. **Hyperliquid's basis tail is not measured.** Its published `premium` is clamped and
   funding-purposed; the liquidation-relevant mark deviation is strictly wider. *This runs against
   the verdict* — HL looks safer than it is, and §5 does not use the number.
4. **The 0.54 %/event rebalance cost in §4 is constructed, not measured**: 0.40 % maintenance
   (probed) + 2 × 4.5 bp taker (cited) + 5 bp slippage + transfer (assumed). The conclusion is
   insensitive — at zero slippage and zero transfer, structure D still dies at L ≈ 7.
5. **Single asset.** Everything in §2 and §5 is **BTCUSDT**. T21's +2.20 pp came from a
   *cross-sectional* 24-name book whose own two leakages T21 declares. The cross-sectional book's
   basis tail is certainly wider than BTC's, so applying BTC's `λ_max` to it would be optimistic.
   *This runs toward the verdict.*
6. **`c` = 50 bp/yr is a BTC-only assumption.** T21 measured 36.8 bp per round trip at 55 %/month
   turnover on the cross-sectional book, i.e. **−2.41 %/yr**. Substituting that makes every table
   in §5c worse by ~1.9 pp.

**Could not be verified under guardrail 1 (no account, no funds):** all fee schedules; Binance
Portfolio-Margin eligibility and whether it nets a spot/perp hedge as assumed; Hyperliquid's
maintenance-margin rule and mark-price formula; the legal-availability statements; whether the
Coinbase US perp-style futures pay a funding rate at all and at what level; and the venue-failure
incident record in §1d. Every one of these is marked at its point of use.

---

*T22. First-party measurements taken 2026-08-19 against `data.binance.vision` (3,433,455 aligned
1-minute bars ×4 series, 23 quarterly-futures contracts), `fapi.binance.com` and `binance.com/bapi`
(1,007 leverage brackets, 467 borrow rates, collateral haircuts), Hyperliquid `POST /info`
(28,115 hourly funding+premium prints ×3 coins, 232 perps, margin tables), Coinbase International
(29,905 hourly funding prints, 264 perps), Coinbase Advanced/CDE (101 FCM contracts, 358 daily
candles), plus the held `btc_perp_funding_binance_2019_2026.csv` (7,586 prints). No account was
opened, no order was placed, no funds were moved.*
