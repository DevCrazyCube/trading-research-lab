# B9l — SPL Token instruction ABI pin

Pinned 2026-08-01. Research browsing and download only; no chain RPC, no transaction signed,
submitted or simulated.

## Why this exists

Wallet-cost reconciliation attributed 50.29% of transactions exactly, and the unattributed half was
dominated by a single residual value: **-2,039,280 lamports, appearing 3,213 times**, which is
exactly SPL token-account rent flowing *back* to the fee payer. `CloseAccount` is executed by the
Token program on an account it owns, so no System instruction records it, and no balance-vector
rule can attribute it.

## Pinned package

| field | value |
| --- | --- |
| package | `spl-token-interface` |
| version | `2.0.0` |
| published | `2025-08-08T17:07:46.761271Z` — before the observation window |
| yanked | `false` |
| crate SHA-256 | `8c564ac05a7c8d8b12e988a37d82695b5ba4db376d07ea98bc4882c81f96c7f3` |
| program ids | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA`, `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` |
| discriminator | single `u8` — **unlike** the System program's 4-byte little-endian `u32` |

Vendored ABI source, so the pin survives without network access:

| file | SHA-256 |
| --- | --- |
| `research/spl_token_interface_2.0.0_instruction.rs` | `7f6f247b549e11d07c83059bad918bb2d0a78824867f961a10b239a9880a1a15` |

### Why 2.0.0 and not 3.0.0

`spl-token` 9.0.0 — the newest release, published 2025-10-28 — is a thin re-export shell whose
`Cargo.toml` declares `spl-token-interface = "2.0"`. Version 3.0.0 exists and was published
2026-05-20, also before the window.

**Both were downloaded and diffed.** Their `instruction.rs` files differ only in doc comments, one
`#[repr(C)]` → `#[repr(C, u8)]` attribute, and wording of `FreezeAccount`/`ThawAccount`
documentation. **No variant was added, removed or reordered, and no discriminator changed.** So the
choice does not affect decoding; 2.0.0 is pinned because it is the version the released `spl-token`
depends on, and the difference is recorded here so nobody has to re-derive it.

Checksums for both were confirmed against the sparse index and against the downloaded bytes:
2.0.0 `8c564ac0…`, 3.0.0 `7143c4e6…`.

## The ABI, as pinned

Declaration order is the wire discriminator. Confirmed twice: from the enum declaration, and from
the crate's own unpack table, which maps `9 => Self::CloseAccount` explicitly.

| tag | variant | | tag | variant |
| ---: | --- | --- | ---: | --- |
| 0 | `InitializeMint` | | 13 | `ApproveChecked` |
| 1 | `InitializeAccount` | | 14 | `MintToChecked` |
| 2 | `InitializeMultisig` | | 15 | `BurnChecked` |
| 3 | `Transfer` | | 16 | `InitializeAccount2` |
| 4 | `Approve` | | 17 | `SyncNative` |
| 5 | `Revoke` | | 18 | `InitializeAccount3` |
| 6 | `SetAuthority` | | 19 | `InitializeMultisig2` |
| 7 | `MintTo` | | 20 | `InitializeMint2` |
| 8 | `Burn` | | 21 | `GetAccountDataSize` |
| **9** | **`CloseAccount`** | | 22 | `InitializeImmutableOwner` |
| 10 | `FreezeAccount` | | 23 | `AmountToUiAmount` |
| 11 | `ThawAccount` | | 24 | `UiAmountToAmount` |
| 12 | `TransferChecked` | | | |

**`CloseAccount` is the only pinned variant that moves lamports.** Its documented accounts are
`0` = the account being closed, `1` = the destination that receives its lamports, `2` = the owner.
It transfers the account's **entire balance**, so the amount is not in the instruction data.

## Independent corroboration from the frozen artifact

Measured over 8,000 transactions, the observed discriminators map onto the pinned names coherently,
and one pairing confirms the mapping without reference to the source at all: **variants 21 and 22
occur in exactly equal counts** — 2,614/2,614 on Token-2022 and 892/892 on SPL Token — which is
`GetAccountDataSize` followed by `InitializeImmutableOwner`, the associated-token-account creation
sequence. A wrong table would not produce that equality.

Observed: `TransferChecked` (most common), `InitializeAccount3`, `GetAccountDataSize`,
`InitializeImmutableOwner`, `CloseAccount`, `Transfer`, `SyncNative`, `SetAuthority`.

## Token-2022 extension ABI (added 2026-08-01)

| field | value |
| --- | --- |
| package | `spl-token-2022` |
| version | `11.0.0` |
| published | `2026-05-08T17:18:29.419225Z` — before the observation window |
| crate SHA-256 | `2f0e045d23300c8c9f57e52fa7a1103a20a707cc02080db929c2ff09044aa06a` |
| vendored | `research/spl_token_2022_11.0.0_pod_instruction.rs`, SHA-256 `7b546580a90ab8d1f52143c21da931d26f8b68c7d2050b4eaf7307fc9c49c7e5` |

Token-2022 shares tags 0..24 with SPL Token and adds extensions 25..44:
`InitializeMintCloseAuthority`, `TransferFeeExtension`, `ConfidentialTransferExtension`,
`DefaultAccountStateExtension`, `Reallocate`, `MemoTransferExtension`, `CreateNativeMint`,
`InitializeNonTransferableMint`, `InterestBearingMintExtension`, `CpiGuardExtension`,
`InitializePermanentDelegate`, `TransferHookExtension`, `ConfidentialTransferFeeExtension`,
**`WithdrawExcessLamports` (38)**, `MetadataPointerExtension` (39), `GroupPointerExtension`,
`GroupMemberPointerExtension`, `ConfidentialMintBurnExtension`, `ScaledUiAmountExtension`,
`PausableExtension`.

### Lamport semantics, established from source rather than assumed

- **`WithdrawExcessLamports` (38) DOES move lamports.** `processor.rs` mutates both
  `source_account_info.lamports` and `destination_account_info.lamports`. It does **not occur** in
  the frozen artifact. Its amount is the balance above rent exemption and is not in the instruction
  data, so the decoder **raises** if one is ever seen rather than attributing zero.
- **The observed extensions do not move lamports.** `extension/token_metadata/processor.rs` and
  `extension/metadata_pointer/processor.rs` contain **zero** occurrences of `lamports`. That is the
  evidence; they are recorded as decoded-and-non-moving rather than skipped.

### Instructions routed by 8-byte interface discriminator

Two observed instructions are not enum tags at all. Token-2022 dispatches them on an 8-byte SPL
interface discriminator whose leading byte falls outside 0..44:

| discriminator | instruction | how identified |
| --- | --- | --- |
| `d7e4a6e45464567b` | `TokenMetadataUpdateAuthority` | reproduced locally as `sha256("spl_token_metadata_interface:update_the_authority")[:8]` |
| `d2e11ea258b84d8d` | `TokenMetadataInitialize` | from its own payload: u32-prefixed name, symbol and URI in order — observed as `"sol has nuggies"` / `"nuggies"` / an https URI |

The first was confirmed by computing the hash locally, which is what established that the scheme is
`sha256(namespace:name)[:8]` and not an enum tag.

## Still not covered

**SPL Token tag 45.** The one remaining undecodable instruction class. Always 10 bytes, shape
`2d 01 <u64 little-endian>`, with the u64 varying between occurrences (100,000,000 and others). It
is on the CLASSIC Token program, not Token-2022, and 45 is outside that program's pinned 0..24
range. It is refused rather than assumed inert, and accounts for the residual 1.74% of transactions
categorised `undecodable_instruction`.

Identifying it needs a source that documents this discriminator on `Tokenkeg…`; nothing in
`spl-token-interface` 2.0.0 or `spl-token-2022` 11.0.0 defines it.

## What these pins do NOT cover

- **SPL Token tag 45**, described above: refused, 1.74% of transactions.
- **Token-2022 extension payloads.** Tags 25..44 are identified and their lamport semantics
  established, but their argument bodies are not decoded. Nothing in wallet-cost accounting needs
  them, and decoding fields nobody reads is surface area that drifts silently.
- **Proof that the deployed programs were built from these exact crate revisions.** The crates
  describe the interface; they are not the binary. The corroboration above — equal 21/22 counts,
  the locally reproduced metadata discriminator, and the payload structure — is what ties the pins
  to the observed bytes.

## Open questions

- Whether any Token-2022 extension instruction moves lamports. Unknown, and deliberately not
  assumed either way.
- Whether the deployed on-chain programs were built from these exact crate revisions. The crate
  describes the interface; it is not proof of the deployed binary. The corroboration above is what
  ties the pin to the observed bytes.
