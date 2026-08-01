# Simulator result schema — v1.0.0

Produced by `scripts/b10a_simulator_kernel.py`. Read-only: consumers must treat every record as
immutable and must pin `schema_version`.

Status: **Phase 2, first bounded slice.** The deterministic arithmetic gate below is measured and
passing. The stochastic Phase 2 gate — landing, contention, failure and fill distributions against
forward observations — is **not** addressed by this kernel and is not claimed.

## The three refusals that define this kernel

1. **No invented execution parameter.** Priority fee, tip, landing probability, latency and
   slippage are unmeasured in this project. A cost policy missing any required field is refused.
   Absence is not zero — zero priority fee is the most optimistic assumption available, not a
   neutral one.
2. **No post-decision state in entry pricing.** `price_entry` takes exactly one curve state and has
   no parameter through which a later observation could reach it. The boundary is structural, and a
   test asserts entry flows are byte-identical whether the token later collapses or moons.
3. **No result is ever executable.** Every record carries `outcome_label: "SIMULATED"` and
   `calibration: "uncalibrated"`. No code path emits anything else.

## Inputs

| input | contents | rule |
| --- | --- | --- |
| `curve state` | `virtual_quote`, `virtual_token`, `real_quote`, `real_token`, `quote_mint`, `mayhem_mode`, `complete`, `slot` | decision-time canonical state only; any missing field is refused |
| `OrderSpec` | `side`, `quote_lamports` | explicit size; never inferred from an observation |
| `fee schedule` | `fee_bps`, `creator_fee_bps`, `cashback_fee_bps`, `buyback_fee_bps` | from decision-time config; no rate is hard-coded in the kernel |
| `CostPolicy` | `base_fee_lamports`, `priority_fee_lamports`, `tip_lamports`, `ata_rent_lamports`, `failed_attempts` | **all required**; absence is refused, never defaulted |

## Result record

```
schema_version   "1.0.0"
outcome_label    "SIMULATED"          — always
calibration      "uncalibrated"       — always; no scenario here is measured
status           priced | incomplete_scenario | exit_unavailable
evidence         caller-supplied provenance, echoed verbatim
entry            side, quote_lamports, tokens_out, curve_fees, execution_costs,
                 lamports_out_of_wallet, state_slot
exit             side, status, tokens_in, quote_lamports, curve_fees, execution_costs,
                 lamports_into_wallet, liquidity, state_slot
entry_slot       decision instant
exit_slot        strictly greater than entry_slot
net_lamports     exit proceeds minus entry outlay, or null when the exit is unavailable
fee_schedule     echoed
cost_policy      echoed
```

## Arithmetic

The kernel calls `b9i`'s functions directly rather than carrying a copy. A simulator with a private
formula drifts from the gate that validates it, and the drift is invisible until it matters.

| quantity | formula |
| --- | --- |
| exact-input buy | `(quote_in - 1) * vt // (vq + quote_in - 1)` |
| legacy exact-token buy | `tokens * vq // (vt - tokens) + 1` — **floor+1, not ceil** |
| sell | `tokens * vq // (vt + tokens)` |
| protocol / creator / cashback fee | `ceil(quote * bps / 10000)` |
| buyback fee | `floor(fee * bps / 10000)` — **floor**, the only one |

**The buyback fee is reported, never charged.** It is a split of the protocol fee, not an addition:
the pinned gross identity is `quote + fee + creator_fee + cashback` with no buyback term, so adding
it to the total would take half the protocol fee from the user twice. The field is named
`buyback_fee_reported_not_charged` so the distinction cannot be lost by a reader skimming keys.

## Cost contract

- **ATA rent is charged on entry and never refunded.** The reclaim is real but conditional on
  closing the account; crediting it would understate cost.
- **Failed attempts cost `base_fee + priority_fee` each**, stated by the caller.
- **Exit proceeds may be negative** when costs exceed proceeds. Reported, never clamped — clamping
  to zero would hide the case that matters most on a small position.

## Fail-closed conditions

| condition | outcome |
| --- | --- |
| quote mint is not native SOL | refused |
| Mayhem mode | refused |
| curve already complete at the decision instant | entry refused |
| curve complete at exit | `exit_unavailable`, liquidity `L3_structural_unavailable`, no invented mark, no assumed migration |
| entry would take more tokens than the **real** reserve holds | refused |
| exit would draw more quote than the **real** reserve holds | refused |
| order buys zero tokens at these reserves | refused, never rounded to zero |
| any curve-state field missing | refused |
| any cost-policy or fee field missing | refused |
| exit state at or before the decision instant | refused as leakage |

The size guard is against the **real** reserve, not the virtual one. The curve formula approaches
the virtual reserve asymptotically and never reaches it, so a virtual-reserve check looks like a
size guard and never fires however large the order.

## Validation gate — measured

```
python scripts/b10a_simulator_kernel.py research/b9d_transaction_bodies.sqlite --gate
```

Replays every eligible observed direct Pump trade at exact integer precision, in canonical order
(`slot, transaction_index, outer_index, inner_index`) — never database insertion order.

| component | exact |
| --- | --- |
| `net_quote` (legacy buy) | 31,132 / 31,132 |
| `quote_out` (sell) | 40,717 / 40,717 |
| `tokens_out` (exact-input buy) | 20,661 / 20,661 |
| **total** | **92,510 / 92,510, zero mismatches** |

743 observations are skipped as outside the frozen regime (non-SOL quote or Mayhem) and are counted
in `skipped_out_of_regime` so the denominator stays honest.

Observations are paired to their events by the coordinates the reserve evidence itself names, and
the pairing must resolve to exactly one instruction. An earlier version of this gate matched on the
outer index alone and reported a spurious 389,217,712-lamport mismatch on a bundled transaction —
the defect was in the pairing, not the venue.

## Not covered

- **Landing, contention, tips, latency, slippage.** Unmeasured; require forward observation. Any
  return computed from this kernel is **simulated, not executable**.
- **PumpSwap entry or exit.** Not an entry venue; a post-graduation exit path needs separate
  validation.
- **Multi-leg, partial or scaled exits.** One entry, one exit.
- **Reserve path between entry and exit.** The kernel prices two states; it does not model the path
  between them.

No profitability claim is made and nothing here is a trading recommendation.
