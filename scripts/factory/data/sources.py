"""Raw downloads + offline readers for FRED, ECB, BIS and Alpaca.

    research/factory/.venv/bin/python -m scripts.factory.data.sources fred ecb bis alpaca

Every download is written unmodified under research/factory/data/raw/<source>/ and logged in
raw/<source>/_fetch_log.jsonl with its URL, UTC fetch time, size and sha256. The readers below parse
ONLY those raw files (no network), so every panel is reproducible from disk.

Endpoints
  FRED    https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>                  (no key)
  ECB     https://data-api.ecb.europa.eu/service/data/<FLOW>/<KEY>?format=csvdata
            EXR/D.<CCY>.EUR.SP00.A   euro reference rates (units of CCY per 1 EUR, 14:15 CET concertation)
            EON/D.EONIA_TO.RATE      EONIA (1999-01-04 .. 2021-12-31; = EUR STR + 8.5 bp from 2019-10-02)
            EST/B.EU000A2X2A25.WT    euro short-term rate (volume-weighted trimmed mean), from 2019-10-01
  BIS     https://stats.bis.org/api/v1/data/WS_CBPOL/D.<CC>?format=csv&detail=dataonly   daily policy rates
          https://stats.bis.org/api/v1/data/WS_LONG_CPI/M.<CC>.628?format=csv&detail=dataonly  CPI index 2010=100
          (+ one `lastNObservations=1` full-detail call per series for the BIS description text)
  Alpaca  https://data.alpaca.markets/v2/stocks/bars  (daily bars, feed=sip, adjustment=all|raw)
          credentials from <repo>/.env travel in headers only and are never written anywhere.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .common import RAW, HttpError, fetch_log, http_get, load_env_value, save_raw, utc_now  # noqa: F401 (RAW re-exported)

# ------------------------------------------------------------------------------------------ what we pull
FRED_IDS = ["DFF", "IUDSOIA", "DCOILWTICO", "IRSTCI01JPM156N",
            "DEXUSEU", "DEXUSUK", "DEXJPUS", "DEXSZUS", "DEXCAUS", "DEXUSAL", "DEXUSNZ", "DEXSDUS", "DEXNOUS",
            "DEXMXUS", "DEXSFUS", "DEXSIUS"]

ECB_CCYS = ["USD", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "MXN", "ZAR", "SGD", "PLN", "HUF",
            "CZK", "ILS", "TRY"]
ECB_SERIES = {  # name -> (flow, key)
    "EONIA": ("EON", "D.EONIA_TO.RATE"),
    "ESTR": ("EST", "B.EU000A2X2A25.WT"),
}

# currency -> BIS reference area
BIS_CBPOL_AREA = {"GBP": "GB", "JPY": "JP", "CHF": "CH", "CAD": "CA", "AUD": "AU", "NZD": "NZ", "SEK": "SE",
                  "NOK": "NO", "MXN": "MX", "ZAR": "ZA", "PLN": "PL", "HUF": "HU", "CZK": "CZ", "ILS": "IL",
                  "TRY": "TR", "SGD": "SG"}          # SG is requested so that its ABSENCE is on record
BIS_CPI_AREA = {"USD": "US", "EUR": "XM", "GBP": "GB", "JPY": "JP", "CHF": "CH", "CAD": "CA", "AUD": "AU",
                "NZD": "NZ", "SEK": "SE", "NOK": "NO", "MXN": "MX", "ZAR": "ZA", "SGD": "SG", "PLN": "PL",
                "HUF": "HU", "CZK": "CZ", "ILS": "IL", "TRY": "TR"}

MACRO_ETFS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VGK", "EWJ", "EWU", "EWG", "FXI", "INDA", "EWZ", "EWA", "EWC",
              "EWY", "EWT",
              "XLE", "XLF", "XLK", "XLV", "XLU", "XLI", "XLP", "XLY", "XLB",
              "SHY", "IEF", "TLT", "TIP", "LQD", "HYG", "EMB", "AGG",
              "GLD", "SLV", "USO", "UNG", "DBC", "DBA", "CPER",
              "VNQ"]
assert len(MACRO_ETFS) == 41 and len(set(MACRO_ETFS)) == 41


def _fresh(source: str, relname: str, max_age_h: float) -> bool:
    rec = fetch_log(source).get(str(Path("raw") / source / relname))
    if not rec or not (RAW / source / relname).exists():
        return False
    t = datetime.strptime(rec["fetched_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t) < timedelta(hours=max_age_h)


def _log(msg: str) -> None:
    print(f"{utc_now()} {msg}", flush=True)


# ------------------------------------------------------------------------------------------------ fetch
def fetch_fred(ids: Optional[List[str]] = None, *, max_age_h: float = 12.0) -> None:
    for sid in ids or FRED_IDS:
        rel = f"{sid}.csv"
        if _fresh("fred", rel, max_age_h):
            continue
        r = http_get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid})
        if not r.text.startswith("observation_date"):
            raise RuntimeError(f"FRED {sid}: unexpected payload {r.text[:120]!r}")
        save_raw("fred", rel, r.content, r.url)
        _log(f"fred {sid}: {len(r.content)} bytes")


def fetch_ecb(*, max_age_h: float = 12.0) -> None:
    base = "https://data-api.ecb.europa.eu/service/data"
    jobs = [(f"EXR_D_{c}_EUR_SP00_A.csv", f"{base}/EXR/D.{c}.EUR.SP00.A") for c in ECB_CCYS]
    jobs += [(f"{flow}_{key.replace('.', '_')}.csv", f"{base}/{flow}/{key}") for flow, key in ECB_SERIES.values()]
    for rel, url in jobs:
        if _fresh("ecb", rel, max_age_h):
            continue
        r = http_get(url, params={"format": "csvdata"})
        if "TIME_PERIOD" not in r.text[:2000]:
            raise RuntimeError(f"ECB {url}: unexpected payload {r.text[:120]!r}")
        save_raw("ecb", rel, r.content, r.url)
        _log(f"ecb {rel}: {len(r.content)} bytes")


def fetch_bis(*, max_age_h: float = 12.0) -> None:
    base = "https://stats.bis.org/api/v1/data"
    for ccy, cc in BIS_CBPOL_AREA.items():
        for rel, params in ((f"WS_CBPOL_D_{cc}.csv", {"format": "csv", "detail": "dataonly"}),
                            (f"WS_CBPOL_D_{cc}_meta.csv", {"format": "csv", "lastNObservations": 1})):
            if _fresh("bis", rel, max_age_h):
                continue
            try:
                r = http_get(f"{base}/WS_CBPOL/D.{cc}", params=params)
            except HttpError as e:                 # BIS answers 404 "No data" when a series does not exist
                save_raw("bis", rel.replace(".csv", ".NO_DATA.xml"), e.body.encode(), e.url,
                         extra={"http_status": e.status})
                _log(f"bis CBPOL {cc}: HTTP {e.status} (no such series) - recorded")
                break
            save_raw("bis", rel, r.content, r.url)
            _log(f"bis {rel}: {len(r.content)} bytes")
    for ccy, cc in BIS_CPI_AREA.items():
        for rel, params in ((f"WS_LONG_CPI_M_{cc}_628.csv", {"format": "csv", "detail": "dataonly"}),
                            (f"WS_LONG_CPI_M_{cc}_628_meta.csv", {"format": "csv", "lastNObservations": 1})):
            if _fresh("bis", rel, max_age_h):
                continue
            try:
                r = http_get(f"{base}/WS_LONG_CPI/M.{cc}.628", params=params)
            except HttpError as e:
                save_raw("bis", rel.replace(".csv", ".NO_DATA.xml"), e.body.encode(), e.url,
                         extra={"http_status": e.status})
                _log(f"bis CPI {cc}: HTTP {e.status} (no such series) - recorded")
                break
            save_raw("bis", rel, r.content, r.url)
            _log(f"bis {rel}: {len(r.content)} bytes")


def fetch_alpaca(symbols: Optional[List[str]] = None, *, start: str = "2016-01-01", max_age_h: float = 12.0) -> None:
    """Daily bars, both adjustment modes. `end` = 00:00 UTC today, so only completed sessions come back."""
    symbols = symbols or MACRO_ETFS
    headers = {"APCA-API-KEY-ID": load_env_value("ALPACA_API_KEY_ID"),
               "APCA-API-SECRET-KEY": load_env_value("ALPACA_API_SECRET_KEY")}
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    for adj in ("all", "raw"):
        if _fresh("alpaca", f"bars_1Day_{adj}_DONE.json", max_age_h):
            continue
        token, page, nbars = None, 0, 0
        while True:
            params = {"symbols": ",".join(symbols), "timeframe": "1Day", "adjustment": adj, "feed": "sip",
                      "start": start, "end": end, "limit": 10000}
            if token:
                params["page_token"] = token
            r = http_get("https://data.alpaca.markets/v2/stocks/bars", params=params, headers=headers)
            data = r.json()
            save_raw("alpaca", f"bars_1Day_{adj}_page{page:03d}.json", r.content, r.url)
            nbars += sum(len(v) for v in data.get("bars", {}).values())
            token = data.get("next_page_token")
            page += 1
            if not token:
                break
        save_raw("alpaca", f"bars_1Day_{adj}_DONE.json",
                 json.dumps({"pages": page, "bars": nbars, "start": start, "end": end, "symbols": symbols}).encode(),
                 "https://data.alpaca.markets/v2/stocks/bars (paging summary, written locally)")
        _log(f"alpaca adjustment={adj}: {page} pages, {nbars} bars")


# ---------------------------------------------------------------------------------------------- readers
def read_fred(sid: str) -> pd.Series:
    """Daily series indexed by naive calendar date; missing observations ('' or '.') are NaN."""
    df = pd.read_csv(RAW / "fred" / f"{sid}.csv", na_values=[".", ""], keep_default_na=True)
    s = pd.Series(pd.to_numeric(df[sid], errors="coerce").to_numpy(dtype="float64"),
                  index=pd.DatetimeIndex(pd.to_datetime(df["observation_date"])), name=sid)
    return s[~s.index.duplicated()].sort_index()


def _read_sdmx_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, usecols=lambda c: c in ("TIME_PERIOD", "OBS_VALUE"), dtype={"TIME_PERIOD": "string"})


def read_ecb_exr(ccy: str) -> pd.Series:
    """Units of `ccy` per 1 EUR at the ECB reference fixing; index = fixing date (naive)."""
    df = _read_sdmx_csv(RAW / "ecb" / f"EXR_D_{ccy}_EUR_SP00_A.csv")
    s = pd.Series(pd.to_numeric(df["OBS_VALUE"], errors="coerce").to_numpy(dtype="float64"),
                  index=pd.DatetimeIndex(pd.to_datetime(df["TIME_PERIOD"])), name=ccy)
    return s[~s.index.duplicated()].sort_index()


def read_ecb_rate(name: str) -> pd.Series:
    flow, key = ECB_SERIES[name]
    df = _read_sdmx_csv(RAW / "ecb" / f"{flow}_{key.replace('.', '_')}.csv")
    s = pd.Series(pd.to_numeric(df["OBS_VALUE"], errors="coerce").to_numpy(dtype="float64"),
                  index=pd.DatetimeIndex(pd.to_datetime(df["TIME_PERIOD"])), name=name)
    return s[~s.index.duplicated()].sort_index()


def read_bis_cbpol(cc: str) -> Optional[pd.Series]:
    """BIS daily central-bank policy rate (per cent p.a.), calendar-day index; None if BIS has no series."""
    p = RAW / "bis" / f"WS_CBPOL_D_{cc}.csv"
    if not p.exists():
        return None
    df = _read_sdmx_csv(p)
    s = pd.Series(pd.to_numeric(df["OBS_VALUE"], errors="coerce").to_numpy(dtype="float64"),
                  index=pd.DatetimeIndex(pd.to_datetime(df["TIME_PERIOD"])), name=cc)
    return s[~s.index.duplicated()].sort_index()


def read_bis_meta(rel: str) -> dict:
    p = RAW / "bis" / rel
    if not p.exists():
        return {}
    rows = list(csv.DictReader(io.StringIO(p.read_text())))
    return rows[-1] if rows else {}


def read_bis_cpi(cc: str) -> Optional[pd.Series]:
    """BIS long CPI index (2010 = 100), monthly; index = first day of the reference month (naive)."""
    p = RAW / "bis" / f"WS_LONG_CPI_M_{cc}_628.csv"
    if not p.exists():
        return None
    df = _read_sdmx_csv(p)
    s = pd.Series(pd.to_numeric(df["OBS_VALUE"], errors="coerce").to_numpy(dtype="float64"),
                  index=pd.DatetimeIndex(pd.to_datetime(df["TIME_PERIOD"] + "-01")), name=cc)
    return s[~s.index.duplicated()].sort_index()


def read_alpaca(adjustment: str) -> Dict[str, pd.DataFrame]:
    """symbol -> DataFrame indexed by the SESSION DATE (America/New_York calendar date of the bar's `t`),
    columns o,h,l,c,v,n,vw."""
    out: Dict[str, list] = {}
    for p in sorted((RAW / "alpaca").glob(f"bars_1Day_{adjustment}_page*.json")):
        data = json.loads(p.read_text())
        for sym, bars in (data.get("bars") or {}).items():
            out.setdefault(sym, []).extend(bars)
    res = {}
    for sym, bars in out.items():
        df = pd.DataFrame(bars)
        t = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York")
        if not ((t.dt.hour == 0) & (t.dt.minute == 0)).all():
            raise RuntimeError(f"alpaca {sym}: a daily bar is not stamped at New York midnight")
        df.index = pd.DatetimeIndex(t.dt.tz_localize(None).dt.normalize())
        df = df.drop(columns=["t"])
        res[sym] = df[~df.index.duplicated()].sort_index()
    return res


def main(argv=None) -> int:
    what = (argv or sys.argv[1:]) or ["fred", "ecb", "bis", "alpaca"]
    for w in what:
        {"fred": fetch_fred, "ecb": fetch_ecb, "bis": fetch_bis, "alpaca": fetch_alpaca}[w]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
