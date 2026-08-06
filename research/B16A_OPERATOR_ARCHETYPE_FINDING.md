# B16a — operator archetypes in the burned corpus

**Exploratory and descriptive. Hypothesis-generating, not a preregistered estimand.** No figure here
is a performance result, a profitability claim or a recommendation. `executable=false`,
`performance_status=not_evaluated`, `execution_status=never_executed`.

**Sources:** the burned B8b/B9d corpus (1,136 curves created in slots 433,894,233–434,097,833, traded
onward through the observation span), B10b's observed paths and B10c's t0 identities. Nothing under
`research/b11a` was read, no network call was made, and the live B11 run was untouched throughout.

**Artifact:** `research/b16a/archetypes.json`. **Code:** `scripts/b16a_operator_archetypes.py`.
**Guards:** `tests/test_b16a_operator_archetypes.py`, 30 tests, mutation sweep 10/10 killed.

## First question: can this evidence distinguish the archetypes at all?

**Yes, for five of the six, and the sixth is barely populated.** The trader wallet is recoverable as
the `user` account of each `buy`/`sell` instruction. That is a positional read, and the stored
account list is *longer* than the IDL declares (18 against 16 for `buy`), so the position was
validated rather than assumed: re-deriving the wallet for 400 curves whose `t0_user` B10c obtained
independently — by decoding the event payload, a different route — gave **400 agreements and zero
disagreements**. The audit refuses outright on any disagreement.

Coverage: **91,466 usable trades → 28,934 (wallet, curve) positions across 15,272 wallets.** 2,630
trades were excluded rather than interpreted — 1,232 in transactions carrying more than one trade
instruction (no evidence pairs a wallet to a reserve delta), 920 with duplicate reserve observations,
476 with none, and 2 whose direction contradicted their reserve delta.

## What the cohorts look like

Entry delay is in slots from the curve's create. Size is the median quote put in. "Sold" is the share
of positions with any observed sell; "unresolved" is the share still holding at the end of the window.

| archetype | positions | wallets | curves | entry med | size med (SOL) | sold | unresolved | exit med |
|---|---|---|---|---|---|---|---|---|
| delayed_entrant | 21,065 | 13,309 | 557 | 400 | 0.196 | 88% | 15% | 190 |
| unclassified_mid_window | 3,773 | 1,450 | 418 | 13 | 0.444 | 99% | 2% | 34 |
| repeat_early_entrant | 2,121 | **126** | 500 | 2 | 0.122 | 99% | 1% | 16 |
| incidental_trader | 925 | 925 | 214 | 14 | 0.802 | 93% | 11% | 71 |
| immediate_launch_sniper | 918 | 601 | 340 | **0** | **1.185** | 96% | 8% | 36 |
| creator_like_participant | 110 | 105 | 110 | 180 | 0.099 | 93% | 8% | 867 |
| migration_trader | 22 | 22 | 7 | 754 | 1.467 | **0%** | **100%** | – |

Rules are applied in a fixed order (creator-like → migration → repeat → immediate → delayed →
incidental), because the categories overlap in reality and the more specific observation should win.
Thresholds are round numbers chosen for legibility and none was moved after seeing a result.

## The result that matters

Observed quote flow per fully-exited position, in SOL. **This is not profit** — it covers one curve
inside one window, before costs this corpus does not record, and a wallet may have moved tokens out
where nothing here would see it. The right-hand columns subtract 95 bps on each leg, the headline
rate B15Q decoded from all 4,096 of its launch transactions; that rate is documented in an *adjacent*
population and is applied here only as a labelled sensitivity, and it still omits execution costs
entirely.

| archetype | n | flow median | less fee: median | less fee: p75 | less fee: p90 |
|---|---|---|---|---|---|
| delayed_entrant | 17,861 | −0.0005 | −0.0020 | +0.0015 | +0.1105 |
| unclassified_mid_window | 3,690 | −0.0010 | −0.0063 | +0.0119 | +0.1661 |
| repeat_early_entrant | 2,095 | −0.0000 | −0.0013 | +0.0096 | +0.0909 |
| incidental_trader | 819 | −0.0058 | −0.0105 | +0.0668 | +0.4929 |
| immediate_launch_sniper | 840 | −0.0000 | −0.0081 | +0.1792 | +1.4124 |
| **creator_like_participant** | 101 | **+0.2500** | **+0.2420** | **+1.4901** | **+5.5482** |
| migration_trader | 0 | – | – | – | – |

**Every trading cohort sits at or just below zero at the median, and the only cohort with a clearly
positive median is the one that created the launch.** The creator-like median is +0.24 SOL after the
documented fee — two orders of magnitude above every other cohort — on 101 fully-exited positions.

The 126 wallets of `repeat_early_entrant` are the closest thing here to a systematic operation: they
enter early (median 2 slots), small (median 0.12 SOL), across many curves (2,121 positions on 500
curves), they almost always sell (99%) and they exit fast (median 16 slots). Their median flow is
**−0.0013 SOL after the documented fee**, with p25 −0.014 and p75 +0.010. That is a distribution
centred on zero, not an edge.

## Concentration

15,272 wallets hold 28,934 positions. **10,090 wallets (66%) touched exactly one curve.** The busiest
1% of wallets (152) hold 3,944 positions (13.6%); the top 10% (1,527) hold 10,808 (37.4%). The median
wallet appears on one curve; the maximum is 99.

## What this says about strategy

The audit was asked whether successful-looking operators suggest a materially different hypothesis.
On this evidence:

1. **It does not support a "snipe faster or bigger" hypothesis.** Immediate snipers exist in numbers
   (601 wallets) and trade at a median 1.19 SOL — roughly twelve times the 0.1 SOL configuration B15Q
   tested — yet their median flow is zero before fees and negative after the documented one. Their
   value is in a right tail (p90 +1.41 SOL), which is a lottery shape, not an edge, and B15M's
   capacity result says a larger position faces *worse* exit liquidity, not better.
2. **It weakly supports a materially different hypothesis, and it is not a trading one.** The only
   cohort with a positive median is the creator-like one. That is the party issuing the launch, not
   the party racing into it. This corpus cannot tell us *why* — and deliberately does not try — but it
   locates whatever edge is observable here on the issuance side of the transaction.
3. **It corroborates B15Q rather than contradicting it.** B15Q found the tested 0.1 SOL round trip
   negative at the median in all eighteen groups. Here, real wallets doing roughly that thing, at
   their own sizes and their own timing, also sit at or below zero at the median before costs.
   Two different methods on two different populations agree.

## What is NOT measurable here, stated plainly

- **Profitability.** Never computed. A position's observed flow is one curve in one window, before
  curve fees and execution costs this corpus does not record.
- **Token transfers.** Invisible: only Pump program instructions were collected, so a wallet that
  sent tokens elsewhere is indistinguishable from one still holding.
- **Identity ownership.** Never inferred. "Creator-like" means a wallet *equals a recorded field* on
  that curve, not that two wallets are one operator, and no clustering was attempted.
- **Wallet history outside the window.** A wallet's first appearance here is not its first trade and
  its last is not its last.
- **Per-wallet executable cost and capacity.** The per-launch fee basis points are not in this corpus
  — exactly the gap B15P existed to fill for a different population. B15Q's capacity and cost figures
  describe its own 5,000-launch population and are not transferable to these curves.
- **Advertised bot features.** Out of scope by construction: only observed on-chain behaviour is
  measured here, and no claim is made about what any tool advertises.

## Caveats on the cohorts themselves

- `migration_trader` has 22 positions on 7 curves and **none** fully exited, so no flow figure exists
  for it and none is offered.
- `creator_like_participant`'s positive median rests on **101 fully-exited positions** — small, and it
  should be read as a direction to investigate rather than a measured quantity.
- The delayed cohort's median entry of 400 slots reflects an observation span of ~1.64M slots after
  each create; "delayed" here spans everything from minutes to days and is not one behaviour.
