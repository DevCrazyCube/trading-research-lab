# History collection contract — v1.0.0

Enforced by `scripts/b13e_collection_contract.py` against the frozen
`research/B13E_LOOKBACK_PREREGISTRATION.md`.

Status: **contract only. Nothing has been collected.** No RPC has been called, B11a has not been
unlocked or enumerated, and this module contains no code path that could reach a network.

## Two commits, in order, and why

The preregistration was committed **alone** and first. The validator came second. A parameter
committed alongside the machinery that consumes it can always be claimed to have been adjusted until
the machinery worked, and the git ancestry is the only evidence that it was not — so a test asserts
that the document's commit is an ancestor of this module's.

## The lookback: 1,642,509 slots

```
LOOKBACK_SLOTS = B9D_CUTOFF_SLOT − B8B_WINDOW_START_SLOT = 435,536,742 − 433,894,233
```

The same quantity B11a already inherited as `observation_span_slots`. **Reused, not chosen**: the
only histories available to look at are the burned ones, whose outcomes are already measured, so
there is no free parameter here to tune.

**Never translated to wall-clock time.** `hours_of_lookback()` exists and raises. Slot production
varies, so a wall-clock lookback is a different number of slots on every day it is applied, and a
parameter whose length depends on network conditions is not frozen.

## The window, per decision

```
lookback_start_slot = max(0, t0_slot − 1,642,509)

E is in the window  ⟺  lookback_start_slot ≤ E.slot                          (SLOT-wise)
                   AND  (E.slot, E.tx, E.outer, E.inner) ≤ t0's coordinate   (COORDINATE-wise)
```

**The asymmetry is the point.** The upper bound is a *leakage* boundary and must be exact to the
instruction — inclusive at t0, exclusive one coordinate later. The lower bound is a *coverage*
boundary at slot granularity: half a slot of lookback is not a meaningful quantity, and a
coordinate-exact lower bound would make the window's length depend on where inside a slot the
decision fell, so two decisions one instruction apart would get measurably different histories.

**Near genesis** the start clamps to 0 and `clamped_at_genesis` is set. A clamped window is shorter
than the lookback; reporting it complete would claim knowledge of a period before the chain existed.

**A short source reports incomplete and never shifts the start.** Moving the start up to whatever a
provider happened to have would redefine the parameter per actor, and the actors with the least
history would get the shortest window — precisely backwards.

## Where the lookback reaches

| decision at | starts at | relation to burned territory |
| --- | --- | --- |
| 435,569,150 (first fresh launch slot) | 433,926,641 | deep inside it |
| 437,211,659 (observation cutoff) | **435,569,150** | exactly one slot after the last burned slot |

The second row falls out of reusing the observation span; nobody arranged it. A test pins the
relationship so that changing either constant breaks visibly.

Note the corollary: **the slot immediately before the fresh window is itself burned**, since B11a
starts one slot after the maximum burned endpoint. Anyone reaching for "just before t0" as an
unburned fixture gets a burned one.

## Burned data: context yes, evidence no

Two checks against two different things, deliberately not collapsed into one.

| role | permitted | why |
| --- | --- | --- |
| `prior_context` | **yes** | it genuinely happened before the decision |
| `evaluated_subject` | no | its outcome has already been measured |
| `label_source` | no | R3 |
| `tuning_data` | no | the answers are already known |
| `performance_evidence` | no | it would be measured on data already used |

**A burned curve may appear in a FEATURE and may never appear in a METRIC.**

Excluding burned context *entirely* is its own error, and `assert_context_not_excluded` names it: a
creator who demonstrably launched during a burned range must not be reported as having none. That
zero would be a collection artefact presented as a fact. The function takes the retained set as an
argument rather than recomputing it, so the check is against what a caller actually kept.

## Cohort, unlock and access

- **Exactly B11a's enumeration.** Wider selects on whatever the broader population contained;
  narrower selects on collectability, which correlates with activity. An empty enumeration is not
  permission to collect broadly.
- **Nothing before unlock.** `assert_unlocked` requires B11a maturity and its **U3** criterion.
  Before that the cohort is unknown, so a run that queried anyway would have chosen its own
  population.
- **`QueryGuard` is permission, not a client.** It holds no endpoint, opens no socket, and the only
  thing it can do is refuse. A test asserts the module imports nothing that could reach a network.
- **Method allowlist**, not a denylist — the next client version adds a method nobody thought to
  forbid. Read-only `get*` methods only; anything that submits, signs or mutates is permanently out.
- **Credentials are refused, not redacted.** A redaction that fails silently looks exactly like one
  that worked.

## Coverage: per actor, never averaged

`cohort_completeness` returns a verdict per actor and one overall boolean that is an **AND**, never
a mean. An average is exactly the statistic that hides the single actor whose history is missing, so
there is no percentage to pick — picking one would require averaging. `coverage_fraction()` exists
and raises.

Per-actor failure codes reuse the abort vocabulary: `AB03` pagination not exhausted, `AB04` coverage
short, `AB05` decode loss at or before t0, `AB07` source hash drift, `AB09` raw not preserved,
`AB10` a start that the formula did not give.

**Pagination exhaustion must be proved.** A page cap is not exhaustion, and neither is an unconsumed
cursor. A silent cap is the failure mode that produces a confidently wrong zero.

**Decode accounting travels with every coverage record** and its partition is asserted, not trusted.

**Snapshots must be atomic at one slot.** Balances read across a range are not a snapshot of
anything: a transfer between two reads can appear twice or vanish, and neither shows up as an error.

## What is pinned, and what is cross-checked

The document's hash pins every parameter. Beyond that, exactly one class of value is re-checked in
code: **anything the code holds its own independent copy of** — the lookback, its two operands, and
the burned-role table. Those can disagree with the document without the document changing, because
the *other* side can move.

Values only the document states (the cohort source, the averaging ban, the unlock criterion) are
**not** re-read in code. A second check on a value the hash already fixes could never fire, and a
check that cannot fire is worse than no check.

## Abort conditions

`AB01`–`AB11`, declared identically in the document and in code, and a test asserts the two lists
are equal.

## Not covered

- Any collection, query, enumeration or credential.
- Any cluster, probability, threshold, score or label.
- B11b's frozen no-model baseline evaluation, which this contract does not alter.
