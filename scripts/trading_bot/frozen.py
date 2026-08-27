#!/usr/bin/env python3
"""The bridge to the frozen B22B slippage harness. IMPORT ONLY -- never edit the source.

WHY THIS FILE EXISTS
--------------------
`scripts/b22b_slippage_harness.py` is pinned at sha256 `a0f1b4c4...` by
`research/B22B_SLIPPAGE_PREREGISTRATION.json`. Its arithmetic discipline -- integer
micro-dollars, integer nanosecond timestamps, fail-closed refusal, adverse-sign
convention, ATR warm-up refusal -- is the settled definition for this programme, and
re-typing any of it here would create a second definition that can drift from the first.

So the rig CONSUMES the pinned artifact. It does not copy it and it does not edit it.

The hash is verified at import time against the preregistration document, so an edit to
the pinned harness makes the entire trading-bot rig refuse to start rather than silently
running against a mutated definition. `scripts/` is not a Python package, so the load is
by file path via importlib -- the same convention the existing test suite uses.

WHAT B22B DOES **NOT** GIVE US, STATED PLAINLY
----------------------------------------------
B22B is a pinned RULE whose collection stage is deliberately unimplemented. **It has never
been run. There is no measured slippage number in this programme.** What transfers is the
method, not a magnitude. Anything in `costs.py` that needs a magnitude must therefore
carry an explicit, sourced provenance and must refuse to invent one. See
`SlippageProvenance` there.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PINNED_PATH = ROOT / "scripts" / "b22b_slippage_harness.py"
PREREGISTRATION_PATH = ROOT / "research" / "B22B_SLIPPAGE_PREREGISTRATION.json"


class PinBroken(RuntimeError):
    """The frozen artifact no longer matches its preregistered hash."""


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_pinned():
    if not PINNED_PATH.exists():
        raise PinBroken(f"pinned artifact missing: {PINNED_PATH}")
    if not PREREGISTRATION_PATH.exists():
        raise PinBroken(f"preregistration missing: {PREREGISTRATION_PATH}")

    prereg = json.loads(PREREGISTRATION_PATH.read_text())
    expected = prereg["pinned_artifact"]["sha256"]
    actual = _sha256(PINNED_PATH)
    if actual != expected:
        raise PinBroken(
            "scripts/b22b_slippage_harness.py has been modified.\n"
            f"  preregistered sha256: {expected}\n"
            f"  on disk sha256:       {actual}\n"
            "The pinned artifact is frozen by research/B22B_SLIPPAGE_PREREGISTRATION.json "
            "and must not be edited. Restore it; do not update the hash."
        )

    spec = importlib.util.spec_from_file_location("_b22b_pinned", PINNED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, actual


b22b, PINNED_SHA256 = _load_pinned()

# ---------------------------------------------------------------------------
# Re-exported frozen definitions. Every name below is B22B's, not ours.
# ---------------------------------------------------------------------------

Refused = b22b.Refused                       # absence is refusal, never zero

MICROS = b22b.MICROS
to_micros = b22b.to_micros                   # THE float boundary at ingest
to_shares = b22b.to_shares

parse_rfc3339_ns = b22b.parse_rfc3339_ns     # integer ns; datetime.timestamp() loses resolution
et_offset_hours = b22b.et_offset_hours       # per-day DST, never one offset for a whole run
session_bound_ns = b22b.session_bound_ns
SESSION_OPEN = b22b.SESSION_OPEN
SESSION_CLOSE = b22b.SESSION_CLOSE

percentile_by_index = b22b.percentile_by_index   # integer index, no interpolation
distribution_summary = b22b.distribution_summary  # sum+count, never a mean

true_range_micros = b22b.true_range_micros   # refuses without a prior close
atr_micros = b22b.atr_micros                 # ATR(n) needs n+1 bars, not n
r_unit_micros = b22b.r_unit_micros           # R = 10% of ATR
ATR_LOOKBACK_DAYS = b22b.ATR_LOOKBACK_DAYS
STOP_LOSS_ATR_PCT = b22b.STOP_LOSS_ATR_PCT

LATENCY_LADDER_MS = b22b.LATENCY_LADDER_MS   # 0 ms is the backtest's fiction, kept to show the gap

# Slippage decision thresholds, in basis points of R, fixed by B22B before any data existed.
EDGE_AT_FILTER_R_BP = b22b.EDGE_AT_FILTER_R_BP
EDGE_AT_BEST_BUCKET_R_BP = b22b.EDGE_AT_BEST_BUCKET_R_BP
IMPAIRED_R_BP = b22b.IMPAIRED_R_BP
NEGLIGIBLE_R_BP = b22b.NEGLIGIBLE_R_BP

ALPACA_DATA_HOST = b22b.ALPACA_DATA_HOST
API_PAGE_LIMIT = b22b.API_PAGE_LIMIT


def pin_report() -> dict:
    """Provenance block for a run report: what was consumed, and at what hash."""
    return {
        "pinned_artifact": "scripts/b22b_slippage_harness.py",
        "sha256": PINNED_SHA256,
        "verified_against": "research/B22B_SLIPPAGE_PREREGISTRATION.json",
        "consumed_not_copied": True,
        "measurement_status": (
            "B22B is a pinned RULE whose collection stage is unimplemented. It has NEVER been "
            "run. No slippage magnitude has been measured by this programme; only the method "
            "transfers."
        ),
    }


__all__ = [
    "b22b", "PINNED_SHA256", "PinBroken", "pin_report",
    "Refused", "MICROS", "to_micros", "to_shares",
    "parse_rfc3339_ns", "et_offset_hours", "session_bound_ns", "SESSION_OPEN", "SESSION_CLOSE",
    "percentile_by_index", "distribution_summary",
    "true_range_micros", "atr_micros", "r_unit_micros",
    "ATR_LOOKBACK_DAYS", "STOP_LOSS_ATR_PCT", "LATENCY_LADDER_MS",
    "EDGE_AT_FILTER_R_BP", "EDGE_AT_BEST_BUCKET_R_BP", "IMPAIRED_R_BP", "NEGLIGIBLE_R_BP",
    "ALPACA_DATA_HOST", "API_PAGE_LIMIT",
]
