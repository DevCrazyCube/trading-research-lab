# MEMEBOT_RUNNER — pre-registration (a parallel take-profit variant of MEMEBOT1/MEMEBOT_FAST)

**Instrument:** `MEMEBOT_RUNNER` — a fast, light, reactive **PAPER** memecoin bot. A **parallel variant**
standing beside `MEMEBOT1` and `MEMEBOT_FAST` under ITERATION_PROTOCOL §4b (multiple forward tests at
once: separate ledgers, separate register entries, separate state; **all** count as trials for the
family's DSR, forever).

**Freeze intent:** the rules below are frozen BEFORE this variant's first forward paper entry. The
loader (`frozen.py`) recomputes the SHA-256 of *this file* and refuses to run if it moved. An
improvement is a **new** frozen instrument, never an edit to a running one — so `MEMEBOT1` and
`MEMEBOT_FAST` are NOT touched; `MEMEBOT_RUNNER` is a fresh object with an empty ledger.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid account. Reads only FREE, KEYLESS public data. Real trading
is a **separate, owner-gated wallet decision**, not reachable from here.

---

## Why this variant exists (the one thing that differs)

Both running bots take profit at a **fixed +50%** (`target_frac = 0.5`). The 2026-08-26 evolutionary
evaluation of the exit surface found that the survivors that scored best by *t* did **not** cap the
winner at +50%: they let winners **run to a high target** and paired it with the dead-coin early exit
to cut the losers fast. The best genome by *t* was **`g73c7da`** — 106-minute horizon, ~22% stop,
**~111% target**, dead-exit on — at **t = 1.94**.

The mechanical reason a fixed +50% cap can hurt on this instrument: a memecoin's payoff is a **fat
right tail**. A rule that sells the rare multi-bagger at +50% clips exactly the part of the
distribution that pays for all the losers. `MEMEBOT_RUNNER` tests the **honest counter-hypothesis**:

> On the SAME entries and the SAME dead-coin early exit, does a **high +110% take-profit** (letting the
> fat tail run) beat the **fixed +50% cap** forward, net of the ~3% toll?

**This is a variant, not a hedge, and not a proven finding.** Standing `MEMEBOT_RUNNER` beside the other
two and later reporting only the best one would be a multi-trial search reported as one test
(ITERATION_PROTOCOL §8.6). It is declared here; it counts as a trial; the honest comparison is *which
EXIT/take-profit rule is better forward*, on paired entries, judged only on data that printed after this
freeze. **It is a LEAN, not a result:** g73c7da's **t = 1.94 sits BELOW the family's ~2.71 noise bar**,
so the in-sample evo score is suggestive, not significant. The **honest prior is ~0 or negative**;
forward paper data is the only arbiter.

**Everything identical to MEMEBOT_FAST except the take-profit / stop / horizon** (§3): the free data
feed, the deterministic screen, fixed 2% sizing, the 1.5%/side toll, freeze-before-outcome, the control
null, the honest scoring, the N_min = 30 kill switch, and the **dead-coin early exit** are the **same
rules** as `MEMEBOT_FAST_PREREGISTRATION.md`. Read that document (and the base
`MEMEBOT_PREREGISTRATION.md`) for the full frame; only the target/stop/horizon are restated below.

---

## 1. The eyes (free, keyless data feed) — FROZEN, identical to MEMEBOT_FAST

Identical to `MEMEBOT_FAST`: GeckoTerminal public API (no key) for discovery + price refresh, the
keyless read-only **PumpPortal** realtime new-token data websocket for faster discovery (enriched
through the already-allowlisted GeckoTerminal endpoint into the same snapshot the screen consumes), and
DexScreener as a keyless cross-check. Every trade/Lightning/RPC/wallet host stays FORBIDDEN in `net.py`.
No order/wallet capability is added — it is a data feed only. Fields the free feed does not expose are
**never fabricated**.

## 2. The screen (deterministic, no LLM per coin) — FROZEN, identical to MEMEBOT_FAST/MEMEBOT1

| # | rule | threshold |
|---|------|-----------|
| 1 | `REJECT_MIN_FDV` | FDV < **$7,000** |
| 2 | `REJECT_MIN_LIQUIDITY` | reserve < **$3,000** |
| 3 | `REJECT_DEADNESS_PROXY` | unique buyers < **10** |
| 4 | `REJECT_BUNDLE_PROXY` | buys/buyer > **4.0** |
| 5 | `REJECT_HONEYPOT_PROXY` | buys ≥ **15** and sellers = **0** |
| 6 | `REJECT_STALE` | pool age > **30 min** |
| — | `REJECT_NO_FDV` / `REJECT_NO_RESERVE` | field absent → refuse, never guess |

## 3. The bot (paper execution) — FROZEN — **the ONLY difference is the take-profit / stop / horizon**

Identical to MEMEBOT_FAST/MEMEBOT1: 10.0 paper-SOL bankroll · **fixed 2%** per entry (never a
martingale) · long only · **1.5%/side (≈3% round-trip) toll** so expectancy is NET · every entry
sha256+UTC **frozen before outcome** · `R = (exit/entry − 1 − 2·toll) / stop_frac`. Caps: ≤ **6** open,
≤ **4** new PASS/scan, ≤ **3** control/scan.

**What differs — the take-profit, stop, and horizon (from the g73c7da evo survivor):**

- **HIGH take-profit: target `target_frac = 1.10` (+110%), NOT the fixed +50% cap.** This is the whole
  point: let the rare winner run into the fat right tail instead of clipping it at +50%. A resolved
  `TARGET` therefore pays far more than the +1.88R of the 50%-cap bots — with this stop it is
  `R = (1.10 − 2·0.015) / 0.22 ≈ +4.86R`. The reward:risk on price is ~5:1 (before toll), by design.
- **Stop `stop_frac = 0.22` (−22%).** A hair tighter than the −25% base, per the g73c7da genome; the
  risk unit is `size · stop_frac`.
- **Horizon `horizon_minutes = 90`** (the g73c7da genome ran ~106 min; 90 is the frozen value used
  here — a memecoin-appropriate hold, far shorter than the 180-min base). At the horizon a still-open
  position resolves at the live mark (`HORIZON_MARK`), or as an `UNEXITABLE_TIMEOUT` loss (exit at the
  stop floor) if the feed shows no live price past horizon — same conservative discrete-poll convention.
- **DEAD-COIN EARLY EXIT (`DEAD_EXIT`) — KEPT, identical to MEMEBOT_FAST.** Checked *after* stop/target,
  fires only when ALL hold: held ≥ **5 minutes** (`after_minutes`), the feed's recent window shows
  **≤ 1** combined new trades (`max_recent_trades`), and price is within **±8%** of entry (`flat_band`).
  **Never kills on absence:** if the feed cannot report buys/sells, deadness is not confirmed and the
  position is held. A high target only pays if the losers are cut cheaply — the dead-exit is what makes
  letting winners run affordable.

**Rationale (a-priori, NOT re-tuned on any MEMEBOT_RUNNER datum).** The +110% target, −22% stop and
90-min horizon come from the in-sample evo survivor g73c7da (best by *t*, 2026-08-26); the dead-exit
thresholds (5 min / ≤1 trade / ±8%) are inherited unchanged from MEMEBOT_FAST. They are frozen here,
before any `MEMEBOT_RUNNER` datum exists, and are not to be re-fit on the forward log. That the genome
was picked from a search is exactly why this variant is a **lean**: its t = 1.94 is below the noise bar,
and only paired forward data resolves whether the high target beats the +50% cap.

## 4. Honest scoring + the control null — FROZEN, identical to MEMEBOT_FAST/MEMEBOT1

`EXPECTANCY = winrate·avgWinR − lossrate·avgLossR` per trade (NET of toll). Control null = the SAME
sizing/stop/target/**exit** applied to a deterministically-sampled set of screen-**REJECT** coins.
`expectancy(PASS) − expectancy(control)` is the forward test of whether the screen adds value under this
take-profit rule. Everything before the minimum sits fenced in `inputs_that_are_not_results`.

## 5. Kill switch — FROZEN, identical to MEMEBOT_FAST/MEMEBOT1

**N_min = 30** resolved PASS trades before any expectancy verdict. **HALT** if, after n ≥ N_min,
`mean_R + 1.645·SE < 0` (forward expectancy significantly negative). Below N_min: **NO VERDICT.**
Behaviour is not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, no paid accounts, free data only.
The forward log (`MEMEBOT_RUNNER_PREREGISTRATION_LOG.jsonl` + `MEMEBOT_RUNNER_RESOLUTION_LOG.jsonl`) is
the only arbiter, and it starts EMPTY. The honest prior is ~0 or negative; this variant exists to test,
forward and at $0, whether letting the fat right tail run (a +110% take-profit) beats the fixed +50% cap
of the running bots — a lean drawn from an in-sample evo survivor (g73c7da, t = 1.94 < the ~2.71 noise
bar), never a proven edge, and never "double every hour", which is the farmer's bait and is encoded as a
goal nowhere.*
