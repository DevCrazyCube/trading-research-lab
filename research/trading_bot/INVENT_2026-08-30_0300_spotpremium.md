# INVENT 2026-08-30 03:00 CEST — CHUNK B invention tick (durable supervisor)

**Verdict: ONE pre-registered family run, DEAD at the friction floor. 2 formulas charged to the
multiple-testing ledger (F1, F2), held-out never computed. Two further families desk-screened and
pre-refuted by ledger citation (0 charged). T31 verified 7/7 clean. Nothing else touched.**

Pre-registration: `INVENT_2026-08-30_0300_spotpremium_PREREG.md` (sha256 `f87fe7f6…`, pinned before
any number). Harness: `scripts/trading_bot/inv0830_spotpremium.py` (pure python). Results:
`INVENT_2026-08-30_0300_spotpremium.json`. Data: cached IBIT SIP dailies (08-23 exotic cache) +
one bounded Binance fetch (`research/data/inv0830_cache/BTCUSDT_30m.csv`, 46 calls, 45,841 rows, 0 gaps).

## 1. Collector verification (standing duty)
- **T31 Deribit wing quotes: 7/7 clean.** Day 7 landed 2026-08-30 02:17:05 CEST: 1,900 rows, BTC 342/342 +
  ETH 328/328 enriched, 124.4 s. `sha256sum -c T31_DERIBIT_FORWARD.sha256` → OK. Cron `15 2 * * *` present.
  Day-30 gate ≈ 09-23. No fault.
- Window-2: `results_unlocked` **false**, `composition_published` false, no stage in flight, no quarantine.
  DECISIONS.md moved 01:01 today (PAC V2.1 dashboard entry — memecoin); **no U4**, no equities decision.
  T38 stays BLOCKED-on-U4 (attended). Nothing read, nothing run.
- T30 day 7 lands 16:30 today (verify at 18:00 per the 00:00 plan). Basket, t4, convexity pins untouched.

## 2. The family that was run: spot-BTC ETF *common* closing premium vs the 24/7 instant spot tether
**Why admissible:** published synchronous tether (BTC/USD instant at 16:00:00 ET × sponsor-published
coins/share) outside the dead ledger — the 08-23 exotic round traded ETP-vs-ETP, which cancels the premium
all wrappers share against spot, so the common premium was never measured; the hedge leg is a perp (no
borrow wall). **Mechanism:** closing-auction imbalance in IBIT prints a premium/discount vs instant BTC;
fade it next session (09:30 → 16:00 ET, hedged with the perp). **Stated prior:** dead — the C3/C6 lesson
(closing-print signal cannot pay at the next open).

Design window 2024-02-09 → 2025-08-31 (390 signal sessions), gates from the prereg:

| object | n | mean bp | t | NW5 t | sign-flip p | G1 ≥ 9 bp | G2 t ≥ 2.5 | G3 p < .01 | G4 shift | verdict |
|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| **F1** all sessions, next-open hedged | 390 | **+1.54** | 1.91 | 2.16 | 0.026 | ✗ | ✗ | ✗ | ✓ | **DEAD** |
| **F2** \|prem\| > 10 bp only | 152 | **+3.83** | 2.19 | 2.59 | 0.0065 | ✗ | ✗ | ✓ | ✓ | **DEAD** |
| D0 own-print (untradable diagnostic) | 390 | +7.13 | 6.86 | 6.12 | 0.000 | — | — | — | — | bounce, and *still* < floor |
| shifted-5 placebo F1 / F2 | 385 / 152 | +0.51 / +0.19 | 0.62 / 0.21 | | 0.26 / 0.41 | | | | | null behaves |

D1 (object size, design): premium sd **16.9 bp**, mean |prem| 10.6 bp, 39 % of sessions beyond 10 bp, ρ1 = 0.155.

**Reading.** The object is real (a 17 bp-sd closing premium exists) and it does revert — but almost
entirely *overnight*, before any retail fill is possible: of the +7.1 bp that the impossible own-print
fill would collect, only +1.5 bp (all days) / +3.8 bp (large-premium days) survives to the 09:30 open, against
a 9 bp round-trip floor (1 bp IBIT half-spread × 2 + 3.5 bp perp taker × 2). Distance from zero is the
decider: even the untradable D0 sits under the floor, so no execution lever (maker perp, MOC entry) can
rescue it — a MOC entry would have to be placed at 15:50 before the premium exists. Held-out **sealed,
never computed**. This is the programme's thesis again: where the tether is published and synchronous, the
market (here the APs at the NAV strike) prices it inside the spread. Same shape as the bond-ETF siblings
(0.21 bp/day vs 0.6–1.25 bp half-spread) and the C-family.

**Dead-ledger row:** *spot-crypto ETP vs 24/7 instant spot — common closing-premium reversal, next-open
hedged (F1/F2)* — DEAD 2026-08-30, mean +1.5 / +3.8 bp vs 9 bp floor, t 1.9 / 2.2 < 2.5, own-print +7.1 bp
also < floor. Do not re-propose any spot-crypto-ETP-vs-spot object at a 1-session horizon (ETHA/FBTC are
the same object; not run, not charged).

## 3. Desk-screened, pre-refuted by citation (no data read, 0 charged)
| # | family I would have proposed | why not admissible | citation |
|---|---|---|---|
| 2 | **Monthly-pay covered-call ETF ex-distribution gap** (JEPI/QYLD/XYLD; distribution published, ex-open mechanically adjusted) | wrapper variant of the ex-dividend drop-off family, dead with permutation p 0.213 / DSR 0.076; the residual drop-ratio ≠ 1 is the *published* tax-clientele effect, not original; ETF wrapper changes the clientele, not the mechanism | `T7_RESULT.md`; FINDINGS T7 row |
| 3 | **Long spot-BTC ETF / short perp funding carry** (no borrow wall, funding published every 8 h) | carry is dead 4 ways; the perp-funding window was closed as a category 08-25; the ETF leg only adds a 0.25 %/yr fee and the equity-market half-spread to a dead carry | `FUNDING_CARRY_VALIDATION.md`, `LEVERAGED_FUNDING_CARRY.md`, `INVENT_0825_MASTER.md` |

Also checked and not proposed: dual-class RV (alive-but-never-enters survivor category, not fresh),
merger-arb deal spread (T11, tail-killed), index reconstitution flow (INVENT_0822 forcedflow NOISE), ETN
indicative value (no free feed), iShares dated-holdings NAV route (`asOfDate` already probed — Akamai wall,
INVENT_0823_bondrv).

## 4. Process notes
- Regime unchanged: this was a 2-formula admissibility-screened test, not a sweep; the free-data sweep
  category stays CLOSED. The 00:00 STRATEGIST expected an abstention here; running one pre-registered
  cheap test that *closes* a not-yet-listed family is the same spirit (a durable "do not re-propose" row).
- Multiple-testing ledger: **+2** (F1, F2). D0/D1 are diagnostics, disclosed above.
- New cached free data: Binance BTCUSDT 30m 2024-01-10 → 2026-08-22 (no key, reusable).

## 5. Untouched
BASKET1 frozen `d53b4fe4…` untouched; t4 path untouched; window-2 untouched; no commit, no orders, no spend,
no wallet. Agenda: no task promoted/killed/re-ordered (open work = T38 only).
