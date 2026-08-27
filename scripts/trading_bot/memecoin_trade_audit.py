#!/usr/bin/env python3
"""Reproducible, read-only audit of every local memecoin paper-trade ledger.

Scopes
------
* sniper: every ``research/data/sniper_cache/live_trades*.jsonl`` resolution ledger;
* MEMEBOT: every active frozen instrument plus the explicitly quarantined EXIT ledger;
* genomes: every ledger on disk, including inactive/killed genomes.

The source ledgers are never edited.  The report publishes a SHA-256 and byte count for every input,
keeps the engines separate (parallel arms are not one investable portfolio), and supplies two views:

``reported``
    The R stored by the engine under the rule that was active when the row was written.

``full_loss_stress``
    An unavailable exit is a -100% position return before the already-pinned round-trip toll.  A
    sub-minute ``UNPRICED`` row is included under the same conservative bound instead of disappearing
    from selection.  This is a stress bound, not a claim that every unavailable observation lost 100%.

For sniper rows, the script also recomputes R under the *current* cost code.  This exposes historical
ledgers that mix gross, toll-only and toll+tip regimes, and the SOL/USD unit mismatch where a fixed
SOL-denominated tip was charged to a paper notional recorded as a few cents.

PAPER/RESEARCH ONLY.  No network, wallet, order, signing, or on-chain write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_JSON = ROOT / "research" / "trading_bot" / "MEMECOIN_TRADE_AUDIT.json"
DEFAULT_MD = ROOT / "research" / "trading_bot" / "MEMECOIN_TRADE_AUDIT.md"
SCHEMA_VERSION = 1


def _mean(values: Iterable[float]) -> float | None:
    xs = list(values)
    return statistics.fmean(xs) if xs else None


def _median(values: Iterable[float]) -> float | None:
    xs = list(values)
    return statistics.median(xs) if xs else None


def _round(value: Any, digits: int = 6) -> Any:
    return round(value, digits) if isinstance(value, float) and math.isfinite(value) else value


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _source(path: Path, root: Path) -> dict:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_jsonl(path: Path) -> tuple[list[dict], list[dict], dict]:
    rows: list[dict] = []
    errors: list[dict] = []
    # Read a single byte snapshot.  Writers may append later, but cannot alter this in-memory cohort.
    payload = path.read_bytes() if path.exists() else b""
    for lineno, raw in enumerate(payload.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append({"line": lineno, "error": type(exc).__name__})
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            errors.append({"line": lineno, "error": "non_object_json"})
    snapshot = {"exists": path.exists(), "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()}
    return rows, errors, snapshot


def _snapshot_source(path: Path, root: Path, snapshot: dict) -> dict:
    return {"path": str(path.relative_to(root)), **snapshot}


def _dedupe_resolutions(rows: list[dict]) -> tuple[list[dict], int]:
    out: list[dict] = []
    seen: set[str] = set()
    duplicates = 0
    for row in rows:
        key = row.get("setup_sha256") or row.get("frozen_sha256")
        if key and key in seen:
            duplicates += 1
            continue
        if key:
            seen.add(str(key))
        out.append(row)
    return out, duplicates


def _reason_counts(rows: Iterable[dict], field: str = "resolution_reason") -> dict:
    counts = Counter(str(row.get(field) or row.get("exit_reason") or "UNKNOWN") for row in rows)
    return dict(sorted(counts.items()))


def _r_summary(rs: Iterable[float]) -> dict:
    xs = [float(x) for x in rs if x is not None and math.isfinite(float(x))]
    wins = [x for x in xs if x > 0]
    losses = [x for x in xs if x <= 0]
    sd = statistics.stdev(xs) if len(xs) >= 2 else None
    se = (sd / math.sqrt(len(xs))) if sd is not None else None
    return {
        "n": len(xs),
        "mean_R": _round(_mean(xs)),
        "median_R": _round(_median(xs)),
        "sum_R": _round(sum(xs)),
        "win_rate": _round(len(wins) / len(xs)) if xs else None,
        "best_R": _round(max(xs)) if xs else None,
        "worst_R": _round(min(xs)) if xs else None,
        "avg_win_R": _round(_mean(wins)),
        "avg_loss_R_abs": _round(_mean(abs(x) for x in losses)),
        "standard_error_R": _round(se),
        "t_stat": _round((statistics.fmean(xs) / se) if se and se > 0 else None),
        "top_winner_share_of_positive_R": (
            _round(max(wins) / sum(wins)) if wins and sum(wins) > 0 else None
        ),
    }


def _full_loss_r(entry: dict) -> float | None:
    try:
        stop = float(entry["stop_frac"])
        toll = float(entry.get("toll_per_side", 0.0))
    except (KeyError, TypeError, ValueError):
        return None
    if stop <= 0:
        return None
    return (-1.0 - 2.0 * toll) / stop


def _paper_bankroll(rows: list[dict], entries: dict[str, dict], *, stress: bool) -> float | None:
    """Fixed-notional paper-bankroll proxy used by MEMEBOT/evo (open positions excluded).

    Their entry builders size every position from the original 10 SOL, not the evolving balance, so
    additive realised P&L is the faithful reconstruction.  It is still a paper proxy: simultaneous
    exposure, failed landing and opportunity cost are not represented by these ledgers.
    """
    if not entries:
        return None
    first = next(iter(entries.values()))
    bankroll = 10.0
    # Frozen MEMEBOT entries carry the actual size; fall back only for malformed historical rows.
    pnl = 0.0
    for row in rows:
        entry = entries.get(str(row.get("setup_sha256")))
        if not entry:
            continue
        r = row.get("realized_r")
        if stress and (row.get("resolution_reason") == "UNEXITABLE_TIMEOUT" or r is None):
            r = _full_loss_r(entry)
        if r is None:
            continue
        try:
            pnl += float(entry.get("size_sol", 0.2)) * float(r) * float(entry["stop_frac"])
        except (KeyError, TypeError, ValueError):
            continue
    return _round(bankroll + pnl)


def _sniper_current_r(row: dict) -> dict | None:
    from scripts.trading_bot.sniper.execution import (
        DEFAULT_SOL_PRICE_USD,
        PAPER_TIP_SOL,
        venue_toll_bps,
    )
    from scripts.trading_bot.sniper.strategy import PRESETS

    try:
        entry = float(row["entry_price"])
        exit_price = float(row["exit_price"])
        usd_size = float(row["usd_size"])
    except (KeyError, TypeError, ValueError):
        return None
    if entry <= 0 or exit_price < 0 or usd_size <= 0:
        return None
    preset = str(row.get("preset") or "convex_core")
    cfg = PRESETS.get(preset, PRESETS["convex_core"])
    risk = float(cfg.catastrophe_frac)
    gross_return = exit_price / entry - 1.0
    toll_return = 2.0 * venue_toll_bps(row.get("venue")) / 10_000.0
    tip_return = 2.0 * PAPER_TIP_SOL * DEFAULT_SOL_PRICE_USD / usd_size
    return {
        "gross_R": gross_return / risk,
        "toll_only_R": (gross_return - toll_return) / risk,
        "current_full_cost_R": (gross_return - toll_return - tip_return) / risk,
        "gross_return": gross_return,
        "current_full_cost_return": gross_return - toll_return - tip_return,
        "round_trip_tip_fraction_of_notional": tip_return,
        "round_trip_toll_fraction_of_notional": toll_return,
    }


def audit_sniper(root: Path) -> dict:
    cache = root / "research" / "data" / "sniper_cache"
    files = sorted(cache.glob("live_trades*.jsonl"))
    sources: list[dict] = []
    variants: dict[str, dict] = {}
    all_rows: list[dict] = []
    parse_errors = 0
    for path in files:
        rows, errors, snapshot = _read_jsonl(path)
        parse_errors += len(errors)
        sources.append(_snapshot_source(path, root, snapshot) | {"parse_errors": errors})
        name = path.stem.removeprefix("live_trades_")
        if name == "live_trades":
            name = "legacy"
        rows, duplicates = _dedupe_resolutions(rows)
        enriched: list[tuple[dict, dict]] = []
        matches = Counter()
        for row in rows:
            recost = _sniper_current_r(row)
            if recost is None:
                continue
            reported = row.get("realized_r")
            if reported is not None:
                candidates = {
                    "gross": recost["gross_R"],
                    "toll_only": recost["toll_only_R"],
                    "toll_plus_tip": recost["current_full_cost_R"],
                }
                closest = min(candidates, key=lambda key: abs(float(reported) - candidates[key]))
                if abs(float(reported) - candidates[closest]) <= 0.002:
                    matches[closest] += 1
                else:
                    matches["other"] += 1
            enriched.append((row, recost))
            all_rows.append(row | {"_variant": name})

        reported_rs = [float(r["realized_r"]) for r, _ in enriched if r.get("realized_r") is not None]
        current_rs = [x["current_full_cost_R"] for _, x in enriched]
        tip_fracs = [x["round_trip_tip_fraction_of_notional"] for _, x in enriched]
        net_returns = [x["current_full_cost_return"] for _, x in enriched]
        variants[name] = {
            "rows": len(rows),
            "duplicates_by_freeze_hash": duplicates,
            "reported": _r_summary(reported_rs),
            "recomputed_current_cost": _r_summary(current_rs),
            "current_full_cost_mean_position_return": _round(_mean(net_returns)),
            "median_round_trip_tip_fraction_of_notional": _round(_median(tip_fracs)),
            "cost_regime_rows": dict(sorted(matches.items())),
            "exit_reasons": _reason_counts(rows),
            "first_opened_epoch": min((r.get("opened_ts") for r in rows if r.get("opened_ts")), default=None),
            "last_resolved_utc": max((str(r.get("resolved_utc")) for r in rows if r.get("resolved_utc")), default=None),
            "entry_commitment_recomputable": False,
            "entry_commitment_gap": (
                "resolution rows omit the frozen signal payload, entry toll/slip/tip and frozen UTC; "
                "their frozen_sha256 cannot be independently recomputed"
            ),
        }

    all_current = [_sniper_current_r(r) for r in all_rows]
    all_current = [x for x in all_current if x is not None]
    watchdog = root / "scripts" / "trading_bot" / "sniper" / "logs" / "watchdog.log"
    restarts = 0
    if watchdog.exists():
        restarts = sum(1 for line in watchdog.read_text(errors="replace").splitlines()
                       if "restarted" in line.lower())
        sources.append(_source(watchdog, root))
    cutover_path = root / "research" / "trading_bot" / "SNIPER_LEGACY_CUTOVER_2026-08-27.json"
    cutover = None
    if cutover_path.exists():
        cutover = json.loads(cutover_path.read_text())
        sources.append(_source(cutover_path, root))
    # V2 is a clean entry->terminal event ledger. Include expected paths even before the first forward
    # event so the audit makes the reset explicit instead of silently falling back to legacy rows.
    from scripts.trading_bot.sniper.paper_ledger import canonical_sha256
    from scripts.trading_bot.sniper.run import VARIANT_SPECS, V3_PREREG_SHA256

    v2_variants: dict[str, dict] = {}
    expected_names = {spec[0] for spec in VARIANT_SPECS}
    event_paths = {cache / f"live_events_{name}.jsonl" for name in expected_names}
    event_paths.update(cache.glob("live_events_v*_core_*.jsonl"))
    for path in sorted(event_paths):
        name = path.stem.removeprefix("live_events_")
        rows, errors, snapshot = _read_jsonl(path)
        sources.append(_snapshot_source(path, root, snapshot) | {"parse_errors": errors})
        entries = {str(r.get("frozen_sha256")): r for r in rows if r.get("kind") == "entry"}
        terminal: dict[str, dict] = {}
        duplicates = 0
        for row in rows:
            if row.get("kind") != "resolution" or row.get("status") not in {"RESOLVED", "INVALIDATED"}:
                continue
            key = str(row.get("frozen_sha256"))
            if key in terminal:
                duplicates += 1
                continue
            terminal[key] = row
        outcomes = list(terminal.values())
        reported = [float(r["realized_r"]) for r in outcomes if r.get("realized_r") is not None]
        stress = [float(r["stress_realized_r"]) for r in outcomes
                  if r.get("stress_realized_r") is not None]
        stress_pnl = 0.0
        initial_equities = set()
        for key, entry in entries.items():
            try:
                initial_equities.add(float(entry["strategy_config"]["initial_bankroll_usd"]))
            except (KeyError, TypeError, ValueError):
                pass
            outcome = terminal.get(key)
            if not outcome or outcome.get("stress_realized_r") is None:
                continue
            try:
                risk_notional = (float(entry["entry_fill"]["usd_size"])
                                 * float(entry["strategy_config"]["catastrophe_frac"]))
                stress_pnl += float(outcome["stress_realized_r"]) * risk_notional
            except (KeyError, TypeError, ValueError):
                continue
        initial_equity = next(iter(initial_equities)) if len(initial_equities) == 1 else None
        v2_variants[name] = {
            "entries": len(entries), "terminal": len(outcomes),
            "open": len(set(entries) - set(terminal)), "duplicate_terminal": duplicates,
            "reported": _r_summary(reported), "full_loss_stress": _r_summary(stress),
            "restart_invalidations": sum(r.get("resolution_reason") == "INVALID_RESTART_GAP"
                                         for r in outcomes),
            "stale_marks_full_loss_stressed": sum(r.get("resolution_reason") == "exit:maxhold_timeout"
                                                  for r in outcomes),
            "commitment_failures": sum(
                canonical_sha256(r.get("frozen_payload")) != r.get("frozen_sha256")
                for r in entries.values()),
            "experiment_preregistration_failures": sum(
                name.startswith("v3_")
                and r.get("experiment_preregistration_sha256") != V3_PREREG_SHA256
                for r in entries.values()),
            "source_exists": path.exists(),
            "full_loss_stress_equity_usd": (
                _round(max(0.0, initial_equity + stress_pnl)) if initial_equity is not None else None),
        }
    return {
        "scope": "all local sniper resolution ledgers; parallel variants are separate tests",
        "sources": sources,
        "parse_errors": parse_errors,
        "variant_ledgers": len(variants),
        "resolution_rows_across_arms": sum(v["rows"] for v in variants.values()),
        "variants": variants,
        "event_variants_v2_and_later": v2_variants,
        "event_terminal_rows_across_arms": sum(v["terminal"] for v in v2_variants.values()),
        "system_current_cost_R": _r_summary(x["current_full_cost_R"] for x in all_current),
        "median_round_trip_tip_fraction_of_notional": _round(_median(
            x["round_trip_tip_fraction_of_notional"] for x in all_current)),
        "watchdog_restart_events": restarts,
        "legacy_cutover": cutover,
        "unresolved_trade_count_at_cutover": (
            cutover.get("totals", {}).get("n_open_cutover_dropouts") if cutover else None),
        "unresolved_trade_count_reason": (
            "legacy entries/open positions were not persisted; identities before cutover are unknowable. "
            "The final published open count is preserved in the cutover receipt and full-loss stressed."
        ),
    }


def _memebot_paths(spec: dict) -> tuple[Path, Path]:
    return Path(spec["_paths"]["prereg_log"]), Path(spec["_paths"]["resolution_log"])


def _audit_entry_compliance(entries: list[dict], spec: dict) -> dict:
    from scripts.trading_bot.memebot.frozen import canonical_sha256
    from scripts.trading_bot.memebot.screen import screen_coin

    pass_entries = [e for e in entries if not e.get("control")]
    violations: list[dict] = []
    bad_hashes = 0
    non_pump = 0
    for entry in entries:
        if canonical_sha256(entry) != entry.get("setup_sha256"):
            bad_hashes += 1
    for entry in pass_entries:
        coin = dict(entry.get("feed_snapshot") or {})
        coin.setdefault("dex", entry.get("dex"))
        result = screen_coin(coin, spec)
        if result["verdict"] != "PASS":
            violations.append({
                "setup_sha256": entry.get("setup_sha256"),
                "name": entry.get("name"),
                "reasons": result["reasons"],
            })
        if str(entry.get("dex") or "").lower() not in {"pump-fun", "pumpfun"}:
            non_pump += 1
    return {
        "pass_entries": len(pass_entries),
        "pass_screen_violations": len(violations),
        "pass_screen_violation_examples": violations[:10],
        "entry_hash_mismatches": bad_hashes,
        "pass_entries_outside_pump_venue": non_pump,
    }


def _audit_memebot_instrument(spec: dict, root: Path) -> tuple[dict, list[dict]]:
    entry_path, resolution_path = _memebot_paths(spec)
    entries, entry_errors, entry_snapshot = _read_jsonl(entry_path)
    resolutions, resolution_errors, resolution_snapshot = _read_jsonl(resolution_path)
    resolutions = [r for r in resolutions if r.get("status") == "RESOLVED"]
    resolutions, duplicates = _dedupe_resolutions(resolutions)
    entry_by_hash = {str(e.get("setup_sha256")): e for e in entries if e.get("setup_sha256")}
    resolved_hashes = {str(r.get("setup_sha256")) for r in resolutions}
    orphan = [r for r in resolutions if str(r.get("setup_sha256")) not in entry_by_hash]
    open_entries = [e for e in entries if str(e.get("setup_sha256")) not in resolved_hashes]
    passed = [r for r in resolutions if not r.get("control")]
    controls = [r for r in resolutions if r.get("control")]
    pump_passed = [r for r in passed if str((entry_by_hash.get(str(r.get("setup_sha256"))) or {}).get("dex") or "").lower()
                   in {"pump-fun", "pumpfun"}]
    stressed: list[float] = []
    for row in passed:
        entry = entry_by_hash.get(str(row.get("setup_sha256")))
        if row.get("resolution_reason") == "UNEXITABLE_TIMEOUT" and entry:
            r = _full_loss_r(entry)
        else:
            r = row.get("realized_r")
        if r is not None:
            stressed.append(float(r))
    compliance = _audit_entry_compliance(entries, spec)
    report = {
        "instrument_id": spec["instrument_id"],
        "entries": len(entries),
        "resolved": len(resolutions),
        "open": len(open_entries),
        "resolved_pass": len(passed),
        "resolved_control": len(controls),
        "duplicate_resolutions": duplicates,
        "orphan_resolutions": len(orphan),
        "parse_errors": len(entry_errors) + len(resolution_errors),
        "reported_pass": _r_summary(r.get("realized_r") for r in passed),
        "reported_pump_only_pass": _r_summary(r.get("realized_r") for r in pump_passed),
        "full_loss_stress_pass": _r_summary(stressed),
        "reported_paper_bankroll_SOL_closed_pass_only": _paper_bankroll(
            passed, entry_by_hash, stress=False),
        "full_loss_stress_paper_bankroll_SOL_closed_pass_only": _paper_bankroll(
            passed, entry_by_hash, stress=True),
        "pass_exit_reasons": _reason_counts(passed),
        "control_exit_reasons": _reason_counts(controls),
        "pass_unexitable_rate": _round(
            sum(r.get("resolution_reason") == "UNEXITABLE_TIMEOUT" for r in passed) / len(passed)
        ) if passed else None,
        "pass_horizon_marks": sum(r.get("resolution_reason") == "HORIZON_MARK" for r in passed),
        "compliance": compliance,
    }
    sources = [
        _snapshot_source(entry_path, root, entry_snapshot) | {"parse_errors": entry_errors},
        _snapshot_source(resolution_path, root, resolution_snapshot) | {"parse_errors": resolution_errors},
    ]
    return report, sources


def audit_memebot(root: Path) -> dict:
    from scripts.trading_bot.memebot.frozen import ACTIVE_INSTRUMENTS, frozen_spec

    instruments: dict[str, dict] = {}
    sources: list[dict] = []
    for instrument_id in ACTIVE_INSTRUMENTS:
        spec = frozen_spec(instrument_id)
        report, src = _audit_memebot_instrument(spec, root)
        instruments[instrument_id] = report
        sources.extend(src)

    contaminated_dir = root / "research" / "trading_bot" / "memebot" / "contaminated"
    contaminated: dict[str, Any] = {"present": contaminated_dir.exists(), "rows": 0, "sources": []}
    if contaminated_dir.exists():
        for path in sorted(contaminated_dir.glob("*.jsonl")):
            rows, errors, snapshot = _read_jsonl(path)
            contaminated["rows"] += len(rows)
            contaminated["sources"].append(
                _snapshot_source(path, root, snapshot) | {"parse_errors": errors})

    return {
        "scope": "all active frozen MEMEBOT ledgers plus quarantined EXIT evidence",
        "sources": sources,
        "instruments": instruments,
        "contaminated_EXIT": contaminated,
        "resolution_rows_across_arms": sum(x["resolved"] for x in instruments.values()),
        "resolved_pass_across_arms": sum(x["resolved_pass"] for x in instruments.values()),
        "warning": "parallel variants share opportunities and are not one investable portfolio",
    }


def _audit_genome(gid: str, rows: list[dict], pop: dict, state: dict) -> dict:
    entries = [r for r in rows if r.get("kind") == "entry"]
    resolutions = [r for r in rows if r.get("kind") == "resolution" and r.get("status") == "RESOLVED"]
    resolutions, duplicates = _dedupe_resolutions(resolutions)
    entry_by_hash = {str(e.get("setup_sha256")): e for e in entries if e.get("setup_sha256")}
    resolved_hashes = {str(r.get("setup_sha256")) for r in resolutions}
    open_entries = [e for e in entries if str(e.get("setup_sha256")) not in resolved_hashes]
    passed_all = [r for r in resolutions if not r.get("control")]
    priced = [r for r in passed_all if r.get("realized_r") is not None]
    unpriced = [r for r in passed_all if r.get("realized_r") is None]
    stressed: list[float] = []
    for row in passed_all:
        entry = entry_by_hash.get(str(row.get("setup_sha256")))
        if entry and (row.get("resolution_reason") == "UNEXITABLE_TIMEOUT" or row.get("realized_r") is None):
            r = _full_loss_r(entry)
        else:
            r = row.get("realized_r")
        if r is not None:
            stressed.append(float(r))
    pass_entries = [e for e in entries if not e.get("control")]
    non_pump = sum(str(e.get("dex") or "").lower() not in {"pump-fun", "pumpfun"}
                   for e in pass_entries)
    pump_priced = [r for r in priced
                   if str((entry_by_hash.get(str(r.get("setup_sha256"))) or {}).get("dex") or "").lower()
                   in {"pump-fun", "pumpfun"}]
    return {
        "genome_id": gid,
        "in_population": gid in pop.get("genomes", {}),
        "active": gid in set(pop.get("active", [])),
        "registered_in_K": gid in set(state.get("K_all_genome_ids_ever", [])),
        "entries": len(entries),
        "resolved": len(resolutions),
        "open": len(open_entries),
        "resolved_pass_total_including_unpriced": len(passed_all),
        "resolved_pass_priced": len(priced),
        "resolved_pass_unpriced": len(unpriced),
        "priced_fraction": _round(len(priced) / len(passed_all)) if passed_all else None,
        "duplicates": duplicates,
        "orphan_resolutions": sum(str(r.get("setup_sha256")) not in entry_by_hash for r in resolutions),
        "reported_pass": _r_summary(r.get("realized_r") for r in priced),
        "reported_pump_only_pass": _r_summary(r.get("realized_r") for r in pump_priced),
        "full_loss_stress_pass": _r_summary(stressed),
        "reported_paper_bankroll_SOL_closed_pass_only": _paper_bankroll(
            priced, entry_by_hash, stress=False),
        "full_loss_stress_paper_bankroll_SOL_closed_pass_only": _paper_bankroll(
            passed_all, entry_by_hash, stress=True),
        "pass_exit_reasons": _reason_counts(passed_all),
        "pass_entries_outside_pump_venue": non_pump,
    }


def audit_genomes(root: Path) -> dict:
    pkg = root / "scripts" / "trading_bot" / "memebot_evo"
    pop_path, state_path = pkg / "population.json", pkg / "evo_state.json"
    pop = json.loads(pop_path.read_text())
    state = json.loads(state_path.read_text())
    sources = [_source(pop_path, root), _source(state_path, root)]
    genomes: dict[str, dict] = {}
    parse_errors = 0
    for path in sorted((pkg / "ledgers").glob("*.jsonl")):
        rows, errors, snapshot = _read_jsonl(path)
        parse_errors += len(errors)
        gid = path.stem
        genomes[gid] = _audit_genome(gid, rows, pop, state)
        sources.append(_snapshot_source(path, root, snapshot) | {"parse_errors": errors})

    mature_reported = [g for g in genomes.values() if g["reported_pass"]["n"] >= 20]
    mature_stress = [g for g in genomes.values() if g["full_loss_stress_pass"]["n"] >= 20]
    rank_reported = sorted(mature_reported,
                           key=lambda g: g["reported_pass"]["mean_R"] or -math.inf, reverse=True)
    rank_stress = sorted(mature_stress,
                         key=lambda g: g["full_loss_stress_pass"]["mean_R"] or -math.inf, reverse=True)
    candidate_ids = set(state.get("candidates", {}))
    falsified_ids = set(state.get("falsified_on_fresh_slice", {}))
    registered = set(state.get("K_all_genome_ids_ever", []))
    on_disk = set(genomes)
    in_population = set(pop.get("genomes", {}))
    noise_bar = math.sqrt(2.0 * math.log(max(2, len(registered))))
    stress_clearers = [
        g["genome_id"] for g in mature_stress
        if g["full_loss_stress_pass"].get("t_stat") is not None
        and g["full_loss_stress_pass"]["t_stat"] > noise_bar
    ]

    return {
        "scope": "every genome ledger on disk, active and inactive",
        "sources": sources,
        "parse_errors": parse_errors,
        "ledger_genomes": len(genomes),
        "active_genomes": len(pop.get("active", [])),
        "population_registry_genomes": len(in_population),
        "K_registered_genomes": len(registered),
        "ledger_ids_missing_from_K": sorted(on_disk - registered),
        "K_ids_without_ledger": sorted(registered - on_disk),
        "population_ids_missing_from_K": sorted(in_population - registered),
        "resolution_rows_across_arms": sum(g["resolved"] for g in genomes.values()),
        "resolved_pass_priced_across_arms": sum(g["resolved_pass_priced"] for g in genomes.values()),
        "resolved_pass_unpriced_across_arms": sum(g["resolved_pass_unpriced"] for g in genomes.values()),
        "candidate_also_previously_falsified": sorted(candidate_ids & falsified_ids),
        "K_corrected_noise_bar_SE": _round(noise_bar),
        "full_loss_stress_genomes_clearing_K_bar": sorted(stress_clearers),
        "top_reported_mature": [
            {"genome_id": g["genome_id"], **g["reported_pass"]} for g in rank_reported[:10]
        ],
        "top_full_loss_stress_mature": [
            {"genome_id": g["genome_id"], **g["full_loss_stress_pass"]} for g in rank_stress[:10]
        ],
        "genomes": genomes,
        "warning": (
            "genomes enter at different calendar times and are ranked on unequal, mostly unpaired cohorts; "
            "these rows are strategy-arm observations, not independent portfolio trades"
        ),
    }


def build_audit(root: Path = ROOT) -> dict:
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    sniper = audit_sniper(root)
    memebot = audit_memebot(root)
    genomes = audit_genomes(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": generated,
        "scope": "all local Pump/memecoin paper-trade ledgers; no live orders",
        "evidence_labels": {
            "verified_fact": "directly recomputed from the hash-pinned source snapshots listed below",
            "stress_assumption": "unavailable/unpriced exit is bounded at -100% before pinned toll",
            "open_question": "whether any observed mark would have been executable at the recorded size",
        },
        "sniper": sniper,
        "memebot": memebot,
        "genomes": genomes,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(audit: dict) -> str:
    lines = [
        "# Memecoin paper-trade audit",
        "",
        f"Generated UTC: `{audit['generated_utc']}`",
        "",
        "**Verified fact:** every figure below is recomputed from the source snapshots whose SHA-256 is "
        "stored in the accompanying JSON. Parallel variants share opportunities and are not added into "
        "one investable portfolio.",
        "",
        "**Stress assumption:** `UNEXITABLE_TIMEOUT` and terminal `UNPRICED` are valued at a full position "
        "loss before the pinned toll. This is a conservative bound, not a claim that every missing mark "
        "was literally worth zero.",
        "",
        "## Sniper",
        "",
        f"Resolved rows across arms: **{audit['sniper']['resolution_rows_across_arms']:,}**. "
        f"Watchdog restart events: **{audit['sniper']['watchdog_restart_events']}**. Entries/open positions "
        "were not persisted historically. The controlled cutover preserved **"
        f"{audit['sniper']['unresolved_trade_count_at_cutover'] or 0}** last-observed open legacy positions "
        "as full-loss-stressed dropouts; earlier restart identities remain unknowable.",
        "",
        "| variant | n | reported mean R | current-cost mean R | median round-trip tip / notional | cost regimes (gross / toll / full / other) |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, row in audit["sniper"]["variants"].items():
        regimes = row["cost_regime_rows"]
        regime_text = "/".join(str(regimes.get(k, 0)) for k in ("gross", "toll_only", "toll_plus_tip", "other"))
        lines.append(
            f"| {name} | {row['rows']} | {_fmt(row['reported']['mean_R'])} | "
            f"{_fmt(row['recomputed_current_cost']['mean_R'])} | "
            f"{_fmt(row['median_round_trip_tip_fraction_of_notional'])} | {regime_text} |"
        )

    lines += [
        "",
        "### Sniper append-only event streams (V2 shakeout + clean V3)",
        "",
        "| variant | entries | terminal | open | reported mean R | stress mean R | stress equity USD | restart invalidations | commitment/experiment failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in audit["sniper"]["event_variants_v2_and_later"].items():
        lines.append(
            f"| {name} | {row['entries']} | {row['terminal']} | {row['open']} | "
            f"{_fmt(row['reported']['mean_R'])} | {_fmt(row['full_loss_stress']['mean_R'])} | "
            f"{_fmt(row['full_loss_stress_equity_usd'])} | "
            f"{row['restart_invalidations']} | {row['commitment_failures']}/"
            f"{row['experiment_preregistration_failures']} |"
        )

    lines += [
        "",
        "## Frozen MEMEBOT variants",
        "",
        "| instrument | pass n | reported mean R | Pump-only n/mean R | full-loss stress mean R | reported paper SOL | stress paper SOL | unexitable | screen violations | non-Pump PASS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in audit["memebot"]["instruments"].items():
        lines.append(
            f"| {name} | {row['resolved_pass']} | {_fmt(row['reported_pass']['mean_R'])} | "
            f"{row['reported_pump_only_pass']['n']}/{_fmt(row['reported_pump_only_pass']['mean_R'])} | "
            f"{_fmt(row['full_loss_stress_pass']['mean_R'])} | "
            f"{_fmt(row['reported_paper_bankroll_SOL_closed_pass_only'])} | "
            f"{_fmt(row['full_loss_stress_paper_bankroll_SOL_closed_pass_only'])} | "
            f"{_fmt(row['pass_unexitable_rate'])} | {row['compliance']['pass_screen_violations']} | "
            f"{row['compliance']['pass_entries_outside_pump_venue']} |"
        )

    lines += [
        "",
        "## Genome population",
        "",
        f"Ledger genomes: **{audit['genomes']['ledger_genomes']}**; active: "
        f"**{audit['genomes']['active_genomes']}**; priced PASS resolutions across arms: "
        f"**{audit['genomes']['resolved_pass_priced_across_arms']:,}**; terminal unpriced PASS rows: "
        f"**{audit['genomes']['resolved_pass_unpriced_across_arms']:,}**.",
        "",
        "| reported rank (mature) | n | mean R | stress rank (mature) | n | stress mean R |",
        "|---|---:|---:|---|---:|---:|",
    ]
    left = audit["genomes"]["top_reported_mature"]
    right = audit["genomes"]["top_full_loss_stress_mature"]
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else {}
        r = right[i] if i < len(right) else {}
        lines.append(
            f"| {l.get('genome_id', '—')} | {l.get('n', '—')} | {_fmt(l.get('mean_R'))} | "
            f"{r.get('genome_id', '—')} | {r.get('n', '—')} | {_fmt(r.get('mean_R'))} |"
        )
    redeclared = audit["genomes"]["candidate_also_previously_falsified"]
    lines += [
        "",
        "## Mechanical findings",
        "",
        f"- Sniper median fixed round-trip tip/notional: "
        f"**{_fmt(audit['sniper']['median_round_trip_tip_fraction_of_notional'])}**.",
        "- Legacy sniper ledgers contain only resolutions; entries lost on historical restarts are unknowable and "
        "entry hashes cannot be recomputed from the retained fields.",
        f"- Genome candidates that are simultaneously in the falsified registry: "
        f"**{', '.join(redeclared) if redeclared else 'none'}**.",
        f"- Genomes clearing the K={audit['genomes']['K_registered_genomes']} noise bar after the "
        f"full-loss stress: **{', '.join(audit['genomes']['full_loss_stress_genomes_clearing_K_bar']) or 'none'}**.",
        "- Reported price marks remain paper observations. Exact position-sized on-chain exit quotes, "
        "landing failures and latency are not present in these ledgers.",
        "",
    ]
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args(argv)
    audit = build_audit(ROOT)
    md = render_markdown(audit)
    if not args.no_write:
        _atomic_write(args.json, json.dumps(audit, indent=2, sort_keys=True) + "\n")
        _atomic_write(args.markdown, md)
    if args.stdout:
        print(md)
    else:
        print(json.dumps({
            "generated_utc": audit["generated_utc"],
            "sniper_rows": audit["sniper"]["resolution_rows_across_arms"],
            "memebot_pass_rows": audit["memebot"]["resolved_pass_across_arms"],
            "genome_priced_pass_rows": audit["genomes"]["resolved_pass_priced_across_arms"],
            "json": str(args.json),
            "markdown": str(args.markdown),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
