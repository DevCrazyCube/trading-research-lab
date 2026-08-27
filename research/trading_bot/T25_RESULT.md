# T25 — cross-venue perpetual funding differential: DEAD BY INSUFFICIENT POWER, held-out window NOT spent

**VERDICT: DEAD BY INSUFFICIENT POWER.** Both blocking gates fail, against a gate hashed before
the census ran. `2023-06-01 → 2024-09-30` was **not** spent, no pre-registration was written, and
no rule was frozen. Cost: one afternoon and 2.34 M funding prints.

**The one number.** The joint history of the two venues — **every month Hyperliquid has ever
existed** — can only certify an edge of **2.85 pp/yr**. The mechanism's own claim, computed from
T21's published snapshot under the frozen charges, is **1.07 pp/yr**. Certifying that would take
**22.5 years of a venue that is 3.3 years old**.

**And a second, independent death that does not depend on the statistics.** In the window T21
already searched, **none of the four declared configurations clears the frozen +1.00 pp/yr bar**:
the best is `topN = 3` at **+0.74 pp/yr over by-year T-bills (t = 0.53, only 40.9 % of months
positive)**, and the most diversified is **−1.47 pp/yr (t = −2.43)**. The trade's *direction* works
— the trailing differential calls next month's sign **79–84 %** of the time — and it loses to
Treasury bills anyway, because the differential must be halved (collateral is posted at **both**
venues) before it is compared to a 3.84 % risk-free rate.

---

## 0. Provenance

| | file | sha256 |
|---|---|---|
| **power gate, hashed BEFORE the census ran** and with `T25_POWER_CENSUS.json` / `T25_RESULT.md` asserted absent in the same command | `T25_POWER_GATE.md` | `3cc5759d8c3490871f093d66fbb756301601e9eccb30a486e4bfc99a3b5b5838` |
| the census that judges against it | `scripts/trading_bot/t25_census.py` → `T25_POWER_CENSUS.json` | asserts the gate hash at start-up and refuses on mismatch |
| the collector | `scripts/trading_bot/t25_collect.py` | free, keyless, read-only |
| design-window-only diagnostics, written **after** the block | `scripts/trading_bot/t25_diag.py` → `T25_DESIGN_DIAGNOSTIC.json` | — |
| **Hyperliquid hourly funding panel**, 106 coins, **2,340,613 prints**, 2023-05-12 → 2026-07-31 | `research/data/t25_cache/hl/`, manifested per file | aggregate `c068180d166e2995b7b921130aa8e0d94b3d930a2d8ac756456de71e64550c7f` |
| Binance USD-M survivorship-complete panel, reused unchanged | `research/data/t23_cache/panel/` (T23) | as published |

**No order was placed, no account created, no custody action taken, nothing purchased.** Every
byte came from free, keyless public endpoints and from panels this repository already held.

---

## 1. Why this candidate, and why it is not a re-run

`NONDIRECTIONAL_INCOME_SHORTLIST.md` (T21) §5 ranks fourteen non-directional mechanisms. Working
down it, excluding everything already killed:

| T21 rank | mechanism | status entering T25 |
|---|---|---|
| 1 | cross-sectional perp funding carry | **DEAD** — T23, power (`FUNDING_CARRY_VALIDATION.md`) |
| 2 | BTC/ETH funding carry | **DEAD** — `FINDINGS.md` §5d, and T23 |
| **3** | **cross-venue perp funding differential** | **live — this document** |
| 4 | delta-hedged short variance | the equity VRP; harvestable form killed in T21 §4b on this programme's own N1 null |
| 5 | stablecoin depeg reversion | on the task's dead list |
| 6 | CME crypto cash-and-carry | **DEAD** — T24, power (`CME_BASIS_PROBE.md`) |
| 7 | negative-funding harvest | `A = 1` — needs alt-coin **spot borrow rates**, which have no free history anywhere |
| 8 | box spread / synthetic financing | live — §6 below re-scores and probes it |
| 9–11 | hedged staking, securities lending, DEX LP | `D = 1` or `A = 1` in T21 — §5 re-scores two of these |

**Rank 3 is the highest-ranked live mechanism and it is not a carry re-run.** T23 and T24 killed
the harvest of the funding **level** (long spot / short perp, one venue; and the CME basis). This
harvests a **difference between two venues' levels**: delta is exactly zero, there is no spot leg,
no borrow and no basis convergence, and what you are paid for is bearing **two** venues' failure
plus the correlation of their margin calls. Different estimand, different risk, different
accessibility.

---

## 2. The census, gate by gate

Judged against `T25_POWER_GATE.md`. `MDE_annual = 2.80 × sd_annual / √years`, on the estimator
that would actually be used — a monthly-rebalanced equal-weight top-N book, **one observation per
calendar month**, per the `T15_RESULT.md` rule.

| gate | measured | threshold | |
|---|---|---|---|
| **G0** data census — HL coin-months as a share of Binance's over the joint span | **3,068 / 3,497 = 0.877** | ≥ 0.95 | **FAIL** → *the test is not run* |
| **G0b** survivorship proof | **41 of 41** HL-delisted-today coins still return full funding history | ≥ 5 | **PASS**, decisively |
| **G1** power on the window that would be SPENT — **BINDING** | **MDE 6.30 pp/yr** (held-out, 1.336 yr, sd 2.600 %, most-favourable `topN = 20`) | ≤ 1.07 pp/yr | **FAIL by 5.89×** → **POWER-BLOCKED** |
| **G1b** the charitable ceiling, entire joint history — **BINDING** | **MDE 2.85 pp/yr** (3.168 yr, sd 1.811 %) | ≤ 1.07 pp/yr | **FAIL by 2.66×** → **no split of this data can ever work** |
| **G1max** most generous reading that exists (diagnostic) | MDE 2.85 pp/yr | ≤ 11.55 pp/yr | pass — see §3 for why it is worthless |
| **G2** bar separation (diagnostic) | MDE 2.85 pp/yr | ≤ 0.07 pp/yr | **FAIL by 40.7×** |
| **G3** month count | design 21, held-out 14 months with ≥ 20 eligible names | ≥ 18 / ≥ 12 | PASS |
| **G4** capacity (reported, not thresholded) | see §4 | — | — |

**Two blocking gates fail independently.** G0 fails because Hyperliquid listed its coins
progressively: **429 coin-months exist on Binance in the joint span with no Hyperliquid leg at
all**, and the held-out window's first two months (2023-06, 2023-07) have **zero** eligible names.
G1/G1b fail on dispersion against the effect. Either one alone stops the test.

---

## 3. What the arithmetic says, stated so it cannot be re-read favourably

`years_needed = (2.80 × sd / E)²`, at the **most favourable** configuration the gate allows
(`topN = 20`, the smallest dispersion in the declared grid, sd = 1.811 %/yr on the full span):

| effect `E` to be certified | years needed | years available |
|---|---|---|
| **E_claim = 1.07 pp/yr** — T21's own p75 snapshot, net of the frozen charges | **22.5** | **3.17** |
| the same, on the held-out window's dispersion | 46.3 | 1.34 |
| the best net excess actually observed in the burned window (+0.738 pp, `topN = 3`) | **51.7** | 3.17 |
| `E_max = 11.55 pp/yr` — T21's p90 snapshot | 0.19 | 3.17 |

**G1max passes and it is worthless, and the census's own measurement is what makes it worthless.**
`E_max` was derived from T21 §6.3's `p90 |differential| = 32.37 pp/yr` — a **single funding
interval's** cross-section. Measured as the thing a monthly book actually collects, the realised
monthly `|differential|` in the burned window is:

| | p50 | p75 | p90 |
|---|---|---|---|
| **realised monthly, measured here** (1,142 coin-months) | **5.04** | **8.66** | **16.16** |
| T21 §6.3 single-interval snapshot | 2.06 | 11.41 | 32.37 |

> **A one-interval cross-section is not a month's carry.** It has a **2.0× fatter p90** and a
> **2.4× thinner median** than the quantity a monthly book realises. Every scoping number built on
> an instantaneous cross-section — including the one that put this candidate on the list — is
> biased in the tail, and the bias flatters.

Putting the *realised* percentiles through the gate's own frozen charges:

| realised monthly `|differential|` | less 1.591 pp friction, ÷2 capital, less 3.843 pp T-bill | |
|---|---|---|
| p50 5.04 | **−2.12 pp/yr** | negative |
| p75 8.66 | **−0.31 pp/yr** | negative |
| p90 16.16 | **+3.44 pp/yr** | positive — and this is an *oracle*, not a strategy |

Even the p90 line requires picking, every month and with perfect foresight, the decile of names
that will realise the largest differential. The estimator's actual foresight is Spearman **+0.391**
(§5).

---

## 4. Capacity, reported whatever the verdict — and it is a second wall

Measured live on 2026-08-19 across 65 screened Hyperliquid perps:

| | value |
|---|---|
| top-of-book half-spread | median **0.85 bp** (p75 1.35, p90 1.95) |
| impact-price half-spread (≈ \$20 k notional) | median **6.05 bp** — 7× the top of book |
| **top-20 depth, thinner side** | median **\$33,309** (p25 \$20,988) |
| book size at 10 % of that depth per name, `topN = 3` | **\$9,993** |
| … `topN = 20` | **\$66,618** |

**The only configuration with any power at all is `topN = 20`, and it caps the book at \$67 k —
below the \$100 k account.** The `topN = 3` form the differential is largest in caps at **\$10 k**.
Every gross number in this document is a top-of-book number; the impact-price spread says the real
cost at size is 7× that.

---

## 5. What survives the block — three findings, all from the burned window

Reported because they outlive the verdict, and labelled because `T25_POWER_GATE.md` §8 forbids
reading them as evidence for the candidate. **None of this touches 2023-06 → 2024-09.**

**(a) The signal is real and it still loses to Treasury bills.** On 2024-10 → 2026-07:

| `topN` | gross differential | **net excess over by-year T-bills** | t | months positive | sign hit rate | worst month |
|---|---|---|---|---|---|---|
| **3** | 11.01 pp/yr | **+0.738 pp/yr** | 0.53 | 40.9 % | 78.8 % | −9.19 |
| 5 | 9.50 | −0.015 | −0.02 | 31.8 % | 81.8 % | −5.19 |
| 10 | 8.22 | −0.666 | −0.90 | 23.8 % | 83.8 % | −6.56 |
| **20** | 6.61 | **−1.472** | **−2.43** | 19.0 % | 82.4 % | −5.96 |

**The trailing differential predicts next month's sign 79–84 % of the time and the trade still does
not clear a 1 pp bar.** Two arithmetic facts do it: the differential must be **halved** because
collateral sits at both venues, and what is left is measured against a **3.84 %** risk-free rate.
`topN = 20` is *significantly negative*. This is `T11`'s shape again — the spread is real and it is
correctly priced — not `T3`'s friction death.

**(b) Cross-venue differentials ARE persistent, which is the opposite of T23's finding for
levels.** Spearman(trailing month, next month) = **+0.391** on 1,142 coin-months. T23 found that
ranking on Binance funding *level* and taking the richest name **lost 70.67 %/yr gross** — one-month
persistence at that tail is negative. The *differential between two venues* does not behave that
way. The mechanism is not a mirage; it is too small and too late.

**(c) Hyperliquid's own metadata is survivorship-complete, and free.** All **41** coins flagged
`isDelisted` in the download universe still return their full funding history from the public
endpoint — `FTM`, `FTT`, `AI16Z`, `CHILLGUY`, `BADGER`, `BLZ`, `CATI`, `CYBER`, `DOOD`, `ARK`, `AI`,
`BNT` among them. **2.02 %** of selectable coin-months are nonetheless lost when a venue stops
publishing mid-month; a *test* would have to charge a delisting tail for those, as T23 did.

---

## 6. Two of T21's data scores are STALE, and correcting them changes what comes next

Both were re-probed live on 2026-08-19 with the repository's own credentials, read-only.

| T21 §2 claim | probed today | consequence |
|---|---|---|
| **"Alpaca INDEX options (SPX/SPXW): ✗ 404 Not Found. Only American-style ETF options"** | ✗ **WRONG.** `GET /v2/options/contracts?underlying_symbols=SPX` returns `"style": "european"`, `"tradable": true`, **55 expirations out to 2031-12-19**; `/v1beta1/options/snapshots/SPX` and historical daily bars both serve. The paper account is **options level 3**. (`SPXW` is genuinely empty.) | T21 §6.8 scores the box spread `I = 1, A = 3` **because of American early-assignment risk**. On a European, cash-settled SPX box that risk **does not exist**. The candidate's own stated killer is gone |
| **"Solana RPC (`.env` `SOLANA_RPC_URL`): ✗ HTTP 403. Every on-chain yield/staking/DeFi mechanism scores `D = 1`"** | ✗ **WRONG today.** `getHealth` returns **200 `ok`** | T21 ranks #9 hedged staking (11) and #11 DEX LP (8) **on that 403**. Both `D` scores are stale |

### 6a. So I probed the box spread, bounded, before recommending it — and it does not survive either

SPX chains, live NBBO, 2026-08-19. A box bought at `cost` pays `K2 − K1` at expiry, so the implied
**lending** rate is `ln((K2−K1)/cost)/T`. Computed over every strike pair 100–1000 wide:

| expiry | T | at **mid** (median) | at the **executable** price — pay ask, hit bid (median) |
|---|---|---|---|
| 2027-08-20 | 1.00 yr | **+4.08 %** (p25 1.57, p75 7.02) | **+0.06 %** (p25 −4.05, p75 +2.88) |
| 2027-12-17 | 1.33 yr | +4.26 % | +0.28 % |
| 2026-12-18 | 0.33 yr | +3.77 % | −4.62 % |
| *3-month T-bill, FRED DTB3* | | **3.71 %** | **3.71 %** |

> **At mid the one-year SPX box lends at +0.37 pp over T-bills. At the price you can actually
> transact four legs, it lends at +0.06 % — 3.65 pp BELOW T-bills.** The bid-ask on four option
> legs is several times the entire financing spread.

**Two caveats, both stated because they run against this conclusion.** (i) The snapshot was taken
at **02:01 ET with the market closed**, and overnight option quotes are wider than during the
session, so the executable column is an **upper bound on cost, not a session measurement**.
(ii) A box is normally worked as a single combo order, which may fill inside the four-legged
quote — a *fill assumption*, and this programme has M0 precisely because fill assumptions are the
thing it keeps getting wrong. **But the mid column is already decisive on its own terms:** the
cross-strike dispersion at mid is **p25 1.57 % to p75 7.02 %** on a quantity that is a single
financing rate by arbitrage. A quote surface that disagrees with itself by 5.5 pp cannot resolve a
0.37 pp pickup. **The honest label is `I = 1` — T21's own score — for a different and better
reason than the one T21 gave.**

---

## 7. Is the retail non-directional market space exhausted? Not quite — but what is left is small, and none of it is the programme's goal

**I will not say EXHAUSTED, because §6 shows two of the survey's `D` scores were wrong and a survey
with stale scores cannot support a claim of exhaustion.** What I will say is sharper and, I think,
more useful:

> **Every mechanism this programme has left is one of three things: too small to matter, blocked on
> a venue the owner has not chosen, or an income stream whose risk is priced exactly right.** After
> T25 there is no remaining candidate that is simultaneously *different*, *testable on free data*,
> *plausibly powered*, **and** large enough to be a trading bot rather than a cash-management
> tweak.

The live remainder, re-scored with today's probes:

| candidate | testable? | powered? | **size of the prize** | verdict this seat would give |
|---|---|---|---|---|
| **Box spread on European SPX** (`D` 2→4, `A` 3→4 after §6) | **yes** — and uniquely, the estimand is a **rate level**, not a Sharpe, so it would *pass* a power census trivially | yes | **+0.37 pp/yr at mid, negative executable** (§6a) | **not worth a slice.** ~\$370/yr on \$100 k at mid, and the honest execution number is negative. Worth **one** RTH re-measure (an hour) and nothing more |
| **Hedged staking** (`D` 1→? after the RPC came back) | partly | unknown | SOL issuance ~5–7 % less the perp funding cost | **re-imports the whole T23/T25 venue problem** plus slashing and an unbonding lockup during which the hedge cannot be unwound. Ranked below the box |
| **DEX LP** (`D` 1→? after the RPC came back) | yes | yes (per-pool, high n) | fee income **minus adverse selection** | `FINDINGS.md` §7 already names the mechanism: this is the same adverse selection that causes illiquidity in equities, wearing the name "impermanent loss". Prior is that they cancel |
| Negative-funding harvest | **no** | — | — | the funding cost leg (alt-coin spot borrow) has **no free history anywhere**. A carry whose cost leg is unmeasurable is not a measurable carry |
| Securities lending | **no** | — | — | no fully-paid-lending programme available at this broker |

**The pattern across T9, T15, T23, T24 and now T25 is one sentence:** *the free data this programme
can reach resolves effects of 3–15 pp/yr, and every surviving non-directional mechanism offers
0.4–3 pp/yr.* That is not a run of bad luck; it is the same wall five times, and it is why the
remaining shortlist is not worth grinding candidate-by-candidate.

### Recommendation, put to the owner rather than decided here

1. **Concentrate on the real-economy track.** This is the recommendation the task anticipated, and
   T25 is the fifth independent measurement supporting it.
2. **One hour, not a slice: re-measure the SPX box during RTH.** Either it confirms §6a (the four-leg
   spread eats the pickup) and the box is closed by measurement rather than by an overnight
   snapshot, or it does not — in which case a **frozen, rate-level** test becomes the cheapest
   certifiable claim this programme has ever had access to, even though the prize is small. Either
   outcome is worth having; that is the M0/T24 shape.
3. **Do not spend a slice on hedged staking or DEX LP.** Both are live only because a credential
   came back, and both re-import a risk this programme has already priced and rejected.
4. **The venue question is still the owner's and it is still unanswered.** Nothing here needs it —
   testing cost \$0 and touched no venue — but every crypto mechanism on the list needs it before a
   single dollar moves.

---

## 8. What this document does not claim

- **No held-out number exists.** `2023-06-01 → 2024-09-30` was not spent. No pre-registration was
  written; no rule was frozen; `T25_PREREGISTRATION.md` does not exist and must not be written
  against this data.
- **§5's design-window table is not a backtest result.** It is the window T21 already searched,
  reported so the block is not mistaken for "we don't know", and `T25_POWER_GATE.md` §8 forbids
  reading it as evidence for the candidate.
- **The download universe has a stated bound** (gate §2b): coins first listed on Hyperliquid after
  2023-08 are absent, so both the edge and the dispersion measured here may be understated. The
  direction is generous to the candidate for the edge and hostile for the power, and it is stated
  in the gate rather than discovered afterwards.
- **Mark divergence between the two venues' perps is not modelled.** Omitting it can only shrink
  the dispersion, i.e. it can only *help* the candidate pass G1, and it still fails.
- **Fee schedules are cited, not verified** (Binance USD-M taker 5.0 bp, Hyperliquid taker 4.5 bp).
  The spreads and depths beside them are first-party.
- **The §6a box measurement is a scoping probe taken with the US market closed**, not a frozen test,
  and it is labelled that way in the same section as its number.
- **US accessibility of Binance.com perpetuals to a US person remains asserted, not probed** —
  T21 §8's own caveat, unchanged and still load-bearing.

---

*T25 run 2026-08-19. Gate `3cc5759d…` hashed before the census; census and diagnostics assert it.
No order, no account, no custody action, no purchase. Real-money execution remains owner-gated.*
