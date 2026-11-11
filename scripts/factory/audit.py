"""audit.py — the future-scramble audit and the lag-sensitivity (PRINT-PROXIMITY) flag. DESIGN_v2 §3.4.

FUTURE-SCRAMBLE AUDIT — what it proves and how
  For each probe row k the strategy is re-run on a PanelBundle that is IDENTICAL for rows <= k and
  REGENERATED for rows > k in every field the harness controls: `prices`, `carry`, EVERY `aux`
  frame and `tbill`. Rows <= k of the two outputs must be bit-identical (NaN == NaN). A divergence
  means a decision at or before k consumed a row after k: verdict LEAKY, first divergent cell named.

  The future is regenerated, not permuted — and regenerated VIOLENTLY, as an antithetic pair.
    * A permutation preserves every permutation-invariant statistic (full-sample mean, std, min,
      max, the NaN count), so a rule that normalises by the full-sample standard deviation — a real
      and common leak — would pass a permutation probe.
    * A PLAUSIBLE continuation (a random walk from the last honest price, as in the v1 draft) is too
      gentle for coarse outputs. A rule that peeks one row ahead through sign() or a threshold only
      diverges if that one regenerated value happens to fall on the other side: about half the
      time for the sign of a one-print change, and almost never for "is the 63-print return
      positive". A single shared series (an aux factor) gives the probe exactly one cell to hit.
    * So every column is sent, after k, far to one side of anything it has shown — and in a second,
      MIRRORED run to the other side. Per kind of column (decided on the whole original column):
          positive  (all finite values > 0: prices, exec prices, volumes, positive rates)
                    last honest value x J (up) or / J (down), J in [3, 5], then a random walk
          real      (other numeric: carry, spreads, z-scores)
                    honest mean + 8 sd (up) or - 8 sd (down), plus noise
          binary / boolean  (numeric flags taking both 0 and 1; boolean masks such as `universe_mask`)
                    all ones (up) or all zeros (down)
          other     (text, dates, categories) rows after k permuted; the mirrored run uses the
                    reversed order. The one kind where a block can come back unchanged.
      Which columns go up in the first run is random; the second run flips every column. Any
      decision that depends on ONE future cell through a monotone or threshold function therefore
      changes in exactly one of the two runs. Integer / boolean dtypes are kept, and no NaN
      survives after k, so a rule that reads the future NaN pattern ("only instruments that never
      delist") diverges too.

  A TRUNCATION probe (default on) also runs the strategy on the panel cut to rows 0..k (what
  `panel.window(end=row k)` returns on a daily panel): the future does not merely differ, it does
  not exist. It is deterministic and catches a dependence on the panel's length or last date. It
  is stricter than the contract requires, never looser.

  Three further ways NOT to pass (any verdict other than PASS is not a pass):
      * the strategy RAISES once the future is changed or removed -> LEAKY: a decision at or before
        k that cannot be computed without the rows after k is, by definition, using them;
      * two runs on the same panel differ -> NON_DETERMINISTIC: a rule that is not reproducible
        cannot be audited (seed it);
      * the strategy modifies the panel it is handed -> MUTATES_INPUT. The audit runs it on a copy,
        so the caller's panel is unharmed, but in a sweep it would corrupt every later rule.

  COST: 1 baseline (+1 determinism) + per probe row: 2 scrambles (1 if `antithetic=False`) + 1
  truncation. Default with 3 probes: 11 strategy runs.

  STATED LIMITS
    * The audit proves that no decision depends on the future of the data THE HARNESS CONTROLS. A
      rule that opens its own file, calls the network or reads a module global is outside what any
      re-run can detect; that is a code-review question. `meta` is copied, not scrambled: a rule
      must not smuggle time-indexed data through `meta`.
    * It probes `len(probe_rows)` rows, not every row. A leak that only switches on in a regime no
      probe row sits in can be missed; spread the probes across the scoring window.
    * Dependences on several future cells at once (a comparison of two future values that move the
      same way in both runs) are caught with high probability, not with certainty.
    * A PASS certifies that the inputs were legal, not that the rule is any good.

PRINT-PROXIMITY (DESIGN_v2 §3.4)
  `lag_sensitivity(net_a, net_b, ppy)`: net_a is the base convention (lag 1 / exec at 01:00),
  net_b one more print of delay (lag 2 / exec at 02:00). Flag PRINT-PROXIMITY when
  Sharpe_a > 0 and Sharpe_a > 2 * Sharpe_b: the edge does not survive one more print, so it lives
  in the print itself (stale fixes, bid-ask bounce), not in something a slower account can trade.
  If Sharpe_a > 0 and Sharpe_b cannot be computed, the flag is raised (conservative).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .engine import Refused
from .panel import PanelBundle
from .stats import Window, sharpe_ratio, window_mask

StrategyFn = Callable[..., pd.DataFrame]
PRINT_PROXIMITY = "PRINT-PROXIMITY"
JUMP_RANGE = (3.0, 5.0)        # positive columns: last honest value x J or / J
REAL_SHIFT_SD = 8.0            # real columns: honest mean +/- 8 standard deviations


@dataclass(frozen=True)
class AuditResult:
    """Outcome of `future_scramble_audit`.

    passed            (property) True only for verdict 'PASS'
    detail            one human-readable sentence: what was proven, or the first offence
    verdict           'PASS' | 'LEAKY' | 'NON_DETERMINISTIC' | 'MUTATES_INPUT'
    probe_rows        the probe rows used (sorted, unique)
    rows_compared     how many output rows were compared in total
    first_divergence  dict naming the first offending cell / probe, or None
    truncation_probe  whether the truncation probe ran
    """

    verdict: str
    detail: str
    probe_rows: tuple
    rows_compared: int
    first_divergence: Optional[dict]
    truncation_probe: bool

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"


# --------------------------------------------------------------------------------------------------
# Regenerating the future
# --------------------------------------------------------------------------------------------------
def _kind(col: pd.Series) -> str:
    """'bool' | 'binary' | 'positive' | 'real' | 'other' — decided on the whole original column."""
    if pd.api.types.is_bool_dtype(col.dtype):
        return "bool"
    if not pd.api.types.is_numeric_dtype(col.dtype):
        return "other"
    vals = pd.to_numeric(col, errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return "real"
    if np.isin(vals, (0.0, 1.0)).all() and (vals == 0.0).any() and (vals == 1.0).any():
        return "binary"                                                # a 0/1 flag that takes BOTH values
    return "positive" if (vals > 0).all() else "real"                  # a constant 0 column (zero tbill) is 'real'


def _fresh_values(honest: np.ndarray, n_after: int, kind: str, up: bool, rng: np.random.Generator) -> np.ndarray:
    """`n_after` regenerated float values for one numeric column, given its honest block (rows <= k)
    and its direction for this run. Never NaN. Consumes the same number of draws whatever `up` is,
    so a mirrored run made from a generator in the same state sees the same noise."""
    honest = honest[np.isfinite(honest)]
    jump = rng.uniform(*JUMP_RANGE)
    wobble = rng.uniform(0.5, 2.0)
    noise = rng.standard_normal(n_after)
    if kind in ("bool", "binary"):
        return np.full(n_after, 1.0 if up else 0.0)
    if kind == "positive":
        anchor = float(honest[-1]) if len(honest) else 1.0
        vol = 0.01
        if len(honest) >= 3:
            sd = float(np.std(np.diff(np.log(honest))))
            vol = min(sd, 0.2) if sd > 0 else 0.01
        steps = np.clip(noise * vol * wobble, -0.5, 0.5)
        return anchor * (jump if up else 1.0 / jump) * np.cumprod(1.0 + steps)
    mean = float(honest.mean()) if len(honest) else 0.0
    sd = float(honest.std()) if len(honest) else 0.0
    scale = (sd if sd > 0 else max(abs(mean) * 0.1, 1e-4)) * wobble
    return mean + (REAL_SHIFT_SD if up else -REAL_SHIFT_SD) * scale + noise * scale


def _scramble_series(col: pd.Series, k: int, up: bool, rng: np.random.Generator) -> pd.Series:
    """One column with rows > k regenerated; rows <= k, the index, the name and the dtype untouched."""
    n_after = len(col) - (k + 1)
    kind = _kind(col)
    if kind == "other":
        order = rng.permutation(n_after)
        tail = col.iloc[k + 1:].to_numpy(copy=True)[order if up else order[::-1]]
        return pd.concat([col.iloc[: k + 1], pd.Series(tail, index=col.index[k + 1:], name=col.name).astype(col.dtype)])
    honest = pd.to_numeric(col.iloc[: k + 1], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
    fresh = _fresh_values(honest, n_after, kind, up, rng)
    dtype = col.dtype
    if isinstance(dtype, np.dtype) and dtype.kind == "f":
        arr = col.to_numpy(copy=True)
        arr[k + 1:] = fresh.astype(dtype)
        return pd.Series(arr, index=col.index, name=col.name)
    if kind == "bool":
        tail_vals: np.ndarray = fresh.astype(bool)
    elif pd.api.types.is_integer_dtype(dtype):
        tail_vals = np.rint(fresh).astype(np.int64)
        if kind == "positive":
            tail_vals = np.maximum(tail_vals, 1)
            last = honest[np.isfinite(honest)]
            if len(last) and tail_vals[0] == int(last[-1]):
                tail_vals[0] += 1                                      # tiny integers: x J can round back
    else:
        tail_vals = fresh
    tail = pd.Series(tail_vals, index=col.index[k + 1:], name=col.name).astype(dtype)
    return pd.concat([col.iloc[: k + 1], tail])


def _scramble_frame(df: pd.DataFrame, k: int, rng: np.random.Generator, mirror: bool) -> pd.DataFrame:
    out = df.copy()
    if len(df) - (k + 1) <= 0:
        return out
    ups = rng.random(df.shape[1]) < 0.5                                 # which columns jump up in the un-mirrored run
    for j in range(df.shape[1]):
        out.isetitem(j, _scramble_series(df.iloc[:, j], k, bool(ups[j]) != mirror, rng))
    return out


def scramble_after(panel: PanelBundle, k: int, rng: np.random.Generator, *, mirror: bool = False) -> PanelBundle:
    """A new PanelBundle identical to `panel` for rows <= k and regenerated for rows > k.

    Regenerated: `prices`, `carry`, every `aux` frame (in sorted name order), `tbill` — each column
    thrown far above or far below its honest history (module docstring). Preserved: the index, the
    columns, the dtypes, and `meta` (copied, plus 'scrambled_after_row': k and 'scramble_mirror').
    `mirror=True` flips the direction of EVERY column; two calls with generators in the same state
    and mirror=False / True are the antithetic pair. The input is never modified.
    """
    T = len(panel.prices)
    if isinstance(k, (bool, np.bool_)) or not isinstance(k, (int, np.integer)) or not (0 <= k <= T - 2):
        raise Refused(f"probe row k={k!r} must be an integer with 0 <= k <= T-2 (T={T}): there must be a future to scramble")
    k = int(k)
    mirror = bool(mirror)
    prices = _scramble_frame(panel.prices, k, rng, mirror)
    carry = None if panel.carry is None else _scramble_frame(panel.carry, k, rng, mirror)
    aux = {name: _scramble_frame(panel.aux[name], k, rng, mirror) for name in sorted(panel.aux, key=str)}
    aux = {name: aux[name] for name in panel.aux}                       # keep the caller's key order
    tbill = _scramble_series(panel.tbill, k, bool(rng.random() < 0.5) != mirror, rng)
    meta = dict(panel.meta)
    meta["scrambled_after_row"] = k
    meta["scramble_mirror"] = mirror
    return PanelBundle(lane=panel.lane, prices=prices, carry=carry, aux=aux, tbill=tbill, meta=meta)


def _clone(panel: PanelBundle) -> PanelBundle:
    return PanelBundle(
        lane=panel.lane,
        prices=panel.prices.copy(deep=True),
        carry=None if panel.carry is None else panel.carry.copy(deep=True),
        aux={name: df.copy(deep=True) for name, df in panel.aux.items()},
        tbill=panel.tbill.copy(deep=True),
        meta=dict(panel.meta),
    )


def _truncate(panel: PanelBundle, k: int) -> PanelBundle:
    """The panel cut to rows 0..k — what `panel.window(end=row k)` returns on a one-print-per-day
    panel, but exact for any index (a midnight END bound in `window()` covers the whole UTC day)."""
    cut = slice(0, k + 1)
    return PanelBundle(
        lane=panel.lane,
        prices=panel.prices.iloc[cut],
        carry=None if panel.carry is None else panel.carry.iloc[cut],
        aux={name: df.iloc[cut] for name, df in panel.aux.items()},
        tbill=panel.tbill.iloc[cut],
        meta=dict(panel.meta),
    )


def _same_frame(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return bool(a.shape == b.shape and a.index.equals(b.index) and a.equals(b))


def _unchanged(work: PanelBundle, original: PanelBundle) -> Optional[str]:
    """None if `work` still equals `original`; otherwise the name of the first field that changed."""
    if not _same_frame(work.prices, original.prices):
        return "prices"
    if not _same_frame(work.carry, original.carry):
        return "carry"
    if not _same_frame(work.tbill, original.tbill):
        return "tbill"
    if set(work.aux) != set(original.aux):
        return "aux (keys)"
    for name in original.aux:
        if not _same_frame(work.aux[name], original.aux[name]):
            return f"aux[{name!r}]"
    return None


# --------------------------------------------------------------------------------------------------
# The audit
# --------------------------------------------------------------------------------------------------
def _run_strategy(fn: StrategyFn, panel: PanelBundle, params: dict, cols: list) -> np.ndarray:
    """Call the strategy and coerce its output to a float64 (T, N) array in the panel's column order.
    A wrong container / index / columns / dtype is a contract violation (`Refused`), not a leak."""
    out = fn(panel, **params)
    if not isinstance(out, pd.DataFrame):
        raise Refused(f"strategy must return a DataFrame; got {type(out).__name__}")
    if not out.index.equals(panel.prices.index):
        raise Refused("strategy output index must equal the panel's prices.index")
    if not out.columns.is_unique or set(out.columns) != set(cols):
        raise Refused("strategy output columns must be exactly the panel instruments")
    try:
        return out[cols].to_numpy(dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise Refused(f"strategy output must be numeric: {exc}") from exc


def _first_divergence(a: np.ndarray, b: np.ndarray) -> Optional[tuple]:
    """First (row, col) where a != b, NaN-aware; None if bit-identical."""
    neq = ~((a == b) | (np.isnan(a) & np.isnan(b)))
    if not neq.any():
        return None
    i, j = np.argwhere(neq)[0]
    return int(i), int(j)


def future_scramble_audit(
    fn: StrategyFn,
    panel: PanelBundle,
    params: Optional[dict],
    probe_rows: Sequence[int],
    rng: np.random.Generator,
    *,
    truncation_probe: bool = True,
    antithetic: bool = True,
    determinism_check: bool = True,
) -> AuditResult:
    """Prove that no row <= k of `fn(panel, **params)` depends on any panel row > k, for every k in `probe_rows`.

    fn           strategy: fn(panel, **params) -> DataFrame on the panel's index and instruments
                 (a signal or a weight frame — the audit only compares it with itself).
    params       keyword arguments for `fn` (None = {}).
    probe_rows   row POSITIONS k with 0 <= k <= T-2; at least one. Put them after the rule's warm-up
                 and spread them (e.g. 40 %, 60 %, 90 % of the scoring window).
    rng          numpy Generator; one base seed is drawn from it and probe k scrambles with
                 default_rng([base, k]), so the audit is reproducible from the generator's state.
    truncation_probe   also run on the panel cut at k (default True).
    antithetic         run the mirrored scramble too (default True; see the module docstring).
    determinism_check  run the baseline twice and refuse a rule that disagrees with itself.

    Returns an `AuditResult` (`.passed`, `.detail`, ...). Exceptions raised by the BASELINE run
    propagate (a broken strategy is not a leak); an exception in a probe run is a LEAKY verdict.
    """
    params = dict(params or {})
    if not isinstance(rng, np.random.Generator):
        raise Refused(f"rng must be a numpy.random.Generator; got {type(rng).__name__}")
    if probe_rows is None or len(probe_rows) == 0:
        raise Refused("an audit with no probe rows proves nothing; give >= 1 probe row")
    T = len(panel.prices)
    probes: List[int] = []
    for k in probe_rows:
        if isinstance(k, (bool, np.bool_)) or not isinstance(k, (int, np.integer)) or not (0 <= int(k) <= T - 2):
            raise Refused(f"probe row {k!r} must be an integer in [0, {T - 2}]")
        probes.append(int(k))
    probes = sorted(set(probes))
    cols = list(panel.prices.columns)
    idx = panel.prices.index
    base_seed = int(rng.integers(0, 2**31 - 1))
    rows_compared = 0

    def result(verdict: str, detail: str, first: Optional[dict] = None) -> AuditResult:
        return AuditResult(verdict, detail, tuple(probes), rows_compared, first, truncation_probe)

    work = _clone(panel)                              # the strategy never touches the caller's panel
    baseline = _run_strategy(fn, work, params, cols)
    changed = _unchanged(work, panel)
    if changed is not None:
        return result("MUTATES_INPUT", f"MUTATES_INPUT: the strategy modified panel.{changed} in place; a rule must "
                      f"treat the panel as read-only", {"field": changed})
    if determinism_check:
        again = _run_strategy(fn, _clone(panel), params, cols)
        cell = _first_divergence(baseline, again)
        if cell is not None:
            i, j = cell
            return result("NON_DETERMINISTIC", f"NON_DETERMINISTIC: two runs on the same panel differ at row {i} "
                          f"({idx[i]}), {cols[j]!r}: {baseline[i, j]!r} vs {again[i, j]!r}; seed the rule",
                          {"row": i, "timestamp": str(idx[i]), "column": str(cols[j])})

    def leak(k: int, kind: str, cell: tuple, probe: np.ndarray, what: str) -> AuditResult:
        i, j = cell
        return result(
            "LEAKY",
            f"LEAKY: output[{i}, {cols[j]!r}] ({idx[i]}) changed from {baseline[i, j]!r} to {probe[i, j]!r} when the "
            f"rows after {k} were {what}; a decision at row {i} cannot depend on row {k + 1} or later",
            {"probe_row": k, "probe_kind": kind, "row": i, "timestamp": str(idx[i]), "column": str(cols[j]),
             "baseline": float(baseline[i, j]), "probe": float(probe[i, j])},
        )

    def crash(k: int, kind: str, exc: Exception, what: str) -> AuditResult:
        return result("LEAKY", f"LEAKY: the strategy raised {type(exc).__name__}: {exc} when the rows after {k} were "
                      f"{what}; decisions at or before {k} cannot need them",
                      {"probe_row": k, "probe_kind": kind, "exception": f"{type(exc).__name__}: {exc}"})

    passes = [("scramble", False)] + ([("scramble_mirrored", True)] if antithetic else [])
    for k in probes:
        for kind, mirror in passes:
            scrambled = scramble_after(panel, k, np.random.default_rng([base_seed, k]), mirror=mirror)
            try:
                probe = _run_strategy(fn, scrambled, params, cols)
            except Refused:
                raise
            except Exception as exc:  # noqa: BLE001 — a crash once the future changed IS the finding
                return crash(k, kind, exc, "regenerated")
            cell = _first_divergence(baseline[: k + 1], probe[: k + 1])
            if cell is not None:
                return leak(k, kind, cell, probe, "regenerated")
            rows_compared += k + 1
        if truncation_probe:
            try:
                probe = _run_strategy(fn, _truncate(panel, k), params, cols)
            except Refused:
                raise
            except Exception as exc:  # noqa: BLE001
                return crash(k, "truncation", exc, "removed")
            cell = _first_divergence(baseline[: k + 1], probe)
            if cell is not None:
                return leak(k, "truncation", cell, probe, "removed")
            rows_compared += k + 1

    how = "regenerated" + (" (both directions)" if antithetic else "") + (" and when they were removed" if truncation_probe else "")
    return result(
        "PASS",
        f"PASS: every output row at or before each probe row ({len(probes)} probes) was bit-identical when the rows "
        f"after it were {how}. This certifies that the inputs were legal, not that the rule is good; data read "
        f"outside the panel is a code-review question.",
    )


# --------------------------------------------------------------------------------------------------
# Lag sensitivity
# --------------------------------------------------------------------------------------------------
def _windowed(net, window: Window) -> np.ndarray:
    if isinstance(net, pd.Series):
        return net.to_numpy(dtype=np.float64)[window_mask(net.index, window)]
    if window is not None:
        raise ValueError("a date window needs a pandas Series with a tz-aware DatetimeIndex")
    return np.asarray(net, dtype=np.float64).reshape(-1)


def lag_sensitivity(net_a, net_b, ppy: float, *, window: Window = None) -> Dict[str, object]:
    """PRINT-PROXIMITY flag from two net return series of the SAME rule.

    net_a   per-print net under the base timing (lag 1, or exec prices with extra_lag 0)
    net_b   the same rule with one more print of delay (lag 2 / the later exec print)
    ppy     periods per year (annualisation of both Sharpes)
    window  optional (start, end) scoring window, as in `stats.summarize`; pass the same window the
            rule is scored on so warm-up rows do not dilute either Sharpe.

    Returns {'flag': bool, 'label': 'PRINT-PROXIMITY' | None, 'sharpe_a', 'sharpe_b', 'ratio', 'reason'}.
    flag = Sharpe_a > 0 and Sharpe_a > 2 * Sharpe_b (strict). If Sharpe_a > 0 and Sharpe_b is NaN the
    flag is raised. Sharpe = mean / std(ddof=1) * sqrt(ppy) (`stats.sharpe_ratio`).
    """
    a = sharpe_ratio(_windowed(net_a, window), ppy)
    b = sharpe_ratio(_windowed(net_b, window), ppy)
    if not np.isfinite(a) or a <= 0.0:
        flag, reason = False, "Sharpe_a is not positive: there is no edge to lose"
    elif not np.isfinite(b):
        flag, reason = True, "Sharpe_b unavailable while Sharpe_a > 0: flagged (the delayed run must be readable)"
    elif a > 2.0 * b:
        flag, reason = True, f"Sharpe_a = {a:.3f} > 2 x Sharpe_b = {2 * b:.3f}: the edge does not survive one more print"
    else:
        flag, reason = False, f"Sharpe_a = {a:.3f} <= 2 x Sharpe_b = {2 * b:.3f}"
    return {
        "flag": bool(flag),
        "label": PRINT_PROXIMITY if flag else None,
        "sharpe_a": float(a),
        "sharpe_b": float(b),
        "ratio": float(a / b) if np.isfinite(a) and np.isfinite(b) and b != 0 else float("nan"),
        "reason": reason,
    }


__all__ = ["AuditResult", "future_scramble_audit", "scramble_after", "lag_sensitivity", "PRINT_PROXIMITY",
           "JUMP_RANGE", "REAL_SHIFT_SD"]
