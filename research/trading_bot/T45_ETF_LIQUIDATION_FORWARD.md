# T45 — ETF liquidation terminal-convergence forward lane (BUILT 2026-09-02 15:00 CEST)

**What this is.** The $0 forward paper logger for the one admissible survivor of the
09-01/09-02 invention rounds: buy the wind-down discount after an ETF liquidation
announcement, hold to the final cash distribution. Prereg is BINDING as filed in
`INVENT_2026-09-02_0300_desk.md` (sha `6821745b…`). Built by the 15:00 CHUNK B tick
under the STRATEGIST 12:00 authorization (agenda T45).

**Runner.** `scripts/trading_bot/t45_etf_liquidation_collect.py`
(pinned `a290805a…`, pin file `research/data/etf_liquidation_forward/T45_PIN.sha256`).
Selftest hermetic, ALL_PASSED (entry math, lookahead guard, K1/K2/K3, PASS path,
tamper-evident hash chain). Cron: `15 23 * * 1-5` → `--cron` (prices then scan);
data under `research/data/etf_liquidation_forward/`.

**Amendment A1 (pinned pre-data, 2026-09-02, before any event existed).** No free
keyless bid/ask source exists on this host — Yahoo v7/v10 quote endpoints are
auth-walled ("Invalid Crumb"/"Unauthorized"), Stooq is behind a JS proof-of-work wall.
The prereg's "buy at the ask" is therefore implemented as
`entry = close(announcement+1) × 1.005` (modeled 50 bp half-spread, conservative for
small wind-down ETFs), `spread_modeled=true` on every event. The constant may never be
retuned once an event enters the ledger. Prices: Yahoo v8 chart (works keyless).
Announcement source: EDGAR full-text search, forms 497/497K, three phrase queries
("liquidation and dissolution", "approved the liquidation", "plan of liquidation");
EDGAR FTS 500s on bursts → retry with backoff is built in.

**Decider (frozen, from the prereg).** PASS = N≥30 completed events, pooled mean net
> 0 AND cluster-bootstrap (issuer × announcement-month, 4000 iters, seed 45) CI-lo > 0.
K1 = <4 events with data by day 21 (clock started **2026-09-02** → K1 read ≈ **09-23**)
→ BLOCKED_ON_DATA. K2 = CI-lo ≤ 0 at N≥30, or mean < −1% at N≥10 → DEAD. K3 = two
events ≤ −15% → DEAD.

**The judgment step (why candidates ≠ events).** The scanner cannot tell a cash
liquidation from a merger from SAI boilerplate; ticker + dates live in filing prose.
So candidates land in `candidates.jsonl` as `review: pending` and an agent tick must
`confirm` (with ticker/announced/last-day read from the filing) or `reject` (with a
reason) each one. **Standing duty: every CHUNK B tick runs
`t45_etf_liquidation_collect.py status` and triages pending candidates** (agenda T46).
Final cash per share is also manual: `record-cash` with a source URL.

**Day-0 triage (11 candidates, all rejected honestly).** 6 mutual/money-market fund
families (BNY Mellon ×3, NYLIM ×2, MFG ×2 counted once more on rescan), 1 insurance
separate account, and 3 that required reading the filing: EA Series Trust = reorg into
an acquiring ETF (share exchange, **no cash terminal** → outside the prereg universe),
Putnam = mutual-fund→ETF conversion (same), VanEck = consolidated SAI carrying 2022
Russia-fund history, not a new announcement. **0 tracked events at build time** — the
universe is quiet this window; K1 exists precisely to decide by 09-23 whether the free
event stream is rich enough.

**Capacity honesty (carried on every report).** Median liquidated ETF ≈ $5.7M AUM →
even a PASS is a small-dollar arm (~$1–5k/event), never a season-maker.

Paper only. No orders, no spend, no keys, no basket contact, t4 untouched.
