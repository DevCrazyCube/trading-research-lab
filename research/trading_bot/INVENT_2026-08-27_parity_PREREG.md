# INVENT_2026-08-27 — PRE-REGISTRATION: put-call-parity implied carry on the free DoltHub options panel

**Date/tick:** 2026-08-27 03:00 CEST (supervisor CHUNK B). **Written before any number was read.**
**Scope:** research only, no orders, no money, no network (all reads from `research/data/doltopts_cache/`,
`research/data/t15_cache/daily_bars.json.gz`, `research/data/ratescredit_cache/fred_daily.json`). No basket action
under any outcome (BASKET1 clock locked 2026-08-24).

## 0. Why this object is not already dead
`grep` of the whole research corpus for `put-call parity | implied borrow`: **0 files**. Everything previously run on
this panel (`DOLT_OPTIONS.md`, T35 design) used IV / greeks / skew / term / strangle cost. The **synthetic forward**
implied by parity — a *law*, not a model — has never been extracted. It is the one published-by-construction tether
on this panel: `C − P = S·e^{−(q+b)T} − K·e^{−rT}` holds bid-to-ask or there is a riskless arb, so `F = (C−P)e^{rT} + K`
is a synchronous, public, spread-bounded anchor for `S`. (T7 ex-dividend, leveraged-ETF RV, CEF tender, spin-offs are
all closed and are *not* this object.)

## 1. Mechanism (stated before looking)
Implied carry `c = r − ln(F/S)/T` = the market's dividend-plus-borrow yield. Two things could live in its cross-section:
(a) a genuine hard-to-borrow / lending-fee signal (the published Ofek–Richardson–Whitelaw shape: high implied borrow →
low subsequent return) — on a 51-name mega-cap, general-collateral universe I expect it to be **absent** (borrow ≈ 0
for all names, so `c` is dividend yield + noise); (b) an **asynchrony artifact**: if the EOD option snapshot is stamped
earlier than the stock close, `F` carries an earlier `S`, so `c_res ∝ +(late-day stock move)/T` and any "edge" from
shorting high-`c` names is just a fade of the late-day move, executable only off the signal's own print (0823 Clause 3).
This round is designed to **tell (a) and (b) apart**, and to answer a data question the programme actually cares about:

**Sub-question D (data-acquisition substitute).** The 2026-08-22 memory ranks a *borrow-availability feed* as the #1
paid-data ask. Can the free panel measure borrow at all? Verdict rule: measurable iff median cross-sectional IQR of
`c_res` > 2 × median per-observation quote-noise floor (`hw/(S·T)`, `hw` = mean half-width of the `C−P` bid/ask band
over the strikes used). Prior: **not measurable** on mega-caps (band width vs 1–3%/yr signal).

## 2. Construction (fixed)
- Universe: the 51 cached names (incl. SPY). Snapshots: all cached dates ≥ 2020-01-01 with 6 forward daily bars.
- Rate `r`: FRED `DGS1MO` (fallback `DGS3MO`) last value on/before the snapshot, decimal.
- Per (date, symbol): the **longest** expiry with 20 ≤ DTE ≤ 65 (so an ex-date inside the window is most often
  included and per-strike noise/T is smallest). Strikes within ±7.5 % of `S` with **both** call and put `bid > 0` and
  `ask ≥ bid`; require ≥ 3 such strikes. `F_K = (C_mid − P_mid)·e^{rT} + K`; `F = median_K F_K`; `c = r − ln(F/S)/T`.
- Dividend robustness: `c_res = c − median(c over the symbol's prior 26 snapshots, min 8)`, strictly backward.
- Noise floor per observation: `nf = mean_K[0.5·((C_ask−C_bid)+(P_ask−P_bid))] / (S·T)`.
- Cross-section each snapshot: rank `c_res`, terciles (≈17/17). L/S book = **long LOW `c_res`, short HIGH `c_res`**,
  equal-weight, each leg 100 % (sign fixed now; the published prior direction).
- Returns: `t15_cache` adjusted daily closes (total-return-ish). Snapshot date mapped to its bar; if the bar is missing
  the snapshot is dropped.

## 3. Formulas (N = 2 return formulas + 1 diagnostic + 1 data verdict)
- **F1 — executable:** enter close(t+1), exit close(t+6), 5-session hold, contiguous weekly books.
- **F2 — same-print (non-executable, diagnostic only):** enter close(t), exit close(t+5). Can NEVER promote anything.
- **F3 — asynchrony diagnostic:** pooled regression of `c_res` on the snapshot-day open→close stock return (panel's own
  `stocks` table). Report slope, t, R². R² > 0.10 with t > 3 ⇒ the signal is contaminated by stamp asynchrony.
- **D — borrow measurability** per §1.

## 4. Bars, split, cost, kill (frozen)
- Split: **design 2020-01-01 → 2023-06-30**; **held-out 2023-07-01 → latest**. Held-out returns are read ONLY if F1
  clears BOTH design bars. F2/F3/D are computed on both windows regardless (diagnostics, not promotions).
- Gross bar: weekly-cluster t ≥ **2.5** on the F1 book AND F1 mean > p99 of **1,000 size-matched random-tercile
  placebo draws** (same dates, same leg sizes). 2.5 ≥ √(2 ln 2) pooled bar for the 2 return formulas with margin.
- Cost (only applied if gross clears): 1.5 bp half-spread per side per name → 3 bp round trip per name, both legs
  → **6 bp/week on the book**, + GC borrow 0.3 %/yr ≈ 0.6 bp/wk. Net bar: net mean > 0 with t ≥ 2.5 on held-out.
- KILL: F1 design gross t < 2.5 or ≤ placebo p99 → **DEAD** (family: parity-implied-carry cross-section, mega-cap,
  weekly). F1 clears design but not held-out → DEAD. F2 clears while F1 does not → DEAD, labelled *Clause-3
  non-executable / asynchrony artifact* (and F3 must show it). D: measurable / not measurable, recorded either way.
- Expectation written now: **all dead; D = not measurable.** Basket: untouched in every branch.

Files: this doc + sha256 sidecar; `scripts/trading_bot/invent_0827_parity.py`; results
`research/trading_bot/INVENT_2026-08-27_parity.{json,md}`.
