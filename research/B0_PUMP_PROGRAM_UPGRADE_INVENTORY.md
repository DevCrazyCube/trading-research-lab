# B0 — Pump Program Upgrade Inventory

Run: 2026-07-27, approximately 10:15–10:22 UTC. Author: Claude.

This is the project's **first measurement**. Everything preceding it in `DOCUMENTATION.md`,
`DECISIONS.md`, and `agent_discussion.md` was design reasoning.

## Method

Read-only JSON-RPC against the public endpoint `https://api.mainnet-beta.solana.com`,
commitment `finalized`. No keys, no signing, no transactions, no writes.

1. `getAccountInfo` on the Pump program address → confirm owner is the BPF upgradeable
   loader and decode the `Program` account layout (`u32` enum = 2, then the ProgramData pubkey).
2. `getAccountInfo` on the ProgramData address → decode `u32` enum = 3, `u64` last-deploy slot,
   `Option<Pubkey>` upgrade authority.
3. `getBlockTime` on the last-deploy slot.
4. `getSignaturesForAddress` on the ProgramData address, limit 1000 → candidate deploy/upgrade
   transaction history.

Script: `scripts/b0_inventory.py` (copied from the scratchpad run; re-runnable, read-only).

Follow-up classification: `scripts/b0_classify_transactions.py` fetched all 95 returned
transactions and decoded outer and inner BPF-upgradeable-loader instructions. The persisted
JSONL evidence is `research/b0_classification_2026-07-27.jsonl`.

## Verified results

| Field | Value |
|---|---|
| Program | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` |
| Owner | `BPFLoaderUpgradeab1e11111111111111111111111` |
| Executable | true |
| ProgramData account | `B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu` |
| ProgramData length | 10,485,760 bytes |
| **Last deploy slot** | **433,095,571** |
| **Last deploy time** | **2026-07-15 16:11:40 UTC** |
| **Upgrade authority** | **`7gZufwwAo17y5kg8FMyJy2phgpvv9RSdzWtdXiWHjFr8` (present — program is MUTABLE)** |
| Signatures returned | 95 |
| Distinct slots touched | 82 |
| Failed transactions among them | 5 |
| Oldest observed slot | 241,767,269 (2024-01-14 12:47:22 UTC) |
| Newest observed slot | 433,095,571 (2026-07-15 16:11:40 UTC) |

### Loader transaction classification

| Loader operation / class | Transactions |
|---|---:|
| Upgrade | 54 |
| DeployWithMaxDataLen | 1 |
| ExtendProgram | 2 |
| SetAuthority | 1 |
| SetAuthorityChecked | 1 |
| No loader instruction found | 36 |

All 54 decoded `Upgrade` transactions succeeded and occupy 54 distinct slots. Fifteen occurred
in 2026, from 2026-01-09 through 2026-07-15. The mean interval between those 15 events is
13.36 days; intervals are highly clustered and range from 0.82 to 50.95 days. This is an event
timeline, not evidence that each upgrade changed the interface or trading behaviour.

### Candidate upgrade events during 2026

18 distinct slots touched the ProgramData account between 2026-01-09 and 2026-07-15:

```
433095571  2026-07-15 16:11:40 UTC      421067069  2026-05-20 21:30:19 UTC
429562010  2026-06-29 00:51:27 UTC (F)  420801996  2026-05-19 16:04:38 UTC
422112651  2026-05-25 17:26:40 UTC      419618068  2026-05-14 04:51:27 UTC
421245305  2026-05-21 17:15:43 UTC      418217974  2026-05-07 16:32:38 UTC
416714655  2026-04-30 18:48:00 UTC      416251172  2026-04-28 16:00:49 UTC
414541007  2026-04-20 19:48:44 UTC      404296915  2026-03-05 03:44:23 UTC
402862753  2026-02-26 14:40:19 UTC      400887915  2026-02-17 14:31:31 UTC
399821352  2026-02-12 18:45:50 UTC      398010699  2026-02-04 13:25:04 UTC
398010653  2026-02-04 13:24:45 UTC      392381020  2026-01-09 16:10:57 UTC
```

`(F)` = transaction failed. Full listing in the run output.

## What this changes

**F1 — The program is mutable and actively changed. (verified fact)**
An upgrade authority is set, so the deployed bytecode can change at any time without notice.
This is not hypothetical: the most recent deploy was **2026-07-15, twelve days before this run**.

**F2 — "Current regime" has a hard, measured upper bound. (verified fact, with an open follow-up)**
`DOCUMENTATION.md` asks "which exact slot/date range offers enough current-regime history without
mixing incompatible fee and instruction regimes?" The answer is now bounded from above: if the
2026-07-15 deploy changed instruction layout, account layout, or economics, then current-regime
history is **twelve days old**, not months. Whether it actually changed anything material is the
immediate follow-up (see below). No amount of further architecture discussion would have
surfaced this; one RPC call did.

**F3 — Successful loader upgrades occurred roughly biweekly in 2026. (verified transaction classification)**
Fifteen successful transactions containing upgradeable-loader `Upgrade` instructions occurred
over 187 days in 2026: a mean inter-event interval of 13.36 days. This replaces the earlier
ProgramData-touch heuristic. It still does **not** establish how frequently bytecode semantics or
interfaces changed; that requires artifact/bytecode comparison across boundaries.

**F4 — The B0 gate is partially satisfied, not satisfied.**
A loader-event timeline and transaction classification now exist. Archival completeness and
behavioural/interface differences across upgrade boundaries remain unverified, so the events
cannot yet be treated as distinct trading regimes.

## Limitations — read before relying on any of the above

- **The public endpoint is not archival.** `getSignaturesForAddress` returned 95 results against
  a limit of 1000, and the oldest is 2024-01-14, which is plausibly the original deployment. That
  the result is under the cap *suggests* completeness, but suggestion is not proof: a
  non-archival node can silently return a truncated range. **This must be re-run against an
  archival provider before the timeline is treated as complete.**
- **A decoded loader event is not automatically a semantic regime boundary.** The classification
  proves which loader instruction executed, not whether bytecode, account layouts, events, fees,
  or instruction semantics materially changed.
- **PumpSwap is not inventoried.** Its program address has not been confirmed against a primary
  source in this session, and inventing one is forbidden by `AGENTS.md`.
- **Bytecode identity was not compared.** Two deploys can ship identical or trivially different
  code. Event count is an upper bound on *behaviour* changes, not a measure of them.
- Slot→time mapping via `getBlockTime` is the cluster's recorded block time, adequate for dating
  regimes but not a latency measurement.

## Immediate follow-ups

1. Re-run against an archival RPC to confirm the history is complete rather than truncated.
2. Compare deployed artifacts/bytecode and IDLs across upgrade boundaries, beginning with
   2026-07-15, and determine which events are semantic regime boundaries.
3. Determine whether the 2026-07-15 deploy changed instruction or account layout — this decides
   whether usable current-regime history is twelve days or several months, which in turn decides
   whether a bonding-curve dataset of meaningful size is available at all right now.
4. Confirm the PumpSwap program address from a primary source, then repeat B0 for it.
5. Add a standing monitor on the ProgramData account: given F1 and F3, an upgrade landing
   mid-research must be an alarm, not a discovery made weeks later.
