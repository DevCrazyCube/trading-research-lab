# Point-in-time history schema — v1.0.0

Produced by `scripts/b13a_history.py`. Read-only: consumers must treat every record as immutable
and must pin `schema_version`.

Status: **Phase 3 foundation, plumbing only.** This is not a feature vector for a model. It is the
evidence a feature vector would later be built from, with the point-in-time boundary already
enforced and every count already labelled as the lower bound it is.

## The one rule everything else serves

**Only events whose canonical coordinate is at or before t0 may enter.** The comparison is on
`(slot, transaction_index, outer_index, inner_index)` — never database insertion order, which
records when a collector wrote a row and says nothing about when the chain produced it.

The boundary is **inclusive at t0 and exclusive one coordinate later**. An event sharing t0's exact
coordinate was part of the state the decision was made against; an event one inner index later was
not, however tempting the fact that it sits in the same transaction.

**A note for review.** A looser reading would admit the remainder of t0's own transaction, since
that transaction completes before any order of ours could land — B10b's transaction-terminality
argument points that way. This module takes the **stricter** reading: an event it wrongly drops
costs information, while an event it wrongly admits costs correctness. The rule is published on
every record in `boundary_rule` and a test refuses a record carrying any other.

## Why every count is a lower bound, and says so in its name

A history computed over a bounded window cannot know what happened before the window opened. A
creator with no launches in the window has `prior_launch_count_observed == 0` — a fact about the
window, **not** the statement "this creator has never launched before".

Presenting the second as the first would be the single most damaging thing this module could do,
because it would turn a collection artefact into a feature that looks like knowledge. So:

- every count carries `_observed`, and a test refuses any field name stating a total;
- every section publishes `counts_are_lower_bounds`, asserted equal to `coverage.left_truncated`;
- `actor_seen_in_window` distinguishes "seen and did nothing" from "not seen";
- **`require_complete_history` fails closed** for any policy that needs a true count. Building a
  history over a truncated window is legitimate; *using* one as though its counts were totals is
  not, and the difference has to be an explicit act rather than an omission.

## Events

Every event carries the four canonical coordinates, its `kind`, and a `source_sha256`. Provenance is
not decoration: a claim about the past that cannot name its source is an assertion.

| kind | fields |
| --- | --- |
| `launch` | `mint`, `bonding_curve`, `creator`, `create_user` |
| `trade` | `mint`, `user`, `is_buy`, `quote_lamports`, `token_units` |
| `completion` | `mint` |
| `transfer` | `from_address`, `to_address`, `lamports` |

`creator` and `create_user` are **different fields and often different wallets**. Conflating them
attributes a stranger's launches to a creator, and a mutant that does exactly that is in the sweep.

`ordered_events` sorts canonically and refuses duplicates. Sorting here rather than requiring sorted
input is deliberate: a caller who happened to read rows in insertion order would otherwise get a
different history from the same evidence, and the difference would be invisible. Ties at an
identical coordinate — four transactions in the real artifact touch two curves at once — break by
the event's own hash, so the order is deterministic without being arbitrary.

## Coverage

Caller-supplied and never inferred: `first_slot`, `last_slot`, `source_population`,
`left_truncated`, `right_truncated`, `complete`, `provenance_sha256`. Absence is refusal. Coverage
claiming to be complete *and* truncated is refused — a truncated window is exactly the one whose
counts are lower bounds.

## Sections

Four, each with an `identity` block, a `features` block and an `evidence` block.

**No string may appear in a feature block, ever** — the same rule as the B11b feature contract, for
the same reason: it is checkable without anyone having to notice which strings happen to be
identities. Identity and feature field sets are declared and disjoint, and
`assert_disjoint_contract` takes its field sets as arguments so the check is reachable rather than a
guard nobody can make fire.

| section | features |
| --- | --- |
| `creator` | prior launches, prior completions of *its own* tokens, prior launches carrying a creator buy and their exact quote, first/previous launch slot, slots since |
| `user` | prior trades, buys and sells separately, exact quote and token flows **by direction**, distinct mints, first/last trade slot |
| `token` | launch slot and slots since, launch-transaction trade count and creator-buy presence/amount, prior trades and flows by direction, distinct users, `completed_before_t0` |
| `funding` | inbound/outbound edge counts and lamports, distinct counterparties; the raw edges live in `evidence` |

**Direction is kept exact and separate everywhere.** A net figure would hide a wallet that cycled a
hundred SOL through one curve behind one that never traded.

**Self-inclusion is prevented.** A creator's prior launches are those strictly before the subject's
own launch and never the subject itself. A completion counts only for a token that creator launched.

**`completed_before_t0` means exactly that.** A token completing after t0 has not completed as far
as this decision is concerned, and recording it would be the plainest possible outcome leak.

## Subject consistency

The subject's declared creator must be the one its launch event names, and likewise its bonding
curve. A caller passing the wrong creator would otherwise receive a perfectly well-formed history
full of zeros — the most convincing possible way to be wrong, because nothing about the record would
look unusual. A launch that predates the window is *not* an error; that is coverage, and
`launch_observed_in_window` says so.

## No clusters

Funding edges are published raw: direction, source, destination, amount, coordinate, provenance.
Nothing is joined into an entity. Cluster inference and confidence are a later task, and
**funding-cluster leakage remains an open gate**. A `cluster_id` here would be a judgement wearing
the costume of a fact, and a test scans the record for one.

## Determinism

Canonical JSON with sorted keys; `history_sha256` over everything else; `source_hash_chain_sha256`
over the provenance of exactly the events inside the boundary, so an event past t0 cannot even
reach the chain. Identical evidence in any order gives a byte-identical record.

## Measured

```
python scripts/b13a_history.py --contract
python scripts/b13a_history_corpus.py research/b9d_transaction_bodies.sqlite \
    research/b10b_observed_paths.sqlite --gate
```

See `research/B13A_HISTORY_FOUNDATION.md`, which also carries the future cohort-based collection
plan.

## Not covered

- Any model, threshold, score or cluster.
- Any feature distribution, correlation or label association — none has been computed, on any
  window.
- B11a. That window has still never been read.
