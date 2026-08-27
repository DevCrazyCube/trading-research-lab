#!/usr/bin/env python3
"""T19 -- the EVALUATE half of the paper bot's trade -> evaluate -> iterate loop.

WHAT THIS IS
============
A **read-only** evaluator over an append-only forward-test ledger. It opens
`research/trading_bot/T4_FORWARD_LOG.jsonl` (and any other paper strategy listed in
`research/trading_bot/FORWARD_REGISTER.json`), recomputes the numbers an owner asks for --
realised PnL, the exposure path, drawdown against BOTH the un-overlaid benchmark and the
T13 vol-matched constant-weight null, days elapsed, hit rate, the execution-rail measurement
-- and then states, in the same breath, **how far the sample still is from licensing any
claim at all**.

WHAT IT MUST NEVER DO, AND WHY THAT IS ENFORCED HERE RATHER THAN PROMISED
=========================================================================
The failure mode this whole programme exists to prevent is **"the last few days looked bad,
so we tuned the rule"**. A forward test that is edited in response to its own forward results
is not a forward test; it is an in-sample fit with extra steps and a false provenance.

So:

* This module **never opens a ledger, a state file, or a pre-registration for writing.**
  `_refuse_if_protected()` is called before every write and refuses on any path under
  `research/trading_bot/` that is a ledger, a state file, an authorisation, or a
  pre-registration. That is a guard, not a convention.
* It **imports** the frozen T13 arithmetic (`maxdd`, `crash_table`, `block_bootstrap_dd_diff`,
  `deflated_sharpe`) and the frozen T4 cost model rather than re-deriving them, so an
  evaluation cannot silently disagree with the thing it evaluates.
* It verifies that each registered strategy's pre-registration still hashes to the value the
  register recorded. **A pre-registration that moved is not frozen**, and the evaluator
  refuses to score the strategy rather than scoring it against a moved goalpost.
* Improvement is out of scope for this file **by construction**. There is no flag, no
  subcommand and no code path here that changes a rule. The honest-iterate half lives in
  `research/trading_bot/ITERATION_PROTOCOL.md`, and its answer is always *stand up a NEW
  pre-registered forward test*, never *edit the running one*.

THE NUMBERS THAT WOULD BE MISREAD, AND HOW THEY ARE FENCED
==========================================================
T4's pre-registration §8 forbids "any CAGR, Sharpe, information ratio, or p-value computed
before §6's minimum is met". A power calculation, however, *needs* an effect-size estimate.
The resolution is not to hide the estimate but to file it where it cannot be quoted as a
result: everything of that kind lives under

    certifiability.power_arithmetic.inputs_that_are_not_results

which carries its own disclaimer in every record. A number lifted out of this report travels
with the reason it is not evidence, the same discipline `t4_forward.track_record()` uses.

USAGE
=====
    python -m scripts.trading_bot.forward_eval report                  # human-readable
    python -m scripts.trading_bot.forward_eval report --json           # machine-readable
    python -m scripts.trading_bot.forward_eval report --strategy T4
    python -m scripts.trading_bot.forward_eval status-line             # one line, for the dashboard
    python -m scripts.trading_bot.forward_eval list                    # registered forward tests
    python -m scripts.trading_bot.forward_eval selftest                # hermetic wiring check

DAILY CRON (the owner's line; see also scripts/trading_bot/t4_eval_entrypoint.sh)
=================================================================================
    30 22 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_eval_entrypoint.sh

  This box is Europe/Amsterdam and cron fires in local time, so 22:30 local is 16:30
  US/Eastern -- half an hour after the close, in both DST regimes, because ET is local-6
  all year. The entrypoint writes the report and refreshes the one-line status file. It is
  read-only with respect to the ledger, so running it twice, or not at all, changes nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import statistics
import sys
import types

from .frozen import Refused, to_micros

ROOT = pathlib.Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research" / "trading_bot"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.t13_risk_shaping import (block_bootstrap_dd_diff, crash_table,  # noqa: E402
                                      deflated_sharpe, maxdd, _ppf)
from .t4_forward import (ACTION_WINDOW_ET, _cost_fraction,  # noqa: E402
                        m0_auction_cost_model)

REGISTER_PATH = RESEARCH / "FORWARD_REGISTER.json"
PROTOCOL_PATH = RESEARCH / "ITERATION_PROTOCOL.md"
STATUS_TXT = RESEARCH / "FORWARD_STATUS.txt"
DEFAULT_REPORT_JSON = RESEARCH / "FORWARD_EVAL.json"

TRADING_DAYS = 252.0

# ---------------------------------------------------------------------------
# Frozen evaluation constants. Every one is inherited from a document that was
# frozen before evidence accrued; none is chosen here. The provenance is on the
# same line so a diff to any of them is a diff to a pre-registration.
# ---------------------------------------------------------------------------

CRASH_THRESHOLD = 0.20              # T4 prereg §6: >=20% peak-to-trough in the benchmark curve
CRASHES_FOR_VERDICT = 3             # T4 prereg §6: the FG-minimum. Below it: NO VERDICT
CRASH_YEARS_APART = 9.0             # T13: eight >=20% episodes in 36.6 held-out years
T13_PER_CRASH_ADVANTAGE_PP = 6.00   # T13 measured mean, n = 3
T13_PER_CRASH_SD_PP = 6.84          # T13 measured sd, n = 3

FG1_MIN_DELTA_MAXDD_PP = 3.0        # T4 prereg §5
FG1_BOOTSTRAP_BLOCK = 21            # T4 prereg §5
FG1_BOOTSTRAP_DRAWS = 10_000        # T4 prereg §5
FG2_MIN_DELTA_CAGR = -0.005         # T4 prereg §5: >= -0.5 %/yr
FG4_MAX_MEDIAN_SHORTFALL_BP = 2.0   # T4 prereg §5
FG4_MIN_FILL_RATE = 0.99            # T4 prereg §5
FG5_MIN_DSR = 0.95                  # T4 prereg §5
DECLARED_TRIALS = 1                 # T4 prereg §1: the grid was searched in T13, not here

# z(0.975) + z(0.80) = 1.959964 + 0.841621. T10_RESULT §8 uses 2.80 for exactly this.
Z_TWO_SIDED_95 = 1.959964
Z_POWER = {0.50: 0.0, 0.80: 0.841621, 0.90: 1.281552}

MIN_SESSIONS_FOR_MOMENTS = 30       # below this, skew/kurtosis are noise and DSR is not estimated
MIN_SESSIONS_FOR_BOOTSTRAP = 252    # a block bootstrap on < 1yr of 21-day blocks is theatre

FRAMING = (
    "READ-ONLY EVALUATION OF A FORWARD TEST THAT HAS CERTIFIED NOTHING. This report is "
    "evidence about what the bot DID, never a forecast of what it WILL do, and it licenses no "
    "return claim at any sample size short of the pre-registered minimum. Improvement is a NEW "
    "pre-registered forward test (ITERATION_PROTOCOL.md), never an edit to a running rule."
)

CLAIMS_NEVER_LICENSED = [
    "the overlay makes money",
    "the overlay beats buy-and-hold",
    "the overlay reduces the drawdown you will live through",
    "any CAGR, Sharpe, information ratio, hit rate or p-value computed before the "
    "pre-registered minimum is met",
    "that a calm stretch without a crash is evidence about crashes",
    "that this log is a reason to fund a live account",
]


class Refuse(Refused):
    """Alias so callers can catch the programme's refusal type without importing frozen."""


# ---------------------------------------------------------------------------
# The write guard. This is the guardrail, in code.
# ---------------------------------------------------------------------------

_PROTECTED_SUFFIXES = ("_LOG.jsonl", "_STATE.json", "_AUTHORISATION.json",
                       "_PREREGISTRATION.md", "_PREREGISTRATION.json",
                       "_FROZEN_CONFIG.json", "FORWARD_REGISTER.json")


def _refuse_if_protected(path: pathlib.Path) -> pathlib.Path:
    """An evaluator that can write a ledger is an evaluator that can rewrite history.

    Called before every write this module performs. The list is by suffix rather than by
    exact name so a future strategy's ledger is protected the day it is created, without
    anybody remembering to add it here.
    """
    path = pathlib.Path(path)
    name = path.name
    for suffix in _PROTECTED_SUFFIXES:
        if name.endswith(suffix):
            raise Refuse(
                f"refusing to write {path}: the evaluator is READ-ONLY with respect to "
                "ledgers, state, authorisations, registers and pre-registrations. If an "
                "evaluation makes you want to change one of those, the answer is a NEW "
                "pre-registered forward test -- see research/trading_bot/ITERATION_PROTOCOL.md."
            )
    return path


def _write(path: pathlib.Path, text: str) -> pathlib.Path:
    path = _refuse_if_protected(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# The register of forward tests. Adding a strategy is a register entry, and the
# register entry names the pre-registration whose hash is then enforced.
# ---------------------------------------------------------------------------

def load_register(path: pathlib.Path = None) -> dict:
    path = path or REGISTER_PATH
    if not path.exists():
        raise Refuse(
            f"{path} does not exist. A forward test that is not in the register is not being "
            "evaluated by anything, which is how a strategy quietly runs for a year with "
            "nobody reading it. Create the entry per ITERATION_PROTOCOL.md §4."
        )
    reg = json.loads(path.read_text())
    if reg.get("schema_version") != 1:
        raise Refuse(f"{path}: schema {reg.get('schema_version')}, this evaluator reads 1")
    return reg


def _sha256(path: pathlib.Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_strategy(strategy_id: str = None, register: dict = None) -> dict:
    reg = register or load_register()
    entries = reg["strategies"]
    if strategy_id:
        hits = [e for e in entries if e["id"].upper() == strategy_id.upper()]
        if not hits:
            raise Refuse(f"no strategy {strategy_id!r} in the register; have "
                         f"{[e['id'] for e in entries]}")
        return hits[0]
    running = [e for e in entries if e.get("status") == "RUNNING"]
    if len(running) != 1:
        raise Refuse(
            f"{len(running)} strategies are RUNNING; name one with --strategy. Evaluating "
            "'the bot' when there is more than one is how two ledgers get conflated."
        )
    return running[0]


def verify_integrity(entry: dict) -> dict:
    """A pre-registration that moved is not frozen. Say so loudly rather than scoring it."""
    prereg = ROOT / entry["preregistration"]
    out = {"preregistration": entry["preregistration"],
           "declared_sha256": entry.get("preregistration_sha256")}
    if not prereg.exists():
        raise Refuse(f"pre-registration {prereg} is missing; refusing to evaluate a forward "
                     "test whose frozen document cannot be read")
    actual = _sha256(prereg)
    out["actual_sha256"] = actual
    out["frozen"] = (actual == entry.get("preregistration_sha256"))
    if not out["frozen"]:
        raise Refuse(
            f"{entry['preregistration']} hashes to {actual[:16]}… but the register recorded "
            f"{str(entry.get('preregistration_sha256'))[:16]}…. A pre-registration that can "
            "move is not a pre-registration. Restore the document; do not update the hash."
        )
    return out


# ---------------------------------------------------------------------------
# Reading a ledger. Tolerant on purpose: a future strategy's log only has to
# carry `settled_sessions` with the fields it can honestly produce, and anything
# it cannot produce is reported as not-computable rather than defaulted to zero.
# ---------------------------------------------------------------------------

REQUIRED_SESSION_FIELDS = ("date", "weight_in_force", "r_model_withcash", "r_benchmark")


def read_ledger(path: pathlib.Path) -> list:
    path = pathlib.Path(path)
    if not path.exists():
        raise Refuse(f"ledger {path} does not exist")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def settled_sessions(records: list) -> list:
    """Every settled session, de-duplicated by date, in calendar order.

    De-duplication is not defensive tidying. `--force` exists on the bot, and a session
    re-run would otherwise be counted twice in every statistic below. The FIRST settlement
    of a date wins, because that is the one that was acted on.
    """
    seen, out = {}, []
    for rec in records:
        for s in rec.get("settled_sessions") or []:
            missing = [f for f in REQUIRED_SESSION_FIELDS if f not in s]
            if missing:
                raise Refuse(f"settled session {s.get('date')!r} is missing {missing}; "
                             "refusing to score a partial record")
            if s["date"] in seen:
                continue
            seen[s["date"]] = True
            out.append(s)
    out.sort(key=lambda s: s["date"])
    return out


def _annual_vol(rets: list) -> float:
    if len(rets) < 2:
        return 0.0
    return statistics.pstdev(rets) * math.sqrt(TRADING_DAYS)


def _equity(rets: list) -> list:
    eq = [1.0]
    for r in rets:
        eq.append(eq[-1] * (1.0 + r))
    return eq


# ---------------------------------------------------------------------------
# N1 -- the ex-post volatility-matched constant-weight null. THE null that
# decides the question, and the one that killed both T13 families.
# ---------------------------------------------------------------------------

def constant_weight_curve(sessions: list, w: float) -> list:
    """Daily net returns of a CONSTANT weight `w` in the instrument plus cash.

    Mirrors `t13_risk_shaping.run(panel, constant_exposure(w, …))`: the portfolio return is
    `w*r_index + (1-w)*r_cash`, and the only cost is the single entry from flat, charged on
    the first session at the frozen auction rail. A constant weight never rebalances, so it
    never pays again -- which is deliberately the harder benchmark to beat.
    """
    model = m0_auction_cost_model()
    rets, prev = [], 0.0
    for s in sessions:
        if "r_index" not in s:
            raise Refuse("this ledger does not record `r_index` per settled session, so the "
                         "vol-matched null cannot be built. Reporting it as not-computable "
                         "rather than substituting the benchmark, which is a different null.")
        r_cash = float(s.get("r_cash_accrual") or 0.0)
        micros = to_micros(float(s["index_close_prev"])) if s.get("index_close_prev") else None
        cost = _cost_fraction(model, prev, w, micros) if micros else {"total_fraction": 0.0}
        r_p = w * float(s["r_index"]) + (1.0 - w) * r_cash
        rets.append((1.0 + r_p) * (1.0 - cost["total_fraction"]) - 1.0)
        prev = w
    return rets


def match_weight(sessions: list, target_vol: float) -> float:
    """Constant w whose realised annualised volatility over THIS window equals target_vol.

    Bisection, exactly as `t13_risk_shaping.match_weight`. `w` is fitted with hindsight the
    strategy never had; that unfairness is the point of the null.
    """
    if target_vol <= 0:
        raise Refuse("the strategy's realised volatility is zero; there is nothing to match")
    lo, hi = 0.0, 3.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _annual_vol(constant_weight_curve(sessions, mid)) < target_vol:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-7:
            break
    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# The report's sections
# ---------------------------------------------------------------------------

def elapsed_block(sessions: list, records: list) -> dict:
    if not sessions:
        first_run = records[0]["session_date"] if records else None
        last_run = records[-1]["session_date"] if records else None
        return {"sessions_settled": 0, "calendar_days": 0, "years": 0.0,
                "first_settled": None, "last_settled": None,
                "first_run_logged": first_run, "last_run_logged": last_run,
                "runs_logged": len(records),
                "note": "no session has settled yet: the first weight has been decided but "
                        "the close it earns has not printed. Every number below is null by "
                        "arithmetic, not by omission."}
    d0 = dt.date.fromisoformat(sessions[0]["date"])
    d1 = dt.date.fromisoformat(sessions[-1]["date"])
    days = (d1 - d0).days
    gaps = []
    prev = None
    for s in sessions:
        cur = dt.date.fromisoformat(s["date"])
        if prev is not None and (cur - prev).days > 9:
            gaps.append({"from": prev.isoformat(), "to": cur.isoformat(),
                         "calendar_days": (cur - prev).days})
        prev = cur
    return {
        "sessions_settled": len(sessions),
        "calendar_days": days,
        "years": days / 365.25,
        "first_settled": sessions[0]["date"],
        "last_settled": sessions[-1]["date"],
        "first_run_logged": records[0]["session_date"] if records else None,
        "last_run_logged": records[-1]["session_date"] if records else None,
        "runs_logged": len(records),
        "discontinuities_over_5_sessions": gaps,
        "note": ("T4 prereg §7: a gap of more than five consecutive sessions is a recorded "
                 "operational discontinuity. The curve stays continuous because a weight "
                 "persists until something moves it; the OPERATIONAL record does not."),
    }


def pnl_block(sessions: list, records: list) -> dict:
    """Realised PnL two ways, because the two are not the same object and must not be merged.

    `curve_*` is the unit-notional accrual the ledger maintains, with a T-bill leg on the
    unexposed fraction. `broker_*` is what the paper account actually shows -- which earns no
    interest on idle cash, so `model_excash` is the comparable curve and a gap between
    `model_withcash` and the broker is EXPECTED, not a reconciliation failure.
    """
    out = {"curve": None, "broker": None}
    if sessions:
        eq = sessions[-1].get("equity") or {}
        out["curve"] = {
            "model_withcash_multiple": eq.get("model_withcash"),
            "model_excash_multiple": eq.get("model_excash"),
            "benchmark_multiple": eq.get("benchmark"),
            "model_withcash_return_pct": (eq["model_withcash"] - 1.0) * 100.0
            if eq.get("model_withcash") is not None else None,
            "model_excash_return_pct": (eq["model_excash"] - 1.0) * 100.0
            if eq.get("model_excash") is not None else None,
            "benchmark_return_pct": (eq["benchmark"] - 1.0) * 100.0
            if eq.get("benchmark") is not None else None,
            "cumulative_cost_bp": sum(float((s.get("cost") or {}).get("total_bp") or 0.0)
                                      for s in sessions),
            "cumulative_cost_bp_if_taker_rail": sum(
                float((s.get("cost_if_taker_rail") or {}).get("total_bp") or 0.0)
                for s in sessions),
        }
    accounts = [r.get("account") or {} for r in records]
    equities = [(r.get("session_date"), a.get("equity"))
                for r, a in zip(records, accounts) if a.get("equity") is not None]
    if equities:
        first_d, first_e = equities[0]
        last_d, last_e = equities[-1]
        out["broker"] = {
            "first_seen": first_d, "first_equity_usd": first_e,
            "last_seen": last_d, "last_equity_usd": last_e,
            "pnl_usd": last_e - first_e,
            "pnl_pct": (last_e / first_e - 1.0) * 100.0 if first_e else None,
            "account_type": "ALPACA PAPER. No real money. Live execution is owner-gated.",
            "note": ("the paper account pays no interest on idle cash, so compare it against "
                     "`model_excash`, never against `model_withcash`."),
        }
    out["note"] = ("realised, not projected. No annualisation is applied at any sample size: "
                   "annualising a few sessions is the single most common way a forward log is "
                   "turned into a forecast it cannot support.")
    return out


def wmax_of(params: dict, date: str) -> float:
    return params[date][1] if date in params else 1.0


def exposure_block(sessions: list, records: list) -> dict:
    weights = [float(s["weight_in_force"]) for s in sessions]
    decisions = [(r["session_date"], r.get("decision") or {}) for r in records
                 if r.get("decision")]
    vols = [(d, float(x["realised_vol_annual"]), float(x["target_weight"]))
            for d, x in decisions if x.get("realised_vol_annual") is not None]
    behaviour = None
    if vols:
        rv = [v for _, v, _ in vols]
        tw = [w for _, _, w in vols]
        # Reconstruct each decision from the rule the record itself carries. This is the check
        # that a weight was produced BY THE FROZEN RULE and not by anything else -- it is
        # arithmetic, not a plot, and it fails loudly rather than looking approximately right.
        params = {}
        for rec in records:
            r = rec.get("rule") or {}
            if r.get("target") is not None and r.get("wmax") is not None:
                params[rec["session_date"]] = (float(r["target"]), float(r["wmax"]))
        breaks = []
        for d, v, w in vols:
            if d not in params:
                continue
            target, wmax = params[d]
            expected = min(wmax, target / v)
            if abs(expected - w) > 1e-12:
                breaks.append({"date": d, "expected": expected, "logged": w})
        derisked = [(d, v, w) for d, v, w in vols if w < wmax_of(params, d)]
        behaviour = {
            "n_decisions": len(vols),
            "realised_vol_min": min(rv), "realised_vol_max": max(rv),
            "target_weight_min": min(tw), "target_weight_max": max(tw),
            "n_below_the_cap": len(derisked),
            "decisions_reconstructed_from_the_frozen_rule": len(
                [d for d, _, _ in vols if d in params]),
            "reconstruction_breaks": breaks,
            "note": ("w = min(w_max, target/realised_vol) is MECHANICAL, so agreement here is "
                     "a wiring check and not a finding. It is reported because a broken "
                     "implementation makes every other number on this page meaningless "
                     "regardless of what the PnL says. A single break invalidates the window "
                     "under FG3."),
        }
    if not weights:
        return {"path": [], "summary": None, "behaviour_check": behaviour,
                "note": "no settled session, so no weight has yet been in force for a return"}
    changes = sum(1 for a, b in zip(weights, weights[1:]) if abs(a - b) > 1e-12)
    return {
        "path": [{"date": s["date"], "weight": float(s["weight_in_force"])} for s in sessions],
        "summary": {
            "n": len(weights), "min": min(weights), "max": max(weights),
            "mean": statistics.fmean(weights), "latest": weights[-1],
            "changes": changes,
            "changes_per_year": changes / max(1e-9, len(weights) / TRADING_DAYS),
            "time_at_cap": sum(1 for w in weights if w >= 0.9999) / len(weights),
        },
        "behaviour_check": behaviour,
    }


def drawdown_block(sessions: list) -> dict:
    """Both comparisons, with the easy one explicitly labelled as the one that does not decide.

    T13 §5i records the exact error of reporting the benchmark comparison alone, and the T4
    pre-registration forbids reporting `delta_maxdd_vs_benchmark_pp` without N1. This function
    therefore computes N1 or explains why it could not; it never returns one without the other.
    """
    if not sessions:
        return {"computable": False,
                "reason": "no settled session; a drawdown needs at least one return"}
    r_f = [float(s["r_model_withcash"]) for s in sessions]
    r_b = [float(s["r_benchmark"]) for s in sessions]
    eq_f, eq_b = _equity(r_f), _equity(r_b)
    dd_f, dd_b = maxdd(eq_f), maxdd(eq_b)

    out = {
        "computable": True,
        "strategy_maxdd_pct": dd_f * 100.0,
        "vs_benchmark_DIAGNOSTIC_ONLY": {
            "benchmark": "un-overlaid buy-and-hold of the same instrument, one entry charged",
            "benchmark_maxdd_pct": dd_b * 100.0,
            "delta_maxdd_pp": (dd_b - dd_f) * 100.0,
            "why_this_is_not_the_answer": (
                "beating 100% exposure is the easy comparison and an overlay with mean "
                "exposure ~0.74 wins it by construction. T13 §5i records this exact error. "
                "It is a diagnostic and may never be quoted as the result."),
        },
    }
    try:
        vol_f = _annual_vol(r_f)
        w1 = match_weight(sessions, vol_f)
        r_n1 = constant_weight_curve(sessions, w1)
        eq_n1 = _equity(r_n1)
        dd_n1 = maxdd(eq_n1)
        out["vs_vol_matched_null_N1"] = {
            "definition": ("ex-post volatility-matched CONSTANT weight in the same instrument "
                           "plus T-bills, solved by bisection over THIS forward window. It is "
                           "fitted with hindsight the strategy never had. That is deliberate: "
                           "it is the gate that killed both T13 families."),
            "matched_weight": w1,
            "strategy_realised_vol_annual": vol_f,
            "null_realised_vol_annual": _annual_vol(r_n1),
            "null_maxdd_pct": dd_n1 * 100.0,
            "delta_maxdd_pp": (dd_n1 - dd_f) * 100.0,
            "gate_FG1_threshold_pp": FG1_MIN_DELTA_MAXDD_PP,
            "size_half_of_FG1_met": (dd_n1 - dd_f) * 100.0 >= FG1_MIN_DELTA_MAXDD_PP,
            "significance_half_of_FG1": _bootstrap_or_reason(r_f, r_n1),
            "reminder": ("the size half of a gate is not the gate. T13's overlay cleared "
                         "+7.25 pp and died on p = 0.233."),
        }
    except Refused as exc:
        out["vs_vol_matched_null_N1"] = {"computable": False, "reason": str(exc)}
    return out


def _bootstrap_or_reason(r_f: list, r_n1: list) -> dict:
    if len(r_f) < MIN_SESSIONS_FOR_BOOTSTRAP:
        return {
            "computed": False,
            "reason": (f"{len(r_f)} settled sessions. A paired block bootstrap with "
                       f"{FG1_BOOTSTRAP_BLOCK}-session blocks needs at least "
                       f"{MIN_SESSIONS_FOR_BOOTSTRAP} to resample anything but itself, and "
                       "T4 prereg §8 forbids quoting a p-value before the §6 minimum in any "
                       "case. Withheld deliberately."),
        }
    res = block_bootstrap_dd_diff(r_f, r_n1, n_boot=FG1_BOOTSTRAP_DRAWS,
                                  mean_block=FG1_BOOTSTRAP_BLOCK, seed=13)
    res["computed"] = True
    res["NOT_LICENSED"] = ("this p-value may not be reported as a result until the §6 minimum "
                           "of completed crash episodes is met. It is shown so the gate can be "
                           "seen approaching, not so it can be quoted.")
    return res


def hit_rate_block(sessions: list) -> dict:
    if not sessions:
        return {"computable": False, "reason": "no settled session"}
    r_f = [float(s["r_model_withcash"]) for s in sessions]
    n = len(r_f)
    wins = sum(1 for r in r_f if r > 0)
    out = {
        "n_sessions": n,
        "sessions_up": wins,
        "raw_hit_rate": wins / n,
        "why_raw_is_nearly_meaningless": (
            "a long-only overlay's daily win rate is the instrument's win rate scaled by "
            "exposure. It measures SPY, not the rule. The paired rate below is the only one "
            "that is about the rule at all."),
    }
    try:
        vol_f = _annual_vol(r_f)
        w1 = match_weight(sessions, vol_f)
        r_n1 = constant_weight_curve(sessions, w1)
        beats = sum(1 for a, b in zip(r_f, r_n1) if a > b)
        p = beats / n
        out["paired_vs_N1"] = {
            "sessions_beating_the_vol_matched_null": beats,
            "paired_hit_rate": p,
            "binomial_se": math.sqrt(0.25 / n),
            "sessions_needed_to_separate_from_0.5_at_80pct_power": (
                _binomial_n_required(p) if abs(p - 0.5) > 1e-9 else None),
            "NOT_LICENSED": ("a hit rate is not the claim under test. T4's claim is entirely "
                             "about the LEFT TAIL, where per-session win rates carry almost no "
                             "information. Reported because it was asked for, fenced because "
                             "it is the number most likely to be misread as an edge."),
        }
    except Refused as exc:
        out["paired_vs_N1"] = {"computable": False, "reason": str(exc)}
    return out


def _binomial_n_required(p: float, power: float = 0.80) -> float:
    z = Z_TWO_SIDED_95 + Z_POWER[power]
    return (z * 0.5 / (p - 0.5)) ** 2


def execution_block(records: list) -> dict:
    """FG4 -- the one thing in this whole test that accrues daily and is worth having early.

    WHAT THIS MEASURES CHANGED ON 2026-08-18, AND THE CHANGE IS NOT COSMETIC.
    Until then the bot placed a market-on-close order and every fill was one observation of
    whether a retail-sized MOC joins the cross M0 measured -- the rail four dead candidates in
    this programme rest on. **That order type EXPIRES UNFILLED on the Alpaca paper account**
    (measured: order 3a5487f8, submitted 2026-08-17T13:50Z, `status="expired"`, `filled_qty=0`
    at the close), so the bot now sends a market DAY order in the final minutes instead.

    Consequently `shortfall_bp_adverse_positive` is no longer auction-vs-print. It is now
    **near-close market fill vs the official closing print**, which carries a crossed spread and
    a few minutes of price drift that the MOC rail did not. The drift is unbiased, so the MEDIAN
    -- which is what FG4's 2 bp threshold gates on -- remains the right statistic and the gate is
    read unchanged; the DISPERSION will be wider than an auction fill's, and that is expected,
    not a failure. Records written before 2026-08-18 measure the MOC rail and records after it
    measure the near-close rail; they are the same field and they are NOT the same measurement.

    A reconciled record with `position_established: false` is a NON-FILL: the order died and the
    decision it was meant to execute was dropped rather than accrued. It counts in the
    denominator and against the fill rate, which is exactly what FG4 is for.
    """
    fills = [r["fill_reconciliation"] for r in records
             if (r.get("fill_reconciliation") or {}).get("reconciled")]
    shortfalls = [f["shortfall_bp_adverse_positive"] for f in fills
                  if f.get("shortfall_bp_adverse_positive") is not None]
    filled = [f for f in fills if f.get("status") == "filled"
              or (f.get("filled_qty") or 0) >= (f.get("qty_ordered") or 1)]
    n = len(fills)
    out = {
        "orders_reconciled": n,
        "orders_fully_filled": len(filled),
        "fill_rate": (len(filled) / n) if n else None,
        "shortfall_bp_adverse_positive": {
            "n": len(shortfalls),
            "median": statistics.median(shortfalls) if shortfalls else None,
            "mean": statistics.fmean(shortfalls) if shortfalls else None,
            "max": max(shortfalls) if shortfalls else None,
        },
        "gate_FG4": {
            "median_shortfall_threshold_bp": FG4_MAX_MEDIAN_SHORTFALL_BP,
            "fill_rate_threshold": FG4_MIN_FILL_RATE,
            "status": "NOT YET MEASURABLE" if n == 0 else (
                "PROVISIONALLY MET" if (
                    statistics.median(shortfalls) <= FG4_MAX_MEDIAN_SHORTFALL_BP
                    and (len(filled) / n) >= FG4_MIN_FILL_RATE) and shortfalls
                else "AT RISK"),
            "consequence_if_it_fails": ("the ENTIRE accrual is restated at the taker rail "
                                        "(2.5 bp/side) BEFORE FG1 is read, not after."),
        },
        "non_fills": [
            {"session": f.get("placed_for_session"), "status": f.get("status"),
             "qty_ordered": f.get("qty_ordered"), "filled_qty": f.get("filled_qty"),
             "decision_dropped": (f.get("decision_cancelled_by_non_fill") or {})
                                 .get("dropped_pending_weight")}
            for f in fills if f.get("position_established") is False
            or ((f.get("filled_qty") or 0) == 0 and f.get("status") in
                ("expired", "canceled", "cancelled", "rejected", "done_for_day"))],
        "rail_measured": (
            f"NEAR-CLOSE MARKET (type=market, tif=day, sent "
            f"{ACTION_WINDOW_ET[0][0]:02d}:{ACTION_WINDOW_ET[0][1]:02d}-"
            f"{ACTION_WINDOW_ET[1][0]:02d}:{ACTION_WINDOW_ET[1][1]:02d} ET) since 2026-08-18 -- "
            "the window is read from t4_forward.ACTION_WINDOW_ET rather than restated here, so "
            "this label cannot drift away from the schedule it describes. Before that: "
            "MARKET-ON-CLOSE (tif=cls), which expired unfilled on the paper account and never "
            "produced a fill observation at all. The shortfall field spans both rails and is "
            "NOT one measurement -- read the session date with the number."),
        "power_on_this_axis": _rule_of_three(n, len(filled)),
        "why_this_matters_most_right_now": (
            "the drawdown question needs decades. This one needs sessions, and it is the "
            "measured half M0 explicitly did not claim. If the rail is not what was assumed, "
            "that is worth knowing in months rather than in 2050. It is now KNOWN not to be "
            "what was assumed -- the executed rail is a near-close market order and the priced "
            "rail is M0's auction -- so FG4 is measuring a live discrepancy, not a formality."),
    }
    return out


def _rule_of_three(n: int, filled: int) -> dict:
    """With zero failures in n trials the 95% upper bound on the failure rate is 3/n."""
    if n == 0:
        return {"computable": False,
                "reason": "no reconciled order yet; absence is not a 100% fill rate"}
    misses = n - filled
    out = {"n": n, "non_fills": misses}
    if misses == 0:
        out["upper_95pct_bound_on_non_fill_rate"] = 3.0 / n
        out["sessions_needed_to_bound_non_fill_below_1pct"] = 300
        out["sessions_remaining_for_that_bound"] = max(0, 300 - n)
        out["note"] = ("rule of three. With no non-fill in n orders the 95% upper bound on the "
                       "non-fill rate is 3/n, so FG4's 99% fill rate cannot be DEMONSTRATED "
                       "below ~300 clean orders however good the record looks.")
    else:
        out["observed_non_fill_rate"] = misses / n
        out["note"] = "a non-fill has occurred; FG4 is a live question, not a formality."
    return out


def fidelity_block(records: list, sessions: list) -> dict:
    """FG3 -- one mismatch invalidates the window, so it is checked rather than assumed.

    The bot cross-checks the frozen implementation against an independent recomputation at
    decision time. This re-checks the SEPARATE thing: that the weight which actually earned
    each settled session's return is the weight the decision queue said should be in force.
    """
    decided = {}
    for rec in records:
        d = rec.get("decision") or {}
        if d.get("target_weight") is None:
            continue
        decided[rec["session_date"]] = float(d["target_weight"])
    mismatches, checked = [], 0
    for s in sessions:
        applicable = [d for d in decided if d < s["date"]]
        if not applicable:
            continue
        expected = decided[max(applicable)]
        checked += 1
        if abs(expected - float(s["weight_in_force"])) > 1e-9:
            mismatches.append({"date": s["date"], "expected": expected,
                               "in_force": float(s["weight_in_force"])})
    return {
        "sessions_checked": checked,
        "mismatches": mismatches,
        "cross_check_notes": sorted({(r.get("decision") or {}).get("cross_check")
                                     for r in records
                                     if (r.get("decision") or {}).get("cross_check")}),
        "gate_FG3": ("NOT YET MEASURABLE" if checked == 0
                     else ("PASS" if not mismatches else "FAIL -- WINDOW INVALIDATED")),
        "consequence_if_it_fails": ("T4 prereg §5: one mismatch invalidates the window. It is "
                                    "not a rounding note to reconcile later."),
    }


# ---------------------------------------------------------------------------
# The certifiability readout -- the section this task exists for
# ---------------------------------------------------------------------------

def crash_episodes(sessions: list) -> list:
    """Completed >=20% peak-to-trough episodes in the UN-OVERLAID benchmark curve.

    Uses the frozen T13 `crash_table` rather than a local reimplementation, through a shim
    that supplies only the `.dates` the function reads. Two definitions of "crash" in one
    programme is one too many.
    """
    if not sessions:
        return []
    r_b = [float(s["r_benchmark"]) for s in sessions]
    r_f = [float(s["r_model_withcash"]) for s in sessions]
    dates = ["inception"] + [s["date"] for s in sessions]
    shim = types.SimpleNamespace(dates=dates)
    return crash_table(shim, _equity(r_b), _equity(r_f), a=1, threshold=CRASH_THRESHOLD)


def _crashes_for_power(power: float) -> float:
    z = Z_TWO_SIDED_95 + Z_POWER[power]
    return (z * T13_PER_CRASH_SD_PP / T13_PER_CRASH_ADVANTAGE_PP) ** 2


def certifiability_block(sessions: list, records: list) -> dict:
    """How many more independent observations before ANY claim is licensable.

    Three axes, and they are not interchangeable. The BINDING one is crashes, because the
    claim under test is a left-tail claim and a left-tail claim gets one observation per
    crash however many sessions elapse.
    """
    episodes = crash_episodes(sessions)
    n_crash = len(episodes)
    remaining_min = max(0, CRASHES_FOR_VERDICT - n_crash)

    power_rows = []
    for p in (0.50, 0.80, 0.90):
        need = _crashes_for_power(p)
        power_rows.append({
            "power": p,
            "crashes_required": round(need, 1),
            "crashes_remaining": round(max(0.0, need - n_crash), 1),
            "expected_years_remaining": round(max(0.0, need - n_crash) * CRASH_YEARS_APART, 0),
        })

    n = len(sessions)
    session_axis = {
        "settled_sessions": n,
        "note": ("sessions accrue fast and buy almost nothing on the primary question. They "
                 "are the denominator for FG4 (the rail) and FG5 (DSR), not for FG1."),
    }
    inputs = {"DISCLAIMER": (
        "EVERY NUMBER IN THIS SUB-BLOCK IS AN INPUT TO A POWER CALCULATION, NOT A RESULT. "
        "T4 prereg §8 forbids quoting a Sharpe, a CAGR or a p-value from this sample as "
        "evidence. They appear here because sizing the remaining sample is impossible "
        "without an effect-size estimate, and hiding the estimate would make the power "
        "arithmetic unauditable rather than honest.")}

    if n >= MIN_SESSIONS_FOR_MOMENTS:
        try:
            r_f = [float(s["r_model_withcash"]) for s in sessions]
            w1 = match_weight(sessions, _annual_vol(r_f))
            r_n1 = constant_weight_curve(sessions, w1)
            paired = [a - b for a, b in zip(r_f, r_n1)]
            dsr = deflated_sharpe(paired, DECLARED_TRIALS, sharpe_var=0.0)
            sr = dsr["sharpe_per_obs"]
            inputs["paired_excess_vs_N1"] = {
                "per_obs_sharpe": sr,
                "annualised_sharpe": sr * math.sqrt(TRADING_DAYS),
                "skew": dsr["skew"], "kurtosis": dsr["kurtosis"],
                "dsr_now_at_1_declared_trial": dsr["dsr"],
            }
            if sr > 0:
                denom = math.sqrt(max(1e-18, 1 - dsr["skew"] * sr
                                      + (dsr["kurtosis"] - 1) / 4.0 * sr ** 2))
                need = 1.0 + (_ppf(FG5_MIN_DSR) * denom / sr) ** 2
                session_axis["sessions_required_for_FG5_DSR_0.95"] = round(need, 0)
                session_axis["sessions_remaining_for_FG5"] = round(max(0.0, need - n), 0)
                session_axis["years_remaining_for_FG5"] = round(
                    max(0.0, need - n) / TRADING_DAYS, 1)
                ann = sr * math.sqrt(TRADING_DAYS)
                session_axis["T10_resolution_check_years_at_80pct_power"] = round(
                    ((Z_TWO_SIDED_95 + Z_POWER[0.80]) / ann) ** 2, 1) if ann > 0 else None
            else:
                session_axis["sessions_required_for_FG5_DSR_0.95"] = None
                session_axis["why"] = (
                    "the paired excess against the vol-matched null is NEGATIVE so far. No "
                    "sample size certifies a negative-signed effect; the honest statement is "
                    "that the sign would have to turn first, and a sign that turns after being "
                    "observed is exactly the thing this protocol forbids acting on.")
        except Refused as exc:
            inputs["paired_excess_vs_N1"] = {"computable": False, "reason": str(exc)}
    else:
        inputs["paired_excess_vs_N1"] = {
            "computable": False,
            "reason": (f"{n} settled sessions is below the {MIN_SESSIONS_FOR_MOMENTS} needed "
                       "for skew and kurtosis to be anything but noise, and DSR's denominator "
                       "is built from both.")}

    fills = [r["fill_reconciliation"] for r in records
             if (r.get("fill_reconciliation") or {}).get("reconciled")]

    return {
        "certifiable": False,
        "verdict": ("NO VERDICT -- the pre-registered minimum is not met. This is neither a "
                    "pass nor a 'promising'."),
        "binding_axis": "completed crash episodes",
        "crash_axis": {
            "definition": (f">= {CRASH_THRESHOLD:.0%} peak-to-trough decline in the un-overlaid "
                           "benchmark curve, peak -> trough (T4 prereg §6, frozen before any "
                           "evidence accrued)"),
            "completed": n_crash,
            "episodes": episodes,
            "required_before_any_verdict": CRASHES_FOR_VERDICT,
            "remaining_before_any_verdict": remaining_min,
            "expected_years_before_any_verdict": remaining_min * CRASH_YEARS_APART,
            "expected_years_per_crash": CRASH_YEARS_APART,
            "power_table": power_rows,
            "effect_size_used": {
                "per_crash_advantage_pp": T13_PER_CRASH_ADVANTAGE_PP,
                "sd_pp": T13_PER_CRASH_SD_PP, "n": 3,
                "source": "T13 held-out window; the same three episodes that failed the gate",
            },
            "the_honest_expectation": (
                "T4 prereg §6 states it plainly and it is repeated here so it cannot be "
                "discovered in year twelve: at the measured effect size this forward test is "
                "NOT expected to certify the overlay. 80% power is ~10 crashes, ~92 years. "
                "What it IS expected to produce is an execution measurement that accrues "
                "daily, a behavioural check outside the observation window, and a working "
                "verifiable bot on the safe side of the owner gate."),
        },
        "session_axis": session_axis,
        "execution_axis": {
            "orders_reconciled": len(fills),
            "note": ("the only axis on which this test buys information at a useful rate. "
                     "~300 clean fills bounds the non-fill rate under 1% by the rule of "
                     "three; that is a year of sessions, not a career. Fills accrue only from "
                     "2026-08-18, when the order type was changed from market-on-close (which "
                     "expires unfilled on the paper account) to a near-close market order."),
        },
        "power_arithmetic": {"inputs_that_are_not_results": inputs},
        "what_would_change_the_answer": [
            "a completed >=20% crash episode -- the only event that moves the primary gate",
            "a persistent positive shortfall on fills -- which would fail FG4 and force the "
            "whole accrual to be restated at the taker rail",
            "a weight mismatch -- which invalidates the window outright under FG3",
            "NOT: a good month, a bad month, or any amount of calm-market performance",
        ],
    }


def gates_block(rep: dict) -> dict:
    """FG1..FG5 in one place, in the frozen order, with 'not readable yet' as a real state.

    A gate has three states here, not two. `NOT READABLE` is not a soft fail and not a soft
    pass: the T4 pre-registration says the gates are read *only* when §6's minimum is met, and
    a summary that collapsed that into "pending, looking good" would be the exact misreading
    the whole document exists to prevent.
    """
    dd = rep["drawdown"]
    n1 = (dd.get("vs_vol_matched_null_N1") or {}) if dd.get("computable") else {}
    cert = rep["certifiability"]
    minimum_met = (cert["crash_axis"]["remaining_before_any_verdict"] == 0)
    size_met = n1.get("size_half_of_FG1_met")
    return {
        "minimum_sample_met": minimum_met,
        "read_order": "FG4 first (it can force a restatement), then FG3, then FG1, FG2, FG5",
        "FG1_drawdown_vs_N1": {
            "threshold": f">= {FG1_MIN_DELTA_MAXDD_PP} pp AND p < 0.05 (paired block bootstrap, "
                         f"{FG1_BOOTSTRAP_BLOCK}-session blocks, {FG1_BOOTSTRAP_DRAWS} draws)",
            "size_half": ("not computable" if n1.get("delta_maxdd_pp") is None
                          else f"{n1['delta_maxdd_pp']:+.4f} pp "
                               f"({'meets' if size_met else 'does not meet'} the size half)"),
            "state": "NOT READABLE -- §6 minimum not met" if not minimum_met else "READABLE",
        },
        "FG2_delta_cagr_vs_N1": {
            "threshold": f">= {FG2_MIN_DELTA_CAGR:+.1%}/yr",
            "state": ("NOT READABLE -- T4 prereg §8 forbids computing a CAGR from this sample, "
                      "so this gate is deliberately not evaluated before the §6 minimum"
                      if not minimum_met else "READABLE"),
        },
        "FG3_fidelity": {
            "threshold": "every settled weight equals the frozen rule's weight; one mismatch "
                         "invalidates the window",
            "state": rep["fidelity_FG3"]["gate_FG3"],
            "readable_now": True,
        },
        "FG4_execution_rail": {
            "threshold": f"median adverse shortfall <= {FG4_MAX_MEDIAN_SHORTFALL_BP} bp AND "
                         f"fill rate >= {FG4_MIN_FILL_RATE:.0%}",
            "state": rep["execution_rail_FG4"]["gate_FG4"]["status"],
            "readable_now": True,
            "note": "the only gate that accrues fast enough to be answered on a human timescale",
        },
        "FG5_dsr": {
            "threshold": f">= {FG5_MIN_DSR} at {DECLARED_TRIALS} declared trial(s)",
            "state": "NOT READABLE -- §6 minimum not met" if not minimum_met else "READABLE",
        },
        "verdict": (cert["verdict"] if not minimum_met else
                    "MINIMUM MET -- read the gates in the frozen order and publish the verdict, "
                    "pass or dead. That publication is owner-gated."),
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def evaluate(strategy_id: str = None, register_path: pathlib.Path = None,
             ledger_path: pathlib.Path = None) -> dict:
    reg = load_register(register_path)
    entry = resolve_strategy(strategy_id, reg)
    integrity = verify_integrity(entry)
    ledger = pathlib.Path(ledger_path) if ledger_path else ROOT / entry["ledger"]
    records = [r for r in read_ledger(ledger) if r.get("kind") == "session"]
    sessions = settled_sessions(records)

    report = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "framing": FRAMING,
        "strategy": {
            "id": entry["id"], "rule_id": entry.get("rule_id"),
            "status": entry.get("status"), "family": entry.get("family"),
            "declared_trials": entry.get("declared_trials"),
            "inception": entry.get("inception"),
            "ledger": entry["ledger"], "integrity": integrity,
            "prior_verdict_on_this_rule": entry.get("prior_verdict"),
        },
        "elapsed": elapsed_block(sessions, records),
        "realised_pnl": pnl_block(sessions, records),
        "exposure_path": exposure_block(sessions, records),
        "drawdown": drawdown_block(sessions),
        "hit_rate": hit_rate_block(sessions),
        "execution_rail_FG4": execution_block(records),
        "fidelity_FG3": fidelity_block(records, sessions),
        "certifiability": certifiability_block(sessions, records),
        "claims_licensed": [],
        "claims_explicitly_not_licensed": CLAIMS_NEVER_LICENSED,
        "iteration_protocol": (
            "research/trading_bot/ITERATION_PROTOCOL.md -- how a new idea is stood up as a "
            "SEPARATE frozen forward test, and how a running one is retired. Nothing in this "
            "report may be used to modify a running rule."),
    }
    report["gates"] = gates_block(report)
    report["status_line"] = status_line(report)
    return report


def status_line(report: dict) -> str:
    """One line, <=200 chars, for the dashboard. Leads with the denominator, never the PnL."""
    s = report["strategy"]
    el = report["elapsed"]
    cert = report["certifiability"]
    n = el["sessions_settled"]
    crashes = cert["crash_axis"]["completed"]
    need = cert["crash_axis"]["remaining_before_any_verdict"]
    pnl = report["realised_pnl"].get("curve")
    pnl_txt = "n/a" if not pnl or pnl.get("model_withcash_return_pct") is None else \
        f"{pnl['model_withcash_return_pct']:+.2f}%"
    dd = report["drawdown"]
    n1 = (dd.get("vs_vol_matched_null_N1") or {}) if dd.get("computable") else {}
    n1_txt = ("N1 n/a" if not n1 or n1.get("delta_maxdd_pp") is None
              else f"vs N1 {n1['delta_maxdd_pp']:+.2f}pp")
    return (f"{s['id']} {s['rule_id']} PAPER | {n} settled sessions "
            f"({el['years']:.2f}y) | realised {pnl_txt} | {n1_txt} | crashes {crashes}/"
            f"{cert['crash_axis']['required_before_any_verdict']} "
            f"({need} more, ~{cert['crash_axis']['expected_years_before_any_verdict']:.0f}y) "
            f"| NOT CERTIFIABLE -- {cert['verdict'].split('--')[0].strip()}")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_text(rep: dict) -> str:
    L = []
    a = L.append
    s, el = rep["strategy"], rep["elapsed"]
    a("=" * 78)
    a(f"FORWARD-TEST EVALUATION -- {s['id']}  ({s['rule_id']})")
    a("=" * 78)
    a(rep["framing"])
    a("")
    a(f"  prior verdict on this rule : {s.get('prior_verdict_on_this_rule') or 'n/a'}")
    a(f"  pre-registration           : {s['integrity']['preregistration']}")
    a(f"  frozen (sha256 verified)   : {s['integrity']['frozen']}")
    a("")
    a("-- ELAPSED " + "-" * 66)
    a(f"  runs logged                : {el['runs_logged']}  "
      f"(first {el['first_run_logged']}, last {el['last_run_logged']})")
    a(f"  settled sessions           : {el['sessions_settled']}")
    a(f"  calendar days / years      : {el['calendar_days']} / {el['years']:.3f}")
    if el.get("discontinuities_over_5_sessions"):
        a(f"  DISCONTINUITIES            : {el['discontinuities_over_5_sessions']}")
    if el.get("note"):
        a(f"  note: {el['note']}")
    a("")
    a("-- REALISED PnL (evidence, not forecast) " + "-" * 36)
    cur = rep["realised_pnl"].get("curve")
    if cur:
        def _pct(key):
            v = cur.get(key)
            return "not recorded by this ledger" if v is None else f"{v:+.4f}%"
        a(f"  model (with cash leg)      : {_pct('model_withcash_return_pct')}")
        a(f"  model (ex cash)            : {_pct('model_excash_return_pct')}")
        a(f"  un-overlaid benchmark      : {_pct('benchmark_return_pct')}")
        a(f"  cumulative cost            : {cur['cumulative_cost_bp']:.4f} bp  "
          f"(taker rail would be {cur['cumulative_cost_bp_if_taker_rail']:.4f} bp)")
    else:
        a("  not computable: no settled session yet.")
    br = rep["realised_pnl"].get("broker")
    if br:
        a(f"  paper account equity       : {br['first_equity_usd']:,.2f} -> "
          f"{br['last_equity_usd']:,.2f}  ({br['pnl_usd']:+,.2f} USD)")
        a(f"  {br['note']}")
    a("")
    a("-- EXPOSURE PATH " + "-" * 60)
    summ = rep["exposure_path"].get("summary")
    if summ:
        a(f"  weight min/mean/max/latest : {summ['min']:.4f} / {summ['mean']:.4f} / "
          f"{summ['max']:.4f} / {summ['latest']:.4f}")
        a(f"  changes                    : {summ['changes']}  "
          f"({summ['changes_per_year']:.1f}/yr), time at cap {summ['time_at_cap']:.1%}")
    else:
        a("  no weight has yet been in force for a settled return.")
    beh = rep["exposure_path"].get("behaviour_check")
    if beh:
        a(f"  decisions logged           : {beh['n_decisions']}  "
          f"realised vol {beh['realised_vol_min']:.4f}..{beh['realised_vol_max']:.4f}, "
          f"target w {beh['target_weight_min']:.4f}..{beh['target_weight_max']:.4f}")
        a(f"  rule reconstruction        : "
          f"{beh['decisions_reconstructed_from_the_frozen_rule']} checked, "
          f"{len(beh['reconstruction_breaks'])} breaks"
          + ("   [WINDOW INVALIDATED]" if beh["reconstruction_breaks"] else ""))
    a("")
    a("-- DRAWDOWN " + "-" * 65)
    dd = rep["drawdown"]
    if not dd.get("computable"):
        a(f"  not computable: {dd['reason']}")
    else:
        a(f"  strategy maxDD             : {dd['strategy_maxdd_pct']:.4f}%")
        b = dd["vs_benchmark_DIAGNOSTIC_ONLY"]
        a(f"  vs un-overlaid benchmark   : {b['delta_maxdd_pp']:+.4f} pp   "
          f"[DIAGNOSTIC ONLY -- the easy comparison]")
        n1 = dd.get("vs_vol_matched_null_N1") or {}
        if n1.get("computable") is False:
            a(f"  vs T13 vol-matched null N1 : not computable -- {n1['reason']}")
        else:
            a(f"  vs T13 vol-matched null N1 : {n1['delta_maxdd_pp']:+.4f} pp  "
              f"(matched w = {n1['matched_weight']:.4f}, gate needs "
              f">= {n1['gate_FG1_threshold_pp']:.1f} pp AND p < 0.05)")
            sig = n1["significance_half_of_FG1"]
            a(f"  FG1 significance half      : "
              + (f"p_null_worse = {sig['p_null_worse']:.4f}" if sig.get("computed")
                 else f"withheld -- {sig['reason']}"))
    a("")
    a("-- HIT RATE " + "-" * 65)
    hr = rep["hit_rate"]
    if not hr.get("computable", True):
        a(f"  not computable: {hr['reason']}")
    else:
        a(f"  raw sessions up            : {hr['sessions_up']}/{hr['n_sessions']} "
          f"= {hr['raw_hit_rate']:.4f}")
        pv = hr.get("paired_vs_N1") or {}
        if pv.get("paired_hit_rate") is not None:
            a(f"  paired vs N1               : {pv['paired_hit_rate']:.4f} "
              f"(+/- {pv['binomial_se']:.4f} binomial se)")
        a("  NOTE: neither rate is the claim under test. The claim is about the left tail.")
    a("")
    a("-- EXECUTION RAIL (FG4) " + "-" * 53)
    ex = rep["execution_rail_FG4"]
    a(f"  orders reconciled          : {ex['orders_reconciled']}  "
      f"fully filled {ex['orders_fully_filled']}")
    sh = ex["shortfall_bp_adverse_positive"]
    a(f"  adverse shortfall (bp)     : n={sh['n']} median={sh['median']} max={sh['max']}"
      f"   [threshold {FG4_MAX_MEDIAN_SHORTFALL_BP} bp]")
    a(f"  FG4 status                 : {ex['gate_FG4']['status']}")
    a(f"  {ex['power_on_this_axis'].get('note', ex['power_on_this_axis'].get('reason', ''))}")
    a("")
    a("-- FIDELITY (FG3) " + "-" * 59)
    fi = rep["fidelity_FG3"]
    a(f"  sessions checked           : {fi['sessions_checked']}   "
      f"mismatches {len(fi['mismatches'])}   status {fi['gate_FG3']}")
    a("")
    a("-- CERTIFIABILITY " + "-" * 59)
    ce = rep["certifiability"]
    ca = ce["crash_axis"]
    a(f"  certifiable                : {ce['certifiable']}")
    a(f"  verdict                    : {ce['verdict']}")
    a(f"  binding axis               : {ce['binding_axis']}")
    a(f"  crash episodes completed   : {ca['completed']} of {ca['required_before_any_verdict']} "
      f"required for ANY verdict")
    a(f"  remaining for a verdict    : {ca['remaining_before_any_verdict']} crashes "
      f"(~{ca['expected_years_before_any_verdict']:.0f} years at 1 per "
      f"{ca['expected_years_per_crash']:.0f})")
    a("  power table (T13 effect size 6.00 pp, sd 6.84, n=3):")
    for row in ca["power_table"]:
        a(f"      {row['power']:.0%} power -> {row['crashes_required']:.1f} crashes total, "
          f"{row['crashes_remaining']:.1f} to go, ~{row['expected_years_remaining']:.0f} years")
    sa = ce["session_axis"]
    inp = (ce["power_arithmetic"]["inputs_that_are_not_results"].get("paired_excess_vs_N1")
           or {})
    if sa.get("sessions_remaining_for_FG5") is not None:
        a(f"  FG5 (DSR>=0.95, 1 trial)   : needs ~{sa['sessions_required_for_FG5_DSR_0.95']:.0f} "
          f"settled sessions in total, {sa['sessions_remaining_for_FG5']:.0f} to go "
          f"(~{sa['years_remaining_for_FG5']:.1f} years) at the CURRENT estimate")
        a(f"    (power input, NOT a result: paired-vs-N1 DSR now "
          f"{inp.get('dsr_now_at_1_declared_trial', float('nan')):.4f}, "
          f"annualised paired Sharpe {inp.get('annualised_sharpe', float('nan')):.4f}. "
          f"FG5 cannot be READ before the crash minimum regardless of this number.)")
    elif sa.get("why"):
        a(f"  FG5 (DSR>=0.95, 1 trial)   : {sa['why']}")
    elif inp.get("reason"):
        a(f"  FG5 (DSR>=0.95, 1 trial)   : not estimated -- {inp['reason']}")
    a("")
    a(f"  {ca['the_honest_expectation']}")
    a("")
    a("-- GATES (frozen order; 'NOT READABLE' is a state, not a soft pass) " + "-" * 9)
    g = rep.get("gates") or {}
    for key in ("FG4_execution_rail", "FG3_fidelity", "FG1_drawdown_vs_N1",
                "FG2_delta_cagr_vs_N1", "FG5_dsr"):
        blk = g.get(key) or {}
        a(f"  {key:<22} : {blk.get('state', '?')}")
        a(f"    threshold                : {blk.get('threshold', '?')}")
        if blk.get("size_half"):
            a(f"    size half so far         : {blk['size_half']}")
    a(f"  overall                : {g.get('verdict', '?')}")
    a("")
    a("-- CLAIMS " + "-" * 67)
    a(f"  licensed                   : {rep['claims_licensed'] or 'NONE'}")
    for c in rep["claims_explicitly_not_licensed"]:
        a(f"  NOT licensed               : {c}")
    a("")
    a("-- ITERATION " + "-" * 64)
    a(f"  {rep['iteration_protocol']}")
    a("")
    a("STATUS LINE: " + rep["status_line"])
    a("=" * 78)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Selftest -- hermetic, no network, no real ledger
# ---------------------------------------------------------------------------

def _synthetic_sessions(n=400, crash_at=200, crash_len=40):
    """A deterministic series that contains one >=20% benchmark crash. No RNG."""
    out = []
    day = dt.date(2026, 1, 2)
    px = 400.0
    prev_w = 0.0
    for i in range(n):
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        if crash_at <= i < crash_at + crash_len:
            r = -0.008
        else:
            r = 0.0012 if (i * 7) % 3 else -0.0006
        px_prev = px
        px *= (1.0 + r)
        w = 0.55 if crash_at - 10 <= i < crash_at + crash_len + 20 else 0.85
        r_cash = 0.04 / 252.0
        out.append({
            "date": day.isoformat(), "status": "settled",
            "weight_in_force": w, "weight_previous": prev_w,
            "index_close": px, "index_close_prev": px_prev, "r_index": r,
            "r_cash_accrual": r_cash,
            "cost": {"total_bp": 0.0, "total_fraction": 0.0},
            "cost_if_taker_rail": {"total_bp": 0.0},
            "r_model_withcash": w * r + (1 - w) * r_cash,
            "r_model_excash": w * r,
            "r_benchmark": r,
        })
        prev_w = w
        day += dt.timedelta(days=1)
    eq = {"model_withcash": 1.0, "model_excash": 1.0, "benchmark": 1.0}
    for s in out:
        eq["model_withcash"] *= 1 + s["r_model_withcash"]
        eq["model_excash"] *= 1 + s["r_model_excash"]
        eq["benchmark"] *= 1 + s["r_benchmark"]
        s["equity"] = dict(eq)
    return out


def _selftest() -> int:
    sessions = _synthetic_sessions()
    r_f = [s["r_model_withcash"] for s in sessions]
    vol_f = _annual_vol(r_f)
    w1 = match_weight(sessions, vol_f)
    r_n1 = constant_weight_curve(sessions, w1)
    vol_n1 = _annual_vol(r_n1)
    episodes = crash_episodes(sessions)

    dd = drawdown_block(sessions)
    cert = certifiability_block(sessions, [])

    guard_refused = False
    try:
        _refuse_if_protected(RESEARCH / "T4_FORWARD_LOG.jsonl")
    except Refused:
        guard_refused = True

    out = {
        "framing": FRAMING,
        "synthetic_sessions": len(sessions),
        "vol_matched": {"strategy": vol_f, "null": vol_n1,
                        "matched_weight": w1,
                        "agree_within_1e-6": abs(vol_f - vol_n1) < 1e-6},
        "crash_episodes_detected": len(episodes),
        "delta_maxdd_vs_N1_pp": (dd["vs_vol_matched_null_N1"] or {}).get("delta_maxdd_pp"),
        "delta_maxdd_vs_benchmark_pp":
            dd["vs_benchmark_DIAGNOSTIC_ONLY"]["delta_maxdd_pp"],
        "certifiable": cert["certifiable"],
        "ledger_write_refused": guard_refused,
    }
    problems = []
    if not out["vol_matched"]["agree_within_1e-6"]:
        problems.append("the vol-matched null does not match the strategy's realised volatility")
    if out["crash_episodes_detected"] < 1:
        problems.append("the synthetic series contains a >=20% benchmark crash and none was found")
    if out["certifiable"]:
        problems.append("certifiable came back True; this evaluator may never emit that")
    if not guard_refused:
        problems.append("the write guard did not refuse a ledger path")
    out["problems"] = problems
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    if problems:
        raise Refuse("selftest failed: " + "; ".join(problems))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="scripts.trading_bot.forward_eval",
                                description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("report", help="evaluate a registered forward test")
    rep.add_argument("--strategy", default=None, help="register id, e.g. T4")
    rep.add_argument("--ledger", default=None, help="override the ledger path (read-only)")
    rep.add_argument("--json", action="store_true", help="machine-readable output")
    rep.add_argument("--write", nargs="?", const=str(DEFAULT_REPORT_JSON), default=None,
                     help="also write the JSON report here (never a ledger or state file)")
    rep.add_argument("--write-status", nargs="?", const=str(STATUS_TXT), default=None,
                     help="also write the one-line status here, for the dashboard")

    sl = sub.add_parser("status-line", help="one line for the dashboard")
    sl.add_argument("--strategy", default=None)
    sl.add_argument("--write", nargs="?", const=str(STATUS_TXT), default=None)

    ls = sub.add_parser("list", help="registered forward tests")
    ls.add_argument("--json", action="store_true")

    sub.add_parser("selftest", help="hermetic wiring check; no network, no ledger")

    args = p.parse_args(argv)

    if args.command == "selftest":
        return _selftest()

    if args.command == "list":
        reg = load_register()
        if args.json:
            json.dump(reg, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(reg.get("note", ""))
            for e in reg["strategies"]:
                print(f"  {e['id']:<6} {e.get('status','?'):<10} {e.get('rule_id','')}")
                print(f"         ledger  {e['ledger']}")
                print(f"         prereg  {e['preregistration']}")
        return 0

    report = evaluate(getattr(args, "strategy", None),
                      ledger_path=getattr(args, "ledger", None))

    if args.command == "status-line":
        print(report["status_line"])
        if args.write:
            _write(pathlib.Path(args.write), report["status_line"] + "\n")
        return 0

    if args.json:
        json.dump(report, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(render_text(report))
    if args.write:
        path = _write(pathlib.Path(args.write),
                      json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
        print(f"\n[written] {path}")
    if args.write_status:
        path = _write(pathlib.Path(args.write_status), report["status_line"] + "\n")
        print(f"[written] {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        raise SystemExit(2)
