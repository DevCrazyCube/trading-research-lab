# B16c — wallet inventory reconciled from preserved token evidence

**Exploratory and descriptive.** Bounds *inventory*; prices nothing and claims no profit.
`executable=false`, `performance_status=not_evaluated`, `execution_status=never_executed`.
Burned artifacts only; no network, no live file, nothing under `research/b11a`.

**Artifact:** `research/b16c/inventory.json`. **Code:** `scripts/b16c_wallet_inventory.py`.
**Guards:** 32 tests, mutation sweep 11/11 killed.

## Feasibility, proved before any reinterpretation

The evidence was already collected and never read: every stored `getTransaction` carries
`meta.preTokenBalances` and `meta.postTokenBalances`.

| | |
|---|---|
| raw transactions stored | 94,985 |
| carrying both balance arrays, with `err == null` | **94,985 (100%)** |
| balance entries missing `owner`, `mint`, `amount`, `decimals` or `accountIndex` | **0** |
| token-account observations extracted | 280,206 |
| distinct (wallet, mint) pairs | 37,982 |
| transactions refused as ambiguous | 0 |

**No SPL Token or Token-2022 instruction layout is decoded, and none needs to be.** The RPC already
states, per token account, its `owner`, `mint`, `programId` and exact integer `amount` with
`decimals`, before and after — and has already resolved lookup-table addresses. Decoding instruction
data would be a second, weaker derivation of what the primary source states directly, and would drag
a third-party layout into the chain of custody. Provenance is therefore the stored response itself.

## The method, and why absolute balances beat deltas

Summing deltas over collected transactions reproduces exactly B16a's blind spot. Reading the
**absolute post-balance** answers the question directly: a wallet whose last observed balance is zero
is flat at that moment, however it got there — transfers included.

The two together also **measure** the blind spot. Consecutive observations of one wallet-mint must
chain: the earlier `after` is the later `before`. Where they do not, a transaction this corpus never
collected moved that balance. **998 of 37,982 wallet-mint pairs (2.6%) show such a gap.** The coverage
limit is now a number rather than a caveat.

## Inventory, re-evaluated for every archetype

| archetype | positions | flat at last observation | still holding | no balance evidence | with a gap |
|---|---|---|---|---|---|
| delayed_entrant | 21,065 | 18,835 | 2,047 | 183 | 94 |
| unclassified_mid_window | 3,773 | 3,715 | 57 | 1 | 45 |
| repeat_early_entrant | 2,121 | 2,095 | 26 | 0 | 5 |
| incidental_trader | 925 | 840 | 85 | 0 | 12 |
| immediate_launch_sniper | 918 | 883 | 35 | 0 | 24 |
| **creator_like_participant** | **110** | **96** | **14** | 0 | 5 |
| migration_trader | 22 | 1 | 21 | 0 | 0 |

**The trade-derived test over-reported unresolved inventory.** The two methods disagree on 1,090
positions, and **1,076 of those are cases where B16a believed a wallet still held and the balance
shows it flat** — only 14 go the other way. B16a could only see a wallet's own buys and sells on one
curve; the balance evidence sees every collected transaction that touched the account.

For the 110 creator-like positions specifically: 96 flat, 14 still holding, none without evidence, 5
carrying a gap. B16a had said 101 exited / 9 unresolved.

## Does B16b's headline survive the better denominator?

Flow less the documented 95 bps, on the stricter denominator (balance flat **and** no gap):

| archetype | trade-derived n | median | balance-derived n | median |
|---|---|---|---|---|
| **creator_like_participant** | 101 | **+0.2420** | **93** | **+0.1943** |
| repeat_early_entrant | 2,095 | −0.0013 | 2,090 | −0.0013 |
| immediate_launch_sniper | 840 | −0.0081 | 859 | −0.0097 |
| delayed_entrant | 17,861 | −0.0020 | 18,755 | −0.0033 |
| incidental_trader | 819 | −0.0105 | 828 | −0.0120 |
| unclassified_mid_window | 3,690 | −0.0063 | 3,672 | −0.0066 |

**Yes, and it moderates.** The creator-like median falls from +0.242 to **+0.194** on a
better-founded denominator, and remains two orders of magnitude above every other cohort. Every other
archetype is unchanged to within a thousandth of a SOL. The qualitative conclusion of B16a and B16b
did not rest on the weaker holding test.

None of this changes the B16b verdict that the creator-like figure is dominated by **selection** —
only 110 of 1,136 curves (9.7%) have a creator-wallet buy at all, and that denominator is untouched
by this work.

## A defect this work found in itself

The first implementation grouped observations by `(owner, mint, accountIndex)` and produced an exact
inversion: 101 creator-like positions "still holding", 9 "flat" — the precise mirror of B16a. That
symmetry was too neat to be a finding, and checking one case by hand showed why: **`accountIndex` is
an index into one transaction's account keys, not a stable identifier for a token account.** The same
account appeared at index 4, then 2, then 3, so one account became three and their last values were
summed, inflating the balance and inverting the verdict. Grouping is now per `(owner, mint)` per
transaction; the index is used only for pairing pre against post *within* a transaction, which is the
one thing it is valid for. A mutant restoring the old grouping is killed.

## What is still refused, and what is still unknown

- **Owner changes within a transaction** are refused, not attributed. **Missing fields** are refused,
  not defaulted. **Failed transactions** are excluded. All are counted.
- **"Flat" means flat at the last collected observation**, not for all time. Anything after the
  corpus's last transaction for that account is unobserved.
- **Shared ownership is never inferred.** Two addresses holding one mint are two addresses; no
  clustering was attempted, and a test reads the AST to confirm none exists in the code.
- **Nothing here is profit.** This bounds inventory. Costs beyond the documented curve fee — creation
  cost, rent, base and priority fees, ATA rent — remain unrecorded in this corpus.
- **A wallet with a second token account untouched by a collected transaction** would have its
  holding understated; that shows up as a gap rather than silently, which is why gaps are reported
  per position.
