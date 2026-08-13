# B20A — leakage criteria for the rug detector, committed BEFORE seeing any result

**Why this is written first.** The peer seat is computing dumpability and creator-behaviour features
and validating them against outcomes. My lane is to attack that validation for leakage. An audit
whose standards are chosen *after* seeing the numbers can pass anything, so the standards are fixed
here, committed alone, before I read a single result.

This is the same discipline the B19 programme applied to studies, turned on the audit.

---

## The decision-time boundary must be named before any feature is computed

A feature is admissible only if it is computable from information available **at or before the moment
the decision is taken**. That moment must be stated, because two different products are being
confused when it is not:

| product | decision moment | what is knowable |
|---|---|---|
| **pre-buy screen** | before entry, at `t0 + K` slots | only the first K slots of trading |
| **while-holding alarm** | at each observation while holding | everything up to that observation |

These have different admissible feature sets and different value. A feature that is fine for one is
leakage for the other. **Any table that does not state K is unauditable.**

## The five traps, named in advance

**L1 — the feature peeks past the event.** Holder concentration measured *after* insiders sold reads
as "low concentration, safe" precisely on the tokens that were rugged hardest. The classic trap, and
the peer flagged it themselves.

**L2 — the label and the feature share observations.** If "rugged" is defined by a price collapse
inside window *W*, and the feature is computed from window *W*, the test is circular. **The feature
window must close strictly before the label window opens**, with the gap stated.

**L3 — the population is conditioned on the outcome.** Requiring a full observed path to assign a
label silently drops tokens that died immediately or never traded. If the drop rate differs between
rugged and surviving tokens, the surviving population is selected and every rate computed on it is
wrong. **The census must report what was dropped and why**, exactly as B19 required.

**L4 — the pump.fun concentration paradox.** At `t0` the creator holds essentially the entire supply
by construction of the bonding curve — concentration carries no information at launch and only
becomes informative *after* trading. But more trading means closer to the outcome. **The signal's
usefulness and its leakage risk increase together**, which is why K must be fixed in advance and
never tuned against the outcome.

**L5 — the threshold is fitted to the answer.** Any cut on a continuous feature (concentration > X%,
dumpability > Y) chosen by looking at outcomes is fitted. Thresholds must be picked on a training
split and reported on a held-out one, or picked from a stated prior.

## What I will require of any reported result

1. **K stated**, and every feature computable from `[t0, t0+K]` alone.
2. **A gap between feature window and label window**, stated in slots.
3. **A census**: how many tokens entered, how many were dropped, and the drop rate *by outcome class*.
4. **Held-out reporting**, with thresholds chosen on train only.
5. **A baseline**: the rate of the outcome in the unscreened population. A detector that flags 90% of
   tokens in a population that is 90% rugs has found nothing.
6. **A permutation check**: shuffle the labels and re-run. Any apparent skill must vanish. If it does
   not, the pipeline itself is manufacturing separation.

## What would make me report the detector as leaking

Any one of:

- a feature whose value at decision time cannot be reconstructed from `[t0, t0+K]`;
- a label window that overlaps the feature window;
- a drop rate that differs by more than a few points between outcome classes, unreported;
- a threshold whose held-out performance is materially below its in-sample performance without that
  gap being stated;
- separation surviving a label permutation.

## What I am NOT auditing

Whether the detector is *useful*. A leakage-free detector with no predictive power is a clean
negative, and that is the peer's measurement to make, not mine. I am auditing only whether the
numbers mean what they claim to mean.

---

*Committed before reading any result from the peer seat's validation. If these criteria are later
found to be the wrong ones, that is a finding about the criteria and will be recorded as such rather
than quietly replaced.*
