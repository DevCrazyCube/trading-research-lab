# External observation ledger schema — v1.0.0

Produced by `scripts/b13c_observations.py`. Read-only: consumers must treat every record as
immutable and must pin `schema_version`.

Status: **Phase 3 foundation, plumbing only.** No collection has been performed, no provider has
been contacted, no vendor has been selected and no credential exists. Every record exercised so far
is synthetic.

## The one question every field serves

**Could we actually have known this, at that instant?**

On-chain leakage is easy to see: a coordinate is either at or before t0 or it is not. External data
has a second clock, and the second clock is where the leak hides. An article published last Tuesday
but *fetched* today is not evidence a decision last Tuesday could have used — and nothing about the
article says so.

## The availability rule

> An external observation is feature-eligible at t0 **if and only if** it was RECEIVED by us at a
> wall-clock instant at or before t0's, **AND** its claimed publication/effective instant is at or
> before t0's.

Both halves are required and **neither implies the other**:

| published | received | eligible at t0 | why |
| --- | --- | --- | --- |
| before | before | **yes** | we had it, and it existed |
| before | after | no | the backfill — we did not have it yet |
| after | before | no | the provider dated it in the future |
| after | after | no | both |

The rule text travels on every record in `availability_rule`, and a record carrying any other is
refused.

**A time claim that cannot be bounded is never eligible.** `unavailable` and `ambiguous` are
different facts — one has no reading, the other has a reading nobody can bound — and both are
unusable. Guessing a timezone would invent the very thing being checked.

## Four clocks, kept apart

| clock | meaning |
| --- | --- |
| `event_time` | when the thing described actually happened |
| `publication_time` | when the provider says it was published or last made effective |
| `receipt_time` | when **we** received it — the only clock we can vouch for |
| `effective_coordinate` | the on-chain canonical coordinate, where one applies (else `null`) |

Collapsing any two of these is how a leak becomes invisible.

Receipt is recorded on **both** a wall clock and a monotonic one. A wall clock can legitimately jump
— NTP, a suspend, a timezone mistake — so it cannot detect reordering. A monotonic clock can, and
one running backwards inside a single fetch session is refused.

### Time claims carry their own width

`time_claim(value_ns, precision_ns, source)` covers the interval
`[value_ns, value_ns + precision_ns]`. A provider that publishes a *date* with no time has given a
claim covering a whole day, and eligibility uses the **latest instant it could mean** — so a
day-precision article becomes usable only at the end of the day it covers. Recording the width lets
that be computed instead of assumed.

## The decision instant

A chain coordinate carries no wall time, and the mapping between them is itself an observation with
error. This module **refuses to derive one**: the caller supplies `wall_ns`, `coordinate` and
`wall_clock_provenance` saying where the wall time came from, so a later reader can audit the join
rather than discover it.

## Ineligibility reason codes

| code | meaning |
| --- | --- |
| `A01_received_after_t0` | we had not fetched it yet |
| `A02_published_after_t0` | the provider dates it after the decision |
| `A03_receipt_time_unavailable` | we cannot say when we received it |
| `A04_publication_time_unavailable` | the publication claim cannot be bounded |
| `A05_mapping_not_exact` | we do not know this is about that token |
| `A06_license_prohibits_use` | the licence forbids it |
| `A07_payload_purged` | nothing remains to read |
| `A08_decoder_unpinned` | the parse cannot be reproduced |

Codes rather than a bare `False`: "not eligible" does not say whether an item is unusable forever,
unusable *yet*, or unusable *for this token*.

## Revisions never rewrite history

A correction, an edit, a deletion and a restore are each a **new observation** in a revision chain
keyed by `(provider, provider_observation_id)`. A chain must begin with exactly one `create`, have
contiguous indices, and each revision must name the hash of the version it supersedes — a chain that
does not link is a chain that rewrote something.

`as_of(chain, instant)` returns the version a decision **actually knew**, and
`version_history_as_of` returns every version known by then. Nothing is ever dropped.

**A deletion received after t0 does not reach back.** The text a decision was made on stays visible
to that decision; removing it would be leakage wearing the costume of data hygiene. Only a deletion
we had already received turns the answer into `Absent(deleted)`.

## Absence is not zero and not false

`Absent` carries a reason — `unknown`, `unavailable`, `deleted`, `not_yet_known` — and calling
`bool()` on it **raises**. A sentinel that quietly evaluates to `False` is how "we never received a
price" becomes "the price was nothing". Test for it with `is_absent()`.

## A ticker is not a token

| status | meaning |
| --- | --- |
| `exact_binding` | the payload contains the mint or account address, and the evidence says where |
| `unverified_mapping` | a name or ticker matched. **Not identity** — tickers collide |
| `source_claim` | the provider asserts it and we have not checked |
| `unmapped` | none attempted or none found |

An exact binding must name an address *and* show its evidence; a weaker status carrying binding
evidence is a record that disagrees with itself, and an unverified mapping must say what text
matched so a reader can see the collision risk they are being asked to accept.
`require_exact_binding` fails closed. `require_binding=False` exists for questions that are not
about a token at all — a global fee schedule belongs to no mint.

## Measurements: a value and its unit, together, or nothing

Financial values live in a `measurement` block and **never in the feature block**. A number that can
be separated from its unit eventually will be, and lamports read as SOL is off by a factor of a
billion.

Every measurement states `value_numerator`, `value_denominator` (exact rational — no float),
`unit`, `quote_asset`, `measurement_basis` and a **stated** `effective_time`.

`assert_comparable` refuses to compare or combine measurements differing in unit, quote asset or
basis. It does **not** convert: a conversion needs a rate, a rate is itself a timestamped
observation, and supplying one here would invent data.

`require_fresh(measurement, instant, max_staleness_ns, rationale)` fails closed on a stale value and
on a value effective *after* the instant. **No default bound is offered.** A freshness bound is a
threshold, thresholds in this project are preregistered, and a module that supplied one silently
would have chosen it for everybody.

## Licence and retention, checked against each other

| licence | permitted retention |
| --- | --- |
| `permits_storage` | raw bytes, hash only, or purged |
| `reference_only` | hash only, or purged |
| `prohibited` | hash only, or purged |
| `unknown` | hash only, or purged — the fail-closed case |

A licence recorded beside a payload it forbids is a licence nobody is honouring, so the combination
is refused. Retained bytes must hash to the recorded digest and match the recorded length; either
side drifting is caught, and there is no way to tell from the record which one moved.

## Blocks

| block | holds |
| --- | --- |
| `identity` | provider, provider observation id, kind |
| `provenance` | query spec hash, fetch session, fetch provenance hash, decoder name and version |
| `payload` | digest, byte length, reference, and the raw bytes only when retention permits |
| `times` | the four clocks |
| `revision` | kind, index, superseded hash |
| `mapping` | how we think we know which token this is about |
| `measurement` | value **with** its unit, for financial quotes only |
| `evidence` | raw text, headlines, URLs, handles |
| `features` | counts and booleans only — **no string may ever appear** |

The feature block is **computed from the record**, never passed in. A caller who hand-wrote it could
state that a publication time was available when it was not, and that single boolean is the whole
availability rule.

## What this module refuses to compute

`sentiment`, `embedding`, `engagement_score`, `source_credibility`, `market_cap` and
`call_language_model` all exist and all raise `DerivedQuantityRefused`. An absent function invites a
caller to write their own; a loud refusal says why they should not.

Any field whose **name** contains `sentiment`, `embedding`, `engagement`, `popularity`,
`credibility`, `virality`, `influence`, `score`, `probability`, `market_cap`, `price_change`,
`momentum`, `normali`, `llm`, `prompt`, `confidence`, `bullish`, `bearish`, `hype` or `trending` is
refused anywhere at any depth, and no float may appear.

**`LLM_IN_DECISION_PATH` is `False`.** A model in the path would make every decision
unreproducible, unauditable at the instant it mattered, and dependent on a remote service whose
behaviour changes without notice.

## Future adapters, and the rules they will have to meet

No adapter is written and no vendor is selected. When one is:

- **Credentials are environment-only and never persisted** — not in a record, not in a query spec,
  not in a log. `query_spec_sha256` is a hash precisely so a spec containing a key cannot be stored
  in the clear.
- **The query spec is hashed and pinned** so a later reader can tell whether two observations came
  from the same subscription or from a silently changed one.
- **Receipt clocks are ours, taken at the adapter boundary**, wall and monotonic together, before
  any parsing.
- **Licence and retention are decided per provider before the first fetch**, and default to
  `unknown` / `hash_only` if nobody decided.
- **Personal data**: a public post's author handle is evidence and stays in the evidence block; it
  never enters a feature. Nothing here profiles a private individual, and deletion notices are
  honoured going forward without rewriting what earlier decisions saw.
- **Rate limits and terms of service** are the adapter's problem to respect, not this schema's to
  encode — but an adapter that cannot record a receipt time may not be used at all.

## Determinism

Canonical JSON with sorted keys; `observation_sha256` over everything else. `ordered_observations`
sorts by `(provider, provider_observation_id, revision_index, digest)` and refuses duplicates, so a
caller who read rows in insertion order gets the same as-of answer as one who did not.

## Measured

```
python scripts/b13c_observations.py --contract
python scripts/b13c_observation_fixtures.py --gate
```

See `research/B13C_EXTERNAL_OBSERVATIONS.md`.

## Not covered

- Any collection, adapter, credential, vendor or purchase.
- Any sentiment, embedding, score, probability, price transform or distribution.
- Any language model in the decision path.
- The burned corpus and B11a. Neither is opened by anything in this module.
