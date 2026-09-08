# T48 tranche 6 — DATA-PATH AUDIT: MEME ARENA (all three arms)

**Date:** 2026-09-05 03:00 CEST (01:01 UTC) · CHUNK B tick · shell canary PASSED
**Instrument:** MEME ARENA — `VIRALITY_ARRIVAL_V2_2`, `BUNDLE_MOMENTUM_V2`, `MIGRATION_ACCEPTANCE_V1`
**Status:** **FAULT — the arena has been input-dead for ~56 hours.** This is the last of the six
T48 instruments, so the data-path audit is now complete.

---

## VERDICT IN ONE LINE

The MEME ARENA has collected **nothing since 2026-09-02T17:09Z**. Its upstream tape writer died on a
**Helius account-level quota exhaustion** (`-32429 max usage reached`), the arena watchdog that was
supposed to respawn it is **itself dead**, and nothing in the programme noticed — `chain_ok` stayed
true, the dashboard stayed up, and the standing claim "ALL 3 ARMS LIVE + COLLECTING" stayed on the
books for two and a half days while the arms sat starved.

---

## (a) RECENCY — **FAIL**

Measured at 2026-09-05T01:01Z:

| artefact | age | meaning |
|---|---|---|
| `research/data/memebot_cache/pumpportal_trades_v2.jsonl` (the tape all arms read) | **56.3h** | feed writer dead |
| `pumpportal_newtokens.jsonl` | **56.3h** | feed writer dead |
| `MIGRATION_ACCEPTANCE_V1/ledger.jsonl` | **56.3h** | last decision |
| `BUNDLE_MOMENTUM_V2/ledger.jsonl` | **41.9h** | drained its backlog ~14h, then stopped |
| `VIRALITY_ARRIVAL_V2_2/ledger.jsonl` | **59.3h** | stalled ~3h BEFORE the tape died (separate stall) |
| `bundle_v2.log`, `migration.log`, `runtime.log` | **0.0h** | processes alive, spinning, logging the same error |

The last tape record is `sequence 471400`, `received_unix_nanos 1788367267…` = 2026-09-02T17:01Z.

## (b) REPRESENTATION — **FAIL (zero, not partial)**

Every declared source is absent from the window the consumers read, not merely under-represented.
`ws_data.py:45` makes `pumpportal_trades_v2.jsonl` the single tape for all arms; per the standing
one-connection-per-key rule, the listener is the SOLE writer, so when it dies every arm reads a frozen
file. Both live arms log the same frozen error string on every cycle:

```
{"instrument": "BUNDLE_MOMENTUM_V2",     "error": "realtime trade stream DISCONNECTED: ..."}
{"instrument": "MIGRATION_ACCEPTANCE_V1","error": "realtime trade stream DISCONNECTED: ..."}
```

## (c) ATTRIBUTION — **NOT REACHABLE, and therefore NOT CLEARED**

The audit's attribution question (is each row's `mint` read from the row's own content, or inherited
from the keyed per-mint subscription that fetched it?) **could not be tested**, because no rows have
arrived in 56 hours. Recorded as **UNTESTED**, explicitly not as a clean bill. It must be re-run on
live rows whenever the feed is restored.

---

## ROOT CAUSE (verified, not inferred)

1. `research/data/arena/listener.log` ends in a tight reconnect loop at **2026-09-02T17:08–17:09Z**:
   `WebSocketBadStatusException('Handshake status 429 Too Many Requests … {"code":-32429,"message":"max usage reached"}')`.
2. The listener process is **gone** — `ps` shows only `runtime`, `bundle_v2_runtime`,
   `migration_acceptance_runtime`, `dashboard.server`. There is no `meme-arena-listener` tmux session.
3. **The arena watchdog is dead too.** `arena_watchdog.sh` is not running (the only watchdogs alive are
   x2-slippage and pac-scalp), and `watchdog.log` ends at 2026-09-02T13:58Z with its five startup lines.
   The "watchdog respawns it" guarantee the whole arena architecture leans on has not existed since 09-02.
4. **A live probe this tick settles that it is not transient.** One read-only `getSlot` on the funded
   `HELIUS_API_KEY`: `HTTP 429 · max usage reached`. **The quota is still exhausted 56 hours later.**
   Restarting the listener would only reproduce the 429 loop.

## WHAT THE ARMS GOT RIGHT

Worth stating plainly, because it is the part of the honesty spine that worked: **the arms refused
rather than fabricated.** They detected the disconnect, logged it, and booked nothing — no invented
fills, no false `-100%` rugs from an absent price. The failure is one of *notification*, not integrity.

## WHAT THE ARMS GOT WRONG — dangling right-censored opens

Cohort counts from the ledgers:

| arm | opened | resolved | void | **dangling open** |
|---|---|---|---|---|
| VIRALITY_ARRIVAL_V2_2 | 8 | 0 | 8 | 0 |
| BUNDLE_MOMENTUM_V2 | 98 | 97 | 75 | **1** |
| MIGRATION_ACCEPTANCE_V1 | 75 | 59 | 7 | **9** |

**Ten positions are frozen mid-flight, right-censored by the outage.** This is a live honesty hazard,
not a bookkeeping detail: if the feed returns and the resolvers simply pick these up, they will resolve
on a 56-hour-stale basis, or fall down the RUG_UNPRICED path and book a false `-100%` — the exact bug
that voided the earlier virality epoch. **Pre-committed here, before anyone can see the numbers: on feed
restoration these ten entries are VOIDs (`FEED_OUTAGE_CENSORED`), never resolutions.** Recording it now,
blind, is what makes it binding; the actual ledger edit is a deliberate step for a tick that has a live
feed, not an autonomous edit from this one.

## SEPARATE, SMALLER FAULT

`VIRALITY_ARRIVAL_V2_2` stopped ~3h before the tape died (59.3h vs 56.3h) and its ledger is
8 opened / 8 void / **0 resolved** — it has never produced a single resolution under the current epoch.
That is its own defect, independent of the outage, and is NOT explained by it. Flagged, not diagnosed;
it needs its own bounded look.

---

## WHY THIS MATTERS BEYOND THE ARENA

This is the sixth and sharpest instance of the T48 thesis, and it generalises past the input surface:

> A green process is not a working process. `chain_ok` proved ledger *continuity* while the ledger was
> not being appended to at all; a dashboard that renders proves a *server*, not a *feed*. Every liveness
> signal the arena publishes was green throughout a total input outage.

It also lands directly on the **pay-or-stop packet (T49)**. That packet framed pay-or-stop as an
equities-lane question. It is not: **the memecoin lane is now hard-blocked on paid data too.** MEME ARENA
cannot collect another row without Helius quota, i.e. without owner spend. Both lanes are queued behind
the same decision, which strengthens the packet rather than changing its menu.

## KILL-CONDITION BOOKKEEPING

T48's kill-condition ("if all five collectors audit CLEAN, the thesis is spent") does **not** fire: six
instruments audited, and this one is a fault, not a clean bill. But every declared instrument has now
been audited, so T48 closes **done** on completed scope. The thesis is vindicated, not spent: **five of
six audits found a real fault, and zero of those faults were caught by a green selftest.**

## WHAT WAS NOT DONE, AND DELIBERATELY

- **The listener was NOT restarted.** The quota is provably still exhausted; a restart is a 429 loop that
  burns nothing but noise, and the real gate is an owner spend decision.
- No frozen rule, prereg, threshold or scoring path touched. No arm re-activated or re-epoched (any such
  edit drifts every closure). No ledger row written. No BASKET1 leg, no re-freeze. t4 untouched. No commit.
