#!/usr/bin/env python3
"""INVENT_R3 exotic theme: build a compact DAILY (UTC) perp panel from the hourly ext panel.

Source: research/data/perpmicro_cache/panel1h_ext.npz  (439 symbols x 40536 hours,
2022-01-01 -> 2026-08-16, Binance USD-M 5m klines rolled to 1h + t23 funding).

Daily fields per symbol:
  o   first available OPEN of the UTC day
  h,l high / low of the day
  c   last available CLOSE of the day
  qv  quote volume summed
  ntr trade count summed
  tbq taker-BUY quote volume summed
  fnd sum of funding RATES settled during the day (the amount a long pays)
  nh  number of hours with data (data-quality gate)

Output: research/data/invr3_cache/daily.npz
"""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext.npz"
OUT = ROOT / "research" / "data" / "invr3_cache"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    z = np.load(SRC, allow_pickle=True)
    t = z["t"]
    sym = z["symbols"]
    NH = len(t)
    ND = NH // 24
    S = len(sym)
    print(f"{S} symbols, {NH} hours -> {ND} days")

    def day_reduce(name, how):
        a = z[name][:, : ND * 24].reshape(S, ND, 24)
        if how == "sum":
            out = np.nansum(a, axis=2)
            out[~np.isfinite(a).any(axis=2)] = np.nan
        elif how == "max":
            out = np.nanmax(np.where(np.isfinite(a), a, -np.inf), axis=2)
            out[~np.isfinite(out)] = np.nan
        elif how == "min":
            out = np.nanmin(np.where(np.isfinite(a), a, np.inf), axis=2)
            out[~np.isfinite(out)] = np.nan
        elif how in ("first", "last"):
            fin = np.isfinite(a)
            idx = np.where(fin, np.arange(24)[None, None, :], 999 if how == "first" else -1)
            k = idx.min(axis=2) if how == "first" else idx.max(axis=2)
            ok = (k >= 0) & (k < 24)
            kk = np.clip(k, 0, 23)
            out = np.take_along_axis(a, kk[:, :, None], axis=2)[:, :, 0]
            out = np.where(ok, out, np.nan)
        return out.astype(np.float32)

    d = {}
    d["o"] = day_reduce("o", "first")
    d["c"] = day_reduce("c", "last")
    d["h"] = day_reduce("h", "max")
    d["l"] = day_reduce("l", "min")
    for k in ("qv", "ntr", "tbq"):
        d[k] = day_reduce(k, "sum")
    # funding: only bars that are settlement bars carry a charge
    fund = z["fund"][:, : ND * 24].reshape(S, ND, 24)
    age = z["fund_age_h"][:, : ND * 24].reshape(S, ND, 24)
    settle = np.isfinite(age) & (age < 1.0) & np.isfinite(fund)
    d["fnd"] = np.where(settle, fund, 0.0).sum(axis=2).astype(np.float32)
    d["nsettle"] = settle.sum(axis=2).astype(np.float32)
    d["nh"] = np.isfinite(z["c"][:, : ND * 24].reshape(S, ND, 24)).sum(axis=2).astype(np.float32)

    days = (t[: ND * 24 : 24] // 86_400_000).astype(np.int64)  # UTC day index
    np.savez_compressed(OUT / "daily.npz", symbols=sym, day=days, **d)
    print("wrote", OUT / "daily.npz")
    print("first day", dt.date(1970, 1, 1) + dt.timedelta(days=int(days[0])),
          "last day", dt.date(1970, 1, 1) + dt.timedelta(days=int(days[-1])))


if __name__ == "__main__":
    main()
