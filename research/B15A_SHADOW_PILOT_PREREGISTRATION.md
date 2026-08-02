# B15a — preregistration: the live Pump launch shadow pilot

Date: 2026-08-02. Author: Claude (handoff 112).
Status: **FROZEN. Committed alone, before any code connects to any endpoint and before a single
frame exists.**

The machine-readable freeze is `research/B15A_SHADOW_PILOT_PREREGISTRATION.json`. This document is
the argument for it. Neither commit carries code, a connection, or a number observed from anything.

## 0. What this is, in one paragraph

A passive observer of public Solana log notifications. It records what it saw, when it saw it, what
it could and could not decode, and what the **frozen B11b P1 policy** would hypothetically have
proposed. It never signs, never constructs a transaction, never submits, never spends, and never
holds key material. Nothing it produces is an order, an execution, or a claim of profit.

## 1. The limitation that has to come first

**This is not Geyser fidelity, and it may never be described as such.** Four kinds of evidence are
structurally unavailable from `logsSubscribe`, and no amount of care in the recorder recovers them:

| unavailable | consequence |
| --- | --- |
| **orphaned / forked slots** | a log notification carries no reorg signal, so a launch observed here may later not exist on the canonical chain — and this pilot cannot tell |
| **account updates** | no pre/post account state arrives, so reserves *at the decision instant* are not observable from the feed alone |
| **slot-dead notifications** | a skipped or dead slot is invisible, so a gap cannot be distinguished from silence |
| **guaranteed delivery** | the subscription is best-effort; a dropped notification leaves no trace in the stream |

So **every count this pilot produces is a lower bound on what happened, and every gap it records is
a lower bound on what it missed.** No completeness claim may be made from it. That sentence is in
the frozen block, not only here, because it is the claim most likely to be quietly dropped when
someone summarises the results.

## 2. Isolation

Everything lives under `research/b15a`. The pilot may not read or write the B11a corpus, the burned
artifacts, or any file in the B11c integrity manifest. A shadow that can write into the evaluation
window is not a shadow, and the running collection must be untouchable from here.

## 3. The window and the stopping rule, fixed before the first frame

Starts at the first successful subscription confirmation. Runs until **whichever comes first**:

- **72 hours** of wall clock, or
- **5,000** observed launch records.

**Extension is forbidden.** A pilot extended after its operator has seen the numbers is a pilot
whose length was chosen by the numbers. Early stopping is permitted only for an explicit operator
stop or a declared fault — credential absent, endpoint refusing, artifact path unwritable, or a
decode-contract mismatch — and the stop must be recorded. No result may be reported before the
stopping rule fires or a fault stops it.

## 4. Two clocks, and why

Every timestamped record carries **wall** and **monotonic** time. Wall time correlates with the
chain and with other systems; it is also subject to NTP steps, so a latency computed from it can be
negative. Monotonic time cannot step, so every *duration* here — observation-to-decision, backfill
latency, freshness — is measured on it, and every *correlation* uses wall. Recording only one would
force every consumer to choose the wrong clock for one of those jobs.

## 5. What gets recorded

Four record types, frozen in the JSON: `raw_frame`, `session`, `connection_event`, `launch`,
`decision`.

The **raw frame is immutable and append-only**: the provider's payload exactly as delivered, with a
sequence number, both clocks, the commitment, and a hash. Everything else in the system is derived
from it and can be recomputed. It cannot. A line once written is never edited or deleted.

`connection_event` carries the unglamorous half of the evidence — connect attempts, subscription
confirmations, heartbeats, suspected gaps, disconnections, reconnect scheduling and faults. A feed
whose outages are not recorded reports its good periods as if they were all of them.

## 6. Decisions are hypothetical, and unknown is never a default

The policy is the **frozen B11b P1** definition re-instantiated — enter every curve passing all
vetoes — at the unchanged 0.1 SOL hypothetical size. That size comes from B10a/B10b/B10c/B11b, so
no size was chosen with this pilot in view. B11b's hard vetoes apply unchanged; B12a's risk-governor
semantics apply where inputs are available, with its ratification still `operator_unratified`.

**Unknown, stale or incomplete input means no shadow entry, with a reason.** Never a default, never
an assumed value, never a zero. Eight reason codes `S01`–`S08` are frozen, and the most important
of them is `S01_feed_only_no_reserves`: the honest common case, where the feed simply cannot tell
you what the reserves were at the instant you would have had to decide.

The freshness bound is **30 seconds on the monotonic clock**, chosen here before any latency was
observed — so it cannot have been fitted to the distribution it bounds.

## 7. What is measurable, and one thing that is not

The pilot publishes reconnect rate, gap rate, backfill success rate and latency, decode/unknown
rate, and observation-to-decision time.

**Absolute one-way feed latency is not measurable and is not claimed.** `logsSubscribe` carries no
provider send timestamp, so there is nothing to subtract from arrival time. What *is* measurable is
arrival spacing and observation-to-decision duration, and those are what the schema records. A
"latency" figure computed against a slot's nominal time would be an estimate of network conditions
dressed as a measurement of the feed.

## 8. Forbidden, by name

Wallet or key material of any kind. Signing. Constructing a transaction. Submitting one. Tips,
priority fees, or any spending. External messaging. Any claim that a result is executable, live,
profitable or production ready. Fitting any model. Adding any window to B14c's `eligible_windows`.
Reading or writing the B11a corpus. Altering or restarting the B11c watcher.

`performance_status` is `not_evaluated` and `execution_status` is `never_executed`, both locked, and
`geyser_fidelity` is among the status names refused by name.

## 9. The operator status line

Redacted by construction. It publishes session identity, liveness, uptime, frame count, reconnects,
gaps, decode counts, decision counts by reason code, and progress toward the stopping rule.

It never publishes a credential, the endpoint path or query, any mint, curve, creator or signature,
or any hypothetical size or simulated figure. A status line is read by people and pasted into
places; identities and figures do not belong in one.
