# Raydium Fee Key (transferable LP-fee rights) — feasibility RESULT

Origin: Codex, 2026-09-09 (`scripts/fee_rights_probe.py`, 14 tests; SDK pinned at commit 28411d09). Completed by Claude after
Codex's usage ran out. NO_TRADE; no purchase, no signing. Raw responses under `research/midcap/fee_rights_private/` (gitignored).

## The instrument
Raydium "Burn & Earn": a creator locks LP and receives a Fee Key NFT (`LockrWmn6K5twhz3y9w1dQERbmgSaRkfnTeTKbpofwE`);
its holder can collect the position's accrued trading fees. Keys are transferable and listed on Magic Eden
(`raydium_fee_key_cpmm`: 11-14 listings, floor 0.027 SOL; `raydium_fee_key_clmm`: 6 listings, floor 0.2 SOL).
Claimable fees per key are public: `https://dynamic-ipfs.raydium.io/lock/cpmm/position?id=<lock PDA>` returns
`positionInfo.unclaimedFee.usdValue`, `tvlPercentage`, and the pool's day/week/month `volumeFee`.
Lock PDA = find_program_address([b"locked_liquidity", nft_mint], lock program) — validated against a decoded lock tx.

## Test (Codex's framing): can a key be bought for less than the cash ALREADY claimable through it?
Every CPMM listing was priced against its own claimable fees (SOL/USD 103.22 at read time):

| ask (SOL) | ask $ | claimable $ | position share | pool fee/day $ | pool |
|---|---|---|---|---|---|
| 0.027 | 3 | 0.16 | 94% | 0 | WSOL/MKIN |
| 0.027 | 3 | 0.00 | 0.5% | 0 | WSOL/SDOGE |
| 0.050 | 5 | 0.00 | 100% | 0 | WSOL/TRC |
| 0.050 | 5 | 0.00 | 0.4% | 0 | UPONLY/WSOL |
| 0.165-0.390 | 17-40 | 0.00-0.01 | 1-19% | 0 | SDOGE, $SLAYR |
| 24-20,000 | 2.5k-2.06M | 0-1 | 54-100% | 0 | TOTO, DGLD, "50000", CMPST |

**Result: 0 of 11 listed keys have claimable fees above the ask; every listed key sits on a pool earning ~$0/day.**
Ask/claimable ratios run from 18x to >10^6. Sellers collect before listing (adverse selection, predicted in the audit),
and what is listed are rights to dead pools. The CLMM collection's keys could not be priced (lock program id not in the
pinned file); asks are 0.2-2 SOL on unknown pools and cannot change the conclusion.

## Population of fresh keys
The 60 most recent lock-program transactions contain 5 distinct keys and 3 collect instructions: three keys on one
$4k-TVL pool earning $0.03/day, one on a $9k pool with zero volume, one fee-info 500. The one high-flow key seen (USEDCAR,
97% of a pool earning ~$494/day, $393 claimable) is a creator's own key and is not listed.

## Verdict
Claimable-fee arbitrage: **dead, measured.** The remaining variant — bidding below present value on keys with durable
fee flow — is an OTC valuation business against informed holders on a population of a handful of keys per day; it is
not a bot and not testable without capital and counterparties. Not pursued.
