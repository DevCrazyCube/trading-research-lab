#!/usr/bin/env python3
"""MEME ARENA — cohort separation (Phase-0 #4). One place that splits a ledger's terminal rows into the
four cohorts the honest read requires, so a measurement failure is NEVER scored as a rug or a loss, and a
control never contaminates the primary statistic:

  PRIMARY               — real money-book trades (incl. a Helius-confirmed RUG as a real -100% loss).
  CONTROL               — the null baseline (e.g. CONTROL_PROXY_FAIL); reported separately, never in primary N.
  MEASUREMENT_FAILURE   — right-censored: the price/feed was unreadable but the coin was alive (or the arbiter
                          could not positively confirm a rug). EXCLUDED from primary N.
  STRATEGY_VOID         — the strategy declined to trade (coverage-fail, entry-lag, exit-capacity) — not an
                          outcome, just a screened candidate.

`censored_fraction` = MEASUREMENT_FAILURE / (PRIMARY + MEASUREMENT_FAILURE) is a pre-registered VALIDITY
gate: right-censoring here is NOT independent of outcome (an unpriceable coin is somewhat more likely to be
a real rug), so a high censored fraction invalidates the read, and the censored cohort's would-be returns
are reported as a sensitivity bound rather than silently dropped. Pure functions; no I/O.
"""
from __future__ import annotations

MEASUREMENT_REASONS = {"MEASUREMENT_FAILURE", "MEASUREMENT_VOID", "INDETERMINATE_VOID"}
STRATEGY_VOID_REASONS = {"COVERAGE_VOID", "ENTRY_LAG_EXCEEDED", "EXIT_CAPACITY_VOID",
                         "STRESS_TEST_FAILED", "NO_ACTIVE_MARKET", "VOID"}
CENSORED_FRACTION_LIMIT = 0.35        # frozen: > this invalidates the read


def _is_control(row: dict) -> bool:
    coh = (row.get("cohort") or "").upper()
    return "CONTROL" in coh


def split_cohorts(resolved_rows: list[dict], void_rows: list[dict] | None = None) -> dict:
    """Bucket terminal rows. `resolved_rows` are kind=='resolved'; `void_rows` are kind=='void'."""
    void_rows = void_rows or []
    primary, control, measurement, strategy_void = [], [], [], []
    for r in resolved_rows:
        (control if _is_control(r) else primary).append(r)
    for v in void_rows:
        reason = (v.get("reason") or "").upper()
        (measurement if reason in MEASUREMENT_REASONS else strategy_void).append(v)
    n_prim, n_meas = len(primary), len(measurement)
    censored_fraction = (n_meas / (n_prim + n_meas)) if (n_prim + n_meas) else 0.0
    return {
        "primary": primary, "control": control,
        "measurement_failures": measurement, "strategy_voids": strategy_void,
        "primary_n": n_prim, "control_n": len(control),
        "measurement_failure_n": n_meas, "strategy_void_n": len(strategy_void),
        "censored_fraction": round(censored_fraction, 4),
        "censored_valid": censored_fraction <= CENSORED_FRACTION_LIMIT,
        # sensitivity bound: what the primary mean would be if every censored trade were a total loss
        "primary_mean": (sum(r["net_return"] for r in primary) / n_prim) if n_prim else None,
        "primary_mean_if_censored_all_rug": (
            (sum(r["net_return"] for r in primary) + n_meas * -1.0) / (n_prim + n_meas))
            if (n_prim + n_meas) else None,
    }


if __name__ == "__main__":
    resolved = [
        {"net_return": 0.2, "cohort": "PRIMARY"},
        {"net_return": -0.12, "cohort": "PRIMARY"},
        {"net_return": -1.0, "cohort": "PRIMARY", "reason": "RUG_CONFIRMED"},   # a real rug = primary loss
        {"net_return": -0.5, "cohort": "CONTROL_PROXY_FAIL"},                   # control, not primary
    ]
    voids = [
        {"reason": "MEASUREMENT_FAILURE"},                                       # right-censored
        {"reason": "MEASUREMENT_FAILURE"},
        {"reason": "COVERAGE_VOID"},                                            # strategy screen
    ]
    c = split_cohorts(resolved, voids)
    assert c["primary_n"] == 3 and c["control_n"] == 1
    assert c["measurement_failure_n"] == 2 and c["strategy_void_n"] == 1
    # censored fraction = 2 / (3+2) = 0.4 > 0.35 -> invalid read
    assert abs(c["censored_fraction"] - 0.4) < 1e-9 and not c["censored_valid"]
    assert abs(c["primary_mean"] - (0.2 - 0.12 - 1.0) / 3) < 1e-9
    # a measurement failure is NEVER auto-scored as a loss (that's the whole point) but IS bounded:
    assert c["primary_mean_if_censored_all_rug"] < c["primary_mean"]
    print("cohorts.py self-check OK: primary/control/measurement/void split + censored-fraction validity gate")
