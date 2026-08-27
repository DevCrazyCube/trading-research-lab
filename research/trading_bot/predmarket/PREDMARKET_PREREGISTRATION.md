# PREDMARKET PRE-REGISTRATION — the agent-driven prediction-market forward CALIBRATION tracker

**Written and frozen 2026-08-23, before a single forward observation exists.** That timing is the
whole point, and it is even more load-bearing here than for the Newsdesk. An LLM agent is the signal
source, and an LLM's backtest is **structurally poisoned by lookahead**: the model was trained on data
through 2026, so on any *resolved* market it already "knows" who won the election, whether the policy
passed, who got confirmed. Prediction-market outcomes are exactly the discrete, memorable world-facts
an LLM has memorised verbatim. A backtest of an agent's probability estimate on resolved markets
therefore measures **memory, not calibration** — it is worthless. The **only** honest instrument is a
**forward-only** one: the agent reads an OPEN, unresolved market TODAY, **commits its own probability
estimate `q_agent` (sha256 + UTC timestamp) BEFORE the market resolves**, and the outcome is scored
later against the venue's official settlement it could not have seen.

This is a **sibling of the Newsdesk** (`../newsdesk/NEWSDESK_PREREGISTRATION.md`), not a new bot. It
reuses the same discipline — pre-registration freeze, append-only forward ledger, per-observation kill
switch, honest scoring fenced below a minimum sample, and the loud "this is a TRACKER, no bets, no real
money" framing. It differs in exactly two ways: **the instrument is a binary prediction-market
contract**, and **the primary metric is CALIBRATION (agent Brier vs market Brier), not P&L**.

Full scoping and the category ranking, venue/fee facts, and the honest bull/bear case are in
`../prediction_markets_scope.md`. This document freezes the rules of the tracker so the forward log it
governs measures a **realised** calibration edge, not a re-fit or a recollection.

---

## 0. WHAT THIS IS, AND — LOUDLY — WHAT IT IS NOT

This is a **CALIBRATION TRACKER**. An agent reads OPEN politics/policy/soft-news markets, commits 0–N
probability estimates each frozen (sha256 + timestamp) the moment it is proposed and appended to a
pre-registration log **before the market resolves**, and a resolver later reads each market's official
settlement and computes the agent's Brier score against the market's Brier score.

- **NO bets are ever placed** — not live, not paper. There is no wallet, no account, no order endpoint,
  no `submit` mode anywhere in the `predmarket/` package. The only network it touches is a fixed
  allowlist of **free, keyless** public READ hosts (`api.elections.kalshi.com`,
  `gamma-api.polymarket.com`, `clob.polymarket.com`). The authenticated trading hosts
  (`trading-api.kalshi.com`, `demo-api.kalshi.com`) are on an explicit **forbidden** list and refuse.
- **NO real money. NO position. NO account. NO wallet. NO crypto.** Every P&L number in the log is a
  hypothetical: "if the frozen side had been bought at the recorded crossed price and held to the
  official resolution, net of the modeled fee, this is what it would have returned." It is the noisy
  *secondary* metric, never the deciding one.
- **This is a HYPOTHESIS under test, and the honest prior is modest.** The hypothesis is that an
  information-reading agent is *better calibrated than the crowd* on politics/policy/soft-news. The
  candid prior (scope §9) is that the agent is **roughly calibration-competitive but not decisively
  better**, with hypothetical expectancy **pinned near zero by the fee/spread wall.** The forward log
  is the only arbiter. Nothing here is evidence of anything yet.

---

## 1. WHY POLITICS / POLICY / SOFT-NEWS ONLY (scope §7, ranks 1 vs 4–5)

The edge — if any — lives where (a) the price is a **qualitative judgment from reading public info**
(the LLM's comparative advantage), (b) coverage is **thin enough that consensus is sloppy**, and (c)
the crowd is **retail/ideological** rather than quant-made. That is **rank-1: politics / policy /
culture / soft-news events.** Unlike equities there is no HFT contest and the horizon is days-to-weeks,
so "reading the world" has time to be right; and the one robust favorable finding in the literature —
**whales bleed EV to disciplined small informed traders** — applies precisely here.

The tracker **concentrates on rank-1 and skips the efficient categories in code:**

- **Macro / econ prints (CPI, Fed, jobs, GDP, PCE)** — rank 5, the *least* tractable. These already
  track the Reuters professional consensus and are the most professionalised (Susquehanna-made). This
  is the prediction-market analogue of the equities "priced in milliseconds" wall. **Refused.**
- **Crypto price-threshold markets** — rank 4. Driven by the same liquid spot the agent has no edge
  over. **Refused.**

`venues._is_efficient_market` and `proposer.validate_estimate` reject any question matching the
efficient-category keyword set; only politics/policy/soft-news markets can reach the ledger.

---

## 2. THE LOOKAHEAD-PROOF FORWARD-ONLY DESIGN (the assertion that makes this honest)

The one failure this instrument exists to defeat is an LLM "predicting" an outcome it was trained on.
Enforced, not promised:

1. **Freeze precedes outcome.** The moment the agent proposes an estimate, the full spec — venue,
   market id, question, the **market-implied probability `p_market` captured now**, the agent's own
   `q_agent`, the hypothetical side and its edge vs the measured cost, thesis, confidence, the
   market's close/resolution date, and `proposed_utc` — is canonically serialised and
   **sha256-hashed**, then appended to `PREDMARKET_PREREGISTRATION_LOG.jsonl` **before** the market
   resolves. The hash makes the commitment tamper-evident.
2. **The proposer is NEVER run on a resolved market.** `validate_estimate` refuses any market whose
   close/resolution date is not strictly in the future. There is **no** code path that runs the
   proposer on a settled market. A "proof"/selftest mode uses synthetic markets only and never writes
   the ledger.
3. **Resolution reads only the official, strictly-later settlement.** The resolver fetches the venue's
   own settlement (Kalshi `result`, Polymarket resolved `outcomePrices`) and records the YES outcome —
   a world-fact that did not exist at freeze. An estimate stays OPEN until the venue reports a definite
   settlement; a phantom outcome is never fabricated.
4. **Implied probability captured at freeze.** `p_market` is the live mid at read time — a real,
   contemporaneous number; the outcome that scores it is strictly later; there is no window in which
   the future is visible.

---

## 3. THE FREE SOURCES (all verified 200 OK, keyless, from this environment on 2026-08-23)

The tracker pulls only these hosts, on a fixed allowlist; any other host refuses:

| source | endpoint | what it gives |
|---|---|---|
| Kalshi events (nested markets) | `api.elections.kalshi.com/trade-api/v2/events?status=open&with_nested_markets=true` | open markets; category on the event; live prices in `*_dollars` fields |
| Kalshi single market | `api.elections.kalshi.com/trade-api/v2/markets/{ticker}` | official `status` + `result` (settlement) |
| Polymarket Gamma events | `gamma-api.polymarket.com/events?closed=false&tag_slug=politics` | open political events + nested markets, `outcomePrices`, `bestBid/bestAsk`, `spread` |
| Polymarket Gamma market | `gamma-api.polymarket.com/markets/{id}` | resolved `outcomePrices` / `closed` (settlement) |
| Polymarket CLOB | `clob.polymarket.com` | order book / prices-history (keyless read, optional deepen) |

Markets are restricted to **binary Yes/No** contracts with a **live two-sided book** (so an implied
probability and a spread exist) in the **rank-1 categories**. Anything else refuses.

---

## 4. HONEST SCORING — CALIBRATION is the metric (agent Brier vs market Brier)

For each **resolved** market record `(q_agent, p_market, outcome ∈ {0,1})` compute:

- **Brier_agent** = `(q_agent − outcome)²`   and   **Brier_market** = `(p_market − outcome)²`.
- The paired difference **d_i = Brier_market_i − Brier_agent_i** ( `d > 0` ⇒ the agent beat the market
  on market _i_ ).

**PRIMARY question:** after `n ≥ N_min = 50` resolved markets, is the agent's mean Brier **significantly
below** the market's — i.e. is the one-sided lower 95% bound on `mean(d)` above zero:
`mean(d) − 1.645·se(d) > 0`? A **calibration curve** (predicted `q_agent` bucket vs realised YES
frequency) is reported alongside.

**Pre-registered benchmarks:**

1. **The market itself** — agent Brier must beat market Brier (the whole point).
2. **Calibration curve** — the agent's bucketed predicted-vs-realised must be at least as well-behaved
   as its Brier claim implies (no single lucky bucket carrying the mean).

**SECONDARY (noisy, confirming only):** hypothetical bet-expectancy. A bet is logged **only** where
`|q_agent − p_market| > c(venue, p)`, the measured **fee + half-spread** wall (Kalshi ≈ 5–8pp mid-
priced; Polymarket ≈ 1–3pp). On that subset, mean of `(outcome − entry) − fee` for YES buys (NO
sign-flipped), where `entry` is the crossed price frozen from the live book. Binary and low-count, so
it is the *confirming* metric, never the deciding one.

All numbers computed before `N_min` travel inside an `inputs_that_are_not_results` block with the
reason they are not evidence, exactly as BASKET1 and the Newsdesk do.

`N_min = 50` (not 30): resolutions are slow and each carries roughly one bit; a smaller sample cannot
separate a real calibration edge from luck against a market that is already near-calibrated.

---

## 5. THE KILL SWITCH — frozen before any datum

Let `n` be the resolved count, `d` the paired Brier-difference stream, `se = sd(d)/√n`.

> **The tracker is HALTED when, after `n ≥ N_min = 50` resolved markets, the agent's mean Brier is NOT
> significantly below the market's — i.e. `mean(d) − 1.645·se(d) ≤ 0`.**

The agent must **prove** it beats the crowd's probability, or the instrument closes: a
calibration-competitive-but-not-better result (the honest base case) **halts on this rule.** That is
the intended, informative negative. On a HALT the instrument is closed (the ledger is never deleted);
resuming is a NEW frozen instrument, never an edit to this one. No pass verdict is licensed before
`n ≥ N_min`. (If a real-money subset is ever run under owner authorisation, the Newsdesk's P&L rule
`mean_R + 1.645·se < 0` HALTs additionally — but this tracker places no bets and cannot reach it.)

---

## 6. THE DISCIPLINE RULES — enforced in code, immutable once frozen

| rule | value | enforced by |
|---|---|---|
| categories | politics / policy / soft-news only | proposer + venue reader reject efficient macro/crypto |
| forward-only | market close/resolution date strictly in the future | proposer refuses a resolved/past market |
| probability sanity | `q_agent`, `p_market` strictly in (0,1) | proposer rejects out-of-range |
| edge floor (for a hypothetical bet) | `|q_agent − p_market| > c(venue,p)` = fee + half-spread | proposer sets side=abstain below the floor |
| abstention | the default; a sub-cost or no-edge read is frozen for calibration but bets nothing | proposer + `--no-trade` |
| thesis | one-paragraph falsifiable reason tied to the question | proposer rejects a thin thesis |
| settlement | official venue result only, strictly later than freeze | resolver; PENDING until definite |
| venues | Kalshi + Polymarket free READ hosts only | `net.assert_free_host`; trading hosts forbidden |

---

## 7. WHAT MAY AND MAY NOT CHANGE (ITERATION_PROTOCOL, restated)

- **Immutable:** the category concentration, the forward-only assertion, the Brier-vs-market primary
  metric, the edge-floor cost model, the source allowlist, the kill thresholds, `N_min`, the scoring
  definition. Changing any is a **NEW** frozen instrument with a new pre-registration.
- **Maintenance (allowed, logged):** fixing a crash/retry/timeout, a feed URL the vendor itself moved,
  adding a read-only metric to the evaluator, widening the set of political tags/categories the reader
  *scans* (this widens the eyes, not the rules; every estimate is still bound by every §6 rule).
- **Forbidden:** editing a frozen estimate's `q_agent`/`p_market`, running the proposer on a resolved
  market, resolving on anything but the official later settlement, restarting/truncating the ledger,
  reading the calibration verdict before `N_min`, and — above all — **placing any bet, opening any
  account or wallet, or spending any money.** Real-money promotion is owner-gated; this tracker places
  no bets and cannot promote itself.

---

## 8. CLAIMS THIS LOG MAY NEVER SUPPORT

- that the tracker, or any estimate, makes money;
- that the agent is better calibrated than the crowd, before §4's `N_min` is met;
- any Brier, calibration or expectancy statistic computed before the minimum, outside an explicit
  `inputs_that_are_not_results` block;
- that a good early streak is evidence about the edge;
- that this paper log is a reason to fund a Kalshi account or a wallet. **Any real-money step is
  owner-gated and legally constrained** — Kalshi is a lawful US route but real money and owner-gated;
  **Polymarket international is US-illegal**; Polymarket US (QCX) is iOS-only and thin. This instrument
  is a tracker that places no bets — it cannot promote itself.

---

## 9. THE HONEST EXPECTATION, IN ONE PARAGRAPH

The structure genuinely differs from equities — days-to-weeks horizon instead of a millisecond latency
race, a mostly-retail ideological crowd instead of pros pricing everything in — which is why the test
is worth running for $0. But the honest base case (scope §9) is sober: the agent is most likely
**roughly calibration-competitive but not decisively better** than the market in politics/soft-news,
and the fee/spread wall pins hypothetical expectancy near zero and forces heavy abstention. If the
agent cannot clear its own edge floor often enough to even reach `N_min = 50` in reasonable time, that
itself is the negative verdict. This log exists to find out, at the cost of zero dollars and zero bets,
and the honest base case is that it halts on the kill switch — arrived at forward, cleanly, and for
free.

---

*Frozen instrument. No bets, no real money, no accounts, no wallet, no crypto, no purchases, no git
commit by the tracker; free/keyless READ data only, on a fixed host allowlist. The agent is never
backtested. Every estimate is a falsifiable forward commitment; the resolved Brier score is the only
evidence, and it is not yet evidence of anything.*
