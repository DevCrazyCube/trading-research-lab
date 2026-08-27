# CEFBOT — a standalone paper-trading bot for the CEF discount-LEVEL tilt

**PAPER / HYPOTHETICAL ONLY.** No real orders. No real money. No broker trading endpoint. Every
position is marked-to-market against realised prices, exactly like
`scripts/trading_bot/basket_forward.py`. Live execution is owner-gated and this bot does not reach
it.

## What it is

The programme re-examined 86 killed edges (`research/trading_bot/THOROUGH_REEXAM.md`) and exactly
**one** cleared the bar as a new, diversifying, free-data-reachable revive: **R1 — the T12 CEF
discount-LEVEL tilt** (held-out backtest **+13.44 bp/week net, t 3.51, annualised Sharpe 2.35,
DSR 0.9971, n = 116 weeks**). That edge **passed a backtest. It has never passed a forward test.**

This bot is that forward test made concrete. Each week it pulls the live CEFConnect discount
snapshot, tilts long into the widest-discount decile, hedges broad equity beta with a short in a
single liquid index ETF (SPY), marks to realised price, and appends an honest, append-only ledger
that can eventually **certify or kill** the edge on data that printed *after* the rule was frozen.

**The honest framing, up front:** a positive backtest is not a positive forward test. This bot
starts a real prospective ledger and the standard discipline applies — **below the sample
minimum there is NO VERDICT; behaviour is not evidence.** The backtest's 2.35 Sharpe is *not* the
forward expectation: after survivorship + point-in-time-NAV + hedge-basis haircuts the honest
forward prior is **~1.0–1.5**, and this specific long-vs-hedge, 1-week-hold expression is a
*distinct, weaker-expected* deployment of the family — not the H=4 long-short cell that produced
2.35 (`CEFBOT_PREREGISTRATION.md` §5, §7).

## The frozen strategy (see `CEFBOT_PREREGISTRATION.md`, sha256-verified at every run)

- **Universe / signal:** CEFConnect `GET /api/v3/DailyPricing` (keyless, free). Eligible = funds
  with `Ticker`/`Discount`/`NAV`(>0)/`Price`, price > $5. Rank by **discount LEVEL** (family S2 —
  the surviving form; the S1 mean-reversion primary is genuinely dead).
- **Long book:** the **widest-discount decile** (`round(0.10 × N)` ≈ 34 of ~335 names today),
  equal weight, long notional 1.0.
- **Market hedge:** SHORT **SPY** at `beta_h = 0.50` of long notional (a **frozen, unfitted**
  prior). One deep, easy-to-borrow index ETF — **by design the bot never shorts individual CEFs**
  (the R1 borrow guard). An equity short hedges *equity* beta only; the residual rates/credit
  factor is not hedged, and the buy-and-hold-CEF null reveals how much survives.
- **Cadence / hold:** rebalance **weekly** (≥5 business days), **1-week hold**, fully re-formed
  each week.
- **PIT-NAV discipline:** `Discount` (a function of NAV, struck after the close) forms the
  **signal only and never a mark** — all P&L is realised **Price** only. The signal snapshot is
  **lagged ≥1 session** behind execution/marks (enforced by the cache; the inaugural tranche is a
  transparently-flagged same-day-signal concession).
- **Costs, per side, honest:** CEF half-spread **11.53 bp** (first-party measured) both legs on
  realised turnover; SPY half-spread 0.116 bp; SEC §31 0.278 bp on sales; FINRA TAF
  $0.000166/share; SPY borrow 33 bp/yr floor. No CEF borrow (no short CEF).

## The two benchmarks (evaluate loop)

1. **Absolute hurdle:** T-bill + **1.00 pp/yr** (~5.3%/yr = 9.94 bp/wk today; the T-bill level is
   a refreshable input, the +1pp alpha bar is frozen).
2. **Beta-isolation null:** the equal-weight **broad CEF universe** (buy-and-hold the CEF basket).
   The bot's long-leg edge over this null is the pure cross-sectional **discount-reversion alpha**,
   separated from CEF beta by construction.

## Gates and the pre-registered kill rule

- **Verdict minimum: 123 settled weekly obs** (the programme's own power floor — the CEF weekly
  instrument cannot certify an annualised Sharpe below ~1.1–1.3 with fewer). Below it, all
  Sharpe/t/annualised figures are quarantined in an `inputs_that_are_not_results` block.
- **Kill (fires early): `n ≥ 26` and cumulative net < 0 and `t_net ≤ −2.0` → HALT** (`DEAD —
  FORWARD-NEGATIVE`). The bot self-halts at run time before committing a new book.
- **Drawdown halt: realised peak-to-trough ≥ 25% → HALT** (`DEAD — DRAWDOWN`).
- **Improvement is a NEW pre-registration**, never a tweak to this rule
  (`ITERATION_PROTOCOL.md`).

## Caveats on the record (not smoothed over)

- **Capacity is SIZE-capped to low single-digit $M** (CEF closing auctions clear $0.0–0.3 M).
- **Point-in-time NAV risk** in the CEFConnect feed is unfalsifiable from that source and hits the
  discount signal hardest.
- **Survivorship:** CEFConnect lists only funds alive today; the bias sign is unknown. The cached
  `proof` replay is therefore a **selection-inflated upper bound**, not forward evidence.

## Run it

```bash
# hermetic self-check (freeze verify + engine proof; no network, no order, no ledger write)
python -m scripts.trading_bot.cefbot selftest

# show today's target widest-discount basket (no commit)
python -m scripts.trading_bot.cefbot show

# advance ONE weekly cycle: fetch snapshot, settle the matured book, enter this week's, log
python -m scripts.trading_bot.cefbot run
python -m scripts.trading_bot.cefbot run-dry     # compute-only, no state/ledger write

# the read-only scorecard + verdict (two benchmarks, gates, kill switch)
python -m scripts.trading_bot.cefbot evaluate
python -m scripts.trading_bot.cefbot evaluate-json

python -m scripts.trading_bot.cefbot status      # one-line status
```

**Weekly cron** (paper; the cadence guard makes extra invocations no-ops, so daily is also safe):

```cron
# 16:30 ET after the close, weekdays — one cycle; guard enforces the weekly rebalance internally
30 20 * * 1-5  cd /home/anont/meme && python -m scripts.trading_bot.cefbot run >> research/trading_bot/cefbot/cefbot.cron.log 2>&1
```

## Files

| path | what |
|---|---|
| `scripts/trading_bot/cefbot/strategy.py` | the FROZEN rule + sha256 verify + book construction |
| `scripts/trading_bot/cefbot/bot.py` | paper execution, weekly state machine, PIT-NAV lag, kill switch |
| `scripts/trading_bot/cefbot/evaluate.py` | read-only scorecard, two benchmarks, gates, kill rule |
| `scripts/trading_bot/cefbot/__main__.py` | CLI |
| `research/trading_bot/cefbot/CEFBOT_PREREGISTRATION.md` | the immutable rule (hashed) |
| `research/trading_bot/cefbot/CEFBOT_LOG.jsonl` | append-only ledger (never edited/restarted) |
| `research/trading_bot/cefbot/CEFBOT_STATE.json` | open book, last rebalance, status |
| `research/data/cefbot_cache/snapshots/` | one cached CEFConnect snapshot per cycle |
