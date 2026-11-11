"""Lane writer / loader: parquet + manifest.json <-> PanelBundle (no network anywhere in this file).

Layout of one lane (research/factory/data/<LANE>/):
    prices.parquet, carry.parquet, tbill.parquet, aux/<name>.parquet, manifest.json
Every parquet has the UTC print index stored as its pandas index (name "ts").
`manifest.json` carries the sha256 of every parquet; `load_lane` refuses a file whose hash differs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ..panel import PanelBundle            # conductor-owned data object (never edited here)
from .common import DATA, REPO, atomic_write_json, sha256_file, utc_now

LANES = ("FX", "FX-EXEC", "FX-FRED", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT")
MAX_FFILL = 3


def lane_dir(lane: str) -> Path:
    return DATA / lane


def _norm_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if idx.tz is None:
        raise ValueError("index must be tz-aware")
    out = idx.tz_convert("UTC").as_unit("ns")
    out.name = "ts"
    return out


def limited_ffill(df: pd.DataFrame, limit: int = MAX_FFILL, *, interior_only: bool = True):
    """Forward-fill at most `limit` consecutive missing prints; longer gaps keep NaN from the
    (limit+1)-th print on. With `interior_only`, nothing is filled after a column's last real value.
    Returns (filled, stats) with per-column counts:
      missing_prints   NaN cells between the column's first and last real value (before filling)
      ffilled          cells filled
      left_nan         cells still NaN inside that span after filling
    """
    filled = df.ffill(limit=limit)
    stats = {}
    for c in df.columns:
        s = df[c]
        if s.notna().any():
            a, b = s.first_valid_index(), s.last_valid_index()
            inside = s.loc[a:b]
            if interior_only:
                filled.loc[filled.index > b, c] = np.nan
            f_inside = filled[c].loc[a:b]
            stats[c] = {"missing_prints": int(inside.isna().sum()),
                        "ffilled": int(inside.isna().sum() - f_inside.isna().sum()),
                        "left_nan": int(f_inside.isna().sum())}
        else:
            stats[c] = {"missing_prints": 0, "ffilled": 0, "left_nan": 0}
    return filled, stats


def asof_on_or_before(obs: pd.Series, print_dates: pd.DatetimeIndex, *, max_stale_prints: int = MAX_FFILL):
    """Like `asof_strictly_before`, but an observation dated ON the print's date is usable (for a source
    that is published earlier in the day than the print, e.g. the 14:15 CET ECB fixing for a 16:00 New
    York close). FRESH = the observation is dated after the previous print's date."""
    return asof_strictly_before(obs, print_dates, max_stale_prints=max_stale_prints, _inclusive=True)


def asof_strictly_before(obs: pd.Series, print_dates: pd.DatetimeIndex, *, max_stale_prints: int = MAX_FFILL,
                         _inclusive: bool = False):
    """Value known BEFORE each print: the last observation dated strictly before the print's date.

    `obs` is indexed by naive observation dates, `print_dates` by naive print dates (sorted, unique).
    A print is FRESH when that observation is dated on/after the previous print's date (something new
    arrived since the last print); otherwise the value is a forward-fill. More than `max_stale_prints`
    consecutive forward-filled prints -> NaN from the next one on (the source has a gap).
    Returns (values Series on print_dates, stats dict).
    """
    o = obs.dropna().sort_index()
    pd_vals = print_dates.values.astype("datetime64[ns]")
    n = len(pd_vals)
    if o.empty:
        return pd.Series(np.nan, index=print_dates), {"fresh": 0, "ffilled": 0, "ffilled_beyond_3_prints": 0,
                                                      "max_stale_prints_allowed": int(max_stale_prints),
                                                      "nan_stale": 0, "nan_before_start": n,
                                                      "first_valid_print": None, "last_valid_print": None}
    o_dates = o.index.values.astype("datetime64[ns]")
    pos = np.searchsorted(o_dates, pd_vals, side="right" if _inclusive else "left") - 1
    ok = pos >= 0
    safe = np.clip(pos, 0, None)
    val = np.where(ok, o.to_numpy(dtype="float64")[safe], np.nan)
    odate = o_dates[safe]
    prev = np.empty(n, dtype="datetime64[ns]")
    prev[1:] = pd_vals[:-1]
    prev[0] = pd_vals[0] - np.timedelta64(7, "D")              # first print: accept an observation < 7 days old
    fresh = ok & ((odate > prev) if _inclusive else (odate >= prev))
    run = np.zeros(n, dtype="int64")
    for k in range(n):
        if not ok[k] or fresh[k]:
            run[k] = 0
        else:
            run[k] = (run[k - 1] if k else 0) + 1
    stale = ok & (run > max_stale_prints)
    val[stale] = np.nan
    out = pd.Series(val, index=print_dates)
    st = {"fresh": int(fresh.sum()), "ffilled": int((ok & ~fresh & ~stale).sum()),
          "ffilled_beyond_3_prints": int((ok & ~fresh & ~stale & (run > MAX_FFILL)).sum()),
          "max_stale_prints_allowed": int(max_stale_prints), "nan_stale": int(stale.sum()),
          "nan_before_start": int((~ok).sum()),
          "first_valid_print": None if out.notna().sum() == 0 else str(out.first_valid_index().date()),
          "last_valid_print": None if out.notna().sum() == 0 else str(out.last_valid_index().date())}
    return out, st


def cpi_available(cpi: pd.Series, print_dates: pd.DatetimeIndex, *, quarterly: bool, max_missed_releases: int = 3):
    """CPI index level usable at each print.

    `cpi` is indexed by the FIRST DAY of its reference month. Availability rule (frozen by the task
    brief): a monthly observation becomes available 2 months after the start of its reference month
    (January -> 1 March); a quarterly one 4 months after the start of its reference quarter
    (Q1 -> 1 May). For quarterly sources (BIS repeats the quarter's value in each of its 3 months)
    only the quarter-start row is used. The level stays in force until the next one becomes available;
    if more than `max_missed_releases` expected releases fail to arrive the value turns NaN.
    Returns (values on print_dates, stats)."""
    s = cpi.dropna().sort_index()
    viol = 0
    if quarterly:
        q = s[s.index.month.isin([1, 4, 7, 10])]
        for d, v in q.items():                                   # the 3 months of a quarter must agree
            rest = s.reindex([d + pd.DateOffset(months=1), d + pd.DateOffset(months=2)]).dropna()
            if len(rest) and not np.allclose(rest.to_numpy(), v, rtol=0, atol=1e-9):
                viol += 1
        s = q
        lag, period = 4, 3
    else:
        lag, period = 2, 1
    avail = pd.DatetimeIndex([d + pd.DateOffset(months=lag) for d in s.index])
    a_vals = avail.values.astype("datetime64[ns]")
    pd_vals = print_dates.values.astype("datetime64[ns]")
    pos = np.searchsorted(a_vals, pd_vals, side="right") - 1    # available on/before the print's date
    ok = pos >= 0
    safe = np.clip(pos, 0, None)
    val = np.where(ok, s.to_numpy(dtype="float64")[safe], np.nan)
    expire = pd.DatetimeIndex([a + pd.DateOffset(months=period * (max_missed_releases + 1)) for a in avail]).values.astype("datetime64[ns]")
    stale = ok & (pd_vals >= expire[safe])
    val[stale] = np.nan
    out = pd.Series(val, index=print_dates)
    st = {"observations_used": int(len(s)), "first_reference_period": str(s.index[0].date()),
          "last_reference_period": str(s.index[-1].date()), "last_available_from": str(avail[-1].date()),
          "nan_before_start": int((~ok).sum()), "nan_stale": int(stale.sum()),
          "quarterly": bool(quarterly), "quarter_consistency_violations": int(viol)}
    return out, st


def to_utc_index(dates: pd.DatetimeIndex, hhmm: str, tz: str) -> pd.DatetimeIndex:
    """Naive calendar dates + a local wall-clock time in `tz` -> UTC DatetimeIndex."""
    h, m = (int(x) for x in hhmm.split(":"))
    local = (pd.DatetimeIndex(dates).normalize() + pd.Timedelta(hours=h, minutes=m)).tz_localize(tz)
    return _norm_index(local)


def write_lane(lane: str, prices: pd.DataFrame, carry: pd.DataFrame, tbill: pd.Series, aux: Dict[str, pd.DataFrame],
               meta: dict, manifest: dict) -> Path:
    d = lane_dir(lane)
    (d / "aux").mkdir(parents=True, exist_ok=True)
    idx = _norm_index(prices.index)
    if not idx.is_monotonic_increasing or not idx.is_unique:
        raise ValueError("print index must be sorted and unique")
    now = pd.Timestamp.now(tz="UTC")
    if idx[-1] > now:
        raise ValueError(f"{lane}: last print {idx[-1]} is in the future")
    files = {}

    def put(rel: str, df: pd.DataFrame) -> None:
        df = df.copy()
        df.index = _norm_index(df.index)
        if not df.index.equals(idx):
            raise ValueError(f"{lane}/{rel}: index differs from prices")
        p = d / rel
        df.to_parquet(p, engine="pyarrow", compression="zstd")
        files[rel] = {"sha256": sha256_file(p), "rows": int(df.shape[0]), "cols": int(df.shape[1]),
                      "bytes": int(p.stat().st_size)}

    put("prices.parquet", prices.astype("float64"))
    if list(carry.columns) != list(prices.columns):
        raise ValueError("carry columns must equal prices columns")
    put("carry.parquet", carry.astype("float64"))
    put("tbill.parquet", tbill.astype("float64").to_frame("tbill"))
    # drop aux files of an earlier build that are not part of this one
    for old in (d / "aux").glob("*.parquet"):
        if old.stem not in aux:
            old.unlink()
    for name, df in aux.items():
        put(f"aux/{name}.parquet", df)
    meta = dict(meta)
    meta["lane"] = lane
    meta["source_manifest"] = str((d / "manifest.json").relative_to(REPO))
    per_inst = {}
    for c in prices.columns:
        s = prices[c].dropna()
        cs = carry[c].dropna()
        per_inst[c] = {"first_print": None if s.empty else str(s.index[0]), "last_print": None if s.empty else str(s.index[-1]),
                       "n_prints": int(len(s)),
                       "carry_first": None if cs.empty else str(cs.index[0]), "carry_last": None if cs.empty else str(cs.index[-1]),
                       "n_carry": int(len(cs))}
    out = {"lane": lane, "built_utc": utc_now(), "rows": int(len(idx)), "columns": list(map(str, prices.columns)),
           "n_columns": int(prices.shape[1]), "first_print": str(idx[0]), "last_print": str(idx[-1]),
           "meta": meta, "files": files, "instruments": per_inst}
    out.update(manifest)
    atomic_write_json(d / "manifest.json", out)
    return d


def read_manifest(lane: str) -> dict:
    return json.loads((lane_dir(lane) / "manifest.json").read_text())


def write_index() -> Path:
    """research/factory/data/index.json: one line of facts per built lane (shape, range, manifest path)."""
    out = {"written_utc": utc_now(), "lanes": {}}
    for lane in LANES:
        mf = lane_dir(lane) / "manifest.json"
        if not mf.exists():
            out["lanes"][lane] = {"built": False}
            continue
        m = json.loads(mf.read_text())
        out["lanes"][lane] = {"built": True, "built_utc": m["built_utc"], "rows": m["rows"], "columns": m["n_columns"],
                              "first_print": m["first_print"], "last_print": m["last_print"],
                              "periods_per_year": m["meta"].get("periods_per_year"),
                              "aux": sorted(Path(r).stem for r in m["files"] if r.startswith("aux/")),
                              "exec_prices_strictly_after_decision": m["meta"].get("exec_prices_strictly_after_decision", False),
                              "manifest": str(mf.relative_to(REPO)),
                              "parquet_bytes": int(sum(f["bytes"] for f in m["files"].values()))}
    p = DATA / "index.json"
    atomic_write_json(p, out)
    return p


def load_lane(lane_id: str, *, verify_hashes: bool = True) -> PanelBundle:
    """Rebuild the PanelBundle of one lane from parquet. No network. Validates:
    sha256 of every parquet against the manifest, index tz/sort/uniqueness (PanelBundle itself), no print
    in the future, and that `exec_prices` only ships together with the strictly-after-decision flag."""
    if lane_id not in LANES:
        raise KeyError(f"unknown lane {lane_id!r}; known: {LANES}")
    d = lane_dir(lane_id)
    mf = d / "manifest.json"
    if not mf.exists():
        raise FileNotFoundError(f"lane {lane_id} has not been built ({mf} missing)")
    man = json.loads(mf.read_text())
    if verify_hashes:
        for rel, rec in man["files"].items():
            h = sha256_file(d / rel)
            if h != rec["sha256"]:
                raise RuntimeError(f"{lane_id}/{rel}: sha256 {h} differs from the manifest ({rec['sha256']})")
    prices = pd.read_parquet(d / "prices.parquet")
    carry = pd.read_parquet(d / "carry.parquet")
    tbill = pd.read_parquet(d / "tbill.parquet")["tbill"]
    aux = {}
    for rel in man["files"]:
        if rel.startswith("aux/"):
            aux[Path(rel).stem] = pd.read_parquet(d / rel)
    meta = dict(man["meta"])
    if prices.index[-1] > pd.Timestamp.now(tz="UTC"):
        raise RuntimeError(f"{lane_id}: a print is stamped in the future")
    has_exec = "exec_prices" in aux
    if has_exec and meta.get("exec_prices_strictly_after_decision") is not True:
        raise RuntimeError(f"{lane_id}: exec_prices present without the strictly-after-decision guarantee")
    if not has_exec:
        meta.pop("exec_prices_strictly_after_decision", None)
    # DESIGN v2 §3.8: what `meta` must carry
    need = ["periods_per_year", "print_convention", "universe_groups", "source_manifest"] + (["asset_class_of"] if lane_id == "MACRO" else [])
    missing = [k for k in need if k not in meta]
    if missing:
        raise RuntimeError(f"{lane_id}: meta lacks {missing}")
    cols = set(prices.columns)
    for g, members in meta["universe_groups"].items():
        if not set(members) <= cols:
            raise RuntimeError(f"{lane_id}: universe group {g!r} names instruments that are not in the panel")
    if list(carry.columns) != list(prices.columns) or not carry.index.equals(prices.index):
        raise RuntimeError(f"{lane_id}: carry is not aligned to prices")
    if "universe_mask" in aux and not (aux["universe_mask"].dtypes == bool).all():
        raise RuntimeError(f"{lane_id}: universe_mask is not boolean")
    return PanelBundle(lane=lane_id, prices=prices, carry=carry, aux=aux, tbill=tbill, meta=meta)
