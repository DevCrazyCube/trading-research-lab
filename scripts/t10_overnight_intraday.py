#!/usr/bin/env python3
"""T10 -- overnight-vs-intraday premium harvesting. Runner for the frozen pre-registration.

    research/trading_bot/T10_PREREGISTRATION.md
    sha256 7f66195125718298c5eb545ae936e9bac89ca537482009b2e8e531a75bbb6d99
    frozen 2026-08-17T09:11:58Z, BEFORE any return in this file was ever evaluated.

    python3 scripts/t10_overnight_intraday.py design   # 2016-02-01 -> 2021-12-31, 8 trials
    python3 scripts/t10_overnight_intraday.py test     # 2022-01-03 -> 2026-08-14, ONCE

`test` REFUSES to run unless T10_FROZEN_CONFIG.json already exists, so it cannot select a
configuration on the spot. Everything statistical comes from the T2 harness
(`scripts/trading_bot/stats.py`); every cost comes from `scripts/trading_bot/costs.py`, the
T6-corrected PER-SIDE model, including M0's measured auction leg. Calendar, universe, auction
prints and corporate-action dates come from `scripts/t3_pressure_reversal.py` unchanged.
"""
from __future__ import annotations

import datetime
import json
import math
import pathlib
import sys
from fractions import Fraction

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import t3_pressure_reversal as t3                                          # noqa: E402
from trading_bot import stats                                              # noqa: E402
from trading_bot.costs import (CostComponent, CostModel, SlippageProvenance,  # noqa: E402
                               measured_auction_leg, measured_borrow_annual,
                               split_turnover)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "trading_bot"
FROZEN = OUT / "T10_FROZEN_CONFIG.json"
PREREG_SHA = "7f66195125718298c5eb545ae936e9bac89ca537482009b2e8e531a75bbb6d99"

START, END = "2016-02-01", "2026-08-14"
DESIGN_END, TEST_START = "2021-12-31", "2022-01-03"
SEED = 20260817

SEC31_FRACTION = float(Fraction(278, 10 ** 7))   # 0.278 bp of SALE notional (top of 2016-26)
TAF_PER_SHARE = 0.000166                         # FINRA TAF, $/share
H_DESIGN_BP = 1.13                               # T3 first-party median quoted half-spread
H_TEST_BP = 1.43
M0_TIER = "A_rank_1_50"                          # dearest of the three LIQUID M0 tiers

TRIALS = [                                       # pre-registration section 6 -- and nothing else
    ("A1", "A", {"instrument": "SPY"}),
    ("A2", "A", {"top_n": 100}),
    ("A3", "A", {"top_n": 300}),
    ("A4", "A", {"top_n": 500}),
    ("B1", "B", {"top_n": 500, "K": 21, "cut": 0.10}),
    ("B2", "B", {"top_n": 500, "K": 21, "cut": 0.20}),
    ("B3", "B", {"top_n": 500, "K": 63, "cut": 0.10}),
    ("B4", "B", {"top_n": 500, "K": 63, "cut": 0.20}),
]


# ---------------------------------------------------------------------------
# cost model -- T6-corrected, PER SIDE, both sides named, M0 auction leg
# ---------------------------------------------------------------------------

def cost_model(half_spread_bp: float) -> CostModel:
    """One rung of the ladder. Rung 0 IS the M0-measured auction rail, not an assumption."""
    hs = Fraction(str(half_spread_bp))
    _, entry_extra = measured_auction_leg("entry", M0_TIER)
    _, exit_extra = measured_auction_leg("exit", M0_TIER)
    if hs == 0:
        entry_half, _ = measured_auction_leg("entry", M0_TIER)
        exit_half, _ = measured_auction_leg("exit", M0_TIER)
    else:
        src = (
            f"STRESS RUNG, not a measurement of an auction: {float(hs)} bp of half-spread on "
            "this leg, as a multiple of T3's first-party measured median quoted half-spread in "
            "this exact top-500-ADV universe (1.13 bp 2016-2021, 1.43 bp 2022-2026, ~20,000 "
            "symbol-days per period). This rung prices M0's UNPERFORMED live half -- the "
            "MOC/MOO order not joining the cross -- being wrong. At 4.0 of notional traded per "
            "session it is the rung that decides this candidate."
        )
        entry_half = CostComponent("entry_half_spread", hs, "bp of notional",
                                   SlippageProvenance.STRESS_LADDER, src)
        exit_half = CostComponent("exit_half_spread", hs, "bp of notional",
                                  SlippageProvenance.STRESS_LADDER, src)
    return CostModel(
        entry_half_spread=entry_half,
        entry_extra_slippage=entry_extra,
        exit_half_spread=exit_half,
        exit_extra_slippage=exit_extra,
        commission_per_share=CostComponent(
            "commission_per_share", Fraction(0), "micro-dollars per share",
            SlippageProvenance.BROKER_SCHEDULE,
            "Alpaca charges $0/share. The FINRA TAF is a SALE-side per-share fee and SEC "
            "Section 31 is ad valorem on sale proceeds; neither fits this side-agnostic field "
            "without mis-charging the buy legs, so both are charged explicitly in the runner "
            "against exact per-auction turnover -- TAF on EVERY share traded (a deliberate ~2x "
            "over-charge, the conservative direction) and Section 31 on sale notional only."),
        borrow_annual=measured_borrow_annual("etb_general_collateral"),
    )


# ---------------------------------------------------------------------------
# panel -- pre-registration section 4
# ---------------------------------------------------------------------------

def build_panel():
    cal = t3.calendar()
    all_days = [r["date"] for r in cal]
    close_by = {r["date"]: r["close"] for r in cal}
    uni500 = t3.build_universe(500)
    union = sorted({s for v in uni500.values() for s in v} | {"SPY"})
    auct = t3.auctions(union)
    ca = {k: set(v) for k, v in t3.corporate_action_dates(union).items()}

    sessions = [d for d in all_days if "2016-01-04" <= d <= END]
    prev = {sessions[i]: sessions[i - 1] for i in range(1, len(sessions))}

    def row(sym, p, day):
        a0, a1 = auct.get(f"{sym}|{p}"), auct.get(f"{sym}|{day}")
        if not a0 or "c" not in a0 or not a1 or "o" not in a1 or "c" not in a1:
            return None
        cad = ca.get(sym, ())
        if day in cad or p in cad:
            return "ca"
        c0, o1, c1 = a0["c"], a1["o"], a1["c"]
        if min(c0, o1, c1) <= 0:
            return None
        return (o1 / c0 - 1.0, c1 / o1 - 1.0, c0, o1, c1)

    panel, spy, dropped = {}, {}, {}

    def bump(k):
        dropped[k] = dropped.get(k, 0) + 1

    for day in sessions[1:]:
        if day < START:
            continue
        p = prev[day]
        if close_by.get(day) != "16:00" or close_by.get(p) != "16:00":
            bump("session_early_close"); continue
        syms = uni500.get(day[:7], [])
        if not syms:
            bump("session_no_universe"); continue
        keep, on, idr, pc0, po, pc = [], [], [], [], [], []
        for sym in syms:
            r = row(sym, p, day)
            if r is None:
                bump("symday_missing_print"); continue
            if r == "ca":
                bump("symday_corporate_action"); continue
            keep.append(sym)
            on.append(r[0]); idr.append(r[1]); pc0.append(r[2]); po.append(r[3]); pc.append(r[4])
        if not keep:
            continue
        on = np.asarray(on); idr = np.asarray(idr)
        panel[day] = {"s": keep, "d": on - idr, "on": on, "id": idr,
                      "pc0": np.asarray(pc0), "po": np.asarray(po), "pc": np.asarray(pc)}
        r = row("SPY", p, day)
        if r not in (None, "ca"):
            spy[day] = {"on": r[0], "id": r[1], "pc0": r[2], "po": r[3], "pc": r[4]}
    return panel, spy, dropped, prev


# ---------------------------------------------------------------------------
# the two families -- pre-registration section 5
# ---------------------------------------------------------------------------

_TOPSETS: dict[int, dict] = {}


def top_sets(top_n):
    if top_n not in _TOPSETS:
        _TOPSETS[top_n] = {m: set(v) for m, v in t3.build_universe(top_n).items()}
    return _TOPSETS[top_n]


def books(panel, spy, family, cfg, day_hi=None, day_lo=None):
    """Yield one scored session at a time.

    (day, syms, w_on, gross, (px_prev_close, px_open, px_close), d_sorted_by_signal, m, sel)

    `w_on` is the OVERNIGHT weight vector; the intraday book is exactly -w_on. `d_sorted` is
    the day's cross-section of paired differences ordered LONG-first (descending signal), which
    is the layout `t3.label_permutation_fast` expects. Signal history is accumulated over every
    day <= the scored day and never over a later one.
    """
    hist: dict[str, list[float]] = {}
    tset = top_sets(cfg["top_n"]) if family == "A" and "top_n" in cfg else None
    for day in sorted(panel):
        if day_hi and day > day_hi:
            break
        row = panel[day]
        scored = (not day_lo) or day >= day_lo

        if family == "B":
            K, cut, need = cfg["K"], cfg["cut"], math.ceil(0.6 * cfg["K"])
            # `extra_lag` is 0 for the FROZEN configuration and is never used by it. It exists
            # only for the declared-deviation diagnostic in T10_RESULT.md section 4b: the frozen
            # signal's most recent term uses C(i,t-1), the very closing print the overnight leg
            # is entered at, which an MOC due at 15:50 cannot see. extra_lag=1 drops it.
            lag = cfg.get("extra_lag", 0)
            sig, idx = [], []
            for j, sym in enumerate(row["s"]):
                h = hist.get(sym)
                if lag:
                    h = h[:-lag] if h and len(h) > lag else None
                if h is not None and len(h) >= need:
                    w = h[-K:]
                    sig.append(sum(w) / len(w))
                    idx.append(j)
            if scored and len(idx) >= 20:
                idx = np.asarray(idx)[np.argsort(-np.asarray(sig), kind="stable")]  # desc signal
                m = max(1, int(round(cut * idx.size)))
                sel = np.concatenate([idx[:m], idx[-m:]])          # long block, then short block
                w = np.concatenate([np.full(m, 0.5 / m), np.full(m, -0.5 / m)])
                dd = row["d"][sel]
                gross = float(0.5 * dd[:m].mean() - 0.5 * dd[m:].mean())
                yield (day, [row["s"][k] for k in sel], w, gross,
                       (row["pc0"][sel], row["po"][sel], row["pc"][sel]), row["d"][idx], m, sel)
        elif cfg.get("instrument") == "SPY":
            if scored and day in spy:
                r = spy[day]
                yield (day, ["SPY"], np.array([1.0]), r["on"] - r["id"],
                       (np.array([r["pc0"]]), np.array([r["po"]]), np.array([r["pc"]])),
                       None, None, None)
        else:
            allowed = tset.get(day[:7], set())
            sel = np.asarray([j for j, s in enumerate(row["s"]) if s in allowed], dtype=int)
            if scored and sel.size >= 20:
                n = sel.size
                yield (day, [row["s"][k] for k in sel], np.full(n, 1.0 / n),
                       float(row["d"][sel].mean()),
                       (row["pc0"][sel], row["po"][sel], row["pc"][sel]), None, None, sel)

        if family == "B":                       # updated AFTER scoring: d(i,t) is never visible
            for j, sym in enumerate(row["s"]):
                h = hist.setdefault(sym, [])
                h.append(float(row["d"][j]))
                if len(h) > 63:
                    del h[0]


def _auction_cost(prev_w, new_w, prev_px, new_px, ef, xf, charge_reg):
    """Exact per-name turnover through ONE auction, charged PER SIDE (T6) + regulatory."""
    cost = traded_tot = sold_tot = 0.0
    for sym in set(prev_w) | set(new_w):
        a, b = prev_w.get(sym, 0.0), new_w.get(sym, 0.0)
        if a == b:
            continue
        entry, exit_ = split_turnover(Fraction(a).limit_denominator(10 ** 9),
                                      Fraction(b).limit_denominator(10 ** 9))
        cost += float(entry) * ef + float(exit_) * xf
        traded = abs(b - a)
        sold = max(0.0, a - b)
        traded_tot += traded
        sold_tot += sold
        if charge_reg:
            px = new_px.get(sym) or prev_px.get(sym)
            cost += sold * SEC31_FRACTION
            cost += traded * TAF_PER_SHARE / px       # TAF on EVERY share: deliberate ~2x
    return cost, traded_tot, sold_tot


def run_config(panel, spy, family, cfg, *, half_spread_bp, prev_session,
               day_hi=None, day_lo=None, charge_reg=True, charge_borrow=True):
    model = cost_model(half_spread_bp)
    ef = float(model.entry_spread_and_slippage_fraction())
    xf = float(model.exit_spread_and_slippage_fraction())
    borrow = float(model.borrow_annual.value)

    dates, gross_l, net_l, cost_l, on_l, id_l, members = [], [], [], [], [], [], []
    traded_l, sold_l = [], []
    prev_w, prev_px = {}, {}
    for day, syms, w, gross, px, dsorted, m, sel in books(panel, spy, family, cfg,
                                                          day_hi, day_lo):
        pc0, po, pc = px
        w_on = {s: float(x) for s, x in zip(syms, w)}
        w_id = {s: -float(x) for s, x in zip(syms, w)}
        px_c0 = {s: float(x) for s, x in zip(syms, pc0)}
        px_o = {s: float(x) for s, x in zip(syms, po)}
        px_c = {s: float(x) for s, x in zip(syms, pc)}

        c1, t1, s1 = _auction_cost(prev_w, w_on, prev_px, px_c0, ef, xf, charge_reg)
        c2, t2, s2 = _auction_cost(w_on, w_id, px_o, px_o, ef, xf, charge_reg)
        cost = c1 + c2

        if charge_borrow:
            short_on = sum(-v for v in w_on.values() if v < 0)
            if short_on:
                p = prev_session.get(day)
                held = (datetime.date.fromisoformat(day)
                        - datetime.date.fromisoformat(p)).days if p else 1
                cost += short_on * borrow * max(1, held) / 365.0

        dates.append(day)
        gross_l.append(gross)
        cost_l.append(cost)
        net_l.append(gross - cost)
        traded_l.append(t1 + t2)
        sold_l.append(s1 + s2)
        if family == "A":
            if sel is None:
                on_l.append(spy[day]["on"]); id_l.append(spy[day]["id"])
            else:
                on_l.append(float(panel[day]["on"][sel].mean()))
                id_l.append(float(panel[day]["id"][sel].mean()))
        if dsorted is not None:
            members.append((day, dsorted.tolist(), m))
        prev_w, prev_px = w_id, px_c

    return {"dates": dates, "gross": gross_l, "net": net_l, "cost": cost_l,
            "traded": traded_l, "sold": sold_l, "members": members,
            "on": on_l, "id": id_l}


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def obs_per_year(dates):
    a = datetime.date.fromisoformat(dates[0])
    b = datetime.date.fromisoformat(dates[-1])
    return len(dates) / ((b - a).days / 365.25)


def summarise(series, label, ppy):
    m = stats.moments(series)
    eq, v = [1.0], 1.0
    for r in series:
        v *= (1.0 + r)
        eq.append(v)
    sr = m["mean"] / m["sd"] if m["sd"] else 0.0
    return {"label": label, "n": m["n"], "mean_bp": m["mean"] * 1e4, "sd_bp": m["sd"] * 1e4,
            "t": m["mean"] / (m["sd"] / math.sqrt(m["n"])) if m["sd"] else 0.0,
            "sharpe_per_obs": sr, "ann_sharpe": sr * math.sqrt(ppy),
            "ann_return": v ** (ppy / m["n"]) - 1.0,
            "max_drawdown": stats.max_drawdown(eq)["max_drawdown"],
            "skew": m["skew"], "kurtosis_non_excess": m["kurtosis"]}


def perm_family_A(gross, cost, trials=10_000, seed=SEED):
    """Session-label exchangeability: independent sign flip of each session's difference.

    The cost schedule is deterministic and is re-charged identically under every draw, so the
    null and the observed statistic differ by the same constant and the p-value is exact.
    """
    rng = np.random.default_rng(seed)
    g, c = np.asarray(gross), np.asarray(cost)
    obs = float((g - c).mean())
    null = np.empty(trials)
    step = 500
    for lo in range(0, trials, step):
        hi = min(trials, lo + step)
        signs = rng.integers(0, 2, size=(hi - lo, g.size)) * 2 - 1
        null[lo:hi] = (signs * g).mean(axis=1) - c.mean()
    ge = int((null >= obs).sum())
    return {"instrument": "session-label sign flip (paired randomisation)",
            "observed_mean": obs, "trials": trials, "seed": seed,
            "p_right_tail": (ge + 1) / (trials + 1),
            "null_mean": float(null.mean()), "null_sd": float(null.std(ddof=1)),
            "null_p95": float(np.quantile(null, 0.95))}


def perm_family_B(members, cost_mean, trials=10_000, seed=SEED):
    """Cross-sectional label permutation -- T3's instrument, identical statistic."""
    out = t3.label_permutation_fast(members, trials=trials, seed=seed)
    out["instrument"] = "cross-sectional label permutation (which name held which rank)"
    out["cost_mean_subtracted_from_both_sides"] = cost_mean
    return out


# ---------------------------------------------------------------------------
# design / test drivers
# ---------------------------------------------------------------------------

LADDER = ("frictionless", 0.0, 0.5, 1.0, 2.0, 4.0)


def _panel_counts(panel, spy, dropped):
    days = sorted(panel)
    dz = [d for d in days if d <= DESIGN_END]
    tz = [d for d in days if d >= TEST_START]
    return {"sessions_kept": len(days), "sessions_design": len(dz), "sessions_test": len(tz),
            "first": days[0], "last": days[-1],
            "symbol_days_design": int(sum(len(panel[d]["s"]) for d in dz)),
            "symbol_days_test": int(sum(len(panel[d]["s"]) for d in tz)),
            "spy_sessions_design": sum(1 for d in dz if d in spy),
            "spy_sessions_test": sum(1 for d in tz if d in spy),
            "dropped": dropped}


def design():
    panel, spy, dropped, prev_session = build_panel()
    counts = _panel_counts(panel, spy, dropped)
    print(json.dumps(counts, indent=2), flush=True)

    rows = []
    for name, family, cfg in TRIALS:
        r = run_config(panel, spy, family, cfg, half_spread_bp=0.0,
                       prev_session=prev_session, day_hi=DESIGN_END)
        ppy = obs_per_year(r["dates"])
        s = summarise(r["net"], f"{name} net", ppy)
        g = summarise(r["gross"], f"{name} gross", ppy)
        rows.append({"trial": name, "family": family, "cfg": cfg, "obs_per_year": ppy,
                     "net": s, "gross": g,
                     "mean_cost_bp": float(np.mean(r["cost"]) * 1e4),
                     "mean_traded_notional": float(np.mean(r["traded"])),
                     "mean_sold_notional": float(np.mean(r["sold"]))})
        print(f"  {name:3s} n={s['n']:4d} gross {g['mean_bp']:+7.3f} bp  cost "
              f"{rows[-1]['mean_cost_bp']:6.3f} bp  net {s['mean_bp']:+7.3f} bp  "
              f"t {s['t']:+5.2f}  annS {s['ann_sharpe']:+6.3f}  turn "
              f"{rows[-1]['mean_traded_notional']:.2f}", flush=True)

    best = max(rows, key=lambda r: (r["net"]["ann_sharpe"], r["net"]["mean_bp"]))
    sv = stats.sharpe_variance_from_trials([r["net"]["sharpe_per_obs"] for r in rows])

    # rig check (pre-registration section 10): EW top-500 full day vs SPY full day
    ew, sp = [], []
    for day in sorted(panel):
        if day > DESIGN_END or day not in spy:
            continue
        p = panel[day]
        ew.append(float(((1 + p["on"]) * (1 + p["id"]) - 1).mean()))
        sp.append((1 + spy[day]["on"]) * (1 + spy[day]["id"]) - 1)
    gap = (np.mean(ew) - np.mean(sp))
    rig = {"ew500_minus_spy_full_day_bp_per_day": float(gap * 1e4),
           "annualised_pct": float(((1 + gap) ** 252 - 1) * 100), "n": len(ew)}
    print("rig check:", json.dumps(rig), flush=True)

    frozen = {
        "preregistration_sha256": PREREG_SHA,
        "frozen_utc": datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selection_rule": "highest design-window net annualised Sharpe at the primary cost rung",
        "trials": len(TRIALS),
        "chosen": {"trial": best["trial"], "family": best["family"], "cfg": best["cfg"]},
        "design_window": {"start": sorted(panel)[0], "end": DESIGN_END},
        "sharpe_variance_across_trials": sv,
        "design_rows": rows,
        "panel_counts": counts,
        "rig_check_ew500_vs_spy": rig,
    }
    FROZEN.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    print(f"\nFROZEN -> {best['trial']} {best['family']} {best['cfg']}  "
          f"design annS {best['net']['ann_sharpe']:+.3f}", flush=True)


def test():
    if not FROZEN.exists():
        raise SystemExit("T10_FROZEN_CONFIG.json is absent -- refusing to run the held-out "
                         "period. The configuration must be frozen on the design window first.")
    frozen = json.loads(FROZEN.read_text())
    if frozen["preregistration_sha256"] != PREREG_SHA:
        raise SystemExit("frozen config was not written under this pre-registration; refusing")
    name = frozen["chosen"]["trial"]
    family = frozen["chosen"]["family"]
    cfg = frozen["chosen"]["cfg"]
    print(f"held-out run, ONCE: {name} {family} {cfg}", flush=True)

    panel, spy, dropped, prev_session = build_panel()
    counts = _panel_counts(panel, spy, dropped)

    out = {"preregistration_sha256": PREREG_SHA,
           "frozen_config_sha256": None, "chosen": frozen["chosen"],
           "run_utc": datetime.datetime.now(datetime.timezone.utc)
           .strftime("%Y-%m-%dT%H:%M:%SZ"),
           "panel_counts": counts, "ladder": {}, "years": {}, "diagnostics": {}}

    primary = None
    for rung in LADDER:
        if rung == "frictionless":
            r = run_config(panel, spy, family, cfg, half_spread_bp=0.0,
                           prev_session=prev_session, day_lo=TEST_START,
                           charge_reg=False, charge_borrow=False)
            key = "frictionless (B19P diagnostic: every cost zero)"
        else:
            hs = rung * H_TEST_BP if rung else 0.0
            r = run_config(panel, spy, family, cfg, half_spread_bp=hs,
                           prev_session=prev_session, day_lo=TEST_START)
            key = ("PRIMARY: M0 auction rail + SEC31 + TAF + borrow" if rung == 0
                   else f"{rung}h = {hs:.3f} bp half-spread on EVERY leg")
        ppy = obs_per_year(r["dates"])
        s = summarise(r["net"], key, ppy)
        out["ladder"][key] = s
        print(f"  {key:58s} net {s['mean_bp']:+8.3f} bp  t {s['t']:+5.2f}  "
              f"annS {s['ann_sharpe']:+6.3f}  annR {s['ann_return'] * 100:+7.2f}%", flush=True)
        if rung == 0.0:
            primary = (r, ppy, s)

    r, ppy, s = primary
    g = summarise(r["gross"], "gross (costs excluded, regulatory still off)", ppy)
    out["obs_per_year"] = ppy
    out["primary_net"] = s
    out["primary_gross"] = g
    out["mean_cost_bp"] = float(np.mean(r["cost"]) * 1e4)
    out["mean_traded_notional_per_session"] = float(np.mean(r["traded"]))
    out["mean_sold_notional_per_session"] = float(np.mean(r["sold"]))

    # gate 2 -- permutation, instrument declared per family
    if family == "A":
        perm = perm_family_A(r["gross"], r["cost"])
    else:
        perm = perm_family_B(r["members"], float(np.mean(r["cost"])))
    out["permutation"] = perm

    # gate 3 -- DSR at the declared trial count
    sv = frozen["sharpe_variance_across_trials"]
    out["dsr_trials_8"] = stats.deflated_sharpe(r["net"], trials=8, sharpe_variance=sv)
    out["dsr_trials_24"] = stats.deflated_sharpe(r["net"], trials=24, sharpe_variance=sv)

    # power statement (pre-registration section 8)
    mde = 2.80 / math.sqrt(len(r["dates"]) / ppy)
    design_row = next(x for x in frozen["design_rows"] if x["trial"] == name)
    design_sharpe = design_row["net"]["ann_sharpe"]
    b22f_sharpe = (0.1006 - 0.0579) / (design_row["gross"]["sd_bp"] / 1e4 * math.sqrt(ppy))
    out["power"] = {
        "n_test": len(r["dates"]), "obs_per_year": ppy,
        "mde_annualised_sharpe_80pct_power": mde,
        "benchmark_design_ann_sharpe": design_sharpe,
        "benchmark_B22F_ann_sharpe": b22f_sharpe,
        "underpowered": mde > max(design_sharpe, b22f_sharpe),
    }

    # year by year, and the leg diagnostics
    years = {}
    for day, net in zip(r["dates"], r["net"]):
        years.setdefault(day[:4], []).append(net)
    for y, v in sorted(years.items()):
        m = stats.moments(v)
        years[y] = {"n": m["n"], "mean_bp": m["mean"] * 1e4,
                    "t": m["mean"] / (m["sd"] / math.sqrt(m["n"])) if m["sd"] else 0.0}
    out["years"] = years

    if family == "A" and r["on"] and r["on"][0] is not None:
        out["diagnostics"]["overnight_only_gross"] = summarise(r["on"], "overnight leg", ppy)
        out["diagnostics"]["intraday_only_gross"] = summarise(r["id"], "intraday leg", ppy)
    # the same two legs for the EW-500 basket over the held-out sessions, always
    on500, id500, spyon, spyid = [], [], [], []
    for day in sorted(panel):
        if day < TEST_START:
            continue
        p = panel[day]
        on500.append(float(p["on"].mean())); id500.append(float(p["id"].mean()))
        if day in spy:
            spyon.append(spy[day]["on"]); spyid.append(spy[day]["id"])
    out["diagnostics"]["ew500_overnight_leg"] = summarise(on500, "EW500 overnight", ppy)
    out["diagnostics"]["ew500_intraday_leg"] = summarise(id500, "EW500 intraday", ppy)
    out["diagnostics"]["spy_overnight_leg"] = summarise(spyon, "SPY overnight", ppy)
    out["diagnostics"]["spy_intraday_leg"] = summarise(spyid, "SPY intraday", ppy)

    (OUT / "T10_HELDOUT_RESULT.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("\n=== GATES ===")
    print(f"1. net mean per session > 0      : {s['mean_bp']:+.4f} bp  t {s['t']:+.2f}")
    print(f"2. permutation p < 0.05          : p = {perm['p_right_tail']:.4f}")
    print(f"3. DSR >= 0.95 at trials = 8     : {out['dsr_trials_8']['dsr']:.4f}")
    print(f"   (power) MDE annS {mde:.3f} vs design {design_sharpe:+.3f} / "
          f"B22F {b22f_sharpe:+.3f} -> underpowered={out['power']['underpowered']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "design"
    {"design": design, "test": test}[cmd]()
