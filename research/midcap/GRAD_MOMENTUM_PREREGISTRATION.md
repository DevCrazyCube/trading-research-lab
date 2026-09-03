# Graduated-memecoin momentum — PRE-REGISTRATION
Frozen 2026-09-03 BEFORE any backtest cell is read. Data crawl was still running at freeze time
(8 of 1075 fetched), so no result could have informed this document.

## The claim under test (owner's words)
"our bot could've scored everything here" — i.e. buying pump.fun coins that are visibly running,
on the trending tab, makes money.

## Universe — survivorship-free by construction
Every `complete=1` mint in research/b11a/window_labels.sqlite (1,075 of 33,866 creates). That
window was enumerated FROM CHAIN, so it contains graduates that later went to zero. Coins with no
GeckoTerminal pool or <30 minute bars are EXCLUDED, and the excluded count MUST be reported —
if exclusion correlates with death, the panel is biased UP and the result is void.

## Execution model (no lookahead)
Signal evaluated on bar i using only bars <= i. Entry at bar i+1 OPEN. Exit at close of i+1+H.
Entering on the signal bar itself is forbidden — that is the classic memecoin backtest lie.

## Cost
3.0% round trip, the repo's measured memecoin toll. NOT negotiable downward: at the owner's $63
size the fixed Solana + platform fees make 3% a floor, not a worst case.

## Grid (declared in full, 18 cells)
lookback x threshold: (5m,+20%) (5m,+50%) (15m,+30%) (15m,+100%) (30m,+50%) (60m,+100%)
hold: 5m, 15m, 60m
PRIMARY CELL, declared now to prevent cherry-picking: **(15m, +30%, hold 15m)**.
All other 17 cells are secondary and require multiplicity correction.

## Gates
 GATE 1 coverage: >= 300 coins with >= 30 usable bars, and the excluded fraction reported.
 GATE 2 power:    MDE from realized per-trade sd, clustered BY MINT (trades within one coin are
                  not independent), computed BEFORE any effect is read.
 GATE 3 effect:   cluster-bootstrap by MINT, 2000 draws. Report mean AND median — a positive mean
                  with a deeply negative median is the tail-carried mirage this repo has hit
                  repeatedly, and does NOT count as a pass.
 GATE 4 multiplicity: secondary cells need Bonferroni-corrected CI (alpha 0.05/18 = 0.0028).

## PASS condition (frozen)
Primary cell net mean > 0 AND cluster-bootstrap CI-lower > 0 AND median > 0.
A pass on secondary cells only, without the primary, is reported as EXPLORATORY — never as a bot.

## Declared kill-risks
 1. Tail-carried mean: a few 30x coins carry a positive mean while the median trade loses. This is
    the single most likely outcome and it is NOT tradeable at $63 — you cannot hold enough names.
 2. Toll dominance: gross edge smaller than 3%.
 3. Fill realism: minute OPEN is unachievable on a coin doing 200%/min. Any positive result must be
    re-tested against a worse fill before it can become a bot.
 4. Exclusion bias: dead coins losing their pool and dropping out of the panel.
