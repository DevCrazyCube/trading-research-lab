# AFTERSHOCK SECONDARY-SELL-RESILIENCE — pre-registration

**Instrument:** `AFTERSHOCK_SS` — a PAPER, free-data-only, forward-only memecoin arm built ON the
handoff-424 execution-measurement engine. It places NO orders, holds NO wallet, touches NO real SOL, and
its results are `SIMULATED_OBSERVED_PATH` scenarios, never executable evidence.

**Hard gate (do not skip).** This test cannot produce evidence until BOTH owner-gated conditions hold:
1. the session seal + activation root are **git-anchored** (committed byte-clean) — the execution engine's
   public order path stays closed until then; and
2. a separately-authorized **Phase-2 latency calibration** replaces the `CALIBRATION_UNCALIBRATED` scenario
   latency with measured sign/send/land clocks.
Until both exist, every run is a labelled scenario for plumbing/feasibility only, and NO promotion,
sizing-up, or real-money conversation is licensed.

---

## Why this design

Every prior memecoin arm lost the same two ways: it bought coins that then **gap-dumped** (stops filled
far worse than intended) or **rugged** (unexitable), and its wins were **capped** below the fat tail. The
newest read confirmed it: MEMEBOT_EXIT_V2 HALTED at −0.777R with 16% unexitable, all stops gapping past
their intended level, and every win pinned at a fixed take-profit. The lesson across the AFTERSHOCK
lineage: **prove exitability before entry, and don't cap the upside.**

So the unique rule here is NOT "buy after many buys". It is: **buy only after the observed curve has
completed two sequential reserve-withdrawal/recovery cycles**. This demonstrates reserve resilience on
the observed path. It does **not** prove independent sellers or fresh independent capital: the canonical
event currently lacks actor/funding-cluster completeness, so those stronger claims are prohibited.

## Entry (FROZEN in `secondary_sell_detector.py`, sealed by hash)

Over the causal observed prefix, require **two sequential withdrawal→recovery cycles** before entry:
1. observed external SOL reserve falls by ≥ `MIN_CYCLE_WITHDRAWAL_LAMPORTS` = 50,000,000 lamports
   (**0.05 SOL**, not a constant USD amount);
2. `real_quote` subsequently returns to ≥ its pre-withdrawal level;
3. the same again in a later, non-overlapping cycle.
The detector emits exactly `[withdraw1, recover1, withdraw2, recover2]`, and `recover2` must be the latest
observed event and the signal. A completed pattern followed by any later event is stale and cannot enter.
No current two-cycle pattern ⇒ no trade.

## Sizing (FROZEN) — point-in-time, staged

- `q_lamports = q_lamports_for_usd("10.00", observed_SOLUSD)` — exact Decimal, point-in-time, per the
  engine's numeraire rule (no frozen SOL/USD constant).
- **Coverage invariant:** that exact $10 size must also be ≤ 50,000,000 lamports. If SOL/USD < $200 and
  $10 therefore requires >0.05 SOL, the attempt REFUSES; the detector may never call 0.05 SOL “our $10”.
- The **second $10** is added ONLY after a THIRD proven sell/recovery cycle post-entry (another
  demonstration the pot still absorbs our-size exits). Never averaged down, never sized from a spike mark.
- One position at a time at a $100 bankroll; report SOL P&L and USD-equity separately (SOL beta ≠ edge).

## Exit (FROZEN) — single executable-quote trail, uncapped

One rule: a **12% trail on the executable full-position quote** (the curve-exact net proceeds of selling
the whole position now, via the b10a kernel). No fixed take-profit, no ratchet, no scale-out — the fat
tail is left uncapped; the trail is the only exit besides capacity collapse / cluster-resume / horizon.
Every entry and exit fill is modelled through the execution engine: signal → uncalibrated latency →
scenario boundary state → slippage-bounded fill; a fill that can't be bracketed is right-censored.

## Promotion (FROZEN)

A result is a CANDIDATE only after the anchored + calibrated gate above AND: ≥ the per-arm minimum resolved
scenario trades; positive log-growth after ALL costs (curve fees, kernel gas, real-size slippage, ATA-rent
lifecycle); positive per UTC day AND per creator-cluster; not carried by one ≥7× winner; unexitable rate
under the B20B baseline; then survival on a fresh anchored confirmation slice. Below that it is BEHAVIOUR.

---

*Paper only. Scenario, not executable evidence, until git-anchored + latency-calibrated. V1–V5 books remain
burned. The forward, anchored, calibrated log is the sole arbiter; nothing here is a claim of profit.*
