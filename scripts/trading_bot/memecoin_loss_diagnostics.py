#!/usr/bin/env python3
"""Post-hoc loss attribution for every local memecoin paper-trade experiment.

This is a DESCRIPTIVE diagnostic, not a backtest or a new strategy result.  It reads immutable byte
snapshots, records their hashes, and explains where recorded/stressed R was lost by cost component,
exit reason, and pre-entry feature slice.  Any threshold suggested by these rows is contaminated and
must be frozen as a new forward experiment before it can become evidence.

PAPER/RESEARCH ONLY.  No network, wallet, signer, order, transfer, or on-chain write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trading_bot.memecoin_trade_audit import (
    _dedupe_resolutions,
    _full_loss_r,
    _read_json_object,
    _read_jsonl,
    _r_summary,
    _round,
    _snapshot_source,
    _sniper_current_r,
)


DEFAULT_JSON = ROOT / "research" / "trading_bot" / "MEMECOIN_LOSS_DIAGNOSTICS.json"
DEFAULT_MD = ROOT / "research" / "trading_bot" / "MEMECOIN_LOSS_DIAGNOSTICS.md"
SCHEMA_VERSION = 1


def _mean(values: Iterable[float]) -> float | None:
    xs = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return statistics.fmean(xs) if xs else None


def _median(values: Iterable[float]) -> float | None:
    xs = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return statistics.median(xs) if xs else None


def _maximum_unavailable_rate_for_break_even(
    executable_mean_r: float | None,
    unavailable_mean_r: float | None,
) -> float:
    """Mixture boundary p where (1-p)*E[executable] + p*E[unavailable] == 0."""
    unavailable_loss = abs(float(unavailable_mean_r or 0.0))
    if executable_mean_r is None or executable_mean_r <= 0 or unavailable_loss <= 0:
        return 0.0
    return float(executable_mean_r) / (float(executable_mean_r) + unavailable_loss)


def _reason_attribution(records: list[dict], r_field: str = "stress_r") -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("reason") or "UNKNOWN")].append(record)
    total_negative = sum(max(0.0, -float(r[r_field])) for r in records if r.get(r_field) is not None)
    result: dict[str, dict] = {}
    for reason, rows in sorted(grouped.items()):
        rs = [float(r[r_field]) for r in rows if r.get(r_field) is not None]
        negative = sum(max(0.0, -x) for x in rs)
        result[reason] = {
            **_r_summary(rs),
            "negative_R_abs": _round(negative),
            "share_of_all_negative_R": _round(negative / total_negative) if total_negative else None,
            "median_hold_seconds": _round(_median(r.get("hold_seconds") for r in rows)),
        }
    return result


def _component_summary(records: list[dict]) -> dict:
    fields = ("gross_R", "entry_slippage_R", "toll_R", "tip_R", "net_R")
    out: dict[str, Any] = {"n": len(records)}
    for field in fields:
        xs = [float(row[field]) for row in records if row.get(field) is not None]
        out[f"mean_{field}"] = _round(_mean(xs))
        out[f"sum_{field}"] = _round(sum(xs)) if xs else None
    errors = [abs(float(r["net_R"]) - float(r["recorded_R"])) for r in records
              if r.get("net_R") is not None and r.get("recorded_R") is not None]
    out["max_abs_reconstruction_error_R"] = _round(max(errors)) if errors else None
    return out


def _fixed_slices(records: list[dict], field: str, bounds: list[float]) -> list[dict]:
    """Descriptive fixed bins. Boundaries are declared in code, not fitted quantiles."""
    result: list[dict] = []
    low = -math.inf
    for high in [*bounds, math.inf]:
        rows = [r for r in records if r.get(field) is not None and low <= float(r[field]) < high]
        label = f"[{low if math.isfinite(low) else '-inf'}, {high if math.isfinite(high) else 'inf'})"
        result.append({
            "range": label,
            "n": len(rows),
            "stress": _r_summary(r.get("stress_r") for r in rows),
        })
        low = high
    return result


def _audit_legacy_sniper(root: Path) -> tuple[dict, list[dict]]:
    cache = root / "research" / "data" / "sniper_cache"
    variants: dict[str, dict] = {}
    sources: list[dict] = []
    for path in sorted(cache.glob("live_trades*.jsonl")):
        rows, errors, snapshot = _read_jsonl(path)
        rows, duplicates = _dedupe_resolutions(rows)
        name = path.stem.removeprefix("live_trades_")
        if name == "live_trades":
            name = "legacy"
        records: list[dict] = []
        for row in rows:
            recost = _sniper_current_r(row)
            if recost is None:
                continue
            records.append({
                "reason": row.get("exit_reason") or row.get("resolution_reason") or "UNKNOWN",
                "stress_r": recost["current_full_cost_R"],
                "gross_R": recost["gross_R"],
                "toll_R": recost["gross_R"] - recost["toll_only_R"],
                "tip_R": recost["toll_only_R"] - recost["current_full_cost_R"],
                "net_R": recost["current_full_cost_R"],
                "recorded_R": row.get("realized_r"),
                "usd_size": row.get("usd_size"),
            })
        gross_positive_net_negative = sum(
            r["gross_R"] > 0 and r["net_R"] <= 0 for r in records)
        variants[name] = {
            "rows": len(rows),
            "duplicates": duplicates,
            "cost_components_current_code": _component_summary(records),
            "exit_reason_current_cost_attribution": _reason_attribution(records),
            "median_usd_notional": _round(_median(r.get("usd_size") for r in records)),
            "gross_positive_but_net_negative": gross_positive_net_negative,
            "gross_positive_but_net_negative_rate": (
                _round(gross_positive_net_negative / len(records)) if records else None),
        }
        sources.append(_snapshot_source(path, root, snapshot) | {"parse_errors": errors})
    return variants, sources


def _event_component(entry: dict, outcome: dict) -> dict:
    try:
        entry_fill = entry["entry_fill"]
        exit_fill = outcome["exit_fill"]
        entry_price = float(entry_fill["price_usd"])
        exit_price = float(exit_fill["price_usd"])
        size = float(entry_fill["usd_size"])
        risk = float(entry["strategy_config"]["catastrophe_frac"])
        ref = float(entry["signal"]["ref_price_usd"])
        gross_r = (exit_price / entry_price - 1.0) / risk
        toll_r = ((float(entry_fill.get("toll_bps", 0.0)) + float(exit_fill.get("toll_bps", 0.0)))
                  / 10_000.0) / risk
        tip_r = ((float(entry_fill.get("tip_usd", 0.0)) + float(exit_fill.get("tip_usd", 0.0)))
                 / size) / risk
        entry_slip_r = ((entry_price / ref) - 1.0) / risk if ref > 0 else None
        return {
            "gross_R": gross_r,
            "entry_slippage_R": entry_slip_r,
            "toll_R": toll_r,
            "tip_R": tip_r,
            "net_R": gross_r - toll_r - tip_r,
            "usd_size": size,
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return {}


def _audit_event_sniper(root: Path) -> tuple[dict, list[dict]]:
    cache = root / "research" / "data" / "sniper_cache"
    variants: dict[str, dict] = {}
    sources: list[dict] = []
    for path in sorted(cache.glob("live_events_v3_core_*.jsonl")):
        rows, errors, snapshot = _read_jsonl(path)
        name = path.stem.removeprefix("live_events_")
        entries = {str(r.get("frozen_sha256")): r for r in rows if r.get("kind") == "entry"}
        terminal: dict[str, dict] = {}
        duplicate_terminal = 0
        for row in rows:
            if row.get("kind") != "resolution" or row.get("status") not in {"RESOLVED", "INVALIDATED"}:
                continue
            key = str(row.get("frozen_sha256"))
            if key in terminal:
                duplicate_terminal += 1
                continue
            terminal[key] = row
        records: list[dict] = []
        for key, outcome in terminal.items():
            entry = entries.get(key)
            if not entry:
                continue
            component = _event_component(entry, outcome)
            entry_fill = entry.get("entry_fill") or {}
            exit_fill = outcome.get("exit_fill") or {}
            hold = None
            try:
                hold = float(exit_fill["ts"]) - float(entry_fill["ts"])
            except (KeyError, TypeError, ValueError):
                pass
            signal = entry.get("signal") or {}
            records.append({
                "reason": outcome.get("resolution_reason") or "UNKNOWN",
                "recorded_R": outcome.get("realized_r"),
                "stress_r": outcome.get("stress_realized_r"),
                "hold_seconds": hold,
                "surge_bps": signal.get("surge_bps"),
                "buy_frac": signal.get("buy_frac"),
                "liq_usd_per_s": signal.get("liq_usd_per_s"),
                **component,
            })
        rs = [float(r["stress_r"]) for r in records if r.get("stress_r") is not None]
        initial_equity = 1000.0
        pnl = sum(float(r.get("realized_pnl_usd") or 0.0) for r in terminal.values())
        terminal_n = len(terminal)
        stress_mean = _mean(rs)
        gate_pass = bool(
            terminal_n >= 100 and stress_mean is not None and stress_mean > 0
            and initial_equity + pnl > initial_equity
        )
        feature_slices = {
            "surge_bps": _fixed_slices(records, "surge_bps", [400.0, 800.0, 1500.0, 3000.0]),
            "buy_frac": _fixed_slices(records, "buy_frac", [0.65, 0.75, 0.85, 0.95]),
            "liq_usd_per_s": _fixed_slices(records, "liq_usd_per_s", [15.0, 30.0, 75.0, 150.0, 500.0]),
            "usd_size": _fixed_slices(records, "usd_size", [2.000001, 5.0, 10.0, 20.0, 30.000001]),
        }
        positive_slices_n20 = [
            f"{feature}:{bucket['range']}"
            for feature, buckets in feature_slices.items()
            for bucket in buckets
            if bucket["n"] >= 20 and (bucket["stress"].get("mean_R") or 0.0) > 0
        ]
        variants[name] = {
            "entries": len(entries),
            "terminal": terminal_n,
            "open": len(set(entries) - set(terminal)),
            "duplicate_terminal": duplicate_terminal,
            "stress": _r_summary(rs),
            "realized_equity_usd": _round(max(0.0, initial_equity + pnl)),
            "frozen_gate_n": 100,
            "frozen_gate_reached": terminal_n >= 100,
            "frozen_gate_pass": gate_pass,
            "cost_components": _component_summary(records),
            "exit_reason_attribution": _reason_attribution(records),
            "minimum_notional_rows": sum(float(r.get("usd_size") or math.inf) <= 2.000001 for r in records),
            "minimum_notional_rate": _round(
                sum(float(r.get("usd_size") or math.inf) <= 2.000001 for r in records) / len(records)
            ) if records else None,
            "feature_slices_posthoc": feature_slices,
            "positive_fixed_feature_slices_with_n_at_least_20": positive_slices_n20,
            "below_balanced_surge_threshold_entries": sum(
                float(r.get("surge_bps") or math.inf) < 400.0 for r in records),
            "below_balanced_liquidity_threshold_entries": sum(
                float(r.get("liq_usd_per_s") or math.inf) < 15.0 for r in records),
            "unavailable_entry_feature": (
                "seller count / unique seller identity was not persisted in V3 entries, so the exitability "
                "hypothesis cannot be reconstructed post hoc from this ledger"
            ),
        }
        sources.append(_snapshot_source(path, root, snapshot) | {"parse_errors": errors})
    return variants, sources


def _memebot_stress_r(row: dict, entry: dict | None) -> float | None:
    if entry and (row.get("resolution_reason") == "UNEXITABLE_TIMEOUT" or row.get("realized_r") is None):
        return _full_loss_r(entry)
    try:
        return float(row["realized_r"]) if row.get("realized_r") is not None else None
    except (TypeError, ValueError):
        return None


def _feed_features(entry: dict) -> dict:
    feed = entry.get("feed_snapshot") or {}
    return {
        "fdv_usd": feed.get("fdv_usd"),
        "reserve_usd": feed.get("reserve_usd"),
        "buyers": feed.get("buyers"),
        "sellers": feed.get("sellers"),
        "buys": feed.get("buys"),
        "age_minutes": feed.get("age_minutes"),
    }


def _audit_memebot(root: Path) -> tuple[dict, list[dict]]:
    from scripts.trading_bot.memebot.frozen import ACTIVE_INSTRUMENTS, frozen_spec

    instruments: dict[str, dict] = {}
    sources: list[dict] = []
    for instrument_id in ACTIVE_INSTRUMENTS:
        spec = frozen_spec(instrument_id)
        entry_path = Path(spec["_paths"]["prereg_log"])
        resolution_path = Path(spec["_paths"]["resolution_log"])
        entries, entry_errors, entry_snapshot = _read_jsonl(entry_path)
        outcomes, resolution_errors, resolution_snapshot = _read_jsonl(resolution_path)
        outcomes = [r for r in outcomes if r.get("status") == "RESOLVED"]
        outcomes, duplicates = _dedupe_resolutions(outcomes)
        entry_by_hash = {str(e.get("setup_sha256")): e for e in entries if e.get("setup_sha256")}
        pass_records: list[dict] = []
        control_records: list[dict] = []
        for outcome in outcomes:
            entry = entry_by_hash.get(str(outcome.get("setup_sha256")))
            if not entry:
                continue
            record = {
                "reason": outcome.get("resolution_reason") or "UNKNOWN",
                "reported_r": outcome.get("realized_r"),
                "stress_r": _memebot_stress_r(outcome, entry),
                "hold_seconds": (
                    float(outcome["held_minutes"]) * 60.0
                    if outcome.get("held_minutes") is not None else None),
                **_feed_features(entry),
            }
            (control_records if outcome.get("control") else pass_records).append(record)
        unavailable_negative = sum(
            max(0.0, -float(r["stress_r"])) for r in pass_records
            if r["reason"] == "UNEXITABLE_TIMEOUT" and r.get("stress_r") is not None)
        all_negative = sum(max(0.0, -float(r["stress_r"])) for r in pass_records
                           if r.get("stress_r") is not None)
        unavailable = [float(r["stress_r"]) for r in pass_records
                       if r["reason"] == "UNEXITABLE_TIMEOUT" and r.get("stress_r") is not None]
        executable = [float(r["stress_r"]) for r in pass_records
                      if r["reason"] != "UNEXITABLE_TIMEOUT" and r.get("stress_r") is not None]
        executable_mean = _mean(executable)
        break_even_unavailable_rate = _maximum_unavailable_rate_for_break_even(
            executable_mean, _mean(unavailable))
        instruments[instrument_id] = {
            "entries": len(entries),
            "resolved": len(outcomes),
            "resolved_pass": len(pass_records),
            "resolved_control": len(control_records),
            "duplicates": duplicates,
            "reported_pass": _r_summary(r.get("reported_r") for r in pass_records),
            "stress_pass": _r_summary(r.get("stress_r") for r in pass_records),
            "stress_control": _r_summary(r.get("stress_r") for r in control_records),
            "exit_reason_attribution": _reason_attribution(pass_records),
            "unavailable_share_of_negative_R": (
                _round(unavailable_negative / all_negative) if all_negative else None),
            "exitability_economics": {
                "observed_unavailable_rate": _round(len(unavailable) / len(pass_records)) if pass_records else None,
                "mean_R_when_an_exit_mark_existed": _round(executable_mean),
                "mean_unavailable_loss_R": _round(_mean(unavailable)),
                "maximum_unavailable_rate_for_zero_expectancy_at_observed_conditional_means": (
                    _round(break_even_unavailable_rate)
                ),
                "label": "post-hoc working-hypothesis boundary, not a frozen screen threshold",
            },
            "frozen_minimum": int(spec.get("statistics", {}).get("N_min", 30)),
            "minimum_reached": len(pass_records) >= int(spec.get("statistics", {}).get("N_min", 30)),
            "feature_slices_posthoc": {
                "reserve_usd": _fixed_slices(pass_records, "reserve_usd", [3000.0, 5000.0, 10_000.0, 25_000.0]),
                "sellers": _fixed_slices(pass_records, "sellers", [1.0, 3.0, 5.0, 10.0]),
                "buyers": _fixed_slices(pass_records, "buyers", [10.0, 20.0, 40.0, 80.0]),
                "age_minutes": _fixed_slices(pass_records, "age_minutes", [2.0, 5.0, 10.0, 20.0]),
            },
        }
        sources += [
            _snapshot_source(entry_path, root, entry_snapshot) | {"parse_errors": entry_errors},
            _snapshot_source(resolution_path, root, resolution_snapshot) | {"parse_errors": resolution_errors},
        ]
    return instruments, sources


def _audit_genome_experiment(root: Path, experiment_id: str, directory: Path) -> tuple[dict, list[dict]]:
    ledger_dir = directory / "ledgers"
    pop_path, state_path = directory / "population.json", directory / "evo_state.json"
    pop, pop_errors, pop_snapshot = _read_json_object(pop_path)
    state, state_errors, state_snapshot = _read_json_object(state_path)
    sources = [
        _snapshot_source(pop_path, root, pop_snapshot) | {"parse_errors": pop_errors},
        _snapshot_source(state_path, root, state_snapshot) | {"parse_errors": state_errors},
    ]
    records: list[dict] = []
    ledger_count = 0
    for path in sorted(ledger_dir.glob("*.jsonl")):
        ledger_count += 1
        rows, errors, snapshot = _read_jsonl(path)
        sources.append(_snapshot_source(path, root, snapshot) | {"parse_errors": errors})
        entries = {str(r.get("setup_sha256")): r for r in rows if r.get("kind") == "entry"}
        outcomes = [r for r in rows if r.get("kind") == "resolution" and r.get("status") == "RESOLVED"]
        outcomes, _ = _dedupe_resolutions(outcomes)
        for outcome in outcomes:
            if outcome.get("control"):
                continue
            entry = entries.get(str(outcome.get("setup_sha256")))
            if not entry:
                continue
            records.append({
                "reason": outcome.get("resolution_reason") or "UNKNOWN",
                "reported_r": outcome.get("realized_r"),
                "stress_r": _memebot_stress_r(outcome, entry),
                "hold_seconds": (
                    float(outcome["held_minutes"]) * 60.0
                    if outcome.get("held_minutes") is not None else None),
            })
    unpriced = sum(r.get("reported_r") is None for r in records)
    registered = set(state.get("K_all_genome_ids_ever", []))
    return {
        "experiment_id": experiment_id,
        "ledger_arms": ledger_count,
        "active_arms": len(pop.get("active", [])),
        "K": len(registered),
        "pass_arm_observations": len(records),
        "priced_pass_arm_observations": len(records) - unpriced,
        "unpriced_pass_arm_observations": unpriced,
        "unpriced_rate": _round(unpriced / len(records)) if records else None,
        "reported_priced": _r_summary(r.get("reported_r") for r in records),
        "full_loss_stress": _r_summary(r.get("stress_r") for r in records),
        "exit_reason_attribution": _reason_attribution(records),
        "candidate_ids": sorted((state.get("candidates") or {}).keys()),
        "falsified_ids": sorted((state.get("falsified_on_fresh_slice") or {}).keys()),
        "confirmed_real": sorted((state.get("confirmed_real") or {}).keys()),
        "interpretation": (
            "counts are correlated genome-arm observations on shared pools, not independent trades or "
            "an investable portfolio"
        ),
    }, sources


def build_diagnostics(root: Path = ROOT) -> dict:
    legacy, legacy_sources = _audit_legacy_sniper(root)
    event, event_sources = _audit_event_sniper(root)
    memebot, memebot_sources = _audit_memebot(root)
    evo_pkg = root / "scripts" / "trading_bot" / "memebot_evo"
    genome_experiments: dict[str, dict] = {}
    genome_sources: list[dict] = []
    for experiment_id, directory in (
        ("v1_archive", evo_pkg / "v1_archive"),
        ("v2_current", evo_pkg),
    ):
        if directory.exists():
            result, sources = _audit_genome_experiment(root, experiment_id, directory)
            genome_experiments[experiment_id] = result
            genome_sources.extend(sources)

    best_event = max(
        event,
        key=lambda name: event[name]["stress"].get("mean_R") or -math.inf,
        default=None,
    )
    confirm = event.get("v3_core_confirm", {})
    balanced = event.get("v3_core_bal", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "all local memecoin paper ledgers, including archived evolutionary V1",
        "evidence_label": "verified recomputation from the byte snapshots in sources",
        "method_label": (
            "POST_HOC descriptive loss attribution; feature slices are contaminated and cannot be "
            "promoted without a new frozen forward experiment"
        ),
        "stress_assumption": "unavailable/unpriced terminal PASS = -100% before pinned toll",
        "sniper": {
            "legacy": legacy,
            "v3": event,
            "best_v3_arm_by_stress_mean_R": best_event,
            "all_v3_arms_failed_frozen_gate": bool(event) and all(
                row["frozen_gate_reached"] and not row["frozen_gate_pass"] for row in event.values()),
            "all_fixed_feature_slices_with_n20_nonpositive": bool(event) and all(
                not row["positive_fixed_feature_slices_with_n_at_least_20"] for row in event.values()),
            "confirmation_state_machine_diagnostic": {
                "confirm_entries": confirm.get("entries"),
                "balanced_entries": balanced.get("entries"),
                "confirm_entries_below_balanced_surge_threshold": confirm.get(
                    "below_balanced_surge_threshold_entries"),
                "confirm_entries_below_balanced_liquidity_threshold": confirm.get(
                    "below_balanced_liquidity_threshold_entries"),
                "finding": (
                    "CONFIRM was not a strict subset of BALANCED: after the five-second wait it rechecked "
                    "buy fraction only, and a failed confirmation re-armed before the base surge dequalified"
                ),
            },
            "sources": [*legacy_sources, *event_sources],
        },
        "memebot": {"instruments": memebot, "sources": memebot_sources},
        "genomes": {"experiments": genome_experiments, "sources": genome_sources},
        "decisions_supported_by_current_evidence": [
            "retire V3 from new paper entries: every arm passed N=100 and failed its frozen positive-stress gate",
            "do not promote any legacy MEMEBOT arm; FAST crossed N=30 and is honest-kill HALTED",
            "continue EXIT_V2 unchanged only until its frozen N=30 gate; current N is below its minimum",
            "keep EVO V2 unchanged until genomes mature; archived V1 produced no K-corrected stress clearer",
            "do not select a threshold from the post-hoc feature slices in this report",
        ],
        "open_execution_gap": (
            "these feeds store paper marks, not position-sized on-chain quotes, landing failures, or measured latency"
        ),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(report: dict) -> str:
    lines = [
        "# Memecoin loss diagnostics",
        "",
        f"Generated UTC: `{report['generated_utc']}`",
        "",
        "**Verified fact:** all figures are recomputed from the byte snapshots hash-pinned in the JSON.",
        "",
        "**Method warning:** this is post-hoc diagnosis. The fixed feature slices may explain losses, but "
        "they are contaminated and cannot become an entry rule without a new frozen forward cohort.",
        "",
        "## Why the legacy sniper lost",
        "",
        "| arm | n | gross mean R | toll drag R | tip drag R | current-cost mean R | median USD size | gross winners turned net losers |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in report["sniper"]["legacy"].items():
        c = row["cost_components_current_code"]
        lines.append(
            f"| {name} | {row['rows']} | {_fmt(c['mean_gross_R'])} | {_fmt(c['mean_toll_R'])} | "
            f"{_fmt(c['mean_tip_R'])} | {_fmt(c['mean_net_R'])} | {_fmt(row['median_usd_notional'])} | "
            f"{row['gross_positive_but_net_negative']} |"
        )

    lines += [
        "",
        "## Clean sniper V3",
        "",
        "| arm | terminal | open | stress mean R | paper equity USD | floor-size share | N100 gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in report["sniper"]["v3"].items():
        lines.append(
            f"| {name} | {row['terminal']} | {row['open']} | {_fmt(row['stress']['mean_R'])} | "
            f"{_fmt(row['realized_equity_usd'])} | {_fmt(row['minimum_notional_rate'])} | "
            f"{'PASS' if row['frozen_gate_pass'] else 'FAIL'} |"
        )
    confirm_diag = report["sniper"]["confirmation_state_machine_diagnostic"]
    lines += [
        "",
        f"Every fixed surge/buy-fraction/liquidity/notional slice with n≥20 remained non-positive: "
        f"**{report['sniper']['all_fixed_feature_slices_with_n20_nonpositive']}**. CONFIRM also was not "
        f"a strict BALANCED subset ({confirm_diag['confirm_entries']} vs "
        f"{confirm_diag['balanced_entries']} entries): "
        f"{confirm_diag['confirm_entries_below_balanced_surge_threshold']} entries fired below +400 bps "
        f"and {confirm_diag['confirm_entries_below_balanced_liquidity_threshold']} below $15/s after "
        "the confirmation wait.",
    ]
    lines += [
        "",
        "### V3 loss by exit reason",
        "",
        "| arm | reason | n | mean R | sum R | share of negative R | median hold s |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in report["sniper"]["v3"].items():
        for reason, stats in row["exit_reason_attribution"].items():
            lines.append(
                f"| {name} | {reason} | {stats['n']} | {_fmt(stats['mean_R'])} | "
                f"{_fmt(stats['sum_R'])} | {_fmt(stats['share_of_all_negative_R'])} | "
                f"{_fmt(stats['median_hold_seconds'])} |"
            )

    lines += [
        "",
        "## Frozen MEMEBOT arms",
        "",
        "| arm | PASS n | reported mean R | honest stress mean R | unavailable share of negative R | minimum |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in report["memebot"]["instruments"].items():
        lines.append(
            f"| {name} | {row['resolved_pass']} | {_fmt(row['reported_pass']['mean_R'])} | "
            f"{_fmt(row['stress_pass']['mean_R'])} | {_fmt(row['unavailable_share_of_negative_R'])} | "
            f"{row['frozen_minimum']} |"
        )
    exit_v2 = report["memebot"]["instruments"].get("MEMEBOT_EXIT_V2")
    if exit_v2:
        economics = exit_v2["exitability_economics"]
        lines += [
            "",
            "### EXIT_V2 loss by exit reason",
            "",
            "| reason | n | mean stress R | sum stress R | share of negative R |",
            "|---|---:|---:|---:|---:|",
        ]
        for reason, stats in exit_v2["exit_reason_attribution"].items():
            lines.append(
                f"| {reason} | {stats['n']} | {_fmt(stats['mean_R'])} | {_fmt(stats['sum_R'])} | "
                f"{_fmt(stats['share_of_all_negative_R'])} |"
            )
        lines += [
            "",
            f"At the observed conditional payoffs, EXIT_V2 needs unavailable exits below "
            f"**{_fmt(economics['maximum_unavailable_rate_for_zero_expectancy_at_observed_conditional_means'])}** "
            f"to break even; observed was **{_fmt(economics['observed_unavailable_rate'])}**. This is a "
            "post-hoc working-hypothesis boundary, not a licensed new threshold.",
        ]

    lines += [
        "",
        "## Evolutionary experiments",
        "",
        "| experiment | arms | PASS arm-observations | unpriced rate | reported priced mean R | stress mean R | confirmed |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in report["genomes"]["experiments"].items():
        lines.append(
            f"| {name} | {row['ledger_arms']} | {row['pass_arm_observations']:,} | "
            f"{_fmt(row['unpriced_rate'])} | {_fmt(row['reported_priced']['mean_R'])} | "
            f"{_fmt(row['full_loss_stress']['mean_R'])} | {','.join(row['confirmed_real']) or 'none'} |"
        )

    lines += [
        "",
        "## Evidence-supported actions",
        "",
    ]
    lines += [f"- {item}." for item in report["decisions_supported_by_current_evidence"]]
    lines += [
        "",
        f"Open execution gap: {report['open_execution_gap']}.",
        "",
    ]
    return "\n".join(lines)


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload)
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)
    report = build_diagnostics(ROOT)
    markdown = render_markdown(report)
    if not args.no_write:
        _atomic_write(args.json, json.dumps(report, indent=2, sort_keys=True) + "\n")
        _atomic_write(args.markdown, markdown)
    if args.stdout:
        print(markdown)
    else:
        print(json.dumps({
            "generated_utc": report["generated_utc"],
            "v3_all_failed": report["sniper"]["all_v3_arms_failed_frozen_gate"],
            "best_v3_arm": report["sniper"]["best_v3_arm_by_stress_mean_R"],
            "json": str(args.json),
            "markdown": str(args.markdown),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
