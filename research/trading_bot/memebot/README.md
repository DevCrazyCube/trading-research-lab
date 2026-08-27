# MEMEBOT1 — a fast, light, reactive PAPER memecoin bot

A sibling of `newsdesk/` and `basket_forward.py`: the **execution scaffolding** for an autonomous
memecoin strategy, run **forward on paper** to honestly measure whether the thesis has ANY positive
expectancy **before any real money**.

> **HARD LIMITS (enforced in code).** NO real orders · NO wallet · NO real SOL · NO on-chain writes ·
> NO paid accounts · free keyless data only. Trade/RPC/wallet hosts are on an explicit FORBIDDEN list
> and refuse loudly. **Real trading is a separate, owner-gated wallet decision — not reachable here.**

Package: `scripts/trading_bot/memebot/`. Research artifacts: `research/trading_bot/memebot/`.

---

## The honest frame

The programme's own research found memecoin/pump.fun trading is **negative-sum by construction**: the
~3% round-trip toll *is* the house edge; the best gross edge measured anywhere was **0.86%** (a quarter
of the toll); the exit-rule family lost **−18.94%/trade even at ZERO cost** (the exit is a trap the
farmers set). Exactly **one** thing survived a full leakage audit — the **deadness screen** (`B20B`), a
**loss-AVOIDANCE entry filter**, not an edge.

So MEMEBOT1 tests one hypothesis, forward, on paper, at $0:

> Can filtering out the guaranteed-loss tokens (deadness-proxy + red-flag screen) plus disciplined
> fixed-fraction sizing and a defined-risk stop/target produce **ANY positive expectancy**, *net of the
> ~3% toll charged on every paper trade*?

**The honest prior is ~0 or NEGATIVE.** The target is **positive expectancy** — explicitly **NOT
"double every hour"** (that is the farmer's bait; a bot chasing it gets rugged, and it is encoded as a
goal nowhere). Below the pre-registered minimum, the log is **behaviour, not evidence**.

## Architecture (light, fast, deterministic — no per-coin LLM)

```
feed.py    the eyes    GeckoTerminal /networks/solana/new_pools  -> new launches across ALL venues
                       (pump-fun, pumpswap, meteora, raydium...), keyless, free (~30 calls/min)
                       + /pools/{addr} to refresh a price + /tokens/{mint}/pools to enrich a PumpPortal
                       push into a screen snapshot. DexScreener secondary.
ws_data.py realtime    PumpPortal wss://pumpportal.fun/api/data (subscribeNewToken) -> PUSHES new mints
                       in real time; a detached listener buffers them for the scan loop. Read-only:
                       the data websocket ONLY; every trade/Lightning REST path stays FORBIDDEN.
screen.py  the filter  deterministic PASS/REJECT + reasons: min FDV, min liquidity, DEADNESS PROXY
                       (unique-buyer count -> B20B mechanism), bundle proxy, honeypot proxy, staleness
paper.py   execution   fixed 2% sizing (NEVER martingale), stop -25% / target +50% (asymmetric),
                       ~3% toll charged, sha256+UTC FROZEN before outcome, discrete-poll resolution
bot.py     the loop    scan (screen -> open frozen PASS + bounded control entries) + track (refresh
                       -> resolve stop/target/horizon). One cycle = a couple of polite feed calls.
scoring.py honesty     EXPECTANCY = winrate*avgWinR - lossrate*avgLossR, PASS vs control null, kill
ledger.py  record      two append-only JSONL logs (prereg + resolution) + hash-verified state
net.py     the fence   host allowlist; forbidden trade/RPC/wallet hosts refuse loudly
```

## The free data feed (verified live)

**GeckoTerminal** public API — no key, free, multi-platform. `new_pools` gives, per pool: creation
time, base-token USD price, FDV, market cap (when known), USD reserve (liquidity), and per-window
buys / sells / **unique buyers** / **unique sellers** + volume. `pools/{address}` refreshes the same to
mark a position. Verified returning live Solana launches across pump-fun / pumpswap / meteora.
**DexScreener** (`token-profiles/latest`) is wired as a keyless secondary cross-check.

**PumpPortal realtime push (added 2026-08-25, verified live).** `wss://pumpportal.fun/api/data`
(`subscribeNewToken`) is a **free, keyless, read-only** websocket that **pushes** a `create` event the
instant a new pump.fun token is minted — seconds, versus the ~90 s GeckoTerminal poll. A detached
listener (`listen`, `ws_data.py`) buffers each new mint; the scan loop **enriches** a buffered mint
through the already-allowlisted GeckoTerminal `tokens/{mint}/pools` endpoint (the push event carries no
unique-buyer/buys/sells counts — those exist only once the token trades) into the SAME snapshot the
identical screen consumes. GeckoTerminal `new_pools` remains the fallback/price-refresh source; a
PumpPortal drop never blocks a scan. **Only the read-only data websocket is opened** — `net.py` keeps
`pumpportal.fun`'s host FORBIDDEN for HTTP so every trade/Lightning REST path (`/api/trade*`) is
unreachable, and `assert_data_ws()` allows *only* the exact `wss://pumpportal.fun/api/data` path. No
order/wallet capability is added; it is a data feed only. *Verified live: 17 real `create` events
buffered in a 30 s connectivity test.*

## Two parallel exit variants (MEMEBOT1 + MEMEBOT_FAST)

The owner correctly flagged the base bot's **180-minute** horizon as absurd for memecoins. Rather than
edit a running frozen spec (forbidden — ITERATION_PROTOCOL §8), a **parallel variant** was
pre-registered and runs **beside** the base on the **same live coins and the same entry screen**,
differing **only** in exit/timescale (§4b: two forward tests, separate ledgers, both declared, both
count toward the family DSR forever):

| | **MEMEBOT1** (base) | **MEMEBOT_FAST** (variant) |
|---|---|---|
| horizon | **180 min** | **25 min** |
| dead-coin early exit | none | **`DEAD_EXIT`**: held ≥ 5 min **and** ≤ 1 recent trade **and** within ±8% of entry → exit now at mark |
| entry screen / sizing / stop / target / toll | identical | identical |
| prereg hash | `11c3bd83…` | `44443a22…` |

Discovery is shared and identical; the same ordered PASS/control selection is offered to both variants
each scan, so their entries are **paired** and fresh forward data can honestly answer *which exit rule
is better*. The dead-exit thresholds are a-priori (one `m5` window; "≤1 trade" = nobody trading; ±8% =
"has not moved"), **frozen before any `MEMEBOT_FAST` datum existed** — not fit on the forward log. The
variant **never kills on absence**: if the feed cannot report buys/sells, deadness is not confirmed and
the position is held.

**What the free feed does NOT give**, and how the screen adapts honestly: the frozen `B20B` rule wants
the *on-chain largest-buyer share at t0+60 slots*, which needs a per-wallet transaction decode the REST
feed does not expose. MEMEBOT1 therefore runs a **documented PROXY** of B20B's mechanism — *"did anybody
else show up?"* via the **unique-buyer count** — not frozen-B20B itself. Frozen-B20B remains the gold
standard and is being evaluated out-of-sample by the separate b11m window-2 decode.

## The screen (frozen thresholds)

| rule | fires when | why |
|------|-----------|-----|
| `REJECT_MIN_FDV` | FDV < $7,000 | checklist min market cap |
| `REJECT_MIN_LIQUIDITY` | reserve < $3,000 | can't exit into liquidity that isn't there |
| `REJECT_DEADNESS_PROXY` | unique buyers < 10 | B20B mechanism: "nobody else showed up" = no exit money |
| `REJECT_BUNDLE_PROXY` | buys/buyer > 4.0 | few wallets, many buys = bundled/self-funded |
| `REJECT_HONEYPOT_PROXY` | buys ≥ 15 & sellers = 0 | sustained buying, no one can sell = trap |
| `REJECT_STALE` | pool age > 30 min | the edge (if any) is in the first minutes |

## Paper execution (frozen)

10 paper-SOL bankroll · **fixed 2%** per entry (never martingale) · long-only · stop **−25%** / target
**+50%** (asymmetric, defined risk; the fat right tail is not capped early) · **1.5%/side toll** so
expectancy is NET · every entry sha256+UTC **frozen before outcome** · resolution by discrete polling
(stop/target level on cross, live mark at the 180-min horizon, unexitable-timeout loss if the feed
shows no live price past horizon). Caps: ≤6 open, ≤4 new PASS/scan, ≤3 control/scan.

## Honest scoring + kill switch

`EXPECTANCY` (not win-rate) is the metric. The **control null** = the same sizing/stop/target on a
deterministic sample of coins the screen **REJECTED**; `expectancy(PASS) − expectancy(control)` is the
live forward test of whether the screen adds value. **Kill:** N_min = 30 resolved PASS trades; HALT if
`mean_R + 1.645·SE < 0`. Below N_min: **NO VERDICT** — everything sits fenced in
`inputs_that_are_not_results`.

## Run it

```bash
python -m scripts.trading_bot.memebot selftest         # hermetic wiring check, NO network
python -m scripts.trading_bot.memebot listen           # PumpPortal realtime stream (detached; --seconds N to test)
python -m scripts.trading_bot.memebot feed --limit 20  # the eyes + screen verdicts (read-only)
python -m scripts.trading_bot.memebot scan             # screen feed, open frozen entries (BOTH variants)
python -m scripts.trading_bot.memebot track            # refresh + resolve open positions (BOTH variants)
python -m scripts.trading_bot.memebot run              # one reactive cycle (track + scan)
python -m scripts.trading_bot.memebot positions        # open paper positions (BOTH variants)
python -m scripts.trading_bot.memebot score            # honest expectancy scorecard (BOTH variants)
python -m scripts.trading_bot.memebot status           # one dashboard line per variant
```

The continuous loop (`scripts/trading_bot/memebot/live_loop.sh`) starts the detached PumpPortal listener
once, then repeats scan → track → **eval-after-each-trade** for BOTH variants each cycle.

Continuous forward running (poll every few minutes for hours/days) belongs in a **detached background
subprocess** (`run --cycles N --interval S` is a bounded in-process demo only), per the project's
standing rule against long network loops inside an agent turn.

## First live paper run (2026-08-25)

20 new coins seen → **4 PASS / 16 REJECT** (reject reasons: 15 deadness-proxy, 13 min-FDV, 11
min-liquidity, 1 bundle). Opened 4 PASS + 3 control paper entries (all frozen sha256+UTC). Within
~2 min the tracker had already resolved one PASS at its stop (**−1.12R**) and one control at its target
(**+1.88R**) — memecoins are exactly that volatile. Verdict: **NO VERDICT** (1/30 resolved) — as it must
be. The frozen-hash guard was confirmed to refuse a tampered pre-registration and recover on restore.

*Paper only. The forward log is the only arbiter. The honest prior is ~0 or negative; this exists to
prove that forward, at $0, before any real-money decision.*
