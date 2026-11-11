# meme-research

An evidence-first research project for trading systems. It began as research for a Pump.fun trading system
and since 2026-11-10 also holds a multi-asset research programme.

**It is not a live trading bot.** Nothing in this repository places orders, and no strategy here has been
shown to make money after costs.

## Current state (2026-11-11)

- No strategy is fundable.
- A forward paper logger for two crypto-perp books has been running since 2026-11-11. It reads public market
  data once a day and places no orders. Its first reading is on 2027-01-09.
- The details, the results and the commands to check the logger are in `research/factory/README.md`.

## Where things are

| File | What it is |
|---|---|
| `AGENTS.md` | Operating rules for every agent and contributor. Read it first. |
| `PLAN.md` | Scope, promotion gates and the current phase. |
| `DOCUMENTATION.md` | Verified facts, architecture and terminology. |
| `DECISIONS.md` | The decision log. New entries are appended at the bottom. |
| `research/FINDINGS.md` | Findings of the earlier programme. |
| `research/factory/README.md` | The current programme: what was tested, what it found, and the forward paper test. |

## Rules that do not bend

From `AGENTS.md`:

- No live trading without the promotion gates in `PLAN.md` and explicit owner authorization.
- No wash trading, spoofing, coordinated promotion or any other market manipulation.
- Signing and treasury systems stay outside research services.
- No secrets, keys or wallet-identifying information in this repository.
