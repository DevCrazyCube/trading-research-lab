# AFTERSHOCK V3 — QUOTE-HARVEST — pre-registration

**Instrument:** `AFTERSHOCK_V3` — a **PAPER**, free-data-only, forward-only memecoin arm. A NEW frozen
instrument with its OWN registry and ledger. **V1 and V2 stay frozen and untouched.** Event-driven off
the pump.fun trade tape.

**HARD LIMITS (invariant, enforced in code):** places NO orders, holds NO wallet, touches NO real SOL,
writes NOTHING on-chain, requires NO paid trading account. Reads only free data. Real trading is a
**separate, owner-gated wallet decision**, not reachable from here.

**Freeze intent:** every threshold below is frozen BEFORE the first V3 forward datum. `aftershock.frozen`
recomputes the SHA-256 of this file and refuses on mismatch. An improvement is a NEW frozen instrument
(V4, …), never an edit to a running one.

**No fitting on the V2 trades (say it plainly).** The V3 exit-improvement parameters (ratchet arm/trail,
rollover confirmation) are a-priori engineering choices grounded in the repo's own trail-zone finding
(`research/B19Q_THE_EDGE_MEASURED.md:302`, usable trail ~8–18%), NOT tuned on V2's 17 PASS trades. There
is NO grid search over the V2 series.

---

## Why V3 (the honest starting point)

V2's three arms, read at 17 PASS each, said one thing loudly: **the entry works as designed (kills the
rug tail, ultra-selective) but the value is in the EXIT.** Arm C — the executable-full-position quote
trail — ran at **−0.045R/trade (pot ×0.984)** vs arms A/B's **−0.103R (×0.965)**, roughly HALF the drag,
on the SAME entries. And arm A ≡ arm B exactly: the entry-flow-veto is redundant with the stabilization
gate. So V3: (1) keep V2's net-replacement entry, DROP the dead-weight veto; (2) commit fully to the
executable-quote exit; (3) attack the residual loss, which is the give-back between the quote's peak and
the trail trigger. The honest prior is still ~0/negative; V3 exists to test whether harvesting nearer the
quote's top turns the small loss into break-even-or-better.

---

## The entry (FROZEN) — V2 net-replacement, veto removed, break-even added

Inherits V2's gates unchanged: material cluster dump; **NRR = (Rt−Rmin)/S ≥ 1**; full recovery Rt ≥ R0;
≥3 new independent buyers; B20B k60 < 0.95; coverage(full position) ≥ 10; stabilization (final-window net
reserve flow non-declining, no cluster resume). **Removed:** the entry-flow-veto (V2 proved it redundant).
**Added — break-even feasibility gate:** the exact full-position round-trip quote at the entry instant
must clear a floor — skip if `ExitQuote(q, entry) < breakeven_min_quote` (a doomed-on-cost entry is not a
trade). At the fractional forward size this rarely binds; it is the gate that makes the staged-$ live
sizing safe.

## The exit (FROZEN) — executable-quote harvest, 3 isolated arms

The exit trails the **executable full-position sell quote** `ExitQuote(q,t)` = curve-exact net proceeds of
selling the WHOLE position now (ECR, stressed), 0 if unsellable. `peak` = highest ExitQuote since entry.
Base exits (all arms): capacity break (coverage < buffer OR quote = 0), cluster resume, hard horizon.
Single full exit, ≤ the pinned-fee model, no partials.

- **Arm A — TRAIL (baseline = V2-C):** exit when `ExitQuote ≤ (1 − trail_frac) × peak` (12%).
- **Arm B — RATCHET:** arm A, but once the position is `ratchet_arm_profit` in the money
  (`ExitQuote ≥ (1 + ratchet_arm_profit) × entry_quote`), the trail TIGHTENS to `ratchet_trail_frac`
  (5%) to lock the gain. Below the profit threshold the base 12% trail lets it run.
- **Arm C — ROLLOVER-HARVEST:** arm B, plus a momentum exit: once in profit and past the peak, exit on
  `rollover_confirm_ticks` consecutive lower ExitQuote ticks (a confirmed lower-high) — harvesting at the
  roll-over instead of waiting for the full trail give-back.

All three share the identical entry, so any divergence is attributable to the exit rule alone.

## Sizing (FROZEN)

Forward arms run at the V1-comparable fraction (`bankroll_sol × position_fraction`) so the mechanism is
tested before the money is scaled. The staged $10+$10 / 20%-of-settled-equity, capacity-capped model
(from the AFTERSHOCK V2 sizing note and Codex's bankroll design) is the intended LIVE sizing, gated on V3
first proving positive. On the V2/V1 series, 20% sizing crushes the pot — more size never repairs
negative expectancy.

## The multiple-testing / promotion bar (FROZEN)

An arm is a CANDIDATE only above its per-arm minimum (N_min = 30 resolved PASS), and REAL only if it also
(1) has positive log-growth after ALL costs (curve fees, ATA rent, real-size slippage, failed-landing
fees), (2) stays positive per UTC day AND per creator-cluster, (3) is not carried by a single ≥7× winner
(drop-the-max robust), (4) keeps the unexitable rate under the B20B baseline, and (5) survives a fresh
hash-frozen confirmation slice it never saw. Below the minimum this is BEHAVIOUR, not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, free data only. V1 and V2 remain
frozen. The forward log is the sole arbiter; nothing here is a claim of profit.*
