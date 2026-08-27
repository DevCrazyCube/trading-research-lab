# T24 — CME regulated crypto-futures cash-and-carry basis: a bounded probe

**What this is.** The single bounded probe `NONDIRECTIONAL_INCOME_SHORTLIST.md` §7 asked for:
*is free CME BTC/ETH futures settlement history obtainable, and if so, is the cash-and-carry basis
a better pillar #1 than crypto-perp funding carry — the same carry mechanism with the FTX-style
exchange-failure tail replaced by CFTC segregation?*

**Status.** **Probe complete. Answer: the data IS obtainable — and the mechanism it reveals is
WORSE than perp funding carry, not better.** This is not a frozen test and nothing here is a
certified result. It is a measurement plus a friction census, of the kind `T15_RESULT.md` says
must precede a harness. Its conclusion is a **power-gate death in the T15 template**: 8.7 years of
every CME Bitcoin futures contract that has ever existed produce an excess-over-T-bills of
**+2.08 pp/yr against its own MDE(80%) of 4.45 pp** — the effect is below the smallest effect the
complete history of the instrument can detect, and certifying a 2 pp/yr edge would take **29.7
years** of a product that is **8.7 years old**.

**Everything below is first-party, measured 2026-08-19 from free, keyless sources.** No account was
created, no order placed, no custody action taken, nothing purchased. Harness:
`scripts/trading_bot/t24_cme_basis.py`; machine-readable receipt: `CME_BASIS_PROBE.json`;
raw cache: `research/data/t24_cache/`.

---

## 1. DATA — is it obtainable? Probed live, not assumed

`NONDIRECTIONAL_INCOME_SHORTLIST.md` scored this candidate `D = 1` on one 403. That score was
**too harsh on the basis and too generous on the term structure**. The corrected picture:

| source | probe result 2026-08-19 |
|---|---|
| **CME quotes API** (`/CmeWS/mvc/Quotes/Future/8874/G`) | ✗ **403** — *"This IP address is blocked due to suspected web scraping activity"* |
| **CME settlements API**, product pages, `/ftp/pub/settle/`, `/ftp/bulletin/` | ✗ **403, all of them**, same message. CME direct is `D = 1` and will stay there |
| CF Benchmarks BRR/BRRNY values API | ✗ **400 "Unknown id"** — the settlement index itself is not free at that path |
| Nasdaq Data Link `CHRIS/CME_BTC1` | ✗ **403** (Akamai bot wall) |
| Stooq `btc.f` | ✗ 200 but a **JavaScript browser challenge**, no CSV |
| investing.com API / Barchart proxy | ✗ **403 / 401** |
| **Yahoo `BTC=F` (CME Bitcoin, continuous front)** | ✓ **200. 2,181 non-null daily closes (2,183 bars), 2017-12-18 → 2026-08-19** — the entire life of the product |
| **Yahoo `ETH=F` (CME Ether, continuous front)** | ✓ **200. 1,393 non-null daily closes (1,395 bars), 2021-02-05 → 2026-08-19** — the entire life of the product |
| **Yahoo per-contract `BTCU26.CME`, `BTCZ26.CME`, `ETHQ26.CME` …** | ✓ **200 for CURRENTLY LISTED contracts** (4 BTC, 5 ETH), each with its full listing history — `BTCZ26.CME` back to 2024-12-27, 411 bars |
| Yahoo per-contract, **EXPIRED**: `BTCN26`, `BTCZ25`, `BTCZ24`, `BTCZ22`, `BTCZ19`, `BTCF18` | ✗ **404 "symbol may be delisted", every one.** There is **no free historical term-structure panel** |
| Yahoo micro contracts `MBT=F`, `MET=F`, `MBTU26.CME` | ✓ 200 but **1 bar only** — no micro history |
| **Binance spot 1h klines** (BTCUSDT/ETHUSDT) | ✓ free, keyless, 75,891 bars each from 2017-12 |
| **Binance perp funding** (BTCUSDT/ETHUSDT) | ✓ free, 7,605 / 7,371 prints — the head-to-head comparator |
| **CFTC public reporting** (Socrata legacy COT) | ✓ free, keyless. 855 rows of CME Bitcoin / Micro Bitcoin open interest, 2018-04 → 2026-08 |
| **US spot-BTC ETFs** IBIT/FBTC/BITB/GBTC (Yahoo) | ✓ free — the regulated spot leg |
| FRED `DGS3MO` live | ✗ timed out twice; used the repo's existing `t13_cache/cash.csv` (FRED **DTB3**, through 2026-08-13) |

**Corrected score: `D = 3`.** A free, complete, 8.7-year front-month CME basis history exists.
A free historical term-structure panel does **not** — expired contracts are gone, so the deferred
curve can only be observed for the ~1.6 years of the nine currently-listed contracts (4 BTC, 5 ETH).

### 1a. The two facts the whole measurement rests on, verified rather than assumed

Nothing below works unless we know *which contract* `BTC=F` is and *at what instant* its close is
struck. Both were established from the data:

- **The clock.** Sweeping all 24 UTC hours of Binance spot against the futures daily close, the
  dispersion of `log(F/S)` is minimised at the **19:00–20:00 UTC bar (close 20:00 UTC): sd 51.7 bp,
  against 262.9 bp at the worst hour** — a 5× separation. 20:00 UTC is **15:00 CT, the CME daily
  settlement**. The Yahoo daily close is the settlement price, not a session-end last trade.
- **The roll.** `BTC=F` equals `BTCQ26.CME` **to the last decimal on 12 sessions,
  2026-08-03 → 2026-08-18** — i.e. from the first session after the 2026-07-31 July expiry.
  `BTC=F` is the **nearest contract, rolling the session after expiry**. Days-to-expiry is
  therefore reconstructible from the CME rule (**last Friday of the contract month**, cash-settled
  to the CME CF Bitcoin Reference Rate at 16:00 London).
- **And the reconstruction validates itself.** If the expiry model were wrong, the basis of the
  expiring contract would not go to zero. It does, monotonically:

  | days to expiry | 1 | 2 | 3 | 4 |
  |---|---|---|---|---|
  | mean raw basis, BTC | **−8.2 bp** | +0.2 bp | +1.6 bp | +3.0 bp |

  A ramp of ≈1.3 bp/day — **4.7 %/yr annualised, matching the measured basis level exactly.**
  (dte 5–7 are empty by construction: sessions are Mon–Fri and expiry is a Friday.)

---

## 2. MEASURE — the historical annualised cash-and-carry basis

Basis = `F(t,T)/S(t) − 1`, annualised `× 365/DTE`. `F` = CME settlement, `S` = Binance spot at the
same instant. Restricted to DTE ≥ 5 so the annualisation is not dividing by ~0.

### 2a. Level and stability

| | n sessions | window | mean | median | sd | positive on |
|---|---|---|---|---|---|---|
| **BTC** | 1,687 | 2017-12-18 → 2026-08-18 | **+4.91 %/yr** | +6.01 % | 27.74 % | **72.9 %** |
| **ETH** | 1,078 | 2021-02-05 → 2026-08-18 | **+5.71 %/yr** | +6.23 % | 17.40 % | **75.0 %** |

Raw (un-annualised) basis on a ~21-day leg: **+0.23 %** (BTC), **+0.27 %** (ETH).

### 2b. By year, against the risk-free rate it must beat — and against the perp

| year | CME BTC basis | Binance BTC perp funding | 3-m T-bill | **CME − rf** | **perp − rf** |
|---|---|---|---|---|---|
| 2018 | −14.43 % | — | 1.93 % | **−16.37 pp** | — |
| 2019 | +5.01 % | +8.55 % | 2.06 % | +2.95 pp | +6.48 pp |
| 2020 | +14.16 % | +15.90 % | 0.36 % | +13.80 pp | +15.55 pp |
| 2021 | +7.70 % | +34.66 % | 0.05 % | +7.65 pp | **+34.61 pp** |
| 2022 | −4.79 % | +3.91 % | 2.02 % | **−6.82 pp** | +1.89 pp |
| 2023 | +11.65 % | +7.44 % | 5.07 % | +6.58 pp | +2.37 pp |
| 2024 | +10.70 % | +12.87 % | 4.97 % | +5.73 pp | +7.90 pp |
| **2025** | +5.93 % | +5.24 % | 4.07 % | **+1.86 pp** | +1.17 pp |
| **2026 YTD** | +3.19 % | +2.21 % | 3.64 % | **−0.45 pp** | −1.43 pp |

Day-weighted over the whole sample: **BTC +2.26 pp over T-bills** (above rf on 63.7 % of sessions),
**ETH +2.37 pp**. Over the **last twelve months: BTC +0.50 pp, ETH +0.02 pp.**

> **The carry has decayed to the risk-free rate.** Semi-annually, BTC's excess runs
> +0.81, +2.83, −0.52, −0.23 pp over 2025H1→2026H2. This is not a crypto-winter artefact: the
> perp funding excess collapsed in lockstep (+0.47, +1.82, −2.63, +2.47 pp). **Both carries died
> at the same time, which is the point — they are the same financing rate.**

### 2c. Term structure — measurable only for the nine live contracts

Curve on 2026-08-18, spot 64,643:

| contract | expiry | DTE | F | raw basis | **annualised** |
|---|---|---|---|---|---|
| `BTCQ26` | 2026-08-28 | 10 | 64,715 | 0.11 % | **4.05 %** |
| `BTCU26` | 2026-09-25 | 38 | 64,970 | 0.51 % | **4.85 %** |
| `BTCV26` | 2026-10-30 | 73 | 65,270 | 0.97 % | **4.85 %** |
| `BTCZ26` | 2026-12-25 | 129 | 65,845 | 1.86 % | **5.26 %** |

Implied forward (calendar-spread) rates: 5.14 %, 4.82 %, 5.74 %. ETH is flatter and lower:
4.24 % (10 d) / 4.38 / 4.37 / 4.48 / **4.62 %** (129 d). **A mild, orderly, upward-sloping contango of about 5 %/yr against a
3.71 % T-bill** — an implied crypto financing rate roughly 1.2 pp above cash at the long end and
0.3 pp above it at the front. This is a *clean, well-behaved curve*, and that is exactly the
problem: there is very little in it.

### 2d. Roll behaviour, and the liquidity fact that destroys the good design

Entering once per contract at DTE ≤ 28 and holding to cash settlement, **105 BTC cycles over 8.7
years**: mean leg **+0.423 %**, compounded **+6.14 %/yr gross**, worst leg **−1.84 %**, and
**25 of 105 legs negative** — the basis is in backwardation about a quarter of the time and the
roll then costs you.

The obvious design response is to roll **quarterly** into the deferred contract: fewer rolls
(0.34 pp/yr instead of 1.02 pp/yr) *and* a higher annualised basis (5.26 % at 129 days vs 4.05 % at
10 days). **It is not executable.** Yahoo-reported median daily volume, last 60 sessions:

| contract | DTE | contracts/day | notional/day |
|---|---|---|---|
| `BTC=F` (all-month aggregate) | — | 8,884 | **$2.85 bn** |
| `BTCQ26` — front | 10 | 1,080 | $326 m |
| `BTCU26` — second | 38 | **22** | $7.3 m |
| `BTCV26` — third | 73 | **0** | **$0** |
| `BTCZ26` — deferred | 129 | **0** | **$0** |

ETH is worse: `ETHQ26` 253 contracts/day ($21.3 m), `ETHU26` **4**/day ($0.4 m), everything beyond
**zero**.

> **The best version of the trade trades zero contracts a day.** The liquidity lives entirely in
> the front month, which forces **twelve rolls a year** and pays the **lowest** point on the curve.
> (Absolute levels are Yahoo's per-contract prints and may undercount; the 1080 : 22 : 0 *ratio* is
> the standard futures shape and the zero is unambiguous.)

### 2e. Convergence — the one risk that turns out to be small

At DTE = 1 the expiring contract's basis is **mean −8.2 bp, median −0.3 bp** (BTC, n = 97);
ETH **−5.0 / −0.3 bp** (n = 61). Convergence is real and near-exact — as it must be, since the
contract is **cash-settled to the BRR**, not physically delivered. The per-observation sd of
54.9 bp is **our measurement floor, not the trade's risk**: §1a establishes that the
Binance-spot-versus-CME-settlement alignment alone carries sd 51.7 bp. **Free data cannot resolve
per-cycle tracking error below ~50 bp**, and a real implementation's spot-leg-versus-BRR tracking
is therefore *unmeasured here* — see §6.

---

## 3. COMPARE — CME basis carry vs crypto-perp funding carry

### 3a. Gross yield: the perp paid far more — until 2023, when it stopped

Same asset, same 1,353 matched sessions (2019-09-10 → 2026-08-18):

| | mean annualised | excess over T-bills |
|---|---|---|
| CME BTC front-month basis | +7.16 % | **+4.37 pp** |
| Binance BTCUSDT perp funding | +12.09 % | **+9.30 pp** |

Correlation of the two, daily: **+0.237**. They are the same economic financing rate measured on
two rails, and the rails disagree a lot.

**But the spread has inverted, and that reframes the whole probe:**

| perp funding − CME basis | BTC | ETH |
|---|---|---|
| 2019-09 → 2022-12 | **+11.33 pp** (perp richer on 69 % of days) | +13.48 pp |
| 2023-01 → 2026-08 | **−0.90 pp** (perp richer on 43 % of days) | −0.08 pp |
| last 12 months | **−0.96 pp** | −1.26 pp |

> **The venue-risk premium the probe was designed to harvest no longer exists.** T21's thesis was
> that the offshore perp pays extra *because* it carries the FTX tail, so a regulated rail paying
> comparable carry would strictly dominate. That was true through 2022, when the perp paid
> **+11.3 pp/yr more** than CME. Since 2023 the offshore perp has paid **less** than the regulated
> CME rail. There is no longer a spread to give up — **and there is no longer a carry to collect
> on either rail.**

### 3b. The tail: CFTC segregation is a genuine, large improvement

This part of the thesis holds and should be recorded as a win even though the trade dies.

| | perp funding carry | CME basis carry |
|---|---|---|
| where the money sits | offshore exchange omnibus wallet | **FCM customer-segregated funds, CFTC-regulated; CME Clearing as CCP** |
| total-loss base rate | Mt Gox, QuadrigaCX, Celsius, Voyager, BlockFi, FTX — T21's ~**1 %/yr per venue** | **we found no total-loss event for a US FCM customer in a cleared CME contract. Asserted from general knowledge, NOT probed — CME's own site is 403** |
| T21's breakeven venue-failure rate | **2.20 %/yr** — same order as the base rate | irrelevant: there is no ~2 pp edge left to price a tail against |
| the tail that replaces it | — | **FCM failure with a segregation shortfall — MF Global (2011, customers ultimately recovered in full) and Peregrine (2012, customers recovered a fraction) — plus CME Clearing itself. Cited, not verified** |

**But the spot leg re-imports what the futures leg removed.** A short CME future does not carry
custody risk; the long spot leg you must hold against it does. Only since **2024-01-11** — the US
spot-BTC ETF launch — has a fully regulated spot leg existed at all. **The regulated version of
this trade is 2.6 years old, not 8.7.** Before that, the only US-listed vehicle was GBTC, whose
realised drag against spot was **−10.10 pp/yr over 8.67 years** (t = −0.81 on the daily
difference — this is a premium-to-discount collapse, not a fee) —
it would have destroyed the carry many times over. Measured drag of the modern ETFs, matched-day
log-return difference against Binance spot at 20:00 UTC:

| | IBIT | FBTC | BITB |
|---|---|---|---|
| drag vs spot | **0.28 pp/yr** | **0.25 pp/yr** | **0.31 pp/yr** |
| n days / t | 651 / −0.05 | 651 / −0.05 | 647 / −0.06 |

These land on the stated 0.25 % expense ratios almost exactly. **The spot leg is now cheap and
regulated — and that is very likely part of why the basis compressed after 2024.**

### 3c. Roll vs 8-hour funding — the perp wins on structure

| | perp | CME |
|---|---|---|
| payment cadence | every 8 h, continuous, no expiry | at settlement, monthly |
| **roll cost** | **zero — a perp never expires** | 12 rolls/yr forced by §2d's liquidity, **1.02 pp/yr** |
| re-entry risk | none | each roll re-enters at the *then-prevailing* basis — **25/105 legs negative** |
| margin form | typically 10–20 %, and the spot leg **cross-margins** the perp on the same venue | **~40 % SPAN, and no cross-margining**: the ETF is in a securities account, the future in a segregated commodity account |
| exit | continuous | continuous, but a partial unwind is chunky at 0.1 BTC granularity |

> **The one structural feature that makes a perp a bad instrument — that it never expires and must
> be forced to converge by a funding payment — is exactly what makes it the *cheaper* carry
> vehicle. The CME contract's clean convergence is paid for twelve times a year.**

### 3d. Capacity — CME wins, decisively and irrelevantly

CFTC legacy COT, report date 2026-08-11:

| | open interest | notional at $64,725 |
|---|---|---|
| CME **Bitcoin** (5 BTC/contract) | 21,185 contracts | **$6.85 bn** |
| CME **Micro Bitcoin** (0.1 BTC) | 28,190 contracts | **$182 m** |
| MBT **non-reportable** (all small traders combined) | long 4,296 / short 2,387 | $27.8 m / **$15.4 m** |

A $100 k *notional* book is **15.5 MBT contracts** — **0.055 %** of MBT open interest and
**0.65 %** of the entire retail short side. (A $100 k *account*, at §4's 1.70× capital multiple,
supports ~9 contracts / $59 k of notional.) Front-month notional turnover is **$326 m–$2.85 bn/day**. Against T21 §3f's perp
finding — *"a $100 k account is already too large for the top-3 form"*, capacity $30–60 k — **the
CME rail removes the capacity wall completely.** It is the clearest advantage in this document,
and it is worth nothing because there is no edge to scale.

### 3e. RETAIL EXECUTABILITY — accessible, but not at our broker and not cheaply

| question | answer, probed or cited |
|---|---|
| smallest contract | **MBT = 0.1 BTC ≈ $6,473 notional**; tick $5/BTC = **$0.50/contract = 0.77 bp**. Also **BFF, Bitcoin Friday Futures = 0.02 BTC ≈ $1,295**, but it expires **weekly** — 52 rolls/yr, unusable for carry |
| smallest viable position | ~$6.5 k ETF + ~$2.6 k SPAN margin + buffer ≈ **$11 k**. Granularity is fine for a $100 k account |
| **SPAN initial margin** | **≈ 39.7 % of notional.** MBT $2,800 on $7,056 notional and BTC $140,000 on $352,784 (both quoted 2026-03-24) give the *same* ratio — an internal consistency check on a **secondary source**; CME's own margin page is 403 |
| commissions | IBKR **$2.25/contract** for MBT plus ~$1.20 exchange/clearing (cited). **3.48 bp per side** on MBT notional |
| account minimum | tastytrade: **$2,500** net liquidity for micro futures. IBKR: futures permission; **$110,000** for portfolio margin |
| **our broker** | **Alpaca offers no futures at all.** This requires a *new broker relationship* — an owner decision, not a technical one |
| idle-margin interest | IBKR quotes **3.13 % on uninvested cash** against a 3.71 % T-bill (both live, 2026-08-19) — a ~0.5 pp haircut on 70 % of notional. **Most retail FCMs pay nothing**, which is 2.6 pp/yr of pure drag |
| tax | CME futures are Section 1256 (60/40 blend), which is a genuine advantage over spot crypto. **Cited, not verified, and not tax advice** |

---

## 4. The net arithmetic — every cost named

**Form:** long a US spot-BTC ETF (IBIT/FBTC), short CME Micro Bitcoin, **monthly roll** (§2d says
liquidity leaves no choice). MBT notional $6,473 at BTC = $64,725.

| line | value |
|---|---|
| cost per side = 1 tick (0.77 bp) + commission/fees (3.48 bp) | **4.25 bp** |
| roll cost, 12 rolls × 2 sides | **−1.02 pp/yr** |
| ETF expense drag (measured, §3b) | **−0.25 pp/yr** |
| capital committed | 1.00 (ETF) + 0.40 (SPAN IM) + 0.30 (VM buffer, §5) = **1.70 × notional** |
| idle-margin haircut, 0.50 pp on 0.70 × notional | **−0.35 pp/yr** |

| regime | gross basis | net on notional | T-bill | excess on notional | **EXCESS ON CAPITAL** |
|---|---|---|---|---|---|
| full sample 2017-12 → 2026-08 | 4.91 % | 3.29 % | 2.55 % | +0.74 pp | **+0.44 pp** |
| 2024 (first ETF year) | 10.70 % | 9.08 % | 4.97 % | +4.11 pp | **+2.42 pp** |
| **2025** | 5.93 % | 4.31 % | 4.07 % | +0.24 pp | **+0.14 pp** |
| **2026 YTD** | 3.19 % | 1.57 % | 3.64 % | −2.07 pp | **−1.22 pp** |
| **front month today (10 d)** | 4.05 % | 2.43 % | 3.71 % | −1.28 pp | **−0.75 pp** |

**At an FCM that pays nothing on futures cash — the norm outside IBKR — every row is negative:**
full sample **−0.41 pp**, 2025 **−1.33 pp**, 2026 YTD **−2.51 pp**, today **−2.07 pp**.

> Against T21's perp figure of **+2.20 pp over risk-free**, the regulated CME expression delivers
> **+0.44 pp over its whole history and −0.75 pp today.** It is not close.

---

## 5. Every risk, named and sized — this is not free income

1. **Contango decay / basis compression — the one that actually killed it.** The trade earns the
   basis and nothing else. The basis fell from +13.8 pp over rf (2020) to **+0.50 pp over the last
   twelve months** and **−0.45 pp in 2026 YTD**. There is no position sizing, no venue, no
   contract choice that fixes a gross yield below cash.
2. **Backwardation / roll risk.** **25 of 105 monthly legs were negative**; the worst was
   **−1.84 %** on a ~21-day leg — roughly four months of the whole book's carry lost in one roll.
   In 2022, **10 of 12 BTC cycles** entered below the risk-free rate. (On the tighter DTE ≤ 21
   entry the harness uses for §6, the worst leg is **−5.52 %** and 28/105 legs are negative.)
3. **Variation-margin calls — the risk that is *worse* here than on a perp.** The short future is
   marked to market in **cash, daily**, while the offsetting gain sits in an ETF in a *different
   account at a different institution* with **no cross-margining** and T+1 settlement. Measured
   worst adverse (upward) BTC moves over the sample, as a fraction of notional:

   | horizon | worst | window | p99 |
   |---|---|---|---|
   | 1 day | **22.33 %** | 2019-06-25 → 06-26 | 9.88 % |
   | 5 days | **41.16 %** | 2019-06-21 → 06-26 | 21.14 % |
   | 10 days | **56.43 %** | 2019-06-16 → 06-26 | **31.52 %** |
   | 21 days | **79.37 %** | 2019-06-05 → 06-26 | 50.44 % |
   | 63 days | **177.71 %** | 2020-11-07 → 2021-01-09 | 123.41 % |

   A 10-day rally at the historical worst **exceeds the entire 40 % initial margin**. The trade is
   P&L-neutral and emphatically **not cash-flow-neutral**; this is the classic basis-trade failure
   mode and it is why §4 charges a 30 % buffer. A retail account that is liquidated by its FCM
   mid-rally realises the loss on one leg and keeps the paper gain on the other.
4. **Convergence and tracking risk.** Small but **unmeasured at retail resolution**. The contract
   settles to the **BRR** (a specific spot-index fix at 16:00 London); the hedge is an ETF whose
   own close is 16:00 New York. §2e shows convergence itself is clean (−8 bp), but free data cannot
   resolve per-cycle tracking below ~50 bp — **which is twice a typical 27 bp monthly leg return.**
5. **Broker / access risk.** Alpaca has no futures. A new FCM relationship is required, and
   **the FCM's cash-interest policy alone flips the sign of §4.**
6. **FCM failure with a segregation shortfall.** Smaller than the FTX tail, not zero: MF Global
   (2011) and Peregrine (2012) were exactly this. Segregation is a legal claim, not a vault.
7. **Product-discontinuation risk, and it has already happened once in this asset class.** CFTC
   data shows **CBOE Bitcoin futures ran from 2017-12 to 2019-04 and were delisted.** Regulated
   venues retire products too.
8. **Deferred-contract illiquidity (§2d).** The cheapest-to-roll, highest-yielding part of the
   curve prints **zero contracts a day**.

---

## 6. The statistical verdict — a T15-shaped death

The estimator a carry book actually uses is the **per-cycle mean**, with `n` = number of cycles —
not the number of daily basis prints. (`FINDINGS.md` §5j: the decile-book power rule; the same
mistake, in the same direction, would inflate `n` here by 16×.)

| | BTC | ETH |
|---|---|---|
| cycles (monthly, ~21-day legs) | **105** | 67 |
| observed annualised excess over T-bills | **+2.08 pp** | +2.00 pp |
| **MDE(80 %, two-sided 5 %)** | **4.45 pp** | 3.93 pp |
| verdict | **BELOW ITS OWN MDE** | **BELOW ITS OWN MDE** |
| t | **1.31** | 1.42 |
| bootstrap 95 % CI (20,000 resamples) | **[−1.21, +5.01] pp** | [−0.82, +4.64] pp |
| in-sample annualised Sharpe | 0.54 | 0.73 |
| **years of cycles needed to certify a 2 pp/yr edge** | **29.7** | 14.8 |
| **years of data that exist** | **8.7** (all of them) | 5.5 (all of them) |

**This is dead before it is tested, and it cannot be revived by waiting.** CME Bitcoin futures
began trading 2017-12-17. The complete history of the instrument is 3.4× too short to certify the
edge it appears to contain — and no DSR deflation has been applied yet, which would only make it
worse. `T15_RESULT.md`'s rule applies without modification: *a candidate whose minimum detectable
effect exceeds the effect it is looking for is dead before it is tested.*

### 6a. The one honest caveat — and why it does not save the trade

Cash-and-carry has a property almost nothing else in this programme has: **the return is
observable at entry.** The leg's payoff *is* `F/S − 1` at the moment you put it on (given
convergence, which §2e measures at −8 bp). So a conditional rule — *only carry when the entry basis
clears rf + X* — requires no prediction at all, and the t-statistics look spectacular:

| BTC, threshold | cycles | time in market | annualised excess while in | blended | t |
|---|---|---|---|---|---|
| unconditional | 105 | 100 % | +2.08 pp | +2.08 pp | 1.31 |
| rf + 0 pp | 71 | 67.4 % | +9.15 pp | +6.17 pp | 8.17 |
| **rf + 4 pp** | 46 | 43.5 % | **+13.14 pp** | **+5.72 pp** | **9.25** |

**Those t-statistics are nearly tautological and must not be read as an edge.** Selecting cycles on
a high entry basis mechanically produces high realised returns, because the realised return *is*
the entry basis. The threshold was also chosen after seeing the unconditional result — a declared
post-hoc search of the exact kind `NONDIRECTIONAL_INCOME_SHORTLIST.md` §3d flags in its own work.

The non-tautological content is **availability**, and availability is what has vanished:

| share of monthly cycles clearing… | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | **2026** |
|---|---|---|---|---|---|---|---|
| rf + 0 pp | 100 % | 92 % | 17 % | 67 % | 92 % | 67 % | 75 % |
| rf + 4 pp | 100 % | 75 % | **0 %** | 50 % | 50 % | 25 % | **0 %** |

**Zero of 8 BTC cycles in 2026 cleared rf + 4 pp; zero of 8 for ETH.** The conditional trade is not
a prediction problem — it is an inventory problem, and the shelf is empty. A rule that is out of
the market and in T-bills is a correct rule and not a strategy.

---

## 7. VERDICT

> **CME crypto-futures cash-and-carry basis is a WORSE pillar #1 than crypto-perp funding carry,
> and neither is currently a pillar at all. It is NOT worth a full freeze-then-test.**

**Why worse, in one table:**

| | perp funding carry (T21 §3e) | **CME basis carry (this probe)** |
|---|---|---|
| gross carry, matched days | +12.09 %/yr | **+7.16 %/yr** |
| excess over T-bills, gross | +9.30 pp | **+4.37 pp** |
| roll cost | **none — no expiry** | −1.02 pp/yr, forced by front-month-only liquidity |
| spot-leg cost | ~0 (spot coin) | −0.25 pp/yr (ETF) — and only regulated since 2024-01-11 |
| capital multiple | ~1.2× (cross-margined) | **1.70×** (40 % SPAN + 30 % VM buffer, no cross-margin) |
| idle-cash drag | none | −0.35 pp (best case) to −2.6 pp (typical FCM) |
| **net excess on capital** | **+2.20 pp** (T21, cross-sectional; BTC-only was −0.46 pp) | **+0.44 pp full sample, −0.75 pp today** |
| venue tail | ~1 %/yr total loss (FTX-class) | **materially smaller — CFTC segregation. The one part of the thesis that held** |
| capacity | **$30–60 k wall** | **$6.85 bn OI — no wall.** |
| history available | 7 yr, survivorship-complete, 920 symbols | **8.7 yr — all there is, and 3.4× too short** |
| statistical status | 2 known leakages, both flattering | **below its own MDE, t = 1.31, CI spans zero** |

**The thesis was right about the tail and wrong about the trade.** CFTC segregation *is* a real
structural improvement, and capacity *is* unbounded compared with the perp book. But:

1. **You are paid less for the safer rail** — 4.37 pp vs 9.30 pp of gross excess over the matched
   window — which is precisely what a risk premium looks like from the other side.
2. **The regulated form's frictions are larger than the risk it removes.** Roll (1.02) + ETF (0.25)
   + idle cash (0.35) = **1.62 pp/yr**, against a tail T21 priced at ~1 %/yr. **You pay more in
   frictions to avoid the tail than the tail costs.**
3. **And since 2023 the offshore perp has paid *less* than CME anyway** (−0.90 pp), so the premium
   the whole probe was built to arbitrage no longer exists in either direction.
4. **Both are now at or below cash.** BTC: CME −0.45 pp, perp −1.43 pp in 2026 YTD.

**Recommendation.** Do **not** promote CME basis carry to a freeze-then-test. Update
`NONDIRECTIONAL_INCOME_SHORTLIST.md` #6 from `D = 1, "worth a bounded probe"` to
**`D = 3, PROBED — WORSE THAN #1, DEAD BY POWER GATE`**, and record that the probe returned exactly
what §7 said either outcome would be worth: a measurement.

**What this probe also says about #1.** T21's primary recommendation — freeze and test the
cross-sectional perp funding carry — is **weakened, not confirmed, by this work.** The BTC/ETH perp
funding excess over T-bills is now **−1.43 pp / −2.43 pp (2026 YTD)** on our own independent pull,
and the CME series shows the same collapse on a completely different rail. **Two independent
measurements of the same financing rate both say the crypto carry complex is currently paying below
cash.** Before spending the clean 7-year Binance window on a frozen test, the pre-registration
should state a required edge that the *current regime* can plausibly clear — because a
survivorship-complete backtest whose profit lives in 2020–21 is a backtest of a rate environment
that no longer exists.

**Owner-facing, not decided here.** Nothing in this probe requires a broker, an account, or a
custody decision. If the owner ever *does* want a regulated crypto rail, this document is the
costing: **~$11 k minimum position, 1.70× capital, a new FCM relationship, and an FCM that pays
interest on futures cash — without which the trade is negative in every regime measured.**

---

## 8. What this document does not claim

- **No frozen test was run and no window was burned.** This is a scoping measurement, and its
  conclusion is a power-gate refusal *before* a harness — the `T15` pattern, cost: one afternoon.
- **The 8.7-year basis series uses a Binance spot leg**, not a regulated one. The fully-regulated
  expression (spot-BTC ETF + CME future) has existed only since **2024-01-11 — 2.6 years.** Every
  pre-2024 figure describes a trade a US retail person could not have put on cleanly.
- **`F` is Yahoo's rendering of the CME settlement, not CME's own file.** The 403 is real (§1) and
  Yahoo is a single point of failure for the whole measurement. The alignment and roll checks in
  §1a, and the convergence ramp in §1a, are the internal validation that stands in for a second
  source. **A second independent futures source was not found free.**
- **Per-contract volumes are Yahoo's and may undercount.** The front/second/deferred *ratio* is what
  §2d leans on.
- **SPAN margin (≈39.7 % of notional), MBT commissions, account minimums, BFF specs and Section
  1256 treatment are cited from broker/vendor pages and search results, not from CME**, whose own
  pages are IP-blocked. The margin figure is internally corroborated (MBT and BTC give the same
  ratio) but is **not** a primary-source number.
- **§6a's conditional result is a declared post-hoc search** and its t-statistics are close to
  tautological. It is included because it is the honest strongest case for the trade, and it still
  fails on availability.
- **The 30 % variation-margin buffer in §4 is a judgement**, sized to the measured **p99 10-day
  rally of 31.5 %** — i.e. it is breached about once every 100 ten-day windows, and the historical
  worst (56.4 %) breaches it badly. A different buffer moves the capital multiple and the net.
- **No purchase, no account, no order, no custody action.** Real-money execution remains
  owner-gated and is not proposed here.

---

*First-party measurements taken 2026-08-19 against the Yahoo chart API (CME `BTC=F`/`ETH=F` and
nine live per-contract symbols), the Binance public REST API (151,782 hourly spot bars and 14,976
funding prints), CFTC public reporting (855 COT rows), Yahoo ETF series for IBIT/FBTC/BITB/GBTC,
and this repository's FRED DTB3 cache. CME Group's own endpoints returned HTTP 403 on every path
attempted. Harness `scripts/trading_bot/t24_cme_basis.py`; receipt `CME_BASIS_PROBE.json`; cache
`research/data/t24_cache/`. No order was placed, no account exists, and nothing was purchased.*
