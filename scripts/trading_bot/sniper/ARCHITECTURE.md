# Sniper stack — architecture & contracts

**What this is:** a clean, modular, real-time Solana memecoin trading stack that runs in PAPER / DRY-RUN
mode. It is NOT a block-0 sniper (our own research proved block-0 sniping is −EV: the Jito tip auction
surrenders 50–70% of profit). It implements the ONE structure our research found had a positive gross
edge: **momentum-surge entry + let-winners-run + flow-exit + convexity bankroll sizing, on liquid
(cheap-to-trade) coins.** The point is to run it on LIVE data in paper and measure whether the thin edge
holds BEFORE any real money.

**Hard, non-negotiable safety line (every module must honor it):**
- PAPER / DRY-RUN ONLY. No wallet is loaded, no private key is read, no transaction is ever signed or
  sent, no on-chain write happens. The Executor's live path is a STUB gated behind an explicit
  `ALLOW_REAL_ORDERS` flag that is HARD-CODED False and must never be flipped by code — flipping it is a
  future human decision that also requires a wallet the operator supplies, which this codebase never
  takes or stores. Fills in paper mode are simulated from observed prices with realistic cost/slippage.
- Free / already-paid data only. No new paid signups by code.

## Module boundaries (each built independently against `types.py`)

1. **`types.py`** (I own this — the contract) — shared dataclasses + Protocol interfaces. Everything
   imports from here. Do not change its signatures without updating all consumers.

2. **`data/` — DataProvider implementations** (agent A). Provider-agnostic real-time + historical feed:
   - `ChainstackProvider` (Solana JSON-RPC / WS via SOLANA_RPC_URL/SOLANA_WS_URL in .env; also a
     Yellowstone-gRPC path stub for when the plan is upgraded). Currently returns 403 — must fail
     gracefully and let the runner fall back.
   - `PublicRpcProvider` (free api.mainnet-beta.solana.com — rate-limited, dev/testing).
   - `BitqueryProvider` (HTTP aggregated queries — reuse scripts/smartmoney/ patterns; streaming quota
     may be spent, HTTP may work).
   - `ReplayProvider` (replays the on-disk 1s candles in research/data/memebot_cache/bitquery_candles/
     — lets the whole stack run + be tested with ZERO network). This is the default for paper testing.
   All implement the `DataProvider` Protocol in types.py. Never sign/send anything (read-only).

3. **`signals.py` — momentum-surge detection** (agent B). From the live/replayed tick+bar stream, detect
   an entry: price up ≥ surge_bps over a short window AND buy-vol fraction ≥ threshold AND ≥ N trades AND
   a liquidity gate (per-second USD throughput ≥ floor). Emits an `EntrySignal`. Deterministic, no LLM.

4. **`strategy.py` — the trading policy + risk** (agent C). Consumes EntrySignals; applies convexity
   exits (LET WINNERS RUN uncapped + flow-reversal exit + a wide catastrophe backstop, NO tight price
   stop — matches the research finding); inverse-vol / fractional bankroll sizing across many concurrent
   positions (this is the "consistency via diversification"); pins the ~toll per venue. Produces
   `OrderIntent`s and manages open `Position`s. Freezes each entry (sha256+UTC) before outcome.

5. **`execution.py` — Executor (DRY-RUN)** (agent D). Turns an `OrderIntent` into a *simulated* fill:
   builds the Jupiter route request + estimates the Jito tip / priority fee / venue toll + slippage, and
   returns a paper `Fill` at a realistic price. The REAL sign+send path is a stub that raises unless
   `ALLOW_REAL_ORDERS` (hard False) — it exists only to show where a future, human-gated, wallet-supplied
   live path would attach. Never holds a key.

6. **`sim.py` + `run.py` — harness & runner** (I integrate). `run.py` wires provider→signals→strategy→
   executor into a loop (paper). `sim.py` replays historical bars end-to-end and reports paper P&L,
   per-trade R distribution (is it convex?), bankroll curve, win rate, and cost breakdown — the honest
   scorecard. A `selftest.py` proves each interface on synthetic data.

## The honest scorecard (what sim.py must report)
Bankroll curve over the run, per-trade R (mean/median/distribution — convex?), net after realistic
toll+slippage+tip, vs a random-entry null. NO VERDICT framing until enough paper trades; this measures
whether the edge our research hinted at survives live, before any capital.
