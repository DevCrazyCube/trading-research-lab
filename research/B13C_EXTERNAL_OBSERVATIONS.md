# B13c — an external observation ledger whose whole job is the second clock

Date: 2026-08-02. Author: Claude (handoff 84). Offline library and report only.
Code: `scripts/b13c_observations.py`, `scripts/b13c_observation_fixtures.py`.
Schema: `docs/OBSERVATION_SCHEMA.md`. Tests: `tests/test_b13c_observations.py`.

## 0. Scope, and what was not touched

Plumbing and synthetic fixtures only. **No collection was performed**: no network call, no provider,
no credential, no vendor selected, nothing purchased. **The burned corpus was not opened and B11a
was not queried, enumerated or read.** No sentiment, embedding, score, probability, price transform
or distribution was computed, and no language model is anywhere near a decision.

## 1. The leak this exists to prevent

On-chain leakage is easy to see: a coordinate is either at or before t0 or it is not. That is why
B13a and B13b could make their boundary structural in one comparison.

External data has a **second clock**, and the second clock is where the leak hides. An article
published last Tuesday but *fetched* today is not evidence a decision last Tuesday could have used —
and nothing about the article says so. Its publication date is genuinely last Tuesday. Every field a
naive schema would record checks out. The only thing wrong is that we did not have it, and that fact
lives nowhere except in a clock nobody thought to write down.

Backfilling is therefore the most natural mistake in this whole area, and it produces a backtest
that is right for a reason that will never repeat.

## 2. The rule, and why it needs both halves

> An observation is feature-eligible at t0 **if and only if** it was received by us at or before
> t0's wall instant, **AND** its claimed publication instant is at or before t0's.

Neither half implies the other, and dropping either one admits a different error:

- receipt alone admits a provider's **future-dated** item, which is common and often innocent — a
  scheduled post, a press release with an embargo date;
- publication alone admits the **backfill**, which is the one that destroys a backtest.

The rule text travels on every record. A record carrying any other text is refused, so a future
edition that loosened the rule could not quietly reuse the old records.

**Unavailable and ambiguous are different facts and both are unusable.** A clock we never got has no
reading; a local timestamp with no timezone has a reading nobody can bound. Guessing a zone would
invent exactly the thing being checked, so both yield `Absent` and neither yields a number.

**Claims carry their own width.** A provider that publishes a date without a time has stated a claim
covering a whole day, and eligibility uses the latest instant it could mean — so a day-precision
article becomes usable at the end of its day, not the start. That is arithmetic on a recorded
interval rather than a policy somebody remembered.

## 3. Four clocks, and the join this module refuses to make

`event_time`, `publication_time`, `receipt_time` and `effective_coordinate` are kept apart because
collapsing any two makes a leak invisible.

Receipt is recorded on **both** a wall clock and a monotonic one, and that pairing does real work: a
wall clock can legitimately jump — NTP, a suspend, a timezone mistake — so it cannot detect
reordering, and a monotonic clock can. A monotonic reading going backwards inside one fetch session
is refused; a wall clock going backwards across sessions is not, because that is normal.

**The slot-to-wall-clock join is refused, not derived.** A chain coordinate carries no wall time, and
the mapping between them is itself an observation with error. The caller supplies the decision
instant's wall time *and says where it came from*, so a later reader audits the join instead of
discovering it. Deriving one here would have hidden a source of error inside a leakage check.

## 4. History is never rewritten, and the deletion case is the subtle one

Corrections, edits, deletions and restores are each a new observation in a revision chain. As-of
replay returns the version a decision actually knew and keeps every prior one.

The case worth stating plainly: **a deletion received after t0 must not reach back**. If a post is
withdrawn on Wednesday, a decision made on Tuesday saw the post, and replaying Tuesday without it
would be leakage wearing the costume of data hygiene — the backtest would be quietly better than
live trading could ever be, because live trading does not get to un-see things. Only a deletion we
had already received turns the answer into `Absent(deleted)`.

`Absent` carries a reason and **raises on `bool()`**. `unknown`, `unavailable`, `deleted` and
`not_yet_known` are four different facts and none of them is zero; a sentinel that quietly evaluated
to `False` is how "we never received a price" becomes "the price was nothing".

## 5. A ticker is not a token, and a value is nothing without its unit

`mapping_status` separates an exact mint/account binding from a name match and from a provider's
bare claim. Ticker collisions are constant and attaching a stranger's news to a token is the
cheapest available error, so an exact binding must name an address *and* show where it was found,
while everything weaker is labelled as what it is. `require_exact_binding` fails closed — with an
explicit waiver for questions that are not about a token at all, since a global fee schedule belongs
to no mint.

**Financial values are kept out of the feature block entirely.** A number that can be separated from
its unit eventually will be, and lamports read as SOL is off by a factor of a billion — so the
value, its unit, its quote asset, its basis and its effective time live in one block together.
Comparison across differing units fails closed and does **not** convert: a conversion needs a rate,
a rate is itself a timestamped observation, and supplying one would invent data.

Freshness is checkable and **the bound belongs to the caller**, who must supply it with a rationale.
No default is offered: a freshness bound is a threshold, this project preregisters thresholds, and a
module that supplied one silently would have chosen it for everybody.

## 6. Licence and retention, checked against each other

`unknown` is the fail-closed case: hash only. Storing raw text under a licence nobody has read is a
decision nobody made, so it is refused rather than defaulted. A licence sitting beside a payload it
forbids is refused, retained bytes must hash to the recorded digest and match the recorded length,
and a record claiming retention while holding nothing is refused too.

## 7. Measured — the synthetic fixture corpus

```
python scripts/b13c_observation_fixtures.py --gate
```

| quantity | value |
| --- | --- |
| synthetic observations | 16 |
| revision chains (distinct provider items) | 13 |
| kinds exercised | all 5 — 7 news, 5 social, 2 quotes, 1 metadata, 1 config |
| mapping statuses exercised | all 4 — 12 exact, 2 unverified, 1 claimed, 1 unmapped |
| revision kinds exercised | 13 create, 2 edit, 1 delete |
| decision instants replayed | 5 |
| observation-instant pairs judged | 80 — 30 eligible, 50 refused |
| refusals by reason | A01 ×18, A02 ×15, A04 ×5, A05 ×20 |
| chains validated | **13 / 13** |
| hashes stable | **16 / 16** |
| backfill refused at every instant | **5 / 5** |
| deletion did not rewrite history | **5 / 5** |
| prior versions preserved | **5 / 5** |
| result independent of arrival order | **5 / 5** |
| reused-identifier collision refused | **yes** |
| unit mixing refused | **yes** |
| refusing computations verified to refuse | **6 / 6** |
| errors | **0** |

**No content appears in that report and none may**, and a test greps the report for the fixture text
to prove it. Publishing what an item said would put content in a file whose licence nobody has
cleared, and would invite exactly the transform this module refuses to compute. The numbers count
records and checks, never what those records say.

`restore` is a declared revision kind the fixture corpus does not exercise; it is driven by unit
tests. Saying so is the point — a report silent about what it never ran reads as though it covered
it.

## 8. Verification — 76 mutants, 76 killed, none disclosed

98 tests, 228 subtests.

Covering every failure mode the directive named: fetch-after-t0 leakage (3), publication-after-t0
(4), ambiguous timestamp (4), retroactive edit (8), deletion (3), receipt clock reversal (2), ticker
collision and wrong mint (7), unit mixing (9), payload and hash drift (3), duplicate provider IDs
(2), raw string into a feature block (4), insertion order (1), plus licence and retention (6),
absence semantics (3), derived-quantity refusals (4), the decision instant (2), the record contract
(4) and the gate's own conditions (6).

**Five survived the first run and every one was a genuine gap:** no fixture built an ambiguous claim
that also stated a precision, or an unavailable claim that still carried a reading — the two ways a
record can be internally inconsistent about a clock; the feature contract was never driven with an
extra or a missing field; and no test supplied a malformed `effective_coordinate`. All five now have
tests. **No equivalent mutants remain to disclose.**

The gate's conditions were extracted into a pure `gate_failures` from the start, following the B13b
lesson: a gate whose conditions can only be exercised by running the whole corpus is a gate nobody
can show works.

## 9. Future adapters — specified, none written

No adapter exists and no vendor has been chosen. Any future one must meet these, and they are stated
now rather than after the first fetch:

1. **Credentials are environment-only and never persisted** — not in a record, not in a query spec,
   not in a log. `query_spec_sha256` is a hash precisely so a spec containing a key cannot be stored
   in the clear.
2. **The query spec is pinned by hash**, so a later reader can tell whether two observations came
   from the same subscription or from one that silently changed under them.
3. **Receipt clocks are taken at the adapter boundary**, wall and monotonic together, before any
   parsing. An adapter that cannot record a receipt time may not be used at all — its items could
   never be shown eligible.
4. **Licence and retention are decided per provider before the first fetch**, and default to
   `unknown` / `hash_only` when nobody decided.
5. **Privacy**: a public post's author handle is evidence and stays in the evidence block, never a
   feature. Nothing here profiles a private individual. Deletion notices are honoured going forward
   without rewriting what earlier decisions saw — the two obligations do not conflict, because the
   ledger separates "what is current" from "what was known then".
6. **The decoder is named and versioned on every record**, so a reparse can be told from a refetch.

## 10. Not claimed

No model, no score, no sentiment, no embedding, no probability, no price transform, no distribution,
no vendor, no collection, no operational readiness. No language model in the decision path. The
counts in this document are counts of synthetic records and checks.
