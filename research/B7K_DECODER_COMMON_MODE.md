# B7k — Decoder common-mode validation

**Preregistration:** `research/B7K_DECODER_COMMON_MODE_PREREGISTRATION.md`, frozen before any
result was computed, SHA-256 `05704fc910b680c3136187b9326901faab8eae0283e2121181d0f36644334a07`
**Artifact:** `research/b7j_positive_control_435564885_435565324.sqlite`, SHA-256
`4ca3a1c93770559d7a97d99afe0b30599b42ee077a471e909684e4ecc2c1373b`
**Pinned IDL:** `idl_sha256 b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49`
**Network cost:** zero. No RPC call. Offline against already-persisted artifacts.
**Raw output:** `research/b7k_decoder_common_mode.json`

## What this addresses

The limitation recorded in Seq 54 and carried unresolved through B7h, B7i and B7j: both discovery
paths share one decoder and one pinned IDL, so a wrong field layout is invisible to both and still
reports exact agreement. Every recall result in this project was conditional on a decoder nothing
had tested.

B7k compares decoded **values** against evidence the validator produced — resolved account keys,
`blockTime`, and payload length — none of which derive from the IDL.

## Result

| Arm | n | C1 membership | C2 timestamp | C3 exact consumption | Unresolvable | Verdict |
|---|---|---|---|---|---|---|
| Graduation (`CompleteEvent`, `CompletePumpAmmMigrationEvent`) | 4 | 4/4 | 4/4 | 4/4 | 0 | **PASS** |
| `TradeEvent` | 8,075 | 8,075/8,075 | 8,075/8,075 | 8,075/8,075 | 0 | **PASS** |

Zero failures on any load-bearing check. The `TradeEvent` arm spans **7,957 distinct transactions**,
which is the effective independent-sample count for C2 (a timestamp shares one witness across
events in the same transaction).

**The graduation arm is n = 4.** It is stated with the verdict everywhere, per the freeze. Four
events cannot support a statistical claim and this report does not make one. The `TradeEvent` arm
carries the weight.

## What the instrument had to survive first

The freeze required the scanner to be shown capable of failing before being pointed at real data.
17 unit tests run against synthetic payloads with layouts known by construction, including:

- a **one-byte offset shift** after the discriminator, which must not pass every check — the exact
  common-mode error class this task exists to detect;
- wrong timestamp, absent pubkey, and trailing-byte fixtures, each failing its specific check;
- an assertion that B7k exercises **the shared decoder itself** (`b7d.read_struct`) rather than a
  private copy, so it cannot accidentally validate a different code path than the one in use.

77 tests pass repo-wide.

## Instrument defect found and fixed at first contact with real data

The first run scored **all four** graduation events `UNRESOLVABLE`. That was a defect in B7k, not a
property of the data. Under `jsonParsed` encoding the RPC resolves address-table entries *into*
`accountKeys` tagged `source: "lookupTable"` (11 of 29 keys on the inspected transaction), and
`meta.loadedAddresses` is absent **because that resolution already happened**. The original guard
read that absence as failure.

The resolvability predicate was corrected and a regression test pins the real payload shape, plus a
second test asserting the guard still fires when a lookup table genuinely has no resolved addresses
— so the fix cannot degrade into a guard that never fires.

**Disclosure:** this change was made *after* seeing data. It touches only how a transaction's
account-key set is resolved. **The frozen checks, the verdict rule and the scope prohibitions were
not modified**, and the change can only move events from `UNRESOLVABLE` into being *tested* — it
cannot turn a failing check into a passing one.

## C4 — the preregistered prediction that turned out to be wrong

C4 was frozen as **reported, not load-bearing**, and predicted `quote_mint` would be identical
across all events in the window. **It is not.** The two graduating tokens carry different quote
mints:

| Mint | `quote_mint` | `sol_amount` | `mint_amount` | `pool_migration_fee` |
|---|---|---|---|---|
| `4R2Sxa8j…pump` | `11111111111111111111111111111111` | 84,990,359,274 | 206,900,000,000,000 | 15,000,001 |
| `5iHCTc3Q…pump` | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (USDC) | 9,816,363 | 206,900,000,000,000 | 15,000,001 |

**The B7j positive-control window contains a non-SOL-quoted graduation.** Nobody noticed this
through B7j's design, freeze, execution and audit. It does not disturb B7j's PASS — that measured
discovery recall, and both events were found on both paths — but it does mean the B7j fixture pair
spans **two quote regimes**, which was never recorded.

Two consequences worth carrying forward:

1. **The field named `sol_amount` does not necessarily hold SOL.** For the USDC-quoted migration it
   differs from the SOL-quoted one by roughly four orders of magnitude, consistent with being
   denominated in the quote mint rather than in lamports. **This is an inference from two
   observations and is explicitly not established here.** Anything that reads `sol_amount` without
   branching on `quote_mint` is a live trap. PLAN.md already lists USDC-paired `quote_*` validation
   as an open task; this is a concrete instance.
2. **`11111111111111111111111111111111` appears to be a default/sentinel** for the native-SOL case
   rather than a real mint account. Also not established here.

That C4 was frozen as non-load-bearing *in advance* is why this is reportable as a finding rather
than as a run failure. Had it been frozen as load-bearing, a correct decode would have been scored
FAIL for a reason unrelated to decoding.

## Post-hoc observation, not a frozen check

`mint_amount` (206,900,000,000,000) and `pool_migration_fee` (15,000,001) are **byte-identical
across both migrations**, in different transactions, for different tokens, under different quote
regimes. Protocol constants landing on exactly equal values through independent decodes is further
corroboration that field assignment is correct. **Labelled post-hoc**: it was not preregistered and
carries less weight than C1–C3.

## What this does and does not establish

**Established.** For the two frozen graduation event types and for `TradeEvent`, within this
439-slot window, the shared decoder's field assignment is consistent with independent
validator-produced evidence. A gross layout error — wrong offset, wrong type width, wrong field
order — is ruled out for the checked fields. The recall results in B7h and B7j no longer rest on a
wholly untested decoder.

**Not established, and stated plainly:**

1. **C1 is membership, not identity.** It proves a decoded pubkey is one of the ~29 accounts the
   transaction touched, not that it is the *right* one. **Two transposed pubkey fields would still
   pass**, and a unit test asserts this residual weakness so it cannot silently change.
2. **A self-consistent but wrong IDL is undetectable offline.** If the published IDL misnames
   fields whose types and positions align, nothing here catches it.
3. **Fields with no independent witness are unvalidated**, not passed: `sol_amount`, `mint_amount`,
   `pool_migration_fee`, `quote_mint`, and the `TradeEvent` reserve fields. C5 economic
   reconciliation was frozen as exploratory and is **not** claimed.
4. **One window, one regime.** No cross-regime generalisation.
5. **No recall, prevalence, performance, or cohort inference.** This tests decoding only.

## Suggested next work

- **Resolve C1's membership-vs-identity gap** by checking decoded pubkeys against their *expected
  account positions* in the instruction's account list per the IDL, which would catch transposition.
- **Establish the `sol_amount` / `quote_mint` relationship properly**, since the two-observation
  pattern above is suggestive and untested. This overlaps PLAN.md's USDC-paired validation task.
- **Record the quote-regime split of the B7j fixtures** wherever B7j's scope is described.
