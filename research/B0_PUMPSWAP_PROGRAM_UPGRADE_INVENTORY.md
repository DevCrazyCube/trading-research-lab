# B0 — PumpSwap Program Upgrade Inventory

Run: 2026-07-27. Read-only mainnet RPC; no keys, signing, or transactions.

## Identity and provenance

The official `pump-fun/pump-public-docs` `idl/pump_amm.json`, pinned at commit
`9c82f61cb711b044a17f770ab8ce9f9bdf78f333`, identifies PumpSwap as
`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`. Its upgradeable-loader ProgramData account is
`6naEzKeUuFh1Jeeu51NXQgr5qkXgXtc9WKNct4xynVJc`.

The audited `scripts/b0_classify_transactions.py` method was applied unchanged. Evidence is
persisted at `research/b0_pumpswap_classification_2026-07-27.jsonl`.

## Verified public-RPC results

| Class | Transactions |
|---|---:|
| Upgrade | 23 |
| DeployWithMaxDataLen | 1 |
| ExtendProgram | 3 |
| SetAuthority | 1 |
| No loader instruction found | 3 |
| Total signatures | 31 |
| Fetch errors | 0 |

All 23 `Upgrade` transactions succeeded. Nine occurred in 2026. The latest was slot
433,112,355 at **2026-07-15 18:07:31 UTC**.

## July 15 boundary correlation

Official docs commit `2c22246b670812e2392e5f94b9543f500d6c9e15`, authored at
2026-07-15 18:13:17 UTC, changed `idl/pump_amm.json`, `idl/pump_amm.ts`, and
`docs/PUMP_SWAP_README.md` for “pool virtual quotes reserves.” This is approximately six minutes
after the observed PumpSwap upgrade and is strong evidence that the boundary changed the public
PumpSwap interface. The documentation diff is evidence of a public interface change, not proof
that every changed field was deployed in that exact transaction.

The bonding-curve Pump program also upgraded on 2026-07-15 at 16:11:40 UTC, but the official
repository has no corresponding July change to `idl/pump.json`; its last IDL commit was May 19.
Therefore the public docs do not answer whether that earlier Pump upgrade changed its interface.

## Limits

- The public endpoint is not archival; under-limit results suggest but do not prove completeness.
- Loader upgrades do not alone establish semantic changes.
- Official repository commit time is correlational and can lag deployment.
- Historical runtime probing still depends on archival transaction availability around each slot.

## Next

1. Pin and diff the PumpSwap IDL immediately before and after the July 15 docs commit.
2. Test historical transaction retrieval around selected Pump and PumpSwap upgrade slots before
   attempting a full boundary scan.
3. Re-run both inventories against an archival provider.
