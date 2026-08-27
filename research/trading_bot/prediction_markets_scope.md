# PREDICTION MARKETS — scope & recommendation: is "reading the world" a real edge here?

**Research/recommendation only. No bets, no accounts, no wallet, no money, no orders, no git commit by
this document. Free public data + small verification fetches only.** Written 2026-08-23.

This is the sibling question to the Newsdesk (`newsdesk/NEWSDESK_PREREGISTRATION.md`). The Newsdesk's
own honest prior is brutal and correct: *"public news is priced into liquid instruments within
seconds, so a free-feed agent reading a headline is almost always late, and the honest expectancy is
≈ 0."* That is the equities verdict, and it is why 0-for-8 directional and the free-data convexity wall
happened. **Prediction markets are worth a separate look precisely because the losing mechanism is
different.** A prediction market does not resolve in milliseconds off a tape an HFT already read — it
resolves on a **future event days-to-weeks out**, and the price is a **probability estimate** that a
mostly-retail crowd is forming from public information. The question this doc answers: is that a real,
tractable edge for an information-reading agent, or another "real but too small / already sharp" dead
end? **Verdict up front in §9. Short version: narrowly yes — worth a $0 forward calibration tracker —
but with a fee/spread wall that demands a large true edge, and a professionalisation clock running
against the only categories that are liquid.**

---

## 1. THE VENUES — data access, fees, liquidity reality

| venue | legal/regulatory | free API for live + historical prices | fee / spread | liquidity reality |
|---|---|---|---|---|
| **Kalshi** | **US-regulated, real legal exchange** (CFTC-designated DCM) | **Yes, fully public.** REST + WebSocket + FIX. No subscription, no per-request charge, no data fee. OpenAPI/AsyncAPI specs published. Order books, trades, all market data keyless-readable. | **Trading fee** `ceil(0.07·P·(1−P)·100)/100` per contract, taker; **~25% of that for makers**. Peaks at 50¢ ($0.0175/contract → **3.5¢ round-trip on a $1 payout**), → ~0 at the extremes. **Spread 3–8¢** typical. | Strong at peak/headline moments, **patchy on the long tail**; empty books = untradeable. Institutionally judged "too thin." |
| **Polymarket (international)** | **US-blocked** since the 2022 CFTC settlement ($1.4M fine, must block US persons). Crypto/USDC on Polygon, global. | **Yes, three public read APIs:** Gamma (market discovery), CLOB (`/prices-history`, order book, keyless read), Data (public activity), **plus a subgraph on The Graph** (wallet-level trades, resolutions). Rate limits ~60/min Gamma, ~100/min CLOB. | **0% trading fee on most markets.** **Spread 2–5¢** typical (tighter than Kalshi; crypto-native book deeper on the tail). Real cost = spread + gas + USDC on/off-ramp. | Largest volumes; **hundreds of niche markets, many thin.** Sharp-trader arb has historically paid ~$40M to sophisticated participants. |
| **Polymarket US (QCX LLC)** | **CFTC-regulated, launched Dec 2025**, the only Polymarket product US persons may lawfully use. iOS-only, waitlist removed May 2026; web/Android pending. State bans emerging (Minnesota, Aug 1 2026, in litigation). | Same API family as international (public read). | ~as Polymarket. | Newer, thinner than international. |
| **PredictIt** | US, legal under a (contested) CFTC no-action posture | Limited/quasi-public data | **Punitive: 10% on profits + 5% on withdrawals; $850 cap per contract position.** | Tiny, capped. **Not viable** for anything but a curiosity. |
| **Manifold** | Play-money (**"mana", not real currency**) | Public API | No real money at stake | **Best free calibration sandbox** — real crowd, real forward resolution, $0 by construction. No P&L meaning, but honest for measuring an agent's calibration vs a crowd. |

**Data conclusion:** Kalshi and Polymarket both give **free, keyless, live + historical** price/resolution
feeds — strictly better data access than the equities work had, and both are addable to the Newsdesk's
fixed host allowlist as **read-only** sources with zero account. Manifold is a free real-crowd
calibration target. **The data is not the constraint here.** The constraints are fees, liquidity, and
legal access to real money.

---

## 2. THE EDGE THESIS — real, or already arbitraged? (honest, both ways)

### Evidence the markets are inefficient (the bull case)
- **Favorite-longshot bias is the single most robust finding in the literature.** Longshots are
  systematically overpriced, favorites underpriced. Concrete: a football study shows **−3.64% average
  return on favorites vs −26.08% on underdogs**; on Kalshi, **contracts bought under 10¢ lose >60% of
  stake.** Betting favorites / fading longshots is a documented, fee-survivable behavioral edge *by
  design*.
- **The genuinely encouraging finding: whales bleed to small traders.** Tick-level Polymarket/Kalshi
  research finds the **most-capitalized traders systematically UNDERPERFORM small-order traders** —
  whales trade on ideological conviction and eat adverse selection. The classic bias is largely a
  **"Yes bias"** (traders overpay for the affirmative). "The loudest participants add no edge." **This
  is the one finding that directly favors a disciplined, non-ideological, information-reading small
  participant** — which is exactly what an LLM agent with an enforced discipline layer is.
- **The markets are thin and news-driven**, with hundreds of niche long-tail contracts under light
  coverage — structurally the opposite of the equities case where pros price everything in ms.

### Evidence the markets are (becoming) efficient (the bear case — and it's strong and fresh)
- **Professionalisation is happening FAST, right now (Aug 2026).** Susquehanna has been Kalshi's
  **flagship market maker since 2023**; DRW and Jump are building prediction-market desks; and on
  **2026-08-19 Cantor Fitzgerald + Susquehanna opened institutional block trading on Kalshi** to ~3,000
  clients, with CNBC reporting hedge funds "about to jump in big." The quant firms are explicitly
  hunting **arbitrage**, not directional bets — but their market-making tightens exactly the liquid
  categories.
- **The headline macro/econ markets are already efficient.** For Kalshi CPI/Fed contracts, research
  finds **"lagged Reuters surprises do not predict systematic deviations of the Kalshi mean from the
  current Reuters consensus"** — i.e. these markets already track the professional consensus and
  incorporate news. Fed-hold and CPI-threshold prices matched outcomes "for days" ahead. **The most
  watched, most liquid, most obviously "news" category is the LEAST beatable.** This is the direct
  analogue of the equities "priced in ms" wall.
- **Arbitrage edges are real but not an LLM-read edge.** Inter-exchange (Kalshi↔Polymarket) spreads
  exist but **last seconds-to-minutes and need automated cross-venue execution + capital**; intra-market
  "prices don't sum to $1" arb is real but is a scanner/execution game, not a world-reading game. These
  belong to the quants, not to an agent reading news.
- **The bias is weakening.** The 2025 favorite-longshot coefficient is smaller and less significant —
  consistent with maturation as volume grows.

### Where an LLM-agent read could plausibly have an edge — by category
The edge lives where (a) the price is a **qualitative judgment from reading public info** (LLM's
comparative advantage), (b) coverage is **thin enough that consensus is sloppy**, and (c) the crowd is
**retail/ideological** rather than quant-made. That is emphatically **not** the macro/crypto headline
markets. See the ranking in §7.

---

## 3. THE LOOKAHEAD TRAP — confirmed identical to the Newsdesk, and if anything worse

An LLM was trained on data through 2026. On any **resolved historical market**, the model already
"knows" who won the election, whether the Fed held, what CPI printed. **A backtest of an agent's
probability estimate on resolved markets measures memory, not calibration — it is worthless, and worse
than the equities case** because prediction-market outcomes are exactly the kind of discrete,
memorable world-facts an LLM has memorised verbatim.

**Therefore the only honest instrument is forward-only, identical in shape to the Newsdesk's design
(NEWSDESK_PREREGISTRATION.md §2):**
1. Agent reads an **OPEN, unresolved** market TODAY plus live free news.
2. It commits, **before resolution**: the market id, the **market-implied probability captured now**,
   its **own probability estimate**, a **direction** (buy YES / buy NO / no-trade), confidence, and the
   triggering event ids — canonically serialised, **sha256-hashed with a UTC timestamp**, appended to an
   append-only pre-registration log.
3. Resolution reads **only the market's official settlement** (a strictly-later fact the agent could not
   have seen at freeze), plus **only price bars strictly after `proposed_utc`** for any mark-to-market.
4. **No code path ever runs the proposer on a market that is already resolved.** A "proof" mode for
   wiring uses synthetic markets and never writes the ledger.

This is the same forward-only discipline the programme already enforces; it ports directly.

---

## 4. THE HONEST EXPECTANCY MATH — and the fee/spread wall

On a binary contract trading at implied probability `p` (price in $), buying YES:
- realised payoff is 0 or 1; **edge per contract before cost = `q_true − p`**, where `q_true` is the
  agent's true probability (buy NO when `p − q_true` is the positive side).
- **cost per round trip `c` = fee + half-spread crossed.** On Kalshi at a mid-priced (~50¢) contract:
  fee ≈ 3.5¢ round-trip **plus** 3–8¢ spread ⇒ **`c ≈ 5–8¢`**. On Polymarket: 0 fee **plus** 2–5¢
  spread ⇒ **`c ≈ 1–3¢`** (before gas/USDC ramp).
- **Break-even condition: `|q_true − p| > c`.** So to profit on a mid-priced Kalshi contract you need
  your probability estimate to be **~5–8 percentage points off the market and RIGHT.** On Polymarket,
  ~2–4pp. **That is a large, high-conviction, off-consensus edge to demand every time** — it rules out
  trading anywhere near the efficient headline markets, and it means the agent must **abstain
  aggressively** and fire only on genuine mispricings. (The fee curve helps at the extremes: fees →0
  near 5¢/95¢, but that is longshot territory where the bias runs against you unless you're fading it.)

**How to measure the edge forward (pre-registered, mirrors `basket_eval` / Newsdesk §4):**
- **Primary metric — calibration vs the market, not P&L.** For each frozen estimate record `(q_agent,
  p_market, outcome∈{0,1})`. After resolution compute **Brier score** `(q − outcome)²` for the agent
  **and** for the market's implied `p`. **The agent has an edge iff its Brier beats the market's Brier**
  (agent Brier < market Brier) over the sample, and its **calibration curve** (predicted vs realised
  frequency, bucketed) is at least as well-calibrated. This is the honest analogue of "better probability
  estimates than the crowd."
- **Secondary — realised expectancy per bet, net of `c`.** Only on the subset where the agent chose to
  trade: mean of `(outcome − p_entry − c)` for YES buys (sign-flipped for NO). This is noisy (binary
  outcomes) and is the *confirming* metric, not the deciding one.
- **Benchmark 1 — the market itself** (agent Brier must beat market Brier).
- **Benchmark 2 — random-direction null** seeded from each setup's own sha256 on the same markets, same
  cost, same resolution: the read must beat coin-flip-on-these-markets.
- **Benchmark 3 — T-bill / do-nothing:** net expectancy after `c` must clear the risk-free carry on the
  notional, or the capital is better in T-bills (the programme's standing benchmark).

**Pre-registered kill rule (port the Newsdesk's, adapted to Brier):**
> **HALT when, after `n ≥ N_min = 50` resolved estimates, the agent's mean Brier is not below the
> market's mean Brier at one-sided 95%** (paired: mean of `Brier_market − Brier_agent` with
> `mean − 1.645·se < 0` ⇒ no demonstrated calibration edge ⇒ HALT). Additionally HALT on the Newsdesk's
> P&L rule if a real-money subset is ever run: `mean_R + 1.645·se < 0`. No pass verdict before `N_min`.
`N_min = 50` (not 30) because resolutions are slow and each carries one bit; a smaller sample cannot
separate a real calibration edge from luck against a market that is already near-calibrated.

---

## 5. THE GATES — what real money would actually require, and honest capacity

- **Kalshi (the clean legal route):** US person, KYC, funded USD account. It is a real CFTC exchange, so
  this is *legally* the straightforward path — **but it is real money and squarely owner-gated**, exactly
  like the Newsdesk/BASKET1 order gate (`T4_OWNER_AUTHORISATION.json` pattern). No order, paper or live,
  leaves a logger without owner sign-off.
- **Polymarket international:** **not lawfully usable by US persons** (geoblocked since 2022 CFTC
  settlement). Would require a crypto wallet, USDC, on/off-ramp, and running into jurisdictional/legal
  reality — **flag honestly: this is a legal no-go for a US owner.** The lawful US alternative is
  **Polymarket US (QCX)**, but it is iOS-only, newer, thinner, and state bans are actively emerging.
- **Honest capacity — small, and it fights the edge.** Institutional users judge Kalshi/Polymarket
  liquidity **"too thin"**; empty books are common off the headline markets. The tractable edge
  categories (§7) — thin long-tail, politics — are **precisely the ones with the shallowest books**, so
  the edge and the illiquidity are the same coin: where you can find mispricing you can place only tens
  to low-hundreds of dollars without moving the price. **Real-money capacity is a few $100s per market at
  most in the beatable categories.** This is fine for a *value probe* and fatal for *scale*.

---

## 6. THE FORWARD PAPER-TRACKER — what to build (if approved), at $0

A near-clone of the Newsdesk, differing only in the instrument and the primary metric:
- **Sources (read-only, keyless, add to allowlist):** Kalshi public API (markets, order books,
  settlements), Polymarket Gamma + CLOB `/prices-history` + Data (for cross-venue implied-prob and
  resolution), optionally Manifold (free real-crowd calibration target), plus the Newsdesk's existing
  news feeds (SEC/Yahoo/Google News/CoinGecko).
- **Proposer:** agent reads open markets + live news, emits for each candidate `(market_id, p_market_now,
  q_agent, direction, confidence, event_ids)` or **"no trade"** (abstention is the default and is logged).
- **Discipline enforced in code (port §6 of the Newsdesk, adapted):** an **edge floor** — reject any
  proposal where `|q_agent − p_market| ≤ c(venue, p)` (must clear the measured fee+half-spread);
  **abstain-heavy**; concurrency cap; immutable once frozen; forward-only resolver.
- **Scoring:** Brier(agent) vs Brier(market) as primary (§4), realised net expectancy secondary, both
  inside an `inputs_that_are_not_results` block until `N_min = 50`.
- **$0, no orders, no account, owner-gated for any promotion** — identical guardrails to the Newsdesk.

---

## 7. CATEGORY RANKING — most → least tractable for an information-reading agent

Ranked by *(edge plausibility for an LLM read) × (crowd is retail not quant-made)*, with the honest
liquidity/capacity caveat on each.

1. **Politics / policy / "culture" / soft-news events** — **most tractable for an LLM.** Price is a
   qualitative judgment from reading news, whales bleed to informed small traders, coverage is uneven,
   crowd is ideological. This is the LLM's comparative advantage vs the equities case (no HFT contest;
   the horizon is days-weeks, so "reading the world" has time to be right). Moderate liquidity on the big
   ones, thin on the rest. **The single best home for the thesis.**
2. **Obscure long-tail / niche events** — **highest edge-per-bet IF the agent genuinely knows something,
   but near-zero capacity and widest spreads.** The mispricing and the empty book are the same coin.
   Good for *calibration* signal, poor for *money*.
3. **Sports** — favorite-longshot bias is strongest and fee-survivable (fade longshots / back real
   favorites), and "recognising the real favorite" needs no infrastructure. **But** sports is a red ocean
   of sharps and the Vegas line already *is* the sharp consensus; an LLM has no obvious edge over it.
   Tractable as a *mechanical* bias play, not as an *information* play.
4. **Crypto price-threshold markets** — driven by the same liquid spot markets that are already
   efficient; the agent has no edge over a live price feed. **Low.**
5. **Macro / econ prints (CPI, Fed, jobs)** — **least tractable, despite being the loudest "news"
   category.** Already tracks Reuters consensus, Susquehanna-made, most-watched, professionalising
   fastest. This is the prediction-market analogue of the equities "priced in milliseconds" wall.
   **Do not expect edge here.**

---

## 8. HOW THIS DIFFERS FROM THE EQUITIES DEAD END (the honest bull case, stated plainly)

The equities programme died on: *free data can't beat pros who price news in milliseconds.* Prediction
markets change **two** things in that sentence: **(a) "milliseconds" → "days-to-weeks"** — the contract
resolves on a future event, so an agent's read has a horizon to be correct over, not a latency race it
always loses; and **(b) "pros" → "a mostly-retail, ideological crowd that demonstrably bleeds EV to
small informed traders"** — in the *non-headline* categories. That is a genuinely different, and more
favorable, structure than equities. **The honest bear case is equally plain:** the fee+spread wall
demands a 2–8pp true edge per bet, the liquid categories are already efficient and professionalising
fast (Susquehanna/DRW/Jump/Cantor, Aug 2026), the beatable categories are the thinnest, and real-money
capacity is a few hundred dollars. **This is not "priced in ms," but it is still "real but small, and
the clock is running."**

---

## 9. RECOMMENDATION

**Build the $0 forward calibration tracker — yes — but frame it as a calibration experiment, not a money
machine, and pre-register the honest expectation that it is small and the window is closing.**

Rationale:
- It is **cheap, strictly honest, and a near-free extension of the Newsdesk** — same forward-only
  discipline, same guardrails, add-only read sources, zero dollars, zero orders, owner-gated.
- It targets the **one finding in the whole prediction-market literature that is genuinely favorable to a
  disciplined, non-ideological, information-reading small participant**: whales bleed to small informed
  traders, and the price is a qualitative read of the world — the LLM's comparative advantage, in a venue
  where (unlike equities) it is **not** racing an HFT.
- The **primary metric is calibration (agent Brier vs market Brier), not P&L** — which is measurable at
  $0, on free official resolutions, with a clean pre-registered kill rule. Even a negative result is
  informative: it would be the cleanest possible test of whether "agent reads the world" is calibration-
  competitive with a crowd, closing the loop the Newsdesk opens.

Brutal honesty / do-not-oversell:
- **Concentrate the forward test on politics/policy/soft-news (rank 1) and skip macro/crypto (ranks 4–5)
  entirely** — testing the efficient categories just buys another honest negative, exactly as the fifth
  directional equities candidate would have.
- **The fee/spread wall is the real killer**, not data or lookahead: needing a right-and-large (2–8pp)
  off-consensus edge *every* bet forces heavy abstention, and Kalshi's fee makes mid-priced contracts
  structurally expensive. If the agent can't clear its own edge floor often enough to reach `N_min = 50`
  in reasonable time, **that itself is the negative verdict.**
- **Real-money capacity is tiny** (a few hundred $ per beatable market) and **legal access is gated**
  (Kalshi = clean but owner-gated real money; Polymarket international = US-illegal; Polymarket US = iOS-
  only, thin, state-ban risk). So even a *positive* forward result promotes only to a **small** real
  probe, never to scale — and only through the owner's real-money gate.

**Base-case expectation, pre-registered:** the tracker most likely shows the agent **roughly
calibration-competitive but not decisively better** than the market in politics/soft-news, with realised
net expectancy pinned near zero by the fee/spread wall — i.e. "real but too small," the programme's
recurring verdict, but arrived at for **$0** and with a genuinely different (and more favorable)
structure than equities that makes it **worth the cheap forward test** rather than assuming the answer.

---

*Research/recommendation only. No accounts, no wallet, no crypto, no orders, no real money, no git commit
by this document. All venue facts are from free public sources (Aug 2026); real-money promotion of any
tracker is owner-gated exactly as BASKET1/Newsdesk are.*

### Sources
- Kalshi API & fees: https://docs.kalshi.com/welcome , https://kalshi.com/docs/kalshi-fee-schedule.pdf , https://www.karlwhelan.com/Papers/Kalshi.pdf
- Polymarket API/subgraph/fees: https://pm.wiki/learn/polymarket-api , https://chainstack.com/polymarket-api-for-developers/ , https://www.newspoly.net/blog/polymarket-historical-data
- Efficiency / favorite-longshot / whales-vs-small: https://www.advancedinvesting.org/how-wise-is-the-crowd-bias-and-edge-in-prediction-markets/ , https://quantpedia.com/systematic-edges-in-prediction-markets/ , https://www2.gwu.edu/~forcpgm/2026-001.pdf , https://cepr.org/voxeu/columns/economics-kalshi-prediction-market
- Quant-firm professionalisation (Aug 2026): https://www.cnbc.com/2026/08/19/hedge-funds-are-about-to-jump-in-big-to-prediction-markets.html , https://www.financemagnates.com/fintech/wall-street-quants-move-into-prediction-markets-to-hunt-for-arbitrage-not-to-bet/ , https://sig.com/predictions/
- Macro-market efficiency: https://arxiv.org/pdf/2606.30040 (Shape of Macroeconomic Beliefs)
- Liquidity/thinness: https://www.risk.net/markets/7963633/ , https://www.cnbc.com/2026/07/02/prediction-markets-mostly-have-thinly-traded-contracts-.html
- Polymarket US legal status: https://cryptonews.com/cryptocurrency/is-polymarket-legal/ , https://predscope.com/guide/polymarket-us
