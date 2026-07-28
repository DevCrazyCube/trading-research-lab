# B7i — Graduation-Anchor Recall Cross-Check Preregistration

**Frozen before any scan:** 2026-07-27
**Status:** FROZEN — awaiting Codex review. **No RPC call has been made under this preregistration.**
**Author:** Claude (owner of this file per `agent_discussion.md` Seq 55)

## Purpose

`docs/DEFINITIONS.md` terminal states **T1a (graduated and migrated)** and **T1b (completed, not yet
migrated)** rest on graduation anchors. B7h validated bonding-curve discovery recall for
`TradeEvent` **only**. This preregisters the identical cross-check for the graduation anchors.

**Deliberately narrow purpose (amended after Codex review).** An earlier draft said this would make
anchor-based lifecycle claims "stop resting on an untested path". That overclaimed and is withdrawn.
This test can, at most, establish anchor discovery recall **inside the 2,000 launch slots**. It
cannot close graduation status for the cohort, cannot validate B7e's zero-anchor observation through
the observation cutoff, and therefore does not by itself make any lifecycle claim safe. See the
scope section.

## Correction carried in from Seq 54

Seq 54 stated that B7e's zero-graduation observation "does not inherit" B7h's recall guarantee.
**That conclusion stands, but the reason given was partly wrong and is corrected here before
freezing.** I implied B7e searched only for `TradeEvent`. It did not:
`scripts/b7e_lifecycle_reconstruct.py` defines
`EVENT_NAMES = ("TradeEvent", "CompleteEvent", "CompletePumpAmmMigrationEvent")` and decodes all
three from every fetched transaction.

The accurate gap is narrower and subtler:

- B7e's candidate path **did look for** graduation events across the cohort and recorded none.
- B7h proved that path has complete recall **for `TradeEvent`**.
- Whether that path would have **surfaced a graduation event had one occurred** is untested,
  because B7h's reference extractor filters on the `TradeEvent` discriminator alone
  (`scripts/b7h_bonding_curve_recall.py`, `extract_trade_events`).

So the open question is not "did B7e look?" but "would B7e have found it?".

## Frozen scope

- **Block window:** `[429,998,000, 430,000,000)` — byte-identical to B7e and B7h. Not reselected.
- **Cohort:** the same 200 B7e mints, fixed by the completed launch database.
- **Event set — frozen, exactly two:**
  - `CompleteEvent`
  - `CompletePumpAmmMigrationEvent`
  Discriminators are **derived, never hardcoded**: `sha256("event:" + name)[:8]`, matched against
  the pinned IDL `research/pump_idl_9c82f61.json` (`idl_sha256 = b90bc471…8e49`, the same IDL used
  by B7e and B7h). `TradeEvent` is out of scope here; it is already settled by B7h.
- **Reference source:** exact pinned-IDL decoding of those two events from every retrievable block
  in the window, using the same Anchor CPI-tag path as B7h, and then **filtered to the exact 200
  cohort mints on the decoded `mint` field** — identical to B7h's `if fields["mint"] in cohort`.

  **This filter is mandatory, not incidental (amended after Codex review).** Both frozen events
  carry a `mint` field in the pinned IDL. Without the filter the reference side would be
  *program-wide* while the candidate side is *cohort-only*, so every non-cohort graduation event in
  the window would appear as a spurious "extra" and the bidirectional test would fail for a reason
  that has nothing to do with recall. An unfiltered reference set is a defect, not a stricter test.
- **Candidate source:** `lifecycle_event` rows in `research/b7e_lifecycle_429998000_430000000.sqlite`
  whose `event_name` is in the frozen event set and whose `slot` lies in the window.
  **This side requires no new RPC** — 13,900 in-window transactions already carry stored raw
  payloads, and B7e already decoded all three event types from them.

## Frozen comparison rule

Bidirectional exact equality on the key

```
(signature, mint, outer_instruction_index, inner_instruction_index, event_ordinal,
 event_payload_base64)
```

- Every reference event decoded from blocks must appear identically in the candidate set.
- Every candidate event whose slot lies in the window must appear identically in the reference set.
- Payload comparison is byte equality on the base64 payload, not field-wise equality.

**`event_ordinal` is included in the key (amended after Codex review).** B7e stores it, and although
every current row happens to be `0`, keying on it enforces schema parity between the two sides and
preserves canonical ordering if a single transaction ever emits more than one event of the same
type at the same instruction coordinates. Relying on "they are all zero today" would be an
assumption about data rather than a property of the key. The reference decoder must therefore emit
`event_ordinal` explicitly, assigned in decode order within each `(signature, outer, inner)` group,
rather than defaulting it.

## Frozen pass / fail / inconclusive rules

Decided now, before any count is observed:

1. **PASS** — the two sets are identical in both directions, payloads included, **and the reference
   set is non-empty**, and every slot in the window is either retrieved or independently verified
   skipped, and there are zero decode errors.
2. **FAIL** — any missing event, extra event, payload mismatch, decode error, or unexplained slot.
   Fails visibly; no conclusion published.

   **Decode-error semantics, made unambiguous (amended after Codex review).** The earlier phrase
   "unknown event schema" was ambiguous about which discriminators are in scope. The frozen rule:

   - An inner instruction carrying the Anchor CPI tag whose event discriminator **equals one of the
     two frozen discriminators**, but whose payload fails to decode against the pinned IDL — or
     decodes with trailing bytes — is recorded as a **visible decode error and FAILS the run**.
   - An inner instruction whose event discriminator is **anything else** (including `TradeEvent`,
     any other Pump event, or a discriminator absent from the pinned IDL) is **out of scope**: it is
     skipped silently and is neither a decode error nor a reference event. It is not this test's
     job to police unrelated events, and treating unknown-but-irrelevant discriminators as failures
     would make the run fail for reasons unrelated to graduation-anchor recall.
3. **INCONCLUSIVE — and this is the likely outcome, stated in advance so it cannot be spun later.**
   If the reference set is **empty** (zero graduation events in the window), the run does **not**
   pass. Two paths agreeing that nothing exists proves nothing about recall: a test with no positive
   instances cannot distinguish a working detector from a broken one. It will be reported as
   `INCONCLUSIVE — no positive instances in window`, and the graduation-anchor caveat stays open.

**Why an empty reference set is expected.** The window is 2,000 slots ≈ 13 minutes, beginning at the
cohort's launch. Graduation requires a curve to fill. B7e observed zero graduation events across the
full 23-day observation span for all 200 tokens, so the prior probability of one landing inside a
13-minute window at launch is low. This preregistration is still worth running because it is cheap
and because the alternative — assuming absence — is what the project's rules forbid.

## Window scope and the explicit non-inference (Codex review, incorporated before freeze)

**Two different spans must not be conflated:**

| Span | Slots | Purpose |
|---|---|---|
| **Launch window** `[429,998,000, 430,000,000)` | 2,000 | the frozen B7h/B7i cross-check window |
| **B7e lifecycle observation** launch → cutoff `435,570,000` | ≈ 5,572,000 | where B7e observed zero graduation events |

The cross-check window is **2,000 of ≈5,572,000 slots — about 0.036%** of the span over which B7e's
zero-graduation observation was made.

**Explicit non-inference. A PASS here does NOT license the statement "B7e's zero-graduation
observation is now trustworthy."** It would establish anchor discovery recall *inside the 2,000
launch slots only*. B7e's absence claim covers the whole 23-day span, and recall over 0.036% of it
does not validate the other 99.96%. Any future document that cites a B7i pass as support for
cohort-wide graduation absence is misusing it, and this paragraph exists to make that misuse
visible.

**Two further statements are prohibited by this preregistration, whatever the outcome:**

1. A launch-window PASS **cannot** validate B7e's zero-anchor observation through the observation
   cutoff `435,570,000`. The 5.57M slots between the launch window and the cutoff are untested by
   this design and remain untested after it.
2. A launch-window PASS **cannot close graduation status for the cohort.** Whether any of the 200
   tokens graduated at any point remains an open question after this run, in every outcome branch.
   Closing it requires evidence over the observation span, not over 0.036% of it.

**Consequence for expectations, stated before running.** Combined with the vacuity rule above, the
realistic outcomes are:

- most likely **INCONCLUSIVE** (no graduation events in a 13-minute window at launch); or
- at best a **PASS with 0.036% coverage** of the span that actually matters.

Neither closes the graduation-anchor question. This is recorded now so that the run's limited value
is understood in advance rather than discovered afterwards, and so the decision to run it at all is
made with that knowledge. The genuinely decisive test is a preregistered window containing positive
instances — see the contingency below — not this one.

## Preregistered contingency (NOT authorised by this document)

If the result is INCONCLUSIVE, the next step is a **separately preregistered** window chosen to
contain positive instances. Its selection rule must be frozen before inspection, and it must not be
chosen by looking for windows that produce a convenient answer. Candidate rule, recorded now so it
cannot be reverse-engineered later: *the smallest contiguous slot range containing the first N
`CompleteEvent`s emitted by the Pump program after the cohort launch window, N frozen in advance,
selected by program-wide scan rather than by cohort membership.* **That scan is not authorised
here and must not be run under this preregistration.**

## What this can and cannot establish

**Can:** whether the bonding-curve-history discovery path surfaces graduation anchors that exist in
blocks, for this window and this program regime.

**Cannot:**
- Prove anything if there are no positive instances (see rule 3).
- Exclude **decoder common-mode failure.** Both sides use the same pinned IDL and the same decode
  logic, so an unrecognised or mis-parsed graduation-event layout would be missed identically by
  both and would still report agreement. This is the same limitation recorded in
  `research/B7H_BONDING_CURVE_RECALL.md`.
- Establish T1b duration, graduation rates, or any lifecycle label. Anchor **recall** only.
- Generalise beyond this window or past a program upgrade.

## Gates

Read-only RPC only. No signing, no spending, no deployment, no live or devnet transactions. The
endpoint is sourced silently from the ignored `.env` and is never printed or persisted. The B7h and
B7e artifacts are inputs and will not be modified.
