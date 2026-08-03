# B15i finding: `minContextSlot` rejects, it does not wait

Recorded 2026-08-03, during the first live run of the B15i processed-commitment pilot.
The preregistration is **not amended** — it is frozen. This records what running it proved false.

## What the freeze claimed

`B15I_PROCESSED_FEED_PREREGISTRATION.json`, `checkpoint_geometry.min_context_slot`:

> "the getAccountInfo request carries minContextSlot equal to the target, so the node itself waits
> until it has reached the target rather than the client polling for it"

## What the endpoint actually does

147 of 147 requests in the first three minutes returned, in about 220 ms:

```
{"code": -32603, "message": "Min context slot not reached"}
```

`minContextSlot` is a **precondition the node checks and rejects on**, not a barrier it blocks on.
The belief was plausible, was written into a frozen document, and was wrong. It cost nothing but
the run that found it, because the run recorded a refusal per target rather than substituting a
current read.

## What changed, and what did not

The remedy needed no new rule. `B15F_CHECKPOINT_V1` already froze one, before any checkpoint was
ever taken:

```json
"context_before_target": "retry, bounded",
"max_attempts": 6,
"retry_interval_slots": 25
```

That is what now runs. Six attempts, twenty-five slots apart, and then a visible refusal.

- The **entry delays** are unchanged: 1, 2, 4.
- The **lateness tolerance** is unchanged: 150 slots, B15F's, compared against B15F's own document
  at startup by `assert_lateness_tolerance_unchanged`.
- **No response past the tolerance is admitted** by the retry budget. A late answer arriving on
  attempt six is refused `Q_LATE` exactly as one arriving on attempt one.
- Nothing was widened to make the pilot work.

Finalization lags about 31 slots, so attempt one is expected to fail and attempt three to succeed,
leaving a lateness near 15 slots — well inside 150, and inside it by measurement rather than by
adjustment.

## The pilot's primary question, answered

**Are 1, 2 and 4 slot entry targets reachable on a standard processed WebSocket? Yes.**

Across the first 49 launches, per delay:

| delay | targets | lead slots at scheduling (min/mean/max) | still future |
|-------|---------|------------------------------------------|--------------|
| 1     | 49      | 1 / 1 / 1                                | 49 / 49      |
| 2     | 49      | 2 / 2 / 2                                | 49 / 49      |
| 4     | 49      | 4 / 4 / 4                                | 49 / 49      |

Every target was still strictly future when it was scheduled — the lead equals the delay exactly,
meaning the CreateEvent notification arrived within the same slot as t0. Receipt to schedule was
7.8 ms at delay 1. B15h's `H_TARGET_MISSED` on 78 of 81 targets was a property of the polling
scheduler, not of the chain.

That answers the scheduling question only. It says nothing about returns, executability or
landing probability, all of which remain unmeasured and unpublishable here.
