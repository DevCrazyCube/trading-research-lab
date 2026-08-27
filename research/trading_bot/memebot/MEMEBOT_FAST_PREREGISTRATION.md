# MEMEBOT_FAST — pre-registration (a parallel exit-timescale variant of MEMEBOT1)

**Instrument:** `MEMEBOT_FAST` — a fast, light, reactive **PAPER** memecoin bot. A **parallel variant**
of `MEMEBOT1`, standing beside it under ITERATION_PROTOCOL §4b (two forward tests at once: separate
ledgers, separate register entries, separate state; **both** count as trials for the family's DSR,
forever).

**Freeze intent:** the rules below are frozen BEFORE this variant's first forward paper entry. The
loader (`frozen.py`) recomputes the SHA-256 of *this file* and refuses to run if it moved. An
improvement is a **new** frozen instrument, never an edit to this one.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid account. Reads only FREE, KEYLESS public data. Real trading
is a **separate, owner-gated wallet decision**, not reachable from here.

---

## Why this variant exists (the one thing that differs)

`MEMEBOT1` froze a **180-minute** hold horizon. On the memecoin timescale that is **absurdly long**: a
pump.fun launch typically lives, moons, or dies inside the first minutes, and a 3-hour horizon means a
frozen corpse ties up a slot for hours while its "mark" is a stale price nobody will trade at.
`MEMEBOT_FAST` tests the **honest counter-hypothesis** that a memecoin-appropriate exit — a short
horizon plus an immediate exit from dead coins — resolves positions on the timescale the instrument
actually moves on, without changing which coins are entered or how they are sized/stopped.

**This is a variant, not a hedge.** Standing `MEMEBOT_FAST` beside `MEMEBOT1` and later reporting only
the better one would be a two-trial search reported as one test (ITERATION_PROTOCOL §8.6). Both are
declared here; both count as trials; the honest comparison is *which EXIT rule is better forward*, on
the **same entries**, judged only on data that printed after this freeze.

**Everything identical to MEMEBOT1 except the exit** (§3): the free data feed, the deterministic
screen, fixed 2% sizing, the −25% stop / +50% target, the 1.5%/side toll, freeze-before-outcome, the
control null, the honest scoring, and the N_min = 30 kill switch are **the same rules** as
`MEMEBOT_PREREGISTRATION.md`. Read that document for the full frame; only the exit/timescale is restated
below.

---

## 1. The eyes (free, keyless data feed) — FROZEN

Identical to MEMEBOT1, plus one **discovery** source added the same day both variants run forward:

- **Primary discovery + price refresh:** GeckoTerminal public API (no key, ~30 calls/min).
  `GET /networks/solana/new_pools` and `GET /networks/solana/pools/{address}`.
- **Realtime discovery (added 2026-08-25):** **PumpPortal** free, keyless, read-only data websocket
  `wss://pumpportal.fun/api/data` (`subscribeNewToken`). It **pushes** a `create` event the instant a
  new pump.fun token is minted (seconds vs the ~90 s GeckoTerminal poll). The push event does **not**
  carry the unique-buyer/buys/sells counts the screen needs — those exist only once the token trades —
  so a pushed mint is **enriched** through the already-allowlisted GeckoTerminal `tokens/{mint}/pools`
  endpoint into the SAME snapshot the screen consumes. PumpPortal opens **only** the read-only data
  websocket; every trade/Lightning REST path (`pumpportal.fun/api/trade*`) stays FORBIDDEN in
  `net.py`. No order/wallet capability is added — it is a data feed only.
- **Secondary (cross-check only):** DexScreener (`api.dexscreener.com`), keyless.
- Fields the free feed does not expose are **never fabricated** — the screen adapts to the exposed proxy.

## 2. The screen (deterministic, no LLM per coin) — FROZEN, identical to MEMEBOT1

| # | rule | threshold |
|---|------|-----------|
| 1 | `REJECT_MIN_FDV` | FDV < **$7,000** |
| 2 | `REJECT_MIN_LIQUIDITY` | reserve < **$3,000** |
| 3 | `REJECT_DEADNESS_PROXY` | unique buyers < **10** |
| 4 | `REJECT_BUNDLE_PROXY` | buys/buyer > **4.0** |
| 5 | `REJECT_HONEYPOT_PROXY` | buys ≥ **15** and sellers = **0** |
| 6 | `REJECT_STALE` | pool age > **30 min** |
| — | `REJECT_NO_FDV` / `REJECT_NO_RESERVE` | field absent → refuse, never guess |

## 3. The bot (paper execution) — FROZEN — **the ONLY difference from MEMEBOT1 is here**

Identical to MEMEBOT1: 10.0 paper-SOL bankroll · **fixed 2%** per entry (never a martingale) · long
only · stop **−25%** / target **+50%** (asymmetric, defined risk) · **1.5%/side (≈3% round-trip) toll**
so expectancy is NET · every entry sha256+UTC **frozen before outcome** · `R = (exit/entry − 1 −
2·toll) / stop_frac`. Caps: ≤ **6** open, ≤ **4** new PASS/scan, ≤ **3** control/scan.

**What differs — the exit/timescale:**

- **SHORT horizon: 25 minutes** (not 180). At the horizon a still-open position resolves at the live
  mark (`HORIZON_MARK`), or, if the feed shows no live price past horizon, as an `UNEXITABLE_TIMEOUT`
  loss (exit at the stop floor) — same conservative discrete-poll convention as MEMEBOT1.
- **DEAD-COIN EARLY EXIT (`DEAD_EXIT`).** If a position is a flat corpse, exit **immediately at the
  current mark** (net toll) rather than holding it for the rest of the horizon. Fires only when **all**
  of the following hold, checked *after* the stop and target (a coin hitting stop/target is not "dead"):
  - held ≥ **5 minutes** (`after_minutes`), and
  - the feed's most-recent window shows **≤ 1** combined new trades (`max_recent_trades`, buys+sells) —
    i.e. ~zero fresh activity, no exit liquidity forming, and
  - price is within **±8%** of entry (`flat_band`) — it has not meaningfully moved.
  - **Never kills on absence:** if the feed cannot report buys/sells, deadness is *not* confirmed and
    the position is held. We exit corpses we can see, never ones we merely cannot measure.

**Rationale for the dead-exit thresholds (a-priori, NOT tuned on observed P&L).** 5 minutes is one full
GeckoTerminal `m5` window — the shortest horizon over which "no new trades" is a measurement rather than
polling noise. `≤ 1` trade over that window is the operational definition of "nobody is trading this."
`±8%` marks "has not moved" on an instrument whose live launches routinely swing tens of percent. These
are frozen here, before any `MEMEBOT_FAST` datum exists; they are not to be re-fit on the forward log.

## 4. Honest scoring + the control null — FROZEN, identical to MEMEBOT1

`EXPECTANCY = winrate·avgWinR − lossrate·avgLossR` per trade (NET of toll). Control null = the SAME
sizing/stop/target/**exit** applied to a deterministically-sampled set of screen-**REJECT** coins.
`expectancy(PASS) − expectancy(control)` is the forward test of whether the screen adds value under this
exit rule. Everything before the minimum sits fenced in `inputs_that_are_not_results`.

## 5. Kill switch — FROZEN, identical to MEMEBOT1

**N_min = 30** resolved PASS trades before any expectancy verdict. **HALT** if, after n ≥ N_min,
`mean_R + 1.645·SE < 0`. Below N_min: **NO VERDICT.** Behaviour is not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, no paid accounts, free data only.
The forward log (`MEMEBOT_FAST_PREREGISTRATION_LOG.jsonl` + `MEMEBOT_FAST_RESOLUTION_LOG.jsonl`) is the
only arbiter. The honest prior is ~0 or negative; this variant exists to test, forward and at $0,
whether a memecoin-appropriate EXIT beats the 180-minute base — not to chase "double every hour", which
is the farmer's bait and is encoded as a goal nowhere.*
