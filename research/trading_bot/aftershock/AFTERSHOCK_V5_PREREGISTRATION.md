# AFTERSHOCK V5 — SCALE-OUT — pre-registration

**Instrument:** `AFTERSHOCK_V5` — a **PAPER**, free-data-only, forward-only memecoin arm. NEW frozen
instrument, own registry + ledger. **V1–V4 stay frozen and untouched.** Event-driven off the tape.

**HARD LIMITS (enforced in code):** NO orders, NO wallet, NO real SOL, NO on-chain writes, NO paid
account. Free data only. Real trading is a separate, owner-gated wallet decision.

**Freeze intent:** thresholds frozen BEFORE the first V5 datum; `aftershock.frozen` refuses on prereg
hash mismatch. An improvement is a NEW instrument, never an edit.

**Honesty about where this came from.** The scale-out rule is MOTIVATED by a gap diagnostic of V3/V4's
plain-trail trades and a backtest of partial-exit policies on that same (burned) set. The parameters are
ROUND a-priori numbers, NOT the backtest optimum, and the finding is only a HYPOTHESIS: a FRESH forward
slice plus the per-day / per-cluster / drop-max / fresh-confirmation promotion gate adjudicates it. No
grid optimum is frozen as the rule.

---

## The diagnostic that motivates V5 — the loss mode is GAPPING

Replaying V3/V4's plain-quote-trail losers: the dominant loss mode is **not** a gradual fade and **not** a
bad entry — it is a **GAP**. In V3 arm A, **62% of losers went GREEN (peaks +10% to +100%+) then a single
tape tick craterred the quote 25–70% before any trail or floor could fire.** You cannot sell at a peak
that has no liquidity; the next available fill is already deep red. This is why the profit-lock (V4) barely
helped and the ratchet/rollover (V3 B/C) actively HURT — they take profit earlier and so cap the fat-tail
winners (V3-A peaked to 6.69×), and the tail is what pays for the gaps.

So the exit faces a genuine tension: trail wide → keep the 6.69× tail but give back the gappers; take
profit fast → bank the gappers but cap the tail. Every single-exit rule sits on one side of it.

## The V5 rule — SCALE-OUT (two legs) (FROZEN)

Break the tension by doing BOTH: bank a gap-proof gain on part of the position, ride the rest for the
tail. Entry is **identical to V3/V4** (net-replacement gates + break-even feasibility; veto removed).
Exit trails the executable full-position quote `ExitQuote(q,t)`, in two legs:

```
LEG 1 (scale-out): the FIRST tick where ExitQuote >= tp_level, sell `scale_frac` of the position at that
                   tick's reserves -> banks a gap-proof gain on that fraction.
LEG 2 (runner):    the remaining (1 - scale_frac) rides the 12% quote-trail (and the base capacity /
                   cluster-resume / horizon exits) exactly as the plain trail does.
realised R = scale_frac * R(leg1) + (1 - scale_frac) * R(leg2)
```

If `tp_level` is never reached, the WHOLE position rides the trail (leg-1 fraction = 0) — V5 then equals
the plain trail, so it can only differ on trades that actually went green. Each leg is priced curve-exact
by the ECR engine at its own tick; a leg-2 that cannot exit is booked at full loss (−1.0) for its
fraction (leg-1's banked gain stands). At most two legs — extra legs repeat network/priority-fee cost.

## The three arms (FROZEN — the scale-out isolated)

- **Arm A — TRAIL (baseline = V3-A / V4-A):** full position on the 12% quote-trail, no scale-out.
- **Arm B — SCALE-50:** sell `scale_frac = 0.5` at `tp_level = 1.50` (+50%), ride 0.5 on the trail.
- **Arm C — SCALE-100:** sell `scale_frac = 0.5` at `tp_level = 2.00` (+100%), ride 0.5 on the trail.

All arms share the identical entry; any divergence is attributable to the scale-out alone. Arms B/C
isolate the take-profit LEVEL. `+50%` and `+100%` are deliberately round; they are not the backtest max.

## Sizing & promotion (FROZEN)

Forward at the V1-comparable fraction until proven; the staged-$ / 20%-settled capacity-capped model is
the intended LIVE sizing, gated on V5 proving positive. An arm is a CANDIDATE only at N_min = 30 resolved
PASS, and REAL only if it also has positive log-growth after ALL costs, stays positive per UTC day AND
per creator-cluster, is not carried by a single ≥7× winner (drop-the-max robust), keeps the unexitable
rate under the B20B baseline, and survives a fresh hash-frozen confirmation slice. Below the minimum this
is BEHAVIOUR, not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, free data only. V1–V4 remain frozen.
The forward log is the sole arbiter; nothing here is a claim of profit.*
