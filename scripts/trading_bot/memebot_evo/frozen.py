#!/usr/bin/env python3
"""Load + VERIFY the frozen MEMEBOT_EVO_V2 pre-registration, refusing if the rules moved OR if the
running engine constants no longer match the frozen block (the V1 failure: prereg said 24/4, code ran
60/3). Two guards, one source of truth:
  1. recompute sha256(EVO_V2_PREREGISTRATION.md) vs the pinned hash in EVO_V2_FROZEN.json;
  2. constant-drift: every engine.py module-level constant in the frozen block must equal the frozen value.
A rule editable after results print is not frozen; an improvement is a NEW frozen instrument, never an edit.
"""
from __future__ import annotations

import hashlib
import json
import pathlib


class RefusedEvo(Exception):
    """Freeze/consistency violation: refuse rather than run an unfrozen or drifted evo search."""


HERE = pathlib.Path(__file__).resolve().parent
FROZEN_JSON = HERE / "EVO_V2_FROZEN.json"
PREREG_MD = HERE / "EVO_V2_PREREGISTRATION.md"


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_evo() -> dict:
    for p in (FROZEN_JSON, PREREG_MD):
        if not p.exists():
            raise RefusedEvo(f"{p.name} is missing; the frozen EVO_V2 cannot be loaded")
    spec = json.loads(FROZEN_JSON.read_text())
    if spec.get("instrument_id") != "MEMEBOT_EVO_V2":
        raise RefusedEvo(f"{FROZEN_JSON.name} declares instrument_id {spec.get('instrument_id')!r}")
    expected = spec.get("preregistration_sha256")
    actual = _sha256_file(PREREG_MD)
    if not expected or actual != expected:
        raise RefusedEvo(
            f"{PREREG_MD.name} changed since the freeze.\n  frozen expects: {expected}\n"
            f"  on disk:        {actual}\nRestore the document. Do NOT update the hash: an improvement "
            "is a NEW frozen instrument, never an edit to a running one.")
    # constant-drift: the engine's live constants MUST equal the frozen block (the V1 divergence guard).
    from . import engine
    for name, frozen_val in (spec.get("constants") or {}).items():
        live = getattr(engine, name, None)
        if live != frozen_val:
            raise RefusedEvo(
                f"engine.{name} = {live!r} but EVO_V2_FROZEN.json pins {frozen_val!r}; the code drifted "
                "from the pre-registration. Reconcile (source the engine constant from the frozen block, "
                "or freeze a new instrument) before running the forward search.")
    spec["_preregistration_sha256_verified"] = actual
    return spec
