"""registry.py — the declared rule grid of DESIGN_v2 §4, the FX universes of §5 and the sixteen
primary ensembles of §6 (builder B2).

Nothing is discovered at run time: `ALL_RULES` is the complete, ordered list of formulas, and
`declared_counts()` states how many (rule x lane x universe) formulas that is, so the trial count of the
pre-registration is a declaration, not an observation.

    rules(lane, panel=None, include_disabled=False, families=None)
                                             the ENABLED rules of a lane (and, with a panel, only those
                                             whose required inputs the panel has)
    not_applicable(lane, panel)              the rules of the lane the panel cannot run, with the reason
    disabled_rules()                         rules kept in the library but excluded from every run
    fx_universes(panel) / universes(panel)   instrument lists per universe, from meta["universe_groups"]
    primaries() / primary_members(spec)      declarative specs of the 16 primaries and their CORE rules
    grid_manifest() / grid_sha256()          the whole declaration as JSON-able data, and its hash, for
                                             pinning in the pre-registration
    declared_counts(families_by_lane=None, lanes=None, universes_by_lane=None,
                    universes_by_lane_family=None)
                                             per lane / family / tier counts and formula totals, enabled
                                             and disabled reported separately, for any run filter

DISABLED RULES. A rule with `enabled=False` stays in `ALL_RULES` (its code and tests are kept) but is
skipped by `rules()`, `primary_members()` and the enabled side of `declared_counts()`; `disabled_reason`
says why. Conductor rulings of 2026-11-10: the SEASON family and the FLOW rule are already on this
repository's dead ledger; TREND.LINREG_T (x3) and REVERSAL.TS_Z.L20 duplicate other rules of the grid;
VALUE.XS_RET.L1260 cannot be assessed on its only lane. None of them is run.

LANE EXCLUSIONS. `LANE_EXCLUSIONS[rule_id][lane]` records, with the reason, every lane on which DESIGN
§4 declared a rule and a conductor ruling removed it (VOL.XS_LOWVOL off MACRO; the three ML rules on FX
only). The rule's `lanes` no longer contains those lanes.

A `Rule` is data plus a pure function: `rule.fn(panel, **rule.params)` returns a raw signal in [-1, 1]
(NaN = no view) that uses rows <= t only; sizing is `common.size_positions(signal, panel,
SIGMA_TARGET[lane])`, i.e. w_i = s_i * (sigma* / sigma_hat_i) / N_eligible. The FX universes are applied
by the CALLER through `panel.subset(...)`.

`requires` tokens (every token must hold; "|" separates alternatives inside one token):
    "carry"               panel.carry is not None
    "aux:<name>"          <name> in panel.aux
    "meta:<key>"          panel.meta[<key>] is present and non-empty
    "instrument:<name>"   <name> is a column of the panel
    "asset_class:<label>" some instrument's meta["asset_class_of"] label contains <label>
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import pandas as pd

from ..panel import PanelBundle
from . import common, rules_carry, rules_misc, rules_ml, rules_reversal, rules_trend, rules_value, rules_xs
from .common import NotApplicable

# --------------------------------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------------------------------
LANES: Tuple[str, ...] = ("FX", "FX-FRED", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT")
FX_LANES: Tuple[str, ...] = ("FX", "FX-FRED")
CRYPTO_LANES: Tuple[str, ...] = ("CRYPTO-PERP", "CRYPTO-SPOT")
#: lanes that have a Tier-2 design / sealed-holdout window in DESIGN §2 (FX-FRED is robustness only)
TIER2_LANES: Tuple[str, ...] = ("FX", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT")
FAMILIES: Tuple[str, ...] = ("TREND", "CARRY", "VALUE", "XSMOM", "REVERSAL", "VOL", "SEASON", "SKEW",
                             "XASSET", "FLOW", "ML")
TIERS: Tuple[str, ...] = ("CORE", "EXPLORATORY")
KINDS: Tuple[str, ...] = ("TS", "XS")
#: sizing volatility target sigma* per lane (DESIGN §3.7)
SIGMA_TARGET: Dict[str, float] = {"FX": 0.10, "FX-FRED": 0.10, "MACRO": 0.10,
                                  "CRYPTO-PERP": 0.20, "CRYPTO-SPOT": 0.20}
#: universes every rule of the lane is run on (DESIGN §5: every FX rule on G10 and on G10EM)
LANE_UNIVERSES: Dict[str, Tuple[str, ...]] = {"FX": ("G10", "G10EM"), "FX-FRED": ("G10",), "MACRO": ("ALL",),
                                              "CRYPTO-PERP": ("ALL",), "CRYPTO-SPOT": ("ALL",)}


#: Conductor ruling 2026-11-10 (after the repo audit): already on this repository's dead ledger.
SEASON_DISABLED = ("dead ledger — calendar effects were swept twice in 2026-08 (about 100 calendar formulas: "
                   "turn-of-month on equities / bonds, Halloween, crypto calendars; plus an FX month-end "
                   "hedge-rebalancing family) and judged noise: scripts/trading_bot/cal_sweep.py:361-379, "
                   "scripts/trading_bot/inv0822b_sweep.py family P. Not re-run (conductor ruling 2026-11-10).")
FLOW_DISABLED = ("dead ledger — the cross-sectional long/short account-ratio fade was about breakeven on "
                 "2025-01 -> 2026-08 after the data-hole fix, and the data layer does not download the metrics "
                 "files. Not re-run (conductor ruling 2026-11-10).")


LINREG_DISABLED = ("redundant: clip(t/3) of a level-on-time regression is sign(slope), 86-87 % agreement with "
                   "TSMOM sign on a random-walk null (conductor ruling 2026-11-10).")
REVERSAL_Z20_DISABLED = ("mirror of TREND.TSMOM_Z.L21 (corr -0.975 on a random-walk null): one two-sided test "
                         "counted twice (conductor ruling 2026-11-10).")
VALUE_RET_DISABLED = ("needs 1261 prints; about one design year on a 2016-start panel. MACRO was its only lane, so "
                      "removing it leaves the rule without a lane: disabled (conductor ruling 2026-11-10). It keeps "
                      "lanes=('MACRO',) only so that its code stays tested.")
_ML_LANES_REASON = "thin and slow on short lanes; >= 20 years needed (conductor ruling 2026-11-10)"
#: rule id -> {lane -> reason}: lanes of the DESIGN §4 grid from which a conductor ruling removed the rule
LANE_EXCLUSIONS: Dict[str, Dict[str, str]] = {
    "VOL.XS_LOWVOL.L252": {"MACRO": "a cross-asset-class vol sort: levered bonds vs commodities "
                                    "(conductor ruling 2026-11-10)"},
    **{rid: {lane: _ML_LANES_REASON for lane in ("FX-FRED", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT")}
       for rid in ("ML.GBC.D2", "ML.GBC.D4", "ML.RIDGE.A1")},
}


@dataclass(frozen=True)
class Rule:
    """One formula of the grid (DESIGN §3.7). `fn(panel, **params)` -> signal in [-1, 1], NaN = no view."""

    id: str            # "TREND.EWMAC.16_64"
    family: str        # TREND | CARRY | VALUE | XSMOM | REVERSAL | VOL | SEASON | SKEW | XASSET | FLOW | ML
    kind: str          # "TS" | "XS"
    tier: str          # "CORE" | "EXPLORATORY"
    fn: Callable       # fn(panel, **params) -> DataFrame signal in [-1, 1], NaN = no view; rows <= t only
    params: dict
    lanes: tuple       # lane ids where it applies
    requires: tuple    # e.g. ("carry",), ("aux:cpi",), ("aux:glsr",)
    description: str
    enabled: bool = True        # False: kept in the library, excluded from every run and count
    disabled_reason: str = ""   # why (dead ledger reference); empty for an enabled rule

    def signal(self, panel: PanelBundle) -> pd.DataFrame:
        """`self.fn(panel, **self.params)`."""
        return self.fn(panel, **self.params)

    def __hash__(self) -> int:  # params is a dict, so hash on the unique id
        return hash(self.id)


@dataclass(frozen=True)
class PrimarySpec:
    """Declarative spec of one primary ensemble (DESIGN §6). The portfolio maths is NOT here: the
    members are `primary_members(spec)` (CORE rules of `families` on `lane`), combined equal-risk within
    family and equal-risk across families by `portfolio.ensemble`, then `transforms` name the book-level
    steps IN ORDER OF APPLICATION (dict insertion order):
        "long_only": True        negative targets -> 0
        "vol_target": x          book volatility target (annualised)
        "max_gross": g           gross exposure cap applied with the vol target
        "buffer": b              no-trade band
        "rebalance": "monthly" | "weekly"   trade only on the first print of the period
        "equal_risk_of": (ids)   the book is the equal-risk combination of other primaries"""

    id: str
    lane: str
    universe: Optional[str]
    families: tuple
    transforms: dict

    def __hash__(self) -> int:
        return hash(self.id)


# --------------------------------------------------------------------------------------------------
# the grid (DESIGN §4), in table order
# --------------------------------------------------------------------------------------------------
def _build_rules() -> Tuple[Rule, ...]:
    core, expl = "CORE", "EXPLORATORY"
    out: List[Rule] = []

    def add(rule_id: str, family: str, kind: str, tier: str, fn: Callable, params: dict,
            lanes: Sequence[str], description: str, requires: Sequence[str] = (),
            disabled_reason: str = "") -> None:
        out.append(Rule(rule_id, family, kind, tier, fn, dict(params), tuple(lanes), tuple(requires), description,
                        enabled=not disabled_reason, disabled_reason=disabled_reason))

    idx = "the excess-return index X"

    # ---- TREND (27): CORE 20, EXPLORATORY 7 (LINREG_T x3 DISABLED) — all lanes -------------------
    for (fast, slow), scalar in rules_trend.EWMAC_SCALARS.items():
        add(f"TREND.EWMAC.{fast}_{slow}", "TREND", "TS", core, rules_trend.ewmac,
            {"fast": fast, "slow": slow, "scalar": scalar}, LANES,
            f"clip({scalar}*(EWMA_{fast}(X)-EWMA_{slow}(X))/sigma_X, +-20)/20 on {idx}; sigma_X = EW std "
            "(span 36) of the daily changes of X")
    for lb in (21, 63, 126, 252):
        add(f"TREND.TSMOM_SIGN.L{lb}", "TREND", "TS", core, rules_trend.tsmom_sign, {"lookback": lb}, LANES,
            f"sign of the {lb}-print excess return X_t/X_(t-{lb}) - 1")
    for lb in (21, 63, 126, 252):
        add(f"TREND.TSMOM_Z.L{lb}", "TREND", "TS", core, rules_trend.tsmom_z, {"lookback": lb}, LANES,
            f"clip(ret_{lb}/(sigma_daily*sqrt({lb})), +-2)/2, ret = excess-index return, sigma = vol_estimate")
    for lb in (20, 40, 80, 160, 320):
        add(f"TREND.BREAKOUT.L{lb}", "TREND", "TS", core, rules_trend.breakout, {"lookback": lb}, LANES,
            f"2*(X-mid_{lb})/(max_{lb}-min_{lb}) on {idx}, smoothed EWMA({lb // 4})")
    add("TREND.SMA_SIGN.200", "TREND", "TS", core, rules_trend.sma_sign, {"window": 200}, LANES,
        f"sign(X - SMA_200(X)) on {idx}")
    for lb in (20, 55, 100):
        add(f"TREND.DONCHIAN.L{lb}", "TREND", "TS", expl, rules_trend.donchian, {"lookback": lb}, LANES,
            f"Donchian stop-and-reverse on {idx}: +1 above the {lb}-print high, -1 below the {lb}-print "
            "low of the previous prints, held until the opposite breakout")
    for lb in (63, 126, 252):
        add(f"TREND.LINREG_T.L{lb}", "TREND", "TS", expl, rules_trend.linreg_slope_t, {"lookback": lb}, LANES,
            f"clip(t/3, +-1), t = OLS slope t-stat of ln X on time over {lb} prints",
            disabled_reason=LINREG_DISABLED)
    add("TREND.SMA_CROSS.50_200", "TREND", "TS", expl, rules_trend.sma_cross, {"fast": 50, "slow": 200}, LANES,
        f"sign(SMA_50(X) - SMA_200(X)) on {idx}")

    # ---- CARRY (10): CORE 8 on FX + FX-FRED, EXPLORATORY 2 on FX ---------------------------------
    carry_req = ("aux:rates|carry",)
    src = "annualised carry = rates[ccy] - rates[USD] (fallback: 5-print carry sum / days * 360)"
    for span in (1, 20, 60, 120):
        add(f"CARRY.TS.S{span}", "CARRY", "TS", core, rules_carry.carry_ts, {"span": span}, FX_LANES,
            f"clip(EWMA_{span}(carry_ann/sigma_hat), +-1); {src}", carry_req)
    for span in (1, 20):
        add(f"CARRY.XS_TERCILE.S{span}", "CARRY", "XS", core, rules_carry.carry_xs_tercile, {"span": span},
            FX_LANES, f"tercile on EWMA_{span}(annualised carry); {src}", carry_req)
    for span in (1, 20):
        add(f"CARRY.XS_LINEAR.S{span}", "CARRY", "XS", core, rules_carry.carry_xs_linear, {"span": span},
            FX_LANES, f"linear-rank weights on EWMA_{span}(annualised carry); {src}", carry_req)
    for lb in (63, 126):
        add(f"CARRY.XS_CHANGE.L{lb}", "CARRY", "XS", expl, rules_carry.carry_change_xs, {"lookback": lb},
            ("FX",), f"tercile on the change of the annualised carry over {lb} prints", carry_req)

    # ---- VALUE (8): CORE 7 on FX (the 4 nominal ones also FX-FRED), EXPLORATORY 1 (DISABLED) ------
    for lb in (756, 1260):
        add(f"VALUE.XS_NOMINAL.L{lb}", "VALUE", "XS", core, rules_value.value_xs_deviation,
            {"lookback": lb, "real": False}, FX_LANES,
            f"tercile on -(ln P - mean_{lb} ln P), P = spot price")
    for lb in (756, 1260):
        add(f"VALUE.XS_REAL.L{lb}", "VALUE", "XS", core, rules_value.value_xs_deviation,
            {"lookback": lb, "real": True}, ("FX",),
            f"tercile on -(q - mean_{lb} q), q = ln P + ln CPI_ccy - ln CPI_USD", ("aux:cpi",))
    for lb in (756, 1260):
        add(f"VALUE.TS_Z.L{lb}", "VALUE", "TS", core, rules_value.value_ts_z, {"lookback": lb}, FX_LANES,
            f"-z_{lb}(ln P): trailing z-score of the log spot price, clipped +-2, /2, negated")
    add("VALUE.XS_REAL_RET.L1260", "VALUE", "XS", core, rules_value.value_xs_long_return,
        {"lookback": 1260, "real": True}, ("FX",),
        "tercile on the negative 5-year (1260-print) change of the log real exchange rate", ("aux:cpi",))
    add("VALUE.XS_RET.L1260", "VALUE", "XS", expl, rules_value.value_xs_long_return,
        {"lookback": 1260, "real": False}, ("MACRO",),
        "tercile on the negative 5-year (1260-print) log return of the price",
        disabled_reason=VALUE_RET_DISABLED)

    # ---- XSMOM (9): CORE 7, EXPLORATORY 2 — all lanes --------------------------------------------
    for lb in (21, 63, 126, 252):
        add(f"XSMOM.TERCILE.L{lb}", "XSMOM", "XS", core, rules_xs.xsmom_tercile, {"lookback": lb, "skip": 0},
            LANES, f"tercile on the vol-scaled {lb}-print excess return (X_t/X_(t-{lb}) - 1)/(sigma_daily*sqrt({lb}))")
    add("XSMOM.TERCILE.L252_SKIP21", "XSMOM", "XS", core, rules_xs.xsmom_tercile, {"lookback": 252, "skip": 21},
        LANES, "tercile on the vol-scaled excess return from t-252 to t-21 (12-1 momentum): "
               "(X_(t-21)/X_(t-252) - 1)/(sigma_daily*sqrt(231))")
    for lb in (126, 252):
        add(f"XSMOM.LINEAR.L{lb}", "XSMOM", "XS", core, rules_xs.xsmom_linear, {"lookback": lb}, LANES,
            f"linear-rank weights on the vol-scaled {lb}-print excess return (X_t/X_(t-{lb}) - 1)/(sigma_daily*sqrt({lb}))")
    add("XSMOM.RESIDUAL.L252", "XSMOM", "XS", expl, rules_xs.residual_momentum, {"lookback": 252}, LANES,
        "tercile on the 252-print sum of (e_i - beta_i * basket), beta against the lane's equal-weight basket")
    add("XSMOM.HIGH_PROXIMITY.L252", "XSMOM", "XS", expl, rules_xs.high_proximity, {"lookback": 252}, LANES,
        f"tercile on X / max_252(X), proximity of {idx} to its 252-print high")

    # ---- REVERSAL (9): EXPLORATORY (TS_Z.L20 DISABLED) — all lanes -------------------------------
    for lb in (1, 5, 10):
        add(f"REVERSAL.XS_TERCILE.L{lb}", "REVERSAL", "XS", expl, rules_reversal.reversal_xs, {"lookback": lb},
            LANES, f"tercile on the NEGATIVE vol-scaled {lb}-print excess return -ret_{lb}/(sigma_daily*sqrt({lb})) "
                   "(long losers, short winners)")
    for lb in (5, 10, 20):
        add(f"REVERSAL.TS_Z.L{lb}", "REVERSAL", "TS", expl, rules_reversal.reversal_ts_z, {"lookback": lb},
            LANES, f"-clip(ret_{lb}/(sigma_daily*sqrt({lb})), +-2)/2 on {idx}",
            disabled_reason=REVERSAL_Z20_DISABLED if lb == 20 else "")
    add("REVERSAL.RSI.2_10_90", "REVERSAL", "TS", expl, rules_reversal.rsi_contrarian,
        {"n": 2, "low": 10.0, "high": 90.0}, LANES,
        f"Wilder RSI(2) of {idx}: +1 below 10, -1 above 90, flat between (stateless)")
    add("REVERSAL.RSI.14_30_70", "REVERSAL", "TS", expl, rules_reversal.rsi_contrarian,
        {"n": 14, "low": 30.0, "high": 70.0}, LANES,
        f"Wilder RSI(14) of {idx}: +1 below 30, -1 above 70, flat between (stateless)")
    add("REVERSAL.BOLLINGER.20_2", "REVERSAL", "TS", expl, rules_reversal.bollinger_reversion,
        {"window": 20, "width": 2.0}, LANES,
        f"Bollinger(20, 2 sigma) on {idx}: +1 below the lower band, -1 above the upper, flat inside (stateless)")

    # ---- VOL (3): EXPLORATORY — all lanes (XS_LOWVOL not on MACRO) -------------------------------
    add("VOL.MANAGED_BASKET.252_21", "VOL", "TS", expl, rules_misc.vol_managed_basket,
        {"long_window": 252, "short_window": 21}, LANES,
        "long-only basket, s = clip(0.5 * sigma_252 / sigma_21, 0, 1)")
    add("VOL.XS_LOWVOL.L252", "VOL", "XS", expl, rules_misc.low_vol_xs, {"lookback": 252},
        [lane for lane in LANES if lane != "MACRO"],                # LANE_EXCLUSIONS: not on MACRO
        "tercile on -sigma_252 (long the least volatile third)")
    add("VOL.BREAKOUT.5_60", "VOL", "TS", expl, rules_misc.vol_breakout,
        {"short_window": 5, "long_window": 60, "threshold": 1.5}, LANES,
        "sign of the 5-print excess return when sigma_5 / sigma_60 > 1.5, else flat")

    # ---- SEASON (5): EXPLORATORY — by lane — DISABLED (dead ledger) ------------------------------
    tom = "turn of the month (last 3 + first 2 decision prints)"
    add("SEASON.TOM.EQUITY", "SEASON", "TS", expl, rules_misc.turn_of_month,
        {"direction": 1.0, "asset_class": "equity"}, ("MACRO",), f"{tom}: long equities", ("asset_class:equity",),
        disabled_reason=SEASON_DISABLED)
    add("SEASON.TOM.LONG", "SEASON", "TS", expl, rules_misc.turn_of_month,
        {"direction": 1.0, "asset_class": None}, CRYPTO_LANES, f"{tom}: long every instrument",
        disabled_reason=SEASON_DISABLED)
    add("SEASON.TOM.LONG_USD", "SEASON", "TS", expl, rules_misc.turn_of_month,
        {"direction": -1.0, "asset_class": None}, ("FX",), f"{tom}: long USD (short every currency)",
        disabled_reason=SEASON_DISABLED)
    add("SEASON.TOM.SHORT_USD", "SEASON", "TS", expl, rules_misc.turn_of_month,
        {"direction": 1.0, "asset_class": None}, ("FX",), f"{tom}: short USD (the negation of LONG_USD)",
        disabled_reason=SEASON_DISABLED)
    add("SEASON.SELL_IN_MAY.EQUITY", "SEASON", "TS", expl, rules_misc.sell_in_may,
        {"asset_class": "equity"}, ("MACRO",), "long equities November-April, flat May-October",
        ("asset_class:equity",), disabled_reason=SEASON_DISABLED)

    # ---- SKEW (2): EXPLORATORY — all lanes -------------------------------------------------------
    add("SKEW.XS_LOW_MINUS_HIGH.L126", "SKEW", "XS", expl, rules_misc.skew_xs, {"lookback": 126}, LANES,
        "tercile on minus the 126-print skewness of excess returns (long low skew, short high skew)")
    add("SKEW.XS_MAX.L21", "SKEW", "XS", expl, rules_misc.max_return_xs, {"lookback": 21}, LANES,
        "tercile on minus the largest single excess return of the last 21 prints divided by sigma_daily "
        "(short the highest vol-scaled MAX)")

    # ---- XASSET (1), FLOW (1, DISABLED: dead ledger): EXPLORATORY --------------------------------
    add("XASSET.OIL_FX.L63", "XASSET", "TS", expl, rules_misc.oil_currencies,
        {"lookback": 63, "instruments": ("CAD", "NOK", "MXN")}, ("FX",),
        "oil currencies (CAD, NOK, MXN): sign of the trailing 63-print WTI return",
        ("aux:oil", "instrument:CAD|instrument:NOK|instrument:MXN"))
    add("FLOW.XS_GLSR_Z.L7", "FLOW", "XS", expl, rules_misc.glsr_fade, {"lookback": 7}, ("CRYPTO-PERP",),
        "tercile on -z of ln(global long/short account ratio) against its own 7 prints (reference leg)",
        ("aux:glsr",), disabled_reason=FLOW_DISABLED)

    # ---- ML (3): EXPLORATORY — FX only (LANE_EXCLUSIONS: thin and slow on the short lanes) -------
    feats = ("features {excess returns at 5/21/63/126/252; annualised carry; value z; vol}, target = forward "
             "21-print excess return, expanding fit with a 21-print purge, refit at the first print of each "
             "year, tercile on the score. Carry is a model FEATURE here (on a perp panel it would be the "
             "funding: a feature, not a re-run of the dead funding-carry strategy)")
    for depth in (2, 4):
        add(f"ML.GBC.D{depth}", "ML", "XS", expl, rules_ml.ml_xs, {"model": "gbc", "max_depth": depth}, ("FX",),
            f"gradient-boosting classifier (depth {depth}, 100 trees, lr 0.05, subsample 0.8) on the sign; {feats}",
            carry_req)
    add("ML.RIDGE.A1", "ML", "XS", expl, rules_ml.ml_xs, {"model": "ridge"}, ("FX",),
        f"ridge regression (alpha 1.0, standardised features) on the value; {feats}", carry_req)
    return tuple(out)


ALL_RULES: Tuple[Rule, ...] = _build_rules()
_BY_ID: Dict[str, Rule] = {r.id: r for r in ALL_RULES}


def _validate() -> None:
    if len(_BY_ID) != len(ALL_RULES):
        raise RuntimeError("duplicate rule ids in the registry")
    for r in ALL_RULES:
        if r.family not in FAMILIES or r.kind not in KINDS or r.tier not in TIERS:
            raise RuntimeError(f"{r.id}: unknown family / kind / tier")
        if not r.lanes or any(lane not in LANES for lane in r.lanes):
            raise RuntimeError(f"{r.id}: unknown lane")
        if not r.id.startswith(r.family + "."):
            raise RuntimeError(f"{r.id}: id must start with its family")
        if r.enabled == bool(r.disabled_reason):
            raise RuntimeError(f"{r.id}: a disabled rule needs a reason and an enabled rule must not have one")
    for rule_id, by_lane in LANE_EXCLUSIONS.items():
        if rule_id not in _BY_ID:
            raise RuntimeError(f"LANE_EXCLUSIONS names an unknown rule {rule_id}")
        for lane, reason in by_lane.items():
            if lane not in LANES or lane in _BY_ID[rule_id].lanes or not reason:
                raise RuntimeError(f"LANE_EXCLUSIONS[{rule_id}][{lane}] contradicts the rule's lanes")


_validate()


# --------------------------------------------------------------------------------------------------
# lookups
# --------------------------------------------------------------------------------------------------
def get(rule_id: str) -> Rule:
    """The rule with this id (KeyError if it is not in the grid)."""
    return _BY_ID[rule_id]


def _check_lane(lane: str) -> None:
    if lane not in LANES:
        raise ValueError(f"unknown lane {lane!r}; lanes are {LANES}")


def _token_holds(panel: PanelBundle, token: str) -> bool:
    for alt in token.split("|"):
        if alt == "carry":
            ok = panel.carry is not None
        elif alt.startswith("aux:"):
            ok = alt[4:] in panel.aux
        elif alt.startswith("meta:"):
            ok = bool(panel.meta.get(alt[5:]))
        elif alt.startswith("instrument:"):
            ok = alt[11:] in panel.prices.columns
        elif alt.startswith("asset_class:"):
            mapping = panel.meta.get("asset_class_of") or {}
            key = alt[12:].lower()
            ok = any(key in str(mapping.get(c, "")).lower() for c in panel.prices.columns)
        else:
            raise ValueError(f"unknown requirement token {alt!r}")
        if ok:
            return True
    return False


def missing_requirements(rule: Rule, panel: PanelBundle) -> Tuple[str, ...]:
    """The `requires` tokens of `rule` that `panel` does not satisfy (empty tuple = applicable)."""
    return tuple(tok for tok in rule.requires if not _token_holds(panel, tok))


def rules(lane: str, panel: Optional[PanelBundle] = None, include_disabled: bool = False,
          families: Optional[Iterable[str]] = None) -> List[Rule]:
    """The ENABLED rules declared for `lane`, in grid order; with `panel`, only those whose required
    inputs the panel has (the rest are reported by `not_applicable`); with `families`, only those
    families. `include_disabled=True` also returns the rules that are kept but not run."""
    _check_lane(lane)
    fams = None if families is None else set(families)
    out = [r for r in ALL_RULES if lane in r.lanes and (fams is None or r.family in fams)
           and (include_disabled or r.enabled)]
    if panel is not None:
        out = [r for r in out if not missing_requirements(r, panel)]
    return out


def disabled_rules() -> List[Rule]:
    """Rules kept in the library but excluded from every run, in grid order (`rule.disabled_reason`)."""
    return [r for r in ALL_RULES if not r.enabled]


def not_applicable(lane: str, panel: PanelBundle, include_disabled: bool = False) -> List[Tuple[Rule, str]]:
    """ENABLED rules declared for `lane` that CANNOT run on `panel`, each with the missing
    requirement(s). These must be ledgered as NOT APPLICABLE — never run with a fabricated input."""
    _check_lane(lane)
    out = []
    for r in rules(lane, include_disabled=include_disabled):
        miss = missing_requirements(r, panel)
        if miss:
            out.append((r, "missing " + ", ".join(miss)))
    return out


def sigma_target(lane: str) -> float:
    """sigma* of the lane for `common.size_positions` (0.10 FX / MACRO, 0.20 CRYPTO)."""
    _check_lane(lane)
    return SIGMA_TARGET[lane]


# --------------------------------------------------------------------------------------------------
# universes (DESIGN §5)
# --------------------------------------------------------------------------------------------------
def fx_universes(panel: PanelBundle) -> Dict[str, List[str]]:
    """{"G10": [...], "G10EM": G10 + EM} read from `panel.meta["universe_groups"]` ({"G10": [...],
    "EM": [...]}). "G10EM" is present only when the panel declares a non-empty "EM" group (FX-FRED has
    none). Apply with `panel.subset(cols)`.
    Raises `NotApplicable` if there is no "G10" group and `ValueError` if a group names an instrument
    the panel does not have (a silent drop would change the universe)."""
    groups = panel.meta.get("universe_groups") or {}
    if "G10" not in groups:
        raise NotApplicable("meta['universe_groups'] must contain a 'G10' group")
    g10 = list(groups["G10"])
    out = {"G10": g10}
    em = [c for c in groups.get("EM", []) if c not in g10]
    if em:
        out["G10EM"] = g10 + em
    have = set(panel.prices.columns)
    missing = sorted({c for cols in out.values() for c in cols if c not in have})
    if missing:
        raise ValueError(f"universe_groups names instruments that are not in the panel: {missing}")
    return out


def universes(panel: PanelBundle) -> Dict[str, List[str]]:
    """Universes of any lane's panel: `fx_universes(panel)` when the panel declares a "G10" group, else
    {"ALL": every column}."""
    if "G10" in (panel.meta.get("universe_groups") or {}):
        return fx_universes(panel)
    return {"ALL": list(panel.prices.columns)}


# --------------------------------------------------------------------------------------------------
# primaries (DESIGN §6)
# --------------------------------------------------------------------------------------------------
def primaries() -> List[PrimarySpec]:
    """The sixteen primary ensembles, declaratively. CORE members only (`primary_members`), equal-risk
    within family, families equal-risk; `transforms` are the book-level steps in order of application."""
    fx = {"vol_target": 0.10, "buffer": 0.10}
    macro = {"vol_target": 0.10, "buffer": 0.10}
    crypto = {"vol_target": 0.20, "buffer": 0.10}
    four = ("TREND", "CARRY", "VALUE", "XSMOM")
    two = ("TREND", "XSMOM")
    return [
        PrimarySpec("P.FX.G10.TREND", "FX", "G10", ("TREND",), dict(fx)),
        PrimarySpec("P.FX.G10.CARRY", "FX", "G10", ("CARRY",), dict(fx)),
        PrimarySpec("P.FX.G10.VALUE", "FX", "G10", ("VALUE",), dict(fx)),
        PrimarySpec("P.FX.G10.XSMOM", "FX", "G10", ("XSMOM",), dict(fx)),
        PrimarySpec("P.FX.G10.ALL", "FX", "G10", four, dict(fx)),
        PrimarySpec("P.FX.G10EM.CARRY", "FX", "G10EM", ("CARRY",), dict(fx)),
        PrimarySpec("P.FX.G10EM.ALL", "FX", "G10EM", four, dict(fx)),
        PrimarySpec("P.MACRO.TREND", "MACRO", "ALL", ("TREND",), dict(macro)),
        PrimarySpec("P.MACRO.XSMOM", "MACRO", "ALL", ("XSMOM",), dict(macro)),
        PrimarySpec("P.MACRO.ALL", "MACRO", "ALL", two, dict(macro)),
        PrimarySpec("P.MACRO.LO_TREND", "MACRO", "ALL", ("TREND",),
                    {"long_only": True, "vol_target": 0.10, "max_gross": 1.0, "rebalance": "monthly"}),
        PrimarySpec("P.CRYPTO.TREND", "CRYPTO-PERP", "ALL", ("TREND",), dict(crypto)),
        PrimarySpec("P.CRYPTO.XSMOM", "CRYPTO-PERP", "ALL", ("XSMOM",), dict(crypto)),
        PrimarySpec("P.CRYPTO.ALL", "CRYPTO-PERP", "ALL", two, dict(crypto)),
        PrimarySpec("P.CRYPTO.LO_TREND", "CRYPTO-SPOT", "ALL", ("TREND",),
                    {"long_only": True, "vol_target": 0.20, "max_gross": 1.0, "rebalance": "weekly"}),
        PrimarySpec("P.GLOBAL", "GLOBAL", None, (),
                    {"equal_risk_of": ("P.FX.G10.ALL", "P.MACRO.ALL", "P.CRYPTO.ALL"), "vol_target": 0.10}),
    ]


def primary_members(spec: Union[PrimarySpec, str], panel: Optional[PanelBundle] = None) -> Tuple[Rule, ...]:
    """The CORE rules of a primary: tier CORE, enabled, family in `spec.families`, declared for
    `spec.lane`, in grid order. A composite primary (P.GLOBAL, `transforms["equal_risk_of"]`) has no
    rules of its own.
    With `panel` (the lane's panel, already subset to `spec.universe`), raises `NotApplicable` if ANY
    member cannot run on it: a primary is one fully specified book, and a book with a member missing
    is a different book — it must fail visibly, not shrink silently."""
    if isinstance(spec, str):
        by_id = {p.id: p for p in primaries()}
        spec = by_id[spec]
    members = tuple(r for r in ALL_RULES
                    if r.enabled and r.tier == "CORE" and r.family in spec.families and spec.lane in r.lanes)
    if panel is not None:
        broken = {r.id: missing_requirements(r, panel) for r in members if missing_requirements(r, panel)}
        if broken:
            raise NotApplicable(f"{spec.id}: members cannot run on this panel: {broken}")
    return members


# --------------------------------------------------------------------------------------------------
# manifest (for pinning the declaration in a pre-registration)
# --------------------------------------------------------------------------------------------------
def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def grid_manifest(include_sources: bool = True) -> dict:
    """The whole declaration as JSON-serialisable data: every rule (id, family, kind, tier, function,
    params, lanes, requires, enabled, disabled_reason), every primary with its member ids, the
    universes and sizing targets per lane, the tie rule, the declared counts and — with
    `include_sources` — the sha256 of every source file of this package, so that a pin covers the
    implementation as well as the declaration."""
    out = {
        "rules": [{"id": r.id, "family": r.family, "kind": r.kind, "tier": r.tier,
                   "fn": f"{r.fn.__module__}.{r.fn.__name__}", "params": _jsonable(r.params),
                   "lanes": list(r.lanes), "requires": list(r.requires), "enabled": r.enabled,
                   "disabled_reason": r.disabled_reason, "description": r.description} for r in ALL_RULES],
        "primaries": [{"id": p.id, "lane": p.lane, "universe": p.universe, "families": list(p.families),
                       "transforms": _jsonable(p.transforms), "members": [m.id for m in primary_members(p)]}
                      for p in primaries()],
        "lane_universes": _jsonable(LANE_UNIVERSES),
        "lane_exclusions": _jsonable(LANE_EXCLUSIONS),
        "sizing": "w_i = s_i * (sigma_target / sigma_hat_i) / N_eligible, |w_i| <= 1",
        "sigma_target": dict(SIGMA_TARGET),
        "tier2_lanes": list(TIER2_LANES),
        "xs_ties": common.DEFAULT_TIES,
        "declared_counts": _jsonable(declared_counts()),
    }
    if include_sources:
        here = Path(__file__).resolve().parent
        out["source_sha256"] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(here.glob("*.py"))}
    return out


def grid_sha256(include_sources: bool = True) -> str:
    """sha256 of `grid_manifest()` in canonical JSON (sorted keys, no whitespace)."""
    blob = json.dumps(grid_manifest(include_sources), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------
# declared counts
# --------------------------------------------------------------------------------------------------
def _tally(rs: Sequence[Rule]) -> dict:
    by_family = {f: sum(r.family == f for r in rs) for f in FAMILIES}
    by_tier = {t: sum(r.tier == t for r in rs) for t in TIERS}
    by_family_tier = {f: {t: sum(r.family == f and r.tier == t for r in rs) for t in TIERS} for f in FAMILIES}
    return {"by_family": {f: n for f, n in by_family.items() if n},
            "by_tier": by_tier,
            "by_family_tier": {f: d for f, d in by_family_tier.items() if by_family[f]}}


def declared_counts(families_by_lane: Optional[Mapping[str, Iterable[str]]] = None,
                    lanes: Optional[Iterable[str]] = None,
                    universes_by_lane: Optional[Mapping[str, Iterable[str]]] = None,
                    universes_by_lane_family: Optional[Mapping[str, Mapping[str, Iterable[str]]]] = None) -> dict:
    """Declared size of the grid: distinct rules, and (rule x lane x universe) formulas — ENABLED rules
    at the top level, DISABLED rules (kept, never run) separately under "disabled".

    Filters (all optional, all combinable; none changes the registry):
    * `families_by_lane`  which families are RUN on a lane, e.g. `{"CRYPTO-SPOT": ("TREND", "XSMOM")}`;
      a lane that is not a key is counted in full, a lane mapped to an empty collection contributes
      nothing;
    * `lanes`             the lanes that are counted at all, e.g. `registry.TIER2_LANES`;
    * `universes_by_lane` the universes a lane is run on (default `LANE_UNIVERSES`, i.e. DESIGN §5: FX
      on G10 and G10EM, every other lane on one universe), e.g. `{"FX-FRED": ("G10", "G10EM")}`;
    * `universes_by_lane_family`  the universes ONE FAMILY is run on within a lane, a subset of the
      lane's universes, e.g. `{"FX": {"ML": ("G10",)}}` (ML on FX-G10 only). A family mapped to an empty
      collection is not run on that lane.

    Returns
        rules_total, rules_by_family, rules_by_tier, rules_by_family_tier   distinct ENABLED rules that
                                                                            run on at least one lane
        lanes[lane] = {universes, n_universes, rules, formulas, formulas_by_universe, by_family,
                       by_tier, by_family_tier, disabled_rules, disabled_formulas,
                       disabled_by_family_tier}
                      (by_* count enabled RULES of the lane; formulas = sum over those rules of the
                      number of universes each is run on)
        formulas_total, formulas_by_tier, formulas_by_family                enabled, over the counted lanes
        formulas_tier2_lanes                                                enabled, over `TIER2_LANES`
        disabled = {rules_total, rules_by_family, rules: {id: reason}, formulas_total,
                    formulas_tier2_lanes, formulas_by_lane}                 same filter, disabled rules
        including_disabled = {rules_total, formulas_total, formulas_tier2_lanes}
        lane_exclusions                                                     `LANE_EXCLUSIONS`
        primaries                                                           16
        filter                                                              the restriction applied"""
    if lanes is not None:
        unknown = set(lanes) - set(LANES)
        if unknown:
            raise ValueError(f"unknown lanes {sorted(unknown)}")
    counted = list(LANES) if lanes is None else [ln for ln in LANES if ln in set(lanes)]
    flt = {} if families_by_lane is None else {k: tuple(v) for k, v in families_by_lane.items()}
    for lane, fams in flt.items():
        _check_lane(lane)
        bad = set(fams) - set(FAMILIES)
        if bad:
            raise ValueError(f"unknown families {sorted(bad)} for lane {lane}")
    uni = {k: tuple(v) for k, v in LANE_UNIVERSES.items()}
    for lane, names in (universes_by_lane or {}).items():
        _check_lane(lane)
        uni[lane] = tuple(names)
    fam_uni: Dict[str, Dict[str, Tuple[str, ...]]] = {}
    for lane, by_family in (universes_by_lane_family or {}).items():
        _check_lane(lane)
        for family, names in by_family.items():
            names = tuple(names)
            if family not in FAMILIES:
                raise ValueError(f"unknown family {family!r} for lane {lane}")
            extra = [n for n in names if n not in uni[lane]]
            if extra:
                raise ValueError(f"{lane}/{family}: {extra} are not universes of the lane {list(uni[lane])}")
            fam_uni.setdefault(lane, {})[family] = names

    def run_on(rule: Rule, lane: str) -> Tuple[str, ...]:
        return fam_uni.get(lane, {}).get(rule.family, uni[lane])

    per_lane: Dict[str, dict] = {}
    on_ids: Dict[str, Rule] = {}
    off_ids: Dict[str, Rule] = {}
    formulas_by_tier = {t: 0 for t in TIERS}
    formulas_by_family = {f: 0 for f in FAMILIES}
    off_formulas_by_lane: Dict[str, int] = {}
    for lane in counted:
        declared = [(r, run_on(r, lane))
                    for r in rules(lane, include_disabled=True, families=flt[lane] if lane in flt else None)]
        declared = [(r, u) for r, u in declared if u]            # no universe on this lane: not run here
        on = [(r, u) for r, u in declared if r.enabled]
        off = [(r, u) for r, u in declared if not r.enabled]
        by_universe = {name: sum(name in u for _, u in on) for name in uni[lane]}
        per_lane[lane] = {"universes": list(uni[lane]), "n_universes": len(uni[lane]),
                          "rules": len(on), "formulas": sum(len(u) for _, u in on),
                          "formulas_by_universe": by_universe, **_tally([r for r, _ in on]),
                          "disabled_rules": len(off), "disabled_formulas": sum(len(u) for _, u in off),
                          "disabled_by_family_tier": _tally([r for r, _ in off])["by_family_tier"]}
        off_formulas_by_lane[lane] = sum(len(u) for _, u in off)
        for r, u in on:
            formulas_by_tier[r.tier] += len(u)
            formulas_by_family[r.family] += len(u)
            on_ids.setdefault(r.id, r)
        for r, _ in off:
            off_ids.setdefault(r.id, r)
    running = [r for r in ALL_RULES if r.id in on_ids]
    parked = [r for r in ALL_RULES if r.id in off_ids]
    tally = _tally(running)
    formulas_total = sum(v["formulas"] for v in per_lane.values())
    formulas_tier2 = sum(v["formulas"] for ln, v in per_lane.items() if ln in TIER2_LANES)
    off_total = sum(off_formulas_by_lane.values())
    off_tier2 = sum(n for ln, n in off_formulas_by_lane.items() if ln in TIER2_LANES)
    return {
        "rules_total": len(running),
        "rules_by_family": tally["by_family"],
        "rules_by_tier": tally["by_tier"],
        "rules_by_family_tier": tally["by_family_tier"],
        "lanes": per_lane,
        "formulas_total": formulas_total,
        "formulas_by_tier": formulas_by_tier,
        "formulas_by_family": {f: n for f, n in formulas_by_family.items() if n},
        "formulas_tier2_lanes": formulas_tier2,
        "tier2_lanes": [ln for ln in counted if ln in TIER2_LANES],
        "disabled": {
            "rules_total": len(parked),
            "rules_by_family": _tally(parked)["by_family"],
            "rules": {r.id: r.disabled_reason for r in parked},
            "formulas_total": off_total,
            "formulas_tier2_lanes": off_tier2,
            "formulas_by_lane": {ln: n for ln, n in off_formulas_by_lane.items() if n},
        },
        "including_disabled": {"rules_total": len(running) + len(parked),
                               "formulas_total": formulas_total + off_total,
                               "formulas_tier2_lanes": formulas_tier2 + off_tier2},
        "lane_exclusions": {rid: dict(by_lane) for rid, by_lane in LANE_EXCLUSIONS.items()},
        "primaries": len(primaries()),
        "filter": {"families_by_lane": flt or None, "lanes": None if lanes is None else counted,
                   "universes_by_lane": {k: list(v) for k, v in (universes_by_lane or {}).items()} or None,
                   "universes_by_lane_family": {ln: {f: list(u) for f, u in d.items()}
                                                for ln, d in fam_uni.items()} or None},
    }
