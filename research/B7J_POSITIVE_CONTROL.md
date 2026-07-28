# B7j — Graduation-Anchor Positive Control: Result

**Run:** 2026-07-27 → 2026-07-28
**Preregistration:** `research/B7J_POSITIVE_CONTROL_PREREGISTRATION.md`, frozen at SHA-256
`4a5c344522883e6bba0c8ef4d4e8be3b8b509bc3730a6b2419aae73b70a333d1` **before** the run.
**Artifact:** `research/b7j_positive_control_435564885_435565324.sqlite`, SHA-256
`4ca3a1c93770559d7a97d99afe0b30599b42ee077a471e909684e4ecc2c1373b`
Read-only throughout. No signing, no spending, no deployment, no live or devnet transactions.

## Result: **PASS**

```json
{"result": "PASS", "window": [435564885, 435565324],
 "reference_events": 4, "candidate_events": 4,
 "missing_from_candidate": 0, "extra_in_candidate": 0,
 "reference_event_types": ["CompleteEvent", "CompletePumpAmmMigrationEvent"],
 "both_types_present": true, "unresolved_slots": {}, "run_errors": 0,
 "distinct_bonding_curves": 2}
```

Every frozen PASS condition is satisfied: at least one reference instance of **each** event type,
full slot accounting, zero decode and fetch errors, and exact bidirectional equality on the frozen
equality projection.

### The two directions are not equally strong (correction, 2026-07-28)

"Exact bidirectional equality" is accurate but easy to over-read, so it is qualified here:

- **`missing_from_candidate = 0` is the load-bearing, purely empirical result.** Every graduation
  anchor found by exact full-block decoding was independently surfaced by the address-history path.
  Nothing in the design forces this direction to come out clean. **This is the recall claim.**
- **`extra_in_candidate = 0` is partly structural, not purely empirical.** The candidate path
  discards any decoded event whose `mint` is not in the reference-discovered mint set
  (preregistration line 79). It therefore **cannot** surface an event belonging to some other mint,
  so this direction could not have produced extras of that kind regardless of the data.

That filter is deliberate and correct — it is the fix for the spurious-extras defect caught in B7i
amendment (1), where an unfiltered candidate side would fail for reasons unrelated to recall. But
the two directions should not be read as two independent tests of equal weight. **The recall
direction is unaffected and the PASS stands.**

## Independent verification (recomputed from the artifact, not read from the summary)

| Check | Result |
|---|---|
| SQLite `integrity_check` | **ok** |
| Slot accounting | **439 / 439 retrieved**, zero unresolved, zero errors |
| Raw blocks persisted | **439**, all distinct, contiguous `435,564,885`–`435,565,323` |
| History pages persisted | **9** (1 + 8), **both curve boundaries proven** |
| Candidate transactions persisted | **6,542**, all distinct signatures |
| `run_error` rows | **0** |
| Reference events | 2 `CompleteEvent` + 2 `CompletePumpAmmMigrationEvent` |
| Candidate events | 2 `CompleteEvent` + 2 `CompletePumpAmmMigrationEvent` |
| **Bidirectional equality, recomputed** | reference − candidate = **0**; candidate − reference = **0**; **sets identical** |

The envelope contained **two** instances of each event type, not the one each that B7a documented.
The additional positives were **included, not dropped**, as the freeze required — discarding them
would have turned a clean test into a curated one.

## What this establishes

**The bonding-curve address-history discovery path surfaces graduation anchors that exist in
blocks.** Every `CompleteEvent` and `CompletePumpAmmMigrationEvent` found by exact full-block
decoding on the public endpoint was also found, byte-identically, by the address-history path on
the credentialed endpoint — the same mechanism B7e relied on, whose recall B7h had validated for
`TradeEvent` only.

Path independence held as designed: **different RPC methods** (`getBlock` full decode versus
`getSignaturesForAddress` + `getTransaction`) on **different providers**, with fallback forbidden.

## What this does NOT establish — binding prohibitions from the freeze

1. **No prevalence inference.** The window was chosen *because* it contains positives. Nothing here
   says how often tokens graduate or migrate.
2. **No performance inference.** Nothing about returns, exit liquidity, or strategy viability.
3. **No cohort inference.** The envelope sits ~5.5M slots after the B7e launch window; these are
   **not** B7e cohort members. This says nothing about whether any of the 200 cohort tokens
   graduated, and **does not validate B7e's zero-anchor observation** through cutoff `435,570,000`.
4. **No same-token or T1b inference.** Whether a completion and a migration here share a mint is
   **out of scope and prohibited**. Detector recall is measured per event type; the T1a→T1b
   transition needs a separate design.
5. **No generalisation across regimes.** One program version, one 439-slot window.

## Limitation carried forward, unresolved

**Common-mode decoder failure is not excluded.** Both paths use the same pinned IDL
(`b90bc471…8e49`) and the same decode logic. A graduation-event layout the decoder fails to
recognise or mis-parses would be missed **identically by both paths**, and this comparison would
still report perfect agreement. B7j tests *discovery* recall, not *decoding* completeness. No
evidence in this project addresses that.

## Process note

The run was, at one point, believed to have been externally terminated; that inference was false —
process visibility crosses a sandbox PID namespace boundary and `pgrep` could not see the live
writer. No resume was launched and nothing was modified. See `agent_discussion.md` Seq 61.

Two implementation defects surfaced by that false alarm remain worth fixing before the scanner is
reused:

- **Candidate event rows are written only in a final batch** after the whole candidate loop, so a
  genuine process death mid-loop would lose every decoded candidate event despite the raw
  transactions being safely persisted.
- **The metadata-reuse resume path clears all raw blocks, history pages and candidate
  transactions.** That was correct when every run rescanned from scratch; it is harmful now that
  expensive evidence accumulates, and should be replaced by an artifact-resume mode that
  reconstructs from stored raw data and fetches only what is missing.
