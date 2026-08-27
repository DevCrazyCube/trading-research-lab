# The Newsdesk — an agent-driven, world-reading forward paper logger

A **new SIGNAL SOURCE**, not a new bot. The programme's bot already does parts 2/3/4 of a
discretionary trader's edge — **asymmetric payoff, strict risk sizing, iron discipline** — perfectly
and mechanically (see `basket_forward.py`). The Newsdesk adds the missing part 5: **a contextual read
of the world**, supplied by an LLM agent reading live free news/event feeds, and executes that read
through the *same* asymmetry + risk + discipline machinery, logged with the *same* freeze-then-test +
forward-ledger + kill-switch + honest-expectancy rigor as BASKET1.

It places **NO orders, holds NO position, touches NO account or real money, writes NO git commit**. It
reads only a fixed allowlist of **free, keyless** public data hosts. It is a **sibling of BASKET1**,
and it is meant to feel like one.

> **The honest prior, stated once so it is not discovered in month six:** public news is priced into
> liquid instruments within seconds. A free-feed agent reading a headline is almost always late, so the
> candid expectancy of "trade the news" is **≈ 0 before costs and negative after the spread a real fill
> would cross.** This instrument is a *hypothesis under test*, and the base case is that it halts on the
> kill switch. The forward log is the only arbiter.

---

## Why forward-only is not optional here (the poisoned-backtest problem)

An LLM agent is the signal source, and **an LLM's backtest is structurally poisoned by lookahead**:
the model was trained on data through 2026, so on any *historical* date it already "knows" what
happened next. A backtest of an agent's discretionary read measures *memory*, not *skill*, and is
worth exactly nothing.

The **only** honest instrument is forward-only: the agent reads **today's** news and **commits a
falsifiable trade (sha256 + UTC timestamp) BEFORE the move happens**; the realised outcome is measured
later against free prices it could not have seen. That structurally eliminates lookahead. It is
enforced in code, not promised:

1. **Freeze precedes outcome.** The instant a setup is proposed, its full spec (instrument, direction,
   entry reference captured *now*, stop, target, horizon, thesis, confidence, triggering event ids) is
   canonically serialised, **sha256-hashed with `proposed_utc`**, and appended to
   `NEWSDESK_PREREGISTRATION_LOG.jsonl` **before** any resolution. `verify_preregistration_hashes`
   recomputes every hash on every run — a spec edited after freeze refuses the whole run.
2. **Resolution reads only the strictly-later path.** `resolve._assert_forward` discards every price
   bar at or before `proposed_utc` and refuses if one would otherwise score a setup. A setup scored on
   a bar it saw at freeze is the exact failure this instrument exists to defeat.
3. **The agent is never backtested.** There is no code path that runs the proposer on a historical
   date. `selftest` uses synthetic data only and never writes the ledger.

---

## Architecture (`scripts/trading_bot/newsdesk/`)

| module | role |
|---|---|
| `net.py` | Host-allowlisted, polite, read-only HTTP. The ONLY network the package touches; every non-allowlisted host (and every trading host) refuses. No POST, no auth, no order path. |
| `world_reader.py` | **The eyes.** Pulls the free feeds into one normalized, de-duplicated event stream (ts, source, headline, tickers/assets, snippet, link, content id). |
| `proposer.py` | **The brain's interface + the enforcement.** Specifies the proposal shape an agent emits as JSON, and mechanically enforces R:R≥2, a mandatory stop, ≤1% risk, ≤5 concurrent, direction consistency, horizon bounds, liquid free-priceable instruments — and freezes an accepted setup (sha256 + `proposed_utc`). `no_trade_record` logs the disciplined abstention. |
| `prices.py` | Free price PATHS for resolution: Yahoo chart OHLC for equities/ETFs, CoinGecko market-chart points for crypto. |
| `resolve.py` | **The forward-only mark-to-market.** Walks the strictly-later realised path, decides stop/target/horizon first (adverse tie-break → stop), records the realised R-multiple, and computes a same-instrument random-direction null R on the same path. |
| `scoring.py` | **Honest scoring (mirror of `basket_eval`).** win-rate, avg-win R, avg-loss R, EXPECTANCY = winrate·avgWinR − lossrate·avgLossR; benchmarks vs zero and vs the random-entry null; the frozen kill switch. Read-only. |
| `ledger.py` | State + the two append-only JSONL logs (never rewritten): pre-registration and resolution. |
| `frozen.py` | Loads + verifies the frozen spec against the pre-registration sha256; the setup-fingerprint hash. |
| `selftest.py` | Hermetic, no-network wiring check of every enforcement, the R-math, the forward-only assertion, and the kill switch. |

The agent (an LLM) is the discretionary component **only** at proposal time; it never sees an outcome,
and the outcome is not available on the day of the read.

---

## The free sources (all verified 200 OK, keyless, from this environment)

**Reading the world (eyes):** SEC EDGAR latest 8-K atom feed (`www.sec.gov`) + full-text search
(`efts.sec.gov`); Yahoo Finance per-ticker headline RSS (`feeds.finance.yahoo.com`); Google News RSS
search (`news.google.com`); CoinGecko trending (`api.coingecko.com`). Agents additionally have
WebFetch/WebSearch for live reading.

**Pricing the outcome (marks):** Yahoo Finance chart OHLC (`query1.finance.yahoo.com`) for
equities/ETFs; CoinGecko market-chart range (`api.coingecko.com`) for crypto. Instruments are
restricted to **liquid, free-priceable symbols** — US equities/ETFs in the frozen watchlist and major
crypto in the frozen universe.

---

## How parts 2/3/4 are enforced (immutable once frozen)

- **Asymmetry (part 2):** reward:risk **≥ 2.0** and a real stop are mandatory — a violation is
  rejected before it can reach the ledger.
- **Risk sizing (part 3):** each setup risks **≤ 1.0%** of the notional account to its stop; size =
  `0.01·account/|entry−stop|`. Because sizing is fixed, outcomes read directly in **R-multiples**
  (stop = −1R, target = +≥2R).
- **Discipline (part 4):** **≤ 5** concurrent open setups; **"no trade today" is allowed and logged**
  (not trading is the skill); a frozen setup's stop/target/horizon are immutable (an improvement is a
  NEW frozen instrument, per §7 of the pre-registration).

---

## How it connects to the existing BASKET/forward-test discipline

It is deliberately the same shape as `basket_forward.py` + `basket_eval.py`:

- a **frozen pre-registration** (`NEWSDESK_PREREGISTRATION.md`) sha256-pinned into a frozen JSON
  (`NEWSDESK_FROZEN.json`), verified on every run — a rule that can move is not frozen;
- an **append-only forward ledger** written before outcomes are known, never truncated;
- a **per-observation kill switch** (HALT if, after `n ≥ N_min = 30`, the one-sided upper-95% bound on
  mean R < 0) — the same one-sided-upper-bound test BASKET1 uses at N_min = 40;
- **honest expectancy scoring** with every pre-minimum number fenced inside
  `inputs_that_are_not_results`, a **benchmark that is not zero** (here the random-entry null, as
  BASKET1's is T-bills), and the loud "this is a LOGGER, no orders, no real money" framing;
- the same **ITERATION_PROTOCOL** stance: improvement is a new frozen instrument, never an edit to a
  running one.

The one addition is the signal source: an agent reading the world, executed by parts 2/3/4.

---

## Running it daily

```bash
# 1. Read today's world (the eyes) — pull the free event stream:
python -m scripts.trading_bot.newsdesk read

# 2. (agent brain) form a contextual read and emit 0-N proposals as JSON, e.g. proposals.json:
#    [{"instrument":"ethereum","asset_class":"crypto","direction":"long","entry_ref":2439.65,
#      "stop":2340.0,"target":2690.0,"horizon_hours":72,"account_risk_pct":1.0,"confidence":0.35,
#      "event_ids":["<world-reader event id>", ...],"thesis":"...tied to the specific event..."}]
#    ('spot SYMBOL...' fetches current free prices to size the levels)
python -m scripts.trading_bot.newsdesk spot ethereum XOM

# 3. Freeze + pre-register the proposals (sha256 + UTC, BEFORE the move):
python -m scripts.trading_bot.newsdesk propose proposals.json
#    or log the disciplined abstention:
python -m scripts.trading_bot.newsdesk propose --no-trade "no clean 2:1 read today because ..."

# 4. Mark open setups to realised free prices (run daily; PENDING until horizon elapses):
python -m scripts.trading_bot.newsdesk resolve

# 5. Read the honest scorecard (expectancy vs zero and vs the random-entry null; kill switch):
python -m scripts.trading_bot.newsdesk score
python -m scripts.trading_bot.newsdesk status      # one dashboard line

# hermetic wiring check (no network, no ledger):
python -m scripts.trading_bot.newsdesk selftest
```

Steps 1–3 run **once per day** (the read + the freeze); step 4 runs **daily** to mark any open setup
whose horizon has elapsed. Per the project's no-network-crawls rule, these are one-shot inline pulls;
nothing here crawls.

---

*Frozen instrument. No orders, no real money, no accounts, no purchases, no git commit by the logger;
free/keyless data only, on a fixed host allowlist. The agent is never backtested. Every proposal is a
falsifiable forward commitment; the realised R-multiple is the only evidence, and it is not yet
evidence of anything.*
