# MEMEBOT paper terminal — local dashboard

A dark, [trade.padre.gg](https://trade.padre.gg)-style **read-only** web terminal for the paper
memecoin bot in `scripts/trading_bot/memebot/`. It visualises the bot's **live paper positions** and
per-coin charts. It places **no orders, holds no wallet, touches no real SOL**, and exposes **no
trading endpoint** — exactly like the bot it watches.

## Run it

```bash
python3 scripts/trading_bot/memebot/dashboard/server.py
# then open:
http://localhost:8791
```

Or detached:

```bash
setsid nohup python3 scripts/trading_bot/memebot/dashboard/server.py \
  > research/trading_bot/memebot/dashboard_server.log 2>&1 < /dev/null &
```

Stdlib-only HTTP server, bound to **127.0.0.1** only. The charting library
(TradingView lightweight-charts) loads from a CDN on a local page; if it is unreachable the dashboard
falls back to a built-in canvas candlestick renderer, so the chart works offline too.

## The two pages

The UI is a single-page app with real hash routes:

### 1. Portfolio — `#/` (landing page)
A dense, sortable table of **every token the bot is in** (open + recently closed), one row each:

- **coin logo** + symbol / name
- **entry price**, **current price**
- **P&L in % and in R** (green up / red down)
- **market cap**, **liquidity**, **age**
- **variant** (`base` = MEMEBOT1, `FAST` = MEMEBOT_FAST, `/flow` = discovered via the push stream)
- **status** (`OPEN`, `stopped`, `target`, `horizon`, `dead-exit`, `null`)

Click any column header to sort; click a **row to open that token's page**. A summary strip on top
is the honest scorecard: **paper invested, total P&L (R), win rate, expectancy /trade (net of the ~3%
toll), and the control-null benchmark**. Control/null rows (coins the screen REJECTED — the benchmark)
can be hidden with the toggle.

### 2. Token detail — `#/token/{pool}`
A separate page you navigate to, with a **Portfolio** back link:

- A big **candlestick chart** with the bot's **BUY ▲ (green)** and **SELL ▼ (red)** markers placed at
  the exact ledger entry/exit time and price, plus **entry / stop / target price lines**.
- A stats panel: price, market cap, liquidity, FDV, 5-min volume, unique buyers, buys/sells, sellers,
  live buy/sell **net flow** (from the local 1-second cache when available), the bot's
  entry/stop/target/size/horizon, P&L, status, **security/behaviour flags**, and the **screen
  decision + reasons**.

## Where the data comes from

- **Positions, entries, exits, P&L, expectancy** — read directly from the bot's own frozen ledgers via
  the bot's own modules (`ledger`, `paper`, `scoring`, `frozen`), so every number matches the bot.
  Both parallel instruments (MEMEBOT1 and MEMEBOT_FAST) are aggregated.
- **Live prices & candles** — the **local 1-second candle cache** (`memestream.candles.get_candles`)
  when the ingester is tracking a pool (instant, un-rate-limited), falling back to the **free, keyless
  GeckoTerminal** public API otherwise. The chart automatically uses GeckoTerminal's longer history
  when the bot's entry predates the local cache, so the buy/sell markers are always on-screen.
- **Coin logos** — resolved via GeckoTerminal token info and proxied server-side (disk-cached
  permanently under `research/data/memebot_cache/logos/`); a neutral monogram square is shown when a
  token has no logo.

All GeckoTerminal access is serialised behind a single process-wide rate gate and cached, to stay well
under the free tier. A background thread keeps open-position prices warm so the pages render in well
under 300 ms; the browser polls every ~6 s (a "live" dot + "last updated" show freshness).

## JSON API (all read-only, GET only)

| Endpoint | What it returns |
|---|---|
| `GET /api/summary` | scorecard: invested SOL, cum R (PASS + control), win rate, expectancy, per-instrument verdicts |
| `GET /api/positions` | every position, open + closed, with computed live P&L (% and R) |
| `GET /api/coin/{pool}` | one coin's detail: entry, live stats, flow, screen decision, stop/target, buy/sell markers |
| `GET /api/ohlcv/{pool}?tf=1s\|5s\|1m\|5m\|15m\|1h&since={epoch}` | candles (local cache first, GeckoTerminal fallback) |
| `GET /api/logo/{pool}` | token logo image (proxied + cached) or a placeholder |

There is **no `POST`** and no order/wallet/trade path anywhere in this server — by construction.

## Honest note

This is a **paper-only display**. Every position is a hypothetical mark-to-market from the bot's
lookahead-proof ledgers; there is no real execution, no wallet, and no real money involved. Numbers
below the pre-registered minimum (30 resolved PASS trades) are shown as **inputs, not a verdict** — the
honest prior for this strategy is ~0 or negative. Real trading would be a separate, owner-gated wallet
decision and is not reachable from here.
