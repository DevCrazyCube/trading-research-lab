# MEMEBOT_G73 — pre-registration (the best evo genome g73c7da, frozen as an instrument, MINUS flow-exit)

**Instrument:** `MEMEBOT_G73` — a fast, light, reactive **PAPER** memecoin bot. A **parallel variant**
standing beside `MEMEBOT1`, `MEMEBOT_FAST` and `MEMEBOT_RUNNER` under ITERATION_PROTOCOL §4b (multiple
forward tests at once: separate ledgers, separate register entries, separate state; **all** count as
trials for the family's DSR, forever).

**Freeze intent:** the rules below are frozen BEFORE this variant's first forward paper entry. The
loader (`frozen.py`) recomputes the SHA-256 of *this file* and refuses to run if it moved. An
improvement is a **new** frozen instrument, never an edit to a running one — so `MEMEBOT1`,
`MEMEBOT_FAST` and `MEMEBOT_RUNNER` are NOT touched; `MEMEBOT_G73` is a fresh object with an empty
ledger.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid account. Reads only FREE, KEYLESS public data. Real trading
is a **separate, owner-gated wallet decision**, not reachable from here.

---

## Why this variant exists (and what it is NOT)

This forward-tests the **best evolutionary genome to date, `g73c7da`**, as a frozen instrument. As of
the 2026-08-26 evo evaluation, `g73c7da` is the strongest performer by *t*:

> **+0.84R mean, t = 2.50, n = 51** — tactic: **106-minute horizon · stop −22% · target +111% ·
> dead-exit ON · flow-exit ON.**

`MEMEBOT_RUNNER` was frozen earlier from an EARLIER snapshot of this same genome (90-min horizon, +110%
target, t = 1.94). `g73c7da` has since accumulated more forward trades and drifted to a **106-minute
horizon and a +111% target**. `MEMEBOT_G73` freezes that **updated** signature so the current best
genome is carried forward as its own lookahead-proof instrument. RUNNER (90m/+110%) and G73 (106m/+111%)
are **both** trials of the "let the fat right tail run" family; both count against the family's DSR.

**This is a LEAN, an EXPLORATION / forward-test — NOT a declaration of a proven edge.** `g73c7da`'s
**t = 2.50 sits BELOW the family's K-corrected noise bar of ~2.71**, so the in-sample evo score is
suggestive, **not** significant. Nothing has cleared the reality gate. The **honest prior is ~0 or
negative**; forward paper data printed AFTER this freeze is the only arbiter.

## The one honest caveat: **g73c7da MINUS flow-exit**

The evolutionary engine's genome carries a **flow-following exit** (`use_flow_exit=1`: sell when the
recent sell/buy pressure ratio exceeds a threshold after a minimum hold). **The frozen memebot's
`paper.py` does NOT implement a flow-exit** — its `resolve_position` supports only stop, target, the
dead-coin early exit, and the horizon mark. Rather than fake an unsupported feature, `MEMEBOT_G73` is
frozen **WITHOUT flow-exit**:

> **MEMEBOT_G73 = g73c7da's entry screen + high +111% target + −22% stop + 106-min horizon +
> dead-exit — but NOT the flow-exit.** It is the high-target + dead-exit signature only.

This is stated plainly so the forward comparison is honest: `MEMEBOT_G73` is **not** a byte-identical
replica of `g73c7da`; it is g73c7da's high-target/dead-exit core minus the one exit rule the frozen
executor cannot run. The evo engine keeps forward-testing the FULL `g73c7da` (flow-exit included) in
its own ledger; this instrument tests whether the high-target/dead-exit core alone stands up forward.

**Everything identical to MEMEBOT_RUNNER/MEMEBOT_FAST except the take-profit / horizon** (§3): the free
data feed, the deterministic screen, fixed 2% sizing, the 1.5%/side toll, freeze-before-outcome, the
control null, the honest scoring, the N_min = 30 kill switch, and the **dead-coin early exit** are the
**same rules** as `MEMEBOT_FAST_PREREGISTRATION.md` / `MEMEBOT_RUNNER_PREREGISTRATION.md`. Read those
(and the base `MEMEBOT_PREREGISTRATION.md`) for the full frame; only the target/stop/horizon are
restated below.

---

## 1. The eyes (free, keyless data feed) — FROZEN, identical to MEMEBOT_FAST/RUNNER

Identical to the running variants: GeckoTerminal public API (no key) for discovery + price refresh, the
keyless read-only **PumpPortal** realtime new-token websocket for faster discovery (enriched through the
already-allowlisted GeckoTerminal endpoint into the same snapshot the screen consumes), and DexScreener
as a keyless cross-check. Every trade/Lightning/RPC/wallet host stays FORBIDDEN in `net.py`. No
order/wallet capability is added — it is a data feed only. Fields the free feed does not expose are
**never fabricated**.

## 2. The screen (deterministic, no LLM per coin) — FROZEN, identical to MEMEBOT_FAST/MEMEBOT1/RUNNER

| # | rule | threshold |
|---|------|-----------|
| 1 | `REJECT_MIN_FDV` | FDV < **$7,000** |
| 2 | `REJECT_MIN_LIQUIDITY` | reserve < **$3,000** |
| 3 | `REJECT_DEADNESS_PROXY` | unique buyers < **10** |
| 4 | `REJECT_BUNDLE_PROXY` | buys/buyer > **4.0** |
| 5 | `REJECT_HONEYPOT_PROXY` | buys ≥ **15** and sellers = **0** |
| 6 | `REJECT_STALE` | pool age > **30 min** |
| — | `REJECT_NO_FDV` / `REJECT_NO_RESERVE` | field absent → refuse, never guess |

The screen is kept identical to the running family (NOT set to g73c7da's evolved screen thresholds), so
`MEMEBOT_G73` differs from RUNNER on exactly ONE axis — the take-profit/horizon — and the family's
control-null comparison stays apples-to-apples. The one thing being tested here is the EXIT, not the
screen.

## 3. The bot (paper execution) — FROZEN — **the ONLY difference is the take-profit / horizon**

Identical to MEMEBOT_FAST/MEMEBOT1/RUNNER: 10.0 paper-SOL bankroll · **fixed 2%** per entry (never a
martingale) · long only · **1.5%/side (≈3% round-trip) toll** so expectancy is NET · every entry
sha256+UTC **frozen before outcome** · `R = (exit/entry − 1 − 2·toll) / stop_frac`. Caps: ≤ **6** open,
≤ **4** new PASS/scan, ≤ **3** control/scan.

**What differs — the take-profit, stop, and horizon (from the updated g73c7da evo genome):**

- **HIGH take-profit: target `target_frac = 1.11` (+111%), NOT the fixed +50% cap.** Let the rare
  winner run into the fat right tail instead of clipping it at +50%. A resolved `TARGET` pays
  `R = (1.11 − 2·0.015) / 0.22 ≈ +4.91R`. The reward:risk on price is ~5:1 (before toll), by design.
- **Stop `stop_frac = 0.22` (−22%).** A hair tighter than the −25% base, per the g73c7da genome; the
  risk unit is `size · stop_frac`.
- **Horizon `horizon_minutes = 106`** — the g73c7da genome's evolved hold, longer than RUNNER's 90-min
  freeze and MEMEBOT_FAST's 25-min, shorter than the 180-min base. At the horizon a still-open position
  resolves at the live mark (`HORIZON_MARK`), or as an `UNEXITABLE_TIMEOUT` loss (exit at the stop
  floor) if the feed shows no live price past horizon — same conservative discrete-poll convention.
- **DEAD-COIN EARLY EXIT (`DEAD_EXIT`) — KEPT, identical to MEMEBOT_FAST/RUNNER.** Checked *after*
  stop/target, fires only when ALL hold: held ≥ **5 minutes** (`after_minutes`), the feed's recent
  window shows **≤ 1** combined new trades (`max_recent_trades`), and price is within **±8%** of entry
  (`flat_band`). **Never kills on absence:** if the feed cannot report buys/sells, deadness is not
  confirmed and the position is held. The dead-exit thresholds (5 min / ≤1 trade / ±8%) are the
  canonical MEMEBOT_FAST/RUNNER values, inherited unchanged; they are NOT set to the genome's evolved
  dead-exit genes. A high target only pays if the losers are cut cheaply — the dead-exit is what makes
  letting winners run affordable.
- **NO flow-exit.** g73c7da's `use_flow_exit=1` is deliberately DROPPED because the frozen executor
  does not implement it (see the caveat above). `MEMEBOT_G73` is g73c7da's high-target + dead-exit core
  ONLY.

**Rationale (a-priori, NOT re-tuned on any MEMEBOT_G73 datum).** The +111% target, −22% stop and
106-min horizon come from the in-sample evo genome g73c7da (best by *t*, 2026-08-26); the dead-exit
thresholds (5 min / ≤1 trade / ±8%) are inherited unchanged from MEMEBOT_FAST/RUNNER. They are frozen
here, before any `MEMEBOT_G73` datum exists, and are not to be re-fit on the forward log. That the
genome was picked from a search is exactly why this variant is a **lean**: its t = 2.50 is below the
~2.71 noise bar, and only paired forward data resolves whether the high target beats the +50% cap.

## 4. Honest scoring + the control null — FROZEN, identical to MEMEBOT_FAST/MEMEBOT1/RUNNER

`EXPECTANCY = winrate·avgWinR − lossrate·avgLossR` per trade (NET of toll). Control null = the SAME
sizing/stop/target/**exit** applied to a deterministically-sampled set of screen-**REJECT** coins.
`expectancy(PASS) − expectancy(control)` is the forward test of whether the screen adds value under this
take-profit rule. Everything before the minimum sits fenced in `inputs_that_are_not_results`.

## 5. Kill switch — FROZEN, identical to MEMEBOT_FAST/MEMEBOT1/RUNNER

**N_min = 30** resolved PASS trades before any expectancy verdict. **HALT** if, after n ≥ N_min,
`mean_R + 1.645·SE < 0` (forward expectancy significantly negative). Below N_min: **NO VERDICT.**
Behaviour is not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, no paid accounts, free data only.
The forward log (`MEMEBOT_G73_PREREGISTRATION_LOG.jsonl` + `MEMEBOT_G73_RESOLUTION_LOG.jsonl`) is the
only arbiter, and it starts EMPTY. The honest prior is ~0 or negative; this variant exists to test,
forward and at $0, whether the best evo genome's high-target (+111%) + dead-exit signature — MINUS the
flow-exit the frozen executor cannot run — beats the fixed +50% cap of the running bots. It is a lean
drawn from an in-sample evo genome (g73c7da, t = 2.50 < the ~2.71 noise bar), never a proven edge, and
never "double every hour", which is the farmer's bait and is encoded as a goal nowhere.*
