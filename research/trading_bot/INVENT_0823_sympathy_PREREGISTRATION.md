# PRE-REGISTRATION — INVENT_0823 `sympathy`: intra-group lead-lag / sympathy

**Written and hashed BEFORE `--stage design` produced a single number.**
Date 2026-08-23. Research only; cached free data; no orders, no money.

---

## 1. The claim under test

When a **group leader** makes a sharp move, do **close peers inside the same tight group**
systematically over- or under-react over the *next* interval, by enough to pay for a realistic
(strictly later) fill?

This is **not** the dead cross-asset lead-lag (crypto→equity, futures→cash) and **not** the
every-bar RV/pair mean-reversion family already killed in `DEEPMINE_etf_structural_rv`
(51 formulas, 0/51 net-positive) and `rv_design_daily` (98 formulas). Those were continuous,
high-turnover spread trades. This family is **event-conditioned and low-turnover**: it only
trades after a leader shock, and each trade is a directional or single-hedge peer position held
for minutes-to-hours.

Same-index **sibling** pairs are excluded from every peer set (SPY/IVV/VOO/SPLG, GLD/IAU/GLDM,
SLV/SIVR, GOOG/GOOGL, QQQ/QQQM, IWM/VTWO, SMH/SOXX, IBB/XBI, XLF/VFH, XLK/VGT, XLE/VDE …):
at most **one ETF per group** is admitted as a peer. This is deliberate — ETF-sibling RV was
exposed as a 15:45 shared-price bounce artefact and must not be re-derived under a new name.

## 2. Data

`research/data/rv_cache/panel_rv.npz` — 132 US symbols, 5-minute bars, 1 410 sessions,
2021-01-04 → 2026-08-14, fields `close/open/vwap/dvol`. Costs from
`research/data/rv_cache/spread_proxy.json` (`headline_half_bp`, provenance
TICK_FLOOR_TIMES_ADVERSITY, floor 1.0 bp) plus **0.15 bp per unit of turnover** for SEC §31 +
FINRA TAF, the same charge `deepmine_etfstruct.py` uses. A round trip on one leg therefore costs
`2 × (headline_half_bp + 0.15)` bp of that leg's notional. Hedged variants additionally pay
`|β| × 2 × (half_bp_leader + 0.15)`.

**Windows.** Design **2021-01-04 → 2024-12-31** (1 005 sessions, 3.99 y). Held out
**2025-01-02 → 2026-08-14** (405 sessions, 1.61 y). The held-out window is not read until the
shortlist file is on disk.

## 3. Groups (fixed here, ex ante; leader = highest median 5-min $-volume single stock)

| id | leader | peers |
|---|---|---|
| SEMI | NVDA | AMD, AVGO, INTC, SMH |
| MEGATECH | AAPL | MSFT, GOOGL, META, AMZN, ADBE, CRM, ORCL, CSCO, NFLX, XLK |
| BANK | JPM | BAC, XLF, KRE |
| ENERGY | XOM | CVX, XLE |
| HEALTH | LLY | UNH, JNJ, MRK, ABBV, XLV, IBB |
| STAPLE | WMT | COST, PG, KO, PEP, XLP |
| DISCR | HD | AMZN, TSLA, XLY |
| GOLD | GDX | GDXJ, GLD |
| PAYMENT | V | MA |
| INDEX | (AAPL, MSFT, NVDA, AMZN, META, each separately) | QQQ |

Membership overlaps between groups (AMZN is in MEGATECH and DISCR). That makes formulas
correlated; the size-matched placebo null below is what handles it.

## 4. Timing rule — the anti-artefact core

The leader's move is measured **to the close of bar b**. The peer position is opened at the close
of bar **b + 1** — a full 5-minute bar later, so signal and fill are *never the same print*, and
the whole of the peer's immediate reaction bar is forfeited. Exit at the close of bar
`min(b + 1 + h, 77)`; intraday formulas never hold overnight. Gap formulas measure the leader's
gap to the 09:35 close and enter at the 09:40 close.

Entry lag is a free parameter of the evaluator, so the **one-bar-gap re-entry test** is run for
every formula: lag 0 (the shared print — reported as a DIAGNOSTIC ONLY, never as a claim), and
lags 1 (the design), 2, 3, 6. A formula whose edge lives only at lag 0, or that collapses from
lag 1 to lag 2, is bounce, not sympathy.

## 5. The 26 formulas (frozen here)

Claims, each a structurally different object; `k` = leader-shock threshold in trailing σ,
`h` = holding bars (1 bar = 5 min).

1. `C1a INTRA_CATCHUP_k3_h3` — peer under-reacts to leader shock; deficit `β·r_L − r_p`; trade toward the deficit.
2. `C1b INTRA_CATCHUP_k3_h6`
3. `C1c INTRA_CATCHUP_k4_h6`
4. `C1d INTRA_CATCHUP_k3_h3_HEDGED` — same, peer hedged with `β` of the leader.
5. `C2a INTRA_FADE_k3_h3` — peer *over*-reacts; trade against the deficit.
6. `C2b INTRA_FADE_k3_h12`
7. `C3a HEAVY_TO_INDEX_k3_h6` — index heavyweight shock → QQQ under-reacts by its weight.
8. `C3b HEAVY_TO_INDEX_k3_h6_SPYHEDGE`
9. `C4a BREADTH_LAGGARD_k2_h6` — no single leader: group *consensus* (median) move, trade the laggard.
10. `C4b BREADTH_LAGGARD_k3_h12`
11. `C5a GAP_CATCHUP_close` — leader overnight gap → peer's residual gap deficit, held to the close.
12. `C5b GAP_CATCHUP_h12`
13. `C6a GAP_FADE_close`
14. `C6b GAP_FADE_h12`
15. `C7a LATEMOVE_NEXTOPEN_CATCHUP` — leader's last-30-min move → peer's *next* morning gap.
16. `C7b LATEMOVE_NEXTOPEN_FADE`
17. `C8a VOLSHOCK_CATCHUP_h6` — leader *volume* shock (not return), peer flow sympathy.
18. `C8b VOLSHOCK_FADE_h6`
19. `C9a ETF_LEADS_STOCK_CATCHUP_h6` — direction test: the sector ETF is the leader, its members the peers.
20. `C9b ETF_LEADS_STOCK_FADE_h6`
21. `C10a INTRA_CATCHUP_DOWNONLY_k3_h6` — asymmetry: leader down-shocks only.
22. `C10b INTRA_CATCHUP_UPONLY_k3_h6`
23. `C11a CUM30_CATCHUP_k3_h6` — leader's cumulative 30-minute move rather than a single bar.
24. `C11b CUM30_FADE_k3_h6`
25. `C12a DISPERSION_NEUTRAL_k3_h6` — after a shock, long the group's biggest laggard vs short its biggest leader, dollar-neutral inside the group.
26. `C12b DISPERSION_NEUTRAL_k3_h39`

`N = 26`.

## 6. Accounting

One unit of capital per **event**, split equally across that event's legs; the day's PnL is the
mean over that day's events; days with no event contribute exactly 0.0. Sharpe is annualised over
**all calendar sessions in the window**, zero days included, so a rare-event formula cannot buy a
Sharpe with scarcity. `t = Sharpe × √years`.

## 7. Nulls — both are size-matched, and the analytic one is reported as the weaker of the two

* **Analytic**: `√(2 ln 26) = 2.55` SE; 1 SE of an annualised Sharpe over 3.99 y is `1/√3.99 =
  0.501` → naive bar **1.28** in Sharpe units. Known to understate by ~2× on overlapping books.
* **PLACEBO-A (day-shift)**: keep every event and every sign, but read the trade's prices from a
  day `d + δ`, `δ` drawn from `±[5, 60]` sessions. Identical trade count, identical slot and
  size distribution, sympathy link destroyed. 400 draws.
* **PLACEBO-B (event sign flip)**: keep every trade, multiply each *event's whole sign vector* by
  a random ±1. 400 draws.

For each draw the **max over all 26 formulas** is taken, so the reported bar is the max-statistic
bar. The gate is the **p95 of the max** under the stricter (higher) of A and B.

## 8. Gates — a formula reaches the held-out window only if ALL hold

1. design **gross** Sharpe > placebo p95-of-max **and** > 1.28 (analytic);
2. design **net** Sharpe > 0;
3. ≥ 400 leg-trades and ≥ 150 active sessions in the design window;
4. lag-robustness: net Sharpe at entry lag 2 ≥ 0.5 × net Sharpe at lag 1 (bounce test);
5. for hedged/neutral formulas, ρ1 of the first difference of the traded spread > −0.35.

The top 3 by design **net** Sharpe among the passers are frozen to
`INVENT_0823_sympathy_SHORTLIST.json` and only then is the held-out window read. If **none**
pass, the top 2 by design net Sharpe are still run out of sample and reported explicitly as
**BELOW THE NOISE BAR** — that is a near-miss report, not a promotion.

## 9. What counts as REAL

Gross beats **both** nulls, held-out **net** Sharpe positive, ρ1 clean, and the fill is a strictly
later print. Anything else is reported as an honest zero. A high gross Sharpe that lives inside
the half-spread is evidence *against*, not for.
