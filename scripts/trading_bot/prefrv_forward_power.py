#!/usr/bin/env python3
"""PREFRV forward-design power arithmetic (task T39), from FROZEN AGGREGATES ONLY.

Inputs are the design/held-out aggregates already on record (INVENT_0822_MASTER 3.1 and
T30_B01_PAIR_EDGES.json counts).  Reads NO forward borrow extract, NO pair-level fee, NO price.
Purpose: state, before the T30 day-30 verdict, how many book-weeks the PREFRV forward paper test
needs to DETECT the design-window net effect, and what effect it can detect in 52 / 156 weeks,
as a function of how many of the 113 pairs the evaluator returns as alive.  Written 2026-08-30.
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "research", "trading_bot", "PREFRV_FORWARD_POWER.json")

# --- frozen aggregates (sources cited in PREFRV_FORWARD_PREREGISTRATION.md s5) ---
T_GRID, DESIGN_WEEKS = 434, 302                 # T30_B01_PAIR_EDGES.json
HELD_WEEKS = T_GRID - DESIGN_WEEKS              # 132
NET_MEAN_BP = 9.6                               # held-out net, bp per book-week (MASTER 3.1)
NET_T = 1.48                                    # held-out net t (MASTER 3.1)
GROSS_SR_HELD = 3.08                            # held-out gross annualised Sharpe (MASTER 3.1)
ACTIVE_PAIRWEEKS_FULL, N_PAIRS = 10226, 113     # sum(active_weeks_full), T30_B01_PAIR_EDGES.json
MEDIAN_ACTIVE_WEEKS_FULL = 86                   # per pair, T30_B01_PAIR_EDGES.json
Z_ALPHA_1S = 1.6449                             # one-sided 5 %
Z_POWER_80 = 0.8416
T_ALIVE = 2.0                                   # forward ALIVE bar (one-sided replication bar)

sd_book_full = NET_MEAN_BP * math.sqrt(HELD_WEEKS) / NET_T          # bp per book-week, full book
sr_week_net = NET_MEAN_BP / sd_book_full
k_full = ACTIVE_PAIRWEEKS_FULL / T_GRID                             # mean active pairs per week
active_frac = MEDIAN_ACTIVE_WEEKS_FULL / T_GRID                     # per-pair P(active)
gross_mean_bp = GROSS_SR_HELD / math.sqrt(52.0) * sd_book_full      # implied held-out gross bp/wk
cost_mean_bp = gross_mean_bp - NET_MEAN_BP

rows = []
for n_alive in (10, 20, 30, 60, 113):
    k = active_frac * n_alive
    # equal-weight average of k active pairs; independence assumed (same-issuer correlation makes
    # the true sd LARGER, so every power figure below is an UPPER bound on power)
    sd_k = sd_book_full * math.sqrt(k_full / k)
    n_detect_net = ((Z_ALPHA_1S + Z_POWER_80) * sd_k / NET_MEAN_BP) ** 2
    n_detect_gross = ((Z_ALPHA_1S + Z_POWER_80) * sd_k / gross_mean_bp) ** 2
    det52 = (Z_ALPHA_1S + Z_POWER_80) * sd_k / math.sqrt(52)
    det156 = (Z_ALPHA_1S + Z_POWER_80) * sd_k / math.sqrt(156)
    t_expected_52 = NET_MEAN_BP / sd_k * math.sqrt(52)
    t_expected_156 = NET_MEAN_BP / sd_k * math.sqrt(156)
    rows.append(dict(
        n_alive_pairs=n_alive, mean_active_pairs_per_week=round(k, 2), sd_book_week_bp=round(sd_k, 1),
        weeks_to_detect_design_net_80pct=round(n_detect_net),
        weeks_to_detect_design_gross_80pct=round(n_detect_gross),
        detectable_net_bp_at_52w=round(det52, 1), detectable_net_bp_at_156w=round(det156, 1),
        expected_t_at_52w_if_design_net_true=round(t_expected_52, 2),
        expected_t_at_156w_if_design_net_true=round(t_expected_156, 2),
        multiple_of_design_net_needed_for_alive_at_52w=round(T_ALIVE * sd_k / math.sqrt(52) / NET_MEAN_BP, 1),
    ))

out = dict(
    written="2026-08-30 15:00 CEST (T39)",
    inputs=dict(T_grid=T_GRID, design_weeks=DESIGN_WEEKS, held_weeks=HELD_WEEKS, net_mean_bp=NET_MEAN_BP,
                net_t=NET_T, gross_sr_held=GROSS_SR_HELD, active_pairweeks_full=ACTIVE_PAIRWEEKS_FULL,
                n_pairs=N_PAIRS, median_active_weeks_full=MEDIAN_ACTIVE_WEEKS_FULL),
    derived=dict(sd_book_week_bp_full_book=round(sd_book_full, 1), weekly_net_sharpe=round(sr_week_net, 4),
                 annual_net_sharpe_check=round(sr_week_net * math.sqrt(52), 3),
                 mean_active_pairs_per_week_full=round(k_full, 2), per_pair_active_fraction=round(active_frac, 3),
                 implied_heldout_gross_bp_per_week=round(gross_mean_bp, 1),
                 implied_heldout_cost_bp_per_week=round(cost_mean_bp, 1)),
    assumption="independent pair returns; same-issuer correlation makes sd larger, so power is an upper bound",
    rows=rows,
)
with open(OUT, "w") as fh:
    json.dump(out, fh, indent=1, sort_keys=True)
print(json.dumps(out["derived"]))
for r in rows:
    print(r)
print("written", OUT)
