# NEWTERR-OPTIMP — the options-implied surface as a signal for the underlying

**Verdict: the territory is noise.** 109 live formulas, zero survivors. The single
result that cleared the multiple-testing bar in magnitude did so in the *opposite*
sign to its stated mechanism, is reproduced *exactly* by a formula containing no
options data at all, and loses money in **both** directions once costs are charged.

Date: 2026-08-20 · window swept 2011-03-16 → 2026-08-19 · pre-registration:
`research/trading_bot/NEWTERR_optimp_PREREG.json` (written before any result existed).

---

## What the territory is

Not buying options. Reading the listed option surface — each Cboe volatility index
is a model-free integral over a live chain — and using it to size a position in the
**underlying cash ETF**. The claimed mechanism throughout is dealer hedging flow and
informed options flow leading spot.

## Data, all free, all cached

| what | source | coverage |
|---|---|---|
| 20 Cboe implied-vol / skew indices | `cdn.cboe.com/api/global/us_indices/daily_prices/*_History.csv` | daily, full history |
| 15 underlyings those chains are written on | Yahoo daily adjusted closes | 2011-03-16 → 2026-08-19 |

Indices used: VIX, VIX9D, VIX3M, VIX6M, VVIX, SKEW, VXN, RVX, VXD, OVX, GVZ,
VXEEM, VXEWZ, VXSLV, VXTLT, VXAPL, VXXLE, VXFXI, VXGDX, VXEFA.
Cache: `research/data/optimp_cache/` (~9 MB). Nothing large was re-fetched.

### What could NOT be tested — declared, not silently dropped

| signal the brief named | why it is untestable on free data |
|---|---|
| **equity / index put-call ratio** | the Cboe daily market-statistics archive returns **HTTP 403**. No free history exists. |
| **GEX / dealer positioning** | no free historical dealer-gamma series exists at all. Proxied here by curve shape (formulas E1–E3); the proxies failed, which is weak evidence against the proxy, not against GEX. |
| **unusual open interest / options volume** | no free per-strike history. Only the aggregate indices are free. |
| **crypto options (Deribit)** | the free-sample pipeline holds **6 snapshots** — 2022-06-01, 2023-01-01, 2023-06-01, 2024-01-01, 2026-01-01, 2026-06-01. Rich per snapshot (1.3k rows, full chain with IV, greeks, OI) but **6 observations total**. You cannot compute a Sharpe from six points. 25-delta skew, term structure and put/call OI on BTC/ETH are **untested**, not disproven. |
| **VIX1D** | history starts 2022-05-13, entirely inside the holdout. No design window exists for it. |

---

## The three gates, as applied

### G0 — mechanism, with the sign fixed in advance

Every formula carries a one-sentence causal WHY **and a pre-specified position sign
derived from it**. The sign was never read off the data. This is the gate that did
the most work: it is what stopped the one large t-stat from becoming a "finding".

Nine mechanism families:

| family | n | the causal claim |
|---|---|---|
| `termstruct` | 6 | short-dated protection already bought ⇒ dealers long downside gamma ⇒ the forced-selling channel is shut |
| `vrp` | 6 | a fat variance premium keeps vol sellers solvent and supplying gamma |
| `skew` | 4 | a rich left tail means crash insurance is already owned |
| `volofvol` | 3 | VVIX/VIX is the price of convexity; rich convexity ⇒ the synthetic equity sale has been made |
| `gammasign` | 3 | the sign of dealer gamma flips spot's daily autocorrelation (contango ⇒ revert, backwardation ⇒ trend) |
| `reliv` | 14 | an asset's own chain rich vs the benchmark chain ⇒ its specific hedgers have paid up |
| `ownvrp` | 14 | per-asset variance premium, same mechanism name by name |
| `crosssec` | 6 | market-neutral cross-section of the above, so beta cannot masquerade as signal |
| `dispersion` | 3 | index vol rich to component vol = implied correlation = macro hedging done at the index |
| `control` | 1 | **no options information** — unconditional 1-day reversal, to prove the surface adds something |

Two response functions per formula (linear z-weight, and a ±1.5σ tail threshold) —
different bets on *where* in the distribution the mechanism bites. 114 built,
**5 degenerate** (the tail threshold never fires on a signal already bounded in
[-1,1]) and excluded from N as never actually tested. **N = 109.**

### G1 — lag-kill

The Cboe indices print at **16:15 ET, after the 16:00 cash close.** An L=1 backtest
reads a number that does not exist yet. So:

- **L1** — diagnostic only; it measures the 15-minute print-gap artefact.
- **L2 — the headline.** Signal from close *t*, position established at close *t+1*,
  earns return *t+2*. A full day of slack.
- **L3** — the kill test, one further day.

### G2 — statistics

- Design **2012-06-01 → 2019-12-31** (1,908 sessions). Holdout **2020-01-01 →
  2026-08-19** (1,666 sessions), gated behind an env flag and not read until the
  selection rule had run and returned empty.
- Nominal bar **√(2 ln 109) = 3.06 SE.**
- **Measured, not assumed:** 40 replications × 60 random-walk signals pushed through
  the identical pipeline give empirical mean max |t| **2.66**, p90 **3.22**, and a
  t-stat sampling sd of **1.06** — so the nominal bar is honest, marginally
  conservative.
- **Effective independent bets = 15.2** (participation ratio of the design-window
  PnL correlation eigenvalues; mean |pairwise corr| 0.154). The 109 formulas are
  nowhere near 109 independent draws — they are mostly long the same stress factor.
- Costs on **both legs, per side**, on |Δweight| every day: 1.5 bp SPY/QQQ up to
  4.0 bp EWZ/USO, anchored on the M0 tier-A close-print half-spread (mean 1.34 bp)
  plus a slippage pad. Borrow charged on **every short day** at easy-to-borrow
  indicative ETF rates (0.3 %/yr SPY → 2.0 %/yr USO).

---

## Harness self-test — run *before* the null was believed

`scripts/trading_bot/optimp_selftest.py`

| probe | result |
|---|---|
| buy-and-hold SPY, design window | Sharpe **1.14** — the known number |
| planted edge (25 % next-next-day sign + 75 % noise), read at the lag it was planted for | Sharpe **3.03**, t **+8.34** |
| same planted edge read at L=1 / L=3 / L=4 | **−1.74 / −1.04 / −0.42** — the lag-kill test kills a real edge placed at the wrong lag |
| 60 random walks, same pipeline | max \|t\| 3.33 vs bar 2.86; sd(t) = 1.22 |

The machine finds an edge that is there and destroys one that is misaligned by a
single day. The null below is therefore a statement about the territory, not about
the harness.

---

## Result

**Best formula in its pre-specified sign, and the only one above t = +2:**

`A2_TS3_level~tail` — tail-threshold on z(VIX / VIX3M). Mechanism: backwardation of
the front against the 3-month means the whole hedging book has rolled into the
front, so the marginal hedger has already transacted.

| | L1 | **L2 (headline)** | L3 |
|---|---|---|---|
| **design** Sharpe (t) | +0.31 (0.84) | **+0.79 (+2.17)** | +0.65 (+1.78) |
| **holdout** Sharpe (t) | +0.14 (0.36) | **+0.16 (+0.41)** | −0.13 (−0.34) |

It **passes** the lag-kill (L3 holds 82 % of L2) and **passes** the staleness check
(L1 < L2, so nothing lives in the print gap). It **fails** the statistical bar:
2.17 against 3.06. And its holdout is +0.16 Sharpe on 1,666 sessions — t = 0.41,
indistinguishable from zero, with the L3 variant already negative.

**Zero of 109 formulas passed the pre-registered design gate.** Runner-up
`D3_VVIX_level~tail` reached t = +1.39.

### The number that settles it

Across all 109 formulas, **corr(design t-stat, holdout t-stat) = +0.052.**

Knowing how a formula did on eight years of design data tells you essentially
nothing about the next six and a half. That is what a noise territory looks like
from the inside.

---

## The one apparent exception, and why it is not one

`H6_XS_IVoverRV5` — cross-sectional long/short on z(own implied vol ÷ own 5-day
realised vol) across 14 chains — hit **design t = −3.36** (Sharpe −1.22) and
**holdout t = −2.02** (Sharpe −0.79). Above the bar in magnitude, persistent across
both windows, and it survives the lag-kill (L3 −1.06). Under a naive reading this
is a 1.2-Sharpe strategy waiting for a sign flip.

It is not. Four checks, all failed:

1. **The sign is backwards.** The mechanism was pre-specified as +1. Flipping it now
   would be choosing the sign from the design data and then presenting the holdout —
   which I have already seen — as validation. This is precisely the failure the
   programme booked last round: *out-of-sample persistence does not validate a
   broken mechanism.*

2. **It is not a static tilt** (checked, and it passes this one): only **3.4 %** of
   gross exposure is a frozen asset tilt, and a frozen-weight replica scores +0.26
   design / −0.45 holdout. The variation is doing the work — so the question becomes
   *what* variation.

3. **It contains almost no options information.** Decomposing the ratio:

   | leg | design Sharpe (t) | holdout Sharpe (t) |
   |---|---|---|
   | full `z(IV / RV5)` | −1.22 (−3.36) | −0.79 (−2.02) |
   | **`z(1 / RV5)` — realised only, NO OPTIONS** | **−1.10 (−3.02)** | **−0.77 (−1.98)** |
   | `z(IV)` — options only | −0.33 (−0.92) | −0.09 (−0.24) |
   | option leg orthogonalised to realised | −0.70 (−1.93) | −0.71 (−1.82) |

   The realised-vol denominator alone reproduces 90 % of design and 97 % of holdout.
   The implied numerator alone is worth t = −0.92 / −0.24, i.e. nothing. This is a
   cross-sectional low-realised-vol tilt wearing an options costume, and it belongs
   to a family already mined.

4. **Both directions lose after costs.** Running the flipped book properly, with
   borrow charged on the new short side:

   | book | design | holdout |
   |---|---|---|
   | as stated (+1) | −1.22 | −0.79 |
   | **flipped (−1)** | **+0.02** | **−0.13** |
   | flipped, realised-only | +0.04 | −0.10 |

   Flipping −1.22 does not give you +1.22; it gives you +0.02. The book is roughly
   flat gross and its turnover costs ~0.6 Sharpe *in either direction*. The
   "significant" −3.36 was a friction drag on a high-turnover book, not a signal.
   Nothing here is monetisable.

The control formula behaved as a control should: `E4_CONTROL_uncond_reversal`
(no options input) scored −0.22 design / −0.46 holdout, and the three gamma-sign
formulas that were supposed to beat it scored −0.79, −0.82 and +0.23. The option
surface added nothing to the reversal it was supposed to condition.

---

## Honest reading

Every mechanism in this territory shares one weakness: the surface is a *price*, and
a price already contains the hedging flow it is supposed to predict. VIX at 16:15
tells you protection was bought — by 16:15 the dealer has already sold the futures.
The programme's earlier domains died at the friction floor; this one dies one step
earlier, at the information floor. There is no lag at which the surface leads spot
in the free daily data, and the L1-vs-L2 columns show the effect is not even hiding
in the 15-minute print gap.

The three genuinely untested sub-territories are **put/call ratio**,
**per-strike open interest / dealer gamma**, and **crypto options skew**. All three
need data this programme does not have. The Deribit case is the cheapest to fix and
the only one with an existing pipeline: `scripts/trading_bot/deribit_free_snapshot.py`
forward-collecting daily would produce a testable 25-delta-skew / term-structure /
put-call-OI panel in roughly a year. That is a collection decision, not a research
result, and it is consistent with the standing free-data-convexity-wall finding.

## Files

- `scripts/trading_bot/optimp_sweep.py` — the parameterised sweep (114 variants, one vectorised pass, ~2 min, low RSS)
- `scripts/trading_bot/optimp_selftest.py` — harness self-test
- `scripts/trading_bot/optimp_null.py` — empirical null bar + effective-N
- `scripts/trading_bot/optimp_diag.py` — gross-vs-net and static-tilt diagnosis
- `scripts/trading_bot/optimp_h6.py` — the H6 decomposition
- `research/trading_bot/NEWTERR_optimp_PREREG.json` — pre-registration
- `research/trading_bot/NEWTERR_optimp_raw.json` — all 114 rows, every lag, both windows
- `research/trading_bot/NEWTERR_optimp_null.json`, `_diag.json`, `_h6.json`
- `research/data/optimp_cache/` — the fetched panel
