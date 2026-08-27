#!/usr/bin/env python3
"""Selftest for convexity_probe -- validates the three exit walkers on synthetic bars with KNOWN
outcomes, the toll math, the pessimistic gap-through fill, and the flow-flip K-streak logic.
PAPER ONLY. Pure arithmetic, no I/O beyond assertions."""
from __future__ import annotations
import convexity_probe as cp


def bar(t, o, h, l, c, buy=0.0, sell=0.0):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": buy + sell,
            "buys": 1 if buy else 0, "sells": 1 if sell else 0, "buy_vol": buy, "sell_vol": sell}


def approx(a, b, tol=1e-9):
    return abs(a - b) < tol


def test_toll_math():
    # exit == entry -> net = -2*toll exactly
    nr = cp._net_return(100.0, 100.0, cp.TOLL_PER_SIDE)
    assert approx(nr, -0.03), nr
    print("  toll math: flat trade nets -3% (2x1.5%) OK")


def test_A_target_hit():
    cfg = cp.Config(policy="A", tp_bps=1000, sl_bps=200, exit_slip_bps=0)
    fwd = [bar(0, 100, 100, 100, 100), bar(1, 100, 120, 100, 115)]  # high 120 >= target 110
    r = cp.walk_exit(fwd, 0, cfg)
    assert r["reason"] == "TARGET", r
    # target px = 110, no slip on limit; net = 110/100-1-0.03 = 0.07
    assert approx(r["net_return"], 0.07), r
    print("  A target hit: limit fill at +10%, net +7% after toll OK")


def test_A_stop_gap_through():
    # bar closes far below the stop -> pessimistic fill at the worse close, not the stop
    cfg = cp.Config(policy="A", tp_bps=1000, sl_bps=200, exit_slip_bps=0)  # stop at 98
    fwd = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 50, 60)]  # low 50 <= stop 98, close 60
    r = cp.walk_exit(fwd, 0, cfg)
    assert r["reason"] == "STOP", r
    # min(98, 60) = 60 -> net = 60/100 - 1 - 0.03 = -0.43  (gapped through, big loss)
    assert approx(r["net_return"], -0.43), r
    print("  A stop gap-through: fills at the worse close (-43%), NOT the -2% stop OK")


def test_B_flowflip_K():
    # buy pressure strong then flips; K=2 consecutive below-thr bars required
    # 10s spacing with a 5s window so each rolling window == the current bar (clean flip test).
    cfg = cp.Config(policy="B", flip_window_s=5, flip_buy_frac=0.5, flip_K=2, max_hold_s=1000,
                    exit_slip_bps=0)
    fwd = [
        bar(0,  100, 100, 100, 100, buy=100, sell=0),   # anchor
        bar(10, 100, 130, 100, 130, buy=100, sell=0),   # running, buyfrac high -> hold
        bar(20, 130, 130, 120, 125, buy=10, sell=90),   # 1st below-thr bar
        bar(30, 125, 125, 118, 120, buy=10, sell=90),   # 2nd below-thr -> FLIP here at close 120
        bar(40, 120, 120,  50,  55, buy=0,  sell=99),   # would-be dump AFTER we are out
    ]
    r = cp.walk_exit(fwd, 0, cfg)
    assert r["reason"] == "FLOWFLIP", r
    assert r["exit_px"] == 120, r   # exited at bar 3 close, before the bar-4 collapse
    # net = 120/100 - 1 - 0.03 = +0.17
    assert approx(r["net_return"], 0.17), r
    print("  B flow-flip K=2: exits at 2nd flip bar (+17%), BEFORE the next-bar dump OK")


def test_B_uncapped_winner():
    # buy pressure stays intact through a big run -> no cap, ride to data end
    cfg = cp.Config(policy="B", flip_window_s=5, flip_buy_frac=0.4, flip_K=2, max_hold_s=100000,
                    exit_slip_bps=0)
    fwd = [bar(i, 100, 100*(1+i), 100, 100*(1+i), buy=100, sell=0) for i in range(1, 6)]
    fwd = [bar(0, 100, 100, 100, 100, buy=100, sell=0)] + fwd
    r = cp.walk_exit(fwd, 0, cfg)
    assert r["reason"] == "DATAEND", r
    # last close = 100*(1+5) = 600 -> 6x; net = 6 - 1 - 0.03 = 4.97
    assert approx(r["net_return"], 4.97), r
    assert r["R"] > 40, r  # a monster right-tail winner in R units
    print(f"  B uncapped winner: rides a 6x with buy-pressure intact, net +497% ({r['R']:.0f}R) OK")


def test_C_backstop():
    # price collapses; catastrophe backstop at -60% cuts (pessimistic gap-through)
    cfg = cp.Config(policy="C", flip_window_s=5, flip_buy_frac=0.4, flip_K=2, backstop_frac=0.60,
                    max_hold_s=100000, exit_slip_bps=0)
    fwd = [
        bar(0, 100, 100, 100, 100, buy=100, sell=0),
        bar(1, 100, 100, 30, 35, buy=0, sell=100),   # low 35 <= backstop 40 -> BACKSTOP at min(40,35)=35
    ]
    r = cp.walk_exit(fwd, 0, cfg)
    assert r["reason"] == "BACKSTOP", r
    assert approx(r["net_return"], 35/100 - 1 - 0.03), r  # -0.68
    print("  C backstop: catastrophe floor fills pessimistically at the worse close (-68%) OK")


def test_slippage_applied():
    cfg = cp.Config(policy="B", flip_window_s=5, flip_buy_frac=0.5, flip_K=1, max_hold_s=1000,
                    exit_slip_bps=200)  # 2% extra exit slip
    fwd = [bar(0, 100, 100, 100, 100, buy=100, sell=0),
           bar(1, 100, 100, 100, 100, buy=10, sell=90)]  # immediate flip, close 100
    r = cp.walk_exit(fwd, 0, cfg)
    # exit close 100 with 2% slip -> 98; net = 98/100 - 1 - 0.03 = -0.05
    assert approx(r["net_return"], -0.05), r
    print("  slippage: 2% extra exit slip charged ON TOP of the 3% toll OK")


def test_liquidity_gate():
    cfg = cp.Config(entry_surge_bps=100, entry_window_s=10, entry_min_buyfrac=0.5,
                    entry_min_trades=1, min_liq_usd_per_s=1000.0)
    # a real surge but tiny throughput -> liquidity gate must REJECT
    bars = [bar(0, 100, 100, 100, 100, buy=5, sell=0), bar(5, 100, 130, 100, 130, buy=5, sell=0)]
    ok, diag = cp.momentum_entry_qualifies(bars, 5, cfg)
    assert not ok, diag
    cfg2 = cp.Config(entry_surge_bps=100, entry_window_s=10, entry_min_buyfrac=0.5,
                     entry_min_trades=1, min_liq_usd_per_s=0.5)
    ok2, diag2 = cp.momentum_entry_qualifies(bars, 5, cfg2)
    assert ok2, diag2
    print("  liquidity gate: rejects a real surge with sub-threshold USD/s throughput OK")


def main():
    print("convexity_probe selftest")
    for fn in [test_toll_math, test_A_target_hit, test_A_stop_gap_through, test_B_flowflip_K,
               test_B_uncapped_winner, test_C_backstop, test_slippage_applied, test_liquidity_gate]:
        fn()
    print("ALL SELFTESTS PASSED")


if __name__ == "__main__":
    main()
