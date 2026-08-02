# B13f — preregistration: the prospective selective feature contract

Date: 2026-08-02. Author: Claude (handoff 90).
Status: **FROZEN. Committed alone, before the materializer that consumes it exists.**

This document is the whole of the first commit. No code, no test and no materializer accompanies it,
for the same reason B13e was split: a feature list committed alongside the machinery that computes
it can always be claimed to have been trimmed until the numbers came out well.

## 0. What this contract is NOT eligible for

**This contract may not be applied to B11a.** B11a's evaluation was frozen in B11b as a *no-model*
baseline over an explicitly declared 17-field t0 contract, and its unlock evidence was written
against that. Introducing a 99-field vector into that window would mean evaluating something nobody
preregistered on a window whose maturity conditions were set for something else.

`eligible_windows` is **empty**. Before any window may be added, a **new training/evaluation design**
must:

1. name a fresh window, disjoint from the burned ranges and from B11a;
2. state its own split — training folds, and an evaluation fold touched once;
3. **fit every transform on training folds only.** Nothing in this document is a fitted transform,
   and that is deliberate: the moment a scaler, an encoder or a selection rule is fitted, it must be
   fitted inside a fold, and this contract has no place to put one.

Until that exists, this vector may be materialized on synthetic fixtures and nowhere else.

## 1. Where every field comes from

Each of the 99 features is a **raw point-in-time fact already declared by an earlier
contract**. Nothing here is new arithmetic. The materializer reads the earlier records through their
own validators rather than recomputing anything, so a change in B11b, B13a or B13d cannot silently
diverge from what this vector claims to contain.

| block | source | count |
| --- | --- | --- |
| A | B11b's frozen t0 contract, **names unchanged** | 17 |
| B | B13a histories over the B13e fixed lookback, **renamed to name the window** | 26 |
| C | B13d raw concentration under **both** denominators | 56 |

### 1.1 Block A — B11b t0 fields (unchanged)

Names are carried through verbatim. Renaming them would fork a frozen contract, and two names for
one fact is how a later reader ends up with both.

| # | field |
| --- | --- |
| 1 | `t0_is_launch_instruction` |
| 2 | `launch_transaction_trade_count` |
| 3 | `creator_initial_buy_present` |
| 4 | `creator_initial_buy_quote_lamports` |
| 5 | `creator_initial_buy_token_units` |
| 6 | `t0_virtual_quote_lamports` |
| 7 | `t0_virtual_token_units` |
| 8 | `t0_real_quote_lamports` |
| 9 | `t0_real_token_units` |
| 10 | `launch_real_token_units` |
| 11 | `tokens_left_curve_units` |
| 12 | `token_total_supply_units` |
| 13 | `is_cashback_enabled` |
| 14 | `fee_bps_observed` |
| 15 | `creator_fee_bps_observed` |
| 16 | `cashback_fee_bps_observed` |
| 17 | `buyback_fee_bps_observed` |

### 1.2 Block B — history over the fixed lookback

Every one of these is computed over the **B13e window of 1,642,509 slots** and is renamed to say so.
B13a's `_observed` suffix says "this is what we saw"; `_in_lookback` says *what we looked at*, which
is the fact a reader needs in order not to read a count as a lifetime total.

| # | field |
| --- | --- |
| 18 | `creator_prior_launch_count_in_lookback` |
| 19 | `creator_prior_completion_count_in_lookback` |
| 20 | `creator_prior_launch_with_buy_count_in_lookback` |
| 21 | `creator_prior_buy_quote_lamports_in_lookback` |
| 22 | `creator_slots_since_previous_launch_in_lookback` |
| 23 | `user_prior_trade_count_in_lookback` |
| 24 | `user_prior_buy_count_in_lookback` |
| 25 | `user_prior_sell_count_in_lookback` |
| 26 | `user_prior_quote_in_lamports_in_lookback` |
| 27 | `user_prior_quote_out_lamports_in_lookback` |
| 28 | `user_prior_token_in_units_in_lookback` |
| 29 | `user_prior_token_out_units_in_lookback` |
| 30 | `user_prior_distinct_mint_count_in_lookback` |
| 31 | `token_slots_since_launch` |
| 32 | `token_prior_trade_count_in_lookback` |
| 33 | `token_prior_buy_count_in_lookback` |
| 34 | `token_prior_sell_count_in_lookback` |
| 35 | `token_prior_quote_in_lamports_in_lookback` |
| 36 | `token_prior_quote_out_lamports_in_lookback` |
| 37 | `token_prior_distinct_user_count_in_lookback` |
| 38 | `token_completed_before_t0` |
| 39 | `creator_funding_inbound_edge_count_in_lookback` |
| 40 | `creator_funding_outbound_edge_count_in_lookback` |
| 41 | `creator_funding_inbound_lamports_in_lookback` |
| 42 | `creator_funding_outbound_lamports_in_lookback` |
| 43 | `creator_funding_distinct_counterparty_count_in_lookback` |

**Deliberately excluded from Block B:**

- `counts_are_lower_bounds` — under this contract the window must be **complete** or the vector is
  unavailable (§3), so this is a constant. A constant is not a feature.
- `actor_seen_in_window` — derivable from the counts under a complete window. Two names for one
  fact.
- **Every absolute slot number** (`first_observed_launch_slot`, `previous_observed_launch_slot`,
  `first_observed_trade_slot`, `last_observed_trade_slot`, `launch_slot`). An absolute slot is a
  calendar index: a model given one can learn "later is better", which is not a property of a token
  and does not survive contact with a different window. The *relative* spans
  (`slots_since_previous_launch`, `slots_since_launch`) carry the same information without the
  calendar, and B13a already computes them — so no new arithmetic is needed to exclude the absolute
  ones.
- The token block's `launch_transaction_trade_count_observed`,
  `launch_transaction_creator_buy_present` and `launch_transaction_creator_buy_quote_lamports_observed`
  — these duplicate Block A's B11b fields exactly. The B11b names win.
- `launch_observed_in_window` — a coverage fact about the collection, not a fact about the token.

### 1.3 Block C — raw concentration under both denominators

Every share is a **gcd-reduced rational flattened into two named integer fields**, a numerator and a
denominator. Not a single "share" field, and never a decimal: a later model adapter handed one
number cannot silently float-round two.

Both denominators are always present. B13d's whole argument applies unchanged — concentration is
whatever the denominator says it is, so publishing one of them is a choice made on the reader's
behalf.

Note that after gcd reduction the pair no longer carries the magnitude, so `*_units` and
`*_denominator_units` travel alongside. They are different facts: the ratio and the scale.

| # | field |
| --- | --- |
| 44 | `concentration_total_supply_denominator_units` |
| 45 | `concentration_total_supply_holder_count` |
| 46 | `concentration_total_supply_top_1_units` |
| 47 | `concentration_total_supply_top_1_share_numerator` |
| 48 | `concentration_total_supply_top_1_share_denominator` |
| 49 | `concentration_total_supply_top_5_units` |
| 50 | `concentration_total_supply_top_5_share_numerator` |
| 51 | `concentration_total_supply_top_5_share_denominator` |
| 52 | `concentration_total_supply_top_10_units` |
| 53 | `concentration_total_supply_top_10_share_numerator` |
| 54 | `concentration_total_supply_top_10_share_denominator` |
| 55 | `concentration_total_supply_herfindahl_numerator` |
| 56 | `concentration_total_supply_herfindahl_denominator` |
| 57 | `concentration_circulating_user_denominator_units` |
| 58 | `concentration_circulating_user_holder_count` |
| 59 | `concentration_circulating_user_top_1_units` |
| 60 | `concentration_circulating_user_top_1_share_numerator` |
| 61 | `concentration_circulating_user_top_1_share_denominator` |
| 62 | `concentration_circulating_user_top_5_units` |
| 63 | `concentration_circulating_user_top_5_share_numerator` |
| 64 | `concentration_circulating_user_top_5_share_denominator` |
| 65 | `concentration_circulating_user_top_10_units` |
| 66 | `concentration_circulating_user_top_10_share_numerator` |
| 67 | `concentration_circulating_user_top_10_share_denominator` |
| 68 | `concentration_circulating_user_herfindahl_numerator` |
| 69 | `concentration_circulating_user_herfindahl_denominator` |
| 70 | `concentration_owner_grouping_available` |
| 71 | `concentration_owner_total_supply_holder_count` |
| 72 | `concentration_owner_total_supply_top_1_units` |
| 73 | `concentration_owner_total_supply_top_1_share_numerator` |
| 74 | `concentration_owner_total_supply_top_1_share_denominator` |
| 75 | `concentration_owner_circulating_user_holder_count` |
| 76 | `concentration_owner_circulating_user_top_1_units` |
| 77 | `concentration_owner_circulating_user_top_1_share_numerator` |
| 78 | `concentration_owner_circulating_user_top_1_share_denominator` |
| 79 | `concentration_role_user_units` |
| 80 | `concentration_role_bonding_curve_units` |
| 81 | `concentration_role_vault_units` |
| 82 | `concentration_role_burn_units` |
| 83 | `concentration_role_program_owned_units` |
| 84 | `concentration_role_unknown_units` |
| 85 | `concentration_accounts_enumerated` |
| 86 | `concentration_accounts_with_positive_balance` |
| 87 | `concentration_zero_balance_account_count` |
| 88 | `concentration_unresolved_owner_account_count` |
| 89 | `concentration_distinct_owners_resolved` |
| 90 | `concentration_units_held_in_accounts` |
| 91 | `concentration_declared_supply_units` |
| 92 | `concentration_supply_residual_units` |
| 93 | `concentration_creator_share_available` |
| 94 | `concentration_creator_total_supply_units` |
| 95 | `concentration_creator_total_supply_share_numerator` |
| 96 | `concentration_creator_total_supply_share_denominator` |
| 97 | `concentration_creator_circulating_user_units` |
| 98 | `concentration_creator_circulating_user_share_numerator` |
| 99 | `concentration_creator_circulating_user_share_denominator` |

## 2. What may never be a feature here

| excluded | why |
| --- | --- |
| **B13b association evidence, of any kind** | it declares itself `uncalibrated_evidence_only`; admitting it would turn "we do not know" into a number a model weights |
| **Any cluster field** | none exists, and B13d's cluster adjustment is structurally unavailable |
| **B13c raw text, URLs, author identities** | strings never enter a feature block; that rule is checkable without anyone having to notice which strings are identities |
| **Sentiment, engagement, popularity, market-cap or price transforms** | judgements, not observations |
| **Ranks, quantiles, logarithms, normalisation, standardisation** | every one is a transform fitted on a distribution, and a distribution computed outside a training fold has already seen the evaluation data |
| **Any value selected from a distribution** | the selection is the leak, whatever the value |
| **Identities, coordinates and provenance** | they live in `grouping` and `evidence` and are never features |

A feature may **never** inspect an outcome, a label, or any path state after t0. The materializer
receives no outcome record, and its inputs are validated against the t0 boundary before a single
field is read.

## 3. Availability: unavailable is not zero

A vector is **unavailable, with reasons**, in each of these cases. Nothing is imputed — not a zero,
not a median, and not a missingness indicator whose value was chosen by looking at outcomes.

| code | condition |
| --- | --- |
| `V01_history_incomplete` | any contributing B13a history is left- or right-truncated, or its coverage does not reach the lookback start |
| `V02_unresolved_decode_evidence` | unresolved decode evidence at or before this subject's t0 |
| `V03_concentration_not_atomic_or_incomplete` | the holder snapshot spans more than one slot, or its enumeration is incomplete |
| `V04_required_denominator_undefined` | either required denominator is zero, so shares over it do not exist |
| `V05_evidence_after_t0` | any contributing record carries a coordinate after t0 |
| `V06_source_hash_drift` | a source record's hash does not match what it claims |
| `V07_contract_hash_mismatch` | this document's frozen block is not the one the materializer was written against |

**Why unavailability rather than imputation.** A zero substituted for a missing count is a claim
that the thing did not happen. A median is a claim that this subject was typical — and the median
is computed from a distribution, which is a transform fitted outside a fold. A missingness flag
whose encoding was chosen because it improved a score is the outcome leaking in through the door
marked "handling missing data". The honest option is to say the vector does not exist for this
subject, and to say why.

### 3.1 Genuinely optional raw fields

Two groups of fields are optional *by nature* rather than by failure, and their availability rules
are frozen here and represented **separately from the numeric fields**:

| availability field | governs | available when |
| --- | --- | --- |
| `concentration_owner_grouping_available` | the four owner-grouping fields per denominator | every token account has exact owner evidence |
| `concentration_creator_share_available` | the three creator-share fields per denominator | the creator binding is exact **and** every owner is resolved |

When an availability field is `false`, the fields it governs are `null` — **never zero**. A creator
share of zero means the creator holds nothing; `null` means we cannot say. Those are different
facts, and a model that cannot tell them apart will learn from the difference between them anyway.

## 4. Types and serialization

- **Integers, booleans and `null` only.** No float may appear anywhere.
- Rationals are flattened into named integer numerator/denominator pairs, both gcd-reduced by
  B13d before they arrive here.
- Every vector carries `schema_version`, the **feature contract hash**, the **preregistration
  hash**, the **source record hashes** it was built from, and its own t0 coordinate.
- Canonical JSON with sorted keys, and a deterministic vector hash.
- The materializer must not mutate its inputs, and must be independent of the order they arrive in.

## 5. Frozen parameters

```json
{
  "preregistration_id": "B13F_FEATURE_CONTRACT_V1",
  "feature_contract_version": "1.0.0",
  "feature_count": 99,
  "feature_order": [
    "t0_is_launch_instruction",
    "launch_transaction_trade_count",
    "creator_initial_buy_present",
    "creator_initial_buy_quote_lamports",
    "creator_initial_buy_token_units",
    "t0_virtual_quote_lamports",
    "t0_virtual_token_units",
    "t0_real_quote_lamports",
    "t0_real_token_units",
    "launch_real_token_units",
    "tokens_left_curve_units",
    "token_total_supply_units",
    "is_cashback_enabled",
    "fee_bps_observed",
    "creator_fee_bps_observed",
    "cashback_fee_bps_observed",
    "buyback_fee_bps_observed",
    "creator_prior_launch_count_in_lookback",
    "creator_prior_completion_count_in_lookback",
    "creator_prior_launch_with_buy_count_in_lookback",
    "creator_prior_buy_quote_lamports_in_lookback",
    "creator_slots_since_previous_launch_in_lookback",
    "user_prior_trade_count_in_lookback",
    "user_prior_buy_count_in_lookback",
    "user_prior_sell_count_in_lookback",
    "user_prior_quote_in_lamports_in_lookback",
    "user_prior_quote_out_lamports_in_lookback",
    "user_prior_token_in_units_in_lookback",
    "user_prior_token_out_units_in_lookback",
    "user_prior_distinct_mint_count_in_lookback",
    "token_slots_since_launch",
    "token_prior_trade_count_in_lookback",
    "token_prior_buy_count_in_lookback",
    "token_prior_sell_count_in_lookback",
    "token_prior_quote_in_lamports_in_lookback",
    "token_prior_quote_out_lamports_in_lookback",
    "token_prior_distinct_user_count_in_lookback",
    "token_completed_before_t0",
    "creator_funding_inbound_edge_count_in_lookback",
    "creator_funding_outbound_edge_count_in_lookback",
    "creator_funding_inbound_lamports_in_lookback",
    "creator_funding_outbound_lamports_in_lookback",
    "creator_funding_distinct_counterparty_count_in_lookback",
    "concentration_total_supply_denominator_units",
    "concentration_total_supply_holder_count",
    "concentration_total_supply_top_1_units",
    "concentration_total_supply_top_1_share_numerator",
    "concentration_total_supply_top_1_share_denominator",
    "concentration_total_supply_top_5_units",
    "concentration_total_supply_top_5_share_numerator",
    "concentration_total_supply_top_5_share_denominator",
    "concentration_total_supply_top_10_units",
    "concentration_total_supply_top_10_share_numerator",
    "concentration_total_supply_top_10_share_denominator",
    "concentration_total_supply_herfindahl_numerator",
    "concentration_total_supply_herfindahl_denominator",
    "concentration_circulating_user_denominator_units",
    "concentration_circulating_user_holder_count",
    "concentration_circulating_user_top_1_units",
    "concentration_circulating_user_top_1_share_numerator",
    "concentration_circulating_user_top_1_share_denominator",
    "concentration_circulating_user_top_5_units",
    "concentration_circulating_user_top_5_share_numerator",
    "concentration_circulating_user_top_5_share_denominator",
    "concentration_circulating_user_top_10_units",
    "concentration_circulating_user_top_10_share_numerator",
    "concentration_circulating_user_top_10_share_denominator",
    "concentration_circulating_user_herfindahl_numerator",
    "concentration_circulating_user_herfindahl_denominator",
    "concentration_owner_grouping_available",
    "concentration_owner_total_supply_holder_count",
    "concentration_owner_total_supply_top_1_units",
    "concentration_owner_total_supply_top_1_share_numerator",
    "concentration_owner_total_supply_top_1_share_denominator",
    "concentration_owner_circulating_user_holder_count",
    "concentration_owner_circulating_user_top_1_units",
    "concentration_owner_circulating_user_top_1_share_numerator",
    "concentration_owner_circulating_user_top_1_share_denominator",
    "concentration_role_user_units",
    "concentration_role_bonding_curve_units",
    "concentration_role_vault_units",
    "concentration_role_burn_units",
    "concentration_role_program_owned_units",
    "concentration_role_unknown_units",
    "concentration_accounts_enumerated",
    "concentration_accounts_with_positive_balance",
    "concentration_zero_balance_account_count",
    "concentration_unresolved_owner_account_count",
    "concentration_distinct_owners_resolved",
    "concentration_units_held_in_accounts",
    "concentration_declared_supply_units",
    "concentration_supply_residual_units",
    "concentration_creator_share_available",
    "concentration_creator_total_supply_units",
    "concentration_creator_total_supply_share_numerator",
    "concentration_creator_total_supply_share_denominator",
    "concentration_creator_circulating_user_units",
    "concentration_creator_circulating_user_share_numerator",
    "concentration_creator_circulating_user_share_denominator"
  ],
  "source_contracts": {
    "b11b_t0_features": "1.0.0",
    "b13a_history": "1.0.0",
    "b13d_concentration": "1.0.0",
    "b13e_lookback_preregistration": "B13E_LOOKBACK_V1"
  },
  "lookback_slots": 1642509,
  "eligible_for_b11a": false,
  "eligible_windows": [],
  "requires_new_training_evaluation_design": true,
  "transforms_fitted": [],
  "value_types_permitted": [
    "integer",
    "boolean",
    "null"
  ],
  "floats_permitted": false,
  "rationals_flattened_to_named_integer_pairs": true,
  "imputation_permitted": false,
  "missingness_indicator_selected_from_outcomes": false,
  "identities_in_features": false,
  "coordinates_in_features": false,
  "provenance_in_features": false,
  "excluded_sources": [
    "b13b_association_evidence",
    "cluster_fields",
    "b13c_raw_text",
    "b13c_urls",
    "b13c_author_identities",
    "sentiment",
    "engagement",
    "market_cap_transforms",
    "ranks",
    "quantiles",
    "logarithms",
    "normalisation",
    "any_value_selected_from_a_distribution"
  ],
  "optional_fields": {
    "concentration_owner_grouping_available": [
      "concentration_owner_total_supply_holder_count",
      "concentration_owner_total_supply_top_1_units",
      "concentration_owner_total_supply_top_1_share_numerator",
      "concentration_owner_total_supply_top_1_share_denominator",
      "concentration_owner_circulating_user_holder_count",
      "concentration_owner_circulating_user_top_1_units",
      "concentration_owner_circulating_user_top_1_share_numerator",
      "concentration_owner_circulating_user_top_1_share_denominator"
    ],
    "concentration_creator_share_available": [
      "concentration_creator_total_supply_units",
      "concentration_creator_total_supply_share_numerator",
      "concentration_creator_total_supply_share_denominator",
      "concentration_creator_circulating_user_units",
      "concentration_creator_circulating_user_share_numerator",
      "concentration_creator_circulating_user_share_denominator"
    ]
  },
  "unavailability_codes": [
    "V01_history_incomplete",
    "V02_unresolved_decode_evidence",
    "V03_concentration_not_atomic_or_incomplete",
    "V04_required_denominator_undefined",
    "V05_evidence_after_t0",
    "V06_source_hash_drift",
    "V07_contract_hash_mismatch"
  ],
  "required_denominators": [
    "total_supply",
    "circulating_user"
  ],
  "grouping_fields": [
    "mint",
    "bonding_curve",
    "creator",
    "create_user",
    "t0_user"
  ]
}
```

## 6. Attestation

No model has been fitted, no transform has been selected, no window has been named and no real
corpus has been read. The field list above was assembled from three already-committed contracts by
mechanical enumeration; every exclusion in §1.2 and §2 is stated with its reason, so a later reader
can disagree with a judgement rather than discover it.
