# MEMECOIN RE-EXAMINATION under the post-shelving methodology

**Date:** 2026-08-24 · **Scope:** research only. No orders, no money, no wallet, no on-chain
transactions, no git commit. Free/cached data + a label-side cached computation only; no long
network fetch was launched. **The frozen basket is NOT touched** — everything here is a finding or a
recommendation, never a basket edit.

**Spirit.** The same "re-examine an old kill with tools the programme did not have when it was shelved"
pass that revived T3. The honest prior — memecoins are the most adversarial, negative-sum,
sniper/bot-dominated venue there is — held. The new tools make the dead things look **worse**, not
better, and they explain *why* more sharply than the original work could. One genuine open question
(the deadness screen's out-of-sample verdict) remains open, for a data reason, and this pass pins
down exactly what is missing.

## The new tools applied (all developed after the memecoin thread was shelved)

1. **√(2 ln N) analytic bar AND a size-matched placebo** (permute the *signal* across ADV-rank slots,
   never rotate returns — that injects a directional leg). The analytic bar understates ~2× on
   overlapping books.
2. **ρ1(Δspread) bounce-gate, run BEFORE the gross bar.** ρ1 near −0.5 = untradable bid-ask /
   measurement bounce; need > ~−0.35. A high gross Sharpe inside a tethered/bounce family is
   *evidence against*. ADF-strength / low-Hurst are anti-diagnostic.
3. **Gross clears the bar FIRST; execution cost is a significance wall, not a fixable friction.**
4. **Deflated Sharpe Ratio** (Bailey–López de Prado): corrects a Sharpe for trial count, length, skew,
   kurtosis.
5. **Free data prices a STATISTIC, never a CLAIM** — and its four clauses (published / synchronous /
   wider-than-spread / executable-off-its-own-print).
6. **Power census first:** to certify an edge of per-observation Sharpe S you need ≈ (2.8/S)² windows.

---

# THING 1 — RE-AUDIT of the pump.fun conclusions under the stricter methodology

**Verdict: CONFIRMED DEAD, more decisively than before. No pump.fun kill was a strictness-kill of a
tradable-but-underpowered edge (the T3 case). The exit-rule family is structurally negative at *zero
cost*, and the best measurable edge is a quarter of the irreducible toll.** Every new tool
reconfirms the kill from an independent direction.

### 1a. The exit-rule family — the new tools deepen the kill

The frozen exit family (`B19K`) returns **−18.94%/trade** on burned window-1 data. `B19P` bounded
every lever and the shape did not move:

| lever (granted in full, more cheaply than reality) | −18.94% → | still |
|---|---|---|
| perfect liquidity (never-sellable removed) | −12.78% | negative |
| infinite size (fixed cost → 0) | −16.69% | negative |
| **zero transaction cost** (rent+base+priority+tip all 0) | **−16.89%** | negative |

The cause is structural and the new lens names it precisely: ~45% win small, ~55% lose big, a capped
win against an uncapped loss on an asset whose **median outcome is a total drain**. No venue, size,
cost, or rebate change reaches the *shape*. This is not a cost wall and not a significance wall — it
is negative gross expectancy on the asset itself.

**Deflated Sharpe (the one method the programme was missing when this was shelved) makes it worse, not
better.** Applied to the best surviving instrument (trailing stop, `B19Q §8e`): observed Sharpe
**0.0111**, skew **+20.2**, kurtosis **521**. The expected-max Sharpe from just **10** trials of pure
noise is **0.0185 — larger than the observed**. DSR = **0.176** at the real ~100-trial search size,
against 0.95 needed. *Sweeping ten meaningless parameters on noise would be expected to look better
than the best real result.* The permutation test (t = 0.50) already reached this verdict; DSR reaches
it with a named correction and a wider margin.

### 1b. The "find a way" search (`B19Q`) — a real edge, a quarter of the toll

The one honest positive the owner's "stop concluding, find a way" push produced:

- best held-out **gross** edge available anywhere: **0.86%** (and that is a search maximum; the
  in-sample 2.48% shrank to 0.86% out of sample — the ordinary signature of threshold-fitting);
- irreducible **cost of trading: ~3.0%** (2.57% venue fee at 125 bps × 2 legs + ~0.46% transaction
  cost once ATA rent is correctly reclaimed).

Under **gross-clears-the-bar-first**, this fails at the first gate in the starkest possible way: the
*gross* edge (0.86%) does not even clear the **cost** bar (3.0%), let alone a significance bar. Two
genuine defects in the prior work were found and fixed (the +6% take-profit inverted a fat-right-tail
payoff; ATA rent was wrongly charged as unrecoverable), each worth ~2 points — together not worth 3.
The single near-miss (0.86% gross vs a 0.93% bar on cheap-tier *graduated* pools) is 7 bps short and
**splices two different populations** (edge measured on bonding curves, fee on graduated pools); it is
a near-miss whose error bars are wider than the gap, not a strictness artifact.

**Is this the T3 case (positive-but-underpowered, killed only by strictness)? No.** T3 was net-positive
and merely under the significance bar. Here the edge is a *fraction of the cost* — cost-negative, not
significance-underpowered. The best positive instrument (trailing stop, +0.48%/trade) has **t = 0.50**,
DSR 0.176, per-position sd 43%, and a **power census of ≈ 31,000 positions / ~8 window-1's** to
distinguish it from zero — and once variance drag is priced (median log-wealth, Kelly-sized), 1,000
trades returns a median **+4.2%** with a **44% chance of ending down**. The mean flatters it; the
statistic a repeated bettor maximises says it is ~nothing. Underpowered *and* below the toll.

### 1c. The ρ1 bounce-gate explains the venue at the microstructure level

The gate applied to memecoin daily price series (Thing 3 below) reads **ρ1(Δ) = −0.43 to −0.57
everywhere**. This is the quantitative form of `B20B`'s structural observation: **on a bonding curve
the price only moves when someone trades**, so any price-based signal or label is dominated by the
half-spread bouncing. Two features that once passed a permutation test at p = 0.003 against an
acute-collapse label both vanished when observation density was held fixed — detection bias wearing a
signal's costume. The new gate would have killed them a priori.

### 1d. What genuinely survived, and it is not an edge

Across the whole thread (memecoin, minute-trading, rug-detector) exactly **one** object cleared every
leakage requirement: the **DEADNESS SCREEN** (`B20B`) — and it is a loss-*avoidance* entry filter, not
an edge. It is the one thing that deserves the forward test it never got (Thing 2). DSR does not touch
it (it is a classification result, not a return series), and nothing in this re-audit weakens the
load-bearing 13–16σ negatives — those were single pre-specified cells, never search maxima.

**Thing 1 bottom line:** the stricter tools confirm dead four independent ways (structural negative
gross, DSR below the 10-trial noise max, gross-below-cost, ρ1 bounce). Nothing here is a revive
candidate.

---

# THING 2 — The DEADNESS SCREEN: the forward test it never got

**Verdict: REAL-but-BLOCKED. The blocker is unchanged — the transaction-body decode — and it is a
detached multi-hour collection, not something to run inline. The cached window-2 data settles the
LABEL side (and it replicates window 1 encouragingly), but the SCREEN's PREDICTOR cannot be computed
from cache. I did not launch the collection (hard limit: detach long fetches; the prior run reset).**

### The screen (frozen, `B20B`)
> At `t0 + 60` slots, compute the share of all tokens bought so far held by the single largest buyer.
> If ≥ 0.95, do not enter.

Window-1 held-out: catches **77.7%** of unexitable tokens at **69.7%** precision; cuts the
buy-through rate from a 35.3% base to 13.0%. Flat plateau 0.70–0.99 (a property of the population, not
a fitted knife-edge). Independently replicated by the peer seat (p = 0.000).

### Exact state of the window-2 cohort (`research/b11m_window2/`)

The prereg'd window-2 supervisor ran to `supervisor_state.json: "state": "quarantined"`,
`reason_code Q07_stage_failed`, `stage: transaction_bodies`. Stages **completed**: program_boundary,
enumerate_creates, build_cohort, subsample_cohort, signature_inventory. What that leaves on disk:

| table / file | rows | usable for the screen? |
|---|---|---|
| `b11a_creates` (creates in window) | 35,267 | cohort identity only |
| `b11a_cohort.outcome` (a VIEW) | 35,267 | **identity only — no exitability label, no reserves** |
| `b11a_subsample` (frozen subsample) | 5,000 | the evaluation set |
| `b11a_signatures.signature_observation` | **5,484,994** | per-curve signature list **with slot** — LABEL side only |
| `b11a_bodies.raw_transaction` / `instruction` / `reserve_observation` | **0 / 0 / 0** | **empty — the decode never ran** |

The `transaction_bodies` stage died at block +3500 with the same failure the task described:

```
ConnectionResetError: [Errno 104] Connection reset by peer
  scripts/b9d_transaction_bodies.py ... rate_limited_request("getBlock", ...)
  endpoint: https://solana-mainnet.core.chainstack.com
```

**Why cache is not enough.** The screen's predictor — *largest buyer's share of tokens bought in the
first 60 slots* — requires **decoded buy amounts and buyer identities** (the pump `TradeEvent`).
`signature_observation` carries only `(bonding_curve, signature, slot, block_time)` — no amount, no
buyer, no direction. So the predictor is uncomputable from cache; it needs the body decode that has
zero rows.

### The one genuine new datum I *could* extract from cache (label side)

For the 5,000 frozen subsample curves I counted signatures after `launch_slot + 60` (a clean proxy
for `B20B`'s "never traded again → 100% unexitable"):

- **1,850 / 5,000 = 37.0%** of subsample curves have ≤ 1 signature after t0+60.

That is a strikingly close match to window-1's **35.3%** unexitability base rate. It is only a proxy
(signature-count, not the reserve-based exitability label), but it says the window-2 population's
deadness base rate is **stable across windows** — the cohort is sound, and the screen is worth
finishing the moment the bodies exist. (First-60-slot activity is also present: median 42 sigs, 4,004
/ 5,000 curves have ≥ 2 — enough to define "largest buyer" once decoded.)

### The blocker, and the free-RPC note the task asked for

The failure was a **transient connection reset after 3,500 successful blocks**, not data
unavailability — Chainstack served enumerate_creates and the full 5.48M-row signature inventory from
the same endpoint. So the fix is operational, not a data wall:

- **Resume on the same Chainstack archival endpoint** with (a) retry-with-exponential-backoff around
  `rate_limited_request`, (b) a resumable checkpoint (the collector left only 12,079
  `transaction_coordinate` rows and no `raw_transaction`, i.e. it does not checkpoint bodies — it must
  be hardened to resume), and (c) fewer workers / lower cps than the 4×14 that reset. A `chainstack`
  skill is available in this environment for endpoint management.
- **Cheaper targeted path:** the screen needs only the **first 60 slots** per subsample curve. Those
  signatures are already enumerated in `signature_observation`; a **`getTransaction` sweep over just
  the first-60-slot signatures** (median 42/curve × 5,000 ≈ 2×10⁵ calls) decodes far less than the
  full `getBlock`-over-all-slots the quarantined stage attempted.
- **Do NOT point this at public `api.mainnet-beta.solana.com`** — it lacks the historical retention for
  slots now weeks old (these are ~slot 437.2M, block_time ~2026-08). Archival tiers that serve it:
  Chainstack (already provisioned), Helius free tier (has a historical transaction API, rate-limited),
  QuickNode/Alchemy archival free tiers. Any one works; the job is a **detached, hardened,
  resumable** subprocess — exactly the class the memory note says must never run inside a Workflow
  agent — so it is scoped here, not launched.

**Thing 2 bottom line:** not dead — genuinely open, and the cheapest-value question left in the whole
memecoin thread (it costs a ~200k-call detached decode, no money, no on-chain writes). The label side
already replicates window 1 at 37.0% vs 35.3%. It stays REAL-but-BLOCKED until the body decode is
finished on an archival RPC with backoff + resume.

---

# THING 3 — ESTABLISHED (listed, liquid) memecoins as a fresh cross-sectional angle

**Verdict: CONFIRMED DEAD. No memecoin-subset factor and no memecoin-vs-BTC rotation clears both
nulls out of sample; every large number was a lookahead/bounce artifact that collapsed under correct
execution alignment; ρ1 fails (−0.43 to −0.57) on every book including the basket-vs-BTC spread; the
one holdout-positive is an illiquidity tilt in the untradeable small-ADV tail. This is the honest
prior confirmed: it is crypto factors re-tested on the most bounce-dominated, thinnest subset.**

### Data and universe
`research/data/perpmicro_cache/panel1h_ext.npz` (439 Binance USD-M perps × 40,536 hours, OHLC + quote
volume + trade count + taker-buy + funding, 2022→2026-08), resampled to daily. Memecoin subset by
name = **33 perps** (1000PEPE/SHIB/BONK/FLOKI/LUNC/RATS/SATS/XEC/CAT-etc, DOGE, WIF, BOME, POPCAT,
PNUT, PENGU, FARTCOIN, MOODENG, GOAT, TURBO, PEOPLE, ACT, AI16Z, ZEREBRO, …).

**Power problem, stated first.** Listings are heavily staggered and many are already delisted. Median
simultaneously-live memecoin perps per quarter: 4 (2023) → 11–13 (2024) → **peak 25 (2025Q1)** →
7–9 (2026). A usable cross-section only exists from 2024 on. So: **design = 2024** (breadth 11–24),
**holdout = 2025-01 … 2026-08** (breadth 25 → 7). One design year at k≈2–3 names/leg is intrinsically
low-power; the power census (S≈0.5 ⇒ ~31 years) says this cannot certify a factor even in principle.
Reported anyway, honestly.

### Factor battery (each one pre-registered hypothesis; sign oriented on design, frozen OOS)
Dollar-neutral cross-sectional book, gross notional 2.0, **executed open-to-open with the fill on a
different print from the signal** (Clause 4), net of **5.5 bp/side + funding accrual**, min 8 live
names/day.

| factor | design SR (net) | design GROSS SR | holdout SR (net) | placebo p95 | ρ1(Δpnl) holdout |
|---|---:|---:|---:|---:|---:|
| LOWVOL (long low-vol) | −1.41 | 1.73 | −0.16 | 2.10 | **−0.474** |
| MOM7 | −0.41 | 0.29 | −1.52 | 2.26 | **−0.573** |
| MOM30 | +0.38 | 0.57 | −0.48 | 2.56 | **−0.430** |
| REV1 (fade yesterday) | −1.17 | 0.75 | +0.13 | 2.27 | **−0.532** |
| FUNDING (long most-negative) | +0.26 | −0.63 | +0.34 | 2.25 | **−0.572** |
| SIZE (long small-ADV) | +0.71 | 0.64 | +2.85 | 2.26 | **−0.509** |

Analytic two-sided bar √(2 ln 2N), N=6 = **2.23** (design ≈1y ⇒ SR-bar ≈2.23). **Every factor's
design |SR| is below both its ADV-slot placebo p95 and the analytic bar.** Nothing clears gate one.

**The decisive diagnostic — the lookahead/bounce collapse.** A first cut with the fill window
overlapping the signal (`oo[d+1]`, a 1-bar lookahead) produced REV1 design SR **−18.2** and holdout
**+12.5**, mean **+1182 bp/day** — a fantasy. Moving the fill to a genuinely later print (enter open
d+1, earn open d+1→d+2) collapsed it to design **−1.17** / holdout **+0.13**. **That ~18-Sharpe was
100% execution-off-its-own-print bounce**, precisely the Clause-4 artifact (up to 63× inflation in the
0823 work), reproduced here in the memecoin cross-section. And even after the fix, **ρ1(Δpnl) sits at
−0.43 to −0.57 for every factor** — the daily memecoin book *is* bid-ask/measurement bounce; per the
gate it is untradable regardless of any Sharpe.

**The one holdout-positive (SIZE, +2.85) is the illiquidity trap, rejected.** Its design SR (0.71) is
below its own placebo p95 (2.26), so it is a holdout coincidence, not a design-confirmed edge; its
turnover is 0.09/day and it lives in the **smallest-ADV memecoins**, the exact thin tail where a
5.5 bp fill is fiction — the same illiquidity-tilt that Round-1 crypto-perp micro found and killed on
the top-50 cut. Rejected on the pre-registered ρ1 (−0.509) and the design-placebo failure.

Note the **within-memecoin LOWVOL sign is negative** (design −1.41): there is *no* internal
low-vol premium among memecoins — consistent with the fact that memecoins are the **short leg** of the
already-found broad crypto low-vol factor (`S1_VOL30`, INVENT_0822B: long low-vol / short high-vol
alts, entirely a high-vol-alt-bleed carry). Testing factors "within memecoins" is re-testing that same
factor on its own short tail.

### Memecoin basket vs BTC (majors) rotation

| construction | design SR | holdout SR | note |
|---|---:|---:|---|
| static long-basket / short-BTC (unconditional premium) | **1.01** (24.3 bp/day) | **−0.05** (−1.1 bp/day) | the 2024 meme premium fully vanished OOS |
| TS-momentum timed (lb 3 / 7 / 14 / 30) | 0.41 / 0.33 / −0.08 / 1.01 | −0.45 / −0.80 / +0.09 / **+0.07** | best design (lb30) → holdout 0.07 |

ρ1(Δ basket-BTC spread) = **−0.461** (bounce even at the basket level). Memecoin-basket **beta to
BTC = 1.64, corr 0.71** — a memecoin-vs-BTC "rotation" is a high-beta directional long-crypto bet,
not a market-neutral edge. Nothing here is diversifying or significant.

**Thing 3 bottom line:** CONFIRMED DEAD. The established-memecoin cross-section is thinner, more
bounce-dominated, and lower-powered than the broad Binance perp universe already swept 107+ formulas
deep; its only large numbers are lookahead/bounce; its every book fails ρ1; and the "memecoin premium"
was a 2024-only directional beta episode that did not repeat. It re-confirms `S1_VOL30` (memecoins =
its short leg) rather than adding anything.

---

# THREE VERDICTS

| # | question | verdict |
|---|---|---|
| 1 | RE-AUDIT pump.fun under stricter tools | **CONFIRMED DEAD** — reconfirmed 4 independent ways (structural negative gross −18.94% at zero cost; DSR 0.176, below the 10-trial noise max; best gross 0.86% < 3.0% toll; ρ1 bounce). No kill was a T3-style strictness-kill. |
| 2 | DEADNESS SCREEN forward test | **REAL-but-BLOCKED** — predictor needs the transaction-body decode, which has 0 rows (RPC ConnectionResetError). Cache settles the LABEL only: window-2 unexitability base rate ≈ **37.0%** replicates window-1's 35.3%. Unblock = detached, hardened, resumable `getTransaction` decode over first-60-slot signatures on an archival RPC (Chainstack/Helius, never public mainnet-beta). Not launched (hard limit). |
| 3 | ESTABLISHED memecoins as a fresh XS angle | **CONFIRMED DEAD** — no factor or rotation clears both nulls OOS; the only large Sharpes were lookahead/bounce (REV1 collapsed 18→1 on correct alignment); ρ1 −0.43…−0.57 everywhere; SIZE's holdout pop is the untradeable illiquidity tail; basket-vs-BTC is 1.64-beta directional. Re-confirms `S1_VOL30`. |

**No basket action.** Nothing here is a promote/freeze candidate — Thing 1 and Thing 3 are dead, and
Thing 2 is a loss-avoidance filter (creates no edge) that is not even runnable yet. The frozen basket
is untouched. The single item worth a follow-up is **finishing the deadness-screen decode** — a
research collection, no money, no on-chain writes, to answer the one open question the memecoin thread
left. If pursued it should be a proposal/observation, not a basket edit.

*Research only. All backtest numbers are cached-data point estimates and selection-inflated upper
bounds; the forward log remains the only arbiter. Scripts:
`scratchpad/meme_xs.py`, `scratchpad/meme_factor2.py` (both cached-panel only, no network).*

---

# UPDATE 2026-08-24 — THING 2 UNBLOCKED: deadness-screen decode running on the FREE RPC

**The blocker is cleared and the decode is now running; the OOS verdict is PENDING a ~3-day
detached collection.** Two things in the Thing-2 write-up above are now CORRECTED by direct test:

1. **The free public RPC DOES retain the window-2 slots.** The claim above — "*Do NOT point this at
   public `api.mainnet-beta.solana.com` — it lacks the historical retention*" — is **wrong** for this
   window. Verified live: `https://api.mainnet-beta.solana.com` serves BOTH `getTransaction` and
   `getBlock` for the window-2 range (slots 437,211,673–438,846,716). So the decode costs $0, needs
   no key, and is read-only.
2. **The prior death was a one-line code bug, not a data or endpoint wall.** `b9d.rpc_request`'s
   retry `except` tuple was `(HTTPError, URLError, TimeoutError)` and did **not** include the bare
   `ConnectionResetError` (an `OSError`) raised inside `response.read()`. A single transient reset
   after ~3,500 blocks escaped the loop and killed the run. Fixed by adding `OSError` to the tuple
   (it routes to the existing `is_retryable_error`, which already accepts `OSError`; fatal errors
   still exhaust the 8 exponential-backoff retries and raise). Not a hash-pinned file (only the B20B
   *runner* is pinned), so the edit is safe.

**What was launched.** `research/b11m_window2/run_free_decode.sh` — a detached restart loop driving
`b9d ... run` against the free endpoint (`--workers 2 --calls-per-second 4`), fully resumable (each
restart continues from the per-row `raw_block_signatures`/`raw_transaction` checkpoint on the same
endpoint, so no endpoint-drift refusal). The 3%-done Chainstack partial was set aside to
`b11a_bodies.chainstack-partial.sqlite` (evidence integrity: one artifact, one endpoint). Log:
`research/b11m_window2/logs/free_decode.log`.

**Scale/ETA.** Full frozen population for the subsample = **366,688 signatures + 118,384 getBlock
slots ≈ 485K read-only calls.** Public endpoint throttles hard (429s even below 2 cps); measured
steady ≈ **1.87 calls/s ⇒ ~72 h (~3 days).** The full population is required because the pinned B20B
LABEL needs full-life reserves (real_quote after t0+60), not just the first-60-slot predictor, and
b9d's exhaustive freeze gates refuse a partial regardless.

**After collection (all OFFLINE — no further RPC):** `decode_and_reserves` (pinned-IDL decode +
reserve reconstruction) → the pinned `b20b_deadness_screen_runner.py` on `--bodies/--paths/--identity`
emits CONFIRMED / WEAKENED / FAILED against the window-1 prior (77.7% recall, 69.7% precision).

**Thing-2 status now: REAL — decode RUNNING on free RPC, OOS verdict PENDING (~3 days).** No money,
no wallet, no on-chain writes; read-only getBlock/getTransaction only. Still a loss-avoidance filter,
never an edge.
