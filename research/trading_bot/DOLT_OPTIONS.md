# DOLT_OPTIONS — first honest test of the free DoltHub equity-options panel

**Date:** 2026-08-25 · **Scope:** research only. Free data only (DoltHub SQL API, CC-licensed
`post-no-preference/options` + `post-no-preference/stocks`). No dolt CLI needed, no accounts, no
payment, no orders, no git commit. One detached bulk fetch (weekly sampling, ~50 names, 2019–2026)
after small verification queries.
**Question the programme set:** the standing conclusion is *"the wall is data, not ideas."*
`FREE_DATASET_HUNT.md` found one genuinely NEW free capability never used — historical US equity
options with IV + full greeks. Does it open a REAL cross-sectional dealer-positioning / skew /
term-structure / vol edge, or is it another confirmation that the signal is priced-in / too small?

---

## 0. TL;DR

- **Access established, free, via the DoltHub SQL API** (no CLI, no key). Endpoint verified:
  `https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q={SQL}`. Schema, coverage
  and the real (severe) query limits are documented in §1.
- **Pulled** a weekly panel of ~50 liquid single names, 2019-05→2026-08 (**342 usable weekly
  cross-sections, avg 49.5 names each**), option greeks + IV joined to underlying open/close from the
  sibling `stocks` DB. Cache: `research/data/doltopts_cache/`.
- **Ran the first honest test**: five cross-sectional, single-name, **directional-on-the-stock**
  signals (skew risk-reversal, put-slope, short-end term slope, IV level, IV change), design/held-out
  split declared before scoring, pooled multiple-testing bar + size-matched placebo.
- **VERDICT: HONEST ZERO. Nothing clears the design bar (2.40 t); best design t = 1.30 (IVLEVEL).**
  The one signal that looks significant out of sample (PUT_SLOPE held-out t 2.07) has the **opposite
  sign to its own design window (−0.89) and to its pre-registered prior** — a sign-flip, i.e. noise.
  The only sign-consistent signal (IVLEVEL) is **pure market beta: alpha_t = 0.00** once the
  equal-weight market is regressed out, in both windows. **The new options data does NOT open an edge
  on this family.** It is another confirmation of the wall — with three *structural* reasons why this
  particular free panel was never going to (§4), which is the durable finding.

---

## 1. ACCESS — what works, the schema, the coverage, and the real limits

### 1a. The working free route: the DoltHub SQL API (route (a) in the brief)
No CLI install and no CSV export were needed. The correct call is:

```
https://www.dolthub.com/api/v1alpha1/{owner}/{repo}/{branch}?q={URL-encoded SQL}
  owner=post-no-preference  repo=options  branch=master
```

`SHOW TABLES` and `DESCRIBE` verified live. Two tables:

**`option_chain`** (PK = date, act_symbol, expiration, strike, call_put):
`date, act_symbol, expiration, strike, call_put, bid, ask, vol(=IV), delta, gamma, theta, vega, rho`.
**No open interest, no volume** (as the hunt flagged). One EOD snapshot/day. Greeks & IV are
model-derived (Yahoo-grade). `decimal(5,4)` precision on IV/greeks.

**`volatility_history`** (PK = date, act_symbol): per-symbol daily `iv_current, hv_current` plus
week/month-ago and 52-wk high/low for both IV and HV. A compact IV/HV summary — useful for a VRP
cross-section, but see the query-limit caveat below.

### 1b. Coverage (verified)
- `MIN(date)=2019-02-09`, `MAX(date)=2026-08-21` (current, ~T-2). `volatility_history` carries
  **2322 distinct symbols**.
- **Cadence is NOT clean-daily before 2020.** 2019 is a sparse backfill — most 2019 weeks return no
  rows (probed directly). Dense ~daily coverage runs **2020-01 → present**. So the usable design
  window is effectively 2020+ (the maintainer's "daily since April 2021" PIT claim holds; 2019–2020
  is thinner backfill).
- **Expirations are FRONT-MONTH ONLY.** Measured across all fetched dates: max DTE per name is
  ~44–65 days (median ~51). There is **no 90-day / LEAP tenor** — only the front ~3 expiries
  (~2wk, ~1m, ~7wk). This kills a true 1M-vs-3M term-structure signal (see §4).

### 1c. The real access constraint (new, important, not in the hunt)
The SQL API is free but **only `date=` equality (the leading PK column) is fast (~1–1.5 s).**
Everything else hits an internal **~55 s query wall** and returns `context deadline exceeded`:
`COUNT(*)`/`COUNT(DISTINCT)`, `SELECT DISTINCT date`, any `act_symbol`-only filter, and **any
date-range scan** — even a single symbol's one-year slice, and even on the small `volatility_history`
table. Responses are also **capped at 1000 rows** (`RowLimit`). Net effect: **you cannot bulk-scan or
aggregate through the API at all.** The only robust primitive is a per-`(date, symbol)` point query
(returns the full ≤~200-row chain in ~1.3 s). A `dolt clone` (route (b)) would lift this but was
unnecessary for a focused universe; for a full-universe daily pull the CLI clone would be the right
tool. This is a genuine, previously-unrecorded property of the source and belongs in the ledger.

**Fetch design forced by 1c:** weekly (every Wednesday, nearest populated day) × ~50 fixed liquid
names, one full-chain point query per `(date, symbol)` + one universe OHLC query per date against the
`stocks` DB. ~18k point queries, 6-way, ~70 min detached (the API throttled us mid-run — confirming
"reasonable volume" is finite; concurrency was kept low deliberately). Script:
`scripts/trading_bot/dolt_options_fetch.py`. Cache: `research/data/doltopts_cache/<DATE>.json`.

---

## 2. THE TEST — design

**Why cross-sectional single names, and why directional-on-the-stock.** Dealer-gamma/GEX on SPY was
already flagged degenerate, and **GEX is not buildable here anyway — it needs open interest, which
this panel lacks.** So the honest, data-appropriate object is the **cross-section of single-name
option-implied signals predicting the underlying's forward return**, executed **on the stock** (a
liquid, cheaply-costed instrument on the programme's measured auction rail). Crucially, the signal
(option IV/greeks) and the P&L instrument (the stock) are **different**, so the Clause-4
same-print-bounce inflation that plagues RV spreads does not apply, and the ρ1(Δs) measurement-error
gate is not the relevant filter (this is not a spread-reversion book).

**Signals (pre-registered), each a weekly cross-sectional rank → dollar-neutral rank-weighted book:**

| signal | definition | pre-registered prior (sign of long-high book) |
|---|---|---|
| `SKEW_RR` | IV(25Δ put) − IV(25Δ call), ~30d | −1 (Xing-Zhang-Zhao smirk: high put skew → underperform) |
| `PUT_SLOPE` | IV(25Δ put) − ATM IV, ~30d | −1 |
| `TERM` | ATM IV(~51d) − ATM IV(~16d) — **short-end slope only** | ±1 (ambiguous — both tested) |
| `IVLEVEL` | ATM IV ~30d (xs rank) | −1 (Ang lottery: high IV → low return) |
| `IVCHG` | ATM IV ~30d change vs prior sample | −1 (rising IV → deteriorating) |

**P&L:** signal from the option chain at close(t); hold the stock close(t)→close(t+1wk). No
lookahead (all inputs known at close t; both option snapshot and stock close are ~16:00). Forward
return from the `stocks` DB.

**Multiple-testing:** family N = 5 signals × 2 sign directions = **10 formulas** (both signs of every
signal counted, the honest conservative choice given TERM's ambiguous prior). Bar = max of analytic
√(2 ln N)=2.146 and a **size-matched placebo** (permute the signal across panel slots, weights left
attached, 400 draws, 95th pct of family-max |t|) = 2.399. **Operative bar = 2.399 t.**

**Split (declared before scoring):** design 2020–2023-12-31 (**209 weeks**), held-out
2024-01-01→2026-08 (**133 weeks**), held-out read once. Scripts:
`scripts/trading_bot/dolt_options_analyze.py`, `_robust.py`. Results: `DOLT_OPTIONS_RESULT.json`.

---

## 3. THE TEST — results

| signal | sign | DESIGN Sharpe | DESIGN t | clears 2.40? | HELD-OUT Sharpe | HELD-OUT t |
|---|---:|---:|---:|:--:|---:|---:|
| SKEW_RR | +1 | −0.37 | −0.74 | no | +1.06 | +1.69 |
| SKEW_RR | −1 (prior) | +0.37 | +0.75 | no | −1.05 | −1.68 |
| PUT_SLOPE | +1 | −0.45 | −0.89 | no | +1.30 | **+2.07** |
| PUT_SLOPE | −1 (prior) | +0.44 | +0.88 | no | −1.30 | −2.09 |
| TERM | +1 | −0.39 | −0.79 | no | +0.60 | +0.95 |
| TERM | −1 | +0.39 | +0.79 | no | −0.60 | −0.96 |
| IVLEVEL | +1 | +0.65 | **+1.30** | no | +0.60 | +0.95 |
| IVLEVEL | −1 (prior) | −0.65 | −1.30 | no | −0.60 | −0.96 |
| IVCHG | +1 | −0.31 | −0.63 | no | −0.48 | −0.76 |
| IVCHG | −1 (prior) | +0.32 | +0.63 | no | +0.47 | +0.76 |

**Nothing clears the design bar. Best design t is 1.30 (IVLEVEL), 0.54× the bar.** Signal coverage is
full (finite = 1.00 for every signal, real cross-sectional dispersion) — the zero is a true null, not
an empty-panel artifact.

### 3a. Why the two "interesting" held-out numbers are not edges
- **PUT_SLOPE +1, held-out t 2.07 — a SIGN-FLIP.** Its design t is **−0.89** (opposite sign) and the
  positive sign is **opposite the pre-registered Xing prior** (high put-skew should predict *lower*
  returns). A signal that is negative in design and positive out of sample, against its own
  hypothesis, is noise, not a discovery. It also **decays within the held-out** (first half t 1.94 →
  second half t 1.05). Same story for SKEW_RR (design −0.74, held-out +1.69, wrong sign, decaying
  1.55→0.94).
- **IVLEVEL +1 — the only sign-consistent signal, and it is PURE BETA.** Long-high-IV is positive in
  both windows (t 1.30 / 0.95) but sub-bar, and a regression of the book on the equal-weight market
  return gives **β = 0.49–0.53 and alpha_t = 0.00 in BOTH design and held-out.** High-IV ≈ high-beta;
  the entire tilt is market exposure in a 2020–2026 up-market, with **zero option-information alpha**.
  This is the F5/`INVENT_0823` "a book with market beta is not an alpha" trap, caught by the control.

**Cost is moot** (as in `EXECUTION_COST_WALL`): gross fails the significance bar before a basis point
is charged, so the auction rail / 2.5 bp taker distinction cannot rescue anything.

---

## 4. VERDICT — the data does not open an edge, and three STRUCTURAL reasons why it can't here

**This is another confirmation that the signal is priced-in / too small — an honest zero — not a new
lead.** BASKET1 is locked; there is **no proposal**. But the round is not empty: it converts a vague
"Yahoo-grade" caveat into three concrete, pre-tradeable limits on what *this* free panel can ever
test, each mapping to an `INVENT_0823` clause:

1. **No open interest / volume → no dealer-positioning signal is even constructible.** GEX and any
   real dealer-gamma/pinning measure need OI to weight the strikes by actual inventory. Model greeks
   alone give per-contract gamma but not *whose* gamma or *how much* is outstanding. The "dealer
   positioning" candidate in the brief is **data-blocked at the source**, not merely weak.
2. **Front-month-only expirations (max ~50–65 DTE) → no real term structure.** The classic Vasquez
   1M-vs-3M IV-term-slope predictor is untestable; only a compressed ~2wk-vs-7wk slope exists, and it
   is noise here (t < 1 both windows).
3. **A single Yahoo EOD snapshot of uncertain timestamp → Clause-2 async-clock risk on anything
   vol-vs-realized.** The snapshot is not a guaranteed 16:00 mark, so any close-to-close realized-vol
   comparison inherits the same asynchrony that manufactured ρ1→−0.5 artifacts elsewhere. We sidestep
   it by trading the *stock* off the option *rank* (async only adds noise to the signal, no bounce in
   P&L) — which is why the result is a clean null rather than a spurious high-Sharpe mirage. But it
   means the "IV-vs-subsequent-realized" (VRP) family cannot be run cleanly on this feed either.

What the skew/level cross-section *can* be tested cleanly (directional stock book) **was** tested, and
it is priced-in: the Xing smirk and the vol-level lottery effect **do not survive** on this liquid
~50-name large-cap universe, 2020–2026, out of sample. (Both are documented single-name equity
anomalies historically strongest in small/illiquid names and pre-2015 — consistent with them being
arbitraged away / absent in a mega-cap universe on recent data.)

**Honest residual optionality (NOT claimed as an edge, logged so it isn't re-derived as "untried"):**
the one thing this panel supports that the programme genuinely hasn't run is an **earnings-date
IV-crush event study** (per-name front-month ATM IV run-up into, and collapse after, scheduled
earnings — a *time-series, single-name* object, not a cross-section, and one where the front-month-only
limitation does not bite). `post-no-preference/earnings` supplies the free PIT earnings calendar to
align it. It is exploratory and, like every short-vol-around-events idea, most likely dies on the
straddle spread — but it is the only untested corner, and it needs a synchronous-fill caveat (Clause
2/4). Everything cross-sectional in skew/term/level/change is now **dead on this data**.

---

## 5. Additions to the DEAD ledger (do not re-propose on this free options panel)

1. **Cross-sectional 25Δ put-call skew (risk-reversal) → forward stock return** — sign-flips
   design↔held-out, sub-bar. Dead on liquid mega-caps 2020–2026.
2. **Cross-sectional put-slope (25Δ put − ATM) → forward return** — same; the held-out t 2.07 is a
   wrong-sign, decaying artifact.
3. **Short-end IV term slope (~2wk vs ~7wk) → forward return** — noise (|t|<1). True 1M-vs-3M is
   **not constructible** (front-month-only data).
4. **Cross-sectional ATM-IV level → forward return** — sign-consistent but **pure market beta,
   alpha_t = 0.00**. Not an alpha.
5. **Cross-sectional 1-week IV change → forward return** — noise.
6. **Any GEX / dealer-gamma / pinning signal on this feed** — **not constructible**: no open interest.

---

## 6. Files

```
research/trading_bot/DOLT_OPTIONS.md                 <- this file
research/trading_bot/DOLT_OPTIONS_RESULT.json        <- design/held-out numbers, bar, per-signal
scripts/trading_bot/dolt_options_fetch.py            <- detached SQL-API fetcher (per-(date,symbol))
scripts/trading_bot/dolt_options_analyze.py          <- signal build + MT bar + placebo + split
scripts/trading_bot/dolt_options_robust.py           <- coverage, beta decomposition, sub-period
research/data/doltopts_cache/<DATE>.json             <- 346 weekly panels, 2019-05..2026-08 (free)
```

**Bottom line:** access to the new free options data was established at zero cost and the first honest
cross-sectional test was run end-to-end. **The data opens no edge** — the skew/term/level cross-section
is priced-in on liquid names, the one OOS-significant number is a sign-flip, and the one consistent
tilt is beta. More durably, three structural limits of this specific free feed (no OI, front-month
only, async EOD snapshot) mean it can never test the highest-value objects (dealer GEX, real term
structure, clean VRP) at all. This *sharpens* "the wall is data": even a genuinely new free dataset
that clears the license/existence bar can still fail the **granularity** bar (OI, tenor, synchronous
clock) that the actual edges require. Research only; no orders, no money, no basket change, no commit.
