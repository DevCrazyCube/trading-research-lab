# B9j — System program instruction ABI pin

Pinned 2026-08-01. Authorized as research browsing/download only (Codex handoff 44); no chain RPC
was used and no transaction was signed, submitted, or simulated.

## Why this exists

Transaction-level wallet-cost reconciliation cannot be done from balance vectors. Measured over
1,200 eligible transactions, attributing the fee payer's delta to `meta.fee`, protocol-side quote
flows, and zero-based account creation/close reconciles only 272 of them — 22.7%. The unattributed
movements are overwhelmingly System-program instructions: 374 of 400 sampled transactions carry
them, 2,014 in total. Attributing them requires decoding them, and decoding them requires an
interface this repository had not pinned.

## Pinned package

| field | value |
| --- | --- |
| package | `solana-system-interface` |
| version | `3.2.0` |
| published | `2026-04-07T18:43:18.249064Z` — before the observation window opens (slot 433,894,233) |
| yanked | `false` |
| crate SHA-256 | `55b54965bf0b76fa8e2b35376583efddd4d916618cfe595bf48c7d7b55a9e628` |
| program id | `11111111111111111111111111111111` |
| serialization | bincode; variant tag is a 4-byte little-endian u32, `String` carries an 8-byte little-endian length prefix |

Vendored ABI source, so the pin survives without network access:

| file | SHA-256 |
| --- | --- |
| `research/solana_system_interface_3.2.0_instruction.rs` | `1126faa2ab8c7a1ecc73dca70de34713ad25bd0e090e2bb8595fb3d767801876` |

### How the checksum was established

Three independent confirmations, because a pin nobody verified is decoration:

1. `https://crates.io/api/v1/crates/solana-system-interface/3.2.0` → `cksum`
2. `https://index.crates.io/so/la/solana-system-interface` (sparse index) → `cksum` for `vers` 3.2.0
3. The crate was downloaded from `https://static.crates.io/crates/solana-system-interface/3.2.0/download`
   and hashed locally; its SHA-256 equals the two above.

**Correction to the handoff that commissioned this.** Handoff 44 stated the registry checksum as
`5b82ac4a3c2ca9c3460964f020e1402edd5753411d7737aa39c3714ad1b5420e`. That value does not match the
registry from either endpoint, nor the downloaded bytes. The verified value is the one recorded
above. Pinning the stated value would have produced a pin that no future verification could
satisfy — the failure mode a pin exists to prevent.

**Not recorded, because it could not be verified.** Handoff 44 also stated a "frozen ABI digest"
of `CBvp4X1gf36kwDqnprAa6MpKckptiAHfXSxFRHFnNRVw`. That string is base58 of pubkey shape and does
not correspond to any digest published by crates.io, docs.rs, or the crate source. It is omitted
rather than recorded as fact. If it denotes something real, its source needs to be named before it
belongs in a pin.

## The ABI, as pinned

Variant tags are the enum's declaration order, read from the vendored source at the line numbers
shown. Confirmed identical on `docs.rs` for the same version.

| tag | variant | payload | source line |
| ---: | --- | --- | ---: |
| 0 | `CreateAccount` | `lamports: u64`, `space: u64`, `owner: Address` | 99 |
| 1 | `Assign` | `owner: Address` | 114 |
| 2 | `Transfer` | `lamports: u64` | 124 |
| 3 | `CreateAccountWithSeed` | `base: Address`, `seed: String`, `lamports: u64`, `space: u64`, `owner: Address` | 134 |
| 4 | `AdvanceNonceAccount` | — | 157 |
| 5 | `WithdrawNonceAccount` | `u64` | 170 |
| 6 | `InitializeNonceAccount` | `Address` | 184 |
| 7 | `AuthorizeNonceAccount` | `Address` | 193 |
| 8 | `Allocate` | `space: u64` | 199 |
| 9 | `AllocateWithSeed` | `base: Address`, `seed: String`, `space: u64`, `owner: Address` | 210 |
| 10 | `AssignWithSeed` | `base: Address`, `seed: String`, `owner: Address` | 229 |
| 11 | `TransferWithSeed` | `lamports: u64`, `from_seed: String`, `from_owner: Address` | 246 |
| 12 | `UpgradeNonceAccount` | — | 262 |
| 13 | `CreateAccountAllowPrefund` | `lamports: u64`, `space: u64`, `owner: Address` | 290 |

## Independent corroboration from the frozen artifact

The pin is not taken on the source's word alone. Every System instruction observed in a sample of
2,000 eligible transactions has a data length that the declared layout predicts exactly:

| tag | variant | observed lengths | predicted | count |
| ---: | --- | --- | --- | ---: |
| 0 | `CreateAccount` | 52 | 4 + 8 + 8 + 32 | 1,124 |
| 1 | `Assign` | 36 | 4 + 32 | 29 |
| 2 | `Transfer` | 12 | 4 + 8 | 7,312 |
| 3 | `CreateAccountWithSeed` | 95, 98, 100, 104, 105, 108, 109, 110, 119, 124 | 92 + seed length | 50 |
| 4 | `AdvanceNonceAccount` | 4 | 4 | 188 |
| 8 | `Allocate` | 12 | 4 + 8 | 29 |

Variant 3's lengths are exactly `92 + seed_length` for seeds of 3, 6, 8, 12, 13, 16, 17, 18, 27 and
32 bytes, which is what the bincode `String` encoding requires and is not what a 4-byte length
prefix would give. Two independent routes — the pinned declaration and the preserved bytes — agree.

Six of fourteen variants occur. The other eight are pinned but unobserved; a decoder must still
refuse them explicitly rather than treat absence as impossibility.

## Open questions

- Whether variant coverage over the *entire* population matches this 2,000-transaction sample.
  Sampling has disagreed with the population four times in this work already, so this is measured
  before any wallet-cost gate is built, not assumed.
- Whether `Address` in this version is byte-identical to a 32-byte pubkey in every variant. The
  layout table assumes it is; the vendored source is the place to settle it.
