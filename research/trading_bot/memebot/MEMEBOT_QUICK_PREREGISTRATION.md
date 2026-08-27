# MEMEBOT_QUICK — pre-registration (a parallel exit-speed variant of MEMEBOT_FAST)

**Instrument:** `MEMEBOT_QUICK` — a fast, light, reactive **PAPER** memecoin bot. A **parallel variant**
of `MEMEBOT1`/`MEMEBOT_FAST`, standing beside them under ITERATION_PROTOCOL §4b (multiple forward tests
at once: separate ledgers, separate register entries, separate state; **every** parallel variant counts
as a trial for the family's DSR/multiple-testing bar, forever).

**Freeze intent:** the rules below are frozen BEFORE this variant's first forward paper entry. The
loader (`frozen.py`) recomputes the SHA-256 of *this file* and refuses to run if it moved. An
improvement is a **new** frozen instrument, never an edit to a running one.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid account. Reads only FREE, KEYLESS public data. Real trading
is a **separate, owner-gated wallet decision**, not reachable from here.

---

## Why this variant exists (the one thing that differs)

`MEMEBOT_FAST` froze a **25-minute** horizon. Its first verdict (n = 30 resolved PASS trades) exposed a
clean, measured time-structure in the outcomes — the motivation for this variant, stated here honestly
so it is on the record and NOT hidden as a post-hoc tune:

- **Every winner resolved fast.** The 9 `TARGET` hits had a median hold of **10.6 min** and a **maximum
  of 21.4 min** — no winner needed more than ~21 minutes.
- **Every catastrophic loss came late.** All 10 `UNEXITABLE_TIMEOUT` losses (each booked at the −25%
  stop floor, the honest can't-actually-sell convention) landed at the **25-minute horizon or later**
  (median 27.6 min). On-chain verification of those coins days later confirmed they were REAL deaths —
  liquidity drained to ~$0, prices −64% to −99.99% — not a data-coverage artefact.

So on this instrument, a position that has not won by ~21 minutes is not waiting to win; it is riding
into the zone where the coin dies and becomes unexitable. `MEMEBOT_QUICK` tests the **honest
counter-hypothesis that being FASTER out — a 15-minute hard horizon — books the non-winners while the
pool still has exit liquidity, before the drain completes**, converting some late unexitable −1.12R
forfeits into smaller, actually-exitable losses, at the cost of clipping the tail of slow winners.

**15 minutes is chosen a-priori, not fit to the sample.** It is a round "fast scalp" number set
*inside* the observed winner-resolution envelope, deliberately NOT the sample's 21.4-min maximum-winner
time (which would be curve-fitting to this exact 9-trade draw). 15 min will clip any winner that needs
15–21 min — that cost is the whole point: if being aggressively fast nets better forward *despite*
losing those slow winners, the owner's speed thesis holds; if it nets worse, it is falsified. Only
fresh post-freeze data decides.

**This is a variant, not a hedge.** Standing `MEMEBOT_QUICK` beside its siblings and later reporting
only the better one would be a multi-trial search reported as one test (ITERATION_PROTOCOL §8.6). It is
declared here; it counts as a trial for the family; the honest comparison is *which EXIT timescale is
better forward*, on the **same entries and same screen**, judged only on data that printed after this
freeze.

**Everything identical to MEMEBOT_FAST except the horizon** (§3): the free data feed, the deterministic
screen, fixed 2% sizing, the −25% stop / +50% target, the 1.5%/side toll, the dead-coin early exit,
freeze-before-outcome, the control null, the honest scoring, and the N_min = 30 kill switch are **the
same rules** as `MEMEBOT_FAST_PREREGISTRATION.md`. Read that document for the full frame; only the
horizon changes (25 min → 15 min).

---

## 1. The eyes (free, keyless data feed) — FROZEN, identical to MEMEBOT_FAST

GeckoTerminal public API (`/networks/solana/new_pools`, `/networks/solana/pools/{address}`) + PumpPortal
free keyless read-only data websocket (`subscribeNewToken`, enriched through GeckoTerminal) + DexScreener
cross-check. Fields the free feed does not expose are **never fabricated**.

## 2. The screen (deterministic, no LLM per coin) — FROZEN, identical to MEMEBOT_FAST

| # | rule | threshold |
|---|------|-----------|
| 1 | `REJECT_MIN_FDV` | FDV < **$7,000** |
| 2 | `REJECT_MIN_LIQUIDITY` | reserve < **$3,000** |
| 3 | `REJECT_DEADNESS_PROXY` | unique buyers < **10** |
| 4 | `REJECT_BUNDLE_PROXY` | buys/buyer > **4.0** |
| 5 | `REJECT_HONEYPOT_PROXY` | buys ≥ **15** and sellers = **0** |
| 6 | `REJECT_STALE` | pool age > **30 min** |
| — | `REJECT_NO_FDV` / `REJECT_NO_RESERVE` | field absent → refuse, never guess |

## 3. The bot (paper execution) — FROZEN — **the ONLY difference from MEMEBOT_FAST is the horizon**

Identical to MEMEBOT_FAST: 10.0 paper-SOL bankroll · **fixed 2%** per entry (never a martingale) · long
only · stop **−25%** / target **+50%** (asymmetric, defined risk) · **1.5%/side (≈3% round-trip) toll**
so expectancy is NET · every entry sha256+UTC **frozen before outcome** · `R = (exit/entry − 1 −
2·toll) / stop_frac`. Caps: ≤ **6** open, ≤ **4** new PASS/scan, ≤ **3** control/scan. The **dead-coin
early exit** (`DEAD_EXIT`: held ≥ 5 min, ≤ 1 recent trade, price within ±8% of entry, never kills on
absence) is **unchanged**.

**What differs — the horizon only:**

- **SHORTER hard horizon: 15 minutes** (not 25). At the horizon a still-open position resolves at the
  live mark (`HORIZON_MARK`), or, if the feed shows no live price past horizon, as an
  `UNEXITABLE_TIMEOUT` loss (exit at the stop floor) — same conservative discrete-poll convention as
  MEMEBOT_FAST. Nothing else changes.

## 4. Honest scoring + the control null — FROZEN, identical to MEMEBOT_FAST

`EXPECTANCY = winrate·avgWinR − lossrate·avgLossR` per trade (NET of toll). Control null = the SAME
sizing/stop/target/**exit (15-min horizon)** applied to a deterministically-sampled set of screen-**REJECT**
coins. `expectancy(PASS) − expectancy(control)` is the forward test of whether the screen adds value
under this faster exit. Everything before the minimum sits fenced in `inputs_that_are_not_results`.

## 5. Kill switch — FROZEN, identical to MEMEBOT_FAST

**N_min = 30** resolved PASS trades before any expectancy verdict. **HALT** if, after n ≥ N_min,
`mean_R + 1.645·SE < 0`. Below N_min: **NO VERDICT.** Behaviour is not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, no paid accounts, free data only.
The forward log (`MEMEBOT_QUICK_PREREGISTRATION_LOG.jsonl` + `MEMEBOT_QUICK_RESOLUTION_LOG.jsonl`) is the
only arbiter. The honest prior is ~0 or negative; this variant exists to test, forward and at $0,
whether being FASTER out beats the 25-minute base — not to chase "double every hour", which is the
farmer's bait and is encoded as a goal nowhere.*
