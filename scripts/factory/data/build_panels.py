"""Rebuild the lanes from the raw files on disk (offline; no network).

    research/factory/.venv/bin/python -m scripts.factory.data.build_panels            # every lane whose raw data exists
    research/factory/.venv/bin/python -m scripts.factory.data.build_panels FX MACRO   # selected lanes

Raw downloads are separate, explicit steps (see each module's docstring):
    python -m scripts.factory.data.sources fred ecb bis alpaca          (short, foreground)
    python -m scripts.factory.data.binance_dl perp-daily|spot-daily     (detached)
    python -m scripts.factory.data.crypto_build plan-perp|plan-spot
    python -m scripts.factory.data.binance_dl perp-hourly|spot-hourly   (detached, ~30 min each)
    python -m scripts.factory.data.crypto_build holes-perp|holes-spot
    python -m scripts.factory.data.binance_dl perp-fill|spot-fill       (detached)
"""
from __future__ import annotations

import sys

from .common import RAW, utc_now
from .panelio import LANES, write_index


def main(argv=None) -> int:
    want = list(argv or sys.argv[1:]) or list(LANES)
    for lane in want:
        if lane not in LANES:
            raise SystemExit(f"unknown lane {lane!r}; known: {LANES}")
    for lane in want:
        if lane in ("FX", "FX-EXEC", "FX-FRED"):
            from . import fx
            {"FX": fx.build_fx, "FX-EXEC": fx.build_fx_exec, "FX-FRED": fx.build_fx_fred}[lane]()
        elif lane == "MACRO":
            from .macro import build_macro
            build_macro()
        elif lane in ("CRYPTO-PERP", "CRYPTO-SPOT"):
            market = "perp" if lane == "CRYPTO-PERP" else "spot"
            src = RAW / ("binance/futures_um" if market == "perp" else "binance/spot")
            if not (src / "_stage_hourly_DONE.json").exists():
                print(f"{utc_now()} {lane}: hourly download not finished ({src / '_stage_hourly_DONE.json'} missing) - skipped",
                      flush=True)
                continue
            from . import crypto_lanes
            (crypto_lanes.build_perp if market == "perp" else crypto_lanes.build_spot)()
    print(f"{utc_now()} index -> {write_index()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
