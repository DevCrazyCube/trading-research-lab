# Agent Operating Rules

This repository is an evidence-first research project for a Pump.fun trading system. It is not yet a live trading bot.

## Context recovery

At the start of every task:

1. Read this file.
2. Read `PLAN.md` for scope, gates, and current phase.
3. Read `DOCUMENTATION.md` for verified facts, architecture, and terminology.
4. Read `DECISIONS.md` before changing architecture or research methodology.
5. Read `agent_discussion.md` when coordinating with another model.
6. Check the working tree and inspect existing code before proposing or making changes.

If these files conflict, stop and resolve the conflict explicitly. Never silently select the more convenient claim.

## Evidence discipline

- Label statements as **verified fact**, **working hypothesis**, **decision**, or **open question**.
- Verify time-sensitive protocol details against primary sources before relying on them.
- Record the source URL, access date, and relevant program/version or slot range.
- Never invent program IDs, instruction layouts, fee rates, RPC guarantees, performance figures, or research results.
- Treat third-party claims and vendor benchmarks as claims, not guarantees.
- Preserve raw data and point-in-time observations. Derived tables must be reproducible.
- Prevent temporal, creator, wallet, token, and funding-cluster leakage.
- Never use future information to construct a historical decision feature.
- Report executable returns after all costs; chart returns are not trading returns.
- State uncertainty and missing evidence plainly.

## Safety and scope

- Do not implement or enable live trading without the promotion gates in `PLAN.md` and explicit user authorization.
- Do not add wash trading, spoofing, coordinated promotion, deceptive behavior, or other market manipulation.
- Keep signing and treasury systems outside research services.
- Default to no trade on stale, incomplete, conflicting, or out-of-distribution data.
- Preserve user work and avoid destructive operations.
- Never commit secrets, seed phrases, private keys, RPC credentials, or wallet-identifying private information.

## Engineering rules

- Prefer exact on-chain decoding using official IDLs and program data over browser scraping.
- Use one canonical event schema for historical and live ingestion.
- Preserve ordering by slot, transaction index, outer instruction index, and inner instruction index; never use database insertion order.
- Make state reconstruction deterministic and validate it against independent RPC checkpoints.
- Keep raw ingestion, canonical state, features, labels, models, simulation, execution, and risk control separable.
- Every behavior-changing change requires proportionate tests and a short entry in `DECISIONS.md` when it changes a durable design choice.
- Unknown instructions or reconciliation failures must fail visibly, never disappear silently.

## Collaboration

- Use `agent_discussion.md` as an append-only decision and handoff log between Codex and Claude.
- Identify author, UTC timestamp, status, evidence, proposal, questions, and requested action.
- Do not treat another model's assertion as verified merely because it is confidently written.
- Only one agent should edit a given implementation area at a time. Record ownership before parallel work.

