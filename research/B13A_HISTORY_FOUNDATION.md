# B13a — point-in-time actor and token history, and the plan for collecting it properly

Date: 2026-08-02. Author: Claude (handoff 78). Offline library and report only.
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

**No feature value appears in that report and none may.** A history is one join away from an
outcome, and a distribution inspected here is a transform chosen with the answer in view. The
numbers above count events and checks, never what those events say about anybody.

Funding edges come from `b9j`'s pinned System ABI with the two addresses taken from the
instruction's own resolved account list. Nothing is inferred: a transfer of N lamports from A to B
is exactly that, and whether it is funding, a tip or a refund is not something this module claims to
know.

## 7. Verification — 31 mutants, 30 killed, one disclosed

62 tests, 217 subtests; **1,281 passing repository-wide**.

Covering every failure mode named in the directive: boundary equality (4), past outcome after t0
(1), self-inclusion (2), left truncation treated as zero (5), identity leakage (3), duplicate events
(1), creator/user role confusion (3), funding direction reversal (3), flow direction (1), source
hash drift (3), insertion-order dependence (2), record contract (3).

**Three survived the first run and every one was a genuine gap:** no test distinguished a completion
belonging to *another* creator; the identity/feature disjointness check read module constants and so
could never fire; and no fixture placed two events at an identical coordinate, so the hash tiebreak
that makes ordering deterministic was untested. All three now have tests, and the disjointness check
takes its field sets as arguments so it is reachable.

**One equivalent mutant, disclosed rather than removed.** Deleting `assert_history` from
`build_as_of_history` changes nothing observable: coverage is validated earlier and the sections are
assembled internally from that validated input, so no caller input can make the self-check fire.
`assert_history` is separately and thoroughly tested when called directly. It is kept because it
would catch a future edit that adds a feature field without updating the contract — the exact class
of error it exists for.

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
