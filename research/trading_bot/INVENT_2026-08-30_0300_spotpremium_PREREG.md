# PRE-REGISTRATION — spot-BTC ETF closing premium vs the 24/7 instant spot tether, next-open hedged

**Written 2026-08-30 03:2x CEST (durable supervisor, CHUNK B) BEFORE any number was computed.**
Admissibility (08-27 rule): a *published, synchronous tether outside the dead ledger*. Tether =
BTC/USD instant spot at 16:00:00 ET × the sponsor-published coins-per-share (constant up to a
0.25 %/yr fee drift ≈ 0.1 bp/day, ignored). Hedge leg = BTC perpetual → **no borrow wall**.

## 1. Why this is not already on the ledger (checked before writing)
- `INVENT_0823_exotic.md` theme C (10 formulas) traded **ETP vs ETP** on the same coin. That construction
  cancels the premium every wrapper shares against spot; it can only see idiosyncratic wrapper noise.
  Verdict there: the d1/z20 reversals paid only on the signal's own print (C3 −0.85 next-open vs +21.45
  own-print) — closing-print bounce, dead. The **common** premium vs the 24/7 spot tether was never measured.
- `INVENT_0822_crypto_tether` traded tokens on crypto venues (wBTC/XAUT) — different wrapper and clock.
- Carry/funding on the ETF-vs-perp pair is NOT proposed (carry dead 4 ways; perp-funding window closed 08-25).

## 2. Data (all free, all already cached or a single bounded fetch)
- ETF: `research/data/exo0823_cache/IBIT_1Day_2024-01-01_2026-08-20_sip_all.json` (Alpaca SIP daily,
  `o` = 09:30 opening print, `c` = official 16:00 close). No distributions → adjustment irrelevant.
- Spot: Binance `BTCUSDT` 30-minute klines, 2024-01-10 → 2026-08-21, fetched once to
  `research/data/inv0830_cache/BTCUSDT_30m.csv`. Instant prices used: **open of the candle that starts at
  16:00:00 ET** (20:00 UTC in EDT / 21:00 UTC in EST) and **open of the candle starting 09:30:00 ET**
  (13:30 / 14:30 UTC). US DST rule applied per date.

## 3. Formula (fixed)
- `p_t = ln(IBIT_close_t / BTC_16:00_t)`; `prem_t = p_t − median(p_{t-20..t-1})` (trailing, excludes t).
- `s_t = −sign(prem_t)` (fade the premium).
- Hedged next-session return, bp: `r_{t+1} = 1e4 · s_t · [ln(IBIT_c/IBIT_o)_{t+1} − ln(BTC_16:00/BTC_09:30)_{t+1}]`.
  Entry at the 09:30 ET open of t+1 (never the signal's own print — Clause 3), exit at the 16:00 close.
- **F1** = all sessions; **F2** = sessions with `|prem_t| > 10 bp` only. **Charged: 2 formulas.**
- Diagnostics (recorded, NOT candidates): **D0** own-print version (enter close t, exit close t+1) to
  show the bounce as in C3/C6; **D1** sd and lag-1 autocorrelation of `prem_t` (size of the object).

## 4. Windows
- Design: sessions 2024-02-09 → 2025-08-31 (first 20 sessions burn the median).
- Held-out: 2025-09-01 → 2026-08-20. **Read only if every design gate passes**; the script prints it only then.

## 5. Gates and kill-condition (design window)
- Friction floor: IBIT half-spread ≈ 1 bp × 2 ETF legs + perp taker 3.5 bp × 2 = **9 bp/trade** (maker not credited).
- G1 mean gross `r` ≥ 9 bp/trade; G2 plain t ≥ 2.5 (Newey-West lag-5 t also reported, must be ≥ 2.0);
  G3 sign-flip placebo (2,000 resamples) p < 0.01; G4 shifted-signal placebo (`prem_{t-5}` in place of
  `prem_t`) must NOT itself pass G1+G2.
- Held-out (only if design passes): mean ≥ 9 bp and t ≥ 2.0.
- **Kill: any design gate fails → family DEAD** and the dead ledger gains the row *"spot-crypto ETP vs 24/7 instant
  spot, common closing premium reversal, next-open hedged"*; no re-proposal of any spot-crypto-ETP-vs-spot object at
  a 1-session horizon. F2 failing while F1 passes does not rescue F2, and vice-versa.

## 6. Stated prior (honest)
DEAD. The 08-23 C-family showed a closing-print signal cannot pay at the next open; the common premium is
arbitraged by APs at the NAV strike and the overnight resets it. Expected |mean r| < 5 bp, |t| < 1, D0 large
and positive (bounce). This test exists to close the family, not to open it.

## 7. Untouched
BASKET1 frozen file, t4 path, window-2, all forward collectors: not touched. No commit, no orders, no spend.
