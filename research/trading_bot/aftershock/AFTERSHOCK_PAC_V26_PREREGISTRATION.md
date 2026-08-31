# AFTERSHOCK PAC V2.6 — right-tail probe with an all-cost risk budget

**Status:** PREREGISTERED PAPER-SCENARIO CHALLENGER — NOT A PROFIT CLAIM, NO WALLET, NO ORDERS.

**Decision (2026-08-31):** V2.5 remains active and immutable until its own 100-resolution gate. The
first 21 V2.5 resolutions are a burned design sample for V2.6. They may motivate this one change,
but no V2.5 row may enter V2.6 performance and no V2.6 threshold may be changed after activation.

## Burned design observation

At the frozen design snapshot, V2.5 had 21 terminal paper positions: seven winners, fourteen losses,
mean +8.98%, median -5.10%. One +318.13% outcome supplied more than the entire aggregate gain;
removing that one outcome produced a -6.48% mean. The immediately executable round-trip mark at
entry averaged approximately -3.01%; losing positions subsequently lost another 9.31 percentage
points on average. This observation is post-outcome and is not V2.6 evidence.

## Frozen hypothesis and the only strategy change

Pump launches are extremely right-tailed. V2.6 therefore leaves the complete V2.5 entry detector,
full-position sizing, 12% executable-quote trail, premise floor, graduation handling, PumpSwap
transition, and 12-minute horizon unchanged. It adds exactly one exit condition:

- At every causally refreshed, priceable full-position state, compute the exact settlement fraction
  using the same accounting as a confirmed full exit:
  `net curve exit - entry all-in - failed exit costs + ATA rent - ATA close gas`, divided by entry
  all-in.
- If that exact fraction is at or below **-8/100**, issue `EXIT_RISK_BUDGET` for the full token
  position. Equality exits. The order retains the inherited 10% minimum-output tolerance and lands
  only after the authenticated processed-inclusion p90. A landing gap is booked, never capped in
  hindsight.
- The -8% boundary is a design risk allowance: roughly the observed 3% round-trip toll plus five
  percentage points of adverse movement. It is not an estimated optimum and no alternative
  threshold is tested inside the V2.6 forward book.
- An unpriceable state cannot pretend to respect the cap; it follows the inherited bounded PumpSwap
  transition and may become a full loss only under that pre-existing rule.

## Frozen entry, sizing, and authority

- Entry is byte-identical V2.5 paid absorption: sell >= probe; recovery to pre-shock plus probe for
  one processed p90; at least three distinct buyers excluding seller; 6x reserve cover; two latency
  windows of token runway; one filled entry per mint per V2.6 ledger.
- Probe is fixed point-in-time USD 10 paper size. There is no scaling, wallet, signer, sender, or
  order submission.
- Executor calibration is inherited by exact anchored V2.5 artifact hash because the public RPC,
  send/sign/processed-land measurement path, snapshot decoder, and pricing kernel are unchanged.
  V2.6 receives a new post-seal activation watermark and begins reading the shared feed at EOF.

## Frozen verdict at 100 terminal positions

Continue research only if all are true:

1. Mean all-cost return is positive and normalized capital index exceeds 100.
2. Mean all-cost return remains positive after removing the single best outcome.
3. Unexitable full-loss rate is no worse than V2.5 at its corresponding frozen evaluation.
4. Ledger, activation, calibration, one-fill-per-mint, and causal landing audits are clean.

Failure of any item rejects V2.6. Passing does not authorize real money.
