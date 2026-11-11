"""nulls.py — SUPERSEDED. The v1 draft's circular-shift null now lives in `mtest.py` (DESIGN_v2 §3.3).

This file is a shim kept so that an old import fails loudly at the CALL, not silently at the import:
`circular_shift_null` here IS `mtest.circular_shift_null`, whose signature changed in v2
(`window=` and `seed=` are required; `borrow_bp_year` / `fill_prices` are gone — see
`hold_cost_long_bp_year` / `hold_cost_short_bp_year` and `exec_prices` / `extra_lag`). A v1-style call
raises TypeError. New code must import from `scripts.factory.mtest`.

What changed relative to the v1 draft (kept in the builder's report, summarised here):
  * positions are rolled INSIDE the scoring window and statistics are computed only there (the draft
    rolled the full panel, so flat warm-up rows rotated into the scored rows);
  * each replicate carries the costs the real book paid (the draft re-derived costs from the rolled
    targets, adding an artificial trade at the seam);
  * the empirical p-value uses the (1 + #)/(1 + n_rep) correction.
"""
from __future__ import annotations

import warnings

from .mtest import circular_shift_null

warnings.warn(
    "scripts.factory.nulls is superseded by scripts.factory.mtest (DESIGN_v2 §3.3); import from mtest",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["circular_shift_null"]
