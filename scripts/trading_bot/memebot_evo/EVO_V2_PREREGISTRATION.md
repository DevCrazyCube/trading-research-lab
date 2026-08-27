# MEMEBOT_EVO_V2 — pre-registration (evolutionary tactic search, honest-measurement rebuild)

**Instrument:** `MEMEBOT_EVO_V2` — a PAPER, free-data-only, forward-only evolutionary search over memecoin
tactic genomes (screen + exit knobs). It places NO orders, holds NO wallet, touches NO SOL, writes
NOTHING on-chain, reads only free keyless data. Real trading is a separate, owner-gated wallet decision.

**Why V2 (say it plainly).** The V1 forward record is CONTAMINATED: the ruleset moved *after* results were
visible — `MIN_MATURE_FOR_SELECTION` was changed 4→3, the fitness silently switched from mean-R to
terminal full-loss stress (`FITNESS_VERSION=2`), the seed set grew via undeclared `extend_*` injections,
and `POP_CEILING=60` was never in the V1 prereg. The V1 prereg also declared population 24 while the
engine ran 60. So V1 cannot be a lookahead-proof forward test. V2 re-freezes the rules to MATCH the code
exactly, one source of truth, verified at load. An improvement is a NEW frozen instrument (EVO_V3, …),
never an edit to this one.

**Freeze intent.** The constants below are frozen BEFORE the first V2 forward datum. The loader
(`memebot_evo/frozen.py`) recomputes the SHA-256 of *this file*, refuses on mismatch, AND asserts every
`engine.py` module-level constant equals the value pinned in `EVO_V2_FROZEN.json` (constant-drift check)
— so the prereg and the code cannot silently diverge again.

**Honest prior.** The likely outcome of this search is that the population converges to ~flat/negative —
and THAT is the honest finding, consistent with the whole memecoin programme (every frozen variant is
flat-to-negative once the unexitable rug tail is honestly marked at full loss). This search is NOT
expected to manufacture an edge; it exists to let fresh forward data adjudicate whether any tactic
genome clears the K-corrected multiple-testing bar on a fresh held-out slice.

---

## 1. Genome space (FROZEN)

A genome parameterises: the deterministic screen (`min_fdv_usd`, `min_reserve_usd`, `min_unique_buyers`,
`max_buys_per_buyer`, `honeypot_min_buys`, `max_pool_age_minutes`, and where present the exitability
rules); the exit rule (`horizon_minutes`, `stop_frac`, `target_frac`, dead-exit, and the vol-scaled /
sub-minute / momentum genes where enabled). No per-coin LLM; deterministic screen only.

## 2. Population & forward accumulation (FROZEN — mirrors the running engine)

- **N_MIN_EVAL = 20** resolved PASS trades before a genome is eligible to rank / gate (a genome below this
  is behaviour, not evidence).
- **POP_CEILING = 60** — hard cap on the active population; kill-free breeding stops at this size.
- **MIN_MATURE_FOR_SELECTION = 3** — a generation (kill + breed) runs only when ≥ this many genomes are mature.
- **MIN_SURVIVORS = 3** — with a small mature pool, keep at least this many top genomes as survivors.
- **MIN_CHILDREN_PER_GEN = 4** — breed at least this many children from the survivors each selection.
- Breeding: crossover (uniform) then mutation (`rate = 0.30`, gaussian `scale = 0.20 × range`).

## 3. Fitness & the honest decider (FROZEN)

- **FITNESS_VERSION = 2** — genomes are ranked/killed on **terminal FULL-LOSS STRESS mean R**: every
  `UNEXITABLE_TIMEOUT` resolution is valued at −100% (before the pinned toll), matching the sniper
  `full_loss_stress_r` and the AFTERSHOCK ecr −1.0 convention. The generous −25% mark is NEVER the
  selection fitness. This is the single biggest honesty fix vs V1.

## 4. The multiple-testing bar (FROZEN, with its honest caveat)

The noise bar is `√(2 ln K)`, K = the count of DISTINCT genomes ever evaluated (all trials count forever).
**Honest caveat, stated in the prereg:** the genomes share largely the SAME coins, so their trials are
NOT independent, and `√(2 ln K)` is an *expected-max-under-null* heuristic, not a controlled significance
threshold. A genome is a CANDIDATE only if its t-stat clears the current `√(2 ln K)` bar; it is REAL only
if a FRESH, untouched held-out slice ALSO clears the bar (the reality-gate). `anything_beats_bar` is
evaluated over **ALL mature genomes**, not just the highest-mean one.

## 5. Reset procedure (V1 archived, not edited)

The V1 ledgers/state/population are ARCHIVED (moved to `*_v1_archive/`), never edited. V2 starts a clean
seeded population at generation 0, K reset to the seeded count. Nothing proven is discarded: the V1
candidate `g73c7da` was already falsified on its fresh slice.

---

*Paper only. No orders, no wallet, no real SOL, no on-chain writes, free data only. The forward log is the
only arbiter. Below the minimum this is behaviour, not evidence; the honest prior is ~0 or negative.*
