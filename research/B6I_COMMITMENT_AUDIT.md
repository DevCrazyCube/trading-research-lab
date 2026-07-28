# B6i — Commitment Correlator Audit and Corrected Measurement

Run: 2026-07-27. Author: Codex. Free public Solana WebSocket; read-only.

## Why B6h could not support F36–F38

The original readers each started their duration clock after their own connection completed.
They therefore had different left and right window edges. They also stopped without a grace
period for confirmations belonging to processed observations near the right edge. Consequently,
the 298 `confirmed-only` signatures could be startup skew, and processed-only observations were
right-censored. Independent public subscriptions also provide no completeness oracle, so absence
from one socket is not proof that the provider never emitted the item.

The claim that processed→confirmed is the dominant component of “decision-time visibility” was
also conceptually wrong. A strategy can act at processed arrival; confirmation happens later.
The delta measures public-endpoint arrival behavior/settlement observation, not chain-event to
client latency.

## Corrections

`scripts/b6h_commitment_correlator.py` now:

- waits for both JSON-RPC subscription acknowledgements before a shared start barrier;
- admits a processed cohort only inside a shared capture interval;
- keeps both streams open for a configurable confirmation grace interval;
- labels the result as client-observed arrival delta, not internal commitment latency;
- reports confirmed-only as a diagnostic, never a proven processed-stream miss.

The recorder now calls a subscription acknowledgement `unknown`, not `heartbeat`; scopes verbatim
capture to WebSocket message payloads; and uses a fixed reconnect delay rather than turning total
lifetime reconnect count into permanent exponential backoff. Schema v0.3 adds the concrete
`log_truncated` loss mode already emitted by the adapter.

## Live results

First diagnostic: 45 s cohort + 3 s grace. Processed 48,294; confirmed 2,719; 2,719 matched;
median matched delta 15.7 s. The extreme rate mismatch showed that three seconds was inadequate.

Second run: 15 s cohort + 60 s grace:

| Metric | Value |
|---|---:|
| Processed notifications over full run | 32,017 |
| Confirmed notifications over full run | 24,016 |
| Processed cohort | 9,682 |
| Matched within grace | 9,469 (97.8%) |
| Unmatched after 60 s | 213 (2.2%) |
| Confirmed-core lacking any processed observation | 0 |
| Median matched arrival delta | 26.46 s |
| p10 / p90 / p99 | 0.286 s / 28.71 s / 29.07 s |
| Negative deltas | 0 |

This does **not** establish 26.46 s as a normal Solana confirmation time. The tight mass near
29 seconds and high variability relative to B6h instead demonstrate public-endpoint buffering,
fanout, rate/backlog, or window-specific effects. One public endpoint is not a stable timing
oracle. The prior 174 ms figure is withdrawn; no replacement constant is adopted.

## Decision

Use processed logs for research-time discovery and record local arrival timestamps. Do not use
this processed/confirmed correlator as an execution-latency model. Before live execution, measure
our own submission-to-processed/confirmed lifecycle from the intended host and endpoint, including
send timestamp, signature observation, RPC response, expiry, fees, and failures. No live trading
was performed.
