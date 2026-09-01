# ARM 2 — BUNDLE_MOMENTUM_V1 — Codex build handoff (2026-09-01)

Assigned to Codex, parallel with Claude's ARM 1. Self-contained. The shared honesty spine is DONE and
committed (`scripts/trading_bot/memebot/arena/`, commit 9db74027): `fill.py`, `exit_engine.py`,
`chainledger.py`, `scorer.py`, `arm.py`, `selftest.py` all green. You plug into it; do NOT reimplement
fills, exits, ledger, or the decision rule.

## What to build
1. **Extend the listener** `scripts/trading_bot/memebot/ws_data.py`: add a `subscribeTokenTrade`
   subscription (today it sends only `subscribeNewToken` at `ws_data.py:122`). The trade tape is gated
   behind the funded read-only key — the `LIGHTNING_API` key per the `candle-feed-sources` memory
   (already owned, scrubbed from logs; see `sniper/data/pumpportal.py:82`). Write the create tape +
   trade tape to buffers the runtime reads. Detached subprocess, never an in-agent loop
   (`no-network-crawls-in-agents`).
2. **`scripts/trading_bot/memebot/arena/arms/bundle_momentum.py`** implementing the `Arm` ABC
   (`arena/arm.py`), `instrument="BUNDLE_MOMENTUM_V1"`, `fill_basis="causal_cp"`, `target_n=120`,
   `extended_cap=240`.

## Frozen entry (all features observable at/before the decision instant — NO lookahead)
- **Universe:** CREATE-confirmed pump.fun mints only (subscribe-at-create). Census + exclude mid-stream
  first-sights (~31%); report create-coverage. Do NOT use `virality_tracker._universe()` (DexScreener boosts).
- **G0 gate (lookahead fix — BINDING):** enter on an **at-s6 concentration proxy** — top wallet's share of
  the first 6 net buys `< 0.95`, computed live off the tape. Port the concentration arithmetic from
  `b20b_deadness_screen_runner.py:39` (`K_SLOTS`, `CONCENTRATION_THRESHOLD=95`) and the fingerprint from
  `swf_fingerprint_runner.py:68` (`_b20b_passes`) / `:81` (`_fingerprint`). Keep the exact t0+60 B20B as a
  **disclosed ex-post AUDIT only** — never enter at s6 and back-apply t0+60.
- **G1 bundle fingerprint:** first K=6 net buys slot-clumped — live analog `max-min(received_ts) <= 1.0s`
  across the first 6 buys (backtest parity: `slot_span<=2`). One paper position per mint, fixed clip, no re-entry.

## Honest fill (through `arena/fill.causal_fill_cp` — do not price it yourself)
- `SIZE_SOL=0.5`, `latency_s=0.9`. Reserves = last tape trade strictly before insertion at/after `s_fill`.
- Build `buy_quote` **fee-on-input** and reconcile vs on-chain `BuyEvents` before freeze (do NOT mirror
  `sell_quote`'s fee-on-output). Mirror `aftershock/pac_v2_pumpswap.py:119` (`sell_quote`) / `:287` (`capture`).
- Fixed lamport cost both legs (~2.25M round trip). Silent/dead coin → resolve at last executable CP exit
  floored −100% (`exit_engine.resolve(..., "RUG_UNPRICED")` already does this). No tape at `s_fill` → VOID (log+count).

## Exit + resolution (through `arena/exit_engine`)
- Decision metric = widening-trail variant (already in `exit_engine`: 0.18/0.25/0.35, hard-stop −12%, 12h horizon).
- **Comparator:** ALSO log SWF's flat-10% trail (isolates the fill from the +1.167 prior).
- Every entered mint MUST resolve (F1 is enforced by `exit_engine`; never drop).

## Ledger + decision (through `arena/chainledger` + `arena/scorer`)
- Hash-chained ledger `research/data/arena/bundle_momentum/ledger.jsonl`; genesis binds
  `code_sha256(bundle_momentum.py) + prereg_sha256 + spec_sha256`. Git-commit the ledger at the decision read.
- Freeze `arena/arms/BUNDLE_MOMENTUM_PREREGISTRATION.md` (pin the .py sha + every constant) BEFORE the first resolve.
- Decision via `scorer.decide(...)`: N=120 (cap 240). KILL if CI-hi<0 (early KILL allowed at N≥40); PASS if
  CI-lo>0 (earns ONLY a stricter co-located/landed-tx V2, never a money claim).
- **Sensitivity grid (pre-registered):** latency{0.45,0.9,1.8}s × clump{0.6,1.0,1.5}s — a PASS must survive the grid.
- **Report regardless:** `mean(net_marginal) − mean(net_honest)` decomposed (`fill.py` already returns the
  decomposition) — on a ~30-SOL virtual curve the FILL explains only ~3–6 pts, so a large gap is
  exit-mark/dead-coin/dump, not entry impact.

## Provenance discipline (do not repeat the SWF mistake)
The +1.167 (+117%) bundle number is a **burned window-1 DEV number, WRONG-SIGN for SWF's own hypothesis
(SWF verdict = DEAD), zero prior weight.** BUNDLE_MOMENTUM_V1 exists to test forward, under honest fills,
whether the signal is real or the in-sample-fill mirage. A KILL is decisive and cheap; do not build a
bundle-chaser on the burned number.

## Definition of done
`python -m scripts.trading_bot.memebot.arena.arms.bundle_momentum --selftest` green; listener writing the
tape; the arm plugged into `runtime.py` (Claude wires the runtime); genesis written; PREREGISTRATION frozen +
committed. No wallet, no orders, no spend.
