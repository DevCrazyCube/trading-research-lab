# MEMEBOT_EVO — an evolutionary variant engine for the paper memecoin bot

A **CPU-only, rule-based, forward-selected population** of memecoin strategy variants ("genomes") that
**breed** (mutation + crossover) and are **selected by forward paper P&L**, under strict
**multiple-testing discipline** so the search does **not** overfit.

This is a **separate package** that **reuses the memebot's primitives read-only** — its free/keyless data
feed (`..memebot.feed`), its deterministic screen (`..memebot.screen`), and its canonical freeze hash
(`..memebot.frozen.canonical_sha256`). **It edits no memebot file.** The one piece it cannot import — a
flow-following exit — is copied/extended locally in `evo_paper.py`.

## Hard limits (non-negotiable)
- **PAPER ONLY** — no real orders, no wallet, no SOL, no on-chain writes. Every position is a hypothetical
  mark-to-market, frozen (sha256 + UTC) **before** its outcome.
- **Forward-selected, never backtest-optimized.** A genome is ranked only on forward trades it was **not**
  bred on.
- **Multiple-testing-bounded.** A "real" survivor must clear the **√(2 ln K)** noise bar (K = cumulative
  genomes ever evaluated) **and then repeat** on a fresh out-of-sample slice.
- **CPU-only** — no GPU, no neural nets, no training, no external ML deps. Pure stdlib arithmetic.
- **Free/cached data only**, via the memebot's host-allowlisted read-only feed.

## Why this exists (honest framing)
The programme already found memecoin trading is **negative-sum by construction** (the ~3% toll is the
house edge). **Evolution cannot create an edge that is not there.** If the edge is absent, this population
converges to ~flat/negative and **that is the honest, cheap answer** — reported plainly, not hidden. The
engine's job is to make a false *"we evolved an edge"* claim hard to make by accident. See
`EVO_PREREGISTRATION.md` for the frozen selection rule, noise bar, reality gate, and kill rule.

## The anti-overfitting rules (in one breath)
1. Genomes accumulate **forward** paper trades, each in its own append-only ledger.
2. Below the pre-registered minimum (`N_min_eval = 20` resolved PASS trades) there is **NO VERDICT** —
   population expectancy is *behaviour, not evidence*.
3. Mature genomes are ranked by forward mean R; bottom half killed, survivors bred + fresh-random mixed in.
4. **K** (distinct genomes ever evaluated) only grows. The bar to beat is **√(2 ln K)** SE.
5. A genome that clears the bar is a **candidate**; it is **REAL** only if it clears the bar **again** on a
   **fresh out-of-sample slice** it was not selected on.
6. **Kill switch:** no confirmed edge after `M = 8` generations *and* best expectancy significantly
   negative → **HALT: "no evolvable edge found."**
7. The **toll is pinned** and never evolved — the search cannot cheat by pretending trading is cheaper.

## Genome schema
`genome.py::GENE_BOUNDS` (screen thresholds + exit rule + two optional early exits), plus flags
`use_dead_exit`, `use_flow_exit`. Fixed (not evolved): `bankroll_sol`, `position_fraction`,
`toll_per_side`. A genome's id is a short sha1 of its canonical gene dict, so identical genomes collapse
to one id and K is counted honestly.

## Commands
```
python -m scripts.trading_bot.memebot_evo selftest        # hermetic wiring + K-bar demo, NO network
python -m scripts.trading_bot.memebot_evo seed [--size 24] # create the initial population (once)
python -m scripts.trading_bot.memebot_evo evolve [--cycles N]  # accumulate + one selection generation
python -m scripts.trading_bot.memebot_evo scan            # open frozen paper entries (all genomes)
python -m scripts.trading_bot.memebot_evo track           # refresh + resolve open positions
python -m scripts.trading_bot.memebot_evo status          # population + K-corrected bar (read-only)
```

### Continuous evolution (detached, watchdog-friendly)
```
bash scripts/trading_bot/memebot_evo/watchdog.sh   # (re)starts evolve_loop.sh if not running
```
`evolve_loop.sh` runs one forward cycle (track → scan → attempt selection) every `EVO_INTERVAL` seconds
(default 180). Selection is a no-op until ≥ 4 genomes mature, so the early loop simply accumulates forward
trades — the honest state below the minimum.

## On-disk layout (all under this package, never touching memebot files)
- `population.json` — genomes + the active set + named-seed ids.
- `evo_state.json` — generation, K (all genome ids ever), candidates, confirmed/falsified, halt state.
- `ledgers/{genome_id}.jsonl` — each genome's own append-only paper entries + resolutions.
- `generation_log.jsonl` — one honest slim report per generation.
- `evolve_run.log`, `watchdog.log` — loop/watchdog logs.
