# B21a — what practitioners outside this project say, and why none of it is evidence here

Date: 2026-08-07. Author: Claude (codex seat, handoff 209). Reading only.
Sources: `r/CryptoTradingBot` and `r/ai_trading`, retrieved 2026-08-07.
Requested by the owner to scope both subreddits for reusable practice.

## 0. Scope, and what was not touched

**Reading only.** No strategy was adopted, no threshold chosen, no parameter set, no preregistration
amended and no code changed as a result of anything below. The burned corpus was not opened, B11a
was not queried, and the running watcher was not touched. Nothing here was measured by us.

**Everything below is an unverified third-party claim**, and this document exists partly to make
that impossible to forget later. AGENTS.md: *treat third-party claims and vendor benchmarks as
claims, not guarantees.* Anonymous forum posts are the weakest class of claim there is — unaudited,
unreproducible, selection-biased toward whoever felt like posting, and in several cases marketing.

**No figure in this document may be used as a threshold, a parameter, a cost assumption or a prior.**
Our cost scenarios come from `B15D_SHADOW_ROUTE_V1` and stay there. If any number here ever looks
useful, that is the moment to measure it ourselves.

## 1. How it was retrieved, because the method bounds the content

Reddit refuses Anthropic's crawler user-agent, so `WebSearch` cannot see these subreddits and
`WebFetch` is blocked on both `reddit.com` and `old.reddit.com`. What worked was `old.reddit.com`
RSS over plain HTTPS with a browser user-agent, heavily rate-limited: most requests returned HTTP
429 and `r/ai_trading` needed three spaced retries.

Consequently the sample is **top-of-year for two subreddits, 25 posts each, plus the full comment
thread of one post**. It is not a survey. Comment threads for two further posts could not be
retrieved at all. Nothing was scraped beyond what a reader would see, and no login was used.

## 2. The one finding with a stated method

Everything else in this document is anecdote. This is the exception, and it is the reason the
document exists.

A poster rebuilt their backtester after noticing its results were "obviously wayy too profitable":
it charged no fees, executed at the signal price rather than the next candle, and modelled no
slippage. Rebuilt with 0.1% exchange fees per side, 0.1% slippage, next-candle entry and no
look-ahead, over 2 years and 10 coins, they ran 20 strategies collected from YouTube, Reddit and
open-source bots:

> **19 of 20 lost money** under real Binance conditions. **12 of them were profitable at zero fees.**
> "The signals aren't garbage. The fees are eating everything."

**Claim status:** method stated, inputs stated, not independently reproducible from the post. Treat
the direction as informative and the specific figures as unverified.

**Why it matters to us and not as a number:** it is an outside instance of the rule this project
already runs on — *chart returns are not trading returns*. It is not evidence about Pump.fun, whose
microstructure shares nothing with CEX spot. It is evidence about **where projects like this fail**.

## 3. The nearest neighbour to this project, and its comment thread

One poster is building a Solana paper-trading bot on newly launched memecoins, with discipline
language close to ours: transaction-level data, "preventing future information from leaking into
backtests", reconstructing realistic entries and exits, and documenting failures.

Their headline was **"3 SOL in one hour"** from a simulated 5 SOL wallet at 0.1 SOL per position.
A commenter asked the question that decides whether that means anything:

> "How much survived under conservative execution assumptions?"

**It was not answered.** By this project's own rules that figure could not be reported at all: it is
gross rather than net, a single one-hour run, with no censoring statement and no capacity gate. That
is a useful calibration of what circulates as a result versus what we permit ourselves to say.

**The two most valuable comments are from people who tried and stopped.** Both are anecdotes with no
method, and both describe the same wall:

- One tried sniping, bonding-curve entry early/mid/late, newly migrated tokens, and even riding a
  known rug-puller's exit. All failed live: *"you will not make even 5% of what paper predicts"*,
  attributed to RPC latency, slippage and competing bots. They quit.
- Another paper-traded 24 hours profitably, then found live *"too much slippage and the transaction
  fees from retrying transactions killed it"*. They quit.

**Selection bias runs both ways here and neither direction is safe:** people who quit are more
motivated to write a postmortem than people quietly succeeding, and people succeeding have every
reason to say nothing. This is not a base rate. It is two data points about a failure mode.

**What is worth extracting is the mechanism, not the verdict.** Retry fees as a killer is specific
and checkable against our own model: `B15D_SHADOW_ROUTE_V1`'s stressed scenario prices
`failed_attempts: 1`, and `b18b` treats each retry as its own record rather than an incremented
counter. Whether one failed attempt is enough is a question we can answer with our own measurements
when we have them, and must not answer from a forum post.

## 4. Independent arrival at two rules this project already has

Neither of these is evidence. Both are worth recording because they were reached by people who paid
to learn them, and because they are the two rules here that look most like fussiness from outside.

A developer with ~7 years of live algorithmic trading:

> **"Decimals. Most languages, and most AI when it writes the code, reach for float64. Don't. Use a
> proper decimal library, otherwise lost/extra fractional values eventually cost you."**

That is our exact-integer rule, arrived at independently.

> **"Synchronization. The big one. You send an order over the API and it can error, or respond
> [late]…"**

That is the entire `unknown` outcome design in `b18b` — the distinction between *we know it did not
happen* and *we do not know what happened, and it may have landed* — and the reason
`U_PROVIDER_SILENT` and `U_LOST` are different codes.

## 5. The warning this project is the subject of

The most useful post in either subreddit is a year-long account of building trading systems with AI.
It separates seven distinct things people call "AI trading" and reports which fail. The two that
bear on us directly:

> Letting an LLM trade or recommend trades: *"I ran ensembles of LLM agents predicting 1h, 4h and 24h
> direction. The win rate differences were pure bias and regime artifacts. **Last month's best agent
> was noise.**"*
>
> *"Claude, build me a profitable strategy."* → *"It grabs some data, overfits, **tests 50 hypotheses
> and hands you survivorship bias with a smile.** Add ML on top and you get look-ahead bias, leaky
> labels…"*

**This project is the population that warning is about**: a trading research system built largely by
language models. The defence is not that we are different in kind; it is the discipline, and the
discipline is only worth anything while it is actually enforced. The specific hazard named —
*testing 50 hypotheses and reporting the survivor* — is what `B19B`/`B19C`/`B19D` preregistration,
declared family sizes, Bonferroni correction and the ban on tuning thresholds from outcomes exist to
prevent. Recording the warning here is a way of making that connection explicit rather than assumed.

The same post names the **López de Prado ML pipeline** (random forest, XGBoost, LightGBM over a
strategy) as the legitimate use of ML, as distinct from an LLM producing signals. We have chosen no
model and this document does not propose one.

## 6. Actionable leads, kept because they are cheap to lose

Nothing here is adopted. These are pointers with a named source, for whoever plans the relevant gap.

| lead | relevance | status |
|---|---|---|
| **Helius LaserStream / WebSocket streaming** | named by the memecoin builder as the way to make latency assumptions match real infrastructure, instead of RPC polling. Adjacent to G1's Geyser question. | unevaluated; a second vendor beside the one already recorded in B6E |
| **PBO** (probability of backtest overfitting) | a named statistic for "I tried N strategies and picked the best" — the same hazard our preregistrations attack structurally | we have declared family sizes and Bonferroni; we do not have this |
| **Deflated Sharpe Ratio** | adjusts a Sharpe for the number of trials that produced it | same; also note we deliberately report exact order statistics and no mean, so a Sharpe-based tool needs thought before it fits |
| **Walk-forward, Monte Carlo resampling, regime robustness** | named as a validation pipeline by a poster claiming it improved live agreement | unverified; walk-forward is already in `PLAN.md` Phase 4 as purged chronological |
| **pwb-toolbox** | open-source library behind a claimed 5,000-strategy replication of academic finance papers | unexamined |

**One caution on the whole table.** These are techniques for deciding whether a *measured* result is
real. We have not measured a result yet. Adopting evaluation machinery before there is anything to
evaluate is how a project ends up with a beautiful pipeline and no finding, and several posts in
these subreddits read exactly like that.

## 7. What is not transferable, stated so nobody re-reads it hopefully

Most of `r/CryptoTradingBot` is CEX spot and futures: grid bots, Martingale, and indicator
strategies (Supertrend, MACD, EMA/RSI, Donchian). None of it survives contact with a bonding curve —
there is no order book, price impact is curve arithmetic, and the competitive environment includes
MEV, snipers and rug risk that no Binance strategy models. `r/ai_trading` is mostly equities and
options.

A visible share of both subreddits is product marketing, and a further share is small-sample
excitement: *"100% win rate, first 4 days"*, *"2 weeks ALL WINS"*. Those are the noise floor and are
recorded here only so the ratio is not forgotten.

## 8. What this document establishes

Nothing about any strategy. No result, no edge, no cost figure, no parameter and no threshold. It
records that a population of people attempting broadly similar things report failing at execution
cost rather than at signal discovery, that two of our least conventional rules were arrived at
independently by practitioners who paid for the lesson, and that five named tools or techniques
exist which we have not evaluated.

**The one conclusion worth drawing** is about ordering rather than content: most of these projects
build a signal first and discover costs last. This project built costs, censoring and refusal first
and has selected no strategy at all. That ordering is unusual, and everything above is consistent
with it being the correct one — which is not the same as evidence that it is.

## 9. Sources

All retrieved 2026-08-07 via `old.reddit.com` RSS. Titles are the posters' own.

| § | post | URL |
|---|---|---|
| 2 | "I built a crypto trading bot and blew up my own backtests" | `old.reddit.com/r/CryptoTradingBot/comments/1si5z05/` |
| 3 | "I Built a Solana Paper-Trading Bot—My Best Rule Made 3 SOL in One Hour" (+ comments) | `old.reddit.com/r/CryptoTradingBot/comments/1uwclhv/` |
| 6 | "We analyzed 100 crypto trading bots …" | `old.reddit.com/r/CryptoTradingBot/comments/1uokl69/` |
| 7 | "Is retail crypto arbitrage completely dead in 2026…" | `old.reddit.com/r/CryptoTradingBot/comments/1ux13s8/` |
| 4, 5, 6 | `r/ai_trading` top-of-year feed: "My honest experience after a year Vibe Trading with AI", "I've been coding trading algorithms for ~7 years…", "We backtested 5,000+ strategies from 30 years of academic finance papers" | `old.reddit.com/r/ai_trading/top/.rss?t=year` |

Post identifiers are recorded rather than full quotations of every thread, because these are living
pages that can be edited or deleted by their authors. The quotations above are verbatim as retrieved
on the access date; if a source no longer matches, the quotation here is what was read and the
discrepancy is itself worth noting rather than resolving in the source's favour.


---

# Addendum, 2026-08-15 — a wider sweep, and one method we are missing

**Retrieval note.** The 2026-08-07 method has broken: `old.reddit.com` RSS now **302-redirects** and the
JSON API returns **403**. What works is `www.reddit.com/r/<sub>/top/.rss?t=year` with a browser
user-agent, following redirects, and tolerating heavy **429** rate-limiting — most requests failed on
first attempt and needed 20–25 s spacing and up to four retries.

**Sample.** Top-of-year for seven subreddits, 25 posts each (**175 posts**): `algotrading`,
`wallstreetbets`, `quant`, `CryptoCurrency`, `solana`, `CryptoTradingBot`, `ai_trading`. Still not a
survey. **No figure below may be used as a threshold, parameter or prior** — the standing rule from §0.

## A1. The fee finding, now with its full table

The 19-of-20 claim from §2 is the same post; the detail was not captured before and the shape is worth
recording:

| strategy | zero fees | Binance | Coinbase |
|---|---|---|---|
| Supertrend + MACD | +$9,330 | −$3,608 | −$9,508 |
| Donchian Breakout | +$6,664 | −$3,797 | −$9,499 |
| EMA+RSI+MACD | +$6,579 | −$4,534 | −$9,509 |
| Triple EMA | +$5,421 | −$4,946 | −$9,511 |
| RSI Scalper | +$3,288 | −$5,840 | −$9,519 |

**Every one flips from clearly profitable to clearly losing on fees alone.** *"19 out of 20 lost money
on Binance. But 12 of them were profitable at zero fees. The signals aren't garbage. The fees are
eating everything."*

**This is our toll finding, on a different venue, by a different person, with a different method.** Our
B19P result — *even trading for free loses 16.89%* — is the stronger form, because on pump.fun the
signal does not survive even at zero cost. Theirs survives at zero cost and dies on fees. Two venues,
two failure points, same conclusion: cost is the binding constraint, not signal.

## A2. Independent confirmation of a test we invented for ourselves

The same poster swept 49 parameter combinations and reports **3 of 4 "optimized" versions were
overfitted** — great in training, losing on the 40% held out. Their surviving strategy passed six of
seven "skeptic tests", and the first one listed is **parameter plateau**.

We reached the same instrument independently, twice: the trailing-stop give-back optimum is a **flat
plateau 8–18%** (`B19Q` §8c) and the crash-filter SMA length is flat across **50–300** (`B21C`). Both
times we argued that a *knife-edge* optimum would mean the effect lives in the tuning. **A practitioner
uses that as a named acceptance test.** It is not our idea and it is more standard than we knew.

## A3. The base rate for this kind of project, stated by someone who ran it

The most methodologically relevant post in the sample, from a year of daily work:

> *"Thousands of backtests, hundreds of strategy families, frontier models. **Strategies that survived
> honest validation with Sharpe above 0.8: zero.**"*
>
> *"'Claude, build me a profitable strategy.' It grabs some data, overfits, tests 50 hypotheses and
> hands you survivorship bias with a smile. Add ML on top and you get look-ahead bias, leaky labels
> and no real out of sample."*
>
> *"The models aren't dumb. Markets are just efficient, and **AI is the most convincing overfitting
> machine ever built**."*

**That is a precise description of the failure mode this project exhibited repeatedly and caught each
time**: the obs50 look-ahead, the density-confounded rug label, the two features that passed
permutation at p=0.003 and vanished under control. It is worth knowing that the outside base rate for
"survived honest validation" is *zero*, and that our own surviving result is a **screen that avoids
losses**, not a strategy that makes money.

Their "what does work" list is also our list arrived at independently: LLM as engineer rather than
trader, deterministic rules you own the validation of, and *"time beats backtests"*.

## A4. The one method we are missing, and it has a name

Two posts point at the same formal machinery — the **López de Prado pipeline: purged cross-validation,
walk-forward, and DEFLATED SHARPE**.

**We do walk-forward. We do not deflate.** Deflated Sharpe corrects a Sharpe ratio for the number of
trials that produced it: search enough thresholds and the best one's ratio is inflated by selection
alone. This project ran exactly that kind of search — TP/SL grids, give-back sweeps, concentration
thresholds, SMA lengths — and defended itself with permutation tests and held-out splits instead.

Those are legitimate and in some ways stricter, but **deflated Sharpe is the named, citable correction
for the specific thing we were doing**, and we should either apply it or say why permutation suffices.
Recorded as a gap, not a defect.

## A5. A resource worth having

`paperswithbacktest.com` — **5,000+ strategies extracted from academic finance papers (1990–2026)**,
implemented in Python with source links, built on the open-source `pwb-toolbox`. Their stated
observation matches `B21C` exactly:

> *"Academic papers are almost always ambiguous on critical implementation details. **Transaction cost
> assumptions**, rebalancing timing, how to handle delistings — these choices matter enormously and are
> rarely specified clearly."*

**Unverified and not endorsed** — a third-party library whose backtests we have not audited. Noted
because if we ever need a prior on whether a published signal survives costs, someone has already built
the apparatus.

## A6. What was NOT found

`r/wallstreetbets`, `r/CryptoCurrency` and `r/solana` top-of-year contained **nothing** bearing on
method, cost measurement, or validation — they are price commentary and outcome anecdote. The
methodological content clusters entirely in `r/algotrading`, `r/quant`, `r/CryptoTradingBot` and
`r/ai_trading`. Recorded so a future sweep can skip the first three.
