# MEMEBOT1 — pre-registration (frozen rules + kill switch)

**Instrument:** MEMEBOT1 — a fast, light, reactive **PAPER** memecoin trading bot.
**Freeze intent:** the rules below are frozen BEFORE the first forward paper entry. The loader
(`frozen.py`) recomputes the SHA-256 of *this file* and refuses to run if it has moved. An improvement
is a **new** frozen instrument, never an edit to this one.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid account. Reads only a fixed allowlist of FREE, KEYLESS public
data hosts (`api.geckoterminal.com`, `api.dexscreener.com`). Trade/RPC/wallet hosts are on an explicit
FORBIDDEN list and refuse loudly. Real trading is a **separate, owner-gated wallet decision**.

---

## The honest frame (why this exists and what the prior is)

The programme's own research established that memecoin/pump.fun trading is **negative-sum by
construction**: the ~3% round-trip venue toll *is* the house edge; the best gross edge measured
anywhere was **0.86%** (a quarter of the toll); the exit-rule family lost **−18.94%/trade even at ZERO
cost** because the exit is a trap the farmers set (`research/trading_bot/MEMECOIN_RECHECK.md`,
`research/FINDINGS.md`). Exactly **one** object survived a full leakage audit: the **deadness screen**
(`research/B20B_DEADNESS_SCREEN.md`) — a **loss-AVOIDANCE entry filter**, not an edge.

So the single hypothesis MEMEBOT1 tests forward, on paper, at $0:

> Can filtering out the guaranteed-loss tokens (a deadness-proxy + red-flag screen) plus disciplined
> fixed-fraction sizing and a defined-risk stop/target produce **ANY positive expectancy**, *net of the
> ~3% toll charged on every paper trade*?

**The honest prior is ~0 or NEGATIVE.** The target is **POSITIVE EXPECTANCY** — explicitly **NOT
"double every hour"** (that is the farmer's bait; a bot that chases it gets rugged, and it is not
encoded as a goal anywhere). Below the pre-registered minimum, the log is **behaviour, not evidence.**

---

## 1. The eyes (free, keyless data feed) — FROZEN

- **Primary:** GeckoTerminal public API (no key, free tier ~30 calls/min).
  - `GET /networks/solana/new_pools` — newest pools across **all** Solana launch venues (pump-fun,
    raydium-launchlab, meteora, …), not one platform. Per pool: creation time, base-token USD price,
    FDV, market cap (when known), USD reserve (liquidity proxy), and per-window
    buys/sells/unique-buyers/unique-sellers + volume.
  - `GET /networks/solana/pools/{address}` — same attributes refreshed, to mark an open paper position.
- **Secondary (cross-check only):** DexScreener (`api.dexscreener.com`), keyless.
- Fields the free feed does **not** expose (per-wallet holdings; the on-chain largest-buyer share the
  frozen B20B rule wants) are **never fabricated** — the screen adapts to the proxy actually exposed.

## 2. The screen (deterministic, no LLM per coin) — FROZEN

Applied to each new coin's feed snapshot; **PASS** only if no rule fires, else **REJECT** + reasons.

| # | rule | threshold | rationale |
|---|------|-----------|-----------|
| 1 | `REJECT_MIN_FDV` | FDV < **$7,000** | checklist min market cap; sub-floor = dust/not-real |
| 2 | `REJECT_MIN_LIQUIDITY` | reserve < **$3,000** | cannot exit into a reserve that isn't there |
| 3 | `REJECT_DEADNESS_PROXY` | unique buyers < **10** | **B20B mechanism, adapted**: "nobody else showed up" → no external money to exit into |
| 4 | `REJECT_BUNDLE_PROXY` | buys/buyer > **4.0** | many buys from few wallets = bundled/self-funded launch |
| 5 | `REJECT_HONEYPOT_PROXY` | buys ≥ **15** and sellers = **0** | sustained buying, no one able/willing to sell = one-way trap |
| 6 | `REJECT_STALE` | pool age > **30 min** | the edge (if any) is in the first minutes; older pools are someone else's trade |
| — | `REJECT_NO_FDV` / `REJECT_NO_RESERVE` | field absent | refuse rather than guess a missing datum |

**On the deadness screen specifically.** Frozen-B20B ("at t0+60 slots, largest buyer's share ≥ 0.95 →
don't enter") requires a per-wallet on-chain decode the free REST feed does not provide, so MEMEBOT1
runs a **documented PROXY** of its mechanism (unique-buyer count), *not* frozen-B20B. Frozen-B20B
remains the gold standard and is being evaluated out-of-sample by the separate b11m window-2 decode.

## 3. The bot (paper execution) — FROZEN

- **Bankroll:** 10.0 paper SOL (hypothetical).
- **Sizing:** **fixed 2%** of bankroll per entry = 0.2 paper SOL. **NEVER a martingale / double-down.**
- **Direction:** long only (bonding-curve venue).
- **Stop / target (asymmetric, defined risk):** stop **−25%**, target **+50%** (reward:risk ≈ 2:1 on
  price, before toll). Target > stop by construction so the fat right tail is not capped too early
  (the `+6%` take-profit that inverted the payoff in prior work is explicitly avoided).
- **Venue toll:** **1.5%/side (≈3% round-trip)** charged on every paper trade — the irreducible house
  edge the research measured. Reported expectancy is therefore **NET**, never a gross fantasy.
- **R-multiple:** `R = (exit/entry − 1 − 2·toll) / stop_frac`. Stop ≈ −1.12R, target ≈ +1.88R.
- **Freeze:** every entry commits its full spec (pool, entry price, stop, target, size, toll, screen
  verdict, `decided_utc`) with a SHA-256 **before** any outcome — lookahead-proof by construction.
- **Resolution:** discrete polling; a position resolves at the **stop/target level** when a poll shows
  price has crossed it, at the **live mark** at horizon (**180 min**), and as an **unexitable-timeout**
  loss (exit at the stop floor) if the feed shows no live price past horizon (the bonding-curve
  "never traded again" case). This is conservative and matches what a real reactive poller could act on.
- **Caps:** ≤ **6** open positions; ≤ **4** new PASS entries per scan; ≤ **3** control entries per scan.

## 4. Honest scoring + the control null — FROZEN

- **Metric:** `EXPECTANCY = winrate·avgWinR − lossrate·avgLossR` per trade (win-rate alone is not it).
- **Control null:** the SAME sizing/stop/target applied to a bounded, deterministically-sampled set of
  coins the screen **REJECTED**. `expectancy(PASS) − expectancy(control)` is the forward test of
  whether the screen adds value — the B20B "passed rate vs base rate" comparison, run live on paper.
- Everything before the minimum sits in `inputs_that_are_not_results`, fenced from being read as an edge.

## 5. Kill switch — FROZEN

- **N_min = 30** resolved PASS trades before any expectancy verdict is licensed.
- **HALT** if, after n ≥ N_min, the one-sided **upper 95% bound** on mean R is **below zero**
  (`mean_R + 1.645·SE < 0`) — i.e. the forward expectancy is *significantly* negative.
- Below N_min: **NO VERDICT.** Behaviour is not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, no paid accounts, free data only.
The forward log (`MEMEBOT_PREREGISTRATION_LOG.jsonl` + `MEMEBOT_RESOLUTION_LOG.jsonl`) is the only
arbiter. The honest prior is ~0 or negative; this instrument exists to prove that forward, at $0,
before any real-money decision.*
