# PREDMARKET — the $0 forward CALIBRATION tracker for prediction markets

**A sibling of the Newsdesk (`../../scripts/trading_bot/newsdesk/`), not a bot and not a bet.** It asks
one honest question: **is an information-reading agent BETTER CALIBRATED than the crowd on
politics/policy/soft-news prediction markets?** It measures that forward, for **$0**, with the same
freeze → append-only ledger → forward-only resolve → honest-scoring discipline the programme already
runs — and with a metric (calibration, not P&L) that is measurable at zero cost on free official
settlements.

> **Places NO bets. Holds NO position. Touches NO account, wallet, or real money. Free keyless public
> READ data only, on a fixed host allowlist. No git commit by the tracker.**
> Any real-money step (a Kalshi account, funds) is **owner-gated and legally constrained** — see §6.

Full scoping (category ranking, fee/spread wall, the Brier-vs-market metric, endpoints) is in
`../prediction_markets_scope.md`. The frozen rules and kill switch are in
`PREDMARKET_PREREGISTRATION.md` (hash-pinned into `PREDMARKET_FROZEN.json`).

---

## Why calibration, not P&L (the honest framing)

The programme's equities work died on a clean wall: *free data can't beat pros who price news in
milliseconds.* Prediction markets change the losing mechanism in two ways — the horizon is
**days-to-weeks** (a read has time to be right, not a latency race), and the crowd is
**mostly-retail/ideological** (the one robust favorable finding in the literature is that whales bleed
EV to disciplined small informed traders). That is a genuinely different, more favorable structure —
worth a cheap forward test rather than assuming the answer.

But the **fee/spread wall** (scope §4) makes P&L a poor primary metric: to profit on a mid-priced
Kalshi contract you need to be **5–8pp off the market and right, every bet**; on Polymarket 1–3pp.
That forces heavy abstention and pins realised expectancy near zero. So the **PRIMARY metric is
CALIBRATION**: when a market resolves, is the agent's **Brier score** `(q_agent − outcome)²` **below**
the market's **Brier score** `(p_market − outcome)²`, paired across markets, at one-sided 95% after
`N_min = 50` resolved markets? That is the honest analogue of "better probability estimates than the
crowd," and it is free to measure. Hypothetical bet-expectancy net of fees is logged as a **noisy
SECONDARY** only.

## Why politics / policy / soft-news ONLY

The edge (if any) lives where the price is a **qualitative judgment from reading public info** (the
LLM's comparative advantage), coverage is **thin enough that consensus is sloppy**, and the crowd is
**retail** not quant-made — i.e. scope **rank-1: politics/policy/culture/soft-news.** The tracker
**skips the efficient categories in code** (scope ranks 4–5): **macro prints** (CPI/Fed/jobs/GDP/PCE)
already track the Reuters consensus and are the most professionalised — the prediction-market analogue
of "priced in milliseconds" — and **crypto price-threshold** markets are driven by liquid spot the
agent has no edge over. `venues._is_efficient_market` + `proposer.validate_estimate` refuse both.

## The lookahead trap, and how it is defeated

An LLM was trained through 2026 and has **memorised** how resolved markets turned out. Scoring an agent
on resolved markets measures memory, not calibration — worthless. So:

1. **The proposer is NEVER run on a resolved market.** `validate_estimate` refuses any market whose
   close/resolution date is not strictly in the future.
2. **Freeze precedes outcome.** Each estimate — venue, market id, question, `p_market` captured now,
   `q_agent`, side/edge/cost, thesis, `proposed_utc` — is sha256-hashed and appended to
   `PREDMARKET_PREREGISTRATION_LOG.jsonl` before the market resolves. The hash is re-verified on every
   `resolve`/`score`; a tampered `q_agent` refuses the whole run.
3. **Resolution reads only the official, strictly-later settlement** (Kalshi `result`, Polymarket
   resolved `outcomePrices`). An estimate stays PENDING until the venue reports a definite outcome.

---

## Architecture (mirrors the Newsdesk package)

```
scripts/trading_bot/predmarket/
  __init__.py     Refused; the loud "tracker, no bets, no money" framing
  net.py          host-allowlisted, polite, READ-ONLY GET; trading hosts explicitly forbidden
  frozen.py       load + verify the frozen spec (refuses if the prereg md hash moved); canonical sha256
  venues.py       pull OPEN politics markets from Kalshi + Polymarket; normalize; the fee/spread cost model
  proposer.py     validate + freeze an estimate; forward-only + probability + edge-floor + thesis enforcement
  ledger.py       two append-only JSONL logs + state; hash re-verification
  resolve.py      forward-only settlement reader; Brier(agent) vs Brier(market) + hypothetical P&L net of fee
  scoring.py      paired Brier-vs-market (one-sided 95%) + kill switch + calibration curve; fenced below N_min
  selftest.py     hermetic wiring check (no network, no ledger)
  __main__.py     CLI: selftest | pull | propose | resolve | score | status
research/trading_bot/predmarket/
  PREDMARKET_PREREGISTRATION.md   frozen rules (hash-pinned)
  PREDMARKET_FROZEN.json          machine spec: venues, cost model, kill switch (N_min=50), allowlist
  PREDMARKET_PREREGISTRATION_LOG.jsonl   append-only: every frozen estimate + abstention
  PREDMARKET_RESOLUTION_LOG.jsonl        append-only: every official settlement
  PREDMARKET_STATE.json                  convenience index (logs are the source of truth)
```

### Free, keyless READ sources (verified live 2026-08-23)

| venue | endpoint | role |
|---|---|---|
| Kalshi | `api.elections.kalshi.com/trade-api/v2/events?status=open&with_nested_markets=true` | open markets; category on event; prices in `*_dollars` fields |
| Kalshi | `api.elections.kalshi.com/trade-api/v2/markets/{ticker}` | official settlement (`status`+`result`) |
| Polymarket | `gamma-api.polymarket.com/events?closed=false&tag_slug=politics` | open political events + nested markets, `outcomePrices`, `bestBid/bestAsk`, `spread` |
| Polymarket | `gamma-api.polymarket.com/markets/{id}` | official settlement (resolved `outcomePrices`/`closed`) |
| Polymarket | `clob.polymarket.com` | order book / prices-history (keyless, optional deepen) |

The authenticated trading hosts (`trading-api.kalshi.com`, `demo-api.kalshi.com`) are on an explicit
**forbidden** list in `net.py` and refuse loudly — no order/wallet surface is reachable from here.

---

## Daily run command

```bash
# 1. wiring check (no network)
python3 -m scripts.trading_bot.predmarket selftest

# 2. pull today's OPEN politics/soft-news markets + live implied probability (eyes)
python3 -m scripts.trading_bot.predmarket pull --min-volume 20000 --limit 40

# 3. the agent reads the candidates, writes estimates.json (see the format below), then FREEZES them:
python3 -m scripts.trading_bot.predmarket propose estimates.json
#    ...or log a disciplined abstention (the default skill):
python3 -m scripts.trading_bot.predmarket propose --no-trade "why nothing cleared the edge floor today"

# 4. settle any newly-resolved markets against official outcomes (forward-only)
python3 -m scripts.trading_bot.predmarket resolve

# 5. the honest scorecard (Brier agent vs market; no verdict before N_min=50)
python3 -m scripts.trading_bot.predmarket score        # full report
python3 -m scripts.trading_bot.predmarket status       # one line
```

**Estimate JSON** (one object or a list): `venue`, `market_id`, `question`, `p_market` (mid captured
now), `q_agent` (the agent's own probability), `close_time`, `yes_bid`, `yes_ask`, `spread`, `thesis`
(one paragraph), `confidence`, optional `event_refs`. The proposer computes the round-trip cost from
the live book and sets the hypothetical side to `yes`/`no` only if `|q_agent − p_market|` clears it —
otherwise `abstain` (still frozen for calibration).

---

## The honest expectation (pre-registered base case)

Roughly **calibration-competitive but not decisively better** than the market on politics/soft-news,
with hypothetical expectancy pinned near zero by fees. On the kill switch (§5 of the prereg) that base
case **HALTS**: the agent must *prove* it beats the crowd's Brier at `N_min = 50`, or the instrument
closes. That is the intended, informative negative — arrived at forward, cleanly, and for **$0**, with
a structure that genuinely differs from the equities dead end. If the agent cannot even clear its own
edge floor often enough to reach `N_min` in reasonable time, that itself is the verdict.

## §6 — the real-money gate (owner-gated, legally constrained)

This tracker cannot promote itself; it places no bets. **Any** real-money step is owner-gated:

- **Kalshi** is the clean *legal* route (CFTC-regulated US exchange) but is **real money and squarely
  owner-gated** (KYC, funded USD account) — the BASKET1/Newsdesk order-gate pattern.
- **Polymarket international is NOT lawfully usable by US persons** (geoblocked since the 2022 CFTC
  settlement). It is read-only here for implied-probability/settlement data; funding it is a legal
  no-go for a US owner.
- **Polymarket US (QCX)** is the lawful US alternative but iOS-only, newer, thinner, with state bans
  emerging. Capacity in the beatable categories is a few hundred dollars per market at most.

Even a *positive* forward result promotes only to a small real probe, and only through the owner's
real-money gate.
