# AFTERSHOCK V4 — PROFIT-LOCK — pre-registration

**Instrument:** `AFTERSHOCK_V4` — a **PAPER**, free-data-only, forward-only memecoin arm. NEW frozen
instrument, own registry + ledger. **V1, V2, V3 stay frozen and untouched.** Event-driven off the tape.

**HARD LIMITS (enforced in code):** NO orders, NO wallet, NO real SOL, NO on-chain writes, NO paid
account. Free data only. Real trading is a separate, owner-gated wallet decision.

**Freeze intent:** thresholds frozen BEFORE the first V4 datum; `aftershock.frozen` refuses on prereg
hash mismatch. An improvement is a NEW instrument (V5, …), never an edit.

**Honesty about where this came from.** The V4 rule is MOTIVATED by a diagnostic of V2/V3's own plain-
quote-trail trades, but its parameters are deliberately ROUND a-priori numbers, not an optimum tuned to
those trades. The diagnostic finding (below) is the hypothesis; only a FRESH forward slice — plus the
per-day / per-cluster / drop-max / fresh-confirmation promotion gate — adjudicates it. No grid search is
frozen as the rule.

---

## The diagnostic that motivates V4

Across the pooled plain-quote-trail winners/losers (V2 arm C + V3 arm A, ~57 trades):
- **Winners peak high (~2.4× the entry quote) and sustain (~2.3 min held).**
- **71% of LOSERS went GREEN first** (peak quote > 1.0 — some to +40%, +100%, +309%) **then round-tripped
  all the way to a loss**, resolving fast (~16 s held). Their peaks cluster at 1.02–1.23: a trade that
  peaks at +10% but is exited by a 12% trail fills at `0.88 × 1.10 = 0.968` — a LOSS. The trail is too
  wide to protect a modestly-green trade, so green gains bleed back to red.

So the residual loss is an EXIT failure, not an entry failure. The fix must stop green trades from
round-tripping to a loss **without capping the sustained runners** (the ratchet/rollover harvest in V3
did cap them — arms B/C underperformed the plain trail, so V4 drops them).

## The V4 rule — break-even PROFIT-LOCK (FROZEN)

Entry is **identical to V3**: net-replacement gates (NRR ≥ 1, full recovery, coverage ≥ 10, k60 < 0.95,
≥3 new buyers, stabilization) + the break-even feasibility gate; the redundant entry-flow-veto stays
removed. Exit trails the executable full-position quote `ExitQuote(q,t)` (=curve-exact net proceeds of
selling the whole position now; 0 if unsellable), with a one-way profit floor added:

```
peak = highest ExitQuote since entry
armed = peak >= lock_arm          # the trade has gone clearly green
EXIT when the FIRST of:
  • armed AND ExitQuote <= lock_floor   -> PROFIT_LOCK   (a green trade may not bleed below the floor)
  • ExitQuote <= (1 - trail_frac) * peak -> QUOTE_TRAIL   (the runner's trailing exit; 12%)
  • ExitQuote = 0 OR coverage < buffer  -> CAPACITY_BREAK
  • cluster wallet resumes selling      -> CLUSTER_RESUME
  • hard horizon                        -> MAX_HOLD
```

The floor is a FIXED quote level, not a proportional trail — so a runner that peaks at 2.4× exits on the
12% trail far above the floor and is untouched; only a trade that fades back toward break-even is caught
at a small locked profit. This is why it protects the losers without capping the winners.

## The three arms (FROZEN — the profit-lock isolated)

- **Arm A — TRAIL (baseline = V3 arm A):** plain 12% quote-trail, no floor.
- **Arm B — LOCK:** arm A + profit-lock, `lock_arm = 1.05` (arm once +5% green), `lock_floor = 1.02`
  (a green trade cannot exit below +2%).
- **Arm C — LOCK-EARLY:** arm A + profit-lock, `lock_arm = 1.02`, `lock_floor = 1.01` (arms sooner, on a
  smaller green blip; catches more modest-green trades but risks exiting a dip-then-run earlier).

All arms share the identical entry, so any divergence is attributable to the profit-lock alone.

## Sizing & promotion (FROZEN)

Forward at the V1-comparable fraction (`bankroll_sol × position_fraction`) until proven; the staged-$ /
20%-settled capacity-capped model is the intended LIVE sizing, gated on V4 proving positive. An arm is a
CANDIDATE only at N_min = 30 resolved PASS, and REAL only if it also has positive log-growth after ALL
costs, stays positive per UTC day AND per creator-cluster, is not carried by a single ≥7× winner (drop-
the-max robust), keeps the unexitable rate under the B20B baseline, and survives a fresh hash-frozen
confirmation slice. Below the minimum this is BEHAVIOUR, not evidence.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, free data only. V1/V2/V3 remain
frozen. The forward log is the sole arbiter; nothing here is a claim of profit.*
