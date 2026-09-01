# MEME ARENA — Master Build Spec (from the ultracode design+harden round, 2026-09-01)

## Arms (hardened, all worth_building)

### virality-arrival (worth_building=True)

**Mirage risk:** The universe is DexScreener BOOSTED tokens = PAID promotion, so attention has ALREADY arrived by the time a coin is boostable. The m5 buy-rate 'acceleration' we enter on, computed on lagged free data, therefore likely LAGS the buyer-arrival inflection rather than leading it — which reduces ARM 1 to the same 'buy the top / become exit liquidity' exhaustion trap that made PAC_SCALP −EV (82% of entries went straight down from fill; median loser never went green). The current live N=4 win-rate 0 is consistent with exactly this. If true, the arm structurally enters AFTER the move and even a PASS on the optimistic-bound fill evaporates under causal V3 fills. Pre-committed guards: (a) KILL is decisive and cheap, so a real KILL here costs almost nothing; (b) the genuine forward test of the thesis (attention BEFORE price) needs the creation-anchored feed to catch pre-boost arrival — the boosted universe cannot test the leading case; (c) never upgrade a PASS to a money claim without V3 causal fills. Secondary mirage: the B20B gate is PROXIED, not enforced, on this data path — do not report it as the validated screen.

**Hardened prereg:** FREEZE (git-commit the code + a new PREREGISTRATION_V2_1.md + its hash) BEFORE any further trade resolves. Void the 4 pre-fix rows (F7): DIAGNOSTIC_ONLY, excluded from N.

Instrument: VIRALITY_GATE_B_V2_1 (optimistic-bound cheap KILL-first FILTER, $0, no wallet).

Sample: N = 120 resolved DISTINCT MINTS (one decision-sample trade per mint per 24h; re-entries logged but not double-counted). Binding rug rule: every opened position resolves — rug/unpriced/horizon all book a loss (F1); a stuck-open count > 0 at decision time invalidates the read.

Accounting: R = per-trade net with the multiplicative two-leg toll at the realistic round-trip rate (F2), fill = single consistent post-decision snapshot (F3). Screen enriched to true unique buyers/sellers or its floors relabeled (F4).

Estimator: mean_R with a cluster/block-bootstrap 95% CI clustered by mint and entry-day (F5) — NOT sd/sqrt(N).

Decision at N=120:
- PASS (earns ONLY the causal-fill V3, explicitly NOT a money claim): bootstrap ci95_lo > 0 AND the F6 lagging-entry split is not monotonically negative in time-since-boost.
- KILL (decisive, cheap): bootstrap ci95_hi < 0, OR event rate < 1 entry/week over the collection window, OR the F6 split shows the lagging-exhaustion signature, OR the resolved-rug rate shows the (now-included) rug tail carries the sign.
- UNDECIDED: CI straddles 0 -> extend to N=200 ONCE, then KILL if still straddling.

Pre-committed scope: a PASS earns only V3 = calibrated decision->landing latency + executable AMM/bonding-curve price WITH impact for the actual 0.1 SOL (never marginal/mid) + exact per-leg gas/priority/slippage + the EXACT B20B >=0.95@t0+60 gate via the creation-anchored feed, plus ideally a non-boosted pre-promotion attention feed to test the actual leading-arrival thesis. No PASS on the boosted/optimistic bound is ever, by itself, evidence to trade real money. Hash-chain is tamper-EVIDENCE only; git is the append-only anchor.

### bundle-momentum (worth_building=True)

**Mirage risk:** Residual optimism the honest fill still does NOT price: ADVERSARIAL SIMULTANEOUS DUMP. The constant-product exit models OUR 0.5-SOL clip walking the curve down, but bundle launches are exactly where the clumped snipers ARE the exit liquidity — if they dump in the same 1-2 slots we try to exit, the real curve is being drained concurrently and true fills are far worse than the single-clip invariant estimate; the observed marginal marks we trail on were printed by trades that happened at without-us reserves, so our own drag on the way out is understated. Second risk: the live clock is receive-time (received_unix_nanos), not chain slot, so both the 1.0s bundle-clump detection and the 2-slot latency are observation-time proxies with PumpPortal push jitter — noise that can smear the fingerprint and mistime the fill reserves. These two are precisely why a PASS earns only a stricter co-located/landed-tx V2 and never a money claim; a KILL, being the pessimistic direction, is unaffected and decisive.

**Hardened prereg:** INSTRUMENT: BUNDLE_MOMENTUM_V1. Frozen before any trade resolves; PREREGISTRATION.md pins bundle_momentum.py sha256 AND every constant below; hash-chained append-only ledger under research/data/bundle_momentum/, anchored by a git commit made BEFORE the first resolve (hash-chain = tamper-evidence only, git = the real anchor, per virality_tracker's own note).

UNIVERSE + INTEGRITY: all fresh pump.fun mints with a CONFIRMED CREATE event on the PumpPortal tape (subscribe-at-create). Mints first seen mid-stream are excluded and censused; report create-coverage. Do NOT use DexScreener boosts.

ENTRY (all features at/before the decision instant): (G0) B20B safety gate — RESOLVED by fix #1: entry instant = t0+60 slots, at which the largest single wallet's net-bought share must be < 0.95 (reuse _b20b_passes, CONCENTRATION_THRESHOLD=95); enter only PASS. The 6-buy clump is a pre-filter observed earlier. (G1) bundle fingerprint: first K=6 net buys slot-clumped — slot_span<=2 in backtest parity vs window DBs; live analog max-min(received_ts)<=1.0s across the first 6 buys. One paper position per mint, fixed clip, no re-entry.

HONEST FILL: SIZE_SOL=0.5. Fill at s_fill=entry_instant+LATENCY(0.9s). Reserves = last tape trade strictly before insertion at/after s_fill. Constant-product on virtual reserves (S=v_sol,T=v_tokens): entry tokens_in=T*SIZE/(S+SIZE), entry_avg=(S+SIZE)/T; exit at (S',T') at s_x+LATENCY, sol_out=S'*tokens_in/(T'+tokens_in), capped at real SOL withdrawable. gross=sol_out/SIZE-1; net_honest=gross-TOLL, TOLL=0.03. MIRROR net_marg (entry S/T, exit S'/T', same toll) logged, plus per-trade decomposition of net_marg-net_honest into {entry-impact, exit-impact, latency, exit-schedule, toll, OOS}. No tape at s_fill -> VOID (logged, counted). Silent/dead coin -> resolve at last executable CP exit vs last real reserve, floored -100% (fix #2).

EXITS: PRIMARY comparator = SWF's flat 10% trail (isolates the fill vs the +1.167 prior). TRADEABLE variant = widening trail 0.18/<0.5, 0.25/<1.5, 0.35 above; HARD_STOP -0.12 all-cost; HORIZON 12h. Both logged; trigger on observed mark, fill at CP price at s_x+LATENCY.

METRIC: net_honest per resolved trade (widening-trail variant is the decision metric; 10%-trail is the comparator). At N=120: mean, SE, 95% CI = mean +/-1.96 SE.
- KILL (decisive, final): CI-hi < 0 at N>=120. Also allowed once early at N>=40 if CI-hi<0.
- PASS-to-stricter (NEVER money): CI-lo > 0 at N>=120. Because exit-latency understates losses on dumping losers, net_honest is an OPTIMISTIC bound — a PASS earns only the co-located/landed-tx/measured-fee V2.
- UNDECIDED: CI straddles 0 -> extend to hard cap N=240, then KILL if still straddling.
Anti-peek: decision read only at N>=120 (single N>=40 futility-KILL exception).

REPORTED REGARDLESS: mean(net_marg) vs mean(net_honest) with the gap decomposition; note that on a ~30-SOL virtual curve the FILL explains only ~3-6 pts, so a ~120-pt gap is attributed to exit-mark/dead-coin/dump (not entry impact), and a non-reproduction of +1.167 is attributed to OOS. PROVENANCE: +1.167 is a burned window-1 DEV number, WRONG-SIGN for SWF's own toxicity hypothesis (SWF verdict DEAD), zero prior weight. SENSITIVITY: pre-registered grid latency in {0.45,0.9,1.8}s x clump in {0.6,1.0,1.5}s; a PASS must survive the grid. VOID rate and dead-coin rate reported; a large value invalidates the run.

### graduation (worth_building=True)

**Mirage risk:** The survivorship/coverage trap that ALREADY voided the window-1 answer (the 33->11 collapse and its bogus "81% up" on 11 obs). Two faces: (1) SELECTION — if you measure drift only on pools that keep trading and silently drop the ones that go dark, you measure survivors and fake a positive number. Defense: every gated-in migration is ENTERED and MUST resolve; a pool that goes dark resolves as UNEXITABLE full-loss, so the denominator is the entire gated cohort, not the survivors. (2) FILL OPTIMISM — pricing the entry at the migration-open (3-bps-below-curve) price instead of the post-sniper, post-latency reserves manufactures the classic +117%-SWF mirage. Defense: re-read reserves at decision+L and price the buy WITH impact against those worse reserves plus the real ~95 bps/leg fee. An optimistic marginal-price fill is the single thing most likely to flip a genuinely NEGATIVE post-migration drift into a fake PASS — which is the exact failure mode this arm exists to avoid.

**Hardened prereg:** INSTRUMENT: MEMEBOT_GRAD (new frozen prefix via memebot.frozen.paths_for; never an edit to a running instrument; code sha256 + prereg sha256 pinned by the frozen loader before the first resolve).

THESIS (honest prior NEGATIVE): a graduated-in taker is exit liquidity for the curve's early buyers, so median post-migration net drift <= 0. This arm is a $0 paper FALSIFICATION test of the sign/size of that drift, not a money claim.

ESTIMAND: mean/median NET R per trade of a react-only, ONE-entry-per-mint long entered at decision = migration_confirm_slot + L, convex-trailed, on the cohort of graduations that (i) confirm a live WSOL-quoted PumpSwap pool and (ii) PASS the deadness gate. Depth floor and exitability precheck are NOT in the measurement gate (fix #1); they run only as a labeled trading overlay measured against the control.

ENTRY: fire iff, strictly at/before decision slot: migration CONFIRMED by reading the PumpSwap pool (getProgramAccounts on pAMMBay6...FMfXEA by base_mint, live WSOL reserves present); deadness gate PASS (slot-bounded decode <= decision slot; reported as a PROXY, with its firing rate logged). L pinned to [pin a specific value, e.g. 15 slots], enforced via context_slot >= migration_confirm_slot + L_slots.

HONEST FILL: entry priced by a fee-ON-INPUT buy_quote (reconciled against real BuyEvents pre-freeze) WITH constant-product impact for size, against the re-read later/worse reserves at the actual observed slot; both legs charged live GlobalConfig fees (~95 bps/leg median) + fixed base+priority+ATA-net lamport cost + pinned slippage buffer. Exit priced by sell_quote against live vaults. Any failed/collapsed read -> UNEXITABLE full-stop loss. Realized latency logged per trade.

EXIT: EXIT_TRAIL, a-priori schedule [pinned, kept within/justified against B19Q's 8-18% plateau], hard-stop -12% all-cost, 90-min horizon marked to sell_quote; dead-pool early exit (quote_reserve below floor OR K silent slots) at the honest sell_quote.

COHORT INTEGRITY: every gated-in migration is ENTERED and MUST resolve (dark -> UNEXITABLE full-loss) so the denominator is the whole gated cohort. Un-confirmable migrations: bounded retry, then logged as un-observed (absence-is-refusal), never dropped. CONTROL NULL: identical sizing/exit entered on migrations that FAIL the deadness gate AND (separately) the depth/exitability overlays, so each filter's removed cohort is measured.

DECISION (frozen before first resolve, N declared a-priori):
- TRIPWIRE, N=30: one-sided sign test on median net drift < 0, p<0.05 -> KILL (interim KILL-only; inflates no PASS false-positive). 
- N=100 resolved: KILL if CI95-hi of mean net R < 0. PASS only if CI95-lo of mean net R > 0 AND survives the Deflated-Sharpe penalty (§8e) for the FULL exit-parameter search surface (the trail schedule is a search — count it), reported explicitly. A PASS earns only a stricter causal V2, never a money claim.
- Report the deadness-gate firing rate and PASS-vs-control net R (the honest test of whether the gate adds value on the seam).

EXPLICIT SCOPE LIMIT: the result is drift CONDITIONAL on this gate; it resolves the programme's open post-migration-drift question only under fix #1 (B20B-only measurement gate). All figures NET of the exact PumpSwap round trip; hash-chained append-only ledger; frozen loader refuses if the prereg moves.

## Architecture

I have enough of the codebase to ground the design. Here is the unified runtime specification.

---

# MEME ARENA — unified frozen-paper runtime for the three hardened arms

## 0. What already exists and is reused verbatim (no rebuild)

| Module | Role in the arena | Reused as-is? |
|---|---|---|
| `memebot/net.py` | Host-allowlisted read-only HTTP + the `wss://pumpportal.fun/api/data` gate; host-wide flock throttle | Yes — the single network chokepoint for every arm |
| `memebot/ws_data.py` | PumpPortal `subscribeNewToken` → `pumpportal_newtokens.jsonl` create buffer (the creation anchor, ~69% coverage) | Reused; **extended** with a trade-tape subscription (below) |
| `memebot/feed.py` | GeckoTerminal `new_pools` / `refresh_pool` / `enrich_token` normalizer | Yes — the enrichment/price-refresh layer |
| `memebot/screen.py` | The count-based deadness **proxy** + red-flags | Reused **only after F4 relabel** (see gate) |
| `memebot/frozen.py` | `paths_for(prefix)`, `frozen_spec()` refuse-on-drift loader, `canonical_sha256` | Yes — the freeze loader pattern, one prefix per arm |
| `memebot/ledger.py` | append-only prereg/resolution logs keyed to `spec["_paths"]` | Pattern reused; wrapped by the hash-chained ledger |
| `virality_tracker.py` | The V2 convex-exit + `prev_hash`/`record_hash` chain + genesis-binds-code+prereg | **Refactored** into the shared exit engine + chain ledger; the arm becomes a thin plug-in |
| `b11m_window2/b11a_creates.jsonl` + `b11a_bodies.sqlite` | The on-chain create→first-60-slot decode | The **exact** B20B `>=0.95@t0+60` oracle — audit-only today, the V3 gate later |

Everything new lives in one package so arms share the package's relative imports:

```
scripts/trading_bot/memebot/arena/
  __init__.py
  hub.py            # ONE shared feed: creation-anchored buffer + GT enrichment, per-cycle cache
  gate.py           # ONE exitability gate: free proxy (tier-1) + exact t0+60 B20B oracle (tier-2)
  fill.py           # ONE honest-fill module (the heart: CP impact, 2-leg toll, latency, real-reserve cap)
  exit_engine.py    # ONE convex-exit + resolution engine (F1: nothing escapes resolution)
  chainledger.py    # hash-chained append-only ledger, one per arm (genesis binds code+prereg sha)
  scorer.py         # cluster/block bootstrap CI + per-arm PASS/KILL/UNDECIDED decision rule
  arm.py            # the plug-in ABC every arm implements
  runtime.py        # the driver loop: one feed pull -> track all arms -> offer candidates -> freeze
  arms/
    virality_arrival.py     # ARM 1 (V2.1, F1–F7) — buildable & collecting TODAY
    bundle_momentum.py      # ARM 2 (V1) — buildable TODAY off the extended trade tape
    graduation.py           # ARM 3 (MEMEBOT_GRAD) — needs the read-only RPC lane (see §7)
  cli.py            # python -m ...arena {run,track,scan,report,status,selftest}
  selftest.py       # hermetic, no-network wiring check for all shared modules + every arm
  dashboard/        # server.py + static; one page, verdict-per-arm + equity + positions + feed health
  supervise/
    arena_watchdog.sh       # flock-guarded tmux supervisor (listener + runtime + dashboard)
```

Frozen artefacts (one prefix per arm, via `frozen.paths_for`):
```
research/trading_bot/memebot/
  VIRALITY_ARRIVAL_V2_1_{FROZEN.json,PREREGISTRATION.md,PREREGISTRATION_LOG.jsonl,RESOLUTION_LOG.jsonl,STATE.json}
  BUNDLE_MOMENTUM_V1_{...}
  MEMEBOT_GRAD_{...}
research/data/arena/<arm>/ledger.jsonl        # the hash-chained append-only ledger (git = real anchor)
```

---

## 1. The shared honest-fill module — `fill.py` (the heart)

This is the single place any arm turns a decision into money, so the honesty rules are enforced once. Two entry points; **no arm may mark a fill any other way** (the selftest asserts arms don't import price arithmetic directly).

**`honest_fill_snapshot(entry_obs, exit_obs, size_sol, toll_buy, toll_sell) -> FillResult`** — the V2/tier-1 optimistic bound, free-feed only.
- Entry booked at a **single fresh snapshot taken AFTER the decision** (F3), never the trigger print.
- Two-leg multiplicative toll (F2): `net = (1+gross)*(1-toll_buy)*(1-toll_sell) - 1`, per-leg at the realistic 3–6% round-trip, **never** `gross - 0.03`.
- Returns `gross`, `net_honest`, and the leg breakdown.

**`causal_fill_cp(entry_ctx, exit_ctx, size_sol, latency_s, tolls, gas) -> FillResult`** — the V3/tier-2 causal fill, mandatory before any money claim and the primary metric for ARM 2.
- Constant-product on **virtual** reserves `(S=v_sol, T=v_tokens)`:
  `tokens_in = T*size/(S+size)`, entry_avg = `(S+size)/T`.
- Fill sampled at `s_fill = decision_instant + latency_s` against the **last tape trade strictly before** `s_fill` (no lookahead).
- Exit `sol_out = S'*tokens_in/(T'+tokens_in)` at `s_x + latency_s`, **capped at the real SOL withdrawable** at that instant (fix #7 / real-reserve bound).
- Per-leg gas + priority + ATA-rent-net (~2.25M lamports round trip for the on-chain arms), plus the multiplicative toll.
- Emits the **decomposition** `net_marg − net_honest → {entry-impact, exit-impact, latency, exit-schedule, toll, OOS}` (fix #5) so a large gap is attributed correctly, not hand-waved as "impact".

`FillResult` also carries `real_reserve_bound_hit`, `latency_s`, and a `basis` tag (`snapshot` vs `causal_cp`) that the ledger records — so a report can never silently mix the two bases.

---

## 2. The shared exitability gate — `gate.py`

Two tiers, honestly labelled (F4 / ARM-2 fix #1 / ARM-3 fix #2):

- **Tier-1 free proxy** — wraps `screen.screen_coin` but the runtime **relabels** its floors as *buy/sell transaction counts*, not "unique buyers", unless `hub` has enriched true unique buyers/sellers via GeckoTerminal (`virality_probe`'s enrichment path). Reported as a **weak count proxy**, never as the validated `>=0.95@t0+60` rule. The structurally-inert `buys_per_buyer` wash check is dropped from the arena screen.
- **Tier-2 exact B20B** — `b20b_exact(mint, decode)` runs the real rule against the `b11a_bodies.sqlite` first-60-slot reconstruction: largest single wallet's net-bought share `>= 0.95` at `t0+60` → unexitable. **Today** this is an *ex-post validity audit* (offline, decode lags live), **disclosed as not-the-same-universe**; it becomes the live entry gate only in V3. `gate.py` exposes both so an arm declares which tier it entered on, and the ledger records it.

For ARM 2's tradeable-today gate this yields the honest option (b): enter on an **at-s6 concentration proxy** (top wallet share of the first 6 buys `< 0.95`, computable live off the trade tape), and keep tier-2 t0+60 B20B as the disclosed audit — never enter at s6 and back-apply the t0+60 gate.

---

## 3. The shared convex-exit + resolution engine — `exit_engine.py`

Generalises `virality_tracker`'s widening trail into a config-driven engine. Every open position, every arm, resolves through it — **F1's core guarantee: no open position escapes N.**

`resolve(pos, obs, params) -> Resolution | None` applies, in this fixed priority:
1. **HORIZON first** (F1) — moved *above* the price-None guard, so age>horizon always books at the last executable price or −100%.
2. **RUG_UNPRICED** — after `N_unpriced` consecutive unpriced fetches, resolve as total loss (`gross ~ -1.0`), cross-checking a DexScreener de-index against GeckoTerminal so a de-list can't hide a rug.
3. **Silent/dead coin** (ARM 2/3) — no tape for the pre-registered window, or real reserve → ~0 → resolve at the last executable CP exit vs last real reserve, floored −100%.
4. **HARD_STOP** −12% all-cost; **TRAIL** widening `0.18/0.25/0.35` (arm-supplied schedule); on-observed-mark trigger, filled through `fill.py` at `s_x+latency`.

Params (`trail schedule`, `horizon`, `hard_stop`, `N_unpriced`, `dead_window`) come from the arm's frozen spec; the engine itself has no free parameters. VOID (no tape at `s_fill`) and dead-coin counts are returned and surfaced — a large value **invalidates the run**.

---

## 4. The per-arm plug-in interface — `arm.py`

```python
class Arm(ABC):
    id: str                       # frozen instrument id / ledger prefix
    prereg_prefix: str            # -> frozen.paths_for(prereg_prefix)
    fill_basis: str               # "snapshot" (ARM1) | "causal_cp" (ARM2/3)
    exit_params: dict             # trail schedule, horizon, hard_stop, dead_window, N_unpriced
    decision: dict                # {target_n, ci_rule, kill_early_n, extend_to, sensitivity_grid}

    def candidates(self, hub) -> Iterable[Candidate]: ...
        # which creation-anchored mints/pools this arm considers this cycle

    def entry_instant(self, obs) -> Instant: ...
        # ARM1: on m5-buy inflection; ARM2: t0+60 (gate) w/ s6 clump prefilter; ARM3: migration_confirm+L

    def should_enter(self, state, obs) -> EntryDecision | None: ...
        # features STRICTLY at/before entry_instant; returns size_sol, tolls, gate tier used, or None

    def extra_log(self, obs) -> dict: ...
        # arm-specific mirage discriminators (F6 splits, ARM2 net_marg + decomposition, ARM3 control-null)
```

The runtime never knows an arm's internals — it only calls these four methods, then routes through the shared `gate → fill → exit_engine → chainledger`. Adding a fourth arm is one file.

**Independence is enforced at the runtime, not the arm** (F5): the driver caps **one decision-sample trade per mint per 24h** (re-entries logged, not double-counted); `N` counts distinct mints.

---

## 5. Hash-chained per-arm ledger — `chainledger.py`

Lifts `virality_tracker`'s chain into a reusable class:
- `genesis` row binds `code_sha256(arm module) + prereg_sha256 + spec_sha` once, up front.
- Every row carries `prev_hash` + `record_hash` (tamper-**evidence** only).
- The **git commit made before the first resolve is the real append-only anchor** — the runtime refuses to resolve any arm whose prereg sha has moved (reusing `frozen.frozen_spec`'s refuse-on-drift), and whose ledger genesis code-sha no longer matches its module.
- ARM 1's 4 pre-fix rows are marked `DIAGNOSTIC_ONLY` and excluded from `N` (F7); a fresh `V2.1` genesis starts after F1–F6 are committed.

---

## 6. The runtime driver — `runtime.py`

One cycle (a detached loop, per the no-network-crawls-in-agents rule; `run --cycles N` is a bounded demo):

1. **One** shared feed pull via `hub`: read the create buffer (ws_data) + one GT `new_pools` page + bounded enrichments, cached per-cycle so the arms share it (no N× GT calls — the same discipline `bot.track_once` already uses with its `_GT_WALLCLOCK_BUDGET_S`).
2. **Track**: for every arm, resolve open positions through `exit_engine` (shortest-horizon arm first, so ARM 2/3's fast books aren't starved — the pattern already in `bot.track_once`). Failures isolate per-position and per-arm.
3. **Scan**: offer the shared candidate set to each arm's `should_enter`; freeze passing entries into that arm's chain ledger *before* any outcome. Respect the one-per-mint-per-24h cap and each arm's `max_open`.
4. **Score**: `scorer.py` recomputes each arm's verdict.

The driver is the only writer, so a single bad arm can't corrupt another's ledger or block the pass.

---

## 7. Data-readiness tiers (honest "buildable TODAY")

- **ARM 1 virality-arrival V2.1** — fully buildable today on free data; it is the refactor of the already-collecting Gate-B. Ship F1–F7, void the 4 rows, restart genesis. **Zero new capability.**
- **ARM 2 bundle-momentum V1** — buildable today by **extending `ws_data.py`** to also `subscribeTokenTrade` for freshly-created mints (same read-only `/api/data` ws, already gated by `net.assert_data_ws`; `traderPublicKey` + received-time give the s6 clump and the top-wallet-share-of-first-6 concentration proxy). The exact t0+60 B20B stays the offline audit (tier-2). Primary metric = `causal_fill_cp`; SWF's flat-10% trail is the pre-registered comparator, the widening trail the tradeable variant; sensitivity grid `latency∈{0.45,0.9,1.8}s × clump∈{0.6,1.0,1.5}s`.
- **ARM 3 graduation (MEMEBOT_GRAD)** — needs two things the current stack **refuses by construction** and that are the one owner-facing gate here:
  - add `subscribeMigration` to the listener (fix #8a — `ws_data` today sends only `subscribeNewToken`);
  - a **new read-only RPC lane** (`arena/rpc.py`, its own allowlist, read methods only: `getProgramAccounts` on `pAMMBay6…FMfXEA` by base mint, `getAccountInfo`) — because `net.py` deliberately forbids `api.mainnet-beta.solana.com`. This is a *read* capability (no wallet, no trade, no write), but it is a genuine boundary change, so per **owner-makes-scope-and-process-calls** it is flagged, not silently added. `buy_quote` is built fee-**on-input** and reconciled against real `BuyEvents` before freeze (fix #3).

---

## 8. Watchdog / tmux supervision — `supervise/arena_watchdog.sh`

One flock-guarded supervisor (the `virality_watchdog.sh` pattern), owning a tmux session `meme-arena` with three long-lived panes:
- **`listener`** — `python -m ...ws_data listen` (create + trade tape, detached; the only stream).
- **`runtime`** — the arena driver loop.
- **`dashboard`** — the read-only server.

The watchdog: refuses to start any arm carrying a `RETIREMENT` authority or whose prereg sha has drifted; auto-restarts only the data-only, append-only processes; re-arm on crash is session-only (per **agent-graph-orchestration**). It never touches a wallet or an RPC-write path.

---

## 9. Dashboard — `dashboard/server.py` (one page)

Read-only, served from the ledgers. Per arm, one verdict card:
- **Verdict**: PASS / KILL / UNDECIDED against the frozen rule, with `N / target`, `mean_net_R`, and the **cluster/block-bootstrap CI** (clustered by mint and entry-day, F5) — **never** `sd/√N`.
- **Equity curve** (per arm) and **live open positions** table (entry basis, gate tier, age vs horizon).
- **Mirage panels**: ARM 1's F6 split (R by time-since-first-boost and which acceleration was entered, `held_s==0` instant-stop fraction, weekly event rate → the lagging-exhaustion KILL signature); ARM 2's `mean(net_marg)` vs `mean(net_honest)` with the gap decomposition and the sensitivity grid; ARM 3's PASS-vs-control net R and deadness-gate firing rate.
- **Feed health**: create-coverage, GT 429 rate, and the **VOID / dead-coin / stuck-open counts** — a stuck-open `>0` at decision time invalidates the read, so it is shown prominently, not buried.

Follow `dataviz` for the equity curve and stat tiles; the design is a small internal ops page, not a marketing artefact.

---

## 10. Decision rules (frozen in `scorer.py`, one per arm)

- **ARM 1**: N=120 distinct mints. PASS iff bootstrap `ci95_lo>0` **and** F6 split not monotonically negative in time-since-boost (earns only V3, not money). KILL if `ci95_hi<0`, or <1 entry/week, or the lagging-exhaustion signature, or the now-included rug tail carries the sign. UNDECIDED → extend to 200 once, then KILL.
- **ARM 2**: N=120. Metric = `net_honest` (causal CP), widening-trail variant is the decision metric, 10%-trail the comparator. KILL if `CI-hi<0` (allowed once early at N≥40); PASS-to-stricter if `CI-lo>0` **and survives the whole sensitivity grid**; UNDECIDED → hard cap 240. `+1.167` is a burned window-1 dev number, wrong-sign, zero prior weight.
- **ARM 3**: TRIPWIRE N=30 one-sided sign test (KILL-only); N=100 KILL if `CI-hi<0`, PASS only if `CI-lo>0` **and survives the Deflated-Sharpe penalty for the full trail-schedule search surface**; result is drift **conditional on the gate** unless the B20B-only measurement gate (fix #1) is adopted.

A KILL is decisive and cheap; **a PASS on any of these optimistic bounds earns only a stricter causal test, never a money claim.**

---

## What I recommend building first (autonomous scope call)

Ship in this order, each independently valuable: (1) `fill.py` + `exit_engine.py` + `chainledger.py` + `scorer.py` (the shared honest core), (2) **ARM 1 V2.1** as the first plug-in — it fixes the live survivorship bias (F1) today and restarts a clean genesis, (3) extend the listener + **ARM 2**, (4) put the **ARM 3 read-only RPC lane** to the owner as an explicit scope decision before writing `rpc.py`. The dashboard and watchdog come online with step 2 so verdicts are visible from the first resolved trade.

Key files to reference when building: `scripts/trading_bot/memebot/virality_tracker.py` (the exit + chain pattern to refactor), `scripts/trading_bot/memebot/frozen.py` (the freeze loader), `scripts/trading_bot/memebot/bot.py` (the shared-feed / per-variant fan-out and the track-budget discipline), `scripts/trading_bot/memebot/ws_data.py` (the listener to extend for trades + migration), and `research/b11m_window2/b11a_bodies.sqlite` (the exact t0+60 B20B oracle for the tier-2 audit and V3 gate).

## Master Build Spec

Codebase is grounded. Everything the arms reference is real, with four corrections that change the build. Here is the finalized master build spec.

---

# MEME ARENA — MASTER BUILD SPEC (grounded, buildable starting today)

## 0. Grounding corrections (verified against the tree — fix these before you copy the arm specs verbatim)

1. **`_b20b_passes` lives in `scripts/swf_fingerprint_runner.py:68`, NOT in `b20b_deadness_screen_runner.py`.** The b20b runner exposes `score()` + module constants `K_SLOTS=60`, `CONCENTRATION_THRESHOLD=95` (`scripts/b20b_deadness_screen_runner.py:39-40`). Both are **offline scorers over the window SQLite DBs**, not live-callable gates. So ARM 2/3 "reuse `_b20b_passes`" is a **port of the concentration arithmetic**, not an import of a running function. Copy `K_SLOTS`, `CONCENTRATION_THRESHOLD`, and the largest-net-buyer-share computation into `arena/gate.py`; cite both source files in a comment.
2. **The live trade tape requires the funded PumpPortal key.** `sniper/data/pumpportal.py:82` documents `subscribeTokenTrade` is "gated behind a funded api-key"; per the `candle-feed-sources` memory that is the read-only `LIGHTNING_API` key (scrubbed from logs). ARM 2 is buildable today **only** on that key. Flag it: ARM 1 needs no key; ARM 2 needs the funded read-only key for the tape; that is a real (already-owned) dependency, not new spend.
3. **ARM 3's RPC read already exists in-tree** — `aftershock/pac_v2_pumpswap.py:293` does `getProgramAccounts` on `pAMMBay6…FMfXEA` (line 37) via `PumpSwapProvider.capture` (line 287). `net.py` forbidding `api.mainnet-beta.solana.com` is real, but aftershock reaches the RPC through its own path, so ARM 3 **reuses `pac_v2_pumpswap`'s existing read lane** rather than a net-new `arena/rpc.py`. It is still a read-boundary the owner should ratify, but the code surface is `buy_quote` (new) + `subscribeMigration` (new), not a whole RPC stack.
4. **`b11a_bodies.sqlite` is 16 GB.** The tier-2 exact B20B oracle is a heavyweight **offline** resource — audit-only today, exactly as the spec says. Do not put it on the live decision path for any arm.

The listener today sends **only** `subscribeNewToken` (`ws_data.py:122`); `subscribeTokenTrade`+`subscribeMigration` are the two additions. The convex-exit + hash-chain to refactor is `virality_tracker.py` (`HARD_STOP=0.12`/`TOLL=0.03` at :52-53, trail at :234, chain at :170-187). The freeze loader is `frozen.paths_for` (:59) / `frozen_spec` (:86) / `canonical_sha256` (:127).

## 1. Module layout (unchanged from your architecture — it is correct)

`scripts/trading_bot/memebot/arena/` with `hub.py, gate.py, fill.py, exit_engine.py, chainledger.py, scorer.py, arm.py, runtime.py, cli.py, selftest.py`, `arms/{virality_arrival,bundle_momentum,graduation}.py`, `dashboard/`, `supervise/arena_watchdog.sh`. Frozen artefacts one prefix per arm via `frozen.paths_for` under `research/trading_bot/memebot/`; hash-chained ledgers under `research/data/arena/<arm>/ledger.jsonl` (git = the real append-only anchor).

## 2. The three arms — final frozen spec (hardening folded in)

**ARM 1 — VIRALITY_ARRIVAL_V2_1** (`fill_basis="snapshot"`, free data, ship today).
- Entry: pinned deepest pair, age≥60min, `m5_buys≥10`, `(m5_buys−prev)/prev ≥ 0.40`, `m5_buys>m5_sells`, `price>prev.price`, tier-1 gate PASS, not open. No bundle/coordination reject (SWF died wrong-sign).
- Fill: `honest_fill_snapshot` — post-decision snapshot (F3), **multiplicative two-leg toll** `net=(1+gross)(1−toll_buy)(1−toll_sell)−1` (F2), never `gross−0.03`. Explicit optimistic bound.
- Exit: widening trail 0.18/0.25/0.35, hard-stop −12%, horizon 12h — through `exit_engine`, which resolves rugs (F1: horizon above the price-None guard; RUG_UNPRICED total loss; GT cross-check).
- Prereg: N=120 **distinct mints** (F5), cluster/block bootstrap CI (never sd/√N), **void the 4 pre-fix rows DIAGNOSTIC_ONLY** (F7), F6 mirage split logged. PASS iff `ci95_lo>0` AND F6 not monotone-negative in time-since-boost; KILL if `ci95_hi<0` OR <1 entry/wk OR lagging-exhaustion signature OR rug tail carries the sign.

**ARM 2 — BUNDLE_MOMENTUM_V1** (`fill_basis="causal_cp"`, needs funded tape key, ship after listener extension).
- **Lookahead fix #1 is binding**: enter on an **at-s6 concentration proxy** (top-wallet share of the first 6 buys `<0.95`, computable live off the tape); keep exact t0+60 B20B as a **disclosed ex-post audit only**. Never enter at s6 and back-apply t0+60.
- Universe: CREATE-confirmed mints only (subscribe-at-create); census & exclude mid-stream first-sights (~31%). Do **not** reuse `virality_tracker._universe()` (DexScreener boost list).
- Fill: `causal_fill_cp` on virtual reserves, latency 0.9s, **real-SOL-withdrawable cap** (fix #7), fixed lamport cost both legs (~2.25M round trip). `buy_quote` built **fee-on-input** and reconciled vs on-chain `BuyEvents` before freeze (fix #3) — do NOT mirror `sell_quote`'s fee-on-output.
- Resolve silent/dead coins at last executable CP exit floored −100% (fix #2); count VOIDs; large VOID/dead rate invalidates the run.
- Prereg: N=120 (cap 240), decision metric = `net_honest` widening-trail, **comparator = SWF flat-10% trail** (fix #4), sensitivity grid latency{0.45,0.9,1.8}×clump{0.6,1.0,1.5} — PASS must survive the grid. **+1.167 is a burned wrong-sign window-1 dev number, zero prior weight** (fix #6). Report `net_marg−net_honest` decomposed into {entry-impact, exit-impact, latency, exit-schedule, toll, OOS} (fix #5) — on a ~30-SOL virtual curve the fill explains only ~3–6 pts, so a ~120-pt gap is exit-mark/dead-coin/dump, not impact.

**ARM 3 — MEMEBOT_GRAD** (`fill_basis="causal_cp"`, gated on owner scope call, §7).
- **Measurement cohort = deadness-gate only** (fix #1): move the 75-SOL depth floor + exitability precheck OUT of the measurement gate into a labeled trading overlay measured by the control null. Otherwise you re-commit the 33→11 survivorship error through the entry gate.
- Relabel gate (A) as **whole-life curve concentration, a PROXY** — not frozen-B20B's 77.7%/69.7% (that recall is t0+60-slot, doesn't transfer); log its firing rate (likely near-vacuous since graduation implies distributed buy-in). Slot-bound the decode to ≤ decision slot (fix #2/§lookahead-3).
- Fill: `buy_quote` fee-on-input reconciled vs `BuyEvents`; pin L numerically, require `context_slot ≥ migration_confirm_slot + L_slots`, price at the actual observed (worse) slot, log realized latency; charge fixed lamport cost both legs. Failed read → UNEXITABLE full loss.
- Every gated-in migration ENTERED and MUST resolve (dark→UNEXITABLE full loss); un-confirmable → bounded retry then logged un-observed, never dropped. Control null enters gate-FAIL **and** depth/exitability-fail migrations so each filter's removed cohort is measured.
- Prereg: TRIPWIRE N=30 one-sided sign test (KILL-only); N=100 KILL if `CI-hi<0`, PASS only if `CI-lo>0` AND survives Deflated-Sharpe for the full trail-schedule search. **Explicit scope: drift conditional on the gate** unless fix #1 adopted. Bring the 25% trail tier inside B19Q's measured 8–18% plateau or justify as a deeper-pool transfer.

## 3. Shared honest-fill `fill.py` — the two entry points

`honest_fill_snapshot(...)` (tier-1 optimistic bound, ARM 1) and `causal_fill_cp(...)` (tier-2, ARM 2/3 primary). CP on virtual `(S=v_sol,T=v_tokens)`: `tokens_in=T·size/(S+size)`, `sol_out=S'·tokens_in/(T'+tokens_in)` capped at real withdrawable SOL. `FillResult` carries `basis` ∈ {`snapshot`,`causal_cp`}, `real_reserve_bound_hit`, `latency_s`, leg breakdown, and the `net_marg−net_honest` decomposition. **Selftest asserts no arm imports price arithmetic directly** — every fill goes through here.

## 4. B20B gate `gate.py` — two honestly-labelled tiers

Tier-1 free proxy = `screen.screen_coin` with floors **relabelled buy/sell transaction counts** unless `hub` enriched true unique buyers/sellers (drop the structurally-inert `buys_per_buyer` wash check, F4). Tier-2 exact = port of `CONCENTRATION_THRESHOLD/K_SLOTS` share arithmetic against `b11a_bodies.sqlite` — **ex-post audit only today**, disclosed not-the-same-universe; the V3 live gate later. Each arm declares which tier it entered on; the ledger records it.

## 5. Ledger + dashboard

`chainledger.py` lifts `virality_tracker`'s `prev_hash`/`record_hash` (:170-187) into a class; genesis binds `code_sha256(arm)+prereg_sha256+spec_sha`; runtime refuses to resolve any arm whose prereg sha drifted (reuse `frozen.frozen_spec` refuse-on-drift) or whose genesis code-sha no longer matches. Dashboard = one read-only page, per-arm verdict card (N/target, mean_net_R, **bootstrap CI clustered by mint+entry-day, never sd/√N**), equity curve, open positions (basis+gate-tier+age), mirage panels (ARM1 F6 split; ARM2 marg-vs-honest + grid; ARM3 control-vs-PASS + gate firing rate), and **feed health with VOID/dead-coin/stuck-open counts prominent** — stuck-open >0 invalidates the read. Follow the `dataviz` skill for the equity curve + stat tiles.

## 6. Watchdog / tmux

One flock-guarded `arena_watchdog.sh` (the `virality_watchdog.sh` pattern) owning tmux `meme-arena` with 3 panes: `listener` (extended `ws_data`: create + trade tape + migration), `runtime` (driver loop), `dashboard`. Refuses to start any arm carrying a RETIREMENT authority or drifted prereg sha; auto-restarts only append-only read processes; re-arm is session-only (per `agent-graph-orchestration`); never touches a wallet or RPC-write. Per `no-network-crawls-in-agents`, the listener + runtime are **detached subprocesses**, not in-agent loops.

## 7. Build order + Codex-vs-owner split

**You/Codex parallel — no owner gate (all $0, read-only, free or already-owned key):**
- **Step 1 (shared core, build first, one owner):** `fill.py` + `exit_engine.py` + `chainledger.py` + `scorer.py` + `arm.py` + `selftest.py`. Hermetic, no network. This is the honesty spine; everything else plugs in.
- **Step 2 (ARM 1 V2.1) — YOU build:** refactor `virality_tracker` into `arms/virality_arrival.py`, ship F1–F7, void the 4 rows, restart a clean genesis. Highest value: fixes the live survivorship bias today. Bring the dashboard + watchdog online here so verdicts are visible from the first resolved trade.
- **Step 3 (listener + ARM 2) — HAND TO CODEX in parallel with step 2:** extend `ws_data.py` with `subscribeTokenTrade` (funded read-only key) + write `arms/bundle_momentum.py` (port `_fingerprint`/concentration from `swf_fingerprint_runner.py` + `b20b_deadness_screen_runner.py`, build `buy_quote` fee-on-input reconciled vs `BuyEvents`, wire `causal_fill_cp` + sensitivity grid). Independent of ARM 1's file; only shares the step-1 core. This is the biggest parallel win — it is self-contained and Codex owns the tape+CP arithmetic cleanly.

**Owner scope gate — do NOT build silently (per `owner-makes-scope-and-process-calls`):**
- **Step 4 (ARM 3):** adds `subscribeMigration` to the listener and puts ARM 3 on the Solana **read** RPC via `pac_v2_pumpswap`. No wallet/no write, but it is a genuine read-boundary crossing (`net.py` deliberately forbids mainnet RPC). **Recommendation: approve it** — it is read-only, reuses an existing in-tree lane, and ARM 3 answers the one open post-migration-drift question the programme left unresolved by choice. Flag it, don't infer it.

**Split rationale:** step 1 is a single-owner foundation (shared invariants must not fork). Steps 2 and 3 are the two independent plug-ins — you take ARM 1 (it is a refactor of code you know and fixes a live bug), Codex takes ARM 2 (self-contained tape+CP work with clean reuse targets). ARM 3 waits behind one owner decision.

**Files to open when building:** `scripts/trading_bot/memebot/virality_tracker.py` (exit+chain to refactor), `frozen.py` (freeze loader), `bot.py` (shared-feed fan-out + track-budget discipline), `ws_data.py` (listener to extend), `virality_probe.py:24` (the enrichment SPEC to reuse in tier-1), `scripts/swf_fingerprint_runner.py:68,81` + `scripts/b20b_deadness_screen_runner.py:39` (port the fingerprint + concentration arithmetic), `aftershock/pac_v2_pumpswap.py:119,287` (`sell_quote` + `capture` to mirror for `buy_quote`), `research/b11m_window2/b11a_bodies.sqlite` (16 GB tier-2 audit oracle, offline only).

**One discipline reminder to carry into every arm:** a KILL is decisive and cheap; a PASS on any of these optimistic bounds earns only a stricter causal test (V3), never a real-money claim — no wallet, no spend, until an explicit owner gate.