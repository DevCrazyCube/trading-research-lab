# B9d — Transaction-body reconstruction preregistration

**Status:** methodology frozen before B9d network execution. **Execution is not authorised by this
document** — see §10.
**Date:** 2026-07-29
**Author:** Claude (Seq 192)
**Population:** the 94,985 distinct successful in-window signatures of the tradable, non-Mayhem
B8b population
**Inputs opened read-only:** `research/b9c_signature_inventory.sqlite`
(SHA-256 `e735c6c59848ff57958402a7488474415c7f20febce7a12cf7227b4267c7391d`),
`research/b9a_outcomes.sqlite` (SHA-256 `882d47d19a331e805be5796cd7d8ab616c7af65391bd327e0221d3c51c4edc38`),
and the B8b cohort at freeze `56d8a83b…8374`

This freeze is written before any transaction body has been fetched or inspected.

**Pre-execution audit amendment (Codex, Seq 197):** §6 originally required
`transaction_index` while fetching only `getTransaction`, which does not supply that coordinate.
The amendment below adds preserved block-signature lookups for every involved slot, freezes the
conservative no-recall-claim branch in §8a, and corrects §10's cost floor. No transaction body had
been fetched when amended.

## 1. Independent re-derivation of the population (done before freezing)

The entire B9d scope rests on one number, so it was re-derived from the B9c artifact before this
document fixed anything. Streaming all 1,347,587 in-window observation rows and joining curve
membership to B9a's `is_mayhem_mode`:

| quantity | re-derived | published (Seq 191) |
|---|---:|---:|
| distinct in-window signatures | 1,347,469 | 1,347,469 |
| whole-cohort successful | 148,596 | 148,596 |
| whole-cohort failed | 1,198,873 | 1,198,873 |
| **tradable distinct** | **1,287,248** | 1,287,248 |
| **tradable successful** | **94,985** | 94,985 |
| tradable failed | 1,192,263 | 1,192,263 |
| Mayhem successful / failed | 53,611 / 6,610 | 53,611 / 6,610 |

All eight match. Additional integrity checks, all clean: **0** signatures carry contradictory
`err` status across curves; **0** signatures appear on both a Mayhem and a non-Mayhem curve, so the
population split is unambiguous; **0** curves appear in B9c but not B9a; exact deduplication removes
**118** observation rows, reproducing the published figure.

### 1a. A predicate trap that must be frozen, because it silently inverts the result

`signature_observation.err_json` stores `json.dumps(row["err"])`. A **successful** transaction is
therefore the four-character string `'null'`, and the column is **never** SQL `NULL` — verified:
0 SQL-NULL rows in-window.

The natural predicate `err_json IS NULL` therefore matches nothing and classifies **all 1,347,469
signatures as failed**. I made exactly this mistake on the first re-derivation pass and it produced
a clean, plausible, entirely wrong table (0 successful, 100% failed) that reproduced every *other*
published figure. **B9d must use `err_json = 'null'` for success and assert the resulting count
equals 94,985 before issuing a single fetch.** A run that derives a different population size stops.

## 2. Frozen purpose

B9d will answer only:

1. For each of the 94,985 transactions, what instructions does it contain, against the pinned
   official IDL, at every nesting level?
2. Which of those instructions mutate bonding-curve reserve state, and what are the exact
   pre- and post-instruction reserve values?
3. In canonical order, what is each member curve's reserve path across the frozen observation
   window?
4. What fraction of instructions, transactions and curves fail to classify, and exactly how?

It will **not** compute returns, exit windows, peak-reserve statistics used as a selection signal,
strategy rules, or any model feature. Those require a separate freeze after B9d reports its
classification completeness.

## 3. Frozen population and its derivation

The fetch set is fixed by this query against the pinned B9c artifact, and by nothing else:

```sql
SELECT DISTINCT o.signature
FROM signature_observation o
JOIN b9a.outcome c ON c.bonding_curve = o.bonding_curve
WHERE o.time_class = 'in_window'
  AND o.err_json  = 'null'
  AND c.is_mayhem_mode = 0;
```

- The run **asserts `COUNT(*) = 94,985`** and asserts both source SHA-256 values before any network
  call. Any mismatch is a hard stop, not a warning.
- Mayhem's 53,611 successful signatures are **not** fetched, under the pre-existing frozen exclusion
  ratified from B9a's measurement of administrative curve mutation. This is a safety policy, never
  a cost decision.
- The 1,192,263 failed tradable signatures are **not** fetched here. They remain preserved in B9c
  for execution-failure modelling; excluding them relies only on validator transaction atomicity —
  a failed transaction commits no state change — and on nothing about their economic relevance.

## 4. Program-version boundaries must be re-verified, not assumed

The observation range spans roughly **1.64 million slots**, from the earliest B8b launch slot
(433,894,233) to the cutoff slot (435,536,742). A decoder that assumes one interface across that
span is making a claim it has not checked.

What is currently on record: B0 measured the Pump program's last deploy at slot **433,095,571**
(2026-07-15 16:11:40 UTC), which is **799,000 slots before the window opens**. On that evidence no
upgrade falls inside the range.

That evidence is **not sufficient**, for two reasons that must be stated rather than discovered:

- **B0 ran 2026-07-27 at ~10:15 UTC. The cutoff slot's block time is 12:19:42 UTC the same day.**
  The inventory therefore does not cover the final **~2 hours** of the observation window.
- B0's history came from `getSignaturesForAddress` on the ProgramData account, whose **archival
  completeness is explicitly unverified** in `PLAN.md`.

**Frozen requirement.** Before decoding, B9d re-runs the upgrade inventory over
`[433,894,233, 435,536,742]` for both the Pump program and PumpSwap, preserves the responses, and:

- first decodes each current ProgramData account's last-deploy slot from a preserved
  `getAccountInfo` response. If that slot is before the observation range, this directly proves no
  later deployment occurred inside it. If it lies inside or after the range, preserved loader
  history must classify every candidate needed to prove the exact interval; a recent-first history
  list that does not cross below the range is incomplete and fails visibly;

- if **no** boundary is found, records that as a preserved, dated result and decodes with one pinned
  IDL revision;
- if **any** boundary is found, the decoder must be version-aware across it, the boundary slot is
  recorded, and every transaction is decoded under the revision in force at its slot.

Unknown or ambiguous boundary evidence fails visibly. The pinned IDL revision (URL, commit, and
retrieval date) is recorded in the artifact metadata; "the official IDL" without a revision is not a
pin.

## 5. Evidence artifact

A new SQLite database, `WAL`, `synchronous=FULL`, holding at least:

1. `metadata` — source paths and SHA-256s, pinned IDL revision and retrieval date, program ids,
   endpoint reference **without credentials**, cutoff slot, schema version, upgrade-boundary result,
   and a completion summary.
2. `raw_transaction` — the **byte-exact compressed response body** per signature, content-addressed
   by SHA-256, with request method, non-secret params, and receipt time. The stored bytes are the
   primary evidence; a reconstructed JSON object is not.
3. `instruction` — one row per instruction at every nesting level, carrying the canonical ordering
   key of §6, program id, discriminator, resolved IDL name or `UNKNOWN`, and account/arg references.
4. `reserve_observation` — per instruction that mutates curve reserves: curve, exact integer
   `virtual_*`/`real_*` values before and after, and the evidence they were read from.
5. `classification_failure` — every unknown discriminator, unparsed instruction, missing field, or
   ambiguity, with enough context to reproduce it. **This table being empty is a result, not a
   precondition.**
6. `raw_block_signatures` / `transaction_coordinate` — byte-exact preserved `getBlock` signature
   responses for every distinct involved slot, and the unique mapping from each frozen signature
   to its zero-based transaction index. Missing signatures, duplicates, or slot disagreement fail
   visibly.

Each raw response and its derived rows commit in **one** transaction. A completed artifact can never
be overwritten, even with a reset flag. A partial artifact resumes only after source metadata
matches exactly. A completed rerun must be byte-immutable — B9b's Seq 188 correction, where an
idempotent rerun rewrote identical metadata and changed the artifact hash, is the precedent this
requirement exists for.

### 5a. Encoding

Fetch with `encoding: "base64"`, `commitment: "finalized"`,
`maxSupportedTransactionVersion: 0`. Rationale: base64 returns the **transaction bytes themselves**,
so the preserved evidence is byte-exact rather than an RPC-normalised interpretation — the same
distinction B6d drew when it refused to call normalised polling JSON a raw provider frame.

Address-lookup-table entries must then be resolved from `meta.loadedAddresses`. Note that B7k
observed the opposite shape under `jsonParsed`, where the RPC resolves table entries *into*
`accountKeys` tagged `source: "lookupTable"` and `loadedAddresses` is consequently **absent** — a
guard that reads that absence as failure scored every graduation event `UNRESOLVABLE`. Whichever
encoding is used, the resolution predicate must be tested against a real payload of that encoding
before the full run, and must still fail when a table genuinely resolves nothing.

**Pre-flight, before the main run:** fetch a small sample and assert the response carries every
field B9d depends on — `meta.err`, `fee`, `innerInstructions`, `preBalances`/`postBalances`,
`preTokenBalances`/`postTokenBalances`, `logMessages`, and `loadedAddresses` where applicable. If
the shape does not carry them, the freeze is wrong and stops; it is not patched mid-run.

## 6. Canonical ordering

Ordering is `(slot, transaction_index, outer_instruction_index, inner_instruction_index)`, per
AGENTS.md. **Database insertion order is never used**, and no reserve path may be assembled from
`ROWID`, fetch order, or completion order. Any transaction whose ordering key cannot be fully
determined is a `classification_failure`, not a row placed by best guess.

`getTransaction` provides the slot but **not** `transaction_index`. B9d therefore fetches and
preserves `getBlock` with `transactionDetails: "signatures"` for every distinct slot in the frozen
population, locates each signature's unique list position, and reconciles that slot against the
transaction response. Offline re-derivation from B9c gives **38,853 distinct non-null slots** for
the 94,985 signatures (range 433,894,233–435,536,000). B9d asserts those figures before any network
call. Signature-list retrieval is part of the required population, not an optional enhancement.
This response-shape claim was checked against the official Solana RPC documentation on 2026-07-29:
[`getTransaction`](https://solana.com/docs/rpc/http/gettransaction) and
[`getBlock`](https://solana.com/docs/rpc/http/getblock).

## 7. Classification rules

- **Every Pump and PumpSwap instruction** in a fetched transaction is classified at outer and inner
  (CPI) levels. Every non-target instruction still retains its program id and canonical coordinate;
  known infrastructure families may receive a pinned classifier, but B9d does not pretend an
  arbitrary third-party program has a Pump IDL.
- An **unknown Pump or PumpSwap discriminator fails visibly** and is recorded. It is never dropped,
  never bucketed as "other", and never inferred from an adjacent event. An unrecognised non-target
  program id is preserved as a non-target program id and cannot silently be treated as a reserve
  mutation.
- **No event-name shortcut.** Decoding only `TradeEvent` and assuming everything else leaves reserves
  untouched is precisely the narrowing B9c refused to authorise. Non-trade instructions can mutate
  relevant state; that must be demonstrated against fetched bodies, not assumed away.
- Reserve values come from decoded instruction/event data reconciled against the transaction's own
  balance evidence. A reserve transition that does not reconcile is a failure row, not a repair.

## 8. Two scope limits that must be stated now, not found later

**8a. The index is address-based, and its exhaustiveness is inherited, not proven for this window.**
B9c enumerated `getSignaturesForAddress` on each bonding-curve address. B7h proved bidirectional
recall — full-block decode against curve histories, zero missing events — but for the **B7e window
and regime**, and `PLAN.md` states B7h does not generalise across regimes. Whether the address index
captures every transaction touching a curve, including those reaching it through an address lookup
table, is **an open question for this window.**

**Frozen resolution:** B9d takes branch (b). It publishes a prominent, unhedged caveat that
curve-history completeness is inherited from a different window and unverified here, and makes no
exhaustiveness claim. A recall experiment is a separate future preregistration with its own fixed
sample size, deterministic slot list, cost, and authorization; it cannot be designed after B9d
bodies are inspected and retrofitted as support. The earlier wording left both sample size and
branch choice free and therefore was not actually frozen.

**8b. Reserve paths end at graduation, by construction.** After a curve completes, trading moves to
a PumpSwap pool whose transactions need not touch the bonding-curve address, so they are absent from
this index. **16 of the tradable population graduated** (B9a). For those members B9d measures the
pre-migration path only, and must label it as truncated rather than reporting a path that appears to
end in silence.

## 9. Forbidden narrowings, carried forward and extended

No token, creator, wallet, activity-size, history-size, graduation, terminal-reserve, or outcome
filter may reduce the fetch set. B9b's history-size distribution and B9a's outcome table are
**inputs to membership only** and may not choose a cheaper subset.

**Outcome-dependent selection is already a live hazard here, on the record.** Seq 178 disclosed that
auditing B9a required cross-tabbing outcome against t=0 covariates, which contaminated the obvious
filter candidates — `is_cashback_enabled` separates the tradable population 1.83% vs 0.93%. Any
filter touching an examined covariate must be frozen and measured on a **fresh cohort, never B8b.**

**B8b is burned for future cohort selection** (DECISIONS, seven burned ranges, freeze §6.1). B9d
results may not be used to place a later window, and any future preregistration must check
disjointness against all seven and fail closed.

## 10. Cost, and the authorisation gate this document does not clear

The exact request floor is **94,985 transaction fetches + 38,853 block-signature fetches = 133,838
calls**, before boundary verification. B6j separately measured ~2.5 successful
`getTransaction` calls/s, so the transaction component alone retains its **~10.6-hour** planning
estimate. If—and only if—the endpoint serves `getBlock` signature calls at the same sustained rate,
the combined scenario is **~14.9 hours**. `getBlock` throughput and payload size are unmeasured, so
14.9 hours is not a lower bound or guarantee. Transaction bodies alone retain the rough **0.95 GB**
estimate; block-signature volume must not be invented. §8a now freezes the no-recall-claim branch,
so no recall-sample cost is included or implied.

**This is materially larger than anything the project has authorised.** The standing authorisation
on record (Seq 121) is 4 min/hour for ~6.2 hours, granted for B8b. **B9d execution requires a new,
explicit owner authorisation** covering duration, endpoint, the 38,853 block-signature lookups, and
the boundary re-verification. Freezing the method is free; running it is not, and this document
deliberately does not assume the second follows from the first.

## 11. Publication gates

B9d publishes no result unless: both source SHA-256s matched at start; the population re-derived to
exactly 94,985; every raw response hash re-verifies; the upgrade-boundary check completed and is
preserved; every instruction at every nesting level is classified or recorded as a failure;
all **38,853** expected slots have preserved signature lists and every frozen signature maps to one
unique transaction index; canonical ordering is complete for every reserve path; SQLite
`integrity_check` is `ok`; a completed
rerun is byte-immutable and makes zero RPC calls; and no completed source artifact changed hash.

**A high classification-failure rate is a publishable result.** Reporting "97% classified" while
quietly dropping the rest is the failure this project has documented twelve times: an instrument
reporting on something adjacent to the claim.

The output is a reserve path, not an exit measurement, a return, or a strategy. Whether any money
was available requires a further freeze.
