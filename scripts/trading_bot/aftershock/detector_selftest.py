#!/usr/bin/env python3
"""Offline selftest for the AFTERSHOCK detector state machine. Builds synthetic tapes and asserts:
FIRE on an absorbed shock, CONTROL on an unabsorbed shock, no-arm on an immaterial sell. No network.

    python -m scripts.trading_bot.aftershock.detector_selftest
"""
from __future__ import annotations

from .detector import Detector, DetectorConfig

K = 30.0 * 1_073_000_000.0     # curve invariant: v_sol * v_tokens (whole units)


class _Curve:
    """Emits tape lines with correct post-trade reserves as v_sol is driven up (buy) / down (sell)."""
    def __init__(self, mint="MINT"):
        self.mint = mint
        self.v_sol = 30.0
        self.v_tokens = K / 30.0

    def trade(self, ts, trader, side, new_v_sol):
        new_v_tokens = K / new_v_sol
        tok = abs(new_v_tokens - self.v_tokens)
        sol = abs(new_v_sol - self.v_sol)
        self.v_sol, self.v_tokens = new_v_sol, new_v_tokens
        return {"ts": ts, "mint": self.mint, "trader": trader, "side": side,
                "sol_amount": sol, "token_amount": tok,
                "v_sol": new_v_sol, "v_tokens": new_v_tokens, "pool": "pump"}


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def _play(lines):
    det = Detector(DetectorConfig())
    fires = []
    for ln in lines:
        r = det.on_line(ln)
        if r is not None:
            fires.append(r)
    return fires


def _build(absorb: bool):
    """Coin launches, cluster (DEV,E1,E2,E3) buys it to ~15 real SOL in the cluster window; DEV fires a
    material sell at t=30; then EITHER 3 new wallets absorb it (absorb=True) or nobody does."""
    c = _Curve()
    L = []
    L.append(c.trade(0.0, "DEV", "buy", 36.0))   # deployer
    L.append(c.trade(2.0, "E1", "buy", 40.0))
    L.append(c.trade(4.0, "E2", "buy", 43.0))
    L.append(c.trade(6.0, "E3", "buy", 45.0))    # R=15; cluster window [0,24] closes with {DEV,E1,E2,E3}
    # a couple of in-window non-cluster buys so k60 is clearly < 0.95 and holders are spread
    L.append(c.trade(8.0, "X1", "buy", 45.5))
    L.append(c.trade(10.0, "X2", "buy", 46.0))
    # SHOCK after the cluster window closes: DEV (cluster) sells materially. R_pre ~ 16.
    L.append(c.trade(30.0, "DEV", "sell", 42.0))  # sells ~4 SOL; 4 >= 0.25*16 -> material
    if absorb:
        L.append(c.trade(32.0, "N1", "buy", 44.0))
        L.append(c.trade(38.0, "N2", "buy", 46.0))
        L.append(c.trade(44.0, "N3", "buy", 47.0))  # 3 new wallets, ~5 SOL absorbed
        # keep the tail populated in [50,54] with R held high
        L.append(c.trade(50.0, "N1", "buy", 47.2))
        L.append(c.trade(52.0, "N2", "buy", 47.4))
    else:
        # nobody absorbs; a tiny cluster trade keeps the tail buffer alive, R stays depressed
        L.append(c.trade(50.0, "DEV", "sell", 41.9))
        L.append(c.trade(52.0, "DEV", "sell", 41.8))
    L.append(c.trade(55.0, "X3", "buy", c.v_sol + 0.1))  # past window close -> triggers evaluation
    return L


def main() -> int:
    ok = True

    fires_abs = _play(_build(absorb=True))
    fired = [f for f in fires_abs if not f["control"]]
    ok &= _check("absorbed shock -> exactly one FIRE (control=False)",
                 len(fired) == 1, f"fires={len(fires_abs)} passing={len(fired)}")
    if fired:
        f = fired[0]
        ok &= _check("FIRE carries frozen entry reserves + cluster + coverage",
                     f["entry_line"].get("v_sol") is not None and f["deployer"] == "DEV"
                     and f["coverage_at_fire"] > 10,
                     f"cov={f['coverage_at_fire']:.1f} cluster={f['cluster_wallets']}")
        ok &= _check("FIRE conditions all pass",
                     all(v["ok"] for v in f["conditions"].values()),
                     str({k: v["ok"] for k, v in f["conditions"].items()}))

    fires_no = _play(_build(absorb=False))
    controls = [f for f in fires_no if f["control"]]
    ok &= _check("unabsorbed shock -> CONTROL (control=True), not a PASS",
                 len(controls) == 1 and all(f["control"] for f in fires_no),
                 f"fires={len(fires_no)}")
    if controls:
        ok &= _check("CONTROL fails on absorb and/or capacity",
                     not controls[0]["conditions"]["absorb"]["ok"],
                     str({k: v["ok"] for k, v in controls[0]["conditions"].items()}))

    # immaterial sell (tiny, below the SOL floor) never arms -> no fire at all
    c = _Curve()
    tiny = [c.trade(0.0, "DEV", "buy", 45.0), c.trade(2.0, "E1", "buy", 46.0),
            c.trade(30.0, "DEV", "sell", 45.9),   # ~0.1 SOL sell, below the 0.5 floor
            c.trade(55.0, "X", "buy", 46.0)]
    ok &= _check("immaterial cluster sell (below SOL floor) never arms -> no fire",
                 len(_play(tiny)) == 0)

    # flush (review #2): an ARMED shock whose absorption window elapses with NO further tape line must
    # be force-closed as the honest CONTROL null (else dead/rugged mints are silently dropped).
    from .detector import _MintDetector, DetectorConfig
    c = _Curve()
    armed_lines = [c.trade(0.0, "DEV", "buy", 36.0), c.trade(2.0, "E1", "buy", 40.0),
                   c.trade(4.0, "E2", "buy", 43.0), c.trade(6.0, "E3", "buy", 45.0),
                   c.trade(30.0, "DEV", "sell", 40.0)]   # material sell -> ARMED, then tape goes silent
    det = _MintDetector(cfg=DetectorConfig())
    for ln in armed_lines:
        det.on_line(ln)
    ok &= _check("shock with no follow-on tape stays ARMED", det.state == "ARMED")
    dec = det.flush(now_ts=60.0)                          # past t_shock(30)+window(24)=54
    ok &= _check("flush past the window -> CONTROL (honest null, review #2)",
                 dec is not None and dec["control"] is True, str(dec is not None))
    ok &= _check("flushed detector disarmed", det.state == "WATCH")

    print("\nDETECTOR SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
