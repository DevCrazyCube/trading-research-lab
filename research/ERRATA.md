# Errata index

Every correction issued against a committed result or a published note, newest first. A result's
sealed artifact is **never** rewritten to repair a statement; corrections are issued here and, where
the correction concerns a spent pass, as a bound erratum document.

Entries in `B19_EVALUATION_LEDGER.json` carry an `errata` field pointing here, so a reader
verifying a pass meets the correction at the point they verify it rather than having to find this
file.

| against | kind | what was wrong | numbers affected |
|---|---|---|---|
| `B19G_EVALUATION_RESULT.json` (ledger 3, `8e5c66d3…`) | [erratum 1](B19G_ERRATUM_1_CENSORING_STATEMENT.md) | the censoring statement, inherited verbatim from B19C as required, describes live shadow recorders that do not exist on a historical window | **none** — artifact byte-identical |
| `B19G_REGIME_STABILITY_NOTE.md` | amended in place (development note, not frozen) | claimed the two windows are "roughly a week apart" when the observed extents are 3.7 hours apart; claimed p90 agreement "within 5%" when two of six groups diverge by 21.2% and 16.8% | none — the note carries no result figures of its own |
| `B19_EVALUATION_LEDGER.json` entry 2 | corrected in place, `corrected_from` recorded | keyed on a stale `study_id` literal (`B19F…_V1`) after the document was superseded to `_V2`, which left `_V2` reading as an unspent pass | none — `result_sha256` unchanged and still matches |
| `B19_COST_FLOOR_FINDING.json` | superseded to V2, withdrawn blocks retained and labelled | omitted curve slippage entirely; computed the exit fee on the wrong base; **reported the residual with the wrong sign**, describing an adverse drift that is actually favourable | yes — toll 4.73% → 5.40%, residual −0.42% → +0.25% |
| `B15M_PAYABILITY_DOWNSET_PROOF.md` | v1 refuted, corrected, appendix retained | hypothesis stated as "reserves non-negative", admitting `virtual_quote = 0` where the predicate is not total | none — the refuting state is unreachable in production |

## Why corrections are visible rather than tidy

Each row above could have been quietly fixed. Keeping them costs nothing and buys the one thing a
reader cannot otherwise get: a way to judge how often this project is wrong, and about what. Two of
these were caught by a reviewer, one by an adversarial agent executing what a human had only read,
and one by a test that failed for a reason nobody predicted.
