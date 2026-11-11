"""Factory data layer (builder B3).

    from scripts.factory.data import load_lane
    panel = load_lane("FX")          # -> scripts.factory.panel.PanelBundle, from parquet, no network

Lanes: FX, FX-EXEC, FX-FRED, MACRO, CRYPTO-PERP, CRYPTO-SPOT (see research/factory/data/<LANE>/manifest.json).
"""
from .panelio import LANES, load_lane, read_manifest

__all__ = ["LANES", "load_lane", "read_manifest"]
