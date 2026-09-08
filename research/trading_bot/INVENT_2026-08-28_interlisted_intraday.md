# INVENT 2026-08-28 03:00 — Interlisted TSX/NYSE intraday convergence: can a FREE intraday feed see it? (measurability probe, pre-registered)

**Status:** pre-registered before any number was read. CHUNK B (INVENTION) tick, durable supervisor, 2026-08-28 03:00 CEST.
**Family:** structural residual #3 (`structural-not-predictive` memory; `DEEPMINE_crosslist.md` §"What would change the answer";
`DEEPMINE_MASTER.md` §7). Admissible under the 08-24 directive: it is a **published synchronous tether** (the other venue's
print at the same instant, TSX and NYSE share the 09:30–16:00 ET session) that is explicitly OUTSIDE the dead ledger (the
family was killed only on DAILY closes, where Δspread ρ1 = −0.49 showed the free feed measured its own error).
This is NOT a strategy sweep and reads NO return, PnL, or sign. It answers one question so that a collector is either
built or refused for a stated reason.

## Question
On free 1-minute bars (Yahoo chart API, `interval=1m`, `range=5d`; TSX line in CAD, NYSE line in USD, `CAD=X` 1-minute
USDCAD), does the interlisted basis `s_t = ln(P_TSX,t / USDCAD_t) − ln(P_NYSE,t)` carry a measurable persistent component,
or does the free intraday feed — like the free daily feed — mostly see its own bar-construction noise?

## Pre-registered design (frozen)
- Pairs (5, fixed, most liquid interlisted names, one per sector, no selection after the fact): RY.TO/RY, TD.TO/TD,
  ENB.TO/ENB, CNQ.TO/CNQ, SHOP.TO/SHOP.
- Bars: minute close on both venues on minutes where BOTH have a bar; FX = minute close of `CAD=X` at the same stamp
  (forward-fill ≤ 5 min allowed for FX only; equity bars never filled). Regular session only (Yahoo returns none other).
- Per pair, per session: `Δs` over consecutive matched minutes; statistics pooled across the ≤5 sessions:
  - `sd(Δs)` in bp; `ρ1(Δs)` (lag-1 autocorrelation of the basis change);
  - iid-noise decomposition (same model as `DEEPMINE_crosslist.md`): `var(e) = −cov(Δs_t, Δs_{t−1})` if positive,
    persistent-innovation `σ_p = sqrt(max(0, var(Δs) − 2·var(e)))` per minute (bp);
  - level dispersion: `p95 |s_t − median_session(s)|` in bp — this INCLUDES noise, so it is an UPPER bound on the true
    premium dispersion.
- Retail friction floor for the two-venue round trip (frozen, deliberately LOW): 2 × (NYSE half-spread ≈ 1.5 bp +
  TSX half-spread ≈ 1.5 bp + FX ≈ 1 bp) = **8 bp**, commissions and the multi-day cross-border journal excluded.
  Any real number is higher; using a low floor makes a "dead" verdict conservative.

## Kill-conditions (frozen before reading)
- **K1 (feed measures its own error):** median pair `ρ1(Δs) ≤ −0.35` → the free 1-min bar basis is dominated by iid
  bar-construction noise exactly as the daily feed was; a free bar-based intraday forward-collect is REFUSED (would
  collect noise); residual #3 becomes a PAID Level-1 quotes item (both venues + FX), joining the paid-data menu.
- **K2 (below friction even on the noisy upper bound):** median pair `p95 |s − median|` < 8 bp → even the
  noise-inflated dispersion cannot pay the lowest plausible retail round trip; the retail object is dead ex ante
  regardless of measurability.
- **PASS (would open a collector task, nothing else):** median `ρ1(Δs) > −0.20` AND median `p95 |s − median|` ≥ 8 bp.
- Either kill = no collector, family stays on the dead ledger as "not measurable / not payable on free data".
- Ex-ante expectation (honest): K1 fires (ρ1 near −0.4…−0.5 from asynchronous last-trade stamps inside each minute
  across two venues); K2 likely fires for RY/TD/ENB. The prior that the true effect is single-digit bp is the shop's own
  finding; nothing here can revive a daily-close object.

## Multiple-testing accounting
5 pairs × 1 metric family, no return read, no sign choice, no parameter search: zero formulas charged to the bar. If a
PASS ever led to a strategy, THAT would be pre-registered separately against the 08-26 pooled bar.

## Script
`scripts/trading_bot/inv0828_interlisted_probe.py` (stdlib only; 11 HTTP requests; writes
`research/trading_bot/INVENT_2026-08-28_interlisted_intraday.json`). Results appended below AFTER the pre-registration
hash was recorded in `research/FINDINGS.md`.

## RESULT (read once, 2026-08-28 01:03 UTC, after the hash `c63fb72f…` was stamped on FINDINGS)
Sessions 2026-08-24..27 (4 per pair; Yahoo `range=5d` returned four RTH sessions), FX bars 5,878.

| pair | sessions | matched min | sd(Δs) bp | ρ1(Δs) | noise sd bp | σ_p/min bp | p95 dev bp | median dev bp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RY.TO/RY | 4 | 1463 | 3.65 | -0.471 | 2.5 | 0.88 | 4.79 | 1.42 |
| TD.TO/TD | 4 | 1531 | 3.11 | -0.531 | 2.26 | 0.0 | 4.56 | 1.17 |
| ENB.TO/ENB | 4 | 1557 | 2.11 | -0.466 | 1.44 | 0.55 | 3.14 | 0.98 |
| CNQ.TO/CNQ | 4 | 1555 | 2.31 | -0.478 | 1.6 | 0.49 | 3.44 | 1.08 |
| SHOP.TO/SHOP | 4 | 1470 | 9.61 | -0.504 | 6.83 | 0.0 | 7.17 | 1.91 |

- **Medians: ρ1(Δs) = -0.478, p95 |s − session median| = 4.56 bp.**
- **K1 FIRES** (−0.478 ≤ −0.35): the free 1-minute basis change has the ρ1 ≈ −0.5 signature of pure iid measurement
  noise — identical to the daily-close result (Canada −0.491). Noise sd 1.4–6.8 bp/min vs a persistent innovation of
  0.0–0.6 bp/min; for SHOP the persistent component is not distinguishable from zero at all. Free bars see their own
  last-trade-stamp error, not the premium.
- **K2 FIRES** (4.56 < 8 bp): even the noise-INFLATED p95 dispersion of the basis is 3–7 bp, below the deliberately low
  8 bp two-venue retail round trip. The true premium (an upper bound of ~1 bp median deviation, session medians −0.4…+0.9
  bp) is an order of magnitude under retail friction. This matches the shop's earlier "single-digit bp" prior — it is
  in fact ~1 bp.
- **Verdict: DEAD, twice over.** (a) A free bar-based intraday forward-collect is REFUSED — it would collect noise
  (no collector task opened). (b) The retail two-venue object is dead ex ante on the noisy upper bound, so even paid
  Level-1 quotes on both venues would only measure a ~1 bp premium that no retail account can pay 8+ bp to harvest.
  Residual #3 is therefore NOT added to the paid-data menu; it is retired from the structural map as
  "real, ~1 bp, HFT-only". Do not re-propose interlisted convergence at any bar resolution.
- Multiple-testing charge: 0 formulas (measurement only, no return/sign read). Artifacts:
  `INVENT_2026-08-28_interlisted_intraday.json`, `scripts/trading_bot/inv0828_interlisted_probe.py`.
