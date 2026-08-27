#!/usr/bin/env python3
"""Held-out scoring for batch-2 calendar formulas. Run ONLY after the design sweep froze.

Usage:  python3 cal_holdout2.py NAME [NAME ...]
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.trading_bot.cal_sweep import OUT  # noqa: E402
from scripts.trading_bot.cal_sweep2 import Family2, build_funding_threshold  # noqa: E402


def main():
    names = sys.argv[1:]
    if not names:
        print("give formula names")
        return
    fam = Family2()
    fam.fund_thr = build_funding_threshold(fam)
    known = {r[0] for r in fam.reg}
    out = []
    for nm in names:
        if nm not in known:
            print("unknown:", nm)
            continue
        d = fam.detail(nm, "design")
        h = fam.detail(nm, "holdout")
        out.append(dict(name=nm, desc=d["desc"], dataset=d["dataset"], design=d, holdout=h))
        print(f"\n=== {nm}  [{d['dataset']}]\n    {d['desc']}")
        for tag, r in (("DESIGN ", d), ("HOLDOUT", h)):
            print(f"  {tag} Sharpe {r['sharpe']:+.3f} | ann {r['ann_return_pct']:+.2f}% "
                  f"| vol {r['ann_vol_pct']:.2f}% | maxDD {r['max_drawdown_pct']:.2f}% "
                  f"| {r['years']:.1f}y | {r['n_active_periods']} active periods")
    p = OUT / "SWEEP_calendar_session_batch2_holdout.json"
    p.write_text(json.dumps(out, indent=1))
    print("\nwrote", p)


if __name__ == "__main__":
    main()
