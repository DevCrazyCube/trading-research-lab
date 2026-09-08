#!/usr/bin/env python3
"""AFTERSHOCK V3 — QUOTE-HARVEST detector. PAPER, read-only.

Entry = V2's net-replacement machinery with the entry-flow-veto REMOVED (V2 proved it redundant with
stabilization) plus a break-even feasibility gate: the exact full-position round-trip quote at the fire
instant must clear a floor, else the entry is doomed on cost and is not taken. V2's detector is reused
and left untouched; V3 only adds the break-even gate on top.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ecr
from .detector_v2 import DetectorV2, DetectorV2Config, _MintDetectorV2


@dataclass(frozen=True)
class DetectorV3Config(DetectorV2Config):
    breakeven_gate: bool = True
    breakeven_min_quote: float = 0.90


@dataclass
class _MintDetectorV3(_MintDetectorV2):
    def _evaluate(self, line: dict) -> dict:
        dec = super()._evaluate(line)   # V2 gates (veto non-strict -> always ok in V3)
        q = self.cfg.q_sol
        entry_reserves = {"v_sol": line.get("v_sol"), "v_tokens": line.get("v_tokens"),
                          "pool": line.get("pool", "pump")}
        rt = ecr.ecr_roundtrip(entry_reserves, line, q)
        entry_quote = 0.0 if rt.get("unexitable") else 1.0 + float(rt["stressed_net_return"])
        be_ok = (not self.cfg.breakeven_gate) or (entry_quote >= self.cfg.breakeven_min_quote)
        fired = (not dec["control"]) and be_ok
        dec["control"] = not fired
        dec["conditions"]["breakeven"] = {"ok": be_ok, "entry_quote": round(entry_quote, 4),
                                          "min": self.cfg.breakeven_min_quote}
        return dec


class DetectorV3(DetectorV2):
    def __init__(self, cfg: DetectorV3Config) -> None:
        self.cfg = cfg
        self._mints: dict = {}

    def on_line(self, line: dict):
        mint = line.get("mint")
        if mint is None:
            return None
        d = self._mints.get(mint)
        if d is None:
            d = self._mints[mint] = _MintDetectorV3(cfg=self.cfg)
        return d.on_line(line)


def detector_v3(spec: dict) -> DetectorV3:
    """Build the V3 detector (veto always off; break-even gate from the frozen spec)."""
    return DetectorV3(DetectorV3Config.from_spec(spec, veto_strict=False))
