# B16b — decomposing the creator-like positive median

**Exploratory and descriptive.** Not a profit measurement, and **not a recommendation to issue
tokens**. `executable=false`, `performance_status=not_evaluated`, `execution_status=never_executed`.
Burned/published artifacts only; no network, no live file, nothing under `research/b11a`.

**Artifact:** `research/b16b/creator_flow.json`. **Code:** `scripts/b16b_creator_flow_decomposition.py`.
**Guards:** 22 tests, mutation sweep 9/9 killed.

## The question

B16a reported a +0.242 SOL median fee-adjusted flow across 101 fully-exited `creator_like` positions
— the only cohort with a clearly positive median. This asks what that figure is made of.

## Answer 1: the dominant explanation is selection, not trading skill

| | |
|---|---|
| curves in the burned corpus | 1,136 |
| curves where a creator-like wallet appears as a **buyer** | **110 (9.7%)** |
| curves where it never does | **1,026 (90.3%)** |
| creator-like positions | 110 |
| of those, fully exited and therefore carrying a flow figure | **101** |
| inventory unresolved, excluded from every flow | 9 |

**The +0.242 median describes 101 positions drawn from the 9.7% of curves whose creator wallet traded
at all and then fully exited.** It is not a statement about creators, or about launches, or about
1,136 curves. Both conditions plausibly correlate with the trade having gone well — a wallet that
bought and is under water is likelier to still be holding, and holding puts it in the excluded 9 — so
the direction of the bias is probably favourable, and its size is unmeasured.

## Answer 2: it is NOT a launch-transaction buy

The obvious mechanism — the creator buying its own token in the create transaction, at the curve's
opening reserves, then selling higher — **does not occur here at all.**

| subset | positions | flow median |
|---|---|---|
| bought in the create transaction | **0** | – |
| did not | **101** | +0.2500 (+0.2420 after the documented fee) |

Excluding same-transaction launch activity changes nothing, because there was none to exclude. Entry
timing supports this: of the 110 creator-like positions, 68 entered **100+ slots** after the create,
30 entered 10–99 slots after, 5 entered 1–9 slots after, and 7 entered in the create *slot* but in a
**different transaction**. Creator-like wallets in this corpus are mostly late buyers of their own
curves, not launch-price insiders.

So the figure survives the test the brief asked for — and survives it trivially, which is itself the
finding. Whatever produces it is not opening-price access.

## Answer 3: the creator/create_user split cannot be made here

`creator` and `create_user` name the **same wallet on 1,120 of 1,136 curves**, and on all 110
creator-like positions the role is `both_fields_name_this_wallet`. There is no contrast to measure.
The code separates the roles and the tests drive all three cases; the corpus simply does not contain
the variation. Reported as a limit, not as a result.

## Answer 4: the fee channels are outside the flow, and are nearly empty anyway

The flow is a difference of bonding-curve reserve deltas, so creator fees, cashback and buyback are
absent from it by construction — they move lamports through vaults. Counting their presence:

| instruction | in corpus | touching a creator-like wallet |
|---|---|---|
| claim_cashback | 930 | 0 |
| claim_cashback_v2 | 14 | 0 |
| distribute_creator_fees_v2 | 59 | 8 |
| migrate_bonding_curve_creator | 38 | 0 |
| transfer_creator_fees_to_pump_v2 | 23 | 0 |
| create_pool / migrate_v2 | 16 / 16 | 0 |
| distribute_creator_fees | 15 | 3 |
| collect_creator_fee_v2 | 5 | 1 |
| collect_creator_fee | 2 | 2 |
| collect_coin_creator_fee | 1 | 0 |

Only **14 instructions in the entire corpus** touch a creator-like wallet across all fee channels.
**No amount is claimed** for any of them: an address appearing in an instruction is not proof it was
paid, and these were not decoded for value. So fee collection cannot explain the +0.242 — but neither
is it ruled out as a channel operating outside this corpus's window.

## Answer 5: token transfers are recorded but not decoded

I first wrote that transfers were invisible here. **That was an overclaim and checking caught it.**
The corpus stores instructions from **201 distinct programs**, including **74,305** SPL Token and
**208,474** Token-2022 instructions. What it does not do is decode them: only the Pump IDL was pinned,
so every non-Pump instruction carries a null `idl_name`, and **0** token-program instructions are
decoded.

The raw material for transfer analysis therefore exists; the decoding does not, and this audit did not
add it. The consequence is unchanged and important: **no flow figure here is bounded by wallet-level
inventory.** A position that looks closed may not be, and one that looks open may have been settled
elsewhere.

## What this is not

- **Not profit.** Complete wallet-level costs, inventory and transfers are not available, and without
  all three a flow is not a result. The figure excludes the cost of creating the token, its rent, and
  every execution cost.
- **Not ownership.** "Creator-like" means a wallet **equals a recorded field** on that curve. No
  clustering, funding-graph or heuristic linkage was attempted, and no claim is made that any two
  addresses share an owner.
- **Not a strategy recommendation.** This decomposes an observation. It does not endorse the
  behaviour it describes and says nothing about its legality, ethics or durability.

## What would be needed to answer the question properly

Stated so the gap is explicit rather than implied: decoding the token programs already present in the
corpus, to bound inventory and see transfers; per-wallet execution costs, which this corpus does not
record; the creation cost and rent per launch; and a denominator over all 1,136 curves rather than the
9.7% that self-selected into the sample. Until then the honest summary is that **a small, selected,
late-entering subset of creator-equal wallets shows a positive median flow, and the leading candidate
explanation is the selection itself.**
