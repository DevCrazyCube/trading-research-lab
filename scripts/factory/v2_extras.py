#!/usr/bin/env python3
"""FACTORY v2 extras (engineer-owned) — PREREGISTRATION_v2 §6: the realism pass and the leverage ladder.

    cd /home/anont/meme
    research/factory/.venv/bin/python -m scripts.factory.v2_extras realism [--offline]
    research/factory/.venv/bin/python -m scripts.factory.v2_extras ladder  [--reps 5000]
    ... realism|ladder --synthetic --out <scratch dir>

`--synthetic --out` behaves exactly as in v2.py (it IS `v2.Ctx`): synthetic panels, scratch output, no pin
check — and here also NO NETWORK and fabricated venue metadata, flagged synthetic in every output.
Both stages only read what `v2.py tier1` wrote; they never re-score a primary and never place an order:
    <run>/tier1_w/<primary id>.parquet     the book's target frame (columns = instruments it ever holds)
    <run>/tier1_net/<primary id>.parquet   its net return streams; column `base` is the IDEAL account
                                           (VenueSpec.ideal() + the lane's base proportional cost)
They write
    <run>/realism_results.json             one record per book x venue x size x contribution + the venue-field
                                           provenance, the instrument mapping and every dropped instrument
    <run>/realism_paths/<book>__<venue>.parquet    per print: every account's equity (multiple of its starting
                                           equity) and net return, beside the ideal's
    <rep>/REALISM.md                       one section APPENDED per run
    <run>/ladder_results.json, <rep>/LEVERAGE_LADDER.md
A book without Tier-1 output, a venue without metadata, a simulation that refuses: each is a visible
REFUSED record with its reason, and the rest still runs.

STAGE realism — the five executable books at EUR 1,000 / 5,000 / 10,000, with and without EUR 100 a month
  P.MACRO.LO_TREND @ trading212_invest, P.CRYPTO.TREND and P.CRYPTO.ALL @ kraken_derivatives_eea,
  P.CRYPTO.LO_TREND @ bitvavo, P.FX.G10.ALL @ pepperstone_eu_ctrader.
  * Timing, rebalance mask and no-trade band are the runner's (`v2.eng_kwargs`; long-only books trade on
    `portfolio.rebalance_rows(index, freq, offset=delay)` only; long/short books use the 10 % band).
  * THE ACCOUNT OPENS ON THE FIRST PRINT OF THE LANE'S FULL WINDOW, flat, with the stated cash; warm-up rows
    are not simulated (an account opened on panel row 0 would collect up to twelve monthly contributions
    before the scored window starts and would no longer be a EUR 1,000 account). The reference is the
    Tier-1 base stream on the same prints. Returns and tracking error are measured, for the account and
    for the ideal alike, from the first print on which the opening trade earns (row delay + 1): until
    then a new account is flat while the ideal book is already invested. Final equity and the cost
    totals cover the account's whole life. With the ideal venue this wiring reproduces the Tier-1 base
    stream to 1e-12 once every instrument has traded once (tests/test_v2_extras.py asserts it).
  * Currency: the panels are in USD. EUR amounts (sizes, contributions, venue minimums) are converted at
    the ECB reference rate recorded in venues.json and every result is reported as a multiple of starting
    equity. The EUR/USD exposure of a EUR account is NOT modelled (realism.py, "WHAT THE NUMBERS ARE IN").
  * The account is the EXCESS-return account of realism.py. No cash interest is credited: the venues' rates
    are unknown in venues.json (`report_total=False`).
  * Venue fields come from venues.json through `VenueSpec.from_json`; every gap is filled by an explicit
    override that the output labels VERIFIED (read from a saved, named source field: the venue's public
    instrument payload under landscape/evidence/venue_instruments/, or a venues.json field quoted
    verbatim) or ASSUMED (with the reason). A field that is still unknown refuses that simulation.
    Where the prereg's base cost exceeds the venue's commission, the difference is the ASSUMED half-spread;
    where venues.json carries a measured or published half-spread for the instrument, that is used.
  * Kraken and Bitvavo: the book is restricted to the instruments the venue lists. A Binance symbol is
    mapped only when (a) its name parses as [1000|1000000|1M]<BASE>USDT with no re-use suffix, (b) the
    venue lists exactly one eligible instrument with that base, and (c) the venue's own price agrees with
    the panel's latest Binance price per unit within a factor of 2 — which checks the unit multiplier and
    the asset identity with numbers instead of ticker spelling (it is what separates Binance's LUNA from
    Bitvavo's). Everything else is DROPPED and listed; a dropped instrument's target is simply not held
    (nothing is re-distributed). Stated limit: today's listing and lot sizes are applied to the whole
    history, including prints before the venue listed the instrument.
  * Metadata that cannot be had (endpoint unreachable, evidence missing or altered) -> "REFUSED: instrument
    metadata unavailable" for that venue; the other venues still run. Nothing is guessed.

STAGE ladder — "leverage x200"
  * Per book: the base-cost net stream inside the FULL window, scaled by L (costs scale with it), 5,000
    stationary-bootstrap ONE-YEAR paths (`stats.stationary_bootstrap_indices`, mean block
    `stats.default_block_length(n)`, seeded; the same paths for every L), compounded with ABSORPTION:
    RUIN when a single print loses >= 100 % (1 + L*r <= 0) or wealth falls to <= 10 % of the start.
    Daily prints understate intraday liquidation, so P(ruin) is a LOWER BOUND.
  * Second table: a 200x BTC position on the Binance USD-M BTCUSDT hourly candles already on disk.

EVIDENCE (landscape/evidence/venue_instruments/, each file beside a .meta.json with URL, UTC fetch time, sha256)
    kraken_futures_instruments.json   GET https://futures.kraken.com/derivatives/api/v3/instruments
    bitvavo_markets.json              GET https://api.bitvavo.com/v2/markets
    kraken_futures_tickers.landscape_copy.json   NOT fetched here: a copy of the tickers snapshot the landscape
                                      task saved; used only to corroborate the Kraken mapping by price
The two GETs are the only network calls this module can make, each at most once (a file on disk is never
fetched again; `--offline` forbids even that). With the evidence on disk the stages need no network.
Nothing here invents a number.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import io
import json
import math
import pathlib
import re
import sys
import time
import zipfile
from dataclasses import dataclass, field, replace
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.factory import portfolio, realism, stats, v2  # noqa: E402
from scripts.factory.engine import Refused as EngineRefused  # noqa: E402
from scripts.factory.panel import PanelBundle  # noqa: E402
from scripts.factory.realism import COST_FIELDS, VenueSpec  # noqa: E402
from scripts.factory.strategies import registry  # noqa: E402

Refused = v2.Refused
REFUSALS = (v2.Refused, EngineRefused)

# ==================================================================================================
# Configuration — a transcription of PREREGISTRATION_v2 §6. Nothing here is tuned.
# ==================================================================================================
BOOKS: Tuple[Tuple[str, str], ...] = (
    ("P.MACRO.LO_TREND", "trading212_invest"),
    ("P.FX.G10.ALL", "pepperstone_eu_ctrader"),
    ("P.CRYPTO.TREND", "kraken_derivatives_eea"),
    ("P.CRYPTO.ALL", "kraken_derivatives_eea"),
    ("P.CRYPTO.LO_TREND", "bitvavo"),
)
EUR_SIZES = (1000.0, 5000.0, 10000.0)
CONTRIBUTIONS_EUR = (0.0, 100.0)

LADDER_L = (0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 50.0, 200.0)
LADDER_REPS = 5000
RUIN_FLOOR = 0.10                       # wealth <= 10 % of the start = ruin
GRID_MAX_L = 200.0
LIQ_LEVERAGE = 200.0
LIQ_DISTANCES = (0.0025, 0.005)         # adverse move that liquidates: 0.25 % (maintenance-style) and 0.5 % (= 1/200)
LIQ_HORIZONS_H = (1, 4, 24)
LIQ_FEES_BP = (5.0, 2.0)
LIQ_START = "2020-01-01"
HOUR_MS = 3_600_000

EVIDENCE_DIR = v2.FACT / "landscape" / "evidence" / "venue_instruments"
ENDPOINTS = {
    "kraken_instruments": {"url": "https://futures.kraken.com/derivatives/api/v3/instruments",
                           "file": "kraken_futures_instruments.json"},
    "bitvavo_markets": {"url": "https://api.bitvavo.com/v2/markets", "file": "bitvavo_markets.json"},
}
# Price evidence for the Kraken mapping. The instruments endpoint carries no price, and a third GET is not
# allowed, so the tickers snapshot the landscape task saved on 2026-11-10 (the file venues.json cites for its
# measured half-spreads) is copied next to the instrument payloads and used ONLY to corroborate the mapping.
KRAKEN_TICKERS_URL = "https://futures.kraken.com/derivatives/api/v3/tickers"
KRAKEN_TICKERS_FILE = "kraken_futures_tickers.landscape_copy.json"
LANDSCAPE_KRAKEN_TICKERS = v2.FACT / "landscape" / "evidence" / "platforms_R1" / "raw" / "kf_tickers.json"
MIN_REQUEST_GAP_S = 0.6                 # <= 2 requests per second, with margin
_LAST_REQUEST = [0.0]

DROP_KINDS = {
    "name": "not a plain live Binance symbol (earlier segment, re-used ticker, or a name that does not parse)",
    "not_listed": "the venue lists no instrument with that base",
    "not_eligible": "listed at the venue but not eligible",
    "no_binance_price": "no recent Binance price (not live at the end of the panel), so the mapping cannot be corroborated",
    "no_venue_price": "no venue price evidence, so the mapping cannot be corroborated",
    "price_mismatch": "the venue's price disagrees with Binance's — not the same asset or unit with certainty",
    "no_pair": "no cTrader pair for this currency",
    "no_price": "no panel price to size the lot",
}
PRICE_TOLERANCE = 2.0                   # venue price x multiplier / Binance price must lie in [1/2, 2]
STALE_ROWS = 3                          # the Binance price must exist within the panel's last 3 prints
KRAKEN_NON_CRYPTO = ("xStocks", "Equities", "Commodities", "Forex", "Indices", "Pre-IPO", "Stablecoin")   # payload `category`
KRAKEN_CODE_TO_BASE = {"XBT": "BTC"}    # Kraken's symbol code for bitcoin; its payload's own `base` field says BTC
BINANCE_MULTIPLIERS = {"1000000": 1e6, "1000": 1e3, "1M": 1e6}
_BINANCE_NAME = re.compile(r"^(?P<mult>1000000|1000|1M)?(?P<base>[A-Z0-9]+?)USDT$")
_KRAKEN_PERP = re.compile(r"^PF_([A-Z0-9]+)USD$")

# cTrader FX: which side of the pair the panel instrument is. "base": the pair is <CCY>USD and a 0.01 lot is
# 1,000 units of the panel instrument; "quote": the pair is USD<CCY> and a 0.01 lot is 1,000 US dollars.
FX_PAIRS = {"EUR": ("EURUSD", "base"), "GBP": ("GBPUSD", "base"), "AUD": ("AUDUSD", "base"),
            "NZD": ("NZDUSD", "base"), "JPY": ("USDJPY", "quote"), "CHF": ("USDCHF", "quote"),
            "CAD": ("USDCAD", "quote"), "SEK": ("USDSEK", "quote"), "NOK": ("USDNOK", "quote")}
# ESMA decision (EU) 2018/796: a "major" pair is any two of these six currencies (30:1); every other pair 20:1.
ESMA_MAJOR_CURRENCIES = ("USD", "EUR", "JPY", "GBP", "CAD", "CHF")
FX_LOT_BASE_UNITS = 1000.0              # 0.01 lot
T212_MIN_ORDER_EUR = 1.0                # ASSUMED, not verified — see build_trading212

VERIFIED, ASSUMED, FROM_FILE, UNKNOWN = "VERIFIED", "ASSUMED", "venues.json", "UNKNOWN"
CURRENCY_FIELDS = ("min_fee", "min_notional", "cash_interest_threshold")      # VenueSpec fields that are currency amounts


def utc_now() -> str:
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_VENUES_DOC: Dict[str, dict] = {}


def venues_doc() -> dict:
    if "doc" not in _VENUES_DOC:
        _VENUES_DOC["doc"] = json.loads(v2.VENUES.read_text())
    return _VENUES_DOC["doc"]


def venue_entry(venue_id: str) -> dict:
    for v in venues_doc()["venues"]:
        if v.get("venue_id") == venue_id:
            return v
    raise Refused(f"venue {venue_id!r} is not in {v2.VENUES}")


def reference_eurusd() -> Tuple[float, dict]:
    fx = venues_doc()["reference"]["fx_reference"]
    rate = fx.get("EURUSD")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        raise Refused("venues.json reference.fx_reference.EURUSD is not a positive number")
    return float(rate), {"EURUSD": float(rate), "source": fx.get("source"), "url": fx.get("url")}


# ==================================================================================================
# Evidence: the two public instrument endpoints, fetched once and saved raw
# ==================================================================================================
def _meta_path(path: pathlib.Path) -> pathlib.Path:
    return path.with_name(path.stem + ".meta.json")


def _http_get(url: str, timeout: float = 30.0) -> Tuple[int, bytes, dict]:
    """ONE plain scripted GET: the requests library's own User-Agent, no cookies, no login, no retry."""
    import requests

    wait = MIN_REQUEST_GAP_S - (time.monotonic() - _LAST_REQUEST[0])
    if wait > 0:
        time.sleep(wait)
    agent = requests.utils.default_user_agent()
    try:
        r = requests.get(url, headers={"User-Agent": agent, "Accept": "application/json"}, timeout=timeout)
    finally:
        _LAST_REQUEST[0] = time.monotonic()
    return r.status_code, r.content, {"user_agent": agent, "content_type": r.headers.get("Content-Type")}


def _payload_problem(key: str, payload) -> Optional[str]:
    if key == "kraken_instruments":
        ok = isinstance(payload, dict) and payload.get("result") == "success" and \
            isinstance(payload.get("instruments"), list) and len(payload["instruments"]) > 0
        return None if ok else "not a Kraken instruments payload (result != success or no 'instruments' list)"
    if key == "bitvavo_markets":
        ok = isinstance(payload, list) and len(payload) > 0 and all(isinstance(x, dict) and "market" in x for x in payload)
        return None if ok else "not a Bitvavo markets payload (expected a non-empty list of markets)"
    if key == "kraken_tickers":
        ok = isinstance(payload, dict) and isinstance(payload.get("tickers"), list) and len(payload["tickers"]) > 0
        return None if ok else "not a Kraken tickers payload (no 'tickers' list)"
    return f"unknown evidence key {key!r}"


def _read_saved(path: pathlib.Path, key: str) -> dict:
    meta_p = _meta_path(path)
    if not meta_p.exists():
        return {"payload": None, "meta": {"path": str(path)}, "error": f"{path.name} has no {meta_p.name} (URL and fetch time unknown)"}
    raw = path.read_bytes()
    meta = json.loads(meta_p.read_text())
    meta["path"] = str(path)
    if meta.get("sha256") != sha256_bytes(raw):
        return {"payload": None, "meta": meta, "error": f"{path.name} does not match the sha256 recorded when it was saved"}
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        return {"payload": None, "meta": meta, "error": f"{path.name} is not JSON: {exc}"}
    problem = _payload_problem(key, payload)
    return {"payload": None if problem else payload, "meta": meta, "error": problem}


def load_evidence(key: str, *, allow_network: bool, directory: Optional[pathlib.Path] = None) -> dict:
    """{"payload", "meta", "error"} for one public instrument endpoint.

    The raw response lives in `directory` (default landscape/evidence/venue_instruments/) beside a
    `.meta.json` with its URL, UTC fetch time, HTTP status, size and sha256. It is fetched AT MOST ONCE:
    when the file is on disk it is used as it is; otherwise one GET is made (if `allow_network`) and the
    response is saved only if it is HTTP 200 and has the documented shape. A failure saves nothing and
    returns an `error` — the caller refuses the venue; it never guesses a lot size."""
    spec = ENDPOINTS[key]
    d = pathlib.Path(directory) if directory is not None else EVIDENCE_DIR
    path = d / spec["file"]
    if path.exists():
        return _read_saved(path, key)
    if not allow_network:
        return {"payload": None, "meta": {"url": spec["url"], "path": str(path)}, "error": "not on disk and the network is not allowed"}
    try:
        status, raw, info = _http_get(spec["url"])
    except Exception as exc:                                   # unreachable endpoint: a visible refusal, not a guess
        return {"payload": None, "meta": {"url": spec["url"]}, "error": f"GET failed: {type(exc).__name__}: {exc}"}
    fetched = utc_now()
    if status != 200:
        return {"payload": None, "meta": {"url": spec["url"], "http_status": status, "fetched_utc": fetched},
                "error": f"HTTP {status}"}
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        return {"payload": None, "meta": {"url": spec["url"], "http_status": status}, "error": f"response is not JSON: {exc}"}
    problem = _payload_problem(key, payload)
    if problem:
        return {"payload": None, "meta": {"url": spec["url"], "http_status": status}, "error": problem}
    d.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    meta = {"url": spec["url"], "method": "GET", "fetched_utc": fetched, "http_status": status, "bytes": len(raw),
            "sha256": sha256_bytes(raw), "saved_as": spec["file"], "fetched_by": "scripts/factory/v2_extras.py", **info,
            "note": "raw response body, byte for byte; public key-less endpoint; one request"}
    _meta_path(path).write_text(json.dumps(meta, indent=1) + "\n")
    meta = dict(meta, path=str(path))
    return {"payload": payload, "meta": meta, "error": None}


def kraken_tickers_evidence(directory: Optional[pathlib.Path] = None) -> dict:
    """The Kraken tickers snapshot used to corroborate the mapping by price. NO network: it is the file the
    landscape task saved (venues.json cites it), copied once next to the instrument payloads."""
    d = pathlib.Path(directory) if directory is not None else EVIDENCE_DIR
    path = d / KRAKEN_TICKERS_FILE
    if not path.exists():
        if not LANDSCAPE_KRAKEN_TICKERS.exists():
            return {"payload": None, "meta": {"path": str(path)},
                    "error": f"no Kraken tickers snapshot on disk ({path.name}, {LANDSCAPE_KRAKEN_TICKERS})"}
        raw = LANDSCAPE_KRAKEN_TICKERS.read_bytes()
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            return {"payload": None, "meta": {"path": str(LANDSCAPE_KRAKEN_TICKERS)}, "error": f"not JSON: {exc}"}
        problem = _payload_problem("kraken_tickers", payload)
        if problem:
            return {"payload": None, "meta": {"path": str(LANDSCAPE_KRAKEN_TICKERS)}, "error": problem}
        d.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        meta = {"url": KRAKEN_TICKERS_URL, "fetched_utc": payload.get("serverTime"),
                "fetched_utc_basis": "the payload's own serverTime", "bytes": len(raw), "sha256": sha256_bytes(raw),
                "saved_as": KRAKEN_TICKERS_FILE, "fetched_by": "the landscape task (platforms_R1), NOT by v2_extras",
                "copied_from": str(LANDSCAPE_KRAKEN_TICKERS), "copied_utc": utc_now(),
                "note": "used only to corroborate the Binance -> Kraken instrument mapping by price"}
        _meta_path(path).write_text(json.dumps(meta, indent=1) + "\n")
    return _read_saved(path, "kraken_tickers")


def real_evidence(allow_network: bool = True) -> Dict[str, dict]:
    ev = {k: load_evidence(k, allow_network=allow_network) for k in ENDPOINTS}
    ev["kraken_tickers"] = kraken_tickers_evidence()
    return ev


def _synthetic_meta(what: str) -> dict:
    return {"synthetic": True, "url": None, "fetched_utc": None, "note": f"FABRICATED {what} for the smoke test — not venue data"}


def synthetic_evidence(ctx: "v2.Ctx", eurusd: float) -> Dict[str, dict]:
    """Fabricated instrument payloads in the venues' real shapes, built from the SYNTHETIC panels so that
    every branch runs with no network: listed and mappable, not listed, not tradeable, price mismatch."""
    def last(panel: PanelBundle) -> pd.Series:
        return panel.prices.ffill().iloc[-1]

    perp, spot = ctx.panel("CRYPTO-PERP"), ctx.panel("CRYPTO-SPOT")
    instruments, tickers = [], []
    for k, (col, p) in enumerate(last(perp).items()):
        base = str(col)[:-4]
        if k % 10 == 7:
            continue                                              # the venue does not list it
        instruments.append({"symbol": f"PF_{base}USD", "type": "flexible_futures", "base": base, "quote": "USD",
                            "contractSize": 1, "contractValueTradePrecision": int(np.clip(round(math.log10(p)), -6, 8)),
                            "tradeable": k % 10 != 9, "suspended": False, "postOnly": False, "isExpired": False,
                            "tradfi": False, "platformsPermitted": ["europa"], "countriesBanned": [],
                            "category": "SYNTHETIC"})
        tickers.append({"symbol": f"PF_{base}USD", "markPrice": float(p) * (50.0 if k % 10 == 8 else 1.01)})
    markets = []
    for k, (col, p) in enumerate(last(spot).items()):
        base = str(col)[:-4]
        if k % 8 == 6:
            continue
        p_eur = float(p) / eurusd * (0.02 if k % 8 == 7 else 0.99)
        markets.append({"market": f"{base}-EUR", "status": "halted" if k == 3 else "trading", "base": base, "quote": "EUR",
                        "quantityDecimals": int(np.clip(2 + round(math.log10(p_eur)), 0, 8)),
                        "minOrderInQuoteAsset": "5.00", "minOrderInBaseAsset": repr(5.0 / p_eur)})
    return {"kraken_instruments": {"payload": {"result": "success", "instruments": instruments},
                                   "meta": _synthetic_meta("Kraken instruments payload"), "error": None},
            "kraken_tickers": {"payload": {"result": "success", "tickers": tickers},
                               "meta": _synthetic_meta("Kraken tickers payload"), "error": None},
            "bitvavo_markets": {"payload": markets, "meta": _synthetic_meta("Bitvavo markets payload"), "error": None}}


# ==================================================================================================
# Instrument mapping: Binance panel columns -> venue instruments
# ==================================================================================================
def parse_binance_symbol(name: str) -> Tuple[Optional[str], float, str]:
    """(base asset, units of that asset in ONE panel unit, why-not) for a panel column of the crypto lanes.

    BTCUSDT -> ("BTC", 1); 1000PEPEUSDT -> ("PEPE", 1000); 1000000MOGUSDT / 1MBABYDOGEUSDT -> 1e6.
    None when the name is not a plain live Binance symbol: an earlier segment of a split symbol
    (`FTTUSDT@20221116`), an old contract whose ticker was re-used (`BNXUSDTSETTLED`, `ICPUSDT_SETTLED`),
    or anything else that does not parse (non-ASCII bases)."""
    s = str(name)
    if "@" in s:
        return None, 1.0, "an earlier segment of a split Binance symbol (the ticker was re-listed after a gap)"
    if "SETTLED" in s:
        return None, 1.0, "an old Binance contract whose ticker was re-used (SETTLED name)"
    m = _BINANCE_NAME.match(s)
    if not m:
        return None, 1.0, "the name does not parse as [1000|1000000|1M]<BASE>USDT"
    return m.group("base"), BINANCE_MULTIPLIERS.get(m.group("mult") or "", 1.0), ""


def kraken_base(symbol: str, base_field: Optional[str] = None) -> Optional[str]:
    """Base asset of a Kraken Futures perpetual `PF_<CODE>USD` (XBT is bitcoin). When the payload's own
    `base` field is given it must agree, otherwise None (e.g. tokenised equities: PF_SPYXUSD has base 'SPYx')."""
    m = _KRAKEN_PERP.match(str(symbol or ""))
    if not m:
        return None
    base = KRAKEN_CODE_TO_BASE.get(m.group(1), m.group(1))
    if base_field is not None and str(base_field) != base:
        return None
    return base


def _kraken_ineligible(it: dict) -> Optional[str]:
    if it.get("type") != "flexible_futures":
        return f"type {it.get('type')!r}"
    if it.get("quote") != "USD":
        return f"quote {it.get('quote')!r}"
    if it.get("tradeable") is not True:
        return "not tradeable"
    for flag, why in (("suspended", "suspended"), ("isExpired", "expired"), ("postOnly", "post-only (no taker orders)"),
                      ("tradfi", "a TradFi perpetual, not a crypto asset")):
        if it.get(flag) is not False:
            return why if it.get(flag) is True else f"field {flag!r} missing"
    if it.get("category") in KRAKEN_NON_CRYPTO:
        return f"not a crypto asset (category {it.get('category')!r})"
    if "europa" not in (it.get("platformsPermitted") or []):
        return "not permitted on the 'europa' (EEA) platform"
    if "NL" in (it.get("countriesBanned") or []):
        return "banned for NL"
    return None


def kraken_listing(instruments: dict, tickers: Optional[dict]) -> Tuple[Dict[str, dict], Dict[str, str]]:
    """({base: instrument facts}, {base: why it is not eligible}) for the EEA-tradeable crypto perpetuals.
    One contract is one unit of base (contractSize 1, required); lot_base = 10^(-contractValueTradePrecision)
    units of the base asset; `price` is the tickers snapshot's markPrice (None when it has none)."""
    prices = {t.get("symbol"): t.get("markPrice") for t in ((tickers or {}).get("tickers") or []) if isinstance(t, dict)}
    listing: Dict[str, dict] = {}
    ineligible: Dict[str, str] = {}
    for it in instruments["instruments"]:
        sym = str(it.get("symbol", ""))
        base = kraken_base(sym, it.get("base"))
        if base is None:
            continue                                                # dated futures (FF_...), tokenised equities
        why = _kraken_ineligible(it)
        prec, size = it.get("contractValueTradePrecision"), it.get("contractSize")
        if why is None and (isinstance(prec, bool) or not isinstance(prec, int)):
            why = f"contractValueTradePrecision is {prec!r}"
        if why is None and (isinstance(size, bool) or not isinstance(size, (int, float)) or size != 1):
            why = f"contractSize is {size!r} (only 1 = one unit of base per contract is understood)"
        if why is None and base in listing:
            why = f"two eligible instruments share the base ({listing[base]['symbol']}, {sym})"
            del listing[base]
        if why is not None:
            ineligible[base] = f"{sym}: {why}"
            continue
        px = prices.get(sym)
        listing[base] = {"symbol": sym, "base": base, "contract_size": float(size), "precision": int(prec),
                         "lot_base": 10.0 ** (-int(prec)),
                         "price": float(px) if isinstance(px, (int, float)) and not isinstance(px, bool) and px > 0 else None,
                         "category": it.get("category"), "opening_date": it.get("openingDate")}
    for base in ineligible:
        listing.pop(base, None)
    return listing, ineligible


def bitvavo_listing(markets: list, eurusd: float) -> Tuple[Dict[str, dict], Dict[str, str]]:
    """({base: market facts}, {base: why not}) for the <BASE>-EUR markets in status 'trading'.
    lot_base = 10^(-quantityDecimals); the minimum order is minOrderInQuoteAsset (EUR); `price` is the EUR
    price the payload itself implies, minOrderInQuoteAsset / minOrderInBaseAsset, converted at `eurusd`."""
    listing: Dict[str, dict] = {}
    ineligible: Dict[str, str] = {}
    for m in markets:
        if not isinstance(m, dict) or m.get("quote") != "EUR":
            continue
        base, market = str(m.get("base", "")), str(m.get("market", ""))
        if market != f"{base}-EUR":
            continue
        why = None if m.get("status") == "trading" else f"status {m.get('status')!r}"
        qd = m.get("quantityDecimals")
        try:
            min_q, min_b = float(m.get("minOrderInQuoteAsset")), float(m.get("minOrderInBaseAsset"))
        except (TypeError, ValueError):
            min_q = min_b = float("nan")
        if why is None and (isinstance(qd, bool) or not isinstance(qd, int) or qd < 0):
            why = f"quantityDecimals is {qd!r}"
        if why is None and not (math.isfinite(min_q) and math.isfinite(min_b) and min_q > 0 and min_b > 0):
            why = "minOrderInQuoteAsset / minOrderInBaseAsset missing or not positive"
        if why is not None:
            ineligible[base] = f"{market}: {why}"
            continue
        listing[base] = {"symbol": market, "base": base, "quantity_decimals": int(qd), "lot_base": 10.0 ** (-int(qd)),
                         "min_order_quote_eur": min_q, "min_order_base": min_b, "price": min_q / min_b * eurusd}
    return listing, ineligible


def latest_prices(panel: PanelBundle, cols: Sequence[str], rows: int = STALE_ROWS) -> pd.Series:
    """The panel's latest price per instrument, NaN when it has none within the last `rows` prints."""
    return panel.prices[list(cols)].iloc[-rows:].ffill().iloc[-1]


def map_instruments(columns: Sequence[str], last_price: Mapping[str, float], listing: Mapping[str, dict],
                    ineligible: Optional[Mapping[str, str]] = None,
                    tolerance: float = PRICE_TOLERANCE) -> Tuple[Dict[str, dict], List[dict]]:
    """Map Binance panel columns to venue instruments; DROP whatever cannot be mapped with certainty.

    Mapped iff the name parses (`parse_binance_symbol`), the venue lists exactly one eligible instrument
    with that base, a recent Binance price and a venue price both exist, and
        1/tolerance <= venue price * multiplier / Binance price <= tolerance
    (both in the panel currency, per ONE panel unit). Returns ({column: facts}, [{instrument, kind, reason}]),
    `kind` being a key of DROP_KINDS."""
    ineligible = ineligible or {}
    mapped: Dict[str, dict] = {}
    dropped: List[dict] = []
    for col in columns:
        base, mult, why = parse_binance_symbol(col)
        if base is None:
            dropped.append({"instrument": str(col), "kind": "name", "reason": why})
            continue
        if base not in listing:
            if base in ineligible:
                dropped.append({"instrument": str(col), "kind": "not_eligible", "reason": f"listed but not eligible — {ineligible[base]}"})
            else:
                dropped.append({"instrument": str(col), "kind": "not_listed", "reason": f"the venue lists no instrument with base {base}"})
            continue
        inst = listing[base]
        p_bin = last_price.get(col, float("nan"))
        p_bin = float(p_bin) if p_bin is not None else float("nan")
        if not (math.isfinite(p_bin) and p_bin > 0):
            dropped.append({"instrument": str(col), "kind": "no_binance_price",
                            "reason": f"no Binance price in the panel's last {STALE_ROWS} prints: the mapping to {inst['symbol']} "
                                      f"cannot be corroborated"})
            continue
        if inst.get("price") is None:
            dropped.append({"instrument": str(col), "kind": "no_venue_price",
                            "reason": f"no venue price evidence for {inst['symbol']}: the mapping cannot be corroborated"})
            continue
        venue_px = float(inst["price"]) * mult
        ratio = venue_px / p_bin
        if not (1.0 / tolerance <= ratio <= tolerance):
            dropped.append({"instrument": str(col), "kind": "price_mismatch",
                            "reason": f"price mismatch with {inst['symbol']}: venue {venue_px:.6g} vs Binance {p_bin:.6g} per panel "
                                      f"unit (ratio {ratio:.4g}) — not the same asset or unit with certainty"})
            continue
        mapped[str(col)] = {"instrument": str(col), "base": base, "multiplier": mult, "venue_symbol": inst["symbol"],
                            "binance_price": p_bin, "venue_price_per_panel_unit": venue_px, "price_ratio": ratio}
    return mapped, dropped


# ==================================================================================================
# VenueSpec builders — one per venue; every value carries its basis and source
# ==================================================================================================
@dataclass
class VenueBuild:
    venue_id: str
    specs: Dict[str, VenueSpec] = field(default_factory=dict)
    provenance: List[dict] = field(default_factory=list)       # field -> value -> basis -> source (grouped)
    instruments: List[dict] = field(default_factory=list)      # one row per simulated instrument
    dropped: List[dict] = field(default_factory=list)          # {"instrument", "kind", "reason"}
    notes: List[str] = field(default_factory=list)
    refused: Optional[str] = None


_SPEC_CACHE: Dict[tuple, VenueSpec] = {}


class _Draft:
    """One instrument's VenueSpec under construction, with a provenance row per field."""

    def __init__(self, venue_id: str, class_keys: Sequence[str], currency: str):
        key = (venue_id, tuple(class_keys), currency)
        if key not in _SPEC_CACHE:
            _SPEC_CACHE[key] = VenueSpec.from_json(v2.VENUES, venue_id, instrument_class=tuple(class_keys), currency=currency)
        self.spec = _SPEC_CACHE[key]
        self.venue_id = venue_id
        self.loaded_in = currency
        self.rows: Dict[str, dict] = {}
        entry = venue_entry(venue_id)
        for name in COST_FIELDS:
            note = self.spec.notes.get(name, {})
            if note.get("status") == "ok":
                raw = entry.get(note.get("json_key"))
                label = f"; file label: {raw['label']}" if isinstance(raw, dict) and isinstance(raw.get("label"), str) else ""
                self.rows[name] = {"value": getattr(self.spec, name), "basis": FROM_FILE,
                                   "source": f"{venue_id}.{note.get('json_key')} {note.get('why')}{label}"}

    def known(self, name: str) -> bool:
        return getattr(self.spec, name) is not None

    def set(self, name: str, value, basis: str, source: str) -> None:
        if basis not in (VERIFIED, ASSUMED):
            raise Refused(f"an override must be VERIFIED or ASSUMED; got {basis!r}")
        was = getattr(self.spec, name)
        self.spec = self.spec.with_overrides(**{name: value})
        if was is not None and was != value:
            source = f"{source} [venues.json had {was:g}]"
        self.rows[name] = {"value": value, "basis": basis, "source": source}

    def done(self, unused: Mapping[str, str]) -> VenueSpec:
        """The finished spec, in USD. An amount that venues.json quotes in another currency must have been
        converted by an explicit override (zero is zero in any currency); otherwise the spec is refused."""
        for name in COST_FIELDS:
            if name not in self.rows:
                why = self.spec.notes.get(name, {}).get("why", "not given")
                self.rows[name] = {"value": None, "basis": UNKNOWN,
                                   "source": f"{why} — not needed: {unused.get(name, 'this run does not depend on it')}"}
        if self.loaded_in != "USD":
            for name in CURRENCY_FIELDS:
                row = self.rows[name]
                if row["basis"] == FROM_FILE and row["value"] not in (None, 0.0):
                    raise Refused(f"{self.venue_id}.{name} = {row['value']!r} {self.loaded_in} was read from venues.json and not "
                                  f"converted to USD")
        return replace(self.spec, currency="USD")


def _group_provenance(venue_id: str, rows_by_instrument: Mapping[str, Mapping[str, dict]]) -> List[dict]:
    """Collapse per-instrument field rows into one row per (field, basis, source)."""
    out: List[dict] = []
    for name in COST_FIELDS:
        groups: Dict[tuple, List[tuple]] = {}
        for inst, rows in rows_by_instrument.items():
            r = rows[name]
            groups.setdefault((r["basis"], r["source"]), []).append((inst, r["value"]))
        for (basis, source), members in groups.items():
            vals = [v for _, v in members]
            nums = sorted({float(v) for v in vals if v is not None})
            value = None if not nums else (nums[0] if len(nums) == 1 else {"min": nums[0], "max": nums[-1], "distinct": len(nums)})
            names = [i for i, _ in members]
            out.append({"venue": venue_id, "field": name, "value": value, "basis": basis, "source": source,
                        "n_instruments": len(names), "instruments": names if len(names) <= 12 else names[:12] + ["..."]})
    return out


_NO_CASH = "no cash yield is credited (report_total=False): the venue's rate is unknown"
_UNUSED_LONG_ONLY = {"financing_short_bp_year": "the book is long-only", "cash_interest_bp_year": _NO_CASH,
                     "cash_interest_threshold": _NO_CASH}
_UNUSED_LS = {"cash_interest_bp_year": _NO_CASH, "cash_interest_threshold": _NO_CASH}


def _base_cost(key: Tuple[str, str], group: Optional[str] = None) -> Tuple[float, float]:
    """(cost bp per side, holding cost bp per year) of the lane's Tier-1 BASE scenario — prereg §3 via v2.COSTS."""
    c, h = v2.COSTS[key]["base"]
    return (float(c[group]), float(h[group])) if isinstance(c, dict) else (float(c), float(h))


def _residual(base_bp: float, fee_bp: Optional[float]) -> float:
    """The half-spread the prereg's base cost leaves once the venue's commission is taken out (never negative)."""
    return max(round(base_bp - (fee_bp or 0.0), 9), 0.0)


def build_trading212(cols: Sequence[str], eurusd: float) -> VenueBuild:
    """UCITS ETFs at Trading 212 Invest through its API: zero commission, fractional QUANTITY orders,
    long-only, unlevered. There is no key-less instrument endpoint, so nothing here is payload-verified."""
    vid = "trading212_invest"
    out = VenueBuild(vid)
    base_bp, _ = _base_cost(("MACRO", "t1_lo"))
    rows = {}
    for col in cols:
        d = _Draft(vid, ("ucits_etfs", "stocks_etfs", "invest"), "EUR")
        d.set("half_spread_bp", _residual(base_bp, d.spec.fee_bp), ASSUMED,
              f"prereg §3: MACRO long-only base cost {base_bp:g} bp per side with zero commission — the exchange "
              f"half-spread of UCITS ETFs is unmeasured (venues.json: null, the API has no market-data endpoint)")
        d.set("lot_step", 0.0, ASSUMED,
              "venues.json lot_step text: 'fractional quantities; API orders by QUANTITY only' — the per-instrument "
              "quantity precision sits behind an API key and was not read; treated as continuous")
        d.set("min_notional", T212_MIN_ORDER_EUR * eurusd, ASSUMED,
              f"venues.json min_order_notional: null (UNKNOWN). EUR {T212_MIN_ORDER_EUR:g} is the commonly reported minimum "
              f"order value for fractional orders, taken from general knowledge and NOT verified on 2026-11-10; the "
              f"per-instrument minTradeQuantity of the keyed instruments endpoint was not read. Converted at EURUSD {eurusd:g}")
        d.set("contract_notional", 1.0, ASSUMED, "by construction: one unit = one fund share at the panel price")
        out.specs[col] = d.done(_UNUSED_LONG_ONLY)
        rows[col] = d.rows
        out.instruments.append({"instrument": col, "venue_symbol": "UCITS equivalent (not identified)", "lot_step_units": 0.0,
                                "min_order_ccy": T212_MIN_ORDER_EUR * eurusd, "half_spread_bp": out.specs[col].half_spread_bp,
                                "leverage_cap": out.specs[col].leverage_cap})
    out.provenance = _group_provenance(vid, rows)
    out.notes = [
        "ASSUMED instrument availability: every US-listed ETF of the panel is taken to have a UCITS equivalent at Trading 212 "
        "(prereg §2: US ETFs proxy UCITS funds). The instrument list needs an API key and was not read.",
        "ASSUMED: EUR-denominated share classes, so the 15 bp FX fee of venues.json does not apply; a USD line would add 15 bp per side.",
        "Cash interest is not credited: the rate is unknown in venues.json.",
    ]
    return out


def build_kraken(cols: Sequence[str], panel: PanelBundle, evidence: Mapping[str, dict], eurusd: float) -> VenueBuild:
    """Kraken Derivatives (EEA) linear perpetuals: 5 bp taker, lot = contractSize * 10^(-contractValueTradePrecision)."""
    vid = "kraken_derivatives_eea"
    out = VenueBuild(vid)
    ins, tick = evidence.get("kraken_instruments") or {}, evidence.get("kraken_tickers") or {}
    if ins.get("payload") is None:
        out.refused = f"instrument metadata unavailable ({ENDPOINTS['kraken_instruments']['url']}: {ins.get('error')})"
        return out
    if tick.get("payload") is None:
        out.refused = f"instrument metadata unavailable (no price evidence to corroborate the mapping: {tick.get('error')})"
        return out
    listing, ineligible = kraken_listing(ins["payload"], tick["payload"])
    mapped, out.dropped = map_instruments(cols, latest_prices(panel, cols).to_dict(), listing, ineligible)
    lane_bp, _ = _base_cost(("CRYPTO-PERP", "t1"))
    cap = float(v2.LANES["CRYPTO-PERP"].max_gross)
    spread_keys = venue_entry(vid).get("typical_half_spread_bp") or {}
    rows = {}
    for col, m in mapped.items():
        inst = listing[m["base"]]
        sym = inst["symbol"]
        keys = ((sym,) if isinstance(spread_keys.get(sym), (int, float)) else ()) + ("all_perps_and_futures", "eea_retail")
        d = _Draft(vid, keys, "USD")
        d.set("min_fee", 0.0, ASSUMED,
              "venues.json min_fee_per_order: null; its min_order_notional.note reads 'no minimum fee' (the schedule is proportional)")
        if not d.known("half_spread_bp"):
            d.set("half_spread_bp", _residual(lane_bp, d.spec.fee_bp), ASSUMED,
                  f"prereg §3: CRYPTO-PERP base {lane_bp:g} bp per side less the taker fee — only BTC, ETH and SOL were measured")
        d.set("lot_step", inst["lot_base"] / m["multiplier"], VERIFIED,
              "Kraken instruments payload: 10^(-contractValueTradePrecision) contracts of contractSize 1 unit of base, divided "
              "by the units of base in one panel unit")
        d.set("min_notional", 0.0, ASSUMED,
              "the payload documents no minimum-order field; the smallest order is one increment of "
              "contractValueTradePrecision (venues.json: 'PF_XBTUSD 0.0001 BTC'), which lot_step already enforces")
        d.set("contract_notional", 1.0, VERIFIED,
              "Kraken instruments payload: contractSize = 1 (one contract = one unit of base); the panel price is per panel unit")
        for side in ("financing_long_bp_year", "financing_short_bp_year"):
            d.set(side, 0.0, ASSUMED,
                  "prereg §3: no holding cost on CRYPTO-PERP beyond the panel's funding leg — which is realised BINANCE "
                  "funding, not what a Kraken account pays (prereg §2, accepted limit)")
        d.set("leverage_cap", cap, ASSUMED,
              f"prereg §3 gross cap {cap:g}x: ESMA's statement of 24 Feb 2026 puts perpetual futures under the 2:1 crypto CFD "
              f"cap; Kraken's own EEA tier-I schedule is 10x")
        out.specs[col] = d.done(_UNUSED_LS)
        rows[col] = d.rows
        out.instruments.append({**m, "contract_value_trade_precision": inst["precision"], "contract_size": inst["contract_size"],
                                "lot_step_units": out.specs[col].lot_step, "min_order_ccy": 0.0,
                                "half_spread_bp": out.specs[col].half_spread_bp, "half_spread_basis": d.rows["half_spread_bp"]["basis"],
                                "leverage_cap": cap, "category": inst["category"], "opening_date": inst["opening_date"]})
    out.provenance = _group_provenance(vid, rows)
    out.notes = [
        "Eligible = PF_ perpetual, tradeable, not suspended / expired / post-only, not a TradFi perpetual and not in a "
        "non-crypto category (stocks, commodities, FX, indices, stablecoins and gold tokens), permitted on the 'europa' platform "
        "(read as the EEA platform — an inference recorded in venues.json), not banned for NL.",
        f"Mapping corroborated by price: Kraken markPrice from the tickers snapshot of "
        f"{tick['meta'].get('fetched_utc') or '(fabricated)'} ({tick['meta'].get('fetched_by') or 'synthetic'}) against the "
        f"panel's last Binance print ({panel.prices.index[-1]}), tolerance x{PRICE_TOLERANCE:g}.",
        "Today's listing and lot sizes are applied to the whole history; Kraken's past listings are not reconstructed.",
    ]
    opened = sorted(str(r["opening_date"]) for r in out.instruments if r.get("opening_date"))
    if opened:
        out.notes.append(f"Payload openingDate of the mapped perpetuals: {opened[0][:10]} … {opened[-1][:10]}. Each is simulated "
                         f"over the whole window all the same: before its opening date the contract did not exist at this venue.")
    if not out.specs:
        out.refused = "no instrument of the book could be mapped to a Kraken perpetual with certainty"
    return out


def build_bitvavo(cols: Sequence[str], panel: PanelBundle, evidence: Mapping[str, dict], eurusd: float) -> VenueBuild:
    """Bitvavo spot <BASE>-EUR: 25 bp taker, EUR 5 minimum order, 10^(-quantityDecimals) lot; long-only, funded."""
    vid = "bitvavo"
    out = VenueBuild(vid)
    mk = evidence.get("bitvavo_markets") or {}
    if mk.get("payload") is None:
        out.refused = f"instrument metadata unavailable ({ENDPOINTS['bitvavo_markets']['url']}: {mk.get('error')})"
        return out
    listing, ineligible = bitvavo_listing(mk["payload"], eurusd)
    mapped, out.dropped = map_instruments(cols, latest_prices(panel, cols).to_dict(), listing, ineligible)
    lane_bp, _ = _base_cost(("CRYPTO-SPOT", "t1"))
    spread_keys = venue_entry(vid).get("typical_half_spread_bp") or {}
    rows = {}
    for col, m in mapped.items():
        inst = listing[m["base"]]
        sym = inst["symbol"]
        keys = ((sym,) if isinstance(spread_keys.get(sym), (int, float)) else ()) + ("crypto_spot_eur_markets", "spot")
        d = _Draft(vid, keys, "EUR")
        d.set("min_fee", 0.0, ASSUMED,
              "venues.json min_fee_per_order: null; the published schedule is proportional and lists no per-order minimum")
        if not d.known("half_spread_bp"):
            d.set("half_spread_bp", _residual(lane_bp, d.spec.fee_bp), ASSUMED,
                  f"prereg §3: CRYPTO-SPOT base {lane_bp:g} bp per side less the taker fee — only BTC, ETH and SOL were measured")
        d.set("lot_step", inst["lot_base"] / m["multiplier"], VERIFIED,
              "Bitvavo markets payload: 10^(-quantityDecimals) units of base, divided by the units of base in one panel unit")
        d.set("min_notional", inst["min_order_quote_eur"] * eurusd, VERIFIED,
              f"Bitvavo markets payload: minOrderInQuoteAsset (EUR), converted at the ECB reference EURUSD {eurusd:g}")
        d.set("contract_notional", 1.0, ASSUMED, "by construction: spot, one unit = one panel unit at the panel price")
        out.specs[col] = d.done(_UNUSED_LONG_ONLY)
        rows[col] = d.rows
        out.instruments.append({**m, "quantity_decimals": inst["quantity_decimals"], "lot_step_units": out.specs[col].lot_step,
                                "min_order_ccy": out.specs[col].min_notional, "min_order_quote_eur": inst["min_order_quote_eur"],
                                "half_spread_bp": out.specs[col].half_spread_bp, "half_spread_basis": d.rows["half_spread_bp"]["basis"],
                                "leverage_cap": out.specs[col].leverage_cap})
    out.provenance = _group_provenance(vid, rows)
    out.notes = [
        "Eligible = <BASE>-EUR market in status 'trading'.",
        f"Mapping corroborated by price: the EUR price the payload itself implies (minOrderInQuoteAsset / minOrderInBaseAsset, "
        f"converted at EURUSD {eurusd:g}) against the panel's last Binance print ({panel.prices.index[-1]}), tolerance "
        f"x{PRICE_TOLERANCE:g}.",
        "The account trades EUR pairs; the simulation is in the panel's USD(T) prices and the EUR/USD move is not modelled.",
        "Today's listing and lot sizes are applied to the whole history. Cash interest is not credited (unknown).",
    ]
    if not out.specs:
        out.refused = "no instrument of the book could be mapped to a Bitvavo EUR market with certainty"
    return out


def build_pepperstone(cols: Sequence[str], panel: PanelBundle) -> VenueBuild:
    """Pepperstone EU Razor on cTrader: FX CFDs in 0.01-lot steps, commission + spread + swap mark-up."""
    vid = "pepperstone_eu_ctrader"
    out = VenueBuild(vid)
    spread_keys = venue_entry(vid).get("typical_half_spread_bp") or {}
    rows = {}
    for col in cols:
        if col not in FX_PAIRS:
            out.dropped.append({"instrument": str(col), "kind": "no_pair",
                                "reason": "no cTrader pair is defined for this currency (G10 only)"})
            continue
        pair, side = FX_PAIRS[col]
        group = v2._fx_group(col)
        base_bp, hold_bp = _base_cost(("FX", "t1"), group)
        major = col in ESMA_MAJOR_CURRENCIES
        skey = f"{pair}_razor"
        keys = ((skey,) if isinstance(spread_keys.get(skey), (int, float)) else ()) + \
            ("fx_cfd_razor_ctrader", "fx_cfd", "fx_major" if major else "fx_minor_gold_major_index")
        d = _Draft(vid, keys, "USD")
        if not d.known("half_spread_bp"):
            if group == "MAJ":
                d.set("half_spread_bp", _residual(base_bp, d.spec.fee_bp), ASSUMED,
                      f"prereg §3: FX-majors base {base_bp:g} bp per side less the commission — venues.json has no published "
                      f"average spread for this pair")
            else:
                d.set("half_spread_bp", base_bp, ASSUMED,
                      f"prereg §3: FX Scandinavia spreads ASSUMED, {base_bp:g} bp per side (charged on top of the commission)")
        last = panel.prices[col].dropna()
        if side == "base":
            d.set("lot_step", FX_LOT_BASE_UNITS, VERIFIED,
                  "venues.json pepperstone_eu_ctrader.lot_step, verbatim: '0.01 lot (1,000 base units) on FX' — the panel "
                  "instrument is the base currency of the pair")
        else:
            if last.empty:
                out.dropped.append({"instrument": str(col), "kind": "no_price",
                                    "reason": "no panel price to convert the 1,000-USD lot into units"})
                continue
            d.set("lot_step", FX_LOT_BASE_UNITS / float(last.iloc[-1]), ASSUMED,
                  "APPROXIMATION: the pair is USD-base, so a 0.01 lot is 1,000 US dollars (venues.json lot_step); converted to "
                  "units of the panel instrument at the panel's latest price and held fixed over the whole history")
        d.set("min_notional", 0.0, VERIFIED,
              "venues.json min_order_notional.fx_cfd: 1000 base-currency units = one 0.01 lot = one lot step, which lot_step "
              "already enforces; there is no separate currency minimum")
        d.set("contract_notional", 1.0, ASSUMED, "by construction: one unit = one unit of the currency at the panel's USD price")
        for name in ("financing_long_bp_year", "financing_short_bp_year"):
            d.set(name, hold_bp, ASSUMED,
                  f"prereg §3: swap mark-up {hold_bp:g} bp/yr long and short — Pepperstone's own annual equivalent is not "
                  f"established in venues.json (peers 58-109 bp/yr, derived)")
        out.specs[col] = d.done(_UNUSED_LS)
        rows[col] = d.rows
        out.instruments.append({"instrument": col, "venue_symbol": pair, "panel_instrument_is": f"{side} currency",
                                "lot_step_units": out.specs[col].lot_step, "min_order_ccy": 0.0,
                                "half_spread_bp": out.specs[col].half_spread_bp, "half_spread_basis": d.rows["half_spread_bp"]["basis"],
                                "leverage_cap": out.specs[col].leverage_cap, "esma_major_pair": major})
    out.provenance = _group_provenance(vid, rows)
    out.notes = [
        "ASSUMED instrument availability: the nine USD pairs are taken to be offered; no instrument endpoint was read.",
        "ASSUMED leverage class: ESMA's 30:1 'major' pairs are any two of USD, EUR, JPY, GBP, CAD, CHF (general knowledge of "
        "decision (EU) 2018/796; venues.json records the caps, not the pair list) — AUD, NZD, SEK and NOK pairs get 20:1.",
        "The 0.27 bp commission is venues.json's figure, derived there from USD 3 per standard lot at the EUR/USD reference price; "
        "the minimum fee is its USD 0.04 per order (rounding at 0.01 lot).",
    ]
    if not out.specs:
        out.refused = "no instrument of the book has a cTrader pair"
    return out


def build_venue(venue_id: str, cols: Sequence[str], panel: PanelBundle, evidence: Mapping[str, dict], eurusd: float) -> VenueBuild:
    if venue_id == "trading212_invest":
        return build_trading212(cols, eurusd)
    if venue_id == "kraken_derivatives_eea":
        return build_kraken(cols, panel, evidence, eurusd)
    if venue_id == "bitvavo":
        return build_bitvavo(cols, panel, evidence, eurusd)
    if venue_id == "pepperstone_eu_ctrader":
        return build_pepperstone(cols, panel)
    raise Refused(f"no VenueSpec builder for venue {venue_id!r}")


# ==================================================================================================
# STAGE realism
# ==================================================================================================
def _stats(net: pd.Series, ppy: int, window) -> dict:
    s = stats.summarize(net, periods_per_year=ppy, window=window)
    return {k: s[k] for k in ("n_obs", "start", "end", "ann_return", "cagr", "ann_vol", "sharpe", "max_drawdown")}


def ideal_reference(ctx: "v2.Ctx", spec, cfg, panel: PanelBundle, w: pd.DataFrame, index: pd.DatetimeIndex) -> Tuple[pd.Series, str]:
    """The IDEAL account's per-print net on `index`: column `base` of the Tier-1 stream where it covers the
    prints, else the same account recomputed with the runner's own `account_run`."""
    path = ctx.run / "tier1_net" / f"{spec.id}.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        if "base" in df.columns and index.isin(df.index).all():
            s = df["base"].reindex(index).astype(np.float64)
            if np.isfinite(s.to_numpy()).all():
                return s.rename("ideal_net"), f"{path.name} column 'base' (Tier-1 drift-aware account, ideal venue, lane base cost)"
    lo = bool(spec.transforms.get("long_only"))
    acct = v2.account_run(panel.subset(list(w.columns)), w, cfg, v2.COSTS[v2._t1_cost_key(spec)]["base"], lo,
                          spec.transforms.get("rebalance"))
    s = acct.net.reindex(index).astype(np.float64)
    if not np.isfinite(s.to_numpy()).all():
        raise Refused(f"{spec.id}: the recomputed ideal account does not cover the FULL window")
    return s.rename("ideal_net"), "recomputed with v2.account_run (ideal venue, lane base cost) — the saved stream did not cover the prints"


def _refused_block(pid: str, venue_id: str, lane: str, why: str, synthetic: bool) -> Tuple[dict, List[dict]]:
    block = {"book": pid, "venue": venue_id, "lane": lane, "status": f"REFUSED: {why}", "provenance": [], "instruments": [],
             "dropped": [], "notes": []}
    recs = [{"book": pid, "venue": venue_id, "lane": lane, "equity0_eur": s, "monthly_contribution_eur": c,
             "status": f"REFUSED: {why}", "synthetic": synthetic} for s in EUR_SIZES for c in CONTRIBUTIONS_EUR]
    return block, recs


def realism_book(ctx: "v2.Ctx", pid: str, venue_id: str, evidence: Mapping[str, dict], eurusd: float) -> Tuple[dict, List[dict]]:
    """Every size x contribution of one book at one venue. Returns (venue block, records)."""
    spec = {s.id: s for s in registry.primaries()}[pid]
    lane = spec.lane
    wpath = ctx.run / "tier1_w" / f"{pid}.parquet"
    if not wpath.exists():
        return _refused_block(pid, venue_id, lane, f"no Tier-1 target frame at {wpath.name} (tier1 not run, or the book is "
                              f"NOT IMPLEMENTABLE AT THIS COST)", ctx.synthetic)
    cfg = ctx.cfg(lane)
    panel = ctx.panel(lane)
    w = pd.read_parquet(wpath)
    if not w.index.equals(panel.prices.index) or any(c not in panel.prices.columns for c in w.columns):
        return _refused_block(pid, venue_id, lane, "the Tier-1 target frame does not match the lane panel (index or instruments)",
                              ctx.synthetic)
    w.index = panel.prices.index
    cols = list(w.columns)
    build = build_venue(venue_id, cols, panel.subset(cols), evidence, eurusd)
    if build.refused:
        block, recs = _refused_block(pid, venue_id, lane, build.refused, ctx.synthetic)
        block.update({"dropped": build.dropped, "notes": build.notes})
        return block, recs
    keep = [c for c in cols if c in build.specs]
    sub = panel.subset(keep).window(cfg.full[0], cfg.full[1])
    idx = sub.prices.index
    if len(idx) < 5:
        return _refused_block(pid, venue_id, lane, "the FULL window has fewer than five prints", ctx.synthetic)
    w_sub = w.loc[idx, keep]
    ideal, ideal_src = ideal_reference(ctx, spec, cfg, panel, w, idx)
    lo = bool(spec.transforms.get("long_only"))
    freq = spec.transforms.get("rebalance")
    delay = 0 if cfg.exec_prints else 1
    mask = portfolio.rebalance_rows(idx, freq, offset=delay) if lo else None
    band = 0.0 if lo else v2.BUFFER
    # The account opens flat: its opening trade is on row `delay` and first earns on row `delay + 1`, while the
    # ideal book is already invested. Returns and tracking are compared from that print on, for both.
    scored = (idx[delay + 1], cfg.full[1])
    in_score = stats.window_mask(idx, scored)
    ideal_st = _stats(ideal, cfg.ppy, scored)
    gross_all = float(w.loc[idx].abs().to_numpy().sum())
    listed_share = float(w_sub.abs().to_numpy().sum() / gross_all) if gross_all > 0 else float("nan")
    block = {"book": pid, "venue": venue_id, "lane": lane, "status": "OK", "long_only": lo, "rebalance": freq,
             "no_trade_band": band, "delay_prints": delay, "window": list(cfg.full), "first_print": idx[0].isoformat(),
             "last_print": idx[-1].isoformat(), "n_prints": int(len(idx)), "returns_scored_from": idx[delay + 1].isoformat(),
             "n_book_instruments": len(cols),
             "n_simulated_instruments": len(keep), "n_dropped_instruments": len(build.dropped),
             "listed_share_of_target_gross": listed_share, "ideal_reference": ideal_src, "ideal": ideal_st,
             "provenance": build.provenance, "instruments": build.instruments, "dropped": build.dropped, "notes": build.notes}
    recs: List[dict] = []
    paths = {"ideal_net": ideal, "ideal_growth": (1.0 + ideal.where(in_score, 0.0)).cumprod()}   # growth of 1 from the first scored print
    for size in EUR_SIZES:
        for contrib in CONTRIBUTIONS_EUR:
            rec = {"book": pid, "venue": venue_id, "lane": lane, "equity0_eur": size, "monthly_contribution_eur": contrib,
                   "eurusd": eurusd, "equity0_ccy": size * eurusd, "currency": "USD (the panel's price currency)",
                   "synthetic": ctx.synthetic}
            try:
                res = realism.simulate_account(sub, w_sub, equity0=size * eurusd, venue=build.specs,
                                               monthly_contribution=contrib * eurusd, rebalance_mask=mask, no_trade_band=band,
                                               ideal_net=ideal, window=cfg.full, **v2.eng_kwargs(sub, cfg))
            except REFUSALS as exc:
                rec["status"] = f"REFUSED: {exc}"
                recs.append(rec)
                continue
            st = _stats(res.net, cfg.ppy, scored)
            gap = (res.net - ideal).to_numpy()[in_score]
            a, b = res.net.to_numpy()[in_score], ideal.to_numpy()[in_score]
            cb, meta = res.cost_breakdown, res.meta
            e0 = size * eurusd
            paid_in = e0 + cb["contributions"]
            share = st["ann_return"] / ideal_st["ann_return"] if ideal_st["ann_return"] > 0 else None
            eq = res.equity / e0
            rec.update({
                "status": "OK", "final_equity_ccy": meta["final_equity"], "final_equity_multiple_of_start": meta["final_equity"] / e0,
                "contributions_ccy": cb["contributions"], "contributions_multiple_of_start": cb["contributions"] / e0,
                "final_equity_over_paid_in": meta["final_equity"] / paid_in, "ruined_at": meta["ruined_at"],
                **{k: st[k] for k in ("cagr", "ann_return", "ann_vol", "sharpe", "max_drawdown")},
                "returns_basis": "time-weighted, from the per-print net of the account (contributions do not count as return)",
                "ideal_cagr": ideal_st["cagr"], "ideal_ann_return": ideal_st["ann_return"], "ideal_sharpe": ideal_st["sharpe"],
                "share_of_ideal_ann_return": share,
                "share_note": None if share is not None else "the ideal net annual return is not positive: a share is not defined",
                "ann_return_gap_vs_ideal": st["ann_return"] - ideal_st["ann_return"],
                "tracking_error_ann": float(gap.std(ddof=1) * math.sqrt(cfg.ppy)), "tracking_mean_gap_ann": float(gap.mean() * cfg.ppy),
                "tracking_corr": float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else None,
                "costs": {"fees_ccy": cb["fees"], "spread_ccy": cb["spread"], "financing_ccy": cb["financing"],
                          "fees_multiple_of_start": cb["fees"] / e0, "spread_multiple_of_start": cb["spread"] / e0,
                          "financing_multiple_of_start": cb["financing"] / e0, "fees_bp_year": cb["fees_bp_year"],
                          "spread_bp_year": cb["spread_bp_year"], "financing_bp_year": cb["financing_bp_year"],
                          "frictions_bp_year": cb["frictions_bp_year"], "carry_bp_year": cb["carry_bp_year"],
                          "bp_year_basis": "bp per year of the account's average equity over its life (the FULL window)"},
                "turnover_sides_per_year": cb["turnover_sides_per_year"],
                "avg_gross_leverage": float(res.gross_leverage.mean()),
                "orders": {"n_orders": meta["n_orders"], "n_orders_at_min_fee": meta["n_orders_at_min_fee"],
                           "n_skipped_min_notional": meta["n_orders_skipped_min_notional"],
                           "n_targets_rounded_to_zero": meta["n_targets_rounded_to_zero"],
                           "n_skipped_lot_or_minimum": meta["n_orders_skipped_min_notional"] + meta["n_targets_rounded_to_zero"],
                           "n_skipped_in_band": meta["n_trades_skipped_in_band"], "n_skipped_no_price": meta["n_orders_skipped_no_price"],
                           "n_prints_leverage_capped": meta["n_prints_leverage_capped"], "n_prints_over_cap": meta["n_prints_over_cap"],
                           "max_margin_utilisation": meta["max_margin_utilisation"], "n_missing_price_held": meta["n_missing_price_held"],
                           "n_trade_rows": meta["n_trade_rows"],
                           "targets_rounded_to_zero_by_instrument": meta["targets_rounded_to_zero_by_instrument"]},
                "equity_path_year_end_multiple_of_start": {str(y): float(v) for y, v in eq.groupby(eq.index.year).last().items()},
            })
            paths[f"net_eur{size:.0f}_plus{contrib:.0f}"] = res.net
            paths[f"equity_eur{size:.0f}_plus{contrib:.0f}"] = eq
            recs.append(rec)
    eqdir = ctx.run / "realism_paths"
    eqdir.mkdir(exist_ok=True)
    pd.DataFrame(paths).to_parquet(eqdir / f"{pid}__{venue_id}.parquet")
    block["paths_file"] = f"realism_paths/{pid}__{venue_id}.parquet"
    return block, recs


def stage_realism(ctx: "v2.Ctx", allow_network: bool = True) -> dict:
    sha = v2.check_pins(ctx)
    eurusd, ref = reference_eurusd()
    evidence = synthetic_evidence(ctx, eurusd) if ctx.synthetic else real_evidence(allow_network)
    out = {"stage": "realism", "prereg_sha256": sha, "generated_utc": utc_now(), "synthetic": ctx.synthetic,
           "reference": ref, "sizes_eur": list(EUR_SIZES), "monthly_contributions_eur": list(CONTRIBUTIONS_EUR),
           "evidence": {k: {"meta": v.get("meta"), "error": v.get("error")} for k, v in evidence.items()},
           "conventions": REALISM_CONVENTIONS, "venues": [], "records": []}
    lanes = {s.id: s.lane for s in registry.primaries()}
    for k, (pid, venue_id) in enumerate(BOOKS):
        t0 = time.time()
        try:
            block, recs = realism_book(ctx, pid, venue_id, evidence, eurusd)
        except REFUSALS as exc:
            block, recs = _refused_block(pid, venue_id, lanes[pid], str(exc), ctx.synthetic)
        out["venues"].append(block)
        out["records"] += recs
        ok = [r for r in recs if r["status"] == "OK"]
        print(f"[realism] {pid} @ {venue_id}: {block['status']}; {len(ok)}/{len(recs)} simulations "
              f"({block.get('n_simulated_instruments', 0)}/{block.get('n_book_instruments', 0)} instruments) "
              f"({time.time() - t0:.1f}s)", flush=True)
        if lanes[pid] not in {lanes[p] for p, _ in BOOKS[k + 1:]}:
            ctx._cache.pop(lanes[pid], None)                       # a 700-column crypto panel is not kept for nothing
            gc.collect()
    (ctx.run / "realism_results.json").write_text(json.dumps(v2.jsonable(out), indent=1, default=str))
    md = ctx.rep / "REALISM.md"
    head = "" if md.exists() else "# FACTORY v2 — realism pass (PREREGISTRATION_v2 §6)\n"
    with md.open("a") as f:
        f.write(head + "\n" + realism_markdown(out) + "\n")
    print(f"[realism] {ctx.run / 'realism_results.json'} ; section appended to {md}", flush=True)
    return out


REALISM_CONVENTIONS = [
    "Each account opens on the first print of the lane's FULL window, flat, with the stated cash; contributions arrive on the "
    "first print of each later calendar month. Warm-up rows are not simulated. A scheduled (long-only) book makes its opening "
    "trade at once, so until the ideal account's next scheduled rebalance the two can hold slightly different weights.",
    "Timing, rebalance schedule and no-trade band are the Tier-1 runner's. Returns (CAGR, vol, Sharpe, drawdown) are "
    "time-weighted from the account's per-print net, so a contribution is not a return.",
    "Returns and tracking error — the account's and the ideal's alike — are measured from the first print on which the "
    "account's opening trade earns (one print after the opening on the crypto lanes, two on FX and MACRO): before it the new "
    "account is flat while the ideal book is already invested. Final equity and cost totals cover the account's whole life.",
    "IDEAL = the same book in the Tier-1 drift-aware account: frictionless fractional venue plus the lane's base proportional "
    "cost. 'Share of ideal' = the venue account's arithmetic annual net return divided by the ideal's, defined only when the "
    "ideal's is positive (below zero: the venue account lost money where the ideal made some). Tracking error = annualised "
    "standard deviation of (venue net - ideal net) per print.",
    "Currency: USD, the panels' currency; EUR amounts are converted at the ECB reference rate in venues.json. The EUR/USD "
    "exposure of a EUR account is not modelled, so multiples of starting equity are what to read.",
    "Excess-return accounts: the carry panel charges the risk-free rate on funded positions and no venue cash interest is "
    "credited (the rates are unknown in venues.json).",
    "Instruments the venue does not list, or that cannot be mapped with certainty, are not held; their targets are not "
    "re-distributed. Today's listings and lot sizes are applied to the whole history.",
    "Orders fill in full at the print plus or minus half the spread: no market impact, no partial fills. The leverage cap is "
    "enforced when trading and only counted between trades; margin calls are not modelled. 'Max margin use' is the largest "
    "gross notional / leverage cap / equity on any print: 1.000 is the limit, and a few bp above it on an unlevered venue is "
    "the cost of the last rebalance, not borrowing.",
    "Costs in bp per year are bp of the account's average equity over its life.",
]


# ---- markdown helpers
def _f(v, nd: int = 2) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "–"
    return f"{v:,.{nd}f}"


def _p(v, nd: int = 1) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "–"
    return f"{100.0 * v:.{nd}f}%"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]], align: Optional[str] = None) -> List[str]:
    align = align or "l" * len(headers)
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---:" if a == "r" else "---" for a in align) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return out


def _value_text(v) -> str:
    if v is None:
        return "unknown"
    if isinstance(v, dict):
        return f"{v['min']:g} … {v['max']:g} ({v['distinct']} values)"
    return f"{v:g}"


UNITS = {"fee_bp": "bp/side", "min_fee": "USD/order", "half_spread_bp": "bp/side", "lot_step": "units", "min_notional": "USD",
         "contract_notional": "x price", "financing_long_bp_year": "bp/yr", "financing_short_bp_year": "bp/yr",
         "leverage_cap": "x equity", "cash_interest_bp_year": "bp/yr", "cash_interest_threshold": "USD"}


def realism_markdown(out: dict) -> str:
    tag = "SYNTHETIC SMOKE TEST — fabricated venue metadata and synthetic panels, not market data" if out["synthetic"] else "real data"
    L: List[str] = [f"## Realism pass — {out['generated_utc']} ({tag})", "",
                    f"Pre-registration sha256 `{str(out['prereg_sha256'])[:16]}…`. Account sizes EUR "
                    f"{', '.join(f'{s:,.0f}' for s in out['sizes_eur'])}; monthly contribution EUR "
                    f"{' / '.join(f'{c:,.0f}' for c in out['monthly_contributions_eur'])}; EUR/USD {out['reference']['EURUSD']:g} "
                    f"({out['reference'].get('source')}).", "", "### How to read this", ""]
    L += [f"- {c}" for c in out["conventions"]]
    L += ["", "### Instrument metadata used", ""]
    for key, ev in out["evidence"].items():
        meta = ev.get("meta") or {}
        if ev.get("error"):
            L.append(f"- `{key}`: **UNAVAILABLE** — {ev['error']} ({meta.get('url')})")
        elif meta.get("synthetic"):
            L.append(f"- `{key}`: {meta.get('note')}")
        else:
            L.append(f"- `{key}`: {meta.get('url')} — fetched {meta.get('fetched_utc')} by {meta.get('fetched_by')}; "
                     f"sha256 `{str(meta.get('sha256'))[:16]}…`; `{meta.get('path')}`")
    for block in out["venues"]:
        L += ["", f"### {block['book']} @ `{block['venue']}`", ""]
        if block["status"] != "OK":
            L += [f"**{block['status']}**", ""]
        else:
            mode = (f"Long-only, trades on the {block['rebalance']} schedule" if block["long_only"]
                    else f"Long/short, no-trade band {_p(block['no_trade_band'], 0)}")
            L += [f"{block['n_simulated_instruments']} of the book's {block['n_book_instruments']} instruments are simulated "
                  f"({_p(block['listed_share_of_target_gross'])} of its gross target exposure inside the window); "
                  f"{block['n_prints']} prints, {block['first_print'][:10]} → {block['last_print'][:10]} (returns scored from "
                  f"{block['returns_scored_from'][:10]}). {mode}. "
                  f"Ideal reference: {block['ideal_reference']} — CAGR {_p(block['ideal']['cagr'])}, "
                  f"Sharpe {_f(block['ideal']['sharpe'])}, max drawdown {_p(block['ideal']['max_drawdown'])}.", ""]
        for n in block.get("notes", []):
            L.append(f"- {n}")
        if block.get("provenance"):
            L += ["", "Venue fields (`venues.json` = read by `VenueSpec.from_json`; VERIFIED / ASSUMED = an explicit override):", ""]
            L += _table(["field", "value", "unit", "basis", "instruments", "source"],
                        [[r["field"], _value_text(r["value"]), UNITS.get(r["field"], ""), r["basis"], r["n_instruments"], r["source"]]
                         for r in block["provenance"]])
        if block.get("dropped"):
            L += ["", f"Dropped — not held at this venue ({len(block['dropped'])} instruments; each reason is in the JSON):", ""]
            for kind, text in DROP_KINDS.items():
                names = [d for d in block["dropped"] if d.get("kind") == kind]
                if not names:
                    continue
                if kind in ("price_mismatch", "not_eligible"):
                    L.append(f"- {text} ({len(names)}):")
                    L += [f"    - `{d['instrument']}`: {d['reason']}" for d in names]
                else:
                    L.append(f"- {text} ({len(names)}): " + ", ".join(f"`{d['instrument']}`" for d in names))
        recs = [r for r in out["records"] if r["book"] == block["book"] and r["venue"] == block["venue"]]
        okr = [r for r in recs if r["status"] == "OK"]
        if okr:
            L += ["", "Results (multiples are of starting equity; returns are time-weighted):", ""]
            L += _table(
                ["start EUR", "+EUR/mo", "final x", "paid in x", "CAGR", "vol", "Sharpe", "max DD", "share of ideal return",
                 "TE /yr", "fees bp/yr", "spread bp/yr", "financing bp/yr", "turnover /yr", "orders", "skipped: minimum / lot→0",
                 "max margin use"],
                [[f"{r['equity0_eur']:,.0f}", f"{r['monthly_contribution_eur']:,.0f}", _f(r["final_equity_multiple_of_start"], 3),
                  _f(1.0 + r["contributions_multiple_of_start"], 3), _p(r["cagr"]), _p(r["ann_vol"]), _f(r["sharpe"]),
                  _p(r["max_drawdown"]), _p(r["share_of_ideal_ann_return"], 0) if r["share_of_ideal_ann_return"] is not None
                  else f"n/a (gap {_p(r['ann_return_gap_vs_ideal'], 2)}/yr)", _p(r["tracking_error_ann"], 2),
                  _f(r["costs"]["fees_bp_year"], 1), _f(r["costs"]["spread_bp_year"], 1), _f(r["costs"]["financing_bp_year"], 1),
                  _f(r["turnover_sides_per_year"], 1), f"{r['orders']['n_orders']:,}",
                  f"{r['orders']['n_skipped_min_notional']:,} / {r['orders']['n_targets_rounded_to_zero']:,}",
                  _f(r["orders"]["max_margin_utilisation"], 3)] for r in okr],
                "rrrrrrrrrrrrrrrrr")
            if block.get("paths_file"):
                L += ["", f"Per-print equity (multiple of starting equity) and net return of every account, beside the ideal's: "
                          f"`{block['paths_file']}`."]
        for r in recs if block["status"] == "OK" else []:
            if r["status"] != "OK":
                L.append(f"- EUR {r['equity0_eur']:,.0f} + {r['monthly_contribution_eur']:,.0f}/mo: **{r['status']}**")
    return "\n".join(L)


# ==================================================================================================
# STAGE ladder — bootstrap ladder
# ==================================================================================================
def terminal_wealth(paths: np.ndarray, leverage: float, floor: float = RUIN_FLOOR):
    """Compound return paths (reps x prints) at `leverage` with ABSORPTION.

    A path is RUINED on the first print where 1 + L*r <= 0 (that single print loses >= 100 %: wealth 0) or
    where compounded wealth is <= `floor` of the start. Nothing after that print counts.
    Returns (terminal, ruined, wiped, when):
      terminal  wealth as a multiple of the start: at the end of the path, or frozen at the print of ruin
      ruined    bool per path
      wiped     bool per path: the ruin was a single-print loss of >= 100 %
      when      print index of the ruin, -1 if none"""
    r = np.atleast_2d(np.asarray(paths, dtype=np.float64))
    g = 1.0 + float(leverage) * r
    wipe = g <= 0.0
    with np.errstate(over="ignore", invalid="ignore"):
        w = np.nan_to_num(np.cumprod(np.where(wipe, 0.0, g), axis=1), nan=0.0, posinf=np.inf)
    hit = w <= floor
    ruined = hit.any(axis=1)
    first = hit.argmax(axis=1)
    rows = np.arange(r.shape[0])
    terminal = np.where(ruined, w[rows, first], w[:, -1])
    return terminal, ruined, ruined & wipe[rows, first], np.where(ruined, first, -1)


def resample_paths(r: np.ndarray, horizon: int, reps: int, block: float, rng: np.random.Generator) -> np.ndarray:
    """(reps, horizon) return paths: the first `horizon` positions of `stats.stationary_bootstrap_indices`
    draws over the whole stream (a stationary-bootstrap path is built left to right, so its head is one)."""
    n = len(r)
    if horizon > n:
        raise Refused(f"a {horizon}-print path needs at least {horizon} prints; the stream has {n}")
    out = np.empty((reps, horizon), dtype=np.float64)
    chunk = max(1, 1_500_000 // n)                              # bound the (chunk, n) index arrays
    done = 0
    while done < reps:
        k = min(chunk, reps - done)
        out[done:done + k] = r[stats.stationary_bootstrap_indices(n, block, k, rng)[:, :horizon]]
        done += k
    return out


def growth_optimal_leverage(r: np.ndarray, l_max: float = GRID_MAX_L, coarse: float = 0.05, fine: float = 0.001) -> dict:
    """argmax over L in [0, l_max] of mean(log(1 + L*r)) on the stream itself (IN-SAMPLE). The mean is -inf
    as soon as one print would lose >= 100 %. Coarse grid, then a fine grid around its best point (the
    objective is concave in L)."""
    r = np.asarray(r, dtype=np.float64)

    def growth(ls: np.ndarray) -> np.ndarray:
        out = np.full(len(ls), -np.inf)
        for a in range(0, len(ls), 256):
            x = 1.0 + np.outer(ls[a:a + 256], r)
            alive = (x > 0.0).all(axis=1)
            out[a:a + 256] = np.where(alive, np.log(np.where(x > 0.0, x, 1.0)).mean(axis=1), -np.inf)
        return out

    lc = np.round(np.arange(0.0, l_max + coarse / 2.0, coarse), 9)
    i = int(np.argmax(growth(lc)))
    lf = np.round(np.arange(max(0.0, lc[i] - coarse), min(l_max, lc[i] + coarse) + fine / 2.0, fine), 9)
    gf = growth(lf)
    j = int(np.argmax(gf))
    worst = float(r.min()) if len(r) else float("nan")
    return {"L": float(lf[j]), "mean_log_growth_per_print": float(gf[j]), "at_grid_cap": bool(lf[j] >= l_max - 1e-9),
            "grid": f"0 … {l_max:g} step {coarse:g}, then step {fine:g} around the best point",
            "single_print_wipe_out_leverage": (1.0 / -worst) if worst < 0 else None,
            "caveat": "IN-SAMPLE: the leverage that would have maximised compound growth on this exact history"}


def ladder_for_stream(r, ppy: float, *, levels: Sequence[float] = LADDER_L, reps: int = LADDER_REPS, seed=0,
                      horizon: Optional[int] = None) -> dict:
    """The leverage ladder of one per-print net return stream (already net of costs, which scale with L)."""
    r = np.asarray(r, dtype=np.float64).reshape(-1)
    if len(r) < 2 or not np.isfinite(r).all():
        raise Refused("the return stream must have at least two finite prints")
    n = len(r)
    m = int(round(ppy)) if horizon is None else int(horizon)
    block = stats.default_block_length(n)
    paths = resample_paths(r, m, int(reps), block, np.random.default_rng(seed))
    rows = []
    for lev in levels:
        term, ruined, wiped, _ = terminal_wealth(paths, lev)
        alive = ~ruined
        med = float(np.median(term))
        _, h_ruined, h_wiped, h_when = terminal_wealth(r[None, :], lev)
        rows.append({
            "L": float(lev), "median_wealth": med, "p05_wealth": float(np.quantile(term, 0.05)),
            "p95_wealth": float(np.quantile(term, 0.95)), "p_final_below_half": float((term < 0.5).mean()),
            "p_ruin": float(ruined.mean()), "p_ruin_single_print_loss": float(wiped.mean()),
            "share_ruined": float(ruined.mean()), "n_survivors": int(alive.sum()),
            "mean_log_wealth_survivors": float(np.log(term[alive]).mean()) if alive.any() else None,
            "median_log_wealth": math.log(med) if med > 0 else None, "median_log_wealth_is_minus_inf": bool(med <= 0),
            "mean_log_growth_per_print_full_sample": float(np.log1p(lev * r).mean()) if (1.0 + lev * r > 0).all() else None,
            "actual_history_ruined": bool(h_ruined[0]), "actual_history_ruin_print": int(h_when[0]) if h_ruined[0] else None,
            "actual_history_ruin_by_single_print": bool(h_wiped[0]),
        })
    best = max(rows, key=lambda row: (row["median_wealth"], -row["L"]))        # ties go to the lower leverage
    mu = float(r.mean())
    var = float(r.var(ddof=1)) if r.max() > r.min() else 0.0      # a constant stream has no variance, whatever float dust says
    sd = math.sqrt(var)
    return {
        "n_obs": n, "periods_per_year": float(ppy), "horizon_prints": m, "block": float(block), "reps": int(reps),
        "stream": {"ann_return": mu * ppy, "ann_vol": sd * math.sqrt(ppy), "sharpe": (mu / sd * math.sqrt(ppy)) if sd > 0 else None,
                   "worst_print": float(r.min()), "best_print": float(r.max())},
        "levels": rows,
        "best_L_by_median_log_wealth": best["L"] if best["median_wealth"] > 0 else None,
        "growth_optimal": growth_optimal_leverage(r),
        "kelly_continuous_time": {"L": (mu / var) if var > 0 else None, "mean_per_print": mu, "variance_per_print": var,
                                  "formula": "mean / variance of the per-print net return"},
    }


# ==================================================================================================
# STAGE ladder — 200x on hourly BTC candles
# ==================================================================================================
def first_passage(values: np.ndarray, thresholds: np.ndarray, below: bool) -> np.ndarray:
    """j[i] = the smallest j >= i with values[j] <= thresholds[i] (`below`) or >= thresholds[i]; len(values)
    if there is none. Sparse table of block minima plus a binary descent: O(n log n)."""
    v = np.asarray(values, dtype=np.float64)
    t = np.asarray(thresholds, dtype=np.float64)
    if not below:
        v, t = -v, -t
    n = len(v)
    levels = [v]
    while len(levels) < max(n.bit_length(), 1):
        prev, half = levels[-1], 1 << (len(levels) - 1)
        levels.append(np.minimum(prev, np.concatenate([prev[half:], np.full(min(half, n), np.inf)])[:n]))
    pos = np.arange(n, dtype=np.int64)
    for k in range(len(levels) - 1, -1, -1):
        inside = pos < n
        block_min = np.full(n, np.inf)
        block_min[inside] = levels[k][pos[inside]]
        pos = np.where(inside & (block_min > t), pos + (1 << k), pos)
    return np.minimum(pos, n)


def liquidation_hours(open_ms: np.ndarray, entry: np.ndarray, high: np.ndarray, low: np.ndarray, distance: float,
                      side: str) -> np.ndarray:
    """Hours from an entry at the OPEN of candle i until the position is liquidated: a LONG when a candle's
    LOW is <= entry * (1 - distance), a SHORT when a HIGH is >= entry * (1 + distance). The entry candle
    itself counts — its low and high print after its open. The value is the END of the liquidating candle
    in whole hours of clock time (1 = within the first hour); NaN = never inside the data (censored)."""
    if side == "long":
        j = first_passage(low, entry * (1.0 - distance), below=True)
    elif side == "short":
        j = first_passage(high, entry * (1.0 + distance), below=False)
    else:
        raise Refused(f"side must be 'long' or 'short'; got {side!r}")
    n = len(entry)
    out = np.full(n, np.nan)
    ok = j < n
    ms = np.asarray(open_ms, dtype=np.int64)
    out[ok] = (ms[j[ok]] - ms[ok]) / HOUR_MS + 1.0
    return out


def liquidation_table(candles: pd.DataFrame, distances: Sequence[float] = LIQ_DISTANCES,
                      horizons: Sequence[int] = LIQ_HORIZONS_H) -> dict:
    """Share of hourly entries liquidated within each horizon, per side and adverse-move distance.
    `candles`: index = open time in ms (sorted, unique), columns open, high, low. Entries without a full
    max(horizons) hours of data after them are left out of every figure."""
    ms = candles.index.to_numpy(dtype=np.int64)
    o, h, lo = (candles[c].to_numpy(dtype=np.float64) for c in ("open", "high", "low"))
    if len(ms) == 0 or (np.diff(ms) <= 0).any():
        raise Refused("candles must be a non-empty frame sorted by a unique open time")
    scored = ms <= ms[-1] - (max(horizons) - 1) * HOUR_MS
    rows = []
    for d in distances:
        for side in ("long", "short"):
            hrs = liquidation_hours(ms, o, h, lo, d, side)[scored]
            never = np.isnan(hrs)
            med = float(np.median(np.where(never, np.inf, hrs)))
            rows.append({"side": side, "adverse_move": float(d), "n_entries": int(scored.sum()),
                         **{f"share_within_{k}h": float((hrs <= k).mean()) for k in horizons},
                         "median_hours_to_liquidation": med if math.isfinite(med) else None,
                         "share_never_liquidated_in_data": float(never.mean())})
    expected = int((ms[-1] - ms[0]) // HOUR_MS) + 1
    return {"n_candles": int(len(ms)), "first_open_utc": pd.Timestamp(int(ms[0]), unit="ms", tz="UTC").isoformat(),
            "last_open_utc": pd.Timestamp(int(ms[-1]), unit="ms", tz="UTC").isoformat(),
            "missing_hourly_candles": expected - int(len(ms)), "rows": rows,
            "time_resolution": "one hour: 'within 1 h' means inside the entry candle"}


def read_ohlc_1h(symbol: str = "BTCUSDT", market: str = "perp") -> pd.DataFrame:
    """Hourly OHLC of one Binance symbol from the raw files the data layer downloaded — no network.

    Same conventions as `scripts.factory.data.crypto.read_klines` (which keeps only the close): REST pages
    `rest_klines_1h/<SYM>/1h_*.json` and archive zips `archive_klines_1h/<SYM>/*.zip` (header optional,
    microsecond stamps detected per file, every candle inside the period its file names); candles off the
    hourly grid are dropped; REST wins on duplicates. Index = open time in ms; columns open, high, low,
    close, count, src (0 = REST, 1 = archive)."""
    from scripts.factory.data import crypto as dcrypto
    from scripts.factory.data.common import RAW

    src = dcrypto.SRC[market]
    parts: List[np.ndarray] = []
    d = RAW / src / "rest_klines_1h" / symbol
    for p in sorted(d.glob("1h_*.json")) if d.exists() else []:
        data = json.loads(p.read_bytes())
        if data:
            a = np.array([(k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[8])) for k in data], dtype=np.float64)
            parts.append(np.column_stack([a, np.zeros(len(a))]))
    d = RAW / src / "archive_klines_1h" / symbol
    for p in sorted(d.glob("*.zip")) if d.exists() else []:
        lo_ms, hi_ms = dcrypto.archive_file_bounds(p.name)
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                b = z.read(name)
                df = pd.read_csv(io.BytesIO(b), header=None, skiprows=1 if b[:1].isalpha() else 0, usecols=[0, 1, 2, 3, 4, 8],
                                 names=["open_time", "open", "high", "low", "close", "count"], dtype="float64")
                a = df.to_numpy(dtype=np.float64)
                if not len(a):
                    continue
                micro = a[:, 0] > 1e14
                if micro.any() and not micro.all():
                    raise Refused(f"{p.name}: the file mixes millisecond and microsecond timestamps")
                if micro.all():
                    a[:, 0] = np.floor(a[:, 0] / 1000.0)
                if a[:, 0].min() < lo_ms or a[:, 0].max() >= hi_ms:
                    raise Refused(f"{p.name}: a candle opens outside the period named by the file")
                parts.append(np.column_stack([a, np.ones(len(a))]))
    if not parts:
        raise Refused(f"no hourly candles on disk for {symbol} under {RAW / src}")
    a = np.vstack(parts)
    df = pd.DataFrame(a[:, 1:], columns=["open", "high", "low", "close", "count", "src"], index=a[:, 0].astype(np.int64))
    df = df[(df.index.to_numpy() % HOUR_MS) == 0].sort_values("src", kind="stable")
    df = df[~df.index.duplicated(keep="first")].sort_index()
    px = df[["open", "high", "low", "close"]].to_numpy()
    bad = ~(np.isfinite(px).all(axis=1) & (px > 0).all(axis=1) & (df["high"] >= df[["open", "close"]].max(axis=1)).to_numpy()
            & (df["low"] <= df[["open", "close"]].min(axis=1)).to_numpy())
    if bad.any():
        raise Refused(f"{symbol}: {int(bad.sum())} hourly candles are not valid OHLC rows, first at open_ms {int(df.index[bad][0])}")
    return df


def btc_candles(ctx: "v2.Ctx") -> Tuple[pd.DataFrame, dict]:
    """(candles from LIQ_START, provenance). Synthetic mode fabricates a seeded random walk instead."""
    start_ms = int(pd.Timestamp(LIQ_START, tz="UTC").value // 10**6)
    if ctx.synthetic:
        rng = np.random.default_rng([v2.SEED, 62])
        n, steps = 24 * 250, 12
        path = 30000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.006 / math.sqrt(steps), n * steps)))
        path = np.concatenate([[30000.0], path])
        seg = np.lib.stride_tricks.sliding_window_view(path, steps + 1)[::steps]
        df = pd.DataFrame({"open": seg[:, 0], "high": seg.max(axis=1), "low": seg.min(axis=1), "close": seg[:, -1]},
                          index=start_ms + HOUR_MS * np.arange(n, dtype=np.int64))
        return df, {"synthetic": True, "note": "FABRICATED hourly candles (seeded random walk) — not market data"}
    raw = read_ohlc_1h("BTCUSDT", "perp")
    df = raw[(raw.index >= start_ms) & (raw["count"] > 0)]
    return df, {"synthetic": False, "symbol": "BTCUSDT", "market": "Binance USD-M perpetual", "interval": "1h",
                "files": "research/factory/data/raw/binance/futures_um/{archive_klines_1h,rest_klines_1h}/BTCUSDT",
                "from": LIQ_START, "rows_from_rest": int((df["src"] == 0).sum()), "rows_from_archive": int((df["src"] == 1).sum()),
                "zero_trade_candles_dropped": int(((raw.index >= start_ms) & (raw["count"] <= 0)).sum())}


def fee_arithmetic(leverage: float = LIQ_LEVERAGE, fees_bp: Sequence[float] = LIQ_FEES_BP) -> List[dict]:
    """Round-trip fees of a position of `leverage` x margin, as a share of the margin."""
    return [{"fee_bp_per_side": float(f), "leverage": float(leverage),
             "round_trip_fee_pct_of_margin": 2.0 * f / 1e4 * leverage * 100.0,
             "price_move_to_break_even_pct": 2.0 * f / 1e4 * 100.0} for f in fees_bp]


def eu_leverage_facts() -> dict:
    """What venues.json records about retail leverage: the ESMA / AFM CFD caps and every venue's own caps."""
    doc = venues_doc()
    rules = doc["reference"]["eu_retail_cfd_rules"]
    venues = []
    for v in doc["venues"]:
        caps = v.get("leverage_caps") or {}
        nums = {k: float(x) for k, x in caps.items() if isinstance(x, (int, float)) and not isinstance(x, bool)}
        entity = str(v.get("legal_entity") or "")
        venues.append({"venue_id": v.get("venue_id"), "legal_entity": entity, "numeric_caps": nums,
                       "max_numeric_cap": max(nums.values()) if nums else None,
                       "claims_eu_entity": not entity.lower().startswith("none"), "nl_eligible": v.get("nl_eligible")})
    eu = [x for x in venues if x["claims_eu_entity"] and x["max_numeric_cap"] is not None]
    top_all = max((x for x in venues if x["max_numeric_cap"] is not None), key=lambda x: x["max_numeric_cap"])
    top_eu = max(eu, key=lambda x: x["max_numeric_cap"]) if eu else None
    kraken = venue_entry("kraken_derivatives_eea").get("leverage_caps") or {}
    return {"esma_retail_cfd_caps": rules.get("leverage_caps"), "margin_close_out": rules.get("margin_close_out"),
            "perpetual_futures_note": rules.get("perpetual_futures_note"), "rules_label": rules.get("label"),
            "rules_url": rules.get("url"), "kraken_eea_retail_cap": kraken.get("eea_retail"), "kraken_eea_detail": kraken.get("detail"),
            "venues": venues, "highest_cap_any_venue": {"venue_id": top_all["venue_id"], "cap": top_all["max_numeric_cap"]},
            "highest_cap_eu_entity": {"venue_id": top_eu["venue_id"], "cap": top_eu["max_numeric_cap"]} if top_eu else None,
            "x200_available": bool(top_all["max_numeric_cap"] >= 200.0)}


def stage_ladder(ctx: "v2.Ctx", reps: int = LADDER_REPS) -> dict:
    sha = v2.check_pins(ctx)
    lanes = {s.id: s.lane for s in registry.primaries()}
    out = {"stage": "ladder", "prereg_sha256": sha, "generated_utc": utc_now(), "synthetic": ctx.synthetic,
           "levels": list(LADDER_L), "reps": int(reps), "ruin_rule": f"a single print loses >= 100 % (1 + L*r <= 0) or wealth <= "
           f"{RUIN_FLOOR:.0%} of the start; absorbing", "caveats": LADDER_CAVEATS, "books": []}
    for k, (pid, venue_id) in enumerate(BOOKS):
        cfg = ctx.cfg(lanes[pid])
        path = ctx.run / "tier1_net" / f"{pid}.parquet"
        rec = {"book": pid, "venue": venue_id, "lane": lanes[pid], "window": list(cfg.full)}
        if not path.exists():
            rec["status"] = f"REFUSED: no Tier-1 net stream at {path.name}"
            out["books"].append(rec)
            continue
        base = pd.read_parquet(path)["base"]
        s = base[stats.window_mask(base.index, cfg.full)]
        try:
            rec.update(ladder_for_stream(s.to_numpy(dtype=np.float64), cfg.ppy, reps=reps, seed=[v2.SEED, 61, k]))
        except REFUSALS as exc:
            rec["status"] = f"REFUSED: {exc}"
            out["books"].append(rec)
            continue
        rec.update({"status": "OK", "first_print": s.index[0].isoformat(), "last_print": s.index[-1].isoformat(),
                    "seed": [v2.SEED, 61, k]})
        for row in rec["levels"]:
            i = row["actual_history_ruin_print"]
            row["actual_history_ruin_date"] = s.index[i].isoformat() if i is not None else None
        out["books"].append(rec)
        print(f"[ladder] {pid}: {rec['n_obs']} prints, block {rec['block']:.0f}; growth-optimal L {rec['growth_optimal']['L']:.2f} "
              f"(in-sample); P(ruin) at 200x {rec['levels'][-1]['p_ruin']:.3f}", flush=True)
    candles, prov = btc_candles(ctx)
    out["btc_200x"] = {"source": prov, **liquidation_table(candles), "fees": fee_arithmetic(),
                       "margin_note": f"at {LIQ_LEVERAGE:g}x the whole margin is a {100.0 / LIQ_LEVERAGE:g} % adverse move; "
                                      f"0.25 % stands for a typical maintenance level — the exact liquidation distance is "
                                      f"venue-specific (maintenance margin, fees, mark versus last price)"}
    out["eu_leverage"] = eu_leverage_facts()
    (ctx.run / "ladder_results.json").write_text(json.dumps(v2.jsonable(out), indent=1, default=str))
    (ctx.rep / "LEVERAGE_LADDER.md").write_text(ladder_markdown(out) + "\n")
    print(f"[ladder] {ctx.run / 'ladder_results.json'} ; {ctx.rep / 'LEVERAGE_LADDER.md'}", flush=True)
    return out


LADDER_CAVEATS = [
    "Prints are daily. A levered position is liquidated on the intraday path, not at the close, so every P(ruin) here is a "
    "LOWER BOUND — the hourly BTC table below shows how much a daily print hides.",
    "Each stream is the book's base-cost net return. Scaling it by L scales its trading and holding costs by L and nothing "
    "else: no extra financing spread on the borrowed notional, no liquidation fee, no funding cap.",
    "The streams are excess returns, so a levered row borrows at the risk-free rate with no mark-up.",
    "P.MACRO.LO_TREND at Trading 212 and P.CRYPTO.LO_TREND at Bitvavo are unlevered cash accounts: their rows above L = 1 are "
    "arithmetic on the stream, not an account those venues offer.",
    "A one-year path is a stationary-bootstrap resample of the book's own history: it can only contain days that happened.",
    "'Mean log wealth, survivors' is conditional on not being ruined: with few survivors it is the luck of the survivors, not "
    "an expectation.",
    "The growth-optimal L and the Kelly ratio are computed on the whole sample and are IN-SAMPLE: they describe this history, "
    "not a forecast, and estimation error makes the true optimum lower.",
]


def ladder_markdown(out: dict) -> str:
    tag = "SYNTHETIC SMOKE TEST — synthetic panels and fabricated candles, not market data" if out["synthetic"] else "real data"
    L: List[str] = [f"# FACTORY v2 — leverage ladder (PREREGISTRATION_v2 §6) — {tag}", "",
                    f"Pre-registration sha256 `{str(out['prereg_sha256'])[:16]}…`. Generated {out['generated_utc']}. "
                    f"{out['reps']:,} one-year stationary-bootstrap paths per book; the same paths for every L. "
                    f"Ruin: {out['ruin_rule']}.", "", "## Read this first", ""]
    L += [f"- {c}" for c in out["caveats"]]
    for b in out["books"]:
        L += ["", f"## {b['book']} (`{b['venue']}`)", ""]
        if b["status"] != "OK":
            L += [f"**{b['status']}**"]
            continue
        st, go, ke = b["stream"], b["growth_optimal"], b["kelly_continuous_time"]
        L += [f"Base-cost net stream, {b['first_print'][:10]} → {b['last_print'][:10]}: {b['n_obs']:,} prints, annual return "
              f"{_p(st['ann_return'])}, volatility {_p(st['ann_vol'])}, Sharpe {_f(st['sharpe'])}, worst print {_p(st['worst_print'], 2)}. "
              f"Paths of {b['horizon_prints']} prints, mean block {b['block']:.0f}.", ""]
        L += _table(["L", "median wealth", "5th pct", "95th pct", "P(final < 0.5)", "P(ruin)", "of which single-print wipe-out",
                     "mean log wealth, survivors", "survivors", "actual history"],
                    [[f"{r['L']:g}", _f(r["median_wealth"], 3), _f(r["p05_wealth"], 3), _f(r["p95_wealth"], 3),
                      _p(r["p_final_below_half"]), _p(r["p_ruin"]), _p(r["p_ruin_single_print_loss"]),
                      _f(r["mean_log_wealth_survivors"], 3), f"{r['n_survivors']:,}",
                      f"ruined {str(r['actual_history_ruin_date'])[:10]}" if r["actual_history_ruined"] else "survives"]
                     for r in b["levels"]], "rrrrrrrrrl")
        best = b["best_L_by_median_log_wealth"]
        best_txt = "none — every median is zero" if best is None else f"{best:g}"
        flag = (" — at the grid cap" if go["at_grid_cap"] else "") + (" — no positive leverage grew this history" if go["L"] == 0 else "")
        wipe = go["single_print_wipe_out_leverage"]
        wipe_txt = "No print of the sample is negative." if wipe is None else f"A single print wipes the account from L = {wipe:,.1f}."
        L += ["", f"- L with the highest median log wealth on the ladder: **{best_txt}**.",
              f"- Full-sample growth-optimal L (in-sample): **{go['L']:.3f}**{flag}; mean log growth "
              f"{_p(go['mean_log_growth_per_print'] * b['periods_per_year'], 2)} a year. {wipe_txt}",
              f"- Continuous-time Kelly, mean / variance: **{_f(ke['L'], 2)}** (in-sample)."]
    x = out["btc_200x"]
    src = x["source"]
    L += ["", "## A 200× BTC position on hourly candles", "",
          (src["note"] if src.get("synthetic") else
           f"Binance USD-M BTCUSDT 1 h candles on disk ({src['files']}), every hourly open from {src['from']}: "
           f"{x['n_candles']:,} candles, {x['first_open_utc'][:16]} → {x['last_open_utc'][:16]} UTC, {x['missing_hourly_candles']} hourly "
           f"candles missing, {src['zero_trade_candles_dropped']} zero-trade candles dropped."),
          "", f"A long entered at an hourly open is liquidated when a candle's low is ≤ entry × (1 − d); a short when a high is ≥ "
          f"entry × (1 + d). The entry candle counts. {x['margin_note'][0].upper() + x['margin_note'][1:]}. Entries without 24 h of "
          f"data after them are left out.", ""]
    L += _table(["side", "adverse move d", "entries"] + [f"liquidated within {k} h" for k in LIQ_HORIZONS_H]
                + ["median hours to liquidation", "never in the data"],
                [[r["side"], _p(r["adverse_move"], 2), f"{r['n_entries']:,}"] + [_p(r[f"share_within_{k}h"]) for k in LIQ_HORIZONS_H]
                 + [_f(r["median_hours_to_liquidation"], 0), _p(r["share_never_liquidated_in_data"], 2)] for r in x["rows"]],
                "lrrrrrrr")
    L += ["", "Fees at 200× (notional = 200 × margin):", ""]
    L += _table(["fee per side", "round trip, % of margin", "price move needed to break even"],
                [[f"{f['fee_bp_per_side']:g} bp", f"{f['round_trip_fee_pct_of_margin']:.0f}%", f"{f['price_move_to_break_even_pct']:.2f}%"]
                 for f in x["fees"]], "rrr")
    e = out["eu_leverage"]
    caps = e["esma_retail_cfd_caps"] or {}
    L += ["", "## What leverage a Dutch retail account can actually get (venues.json)", "",
          f"- EU retail CFD caps ({e['rules_label']}, {e['rules_url']}): " + ", ".join(f"{k} {v}:1" for k, v in caps.items())
          + f"; margin close-out at {e['margin_close_out']}.",
          f"- Kraken Derivatives EEA: {e['kraken_eea_retail_cap']}× — {e['kraken_eea_detail']}.",
          f"- {e['perpetual_futures_note']}",
          f"- Highest cap of any venue in the file: {e['highest_cap_any_venue']['cap']:g}× (`{e['highest_cap_any_venue']['venue_id']}`)"
          + (f"; highest at a venue with an EU-authorised entity: {e['highest_cap_eu_entity']['cap']:g}× "
             f"(`{e['highest_cap_eu_entity']['venue_id']}`)." if e["highest_cap_eu_entity"] else "."),
          f"- **200× is {'recorded' if e['x200_available'] else 'not available'} at any venue in venues.json.** The 200× rows above "
          f"are arithmetic, not an account the owner can open at an EU-regulated venue.", ""]
    L += _table(["venue", "highest numeric cap", "EU entity claimed", "legal entity (venues.json)"],
                [[f"`{v['venue_id']}`", "–" if v["max_numeric_cap"] is None else f"{v['max_numeric_cap']:g}×",
                  "yes" if v["claims_eu_entity"] else "no", v["legal_entity"][:110]] for v in e["venues"]], "lrll")
    return "\n".join(L)


# ==================================================================================================
# CLI
# ==================================================================================================
def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="FACTORY v2 extras: prereg §6 realism pass and leverage ladder")
    ap.add_argument("stage", choices=["realism", "ladder"])
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--reps", type=int, default=LADDER_REPS, help="ladder: bootstrap paths per book")
    ap.add_argument("--offline", action="store_true", help="realism: never fetch; a venue without saved metadata is REFUSED")
    a = ap.parse_args(argv)
    if a.synthetic and not a.out:
        raise SystemExit("--synthetic needs --out <scratch dir>: a smoke test never writes into runs/v2")
    ctx = v2.Ctx(a.synthetic, a.out)
    if a.stage == "realism":
        stage_realism(ctx, allow_network=not a.offline)
    else:
        stage_ladder(ctx, a.reps)


if __name__ == "__main__":
    main()
