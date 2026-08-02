# B13a — point-in-time actor and token history, and the plan for collecting it properly

Date: 2026-08-02. Author: Claude (handoffs 78, 80). Offline library and report only.
Code: `scripts/b13a_history.py`, `scripts/b13a_history_corpus.py`.
Schema: `docs/HISTORY_SCHEMA.md`. Tests: `tests/test_b13a_history.py`.

## 0. Scope, and what was not touched

Plumbing only. **B11a was not queried, enumerated or read**, B11b and B12a/b are unchanged, no
model or baseline exists, and no threshold was chosen. No feature distribution, correlation or
label association has been computed on any window, including the burned one.

## 1. Why a history is the most dangerous artifact here

Everything in it is about the past, so nobody thinks to check the boundary. One event on the wrong
side of t0 turns a feature into a peek at the answer — silently, in a field that will still be there
three phases later, long after anybody remembers how it was built.

So the module is organised around one rule and the naming that keeps its results honest.

## 2. The boundary, stated and published

An event enters if and only if its canonical coordinate `(slot, transaction_index, outer_index,
inner_index)` is **at or before** t0's. Inclusive at t0, exclusive one coordinate later. Insertion
order is never consulted. The rule travels on every record in `boundary_rule`, and a record carrying
any other text is refused.

**One judgement I want audited.** A looser reading would admit the remainder of t0's own
transaction, since that transaction completes before any order of ours could land — which is exactly
B10b's transaction-terminality argument. I took the **stricter** reading: an event wrongly dropped
costs information, an event wrongly admitted costs correctness. The difference only affects other
actors' events sharing t0's transaction; for the subject curve the two coincide, because t0 is
already that curve's transaction-terminal state.

## 3. Every count is a lower bound, and its name says so

A bounded window cannot know what happened before it opened. `prior_launch_count_observed == 0` is a
fact about the window, not the claim "this creator has never launched before" — and the second
dressed as the first would turn a collection artefact into a feature that looks like knowledge.

- every count ends in `_observed`; a test refuses any field name that states a total;
- `counts_are_lower_bounds` is published per section and asserted equal to `coverage.left_truncated`;
- `actor_seen_in_window` separates "seen and did nothing" from "not seen at all";
- `require_complete_history` **fails closed** for any policy that needs a true count. Building a
  history over a truncated window is fine; using one as though its counts were totals is not, and
  that has to be an explicit act rather than an omission.

## 4. What the sections contain

Creator, user, token and funding, each with declared and disjoint identity and feature blocks, and
**no string anywhere in a feature block**.

Direction is kept exact and separate throughout — buys and sells, quote and token, inbound and
outbound funding — because a net figure hides a wallet that cycled a hundred SOL through one curve
behind one that never traded.

Self-inclusion is prevented: a creator's prior launches are strictly before the subject's own, and a
completion counts only for a token that creator launched. `completed_before_t0` means exactly that.

**Funding edges are raw.** Direction, source, destination, amount, coordinate, provenance — and
nothing joined into an entity. Cluster inference and confidence are a later task and
**funding-cluster leakage remains an open gate**. A `cluster_id` in this record would be a judgement
wearing the costume of a fact.

## 5. A defect the subject-consistency check found immediately

The subject's declared creator must match its launch event's, and likewise its bonding curve. A
caller passing the wrong creator would otherwise get a perfectly well-formed history full of zeros —
the most convincing possible way to be wrong, because nothing about the record would look unusual.

**The check caught my own test fixture disagreeing with itself the moment it was added**: the
fixture named a bonding curve the launch helper did not generate. That is the argument for the
check; the same mistake in a caller would have produced silent zeros.

## 5b. The seam handoff 80 closed — untruncated geometry is not completeness

Codex's review found a blocking defect before B13b, and it was a real one. Section 3 above argues
carefully that a bounded window cannot know what preceded it — and then measured completeness
purely as **window geometry**. That equates "the window has the right shape" with "everything
inside it was read". A payload the extractor cannot decode produces no event, and an absent event
is indistinguishable from an event that never happened. The exact confusion this module exists to
prevent, one level below where it was being checked. A funding edge lost to a decode failure does
not announce itself; it shows up later as a cluster that isn't there.

**Sums, not counters.** Every coverage now carries a `decode_accounting` that must partition
exactly three ways — transactions, System instructions, and lamport-moving instructions. A counter
can be forgotten at one `continue`; a partition that must add up cannot be, because the arithmetic
fails the moment an instruction falls out of the accounting. Evidence that was *lost* rather than
absent is listed in `unresolved` with a full coordinate, one of four declared reason codes and a
detail, and the list length must equal the count the partitions imply.

`complete = True` is now refused while anything is unresolved, whatever the geometry says.

**The poisoning boundary is per subject.** An unresolved instruction at or before a subject's t0
poisons that subject, because the edge it would have produced is precisely the one its history is
missing. One after t0 does not, because it cannot have removed anything that decision could have
seen. Poisoning every subject for a failure none of them could have seen would be fail-closed in
form and useless in substance.

### A production bug the pinned fixture found, which the corpus never would have

Writing a test that pins a genuinely undecodable payload exposed a crash on the path that was
supposed to record one:

```python
except B9D.FreezeViolation as error:     # never matches
except B9J.FreezeViolation as error:     # the class actually raised
```

Every module here loads its own dependency graph by path, so `b9j`'s `FreezeViolation` reached
directly is a **different class object** from the one reached through B13a's chain. The `except`
silently matched nothing, and an undecodable payload would have escaped as an unhandled crash
rather than being recorded as unresolved evidence.

The burned corpus would never have caught it. A full survey of the b9j artifact — **94,985
transactions, 412,028 System instructions** — contains exactly **two** undecodable payloads, both
padded `CreateAccount` bodies (52 of 56 bytes decoded, 4 trailing) in signature
`5nYDQmEz8Zdj…xY4U` at coordinate `(433968746, 858)`, outer 2 / inner 0 and outer 2 / inner 2.
Neither is in the 60-curve slice, so the gate reports `undecodable: 0` and always would have. Two
in 412,028 is exactly the density at which a corpus run proves nothing and a pinned fixture proves
everything. The two coordinates are now pinned in the tests, along with an assertion that the two
`FreezeViolation` classes really are distinct — otherwise the test would pass again the day the
loader changed and the bug came back.

Two failure buckets have never occurred in real data at all: a lamport-moving transfer whose
endpoints are not in its account list, and a self-transfer. The classification was extracted into a
pure `classify_moving_instruction` so both can be driven directly, and the two transaction-level
failures are driven against an in-memory database holding a coordinate with no body, and no
coordinate at all. A path that never runs is a path nobody notices breaking.

## 6. Measured — plumbing integrity on the burned B8b corpus

```
python scripts/b13a_history_corpus.py research/b9d_transaction_bodies.sqlite \
    research/b10b_observed_paths.sqlite --gate --limit 60 --subjects 25
```

| quantity | value |
| --- | --- |
| launch events (whole corpus) | 1,136 |
| completion events (whole corpus) | 16 |
| trade events (bounded slice) | 7,718 |
| **funding transfer edges** (bounded slice, decoded from the pinned System ABI) | **35,568** |
| total events, all distinct | 44,438 |
| subjects checked | 25 |
| boundary respected | **25 / 25** |
| identity kept out of features | **25 / 25** |
| result independent of arrival order | **25 / 25** |
| errors | **0** |
| System instructions accounted for (bounded slice) | **36,869 = 35,568 moving + 1,301 non-moving + 0 undecodable** |
| transactions accounted for | **7,712 = 7,712 with body + 0 missing body + 0 missing coordinate** |
| unresolved evidence | **0** |
| completeness refused for every subject | **25 / 25** |

The last row is the point. The window is truncated by construction, so no subject's history rests
on complete evidence and every one of them refuses a policy that would need a true count. The
accounting says the refusal is about geometry alone — nothing in this slice was lost.

**No feature value appears in that report and none may.** A history is one join away from an
outcome, and a distribution inspected here is a transform chosen with the answer in view. The
numbers above count events and checks, never what those events say about anybody.

Funding edges come from `b9j`'s pinned System ABI with the two addresses taken from the
instruction's own resolved account list. Nothing is inferred: a transfer of N lamports from A to B
is exactly that, and whether it is funding, a tip or a refund is not something this module claims to
know.

## 7. Verification — 54 mutants, 52 killed, two disclosed

89 tests, 240 subtests.

Covering every failure mode named in the directive: boundary equality (4), past outcome after t0
(1), self-inclusion (2), left truncation treated as zero (5), identity leakage (3), duplicate events
(1), creator/user role confusion (3), funding direction reversal (3), flow direction (1), source
hash drift (3), insertion-order dependence (2), record contract (3).

**Three survived the first run and every one was a genuine gap:** no test distinguished a completion
belonging to *another* creator; the identity/feature disjointness check read module constants and so
could never fire; and no fixture placed two events at an identical coordinate, so the hash tiebreak
that makes ordering deterministic was untested. All three now have tests, and the disjointness check
takes its field sets as arguments so it is reachable.

The handoff-80 sweep added 23 mutants on the completeness seam: each of the three partition sums,
the unresolved-list length check, coordinate and reason-code validation, the refusal to claim
completeness with anything unresolved, each of the four `C0x` codes, the poisoning boundary made
exclusive and made slot-only, a failure after t0 made to poison, the transaction-level sentinel
moved inside the transaction, each accounting bucket silently skipped, and the wrong
`FreezeViolation` class.

**Six survived the first run of that batch and five were genuine gaps**: `assert_coverage` required
the accounting field without validating it; `completeness_failures` was never driven with the
accounting absent; the code assertions checked membership in the declared set rather than which
code was reported; and the two never-observed moving buckets and the two transaction-level failures
had no test at all. All five now have tests, and the moving classification became a pure function
so it can be driven without a database.

**Two equivalent mutants, disclosed rather than removed.** Deleting `assert_history` from
`build_as_of_history`, and deleting the extractor's own `assert_decode_accounting` before it
returns, both change nothing observable: in each case the data is assembled internally from
already-validated input, so no caller input can make the self-check fire. Both functions are
separately and thoroughly tested when called directly. They are kept because they would catch a
future edit that adds a field or a `continue` without updating the contract — the exact class of
error they exist for. This is a different judgement from the b10b case, where an unreachable check
was **deleted**: that one could never fire for any future edit either, whereas these two fire the
moment the code around them changes.

## 8. The cohort-based collection plan, specified now and not yet executed

**Nothing below may be run until B11a's enumeration unlocks**, and none of its parameters may be
chosen by looking at any observed history.

1. **Cohort first, histories second.** Histories are collected **only for the actors and tokens that
   B11a's own enumeration produces** — its creators, its launch signers, its t0 traders and its
   mints. Collecting histories for a wider population and then filtering would be selection on
   whatever the wider population happened to contain.
2. **The lookback is preregistered before it is measured.** A lookback chosen after seeing how far
   back actors' histories happen to run is a lookback chosen for its results. It must be frozen in
   its own preregistration, expressed in **slots** (not wall-clock, for the reason B11a gives), with
   its rationale drawn from operational meaning or a prior document — never from an observed
   history. **It is deliberately not chosen in this document.**
3. **A completeness gate, stated in advance.** The preregistration must state what fraction of
   cohort actors need a history reaching the full lookback for the collection to count as complete,
   and what happens when it does not: report and stop, never silently proceed with a shorter
   lookback for the actors that lack one. An actor whose history does not reach the lookback is
   **left-truncated**, its counts stay lower bounds, and `require_complete_history` fails closed for
   any policy needing totals.
4. **Coverage is published per actor, not per cohort.** One actor's complete history does not make
   another's complete, and a cohort-level average would hide exactly the actors whose history is
   missing.
5. **Funding-cluster inference stays out.** Edges are collected; entities are not resolved. Cluster
   inference, its confidence, and the leakage it introduces are a separate task with its own gate.
6. **No history may be inspected before the labels are.** Collecting histories for the B11a cohort
   and looking at their distributions would choose transforms with the answers one join away —
   which is the same failure the B11b feature contract was frozen to prevent, arriving through a
   different door.

## 9. Not claimed

No model, no baseline, no threshold, no cluster, no feature distribution, no correlation, no label
association. No operational readiness. The counts in this document are counts of events and checks.
