#!/usr/bin/env python3
"""Selftest for convexity_toll -- venue classification, the inverse-throughput slippage curve, and the
net-return math, plus two WORKED EXAMPLES (one cheap/liquid coin, one expensive bonding-curve coin).
PAPER ONLY. Pure arithmetic, no I/O beyond assertions/prints."""
from __future__ import annotations
import convexity_toll as ct


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


def test_classify():
    assert ct.classify_venue(200.0, split=50.0) == "CHEAP"
    assert ct.classify_venue(10.0, split=50.0) == "EXPENSIVE"
    assert ct.classify_venue(50.0, split=50.0) == "CHEAP"       # boundary inclusive
    assert ct.classify_venue(None, split=50.0) == "EXPENSIVE"
    print("  classify: >=split CHEAP, <split EXPENSIVE, None->EXPENSIVE OK")


def test_slippage_curve():
    # inverse-throughput: thin coin slips more; floored and capped, never zero
    assert approx(ct.slippage_bps_side(5.0),  25.0 + 1125.0 / 5.0)    # 250 bps
    assert approx(ct.slippage_bps_side(50.0), 25.0 + 1125.0 / 50.0)   # 47.5 bps
    assert approx(ct.slippage_bps_side(100.0),25.0 + 1125.0 / 100.0)  # 36.25 bps
    assert ct.slippage_bps_side(1e9) >= ct.SLIP_FLOOR_BPS             # never below floor
    assert ct.slippage_bps_side(1e9) < ct.SLIP_FLOOR_BPS + 1e-3       # tends to floor
    assert ct.slippage_bps_side(0.001) == ct.SLIP_CAP_BPS            # capped for near-zero throughput
    assert ct.slippage_bps_side(None) == ct.SLIP_CAP_BPS
    # monotone: more liquidity -> less slippage
    assert ct.slippage_bps_side(10) > ct.slippage_bps_side(100) > ct.slippage_bps_side(1000)
    print("  slippage curve: inverse-throughput, floor 25 / cap 300 bps, monotone OK")


def test_net_return_flat_trade():
    # a flat trade (gross 1.0x) loses exactly the round-trip toll + round-trip slippage
    c = ct.cost_for(100.0, split=50.0)              # CHEAP, slip 36.25 bps/side, toll 0.35%/side
    nr = ct.net_return(1.0, c)
    s = c.slip_frac
    expected = 1.0 * (1 - s) / (1 + s) - 1 - 0.007  # -2s(approx) - 0.7%
    assert approx(nr, expected), (nr, expected)
    # sanity: a flat cheap trade should lose roughly toll(0.70%) + 2*slip(0.725%) ~ -1.4%
    assert -0.020 < nr < -0.010, nr
    print(f"  net flat CHEAP trade: {nr*100:+.2f}% (toll+2xslip) OK")


def test_expensive_costs_more_than_cheap():
    cheap = ct.cost_for(500.0, split=50.0)   # high liq -> CHEAP, low slip
    exp = ct.cost_for(6.0, split=50.0)       # low liq  -> EXPENSIVE, high slip
    # same 2x gross winner nets far less on the expensive/thin coin
    assert ct.net_return(2.0, cheap) > ct.net_return(2.0, exp)
    assert exp.round_trip_toll == 0.02 and cheap.round_trip_toll == 0.007
    print(f"  2x winner nets {ct.net_return(2.0,cheap)*100:+.1f}% CHEAP vs "
          f"{ct.net_return(2.0,exp)*100:+.1f}% EXPENSIVE OK")


def worked_examples():
    print("\nWORKED EXAMPLES (realistic cost applied to a raw price path)")
    # (1) CHEAP / liquid migrated coin: throughput 250 USD/s, rode a +80% gross move (1.80x)
    liq1, gross1 = 250.0, 1.80
    c1 = ct.cost_for(liq1, split=50.0)
    nr1 = ct.net_return(gross1, c1)
    print(f"  CHEAP  liq={liq1:>6.0f} USD/s  venue={c1.venue:<9} toll={c1.round_trip_toll*100:.2f}%RT "
          f"slip={c1.slip_bps_side:.1f}bps/side  gross={gross1:.2f}x -> net {nr1*100:+.1f}%")
    # (2) EXPENSIVE bonding-curve microcap: throughput 7 USD/s, same +80% gross move
    liq2, gross2 = 7.0, 1.80
    c2 = ct.cost_for(liq2, split=50.0)
    nr2 = ct.net_return(gross2, c2)
    print(f"  EXPEN. liq={liq2:>6.0f} USD/s  venue={c2.venue:<9} toll={c2.round_trip_toll*100:.2f}%RT "
          f"slip={c2.slip_bps_side:.1f}bps/side  gross={gross2:.2f}x -> net {nr2*100:+.1f}%")
    print(f"  same +80% gross move nets {(nr1-nr2)*100:+.1f} pp MORE on the cheap/liquid coin")


def main():
    print("convexity_toll selftest")
    for fn in [test_classify, test_slippage_curve, test_net_return_flat_trade,
               test_expensive_costs_more_than_cheap]:
        fn()
    print("ALL SELFTESTS PASSED")
    worked_examples()


if __name__ == "__main__":
    main()
