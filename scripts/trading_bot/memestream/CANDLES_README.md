# memestream — realtime 1-second candle data layer (paper / read-only)

A self-contained data layer that aggregates **real memecoin trades** into **1-second OHLCV candles
with a buy/sell split** for the coins the paper memebot currently holds, and exposes a clean
importable **read API** for two later consumers:

- the **dashboard's** 1-second price charts → `get_candles(pool, timeframe, lookback_secs)`
- the **flow-following exit's** realtime buy-pressure → `get_flow(pool, window_secs)`

This module builds *only* the data layer + ingestion + read API. It does **not** wire the consumers,
place orders, hold a wallet, touch real SOL, or write anything on-chain. It reads only free, keyless,
read-only public data.

Package: `scripts/trading_bot/memestream/`
Cache:   `research/data/memebot_cache/candles/`

---

## Trade source

### What we use today (free, keyless): GeckoTerminal per-pool trades
`GET https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/trades`, fetched through
`memebot.net.http_get_json` so it inherits the bot's existing **polite 2.1 s throttle + 429 backoff +
host allowlist**. Each trade carries a second-resolution `block_timestamp`, a `kind` (buy/sell), USD
volume, and per-side USD prices — everything the 1 s aggregator needs. The base-token (memecoin) USD
price is picked deterministically using the held coin's mint.

### Why not the PumpPortal push
The spec asked for PumpPortal's `subscribeTokenTrade` push. A live test on 2026-08-25 showed it is **no
longer free**:

> `'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an
> API key funded with at least 0.02 SOL.`

Funding a key is real money + a wallet, which this paper layer must never do. So the push path is
**implemented but dormant**: `sources.pumpportal_probe` / `normalize_pumpportal_trade` open only
`wss://pumpportal.fun/api/data` behind `net.assert_data_ws`, detect the gating message, log it, and
fall back to the free source **without funding anything**. If PumpPortal restores the free tier (or an
owner supplies a funded key — a separate, owner-gated decision made elsewhere), the same normalizer
feeds the same aggregator with no other change. `subscribeNewToken` remains free and is unaffected.

### Honest latency
This tightens the bot's reaction from the ~90 s GeckoTerminal `new_pools` cadence to **real
1-second-resolution candles**, refreshed once per poll sweep. With the polite 2.1 s throttle the sweep
is ~`num_pools × 2.1 s` (≈40 s for ~19 held coins), so *discovery* of a new trade lands within a sweep,
not in 1–2 s. The **push** path would give ~1–2 s if it were free. Either way this is a paper
monitoring layer — it does **not** out-race millisecond snipers or MEV bots. A consumer that needs
sub-sweep latency on one coin can run a dedicated tight loop: `listen --pool <POOL>`.

---

## 1-second aggregation

Trades are deduplicated by `tx_hash` and rolled into 1 s buckets keyed by `floor(block_timestamp)`.
A second is flushed to disk once it is **complete** (older than the newest activity, minus a small
guard); a flushed second is **closed** (late trades for it are dropped, never partially re-flushed).
The series is **sparse** — only seconds that had ≥1 trade are written; a gap means "no trades that
second". `5s` and `1m` frames are **derived from the 1 s base on read** (no separate storage).

---

## Cache format

One append-only JSONL per held pool, bounded to a ring of the most recent `MAX_CANDLES` (~4 h of 1 s):

```
research/data/memebot_cache/candles/{pool}.jsonl
research/data/memebot_cache/candles/_keymap.json   # {pool|mint: pool} so reads key by either
research/data/memebot_cache/candles/ingest.log     # ingestion log
```

Each line is one completed 1-second candle:

```json
{"t":1787655289,"o":6.99e-05,"h":7.05e-05,"l":6.93e-05,"c":6.96e-05,
 "v":638.24,"buys":10,"sells":3,"buy_vol":364.60,"sell_vol":273.65}
```

| field | meaning |
|-------|---------|
| `t` | epoch seconds, start-of-second bucket (UTC) |
| `o` `h` `l` `c` | base-token price in **USD** within the second |
| `v` | total traded volume in **USD** in the second |
| `buys` / `sells` | number of buy / sell trades |
| `buy_vol` / `sell_vol` | buy / sell volume in **USD** |

> Volumes are **USD** for the GeckoTerminal source. The dormant PumpPortal path records volume in
> **SOL** (documented on `normalize_pumpportal_trade`); if it is ever activated, note the unit change.

---

## Read API

Import and call — read-only, cross-process safe, they touch only the JSONL cache:

```python
from scripts.trading_bot.memestream.candles import get_candles, get_flow
```

### `get_candles(pool, timeframe='1s', lookback_secs=None) -> list[dict]`
Cached OHLCV candles for `pool` (a **pool address** or a **token mint** — resolved via `_keymap.json`),
oldest-first. `timeframe` ∈ `{'1s','5s','1m'}` (5s/1m derived from 1s). `lookback_secs` keeps only
candles within N seconds of the newest cached candle. Returns `[]` if the pool has no cache yet
(honest absence — never a fabricated candle). Duplicate/re-flushed seconds are collapsed on read.

### `get_flow(pool, window_secs=60) -> dict`
Realtime buy/sell **pressure** over the last `window_secs` — what the flow-following exit consumes:

```json
{"pool":"3j4M22...","window_secs":60,"trades":300,"buys":199,"sells":101,
 "buy_vol":6058.43,"sell_vol":5098.17,"net":960.26,"buy_frac":0.543,
 "as_of":1787655295,"as_of_utc":"2026-08-25T10:54:55+00:00"}
```

`net = buy_vol - sell_vol` in USD (positive = net buying). `buy_frac = buy_vol/total` (or `null` if no
volume). `as_of` is the newest cached candle's second, so a stale feed is visible (compare to wall
clock). A pool with no recent trades returns zeros with `trades: 0` — an explicit "nothing traded",
never a silent zero.

Helpers: `candles.cached_pools()` lists pools with a cache; `candles.register_keys(pool, mint)` /
`candles.resolve_pool(key)` manage the pool↔mint keymap.

---

## Ingestion (run detached)

The long-lived listener discovers held pools from the memebot ledgers (`sources.read_holdings` — open
paper positions across both `MEMEBOT` and `MEMEBOT_FAST`), re-discovers them every 120 s so the watch
set follows the bot's positions, round-robin polls each pool's trades, and flushes 1 s candles. It is
resilient: a transient poll error is skipped and the loop continues; a bad holdings read is logged and
retried. CPU-light (~32 MB RSS).

```bash
# detached, reconnecting, resubscribing on holdings change:
setsid nohup python -m scripts.trading_bot.memestream listen \
    >> research/data/memebot_cache/candles/ingest.log 2>&1 < /dev/null &

# other commands:
python -m scripts.trading_bot.memestream holdings              # list held pools
python -m scripts.trading_bot.memestream verify --seconds 70   # short live ingest + sample
python -m scripts.trading_bot.memestream sample --pool <POOL>  # print cached candles + flow
python -m scripts.trading_bot.memestream listen --pool <POOL>  # tight single-pool watch
```

---

## Guarantees / limits

- Read-only trade websocket only (`net.assert_data_ws`); **no trade REST**, no order, no wallet, no
  real SOL, nothing on-chain. Paper only.
- Free, keyless data hosts only (GeckoTerminal via `net.assert_free_host`).
- Standalone module — it does **not** edit `dashboard/` or `memebot_evo/`; it only *reads* memebot's
  ledgers/state and *reuses* `memebot.net`. The two consumers import `get_candles` / `get_flow` later.
