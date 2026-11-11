"""Binance raw files -> daily frames, point-in-time universe, exec prints, funding carry.

Offline: every function here reads research/factory/data/raw/binance/** only.

ROW-LABEL CONVENTION (both crypto lanes)
  The row stamped `D 00:00 UTC` holds the CLOSE of the daily candle that ENDED at `D 00:00` (the candle
  that opened at `D-1 00:00`). That close is the decision print. `volume_quote` on row D is the quote
  volume of that same candle. Execution prints are later in clock time on the same row:
  `exec_prices`     = close of the 1h candle opened at `D 00:00`  (the 01:00 UTC price of day D)
  `exec_prices_alt` = close of the 1h candle opened at `D 01:00`  (the 02:00 UTC price of day D)

PHANTOM CANDLES
  After a contract/pair is delisted Binance keeps emitting flat, zero-trade candles (REST and archive
  alike; e.g. FTTUSDT perp is flat at 1.59 with 0 trades from 2022-11-15 to today). A daily candle with
  `count == 0` trades is therefore NOT a print: price and volume are NaN on its row.
  A row D is "live" for a symbol iff the daily candle that ended at D had >= 1 trade. On a live row the
  1h execution candle may itself have zero trades (its close is then the last traded price — for the
  first row after a delisting this is the settlement mark); the manifest counts those.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .common import RAW, atomic_write_json, utc_now

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
SRC = {"perp": "binance/futures_um", "spot": "binance/spot"}

# ---- re-used perp names ---------------------------------------------------------------------------------
# When Binance delists a perpetual and later wants the ticker back, the OLD contract is renamed
# "<SYMBOL>SETTLED" (again "...SETTLEDSETTLED" for a second re-use, "ICPUSDT_SETTLED" in one case).
# REST klines serve the old contract under that name; its funding history stays under the PLAIN name.
# For a ticker that has not been re-listed yet, REST serves the SAME contract under both names (an alias).
SETTLED_RE = re.compile(r"(_?SETTLED)+$")


def plain_name(sym: str) -> str:
    return SETTLED_RE.sub("", sym)


def is_settled_name(sym: str) -> bool:
    return bool(SETTLED_RE.search(sym))


# ---- commodity-backed tokens (both markets) ----------------------------------------------------------
# Tokens redeemable for / pegged to a physical commodity are not crypto assets: PAX Gold and Tether Gold.
# They are the only such bases among Binance's USDT pairs and USDT perps on 2026-11-10 (names scanned for
# XAU/PAXG/GOLD/KAU/XAG/SILV/OIL/DGX/PMGT/PLAT/XPT/XPD/COPPER/BRENT/WTI; the perp venue's "RWA" sub-type
# holds PAXG, XAUT and the ordinary coins MANTRA and CFG). Conductor ruling 2026-11-10: exclude them like
# the TradFi perps and the tokenised equities.
COMMODITY_BACKED_BASES = {"PAXG", "XAUT"}
COMMODITY_REASON = "commodity-backed token (gold) - not a crypto asset"

# ---- perp exclusions (USDT-margined perpetuals that are NOT crypto-coin contracts) ---------------------
PERP_INDEX_NAMES = {"BTCDOMUSDT", "DEFIUSDT", "ALLUSDT", "FOOTBALLUSDT", "BLUEBIRDUSDT", "DOTECOUSDT"}
PERP_STABLE_FIAT_NAMES = {"USDCUSDT"}

# ---- spot exclusions -------------------------------------------------------------------------------
# USD-pegged (verified 2026-11-10: close within 0.9..1.1 on > 90 % of their traded days) and fiat-pegged tokens.
# NOT in the list on purpose: USTC (de-pegged TerraClassicUSD, trades 0.004..0.06) and FRAX (since 2026-01 the
# ticker of the former FXS governance token, 0.22..1.23) — both behave as ordinary coins.
SPOT_STABLE_BASES = {"USDC", "BUSD", "TUSD", "FDUSD", "USDP", "PAX", "DAI", "SUSD", "UST", "BFUSD", "XUSD", "USD1",
                     "USDE", "USDS", "USDSB", "USDSOLD", "RLUSD", "RWUSD", "U",
                     "AEUR", "EURI", "BKRW", "KGST"}          # last four: EUR / KRW / KGS pegged
# Binance tokenised equities / ETFs are spot tokens named <TICKER>B (AAPLB, NVDAB, SPYB ...), first listed
# 2026-06. Most have a TRADIFI_PERPETUAL twin on the futures venue (the stem is that contract's base asset);
# these four do not and were identified by their price level (e.g. STXB 460..944 vs the coin STX 0.3).
SPOT_TOKENIZED_EXTRA = {"BBB", "QNTB", "STXB", "USDEB"}
TOKENIZED_WAVE_START = pd.Timestamp("2026-06-01", tz="UTC")
SPOT_FIAT_BASES = {"EUR", "GBP", "AUD"}
SPOT_WRAPPED_BASES = {"WBTC", "WBETH", "BETH", "BNSOL"}
SPOT_LEVERAGED_PAIRS = (("UP", "DOWN"), ("BULL", "BEAR"))


def spot_leveraged(base: str, bases: set) -> bool:
    """Binance leveraged tokens always exist as a sibling pair (XUP + XDOWN, XBULL + XBEAR, incl. the bare
    BULL / BEAR). A real coin whose ticker merely ends in UP (JUP, SYRUP) has no such sibling."""
    for a, b in SPOT_LEVERAGED_PAIRS:
        if base.endswith(a) and (base[: -len(a)] + b) in bases:
            return True
        if base.endswith(b) and (base[: -len(b)] + a) in bases:
            return True
    return False


ARCHIVE_NAME = re.compile(r"-(?P<kind>1d|1h|fundingRate)-(?P<y>\d{4})-(?P<m>\d{2})(?:-(?P<d>\d{2}))?\.zip$")


def archive_file_bounds(name: str) -> Tuple[int, int]:
    """[start_ms, end_ms) of the period an archive file name claims to hold (a month, or one day)."""
    m = ARCHIVE_NAME.search(name)
    if not m:
        raise ValueError(f"unrecognised archive file name: {name}")
    y, mo = int(m.group("y")), int(m.group("m"))
    if m.group("d"):
        a = pd.Timestamp(year=y, month=mo, day=int(m.group("d")), tz="UTC")
        b = a + pd.Timedelta(days=1)
    else:
        a = pd.Timestamp(year=y, month=mo, day=1, tz="UTC")
        b = a + pd.DateOffset(months=1)
    return int(a.value // 10**6), int(b.value // 10**6)


def _kline_rows_from_csv(b: bytes) -> np.ndarray:
    """(open_ms, close, quote_volume, count) rows from an archive kline CSV (header optional).

    Binance SPOT archive files carry MICROSECOND timestamps from 2025-01 on (milliseconds before; USD-M
    futures files are milliseconds throughout). The unit is detected by magnitude PER FILE; a file that
    mixes units is refused."""
    has_header = b[:1].isalpha()
    df = pd.read_csv(io.BytesIO(b), header=None, skiprows=1 if has_header else 0, usecols=[0, 4, 7, 8],
                     names=["open_time", "close", "quote_volume", "count"], dtype="float64")
    a = df.to_numpy(dtype="float64")
    if len(a):
        micro = a[:, 0] > 1e14
        if micro.any() and not micro.all():
            raise ValueError("kline file mixes millisecond and microsecond timestamps")
        if micro.all():
            a[:, 0] = np.floor(a[:, 0] / 1000.0)
    return a


def archive_kline_rows(path: Path) -> np.ndarray:
    """Rows of one archive zip, with every open time asserted to lie inside the period in the file name."""
    lo, hi = archive_file_bounds(path.name)
    parts = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            a = _kline_rows_from_csv(z.read(n))
            if len(a):
                if a[:, 0].min() < lo or a[:, 0].max() >= hi:
                    raise ValueError(f"{path.name}: a candle opens outside the period named by the file "
                                     f"([{a[:, 0].min():.0f}, {a[:, 0].max():.0f}] vs [{lo}, {hi}))")
                parts.append(a)
    return np.vstack(parts) if parts else np.empty((0, 4))


def _kline_rows_from_rest(b: bytes) -> np.ndarray:
    data = json.loads(b)
    if not data:
        return np.empty((0, 4))
    return np.array([(r[0], float(r[4]), float(r[7]), float(r[8])) for r in data], dtype="float64")


def read_klines(market: str, sym: str, interval: str) -> pd.DataFrame:
    """All candles of one symbol from REST pages and archive zips; index = open time in ms (int64),
    columns close, quote_volume, count, src (0 = REST, 1 = archive). REST wins on duplicates."""
    src = SRC[market]
    parts: List[np.ndarray] = []
    d = RAW / src / f"rest_klines_{interval}" / sym
    if d.exists():
        for p in sorted(d.glob(f"{interval}_*.json")):
            a = _kline_rows_from_rest(p.read_bytes())
            if len(a):
                parts.append(np.column_stack([a, np.zeros(len(a))]))
    d = RAW / src / f"archive_klines_{interval}" / sym
    if d.exists():
        for p in sorted(d.glob("*.zip")):
            a = archive_kline_rows(p)
            if len(a):
                parts.append(np.column_stack([a, np.ones(len(a))]))
    if not parts:
        return pd.DataFrame(columns=["close", "quote_volume", "count", "src"], index=pd.Index([], dtype="int64"))
    a = np.vstack(parts)
    df = pd.DataFrame(a[:, 1:], columns=["close", "quote_volume", "count", "src"], index=a[:, 0].astype("int64"))
    # Candles that do not open on the interval grid are discarded and counted. They exist: after the Binance
    # outage of 8-9 Feb 2018 the spot ARCHIVE holds 43 "hourly" candles per symbol anchored at the restart
    # second (09:28:14.789, 10:28:14.789, ...), while REST serves the same hours on the hour.
    step = DAY_MS if interval == "1d" else HOUR_MS
    off = (df.index.to_numpy() % step) != 0
    n_off = int(off.sum())
    if n_off:
        df = df[~off]
    df = df.sort_values("src", kind="stable")
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df.attrs["off_grid_dropped"] = n_off
    return df


# ------------------------------------------------------------------------------------- classification
def classify_perp(names: List[str]) -> pd.DataFrame:
    """One row per USDT-quoted perpetual name: included in the CRYPTO-PERP lane or not, and why."""
    info = json.loads((RAW / SRC["perp"] / "exchangeInfo" / "latest.json").read_text())
    S = {s["symbol"]: s for s in info["symbols"]}
    rows = []
    for n in sorted(names):
        s = S.get(n)
        rec = {"symbol": n, "in_exchange_info": s is not None, "status": s["status"] if s else "ARCHIVE_ONLY",
               "contract_type": s.get("contractType") if s else None,
               "underlying_type": s.get("underlyingType") if s else None,
               "onboard_ms": s.get("onboardDate") if s else None,
               "delivery_ms": s.get("deliveryDate") if s else None}
        base = s.get("baseAsset") if s else plain_name(n)[:-4]
        if n in PERP_STABLE_FIAT_NAMES:
            rec.update(include=False, reason="stablecoin/fiat underlying")
        elif base in COMMODITY_BACKED_BASES:
            rec.update(include=False, reason=COMMODITY_REASON)
        elif n in PERP_INDEX_NAMES or (s and s.get("underlyingType") == "INDEX"):
            rec.update(include=False, reason="synthetic index (BTCDOM-type)")
        elif s and s.get("contractType") == "TRADIFI_PERPETUAL":
            rec.update(include=False, reason=f"TRADIFI_PERPETUAL ({s.get('underlyingType')}) - not a crypto underlying")
        elif s and s.get("contractType") != "PERPETUAL":
            rec.update(include=False, reason=f"contractType {s.get('contractType')}")
        else:
            rec.update(include=True, reason="crypto perpetual" if s else "crypto perpetual (archive-only, delisted)")
        rows.append(rec)
    return pd.DataFrame(rows).set_index("symbol")


def classify_spot(names: List[str]) -> pd.DataFrame:
    info = json.loads((RAW / SRC["spot"] / "exchangeInfo" / "latest.json").read_text())
    S = {s["symbol"]: s for s in info["symbols"]}
    rows = []
    bases = {(S[n]["baseAsset"] if n in S else n[:-4]) for n in names}
    for n in sorted(names):
        s = S.get(n)
        base = s["baseAsset"] if s else n[:-4]
        rec = {"symbol": n, "base": base, "in_exchange_info": s is not None,
               "status": s["status"] if s else "ARCHIVE_ONLY"}
        if base in SPOT_STABLE_BASES:
            rec.update(include=False, reason="stablecoin base (stablecoin-vs-stablecoin pair)")
        elif base in COMMODITY_BACKED_BASES:
            rec.update(include=False, reason=COMMODITY_REASON)
        elif base in SPOT_FIAT_BASES:
            rec.update(include=False, reason="fiat base")
        elif base in SPOT_WRAPPED_BASES:
            rec.update(include=False, reason="wrapped / staked wrapper token")
        elif spot_leveraged(base, bases):
            rec.update(include=False, reason="leveraged token (UP/DOWN/BULL/BEAR)")
        else:
            rec.update(include=True, reason="spot coin")
        rows.append(rec)
    return pd.DataFrame(rows).set_index("symbol")


def flag_tokenized_equities(cls: pd.DataFrame, first_rows: pd.Series) -> pd.DataFrame:
    """Mark Binance tokenised equities (<TICKER>B, listed since 2026-06) as excluded from the spot lane.
    A B-suffixed token listed in that wave that matches neither rule is REFUSED (manual classification
    needed) rather than silently treated as a coin."""
    info = json.loads((RAW / SRC["perp"] / "exchangeInfo" / "latest.json").read_text())
    trad = {s["baseAsset"] for s in info["symbols"] if s.get("contractType") == "TRADIFI_PERPETUAL"}
    cls = cls.copy()
    unknown = []
    for sym in cls.index[cls["include"]]:
        base = cls.at[sym, "base"]
        first = first_rows.get(sym)
        if not (base.endswith("B") and len(base) >= 3) or first is None or pd.isna(first) or first < TOKENIZED_WAVE_START:
            continue
        if base[:-1] in trad or base in SPOT_TOKENIZED_EXTRA:
            cls.at[sym, "include"] = False
            cls.at[sym, "reason"] = "tokenised equity / ETF (<TICKER>B) - not a crypto asset"
        else:
            unknown.append(sym)
    if unknown:
        raise RuntimeError(f"unclassified <TICKER>B spot tokens listed since 2026-06 (coin or tokenised equity?): {unknown}")
    return cls


# ------------------------------------------------------------------------------------------ daily frames
def daily_frames(market: str, names: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """close, quote volume, trade count — wide, row-labelled by candle END (open + 1 day), UTC.
    Zero-trade candles are kept here (count == 0); callers decide what a print is."""
    closes, qvols, counts, notes = {}, {}, {}, {}
    for n in names:
        df = read_klines(market, n, "1d")
        if df.attrs.get("off_grid_dropped"):
            notes[n] = f"{df.attrs['off_grid_dropped']} daily candles not opening at 00:00 UTC were dropped"
        if df.empty:
            notes[n] = "no daily candles on disk"
            continue
        idx = pd.to_datetime(df.index + DAY_MS, unit="ms", utc=True)
        closes[n] = pd.Series(df["close"].to_numpy(), index=idx)
        qvols[n] = pd.Series(df["quote_volume"].to_numpy(), index=idx)
        counts[n] = pd.Series(df["count"].to_numpy(), index=idx)
    close = pd.DataFrame(closes).sort_index()
    full = pd.date_range(close.index[0], close.index[-1], freq="D", tz="UTC")
    close = close.reindex(full)
    qvol = pd.DataFrame(qvols).reindex(full)
    count = pd.DataFrame(counts).reindex(full)
    cols = sorted(close.columns)
    return close[cols], qvol[cols], count[cols], notes


def live_frames(close: pd.DataFrame, qvol: pd.DataFrame, count: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Prices / volumes with zero-trade (phantom) candles removed."""
    live = count > 0
    return close.where(live), qvol.where(live)


# ------------------------------------------------------------------------------------------- exec prints
def exec_prints(market: str, sym: str) -> pd.DataFrame:
    """From the 1h candles of one symbol: DataFrame indexed by day D (UTC midnight) with
       exec (close of the candle opened D 00:00), exec_n (its trade count),
       alt  (close of the candle opened D 01:00), alt_n,
       pre  (close of the candle opened D-1 23:00 == should equal the daily close on row D), pre_n.
    Also returns attrs['last_traded_close_ms'] = close time of the last 1h candle with >= 1 trade."""
    df = read_klines(market, sym, "1h")
    if df.empty:
        out = pd.DataFrame(columns=["exec", "exec_n", "alt", "alt_n", "pre", "pre_n"])
        out.attrs["last_traded_close_ms"] = None
        out.attrs["n_hourly"] = 0
        out.attrs["n_hourly_rest"] = 0
        out.attrs["traded_open_ms"] = np.empty(0, dtype="int64")
        out.attrs["off_grid_dropped"] = 0
        return out
    ms = df.index.to_numpy()
    hour = (ms % DAY_MS) // HOUR_MS
    day = ms - (ms % DAY_MS)
    traded = df["count"].to_numpy() > 0
    last_traded = int(ms[traded].max() + HOUR_MS) if traded.any() else None

    def pick(h: int, shift_days: int = 0) -> Tuple[pd.Series, pd.Series]:
        sel = hour == h
        idx = pd.to_datetime(day[sel] + shift_days * DAY_MS, unit="ms", utc=True)
        return (pd.Series(df["close"].to_numpy()[sel], index=idx),
                pd.Series(df["count"].to_numpy()[sel], index=idx))

    e, en = pick(0)
    a, an = pick(1)
    p, pn = pick(23, shift_days=1)
    out = pd.DataFrame({"exec": e, "exec_n": en, "alt": a, "alt_n": an, "pre": p, "pre_n": pn}).sort_index()
    out.attrs["last_traded_close_ms"] = last_traded
    out.attrs["n_hourly"] = int(len(df))
    out.attrs["n_hourly_rest"] = int((df["src"] == 0).sum())
    out.attrs["traded_open_ms"] = ms[traded]            # open times of every 1h candle with >= 1 trade
    out.attrs["off_grid_dropped"] = int(df.attrs.get("off_grid_dropped", 0))
    return out


# ---------------------------------------------------------------------------------------------- funding
def funding_events(sym: str) -> pd.DataFrame:
    """All funding events of one perp: index = funding time in ms, column rate; attrs carry counts."""
    src = SRC["perp"]
    t: List[float] = []
    r: List[float] = []
    n_arch = n_rest = 0
    # an old contract renamed "...SETTLED" keeps its funding history under the plain ticker
    names = [sym] + ([plain_name(sym)] if is_settled_name(sym) else [])
    for d in [RAW / src / "archive_funding" / n for n in names]:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.zip")):
            lo, hi = archive_file_bounds(p.name)
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    b = z.read(n)
                    df = pd.read_csv(io.BytesIO(b), header=0 if b[:1].isalpha() else None,
                                     names=None if b[:1].isalpha() else ["calc_time", "funding_interval_hours", "last_funding_rate"])
                    ct = df["calc_time"].astype("float64")
                    if len(ct) and (ct.min() < lo - 60_000 or ct.max() >= hi + 60_000):
                        raise ValueError(f"{p.name}: a funding time lies outside the month named by the file")
                    t += ct.tolist()
                    r += df["last_funding_rate"].astype("float64").tolist()
                    n_arch += len(df)
    for d in [RAW / src / "rest_funding" / n for n in names]:
        if not d.exists():
            continue
        for p in sorted(d.glob("funding_*.json")):
            for rec in json.loads(p.read_bytes()):
                t.append(float(rec["fundingTime"]))
                r.append(float(rec["fundingRate"]))
                n_rest += 1
    out = pd.DataFrame({"rate": r}, index=pd.Index(np.array(t, dtype="int64"), name="ms"))
    out = out.sort_index(kind="stable")
    minute = (out.index.to_numpy() + 30_000) // 60_000        # archive first (appended first), REST only fills
    out = out[~pd.Index(minute).duplicated(keep="first")]
    out.attrs["n_archive"] = n_arch
    out.attrs["n_rest"] = n_rest
    return out


def funding_to_rows(ev: pd.DataFrame, rows: pd.DatetimeIndex, *, cut_after_ms: Optional[int],
                    cut_before_ms: Optional[int] = None) -> Tuple[pd.Series, pd.Series]:
    """Sum of funding rates per EXEC interval. Row D collects events with time in (D-1 01:00, D 01:00].
    Events after `cut_after_ms` (the end of the last traded hour) or before `cut_before_ms` (the first
    traded hour) are phantom and dropped.
    Returns (sum_rate, n_events), both indexed by `rows` (0 where no event)."""
    ms = ev.index.to_numpy()
    rate = ev["rate"].to_numpy()
    if cut_after_ms is not None:
        keep = ms <= cut_after_ms
        ms, rate = ms[keep], rate[keep]
    if cut_before_ms is not None:
        keep = ms >= cut_before_ms
        ms, rate = ms[keep], rate[keep]
    # label = the first row D with D 01:00 >= event time  <=>  D = ceil((t - 1h) / 1d) days
    lab = -((-(ms - HOUR_MS)) // DAY_MS) * DAY_MS
    s = pd.Series(rate, index=pd.to_datetime(lab, unit="ms", utc=True))
    g = s.groupby(level=0)
    tot = g.sum().reindex(rows).fillna(0.0)
    cnt = g.size().reindex(rows).fillna(0).astype("int64")
    return tot, cnt


def write_plan(market: str, plan: dict) -> Path:
    p = RAW / SRC[market] / "_ever_in_mask.json"
    atomic_write_json(p, {"written_utc": utc_now(), **plan})
    return p
