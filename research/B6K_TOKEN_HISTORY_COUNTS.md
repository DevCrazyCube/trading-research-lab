# B6K — Launch-selected token history counts

**Status:** provisional measurement; insufficient sample for a lifetime distribution  
**Access date:** 2026-07-27  
**Program/version scope:** current Pump program at `6EF8…F6P`; `CreateEvent` decoded from the pinned official IDL `research/pump_idl_9c82f61.json`  
**Source:** Helius Solana mainnet JSON-RPC (`mainnet.helius-rpc.com`); credential intentionally omitted

## Question

B6J provisionally sized cohort backfill using an unmeasured assumption that a token lifetime contains hundreds to low thousands of address transactions. B6K asks what launch-selected tokens actually show.

## Method

`scripts/b6k_token_lifetime_counts.py` scans Pump program signatures newest-to-oldest, fetches finalized transactions with bounded ordinary-request concurrency, and decodes Anchor `CreateEvent` log payloads. The current pinned IDL places three Borsh strings before the mint pubkey. Only decoded creates enter the cohort; recently traded tokens do not.

For each launch mint, `getSignaturesForAddress` is paginated to a cap of 10,000. The endpoint URL is supplied only through `SOLANA_RPC_URL`; output and files contain only `configured-mainnet`.

## Result

Among the newest 1,000 Pump program signatures, two `CreateEvent` launches were decoded. Their address histories at observation time contained **594** and **3,819** signatures. Neither reached the 10,000-signature pagination cap.

The registered Helius endpoint supported concurrent ordinary JSON-RPC requests. JSON-RPC batch attempts were rejected and are not used by the final script. Four workers completed the launch-selected scan without an unhandled rate-limit failure.

## Interpretation

- **Verified fact:** these two launch-selected mint addresses had 594 and 3,819 indexed signatures respectively when observed.
- **Working hypothesis:** B6J's “hundreds to low thousands” order-of-magnitude assumption may be plausible, but this sample is far too small to validate its distribution or cohort/day estimate.
- **Open question:** both launches were recent and can acquire future signatures. Exhausting history pagination means complete *history to observation time*, not a completed token lifetime.
- **Open question:** address signatures include non-Pump activity and have not been decoded into trades, failures, migration, or terminal state.

No percentile, mean, or completed-lifetime claim is made from `n=2`. A defensible follow-up must discover an exhaustive older launch window, define an observation cutoff and completion/censoring rule, then decode each address history.

## Reproducibility

```bash
SOLANA_RPC_URL='<credential-bearing endpoint>' \
  python scripts/b6k_token_lifetime_counts.py \
  --tokens 20 --cap 10000 --scan-limit 1000 --workers 4
```

The credential must never be placed in a tracked file or captured output.
