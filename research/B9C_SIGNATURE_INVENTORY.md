# B9c — Evidence-grade signature inventory and lossless narrowing

**Status:** complete; B9d transaction fetching not started  
**Access date:** 2026-07-29  
**Frozen method:** `research/B9C_SIGNATURE_INVENTORY_PREREGISTRATION.md`  
**Population:** all 1,601 B8b members, with the pre-existing Mayhem policy reported separately  
**Source:** configured Solana mainnet JSON-RPC; credential omitted  
**Artifact:** `research/b9c_signature_inventory.sqlite` (840 MiB), SHA-256
`e735c6c59848ff57958402a7488474415c7f20febce7a12cf7227b4267c7391d`

## Question

B9b showed that naive transaction-body reconstruction would require at least 1.26 million fetches,
but it did not preserve raw pages and counted through the later observation date. B9c asks how much
work remains after only the lossless exclusions frozen in advance: exact signature deduplication,
the ratified observation envelope, and validator-reported transaction failure.

This is still an inventory. It does not identify trades, reconstruct reserves, measure exit
windows, or calculate returns.

## Method and evidence preservation

`scripts/b9c_signature_inventory.py` reads the audited B9a cohort `mode=ro`. It resolved the
ratified cutoff timestamp **1785154782** (2026-07-27 12:19:42 UTC) to slot **435,536,742**;
the preserved `getBlockTime` response equals the cutoff timestamp exactly, and the immediately
produced successor slot **435,536,743** has time **1785154783**.

For every bonding curve, finalized `getSignaturesForAddress` pages were fetched recent-first until
an empty page or a page crossing below that member's launch slot proved the lower boundary. The
40-page safety cap was never reached. Each exact JSON-RPC response body was zlib-compressed and
committed atomically with its normalized rows. Credentials and endpoint URLs were not persisted.

The artifact contains:

- 1,601/1,601 curves with `boundary_proven = 1`, status `complete`, and no errors or caps;
- 4,167 curve-history pages and 24 preserved cutoff-resolution responses;
- 1,347,905 normalized curve/signature observations;
- byte hashes that verify for every raw response;
- exact raw-to-normalized replay equality for all 4,167 pages and 1,347,905 rows;
- SQLite `integrity_check = ok`.

The completed artifact reruns with zero RPC requests and is byte-immutable: before/after SHA-256
was identical to the value above.

## Results

### Frozen observation envelope

| classification | observation rows | distinct signatures |
|---|---:|---:|
| before member launch | 13 | 13 |
| **inside frozen window** | **1,347,587** | **1,347,469** |
| after cutoff | 305 | 305 |

Exact cross-curve deduplication removes only **118 rows (0.0088%)**. It is valid but operationally
immaterial; almost every address observation is already a distinct transaction.

### Validator outcome classification

| population | distinct in-window signatures | successful (`err = null`) | failed (`err != null`) | successful share |
|---|---:|---:|---:|---:|
| whole cohort | 1,347,469 | **148,596** | 1,198,873 | 11.03% |
| **tradable, non-Mayhem** | **1,287,248** | **94,985** | **1,192,263** | **7.38%** |
| excluded Mayhem | 60,221 | 53,611 | 6,610 | 89.02% |

The tradable reserve-state candidate workload is therefore **94,985 transaction bodies**, a
92.62% reduction from its complete distinct-signature inventory. Failed transactions remain in
the artifact and are excluded only from state-mutation fetching because Solana transactions are
atomic; they are not discarded from future execution-failure modeling.

## Interpretation

- **Verified fact:** exact deduplication does not solve the workload problem; only 118 duplicate
  curve observations occur inside the frozen window.
- **Verified fact:** validator outcome classification does solve most of the reserve-state fetch
  workload. Only 94,985 of 1,287,248 distinct tradable signatures can have committed state changes.
- **Working estimate:** at B6j's separately measured ~2.5 successful `getTransaction` calls/second,
  94,985 fetches imply about **10.6 continuous hours** rather than at least 5.8 days. At B6j's rough
  10 KB/transaction, response volume is about **0.95 GB**. Both are cross-run planning estimates,
  not endpoint guarantees.
- **Verified fact with an important non-inference:** the Mayhem/tradable failure-share difference is
  descriptive of address-indexed transactions, not evidence that Mayhem is safer or more
  profitable. Mayhem remains excluded because B9a measured administrative curve mutation. The
  populations and transaction mix differ sharply, and B9c does not decode instruction identity.
- **Open question:** successful signatures include trades, creates, maintenance, claims, migration,
  and unknown instructions. B9c does not authorize an event-name shortcut. B9d must fetch and
  classify all 94,985 successful tradable transaction bodies, preserve raw responses, and fail
  visibly on unknown instructions before reserve paths can be reconstructed.
- **Open question:** failed transaction metadata is sufficient to prove no committed state mutation,
  but full payer costs and failure causes still require transaction bodies when execution modeling
  reaches that phase. B9c preserves the complete failed-signature inventory for that later work.

## Verification

```bash
python3 -m pytest tests/test_b9c_signature_inventory.py -q
SOLANA_RPC_URL='<credential-bearing endpoint>' \
  python3 scripts/b9c_signature_inventory.py --workers 4 --max-pages 40
python3 -m pytest -q
```

Focused verification passes 10 tests. The completed-artifact rerun verifies raw hashes,
raw-to-normalized equality, membership terminal states, counts, integrity, zero network work, and
byte immutability. The full repository suite result is recorded in the release handoff.
