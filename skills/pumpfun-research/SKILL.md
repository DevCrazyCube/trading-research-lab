---
name: pumpfun-research
description: Conduct evidence-first research and engineering for this repository's Pump.fun/Solana recorder, historical backfill, simulator, wallet intelligence, models, risk controls, and staged trading evaluation. Use for any task involving Pump.fun, PumpSwap, Jetstreamer, Yellowstone/Geyser, Solana execution, rug detection, wallet clustering, backtesting, strategy evaluation, or preparation for paper/tiny live trading in this project.
---

# Pump.fun Research

## Recover context

Read, in order, from the repository root:

1. `AGENTS.md`
2. `PLAN.md`
3. `DOCUMENTATION.md`
4. `DECISIONS.md`
5. `agent_discussion.md` when collaborating with Claude or reviewing a handoff

Inspect the working tree and relevant implementation before acting. Resolve contradictions explicitly.

## Classify the task

- For research, verify time-sensitive facts with primary sources and update documentation only when the evidence changes project knowledge.
- For architecture, distinguish proposal from accepted decision; append durable accepted choices to `DECISIONS.md`.
- For ingestion or simulation, preserve raw data, version decoders, enforce canonical ordering, and reconcile against independent evidence.
- For modeling, enforce point-in-time features, chronological evaluation, executable labels, dependency-aware uncertainty, and simple baselines.
- For collaboration, append a structured message to `agent_discussion.md`; do not overwrite the other agent's contribution.
- For live-trading requests, check `PLAN.md` gates and require explicit user authorization. Do not bypass incomplete gates.

## Maintain epistemic integrity

Use the labels **verified fact**, **working hypothesis**, **decision**, and **open question**. Never turn vendor claims, study-specific results, or backtest outcomes into guarantees. Record versions, slot/date ranges, assumptions, costs, missing data, and uncertainty.

Reject results containing temporal leakage, unrealistic fills, omitted fees, unconstrained exits, or silent decode/reconciliation failures.

## Complete work

Run validation proportionate to risk. Update only the durable context files materially affected by the work. Keep them concise and avoid duplicating the same fact across files unless one location clearly points to the canonical source.
