# INVENT_0823 · RATES / TREASURY TERM-STRUCTURE — PRE-REGISTRATION

**Written before the held-out window was read.** `--stage design` constructs its `Panel` with
`end = 2020-12-31`, so held-out rows are not merely unscored, they are **unreachable from the
design process** — the loader never sees them.

**Harness:** `scripts/trading_bot/invent0823_rates.py`
**Report:** `scripts/trading_bot/invent0823_rates_report.py`
**Data:** `research/data/ratescredit_cache/{etf_daily,fred_daily}.json` (cached, free; Yahoo
adjusted closes = total return, FRED H.15 / TIPS / breakeven series). No network.

## Windows

| | |
|---|---|
| design | 2010-08-06 → 2020-12-31 (~2,620 trading days) |
| **held out** | **2021-01-01 → 2026-08-18 (~1,415 days, 5.6 y)** |

The held-out block is the entire 2022–2024 hiking cycle, the deepest curve inversion since 1981,
and the 2024–2026 re-steepening. For a *rates* theme this is the most hostile out-of-sample
window available: the design decade is ZIRP plus one shallow hiking cycle, the held-out block is
a different rate regime entirely. A curve signal that is really a 2010s duration-bull artifact
cannot survive it.

## N and the bar

**N = 33 pre-registered formulas**, seven families (A ladder-residual ×8, B sibling ×9,
C breakeven-gap ×6, D roll-down ×4, F butterfly-gap ×2, G real-curve ladder ×2, E decoy ×2).
No formula was added after any number was read.

* analytic bar, two-sided, `sqrt(2 ln 2N)` — reported
* **size-matched placebo**, 400 draws, same 33 books, signal destroyed and nothing else:
  * **XS books → per-day permutation of the signal across panel slots.** This is the
    ADV-slot-permutation null, NOT rotate-the-returns (that null is broken — it injects a
    directional leg). Duration weights stay attached to their slots, so the placebo book has
    the same gross, the same turnover, the same cost and the same return covariance; only the
    assignment of signal to instrument is destroyed.
  * **TS books → circular shift of the signal series** by a uniform offset in [63, T−63].
* **bar used = max(analytic, placebo p95)**.

## Gates, in order

1. **ρ1(Δspread) BOUNCE GATE — runs FIRST, before any Sharpe is consulted.** Each book's spread
   is a cumulative residual return, so Δ(spread) *is* the daily residual return and the gate is
   ρ1 of that series on the **design window only**. `ρ1 < −0.35` ⇒ the "mean reversion" is
   measurement-error bounce ⇒ **dead on arrival, regardless of Sharpe**. Inside a tethered
   family a high short-horizon gross Sharpe is **evidence against**, not for.
2. **GROSS bar.** Design gross |t| must exceed `max(sqrt(2 ln 2N), placebo p95)`. Cost fixes for
   a sub-bar gross are not attempted — that is the EXECUTION_COST_WALL lesson.
3. **Lag-kill.** Every formula is scored at lag 1 (base), lag 2 (kill), and lag 0 (diagnostic
   only). A signal that is large at lag 0 and gone at lag 1 was reading the bar it trades.
4. **Held-out.** Only formulas passing 1+2 earn a held-out look. Promotion requires held-out
   **net** positive as well.
5. **Executable.** Every leg is a US Treasury ETF; every short leg is easy-to-borrow, and
   borrow is charged at the 33 bp/yr ETB floor anyway. Half-spread = max(dollar-volume tier,
   half-a-penny tick floor), charged on both legs, plus 0.15 bp/turnover regulatory.
   Break-even half-spread is reported next to every Sharpe.

## What would make this theme REAL

A formula that (a) passes ρ1, (b) clears the gross bar on design, (c) survives lag 2, (d) is
net-positive out of sample across the 2021–2026 regime change, and (e) has a break-even
half-spread comfortably above the charged one. Anything less is reported as noise.

## What would make it NOISE — stated in advance

* the decoys (`E1_decoy_BIL_vs_publishedbill`, `E2_decoy_TLH_follows_TLT`) scoring at or above
  the real families on gross — that is the signature of a complex whose gross Sharpe is
  manufactured by tick bounce;
* break-even half-spreads below the charged half-spread across the board;
* survivors that vanish at lag 2.

## Explicitly NOT done

No regime conditioning or macro gating of any kind. No signal switches on VIX, NFCI, the level
of rates, or a Fed-cycle state. That family is proven noise and harmful in this programme, and
excluding it is a pre-registration commitment, not a post-hoc choice.
