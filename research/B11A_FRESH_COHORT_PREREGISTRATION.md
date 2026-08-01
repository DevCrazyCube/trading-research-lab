# B11a — first fresh evaluation cohort, preregistered before inspection

Date: 2026-08-02. Author: Claude (handoff 68).
Machine-readable freeze: `research/B11A_FRESH_COHORT_PREREGISTRATION.json`.

```
file      sha256 = 5faabb33ad317240824450a9b8a3a4026137a04e4457b4767e95488a5c469ac0
canonical sha256 = ae4d2f0351aaba193fe7d87cde8cd68ce83aa8d21515d4d20af0a158f8dafe9f
```

The canonical hash is over `json.dumps(document, sort_keys=True, separators=(",", ":"))`, so it
survives reformatting; the file hash pins the committed bytes. Both are recorded because a
reformatting that preserved meaning should not read as tampering, and a byte change that preserved
formatting should not read as innocent.

**This document and the JSON were committed alone, before any chain or RPC query of any kind.** That
ordering is the whole point: a window fixed after looking is not a preregistered window.

## Why this exists

Every cohort this project has built so far is burned. `DECISIONS.md` R3 requires *"a fresh
preregistered window disjoint from every burned range"* before any label may be measured or tuned,
and B10c established in code that the current corpus **is** the burned B8b cohort. There is
therefore no window in this project on which a model could honestly be evaluated. This freezes one.

## The window is derived, not chosen

Every endpoint is a formula over numbers already on the record. **No candidate window was inspected
and rejected**, and nothing below was adjusted for yield, market regime, current activity, outcomes,
convenience or collection cost.

### Step 1 — the burned-range register, normalised

A half-open source range `[a, b)` normalises to inclusive `[a, b-1]`. Where a document's burn
statement is wider than the code range it describes, **the wider statement governs** — B7b's code
scanned `range(435566652, 435566690)` but its burn statement reads *"Slots 435,566,652 – 435,566,690
are BURNED"*, and the conservative reading is the one that keeps a slot out of evaluation.

| origin | source | inclusive `[first .. last]` |
| --- | --- | --- |
| B7e mature cohort | `[429,998,000, 430,000,000)` | 429,998,000 .. 429,999,999 |
| B7d engineering pilot | `[430,000,000, 430,000,500)` | 430,000,000 .. 430,000,499 |
| B8a cohort | `[433,302,364, 433,304,364)` | 433,302,364 .. 433,304,363 |
| B8b cohort (= the B9d/B10b/B10c corpus) | `[433,894,233, 434,097,833]` | 433,894,233 .. 434,097,833 |
| B7j/B7k positive-control envelope | `[435,564,885, 435,565,324)` | 435,564,885 .. 435,565,323 |
| B7b dead-threshold sample | `435,566,652 – 435,566,690` | 435,566,652 .. 435,566,690 |
| B7c trade-only gap sample | `435,569,119 – 435,569,149` | 435,569,119 .. 435,569,149 |

**Maximum inclusive endpoint: 435,569,149** (B7c).

### Step 2 — the four endpoints

| quantity | formula | value |
| --- | --- | --- |
| launch start | `max(inclusive_last) + 1` | **435,569,150** |
| launch span | `B8b_end_inclusive - B8b_start + 1` | 203,601 slots |
| observation span | `B9d_cutoff - B8b_start` | 1,642,509 slots |
| launch end (inclusive) | `start + launch_span - 1` | **435,772,750** |
| observation cutoff (inclusive) | `start + observation_span` | **437,211,659** |

Sources for the two inherited spans are artifact metadata, not prose: `window_start_slot` /
`window_end_slot_inclusive` in `research/b8b_cohort_433894233_434097833.sqlite`, and `cutoff_slot`
in `research/b9d_transaction_bodies.sqlite`.

Disjointness is checked for **both** the launch window and the full observation span
`[435,569,150 .. 437,211,659]` against all seven ranges: **no intersection**. It is trivially true
here because every burned range ends at or below the launch start, but it is checked rather than
argued, and the checker fails closed.

### Why the spans are inherited in slots, not re-derived from wall-clock

Re-deriving "24 hours" or "8 days" from a slot rate would make the window's size depend on how fast
the network happens to be running — a property of the very regime being evaluated, and one that
moves. Inheriting the **slot span** from B8b/B9d removes that dependence completely. The cost is
that the fresh launch window is the same 203,601 slots as B8b rather than the same wall-clock
duration; that is the intended trade.

## What is frozen besides the endpoints

- **Regime.** Direct Pump bonding curve, SOL-paired, non-Mayhem, curve open at the decision instant.
  PumpSwap is not an entry venue and a completed curve is structural exit-unavailability, never
  valued through PumpSwap. Membership is fixed at `CreateEvent` (C3) and exhaustive within the
  launch window (C4) — no filtering on creator, name, reserves or anything else, because a filter is
  a decision-time policy, never a sampling step.
- **Program-version boundary policy.** No loader `Upgrade` slot for either the Pump or the PumpSwap
  program may fall inside the launch window or the observation span. B0 measured a roughly 13-day
  upgrade cadence and this window spans about 8.5 days of slots, so the constraint is **tight and
  must be verified at preflight, not presumed.** A violation aborts and is reported as a regime
  split; the window is not moved, shortened or pooled.
- **Identity/group split floor.** At least `creator ∪ user` (R5), with `creator`, `create_user` and
  `t0_user` required at t0. Funding-cluster leakage is an unmeasured superset and **remains an open
  gate** — meeting this floor does not close it.
- **Label horizons.** The four B10c horizons, unchanged, carried verbatim from
  `B10C_PREREGISTRATION_PLUMBING.json`, which carried them unchanged from the B10b plumbing run. No
  horizon anywhere in that chain was chosen after seeing a label distribution.
- **Observation maturity.** The finalized tip must reach 437,211,659. Retrievability from the
  provider is a **separate** condition: a provider gap is a recorded gap under C5, never a reason to
  shorten the window.

## B10c's enum is deliberately NOT extended here

`scripts/b10c_outcome_labels.py` still accepts only `window_status: burned_development`, and must
keep refusing `fresh_preregistered` until a separate `DECISIONS.md` entry records that models,
horizons and thresholds were frozen first.

Extending it now would open a path to revealing this window's labels before anything is frozen
against them — which is precisely the failure this document exists to prevent, and it would be a
strange way to celebrate having finally obtained a clean window. A test pins the refusal.

## Abort branches

| id | condition | action |
| --- | --- | --- |
| A1 | overlap with any burned range | abort; **never shift** — a shifted window is a chosen window |
| A2 | program upgrade boundary inside the window or span | abort, report as a regime split; do not relax, move, or pool |
| A3 | cutoff not yet mature | wait, report the exact remaining slots; **do not move or shorten** |
| A4 | recorder or provider gap over a member's lifetime | flag incomplete under C5; never substitute or silently drop |
| A5 | any frozen endpoint would change after commit | forbidden; requires a new preregistration with a new id, and this window is then burned |
| A6 | no window satisfies every constraint | a reportable finding, not a licence to relax one |
| A7 | any composition, census, yield, label or return figure computed before models/horizons/thresholds are frozen | **the window is burned** and must be recorded as such |

## Prohibited inferences

- **No composition query at or before preflight.** `getSlot` is permitted.
  `getSignaturesForAddress`, `getBlock`, and anything that reveals what is *in* the window are not.
- **No return, label, census, yield, regime-split or actor-concentration figure** on this window
  until models, horizons and thresholds are frozen and recorded.
- **No re-placement or resizing** for yield, regime, activity, cost or outcomes.
- This document authorises **no** model research, live execution, signing, spending, or paid data
  subscription.

## Status

This is a freeze, not a result. It contains no measurement of the window it describes, and by
construction it cannot: nothing had been queried when it was committed.
