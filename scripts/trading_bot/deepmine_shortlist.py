#!/usr/bin/env python3
"""Apply §5 of DEEPMINE_etf_structural_rv_PREREGISTRATION.md mechanically.

This file exists so the shortlist is produced by the frozen rule rather than by a human eye
that has just read the design table. It refuses to run unless the pre-registration still
hashes to the value recorded before the design sweep.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
KEY = "etf_structural_rv"
PREREG = OUT / f"DEEPMINE_{KEY}_PREREGISTRATION.md"
PREREG_SHA = "1a141a67ae5e30102a51aeaaa00dede7a75f3310be227b67bbf6c0feb217f468"

MAX_TURNOVER = 4.0
MIN_DAYS = 500
MAX_UNSHORTABLE = 0.10
CAP = 6
FLOOR_N = 3


def main():
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA:
        raise SystemExit(f"pre-registration hash changed: {got} != {PREREG_SHA}. Refusing.")
    design = json.loads((OUT / f"DEEPMINE_{KEY}_design.json").read_text())
    b95 = design["noise_bar"]["bootstrap"]["p95"]
    rows = design["results"]
    ok = [r for r in rows
          if r["sharpe_net"] == r["sharpe_net"]
          and r["sharpe_net"] > b95
          and r["daily_turnover"] <= MAX_TURNOVER
          and r["n_days"] >= MIN_DAYS
          and r["unshortable_short_share"] <= MAX_UNSHORTABLE]
    ok.sort(key=lambda r: -r["sharpe_net"])
    shortlist = ok[:CAP]
    below = False
    if len(shortlist) < FLOOR_N:
        below = True
        rest = sorted(rows, key=lambda r: -(r["sharpe_net"] if r["sharpe_net"] == r["sharpe_net"] else -9))
        names = {r["name"] for r in shortlist}
        for r in rest:
            if len(shortlist) >= FLOOR_N:
                break
            if r["name"] not in names:
                shortlist.append(r)
                names.add(r["name"])
    payload = {
        "key": KEY,
        "prereg_sha256": PREREG_SHA,
        "bootstrap_p95_noise_bar": b95,
        "gates": {"sharpe_net_gt": b95, "daily_turnover_le": MAX_TURNOVER,
                  "n_days_ge": MIN_DAYS, "unshortable_short_share_le": MAX_UNSHORTABLE,
                  "cap": CAP},
        "n_passing_all_gates": len(ok),
        "below_noise_bar": below,
        "below_noise_bar_note": (
            "Fewer than three configs cleared the gates, so §5's floor carried the top three by "
            "design sharpe_net to the held-out window anyway. Running them is NOT a promotion."
            if below else "Not applicable: the gates produced at least three configs."),
        "shortlist": [{"name": r["name"], "kind": r["kind"], "design_sharpe_net": r["sharpe_net"],
                       "design_sharpe_gross": r["sharpe_gross"],
                       "daily_turnover": r["daily_turnover"],
                       "unshortable_short_share": r["unshortable_short_share"]}
                      for r in shortlist],
    }
    p = OUT / f"DEEPMINE_{KEY}_SHORTLIST.json"
    p.write_text(json.dumps(payload, indent=1))
    print(json.dumps(payload, indent=1))
    print("\n--only " + ",".join(r["name"] for r in shortlist), flush=True)


if __name__ == "__main__":
    main()
