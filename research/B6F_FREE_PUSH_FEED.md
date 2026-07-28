# B6f — Free Push Feed: `blockSubscribe` vs `logsSubscribe`

Run: 2026-07-27, approximately 13:45–14:00 UTC. Author: Claude.
Endpoint: `wss://api.mainnet-beta.solana.com` (free public, no account, no key).
Client: `scripts/wsmin.py` — a stdlib-only RFC 6455 implementation, no dependency added.

Read-only. No keys, no signing, no transactions.

Prompted by Codex's Seq-24 narrowing: F26 disqualified HTTP *polling*, not every free push
transport. That narrowing was correct and this document confirms it.

## Result 1 — `blockSubscribe` is unavailable

```
-> blockSubscribe {mentionsAccountOrProgram: PUMP}
<- SERVER ERROR: code=-32601 message='Method not found'
```

The method is optional and expensive, and the public validator does not enable it. This does not
rule it out on a registered free tier or self-hosted validator, but it is not available here.

## Result 2 — `logsSubscribe` works, keeps up, and carries the event payload

70-second continuous run, `commitment: confirmed`, `mentions: [Pump]`:

| Metric | Value |
|---|---:|
| Notifications | **17,071** (243.8/s) |
| Unique signatures | 17,071 (no duplicates) |
| Succeeded / failed | 2,111 / **14,960** |
| **TradeEvents decoded from logs** | **2,003** (94.9% of successful txs) |
| Notifications with truncated logs | **0** |
| Bandwidth | 20.04 MB (293 KB/s) → **24.1 GB/day** |
| Disconnects | 0 |

At ~10× compression (F27) that is **~2.4 GB/day**, so 166 GB of free space holds roughly
**two months** of continuous Pump capture at zero cost.

### F32 — Pump emits TradeEvent through logs *as well as* self-CPI (verified fact)

Every successful Pump transaction sampled carried a `Program data:` log line, and the base64
decodes to a payload beginning `bddb7fd34ee661ee` — the derived `TradeEvent` discriminator.

This is the Anchor `emit!` form: event discriminator followed directly by the borsh body, with no
8-byte `e445a52e51cb9a1d` CPI tag (that tag appears only on the self-CPI inner-instruction copy).
Pump therefore emits the same event on **both** paths.

**This corrects a claim I made in `agent_discussion.md` Seq 18**, where I asserted that
`logsSubscribe` "delivers logs, not inner-instruction data, so it cannot carry the C2 decode path
at all." That was wrong. It carries the full `TradeEvent` payload directly.

The original C2 reasoning is *not* overturned — logs remain truncatable and self-CPI remains the
authoritative source. What changes is that logs are a viable **transport** for live capture, with
truncation as a detectable risk rather than a disqualifier.

### F33 — 88% of Pump-mentioning transactions failed (working hypothesis, best sample so far)

14,960 of 17,071 notifications carried an error. This is 70 seconds of *continuous* observation
rather than the few-slot snapshots that produced F9's contradictory 36.7% and 85.0% figures — so
it is the most credible estimate the project has, and it sits at the top of that range.

It remains one 70-second window and is **not** a base rate. But it strengthens the standing
working hypothesis that transaction landing reliability may matter more to net performance than
marginal improvements in direction classification: a strategy ignoring landing probability would
be modelling roughly one attempt in eight.

Note also that this stream **includes failed transactions**, which is precisely the landing-
reliability data the research needs and which a success-only feed would omit.

## What this feed does and does not provide

**Provides:** real-time `TradeEvent` payloads (mint, user, is_buy, amounts, virtual and real
reserves, fee and creator-fee basis points and amounts, creator, timestamp, `ix_name`,
`mayhem_mode`, quote fields), transaction signature, success/failure, and slot.

**Does not provide:**
- Fees actually paid, compute units consumed, priority fee, or Jito tips — so **cost
  reconstruction (F12/B4-style) is impossible from logs alone** and needs `getTransaction`.
- Account keys and balance deltas — so funding-graph and wallet-clustering inputs beyond the
  event's own `user`/`creator` fields require a follow-up fetch.
- Slot status transitions, dead slots, or processed→confirmed→finalized progression — so
  **orphan derivation (R2) and observation-latency modelling (C3) remain impossible.**
- Account updates.
- Any protection against log truncation, which was C2's original concern. Zero occurrences in
  this window is not a guarantee; a truncated-log detector must be wired to the `unknown`-frame
  alarm rather than assumed absent.

## Assessment

This is sufficient for **Phase 1 research recording and Phases 3–4 modelling** at zero cost. It is
**not** sufficient to close Phase 1's live-capture gate as specified, nor to build Phase 2's
executable and stressed views, because latency and orphan behaviour are absent.

That maps cleanly onto the decision already recorded: research now on free data, buy
execution-grade streaming only if a model earns it.

## Limitations

- One 70-second window on one day; Pump traffic is non-stationary (F9).
- `confirmed` commitment only; a `processed` subscription was not tested and would be the closer
  approximation to decision-time visibility.
- No reconnect, sleep, or long-run stability was exercised. Zero disconnects in 70 seconds says
  little about hours.
- The public endpoint applies undocumented rate and connection limits that were not probed.
- Compression is assumed at F27's 10×, measured on RPC block JSON, not on this stream.

## Follow-ups

1. Long-run stability and reconnect behaviour; wire `session`/`gap` accounting to it.
2. Test `processed` commitment for a nearer-to-decision-time view.
3. Build a truncated-log detector as a fail-visible alarm.
4. Measure compression on this stream specifically.
5. Decide whether to pair the stream with selective `getTransaction` backfill for the cost and
   account-key fields it lacks, and at what sampling rate that stays inside free rate limits.

## Subsequent audit correction

See `research/B6G_FREE_LOGS_AUDIT.md`. The free transport finding is independently reproduced, but
the original 94.9% figure divided TradeEvent count by successful-transaction count even though a
transaction can emit multiple events. Correct event-bearing-transaction coverage in two new
30-second windows was 88.1% confirmed and 94.1% processed; almost all successful non-event
notifications were legitimate non-trade instructions. Space-separated `Program data` fields were
also valid Solana log-data encoding, not malformed base64.
