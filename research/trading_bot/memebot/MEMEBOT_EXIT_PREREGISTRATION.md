# MEMEBOT_EXIT — pre-registration (the exitability-first fast-scalp)

**Instrument:** `MEMEBOT_EXIT` — a fast, light, reactive **PAPER** memecoin bot. A **parallel variant**
standing beside MEMEBOT1/FAST/QUICK under ITERATION_PROTOCOL §4b (separate ledgers, register entry, and
state; counts as a trial for the family's multiple-testing bar).

**What this instrument is FOR (say it plainly).** Not an alpha hunt. This is the owner's actual game:
disciplined fast scalping — buy only what you can sell, sell fast, and never get stuck in the dump. On
memecoins the money does not die to the toll; it dies to the **unexitable dump** — a coin whose exit
path closes while you hold it (verified on-chain: silent coins drain to ~$0 liquidity, −64% to −100%,
and the position cannot be sold at any price). So the whole design point of MEMEBOT_EXIT is to attack
THAT one leak: refuse coins with no proven exit path, and get out before the path closes.

**Freeze intent:** the rules below are frozen BEFORE this variant's first forward paper entry. The
loader (`frozen.py`) recomputes the SHA-256 of *this file* and refuses to run if it moved. An
improvement is a **new** frozen instrument, never an edit to this one.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid account. Reads only FREE, KEYLESS public data.

---

## Why this variant exists (the two things that differ)

**1. EXITABILITY-FIRST ENTRY.** On top of the shared deadness/red-flag screen, MEMEBOT_EXIT adds one
positive requirement: **don't buy what nobody has sold.** It requires `min_sellers` demonstrated
successful exits in the feed snapshot before entering — the free-feed, tradable-today stand-in for the
audited B20B rule ("is there external money to exit into?"). If N wallets have already sold into this
pool, an exit path exists *right now*; if nobody has sold, you would be buying into a one-way trap that
the zero-seller honeypot rule only catches at its extreme. Paired with a **high liquidity floor** (a
deep reserve is depth you can actually exit through), this is the "know what you buy" half of the game.

**2. FAST EXIT.** A short 12-minute hard horizon plus the dead-coin early exit. The owner's thesis and
the QUICK verdict agree: winners resolve in ~10 minutes and the unexitable deaths arrive later, so being
fast books the non-winners while the exit path is still open. Get out before the drain completes.

**Everything else is the shared frame** (§2–§5 of `MEMEBOT_PREREGISTRATION.md`): the free data feed,
fixed 2% sizing, the −25% stop / +50% target, the 1.5%/side toll so expectancy is NET, freeze-before-
outcome, the control null, and the N_min=30 kill switch.

---

## 1. The eyes — FROZEN, identical to the shared feed

GeckoTerminal public API + PumpPortal free keyless data websocket (enriched via GeckoTerminal) +
DexScreener cross-check. Fields the free feed does not expose are **never fabricated**.

## 2. The screen — FROZEN — **exitability-first (the shared screen PLUS one positive rule)**

| # | rule | threshold |
|---|------|-----------|
| 1 | `REJECT_MIN_FDV` | FDV < **$7,000** |
| 2 | `REJECT_MIN_LIQUIDITY` | reserve < **$10,000** (raised: depth = exit capacity) |
| 3 | `REJECT_DEADNESS_PROXY` | unique buyers < **12** |
| 4 | `REJECT_BUNDLE_PROXY` | buys/buyer > **4.0** |
| 5 | `REJECT_HONEYPOT_PROXY` | buys ≥ **15** and sellers = **0** |
| 6 | `REJECT_STALE` | pool age > **30 min** |
| 7 | `REJECT_NOT_EXITABLE` | **sellers < 3** — no proven exit path (don't buy what nobody has sold) |
| — | `REJECT_NO_FDV` / `REJECT_NO_RESERVE` | field absent → refuse, never guess |

## 3. The bot (paper execution) — FROZEN — **fast exit**

Shared: 10.0 paper-SOL bankroll · **fixed 2%** per entry (never a martingale) · long only · stop
**−25%** / target **+50%** · **1.5%/side (≈3% round-trip) toll** so R is NET · every entry sha256+UTC
frozen before outcome · `R = (exit/entry − 1 − 2·toll) / stop_frac`. Caps: ≤ **6** open, ≤ **4** new
PASS/scan, ≤ **3** control/scan.

**What differs — a FAST exit:**
- **SHORT hard horizon: 12 minutes.** At the horizon a still-open position resolves at the live mark
  (`HORIZON_MARK`), or, if the feed shows no live price, as an `UNEXITABLE_TIMEOUT` loss at the stop
  floor — the same conservative convention as the other variants.
- **DEAD-COIN EARLY EXIT (`DEAD_EXIT`)**, unchanged: held ≥ 5 min, ≤ 1 recent trade, price within ±8%
  of entry, never kills on absence.

## 4. Honest scoring — FROZEN, and the metric that MATTERS here

Expectancy (NET of toll) vs zero and vs the control null, as for every variant. But the **honest decider
for THIS instrument is the unexitable-dump rate**: what fraction of resolved PASS trades ended as
`UNEXITABLE_TIMEOUT`. The entire hypothesis is that exitability-first entry + fast exit **drives that
rate down** versus the other variants (FAST ran ~33%). If the dump rate falls AND expectancy is no worse,
the discipline works; if the dump rate does not fall, the free-feed exitability proxy is too weak and we
say so. Portfolio P&L and the dump rate — not a t-stat versus a null — are what "does it make money"
means here.

## 5. Kill switch — FROZEN, identical

**N_min = 30** resolved PASS trades before any verdict. **HALT** if, after n ≥ N_min,
`mean_R + 1.645·SE < 0`. Below N_min: **NO VERDICT.**

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, no paid accounts, free data only.
The forward log is the only arbiter. The honest prior is that most memecoins are still unexitable traps;
this instrument's job is to enter only the ones with a proven exit and to leave before the exit closes.*
