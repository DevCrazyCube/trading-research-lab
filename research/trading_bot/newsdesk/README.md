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

---

## FEED HEALTH — DEGRADED for live-session coverage (T41 verdict, 2026-09-01 00:00 CEST)

Measured 2026-08-31 ~22:00 UTC (after the close of a full Monday US session), via
`newsdesk read` per-source enumeration:

| source | last item in pull | live-session items |
|---|---|---|
| SEC_8K | **none in pull** (0 items) | 0 |
| YAHOO_RSS | 2026-08-30 22:25 UTC | 0 |
| GOOGLE_NEWS | 2026-08-30 23:00 UTC | 0 |

Zero items dated either of the two most recent trading days (Fri 2026-08-28 and Mon
2026-08-31); 33 items dated the intervening weekend (listicles/opinion). The feed
delivers stale weekend content and misses trading-day news entirely.

**Consequence (binding on CHUNK C ticks until repaired):** an abstention from this feed
is a PROCESS record, not evidence of "no asymmetric setup today". A propose tick must
first check the pull contains items dated the live session; if not, log the abstention
as **FEED BLIND**, not as a judged no-news day. Repair task: `T42_newsdesk_feed_repair`
in `scripts/agent_graph/agenda.json`.

**Addendum (2026-09-01 06:00 CEST tick, measured 04:05 UTC):** the blindness is
narrower than the T41 table suggested. This overnight pull contained **39/60 items
stamped within the previous ~4 hours** (Mon 31 Aug evening ET, post-close: the AMZN FTC
suit, the Apple CEO handoff, TSLA HK, AVGO earnings previews) — so an early-UTC read
DOES see fresh post-close/overnight news and can render a JUDGED abstention/proposal.
What remains broken: **SEC_8K = 0 items in every pull so far**, and **zero items
timestamped during the intraday session itself** (the T41 gap — RSS publish times
cluster in the evening). Scope T42 to (a) the dead SEC 8-K feed and (b) intraday-hour
coverage, not to a wholesale rebuild; and time propose ticks that want freshness to
early-UTC hours, where the feed is demonstrably live.

## FAULT + FIX 2026-09-02 (CHUNK C tick, 18:00 CEST) — the eyes were reading the wrong day

`world_reader.read_world()` ordered the merged event stream with
`events.sort(key=lambda e: e["ts"], reverse=True)` — a **raw string sort over two incompatible
timestamp formats**. The RSS feeds (Yahoo, Google News) emit RFC-822 (`"Wed, 02 Sep 2026 15:33:00
+0000"`); SEC EDGAR emits ISO-8601 (`"2026-09-02T15:02:44-04:00"`). Two consequences, both silent:

1. **Ordered by weekday name, not by time.** Reverse-lexicographic on `"Wed" > "Tue" > "Thu" > ...`
   put a 2026-07-29 item at the *top* of the 2026-09-02 stream. The first ~60 rows the proposer brain
   ever saw were up to five weeks stale.
2. **The SEC 8-K feed was invisible.** ISO strings start with a digit, which sorts below every
   letter-prefixed RFC-822 string, so all 40 8-Ks — the only hard, non-commentary feed — landed at the
   very bottom, past the default `--limit 60`. Every newsdesk tick since the 2026-08-23 freeze
   proposed without ever seeing a single material-event filing.

**Fix (this tick):** added `_ts_utc()` (ISO via `fromisoformat`, RFC-822 via
`email.utils.parsedate_to_datetime`, naive→UTC, unparseable→sorts last, never dropped), added a
normalized `ts_utc` field to every event, and sort on the parsed datetimes. Verified: post-fix the
top-120 window is entirely within the last hour and the 8-K feed is present. `newsdesk selftest`
→ `ALL_PASSED: true`.

**Scope:** this touches the READING surface only. Event `id` is `sha256(source|headline|link)` and
does not include the timestamp, so ids are stable and the existing ledger references still resolve.
No frozen rule, no proposal, no resolution and no scoring path was modified.

**Scoring caveat — a regime break, not a retraction.** Every proposal frozen *before*
2026-09-02T16:00Z was generated from the stale-ordered stream; post-fix proposals come from a
materially different input distribution. Those are two regimes and **must not be pooled naively**.
The pre-fix rows stay in the ledger (they were honestly forward-frozen and the freeze-before-outcome
property is intact) — but the running expectancy (−0.474R over 2 resolved of 30) is now a number
about a *broken* reader, and the forward clock on the hypothesis-as-intended effectively starts here.

**Second, unfixed caveat — `tickers` is feed attribution, not subject attribution.** Yahoo's
per-ticker RSS returns generic syndicated content, so items are tagged with the feed they came from,
not what they are about: on 2026-09-02 a Fulton Financial dividend screen was tagged `META`, a
Netcompany shareholder notice `NVDA`, a FORVIA buyback `AMZN`. The proposer must read the headline,
never the tag. Left as-is rather than guessed at; recorded so it is not mistaken for signal.

## FAULT + FIX 2026-09-03 — false ticker attribution (second data-path fault)

`world_reader.read_yahoo_headlines()` pulls Yahoo's **per-ticker** headline RSS across the 18-name
frozen watchlist and tagged every returned item with the ticker whose feed it came from. That feed
returns general market news, so the tag was *subscription provenance*, not attribution. Measured on
the live 2026-09-03 00:00 pull: **10 of 19 ticker tags were false (53%)** — e.g. "Why Goldgroup
Mining Stock Soared" tagged NVDA, "Broadcom's Outlook Weighs on Stock" tagged GOOGL while AVGO went
untagged.

`tickers` is the join key between a headline and the tradable universe — what the proposing agent
reads to decide which instrument a story is about — so a false tag invites a frozen proposal on a
name that had no news. Nothing outside `world_reader` consumes the field, so the blast radius is the
agent's discretionary read (which is the entire instrument).

**Fix, reading surface only:** subscription provenance moves to a new `feed_ticker` field; `tickers`
now means *mentioned* and survives only on a word-boundary symbol match or a company-name alias
(`_TICKER_ALIASES`). Event ids `sha256(source|headline|link)` are unchanged, so all ledger references
still resolve; no frozen rule, proposal, resolution or scoring path was touched. `selftest` gains
`ticker_attribution_verified` → ALL_PASSED. This lands inside the not-yet-scored 09-02 regime, so no
additional regime break is stamped; the 09-02 pre/post pooling ban still stands.
