#!/usr/bin/env python3
"""Read-only PAC terminal-prefix census on the burned PumpPortal tape cache.

This reports signal availability only.  It does not replay returns and must not be used to change the
already-frozen PAC thresholds. Duplicate provider-second timestamps receive a deterministic +1ns ordering
for this diagnostic only, so the output is not forward/executable evidence.
"""
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

from . import ecr
from . import pac_detector as pac
from . import secondary_sell_detector as ss


ROOT = pathlib.Path(__file__).resolve().parents[3]
TAPE = ROOT / "research" / "data" / "memebot_cache" / "tape"


def _events(path: pathlib.Path):
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if all(item.get(key) is not None for key in ("v_sol", "v_tokens", "ts")):
            rows.append(item)
    events, previous, last_ns = [], None, -1
    for item in rows:
        kernel = ecr.reserves_from_tape({
            "v_sol": item["v_sol"], "v_tokens": item["v_tokens"],
            "pool": item.get("pool", "pump"),
        })
        post = SimpleNamespace(real_quote=int(kernel["real_quote"]))
        pre = previous or post
        observed = max(int(float(item["ts"]) * 1_000_000_000), last_ns + 1)
        events.append(SimpleNamespace(pre_state=pre, post_state=post,
                                      observation_unix_nanos=observed))
        previous, last_ns = post, observed
    return tuple(events)


def census() -> dict:
    files = [path for path in TAPE.glob("*.jsonl") if not path.name.startswith("_")]
    valid = old_ss = pac_count = 0
    spans, withdrawals = [], []
    for path in files:
        try:
            events = _events(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if len(events) <= 8:
            continue
        valid += 1
        if ss.detector(events, 8):
            old_ss += 1
        evidence = pac.detector(events, 8)
        if not evidence:
            continue
        pac_count += 1
        metrics = pac.pac_metrics(events, evidence)
        spans.append((events[evidence[-1]].observation_unix_nanos
                      - events[evidence[0]].observation_unix_nanos) / 1_000_000_000)
        withdrawals.append(min(metrics["withdrawal_1_lamports"],
                               metrics["withdrawal_2_lamports"]) / 1_000_000_000)

    def triple(values):
        return [] if not values else [min(values), sorted(values)[len(values) // 2], max(values)]

    return {
        "scope": "BURNED terminal-prefix feasibility only; no returns; no threshold selection",
        "ordering_caveat": "duplicate provider-second timestamps receive deterministic +1ns ties",
        "files": len(files),
        "valid_prefixes": valid,
        "secondary_sell_terminal_signals": old_ss,
        "pac_terminal_signals": pac_count,
        "pac_terminal_signal_rate": pac_count / valid if valid else None,
        "pac_span_seconds_min_median_max": triple(spans),
        "pac_min_withdraw_sol_min_median_max": triple(withdrawals),
    }


if __name__ == "__main__":
    print(json.dumps(census(), indent=2, sort_keys=True))
