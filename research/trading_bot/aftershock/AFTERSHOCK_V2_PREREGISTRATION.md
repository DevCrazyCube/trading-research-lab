# AFTERSHOCK V2 — PAYABLE ABSORPTION — pre-registration

**Instrument:** `AFTERSHOCK_V2` — a **PAPER**, free-data-only, forward-only memecoin arm. A NEW frozen
instrument with its OWN registry and its OWN ledger. **V1 (`AFTERSHOCK`) stays frozen and untouched**;
V2 is not an edit to it. Like V1 its entry is EVENT-driven off the pump.fun trade tape, not a snapshot
screen.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid trading account. Reads only free data. Real trading is a
**separate, owner-gated wallet decision**, not reachable from here.

**Freeze intent:** every threshold below is frozen BEFORE the first V2 forward paper entry. The loader
(`aftershock.frozen_v2`) recomputes the SHA-256 of *this file*, refuses on mismatch, AND asserts the
running spec equals the frozen block (constant-drift check). An improvement is a NEW frozen instrument
(V3, …), never an edit to a running one.

**No fitting on burned data (say it plainly).** NOT ONE threshold in this document is chosen from the 429
V1 forward trades. There is NO genome search and NO grid over the burned series. The V2 gates are an
a-priori mechanism hypothesis; only fresh forward data adjudicates them.

---

## Why V2 (the honest starting point)

V1's forward record, read at 429 resolved trades, says two things at once:

1. **V1 already solved the rug problem.** Only 5 unexitables = **1.17%**, far under the B20B deadness
   baseline (`research/B20B_DEADNESS_SCREEN.md`: 35.3% → 13.0% with the defensive screen alone). Entering
   only demonstrably-absorbed shocks works: the unexitable tail is essentially gone.
2. **V1 still loses — to fees and mid-churn entries, not to rugs.** Pot at 2% sizing ≈ **0.752× (≈ −24.8%)**;
   the expectancy kill-gate is **HALTED**. Decomposition of the first 425 trades: FLOW_FLIP 272 exits
   summing **−24.50R**; TRAIL_STOP 118 exits summing **+19.09R**. Gross (before all cost) the mean trade
   is ≈ **+1.79%**; after the Pump curve cost even at optimistic zero transaction cost it is ≈ **−0.72%**.

So V1 finds something real but **trades too often in the middle of churn**, and its entry counts GROSS
buys as "absorption" even when simultaneous sells pull nearly all of it back out. Pump's bonding curve
charges ~1.25%/trade → a round-trip starts ~2.5% in the hole before execution overhead. The only honest
way to beat that is **less churn and larger net moves**, never merely bigger orders.

**V2's single hypothesis:** requiring *net* external reserve replacement (not gross churn) plus an
entry-veto that forbids buying into an already-flipping tape, and trailing on the *executable full-position
sell quote* rather than chart price, closes the remaining fee/churn gap while keeping V1's ~1% unexitable
rate. The honest prior is still that this may end flat/negative; that is an acceptable finding.

---

## The unique formula — net reserve replacement (FROZEN)

Let `R(t)` = the real EXTERNAL SOL in the bonding curve at time `t` (the money that can actually pay
sellers), computed curve-exact by the V1 ECR kernel (`real_quote = virtual_quote − 30 SOL`; integer-exact).
Around one material cluster dump of size `S` SOL:

- `R0`   = external SOL immediately BEFORE the cluster dump
- `Rmin` = the LOWEST external SOL reached after the dump (the trough)
- `Rt`   = external SOL at the END of the absorption phase
- `q`    = the full planned position size in SOL

Derived, exact:

```
NetReplacementRatio (NRR) = (Rt − Rmin) / S        # net SOL that refilled the trough, per SOL dumped
Coverage(q,t)             = R(t) / q               # size-invariant liquidity gate
ExitQuote(q,t)            = exact net SOL proceeds if the WHOLE position q is sold right now (ECR, stressed)
```

The distinction from V1: V1 arms on `absorb_mult` over GROSS buys and accepts `capacity_recover_frac = 0.9`.
V2 requires **NRR ≥ 1** (the withdrawn SOL was NET replaced, not round-tripped) AND **full** recovery
`Rt ≥ R0`.

---

## The V2 entry — ALL of these must hold (FROZEN)

1. A creator / top-early-buyer (`C(mint)` = deployer ∪ top-3 early buyers, as V1) has MATERIALLY dumped:
   `side=sell` ∧ `trader ∈ C(mint)` ∧ `S ≥ 0.5 SOL` ∧ `S ≥ 0.25·R0`.
2. **NRR ≥ 1.0** — the extracted SOL is NET replaced, not merely round-tripped.
3. **Rt ≥ R0** — the curve is FULLY restored (V2 = 1.0; V1 accepted 0.9).
4. **≥ 3 new INDEPENDENT buyers** during absorption (wallets not in `C(mint)`, distinct).
5. **B20B pass**: top-buyer share `k60 < 0.95`.
6. **Coverage(q) ≥ 10** for the FULL intended position.
7. **Entry-veto (essential): NO exit condition may already be true at the entry instant.** A candidate
   that would simultaneously buy and satisfy FLOW_FLIP / coverage-fail / stale-quote is NOT a trade.
8. **Stabilization phase**: after absorption confirms, one additional short window in which NET reserve
   flow stays positive (no fresh cluster sell, `R` not declining) before the probe fills.

Our own paper buy is REMOVED from every flow/absorption/confirmation computation (we never count our own
order as demand).

---

## Sizing — staged, capacity-capped (FROZEN; aggressive owner-mode, NOT yet evidence-backed)

Paper bankroll model, starting `$100` settled equity:

```
target   = min( 0.20 × settled_equity , $50 , exact_capacity_cap )
exact_capacity_cap = largest q whose full ExitQuote(q) clears the frozen slippage/cost limit
probe    = $10 ;  add = $10 ;  max_per_mint = $20 (at the $100 bankroll)
if target < $10:  NO TRADE (skip, never downsize to dust — $2 orders are pointless)
at most ONE full position at a time at $100 ; compounding uses SETTLED equity only
```

Scaling table (informational): `$100→$20, $150→$30, $200→$40, $250+→$50 cap`.

The **second $10 tranche** fills ONLY if, after the probe: (a) external reserve rises further; (b) no
cluster wallet resumes selling; (c) the exact full-`$20` sell quote still clears the capacity gate; and
(d) our own probe is excluded from all flow/confirmation math. No martingale, no averaging down, no
"cheaper so add".

**Explicit warning, frozen in the record:** on the SAME observed V1 series, 20% sizing would have driven
the pot to ≈ **0.027×**. More size does not repair negative expectancy — it only accelerates ruin. The
`$20` stand therefore turns on ONLY after V2 is independently proven positive. Until then this sizing is
a declared intent, and the forward arms below run at V1-comparable fractional sizing so the mechanism is
tested before the money is scaled.

---

## The exit — executable-quote trail, single full exit (FROZEN)

No fixed take-profit, no partial exits (the repo found an uncapped simple trailing exit fits this
extreme right tail better and partials were worse — `research/B19Q_THE_EDGE_MEASURED.md:179`; usable
trail zone ~8–18%, `:302`). Keep V1's **12%** trail but apply it to the NET full-position sell quote,
not chart price:

```
peak = highest ExitQuote(full position, t) seen since entry
EXIT ALL when ANY of:
  • ExitQuote ≤ 0.88 × peak            (12% trail on the executable quote)
  • Coverage(full position) < 6
  • a cluster wallet resumes material selling
  • ExitQuote / reserves are stale or self-conflicting
  • the hard horizon (max_hold) is reached
```

One full exit only: liquidity can vanish and every extra transaction adds failure + priority-fee risk
(Solana charges base + optional priority fees even on FAILED transactions).

---

## What must be technically different from V1 (FROZEN intent)

- PumpPortal may SIGNAL candidates, but the FINAL decision uses the canonical on-chain event stream with
  REAL slots and instruction ordering. No synthesized `0.4 s = 1 slot`.
- Exact POSITION-SIZED buy and sell quotes (not q=0.1 proxy for a $20 order).
- Close the ATA after a successful exit and reclaim rent.
- Priority fee derived from MEASURED landing data, not a fixed oversized tip.
- NO order when exact all-in break-even is not achievable at the quoted size.
- V1 frozen; V2 is a new instrument and a new ledger.

---

## The three forward arms (FROZEN — sizing/exit isolated, one mechanism change each)

- **Arm A** — `net_reserve_entry` (gates 1–8) + V1's existing exits. Isolates the entry change alone.
- **Arm B** — Arm A **+ entry-flow-veto** made strict (gate 7 hard). Isolates the veto's contribution.
- **Arm C** — Arm B **+ capacity/emergency-only exits and the 12% executable-quote trail** (the quote-based
  exit above, dropping the churny FLOW_FLIP as a routine exit). Isolates the exit change.

All three share identical candidate signals; only the named mechanism differs, so any divergence is
attributable. NO genome search; NO threshold chosen from the burned 429.

---

## Promotion criteria (FROZEN) — what a winning arm must do

An arm is a CANDIDATE only if, on its OWN fresh forward slice, it has:

1. **positive log-growth after ALL costs** — Pump curve fees, ATA rent, slippage at the real position
   size, and failed-landing fees;
2. stays **positive per UTC day AND per creator-cluster** (not one good day / one whale deployer);
3. is **not carried by a single ≥7× winner** (drop-the-max robustness);
4. keeps the **unexitable rate well under the B20B baseline**;
5. then SURVIVES a fresh, hash-frozen CONFIRMATION period it never saw.

Below the per-arm minimum this is BEHAVIOUR, not evidence. The honest prior is ~0 or negative; the
forward log is the only arbiter.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, free data only. V1 remains frozen.
The forward record is the sole arbiter; nothing here is a claim of profit.*
