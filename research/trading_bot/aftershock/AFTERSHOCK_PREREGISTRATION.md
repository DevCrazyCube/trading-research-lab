# AFTERSHOCK — pre-registration (the rug-absorption survivor paper arm)

**Instrument:** `AFTERSHOCK` — a **PAPER**, free-data-only, forward-only memecoin arm. It keeps its OWN
frozen registry (deliberately NOT in `memebot.frozen.INSTRUMENTS`) because its entry is EVENT-driven off
the pump.fun trade tape, not a periodic snapshot screen.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid trading account. Reads only the free PumpPortal trade tape.
Real trading is a **separate, owner-gated wallet decision**, not reachable from here.

**Freeze intent:** the rules below are frozen BEFORE the first forward paper entry. The loader
(`aftershock.frozen`) recomputes the SHA-256 of *this file* and refuses to run if it moved. An
improvement is a **new** frozen instrument, never an edit to this one.

---

## The thesis (say it plainly)

A long-only sniper cannot profit from coins that go to zero — the ~98–99% of pump.fun launches that fail.
It CAN use those failures as a real-time stress test. Do **not** buy before the rug. Watch each mint from
birth; when a creator/early-cluster wallet fires the first **material sell** (the rug-like shock), run an
absorption test, and **enter only the coins whose shock is demonstrably absorbed by external, non-cluster
demand** — the survivors where real buyers keep showing up after the dangerous inventory has hit the
market. This is the directional complement to the audited B20B deadness screen (which is purely
defensive: it lowered measured unexitability 35.3% → 13.0% but creates no edge on its own,
`research/B20B_DEADNESS_SCREEN.md`). The honest prior remains that most memecoins are unexitable traps;
AFTERSHOCK's job is to enter only the proven-absorbing ones and to leave before the exit path closes.

The honest decider is **pot growth**, and the **unexitable-dump rate is a hard KILL-GATE, not the score**
(a 0%-dump bot that bleeds a little each trade still drains the pot).

---

## 1. The eyes — the free PumpPortal trade tape (FROZEN)

A central broker (`memestream.pumpportal_broker`, one keyed PumpPortal connection) writes a per-mint raw
trade tape: `{ts, mint, trader, side, sol_amount, token_amount, v_sol, v_tokens, pool}`. `v_sol`/`v_tokens`
are the exact post-trade bonding-curve virtual reserves; `trader` is the taker wallet. No fabricated
fields. Pump/SOL bonding-curve regime only (`pool == "pump"`); migrated pools are treated as
exit-unavailable until a separate PumpSwap validation exists.

## 2. The ECR engine — curve-EXACT (FROZEN)

Position size `q = 0.1 SOL`. All curve arithmetic is integer-exact via the repo's audited kernel
(`b10a_simulator_kernel` over `b9i`), never a proxy. Pinned constants (verified against real pump.fun
CreateEvents): `real_quote = virtual_quote − 30 SOL`; `real_token = virtual_token − 279_900_000_000_000`
atoms; fee **125 bps/side** (95 bps protocol + 30 bps creator); execution model base 5000 + priority
100_000 + ata-rent 2_039_280 lamports, **one failed landing per side** as the a-priori stress lever.

- `coverage_ratio(t, q) = R(t)/q`, `R(t) = real external SOL in the curve` — the size-invariant liquidity gate.
- `ecr_roundtrip(entry_reserves, exit_line, q)` — the curve-exact, stressed round-trip return. If the
  exit curve cannot pay the position (or the pool migrated) it is **UNSELLABLE → stressed_net_return = −1.0**
  (full economic loss). The loss is floored at −1.0.

## 3. The entry state machine (FROZEN, a-priori thresholds; slots via 0.4 s/slot)

Per mint, WATCH → ARMED → ABSORPTION:

- **ARM** on the first MATERIAL cluster sell: `side=sell` AND `trader ∈ C(mint)` AND `sol ≥ 0.5 SOL`
  AND `sol ≥ 0.25 · R(t⁻)`. `C(mint)` = deployer (first buyer) ∪ top-3 early buyers by tokens bought over
  the first 60 slots; `k60` = largest early buyer's share of tokens bought.
  The cluster set `C(mint)` is FROZEN at the shock instant (the dangerous early inventory), so genuine
  post-shock absorbers are never mis-counted into it. An armed shock whose absorption window elapses in
  wall-clock time with no closing trade is force-closed as a CONTROL (the honest null is never dropped).
- **ABSORPTION TEST** over the next 60 slots (24 s); FIRE only if ALL hold:
  1. **absorb** — Σ non-cluster buy SOL ≥ 1.0 × the shock's sell SOL AND ≥ 3 never-before-seen wallets;
  2. **capacity held** — `R(t) ≥ 0.90 · R_pre` across the last 10 slots;
  3. **concentration** — `k60 < 0.95` AND the top non-reserve holder share is not rising;
  4. **coverage floor** — `coverage_ratio(t, q) ≥ 10` across the last 10 slots AND non-decreasing.
- A shock that fails the test becomes a **CONTROL** observation (`control=True`) — the honest null: "the
  rug fired but nobody caught it." A mint may re-arm on a later material sell.

## 4. The exit (FROZEN — capacity/flow first, price second; NO fixed take-profit)

Resolve on the FIRST of: (1) `coverage_ratio < 6`; (2) a cluster wallet sells `≥ 0.25 · R` after entry;
(3) non-cluster `sell_frac ≥ 0.65` over the trailing 60 slots, gated by a magnitude floor (window volume
`≥ 0.1 SOL` AND `≥ 3` trades) so a lone trivial sell cannot trip it; (4) price `≤ 0.88 × peak` (12%
trailing — lets the rare right-tail runner run); (5) `t ≥ t_entry + 3000 slots` (~1200 s), enforced on a
WALL-CLOCK backstop so a coin that goes silent still resolves. The realised outcome is priced by
`ecr_roundtrip`; an exit the curve cannot pay is booked `UNEXITABLE_TIMEOUT`, `stressed_net_return = −1.0`.

## 5. Scoring + kill-gates (FROZEN)

`f = position_fraction = 0.02`. Per resolved PASS trade `g_i = ln(1 + f · stressed_net_return_i)`;
**SCORE = pot growth `G = Σ g_i`**, `pot_multiple = exp(G)`, plus max drawdown and cluster HHI (a `G`
carried by one deployer is fragile — reported, never magic-weighted). Control stream scored identically →
`G_control`; the edge is `G − G_control`.

Kill-gates (a-priori), evaluated only at `n ≥ N_min = 30`:
1. **Expectancy HALT** — `upper95(g) < 0` (mean + 1.645·se of the log-growth stream).
2. **Dump-rate HALT** — `dump_rate ≥ 0.13` (B20B's measured passed-unexitable rate). If AFTERSHOCK
   cannot beat the raw B20B screen on unexitability itself, its added machinery is worthless.

Below `N_min` everything is **behaviour, not evidence**, fenced under `inputs_that_are_not_results`.

## 6. Honest gaps (declared, not hidden)

- Slots are synthesised from wall-clock ts at 0.4 s/slot (the tape is not slot-stamped).
- Cluster identity uses the first-observed-buyer proxy; a dev buying via a second wallet is missed.
- `k60 < 0.95` embeds B20B, whose window-2 forward test is still pending; if B20B weakens, threshold (3.3)
  must be revisited.
- Post-graduation (migrated-pool) AFTERSHOCK is deferred: migrated exits are treated as unavailable until
  a separate PumpSwap-reserve validation exists.
- "Unsellable = full loss" is deliberately punishing (no partial-fill credit): the design exits at
  coverage 6 precisely to avoid ever reaching it, and the conservative mark is the point.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, no paid accounts, free tape only.
The forward log is the only arbiter. The prior is that most memecoins are unexitable traps; this arm
exists to test, forward and at $0, whether demonstrated rug-absorption identifies the survivors that a
disciplined fast scalp can actually grow a portfolio on.*
