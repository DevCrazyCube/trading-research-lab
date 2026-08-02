# Association evidence ledger schema — v1.0.0

Produced by `scripts/b13b_association.py`. Read-only: consumers must treat every record as immutable
and must pin `schema_version`.

Status: **Phase 3 foundation, evidence only.** This is not a clustering, not an entity resolution
and not an input to a model. It is the raw evidence a clustering would later be argued from, with
the point-in-time boundary already enforced and every conclusion the evidence does not support
already refused.

## What a link is, and what it is not

A link says: *here is what was observed about these two addresses, at or before this instant, with
the coordinate and the source hash of every observation.* It does not say they are the same person,
it does not say how likely that is, and it does not offer a number that could be mistaken for
either.

`confidence_status` is `uncalibrated_evidence_only` on every link and on the ledger. Its published
meaning travels with the record:

> Every item in this ledger is a raw observation with a coordinate and a source hash. Nothing here
> has been calibrated against any outcome, no weight has been fitted, and no threshold has been
> chosen. A reader may not convert these counts into a probability that two addresses share an
> owner, because no such conversion has been validated and this module will not supply one.

## Four refusals that are structural, not promised

### 1. A link must be witnessed, so A—B plus B—C cannot manufacture A—C

Every evidence item names its own `witness_addresses`, and **every** item in a link must name both
endpoints. A—B evidence witnesses `{A, B}`; B—C evidence witnesses `{B, C}`. Neither witnesses
`{A, C}`, so no A—C link can be assembled from them and none can be smuggled in afterwards.
Non-transitivity is a property of the data structure rather than a rule somebody remembered.

`assert_no_transitive_link(ledger)` is a public entry point for a caller holding a ledger built
elsewhere. `assert_ledger` deliberately does **not** call it: the per-item rule is strictly stronger
— one item versus every item — so a call there could never fire, and a check that cannot fire is
worse than no check.

### 2. Exact identity is a different relation type

| relation | requires | evidence permitted |
| --- | --- | --- |
| `identity_equality` | `address_a == address_b` | `E00` only |
| `association_evidence` | `address_a < address_b` | everything except `E00` |

Association evidence inside an identity claim is refused, and so is the reverse. This is the wall
between "they transacted" and "they are the same".

### 3. Nothing calibrated may enter, by name or by type

`assert_uncalibrated` refuses any field whose **name** contains `cluster`, `probability`,
`same_owner`, `owner_id`, `entity_id`, `component`, `likelihood`, `posterior`, `confidence_score`,
`merge`, `calibrat`, `p_same` or `score` — anywhere in the record, at any depth. By name rather than
by value, because the damage is done the moment a downstream reader sees the name: a field called
`cluster_id` holding `"none"` still teaches the next person that clusters are something this record
has. `assert_no_float` then refuses any float, because a fitted number arrives as one.

### 4. The clustering operations exist in order to refuse

`cluster_id`, `connected_component`, `merge_addresses`, `association_probability` and
`cluster_adjusted_concentration` all exist and all raise `ClusterRefused`. An operation that is
simply absent invites a caller to write their own; one that refuses, loudly, tells them why they
should not. `ClusterRefused` is a distinct subclass because "fix your input" and "this question has
not been earned yet" are different problems.

## Evidence kinds

Each carries what it does **not** mean, and that half travels on the record.

| kind | directional | means — and does not mean |
| --- | --- | --- |
| `E00_exact_address_equality` | no | the same address in two roles. This IS identity, and the only relation here that asserts sameness |
| `E01_direct_transfer` | **yes** | lamports moved. Evidence of a TRANSFER and nothing else — everyone who has paid an exchange has one |
| `E02_shared_funder` | no | one address paid both endpoints. A shared COUNTERPARTY, not common control |
| `E03_repeated_counterparty` | **yes** | they transacted more than once. The raw count, compared against no threshold |
| `E04_co_occurrence_in_transaction` | no | both are named in one transaction. Being named is not acting |
| `E05_co_signing_launch_roles` | no | different roles in one launch. A shared ACTION, weaker than shared control |

**These kinds overlap and are not independent.** An `E01` transfer is also an `E04` co-occurrence.
That is recorded on the co-occurrence item itself (`overlaps_other_evidence_kinds`) and is one more
reason these counts may never be summed into a score.

**Direction is never dropped and never netted.** A directional kind recorded as `not_directional` is
refused, and so is a non-directional kind claiming a direction — an invented direction is worse than
none. `lamports_a_to_b_observed` and `lamports_b_to_a_observed` stay separate, because a netted
figure hides a wallet that cycled a hundred SOL behind one that never moved.

Every item carries `coordinates` (all at or before t0, canonically ordered) and a
`source_sha256_list` of the same length. An observation that cannot say where it happened cannot be
checked against the boundary, and one that cannot name its source is an assertion.

## Counter-evidence is mandatory

A shared service wallet is the obvious false link: an exchange hot wallet funds thousands of
unrelated actors, and "shared funder" between two of its customers is evidence of nothing.

| code | meaning |
| --- | --- |
| `X01_endpoint_role_unknown` | an endpoint's role is not established, so a service cannot be excluded |
| `X02_endpoint_is_known_service` | an endpoint is an established service |
| `X03_intermediary_role_unknown` | a shared funder's role is not established |
| `X04_intermediary_is_known_service` | evidence routed through a service is evidence about the service |
| `X05_evidence_from_incomplete_history` | a contributing history is incomplete, so this is a lower bound |

**`unknown` raises the flag rather than lowering it.** Absence of a known service role is not
evidence that an address is not a service. Registering an address explicitly as `unknown` is
refused — unknown is what absence already means, and nobody can establish that a role is unknown. A
registered role must carry `provenance_sha256` and `established_by`; a role asserted without
provenance is the same unsupported claim as a cluster.

## Completeness, propagated and failing closed

| code | meaning |
| --- | --- |
| `G01_contributing_history_incomplete` | a history behind these links is incomplete |
| `G02_lookback_not_chosen` | no lookback is preregistered, so "no association" means "none in whatever window this covered" |
| `G03_endpoint_history_absent` | this address is not among the focus addresses, so its absence says nothing |
| `G04_unresolved_evidence_at_or_before_t0` | B13a lost evidence this ledger needed |

`require_complete_neighbourhood(ledger, address)` fails closed, per address and against that
address's own t0 — the same per-subject judgement B13a makes, for the same reason. A focus address
with no links is **not** reported as absent: "seen and unconnected" and "never looked at" are
different facts.

## The lookback is not chosen here

`lookback_chosen` is `False` and `lookback_slots` is `null`. Setting the number while
`lookback_chosen` is false is refused — a number nobody chose is a number somebody will use. A
chosen lookback must name its preregistration, because a lookback picked after seeing how far back
the evidence happens to run is a lookback picked for its results.

The **repetition threshold** is likewise not chosen: `E03` publishes the raw count with
`repetition_threshold_applied: false`. Two is the arithmetic meaning of "repeated", not a
significance threshold.

## Blocks and fields

| block | holds |
| --- | --- |
| `grouping` | `address_a`, `address_b`, `relation_type` — **the only place addresses live besides `evidence`** |
| `features` | counts and booleans only; **no string may ever appear** |
| `evidence` | the typed items, canonically ordered and duplicate-free |
| `counter_evidence` | why this link might be false |
| `completeness` | whether the neighbourhood is complete and whether counts are lower bounds |

`assert_disjoint_blocks` takes its field sets as arguments so the check is reachable rather than a
guard nobody can make fire.

## Determinism

Canonical JSON with sorted keys; `link_sha256` per link; `ledger_sha256` over everything else;
`evidence_hash_chain_sha256` over the sources of exactly the evidence inside the boundary, so an
observation past t0 cannot reach the chain. Links are emitted in canonical order — not merely
deterministically, so two ledgers over the same evidence diff cleanly. Duplicate evidence is refused
both at assembly and on a finished record: the same observation counted twice reads as independent
corroboration and is not.

## Measured

```
python scripts/b13b_association.py --contract
python scripts/b13b_association_corpus.py research/b9d_transaction_bodies.sqlite \
    research/b10b_observed_paths.sqlite --gate
```

See `research/B13B_ASSOCIATION_LEDGER.md`.

## Not covered

- Any cluster, entity, merge, probability, score or "same owner" claim.
- Any association degree, degree distribution or neighbourhood ranking — none has been computed.
- Any label join. B11a has still never been read.
