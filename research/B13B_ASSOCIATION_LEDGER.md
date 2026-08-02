# B13b — an association evidence ledger that refuses to be a clustering

Date: 2026-08-02. Author: Claude (handoff 82). Offline library and report only.
Code: `scripts/b13b_association.py`, `scripts/b13b_association_corpus.py`.
Schema: `docs/ASSOCIATION_SCHEMA.md`. Tests: `tests/test_b13b_association.py`.

## 0. Scope, and what was not touched

Evidence foundation only. **B11a was not queried, enumerated or read**, no baseline changed, no
label was joined, and no cluster, threshold, lookback or calibration was chosen. No association
degree or degree distribution was computed on any window, including the burned one.

## 1. The failure this module is built against

The tempting move in wallet intelligence is one short step: two addresses share a funder, therefore
they are probably the same actor, therefore concentration is higher than it looks, therefore the
position is riskier than it looks. Every arrow in that chain is a judgement, and by the fourth one
they have all turned into a number that looks like a measurement.

The specific damage is that a cluster is **indistinguishable from an observation** once it is in a
record. `prior_launch_count_observed` says where it came from; `cluster_id` does not. Three phases
later, nobody remembers which one was inferred.

So this module publishes evidence and refuses conclusions, and the refusals are structural rather
than promised.

## 2. Four structural refusals

**A link must be witnessed.** Every evidence item names the addresses it witnesses, and every item
in a link must name both endpoints. A—B evidence witnesses {A, B}; B—C witnesses {B, C}; neither
witnesses {A, C}. There is no way to write an A—C link from them, so non-transitivity is a property
of the data structure and not a rule anyone has to remember. `assert_no_transitive_link` remains a
public entry point for a ledger built elsewhere, but `assert_ledger` deliberately does not call it:
the per-item rule is strictly stronger, so the call could never fire, and a check that cannot fire
is worse than no check.

**Exact identity is a different relation type.** `identity_equality` requires `address_a ==
address_b` and admits only `E00` evidence; `association_evidence` requires two distinct addresses
and refuses `E00`. That wall is what stops "they transacted" from becoming "they are the same".

**Nothing calibrated may enter, by name or by type.** A field whose *name* contains `cluster`,
`probability`, `same_owner`, `score`, `merge`, `posterior`, `component`, `entity_id`, `likelihood`
or `calibrat` is refused anywhere in the record at any depth — by name, because the damage is done
the moment a downstream reader sees it. A field called `cluster_id` holding `"none"` still teaches
the next person that clusters are something this record has. Floats are refused by type, because a
fitted number arrives as one.

**The clustering operations exist in order to refuse.** `cluster_id`, `connected_component`,
`merge_addresses`, `association_probability` and `cluster_adjusted_concentration` all raise
`ClusterRefused`. An absent operation invites a caller to write their own; a loud refusal tells them
why they should not, and `ClusterRefused` is a distinct subclass because "fix your input" and "this
question has not been earned yet" are different problems.

## 3. What each kind of evidence does not mean

The second half of each sentence is the load-bearing half, and it travels on the record:

- **direct transfer** — lamports moved, and *nothing else*. Everyone who has ever paid an exchange
  has a direct transfer to it.
- **shared funder** — a shared counterparty, *not* common control. A service wallet funds thousands
  of unrelated actors.
- **repeated counterparty** — the raw count, compared against *no threshold*, because none has been
  preregistered.
- **co-occurrence** — being *named* in a transaction, which is not the same as acting in it.
- **co-signing launch roles** — a shared *action*, which is weaker than shared control.

**These kinds overlap, and overlapping evidence is not independent evidence.** Every direct transfer
is also a co-occurrence; the co-occurrence item says so on its face. Five evidence items about one
transfer is one observation seen five ways, and that is one more reason these counts may never be
added into a score.

Direction is never dropped and never netted, in either representation: a directional kind recorded
as `not_directional` is refused, an invented direction on a non-directional kind is refused, and
`lamports_a_to_b_observed` stays separate from `lamports_b_to_a_observed` throughout.

## 4. Counter-evidence, and why `unknown` counts against a link

A shared service wallet is the obvious false link, so the honest default has to be that we do not
know whether an address is one. `unknown` therefore **raises** the counter-evidence flag rather than
lowering it: absence of a known service role is not evidence of absence of a service.

Two consequences worth stating plainly. Registering an address explicitly as `unknown` is refused —
unknown is what absence already means, and nobody can establish that a role is unknown. And a
registered role must carry provenance, because a role asserted without it is the same unsupported
claim as a cluster.

Under today's data no role is established for anything, so **every link in the measured run carries
counter-evidence**. That is the correct output, not a gap: it says the ledger cannot presently rule
out that any of these links runs through a service.

## 5. Measured — plumbing integrity on the burned development corpus

```
python scripts/b13b_association_corpus.py research/b9d_transaction_bodies.sqlite \
    research/b10b_observed_paths.sqlite --gate --limit 60 --addresses 12 --instants 5
```

| quantity | value |
| --- | --- |
| events in the stream | 44,438 |
| focus addresses | 12 |
| decision instants | 5 |
| links emitted (all instants) | 270 — 260 association, 10 identity |
| evidence items | 10,988 |
| — direct transfer / repeated counterparty | 105 / 15 |
| — shared funder / co-occurrence | 3,815 / 7,043 |
| — exact address equality | 10 |
| boundary respected | **5 / 5** |
| every link witnessed by evidence naming both endpoints | **5 / 5** |
| counter-evidence on every link | **5 / 5** |
| identities kept out of features | **5 / 5** |
| result independent of arrival order | **5 / 5** |
| neighbourhood completeness refused | **60 / 60** address-instants |
| refusing operations verified to refuse | **5 / 5** |
| errors | **0** |

**No association degree and no degree distribution appear above, and none may.** A degree
distribution inspected here is the first step of choosing a threshold with the answer in view, and
the threshold is precisely what this phase may not choose. The numbers count links and checks, never
how those links are spread.

**Focus addresses are chosen by first appearance in canonical coordinate order among the slice's
transfer edges — never by degree.** Selecting "the most connected wallets" would pick the population
on the very quantity the ledger measures, and every count above would then be a consequence of the
choice rather than a property of the data. The rule is published on the report.

**One code path this corpus does not exercise**, and the report says so rather than staying silent:
`E05_co_signing_launch_roles` never fires, because the focus addresses are transfer participants and
launch-role pairs do not arise among them. That path is driven by synthetic fixtures instead. A gate
that omits the kinds it never ran reads as though it covered them.

## 6. Verification — 53 mutants, 53 killed, none disclosed

98 tests, 62 subtests.

Covering every failure mode the directive named: direction reversal (5), transitive closure (3),
direct-transfer-as-control (3), service-role loss (8), future-coordinate leak (2), duplicate
evidence (3), identity-feature leak (3), incomplete history promoted to complete (6),
probability/cluster field injection (6), evidence hash drift (4), plus accounting, canonical
ordering and the gate's own conditions (10).

**Nine survived the first run. Six were genuine gaps and three were redundant checks:**

- no fixture had a *one-way* repetition, so a mutant collapsing every repetition to
  `both_directions` survived — "they kept paying each other" and "one kept paying the other" are
  different facts;
- the ledger-level confidence status was never asserted, only the per-link one;
- link ordering was tested for determinism but not for being *canonical*, so removing the sort
  survived;
- the evidence derivation was only ever driven through `build_association_ledger`, which pre-sorts,
  so its own tiebreak was untestable — it is now driven directly with a shuffled list;
- the corpus runner's focus selection and gate conditions had no tests at all.

The three redundant checks were **removed rather than disclosed**. A duplicate no-evidence check in
`build_link` produced the same refusal as the one in `assert_link`; the ledger-level transitivity
call could never fire behind the strictly stronger per-item rule; and the gate's conditions were
inlined where only a full corpus run could reach them. The last one became a pure `gate_failures`
function, which is both testable and better: **a gate whose conditions can only be exercised by
running the whole corpus is a gate nobody can show works.**

No equivalent mutants remain to disclose.

## 7. Specified, and deliberately not chosen

Each of these must be frozen in its own preregistration **before the actors it applies to are
known**, and none may be picked by looking at an observed ledger:

1. **The lookback**, in slots. A lookback picked after seeing how far back the evidence happens to
   run is a lookback picked for its results.
2. **The repetition threshold.** `E03` publishes the raw count with
   `repetition_threshold_applied: false`. Two is the arithmetic meaning of "repeated", not a
   significance threshold.
3. **Any probability calibration.** It needs a validation set, and the only fresh one is B11a, which
   is locked. Calibrating against the burned corpus would fit the threshold to data whose labels
   have already been measured.
4. **Any merge threshold**, together with the merge rule itself and what happens to a cluster when
   one of its links turns out to run through a service.

## 8. The open clustering gate

Clustering remains gated, and this pass makes the gate concrete rather than merely stated. Before
any cluster may be inferred, a preregistration must settle:

- the merge rule and its threshold, chosen before the cohort is enumerated;
- how a cluster is invalidated when an established service role appears on one of its links —
  today's ledger flags that possibility on *every* link, so the rule cannot be an afterthought;
- **funding-cluster leakage**, still open: a cluster built entirely from evidence at or before t0
  can still encode which actors turned out to matter, because the population it was fitted on was
  chosen with outcomes visible;
- what a cluster claims when the neighbourhood it rests on is incomplete — today every measured
  neighbourhood is, and `require_complete_neighbourhood` refuses all 60 of them.

## 9. Not claimed

No cluster, no entity, no merge, no probability, no score, no "same owner" claim. No lookback, no
threshold, no calibration. No association degree or distribution, no label association, no model, no
operational readiness. The counts in this document are counts of links, evidence items and checks.
