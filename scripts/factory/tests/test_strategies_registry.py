"""The registry (builder B2): the declared grid of DESIGN_v2 §4 as amended by the conductor rulings of
2026-11-10, the universes of §5, the sixteen primaries of §6, applicability and the declared counts.

The expected counts are NOT read back from the registry. `TABLE` below is a row-by-row transcription of
the §4 table (family, tier, number of rules, lanes); `EXPECTED_IDS` is the id list in the same order;
`DISABLED` and `LANES_REMOVED` transcribe the rulings. Per-lane / per-family / per-tier numbers are
derived from those here and compared with what the registry declares.
"""
from __future__ import annotations

import dataclasses
import inspect
import subprocess
import sys
from collections import Counter

import pytest

from scripts.factory.strategies import common as C
from scripts.factory.strategies import registry as R
from scripts.factory.tests.test_strategies_synth import EM, G10, lane_panel, mini_panel

ALL = ("FX", "FX-FRED", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT")
FXL = ("FX", "FX-FRED")
CRYPTO = ("CRYPTO-PERP", "CRYPTO-SPOT")
CORE, EXPL = "CORE", "EXPLORATORY"

# (family, tier, number of rules, lanes) — DESIGN_v2 §4, in table order
TABLE = [
    ("TREND", CORE, 6, ALL),              # EWMAC (2,8) .. (64,256)
    ("TREND", CORE, 4, ALL),              # TSMOM sign, L in {21,63,126,252}
    ("TREND", CORE, 4, ALL),              # TSMOM z, same L
    ("TREND", CORE, 5, ALL),              # continuous breakout, L in {20,40,80,160,320}
    ("TREND", CORE, 1, ALL),              # sign(P - SMA_200)
    ("TREND", EXPL, 3, ALL),              # Donchian L in {20,55,100}
    ("TREND", EXPL, 3, ALL),              # regression-slope t-stat L in {63,126,252}
    ("TREND", EXPL, 1, ALL),              # sign(SMA_50 - SMA_200)
    ("CARRY", CORE, 4, FXL),              # TS, smoothing {1,20,60,120}
    ("CARRY", CORE, 2, FXL),              # XS tercile, smoothing {1,20}
    ("CARRY", CORE, 2, FXL),              # XS linear rank, smoothing {1,20}
    ("CARRY", EXPL, 2, ("FX",)),          # XS on the change of carry, L in {63,126}
    ("VALUE", CORE, 2, FXL),              # XS tercile nominal, L in {756,1260}
    ("VALUE", CORE, 2, ("FX",)),          # the same on the CPI-deflated rate
    ("VALUE", CORE, 2, FXL),              # TS -z_L(ln P)  (nominal)
    ("VALUE", CORE, 1, ("FX",)),          # XS negative 5-year REAL return
    ("VALUE", EXPL, 1, ("MACRO",)),       # XS negative 5-year return
    ("XSMOM", CORE, 4, ALL),              # tercile L in {21,63,126,252}
    ("XSMOM", CORE, 1, ALL),              # 252 skipping 21
    ("XSMOM", CORE, 2, ALL),              # linear rank L in {126,252}
    ("XSMOM", EXPL, 1, ALL),              # residual momentum
    ("XSMOM", EXPL, 1, ALL),              # proximity to the 252-print high
    ("REVERSAL", EXPL, 3, ALL),           # XS tercile L in {1,5,10}
    ("REVERSAL", EXPL, 3, ALL),           # TS -z L in {5,10,20}
    ("REVERSAL", EXPL, 2, ALL),           # RSI(2) 10/90, RSI(14) 30/70
    ("REVERSAL", EXPL, 1, ALL),           # Bollinger(20, 2 sigma)
    ("VOL", EXPL, 1, ALL),                # vol-managed long-only basket
    ("VOL", EXPL, 1, ALL),                # XS low-vol tercile
    ("VOL", EXPL, 1, ALL),                # vol breakout
    ("SEASON", EXPL, 1, ("MACRO",)),      # turn of month: MACRO long equities
    ("SEASON", EXPL, 1, CRYPTO),          # turn of month: CRYPTO long
    ("SEASON", EXPL, 2, ("FX",)),         # turn of month: FX long USD and its negation
    ("SEASON", EXPL, 1, ("MACRO",)),      # sell in May on equities
    ("SKEW", EXPL, 1, ALL),               # low-minus-high 126-print skewness
    ("SKEW", EXPL, 1, ALL),               # short the highest 21-print max return
    ("XASSET", EXPL, 1, ("FX",)),         # oil currencies
    ("FLOW", EXPL, 1, ("CRYPTO-PERP",)),  # global long/short account ratio
    ("ML", EXPL, 3, ALL),                 # GBC depth 2, GBC depth 4, ridge
]
UNIVERSES = {"FX": 2, "FX-FRED": 1, "MACRO": 1, "CRYPTO-PERP": 1, "CRYPTO-SPOT": 1}      # §5

# Conductor rulings of 2026-11-10 on the §4 grid (the code and the tests of every rule are kept)
DISABLED = {
    # already on the repository's dead ledger
    "SEASON.TOM.EQUITY": "dead ledger", "SEASON.TOM.LONG": "dead ledger", "SEASON.TOM.LONG_USD": "dead ledger",
    "SEASON.TOM.SHORT_USD": "dead ledger", "SEASON.SELL_IN_MAY.EQUITY": "dead ledger",
    "FLOW.XS_GLSR_Z.L7": "dead ledger",
    # duplicates of other rules of the grid
    "TREND.LINREG_T.L63": "redundant", "TREND.LINREG_T.L126": "redundant", "TREND.LINREG_T.L252": "redundant",
    "REVERSAL.TS_Z.L20": "mirror of TREND.TSMOM_Z.L21",
    # MACRO was its only lane and it cannot be assessed there
    "VALUE.XS_RET.L1260": "1261 prints",
}
NOT_FX = ("FX-FRED", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT")
LANES_REMOVED = {
    "VOL.XS_LOWVOL.L252": ("MACRO",),                     # a cross-asset-class volatility sort
    "ML.GBC.D2": NOT_FX, "ML.GBC.D4": NOT_FX, "ML.RIDGE.A1": NOT_FX,      # thin and slow on short lanes
}

EXPECTED_IDS = [
    "TREND.EWMAC.2_8", "TREND.EWMAC.4_16", "TREND.EWMAC.8_32", "TREND.EWMAC.16_64", "TREND.EWMAC.32_128",
    "TREND.EWMAC.64_256",
    "TREND.TSMOM_SIGN.L21", "TREND.TSMOM_SIGN.L63", "TREND.TSMOM_SIGN.L126", "TREND.TSMOM_SIGN.L252",
    "TREND.TSMOM_Z.L21", "TREND.TSMOM_Z.L63", "TREND.TSMOM_Z.L126", "TREND.TSMOM_Z.L252",
    "TREND.BREAKOUT.L20", "TREND.BREAKOUT.L40", "TREND.BREAKOUT.L80", "TREND.BREAKOUT.L160", "TREND.BREAKOUT.L320",
    "TREND.SMA_SIGN.200",
    "TREND.DONCHIAN.L20", "TREND.DONCHIAN.L55", "TREND.DONCHIAN.L100",
    "TREND.LINREG_T.L63", "TREND.LINREG_T.L126", "TREND.LINREG_T.L252",
    "TREND.SMA_CROSS.50_200",
    "CARRY.TS.S1", "CARRY.TS.S20", "CARRY.TS.S60", "CARRY.TS.S120",
    "CARRY.XS_TERCILE.S1", "CARRY.XS_TERCILE.S20", "CARRY.XS_LINEAR.S1", "CARRY.XS_LINEAR.S20",
    "CARRY.XS_CHANGE.L63", "CARRY.XS_CHANGE.L126",
    "VALUE.XS_NOMINAL.L756", "VALUE.XS_NOMINAL.L1260", "VALUE.XS_REAL.L756", "VALUE.XS_REAL.L1260",
    "VALUE.TS_Z.L756", "VALUE.TS_Z.L1260", "VALUE.XS_REAL_RET.L1260", "VALUE.XS_RET.L1260",
    "XSMOM.TERCILE.L21", "XSMOM.TERCILE.L63", "XSMOM.TERCILE.L126", "XSMOM.TERCILE.L252",
    "XSMOM.TERCILE.L252_SKIP21", "XSMOM.LINEAR.L126", "XSMOM.LINEAR.L252",
    "XSMOM.RESIDUAL.L252", "XSMOM.HIGH_PROXIMITY.L252",
    "REVERSAL.XS_TERCILE.L1", "REVERSAL.XS_TERCILE.L5", "REVERSAL.XS_TERCILE.L10",
    "REVERSAL.TS_Z.L5", "REVERSAL.TS_Z.L10", "REVERSAL.TS_Z.L20",
    "REVERSAL.RSI.2_10_90", "REVERSAL.RSI.14_30_70", "REVERSAL.BOLLINGER.20_2",
    "VOL.MANAGED_BASKET.252_21", "VOL.XS_LOWVOL.L252", "VOL.BREAKOUT.5_60",
    "SEASON.TOM.EQUITY", "SEASON.TOM.LONG", "SEASON.TOM.LONG_USD", "SEASON.TOM.SHORT_USD",
    "SEASON.SELL_IN_MAY.EQUITY",
    "SKEW.XS_LOW_MINUS_HIGH.L126", "SKEW.XS_MAX.L21",
    "XASSET.OIL_FX.L63", "FLOW.XS_GLSR_Z.L7",
    "ML.GBC.D2", "ML.GBC.D4", "ML.RIDGE.A1",
]


def _design_spec():
    """{rule id: (family, tier, lanes)} of DESIGN §4: TABLE expanded over EXPECTED_IDS (same order)."""
    out, ids = {}, iter(EXPECTED_IDS)
    for family, tier, n, lanes in TABLE:
        for _ in range(n):
            rule_id = next(ids)
            assert rule_id.startswith(family + "."), (rule_id, family)
            out[rule_id] = (family, tier, tuple(lanes))
    assert next(ids, None) is None
    return out


DESIGN = _design_spec()
#: the grid after the rulings: {rule id: (family, tier, lanes, enabled)}
RULED = {rid: (fam, tier, tuple(ln for ln in lanes if ln not in LANES_REMOVED.get(rid, ())), rid not in DISABLED)
         for rid, (fam, tier, lanes) in DESIGN.items()}


def expected_ids(lane, enabled=True, families=None, spec=None):
    """Rule ids expected on `lane` (enabled only / disabled only / both when `enabled` is None)."""
    spec = RULED if spec is None else spec
    return [rid for rid, (fam, _tier, lanes, on) in spec.items()
            if lane in lanes and (enabled is None or on == enabled) and (families is None or fam in families)]


def table_counts(lane=None, enabled=True, families=None):
    """Counter of (family, tier) -> rules after the rulings, for one lane (or distinct rules if None)."""
    out = Counter()
    for rid, (fam, tier, lanes, on) in RULED.items():
        if (enabled is None or on == enabled) and (families is None or fam in families) \
                and (lanes if lane is None else lane in lanes):
            out[(fam, tier)] += 1
    return out


def test_the_design_table_itself_adds_up():
    """§4 as written: 78 rules, 376 (rule x lane x universe) formulas, 311 on the Tier-2 lanes."""
    assert len(DESIGN) == sum(n for _, _, n, _ in TABLE) == 78
    per_lane = {lane: sum(lane in lanes for _, _, lanes in DESIGN.values()) for lane in ALL}
    assert per_lane == {"FX": 73, "FX-FRED": 65, "MACRO": 56, "CRYPTO-PERP": 55, "CRYPTO-SPOT": 54}
    assert sum(per_lane[ln] * UNIVERSES[ln] for ln in ALL) == 376
    assert sum(per_lane[ln] * UNIVERSES[ln] for ln in ALL if ln != "FX-FRED") == 311
    # the rulings remove 13 (rule, lane) pairs and disable 11 rules
    assert sum(len(v) for v in LANES_REMOVED.values()) == 13 and len(DISABLED) == 11


# --------------------------------------------------------------------------------------------------
# the Rule object and the id list
# --------------------------------------------------------------------------------------------------
def test_rule_dataclass_is_the_design_contract_plus_the_enable_switch():
    names = [f.name for f in dataclasses.fields(R.Rule)]
    assert names == ["id", "family", "kind", "tier", "fn", "params", "lanes", "requires", "description",
                     "enabled", "disabled_reason"]
    rule = R.get("TREND.EWMAC.16_64")
    assert (rule.family, rule.kind, rule.tier) == ("TREND", "TS", "CORE")
    assert rule.params == {"fast": 16, "slow": 64, "scalar": 3.75} and rule.enabled and rule.disabled_reason == ""
    assert isinstance(rule.lanes, tuple) and isinstance(rule.requires, tuple) and isinstance(rule.params, dict)
    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.tier = "EXPLORATORY"
    assert len({r for r in R.ALL_RULES}) == len(R.ALL_RULES)        # hashable (by id)
    with pytest.raises(KeyError):
        R.get("TREND.EWMAC.3_9")


def test_rule_ids_are_stable_unique_and_in_grid_order():
    assert [r.id for r in R.ALL_RULES] == EXPECTED_IDS
    assert len(EXPECTED_IDS) == len(set(EXPECTED_IDS)) == 78
    for r in R.ALL_RULES:
        assert r.id.split(".")[0] == r.family and r.kind in ("TS", "XS") and r.tier in (CORE, EXPL)
        assert r.description and callable(r.fn) and r.lanes and set(r.lanes) <= set(ALL)


def test_every_rule_function_accepts_its_declared_parameters():
    for r in R.ALL_RULES:
        sig = inspect.signature(r.fn)
        bound = sig.bind("panel", **r.params)                       # raises TypeError on a wrong keyword
        assert list(bound.arguments)[0] == "panel", r.id
        assert r.fn.__doc__ and r.fn.__module__.startswith("scripts.factory.strategies.rules_"), r.id


def test_ewmac_scalars_and_cap_are_the_design_table():
    expected = {(2, 8): 10.6, (4, 16): 7.5, (8, 32): 5.3, (16, 64): 3.75, (32, 128): 2.65, (64, 256): 1.87}
    from scripts.factory.strategies import rules_trend
    assert rules_trend.EWMAC_SCALARS == expected and rules_trend.EWMAC_CAP == 20.0 and rules_trend.EWMAC_VOL_SPAN == 36
    for (fast, slow), scalar in expected.items():
        assert R.get(f"TREND.EWMAC.{fast}_{slow}").params["scalar"] == scalar


def test_kinds_and_requirements():
    xs = {r.id for r in R.ALL_RULES if r.kind == "XS"}
    assert all(i.split(".")[1].startswith("XS") or i.startswith(("XSMOM.", "ML.")) for i in xs)
    assert {r.family for r in R.ALL_RULES if r.kind == "XS"} == {"CARRY", "VALUE", "XSMOM", "REVERSAL", "VOL",
                                                                 "SKEW", "FLOW", "ML"}
    req = {r.id: r.requires for r in R.ALL_RULES if r.requires}
    assert {i for i in req if req[i] == ("aux:rates|carry",)} == {r.id for r in R.ALL_RULES if r.family in ("CARRY", "ML")}
    assert {i for i in req if req[i] == ("aux:cpi",)} == {"VALUE.XS_REAL.L756", "VALUE.XS_REAL.L1260",
                                                          "VALUE.XS_REAL_RET.L1260"}
    assert req["XASSET.OIL_FX.L63"] == ("aux:oil", "instrument:CAD|instrument:NOK|instrument:MXN")
    assert req["FLOW.XS_GLSR_Z.L7"] == ("aux:glsr",)
    assert req["SEASON.TOM.EQUITY"] == req["SEASON.SELL_IN_MAY.EQUITY"] == ("asset_class:equity",)
    assert len(req) == 10 + 3 + 3 + 1 + 1 + 2
    # funding carry is not re-run on the perp lane; the nominal value rules also run on FX-FRED
    assert all("CRYPTO-PERP" not in r.lanes for r in R.ALL_RULES if r.family == "CARRY")
    assert {r.id for r in R.ALL_RULES if r.family == "VALUE" and "FX-FRED" in r.lanes} == {
        "VALUE.XS_NOMINAL.L756", "VALUE.XS_NOMINAL.L1260", "VALUE.TS_Z.L756", "VALUE.TS_Z.L1260"}


# --------------------------------------------------------------------------------------------------
# counts
# --------------------------------------------------------------------------------------------------
def test_grid_matches_the_design_table_and_the_rulings_rule_by_rule():
    assert [r.id for r in R.ALL_RULES] == list(DESIGN)
    for r in R.ALL_RULES:
        family, tier, lanes, enabled = RULED[r.id]
        assert (r.family, r.tier, r.lanes, r.enabled) == (family, tier, lanes, enabled), r.id
    for lane in ALL:
        assert [r.id for r in R.rules(lane)] == expected_ids(lane), lane
        assert [r.id for r in R.rules(lane, include_disabled=True)] == expected_ids(lane, enabled=None), lane
        assert Counter((r.family, r.tier) for r in R.rules(lane)) == table_counts(lane), lane
    assert Counter((r.family, r.tier) for r in R.ALL_RULES if r.enabled) == table_counts()


def test_declared_counts_literal_numbers():
    c = R.declared_counts()
    # 78 declared, 11 parked (SEASON 5, FLOW 1, LINREG_T 3, REVERSAL.TS_Z.L20, VALUE.XS_RET.L1260)
    assert c["rules_total"] == 67
    assert c["rules_by_tier"] == {"CORE": 42, "EXPLORATORY": 25}
    assert c["rules_by_family"] == {"TREND": 24, "CARRY": 10, "VALUE": 7, "XSMOM": 9, "REVERSAL": 8, "VOL": 3,
                                    "SKEW": 2, "XASSET": 1, "ML": 3}
    assert c["rules_by_family_tier"]["TREND"] == {"CORE": 20, "EXPLORATORY": 4}
    assert c["rules_by_family_tier"]["CARRY"] == {"CORE": 8, "EXPLORATORY": 2}
    assert c["rules_by_family_tier"]["VALUE"] == {"CORE": 7, "EXPLORATORY": 0}
    assert c["rules_by_family_tier"]["XSMOM"] == {"CORE": 7, "EXPLORATORY": 2}
    assert c["rules_by_family_tier"]["REVERSAL"] == {"CORE": 0, "EXPLORATORY": 8}
    per_lane = {ln: (v["rules"], v["n_universes"], v["formulas"]) for ln, v in c["lanes"].items()}
    assert per_lane == {"FX": (67, 2, 134), "FX-FRED": (58, 1, 58), "MACRO": (45, 1, 45),
                        "CRYPTO-PERP": (46, 1, 46), "CRYPTO-SPOT": (46, 1, 46)}
    assert c["lanes"]["FX"]["universes"] == ["G10", "G10EM"]
    assert c["lanes"]["FX"]["formulas_by_universe"] == {"G10": 67, "G10EM": 67}
    assert c["lanes"]["FX"]["by_tier"] == {"CORE": 42, "EXPLORATORY": 25}
    assert c["lanes"]["FX-FRED"]["by_tier"] == {"CORE": 39, "EXPLORATORY": 19}
    assert c["lanes"]["MACRO"]["by_tier"] == {"CORE": 27, "EXPLORATORY": 18}
    assert c["lanes"]["CRYPTO-PERP"]["by_tier"] == {"CORE": 27, "EXPLORATORY": 19}
    assert c["lanes"]["CRYPTO-SPOT"]["by_tier"] == {"CORE": 27, "EXPLORATORY": 19}
    assert c["lanes"]["FX"]["by_family_tier"]["ML"] == {"CORE": 0, "EXPLORATORY": 3}
    assert all("ML" not in c["lanes"][ln]["by_family"] for ln in NOT_FX)
    assert c["lanes"]["MACRO"]["by_family"] == {"TREND": 24, "XSMOM": 9, "REVERSAL": 8, "VOL": 2, "SKEW": 2}
    assert c["formulas_total"] == 134 + 58 + 45 + 46 + 46 == 329
    assert c["formulas_tier2_lanes"] == 134 + 45 + 46 + 46 == 271
    assert c["tier2_lanes"] == ["FX", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT"]
    assert c["formulas_by_tier"] == {"CORE": 84 + 39 + 27 + 27 + 27, "EXPLORATORY": 50 + 19 + 18 + 19 + 19}
    assert sum(c["formulas_by_family"].values()) == 329
    # disabled, reported separately
    d = c["disabled"]
    assert d["rules_total"] == 11
    assert d["rules_by_family"] == {"TREND": 3, "VALUE": 1, "REVERSAL": 1, "SEASON": 5, "FLOW": 1}
    assert d["formulas_by_lane"] == {"FX": 12, "FX-FRED": 4, "MACRO": 7, "CRYPTO-PERP": 6, "CRYPTO-SPOT": 5}
    assert d["formulas_total"] == 34 and d["formulas_tier2_lanes"] == 30
    assert set(d["rules"]) == set(DISABLED) and all(d["rules"].values())
    assert c["lanes"]["MACRO"]["disabled_by_family_tier"] == {
        "TREND": {"CORE": 0, "EXPLORATORY": 3}, "VALUE": {"CORE": 0, "EXPLORATORY": 1},
        "REVERSAL": {"CORE": 0, "EXPLORATORY": 1}, "SEASON": {"CORE": 0, "EXPLORATORY": 2}}
    assert c["including_disabled"] == {"rules_total": 78, "formulas_total": 363, "formulas_tier2_lanes": 301}
    # 363 = the 376 of §4 minus the 13 (rule, lane) pairs removed by ruling
    assert set(c["lane_exclusions"]) == set(LANES_REMOVED)
    assert c["primaries"] == 16
    assert c["filter"] == {"families_by_lane": None, "lanes": None, "universes_by_lane": None,
                           "universes_by_lane_family": None}


def test_declared_counts_agree_with_the_table_for_every_lane():
    c = R.declared_counts()
    total_on = total_all = 0
    for lane in ALL:
        on, off = table_counts(lane), table_counts(lane, enabled=False)
        assert c["lanes"][lane]["rules"] == sum(on.values())
        assert c["lanes"][lane]["formulas"] == sum(on.values()) * UNIVERSES[lane]
        assert c["lanes"][lane]["disabled_rules"] == sum(off.values())
        assert c["lanes"][lane]["disabled_formulas"] == sum(off.values()) * UNIVERSES[lane]
        for (family, tier), n in on.items():
            assert c["lanes"][lane]["by_family_tier"][family][tier] == n
        for (family, tier), n in off.items():
            assert c["lanes"][lane]["disabled_by_family_tier"][family][tier] == n
        total_on += sum(on.values()) * UNIVERSES[lane]
        total_all += (sum(on.values()) + sum(off.values())) * UNIVERSES[lane]
    assert (total_on, total_all) == (c["formulas_total"], c["including_disabled"]["formulas_total"]) == (329, 363)


def test_declared_counts_with_run_filters():
    # (1) the long-only spot lane restricted to TREND and XSMOM
    c = R.declared_counts({"CRYPTO-SPOT": ("TREND", "XSMOM")})
    assert c["lanes"]["CRYPTO-SPOT"]["rules"] == 24 + 9 == 33
    assert c["lanes"]["CRYPTO-SPOT"]["by_tier"] == {"CORE": 27, "EXPLORATORY": 6}
    assert c["lanes"]["FX"]["formulas"] == 134                       # a lane that is not a key is counted in full
    assert c["formulas_total"] == 134 + 58 + 45 + 46 + 33 == 316
    assert c["formulas_tier2_lanes"] == 134 + 45 + 46 + 33 == 258
    assert c["rules_total"] == 67                                    # every enabled rule still runs somewhere
    assert c["filter"]["families_by_lane"] == {"CRYPTO-SPOT": ("TREND", "XSMOM")}
    # (2) the conductor's screen: the four Tier-2 lanes, spot restricted, ML on FX-G10 only
    b = R.declared_counts(families_by_lane={"CRYPTO-SPOT": ("TREND", "XSMOM")}, lanes=R.TIER2_LANES,
                          universes_by_lane_family={"FX": {"ML": ("G10",)}})
    assert list(b["lanes"]) == ["FX", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT"]
    assert b["lanes"]["FX"]["formulas"] == 64 * 2 + 3 == 131         # 64 non-ML rules on two universes + 3 ML on G10
    assert b["lanes"]["FX"]["formulas_by_universe"] == {"G10": 67, "G10EM": 64}
    assert b["lanes"]["FX"]["rules"] == 67
    assert b["formulas_total"] == b["formulas_tier2_lanes"] == 131 + 45 + 46 + 33 == 255
    assert b["formulas_by_tier"] == {"CORE": 84 + 27 + 27 + 27, "EXPLORATORY": 47 + 18 + 19 + 6}
    assert b["formulas_by_family"]["ML"] == 3
    assert b["filter"]["universes_by_lane_family"] == {"FX": {"ML": ["G10"]}}
    every = R.declared_counts(families_by_lane={"CRYPTO-SPOT": ("TREND", "XSMOM")},
                              universes_by_lane_family={"FX": {"ML": ("G10",)}})
    assert every["formulas_total"] == 255 + 58 == 313 and every["formulas_tier2_lanes"] == 255
    # a family with no universe on a lane is not run there
    none = R.declared_counts(universes_by_lane_family={"FX": {"ML": ()}})
    assert none["lanes"]["FX"]["formulas"] == 128 and none["rules_total"] == 64 and "ML" not in none["rules_by_family"]
    # (3) generic check against the table for an arbitrary family filter
    flt = {"FX": ("CARRY", "VALUE"), "MACRO": ("TREND",), "FX-FRED": (), "CRYPTO-PERP": ("ML", "SEASON", "FLOW")}
    c = R.declared_counts(flt)
    for lane in ALL:
        assert c["lanes"][lane]["rules"] == sum(table_counts(lane, families=flt.get(lane)).values()), lane
        assert c["lanes"][lane]["disabled_rules"] == sum(table_counts(lane, enabled=False, families=flt.get(lane)).values())
    assert c["lanes"]["FX-FRED"]["rules"] == 0 and c["lanes"]["CRYPTO-PERP"]["rules"] == 0
    assert c["lanes"]["CRYPTO-PERP"]["disabled_rules"] == 2          # ML is not declared on the perp lane any more
    assert c["lanes"]["FX"]["rules"] == 17 and c["lanes"]["MACRO"]["rules"] == 24
    # (4) lanes and universes
    only = R.declared_counts(lanes=("FX", "MACRO"))
    assert list(only["lanes"]) == ["FX", "MACRO"] and only["formulas_total"] == 134 + 45
    assert only["filter"]["lanes"] == ["FX", "MACRO"]
    more = R.declared_counts(universes_by_lane={"FX-FRED": ("G10", "G10EM")})
    assert more["lanes"]["FX-FRED"]["formulas"] == 116 and more["lanes"]["FX-FRED"]["universes"] == ["G10", "G10EM"]
    assert more["formulas_total"] == 329 + 58 and more["formulas_tier2_lanes"] == 271
    assert more["filter"]["universes_by_lane"] == {"FX-FRED": ["G10", "G10EM"]}
    less = R.declared_counts(universes_by_lane={"FX": ("G10",)})
    assert less["formulas_total"] == 329 - 67 and less["disabled"]["formulas_by_lane"]["FX"] == 6
    assert R.LANE_UNIVERSES["FX"] == ("G10", "G10EM")                # the default declaration is untouched
    # (5) refusals
    for bad in ({"families_by_lane": {"FX": ("MOMENTUM",)}}, {"families_by_lane": {"EQUITY": ("TREND",)}},
                {"lanes": ("FX", "BONDS")}, {"universes_by_lane": {"EQUITY": ("ALL",)}},
                {"universes_by_lane_family": {"FX": {"ML": ("G7",)}}},          # not a universe of the lane
                {"universes_by_lane_family": {"FX": {"MOMENTUM": ("G10",)}}},
                {"universes_by_lane_family": {"BONDS": {"ML": ("G10",)}}}):
        with pytest.raises(ValueError):
            R.declared_counts(**bad)


# --------------------------------------------------------------------------------------------------
# disabled rules and lane exclusions
# --------------------------------------------------------------------------------------------------
def test_disabled_rules_have_a_reason_and_are_kept():
    off = R.disabled_rules()
    assert [r.id for r in off] == [
        "TREND.LINREG_T.L63", "TREND.LINREG_T.L126", "TREND.LINREG_T.L252", "VALUE.XS_RET.L1260",
        "REVERSAL.TS_Z.L20", "SEASON.TOM.EQUITY", "SEASON.TOM.LONG", "SEASON.TOM.LONG_USD",
        "SEASON.TOM.SHORT_USD", "SEASON.SELL_IN_MAY.EQUITY", "FLOW.XS_GLSR_Z.L7"]
    assert {r.id for r in off} == set(DISABLED)
    for r in off:
        assert not r.enabled and DISABLED[r.id] in r.disabled_reason and "conductor ruling" in r.disabled_reason
        assert R.get(r.id) is r                                       # still addressable
    assert "86-87 %" in R.get("TREND.LINREG_T.L126").disabled_reason
    assert "-0.975" in R.get("REVERSAL.TS_Z.L20").disabled_reason
    assert R.get("VALUE.XS_RET.L1260").lanes == ("MACRO",)            # kept only so that its code stays tested
    assert all(r.enabled and r.disabled_reason == "" for r in R.ALL_RULES if r not in off)
    assert R.get("REVERSAL.TS_Z.L5").enabled and R.get("REVERSAL.TS_Z.L10").enabled
    for lane in ALL:
        ids = {r.id for r in R.rules(lane)}
        assert not ids & set(DISABLED)
        both = {r.id for r in R.rules(lane, include_disabled=True)}
        assert ids <= both and both - ids == {r.id for r in off if lane in r.lanes}
    assert [r.id for r in R.rules("CRYPTO-PERP", families=("SEASON", "FLOW"))] == []
    assert [r.id for r in R.rules("CRYPTO-PERP", include_disabled=True, families=("SEASON", "FLOW"))] == [
        "SEASON.TOM.LONG", "FLOW.XS_GLSR_Z.L7"]
    # a disabled rule still computes (its code and tests are kept)
    assert R.get("FLOW.XS_GLSR_Z.L7").signal(lane_panel("CRYPTO-PERP")).notna().any().any()
    assert R.get("TREND.LINREG_T.L63").signal(lane_panel("MACRO")).notna().any().any()


def test_lane_exclusions_are_recorded_with_their_reason():
    assert {rid: tuple(by_lane) for rid, by_lane in R.LANE_EXCLUSIONS.items()} == LANES_REMOVED
    for rid, lanes in LANES_REMOVED.items():
        rule = R.get(rid)
        assert rule.enabled and not set(lanes) & set(rule.lanes)
        assert set(rule.lanes) | set(lanes) == set(DESIGN[rid][2])     # nothing else changed
        assert all("conductor ruling" in R.LANE_EXCLUSIONS[rid][lane] for lane in lanes)
    assert "vol sort" in R.LANE_EXCLUSIONS["VOL.XS_LOWVOL.L252"]["MACRO"]
    assert ">= 20 years" in R.LANE_EXCLUSIONS["ML.RIDGE.A1"]["CRYPTO-PERP"]
    assert R.get("VOL.XS_LOWVOL.L252").lanes == ("FX", "FX-FRED", "CRYPTO-PERP", "CRYPTO-SPOT")
    for rid in ("ML.GBC.D2", "ML.GBC.D4", "ML.RIDGE.A1"):
        assert R.get(rid).lanes == ("FX",)
    assert [r.id for r in R.rules("MACRO") if r.family in ("ML", "VALUE")] == []
    assert "VOL.XS_LOWVOL.L252" not in {r.id for r in R.rules("MACRO", include_disabled=True)}


# --------------------------------------------------------------------------------------------------
# applicability
# --------------------------------------------------------------------------------------------------
def _without(panel, *aux_names, carry=True, meta_drop=()):
    from scripts.factory.panel import PanelBundle
    meta = {k: v for k, v in panel.meta.items() if k not in meta_drop}
    return PanelBundle(lane=panel.lane, prices=panel.prices, carry=panel.carry if carry else None,
                       aux={k: v for k, v in panel.aux.items() if k not in aux_names}, tbill=panel.tbill, meta=meta)


def test_rules_are_filtered_by_what_the_panel_has_and_the_rest_is_reported():
    fx = lane_panel("FX")
    assert len(R.rules("FX", fx)) == 67 and R.not_applicable("FX", fx) == []
    no_cpi = _without(fx, "cpi")
    gone = {r.id: why for r, why in R.not_applicable("FX", no_cpi)}
    assert gone == {"VALUE.XS_REAL.L756": "missing aux:cpi", "VALUE.XS_REAL.L1260": "missing aux:cpi",
                    "VALUE.XS_REAL_RET.L1260": "missing aux:cpi"}
    assert len(R.rules("FX", no_cpi)) == 64 and not {r.id for r in R.rules("FX", no_cpi)} & set(gone)
    no_oil = _without(fx, "oil")
    assert [r.id for r, _ in R.not_applicable("FX", no_oil)] == ["XASSET.OIL_FX.L63"]
    # carry rules run from rates alone or from the accrual panel alone, but not from neither
    assert not R.not_applicable("FX", _without(fx, "rates"))
    assert not R.not_applicable("FX", _without(fx, carry=False))
    neither = {r.family for r, _ in R.not_applicable("FX", _without(fx, "rates", carry=False))}
    assert neither == {"CARRY", "ML"}
    assert len(R.rules("FX", _without(fx, "rates", carry=False))) == 67 - 10 - 3
    # a disabled rule is reported only on request
    perp = _without(lane_panel("CRYPTO-PERP"), "glsr")
    assert R.not_applicable("CRYPTO-PERP", perp) == []
    assert [r.id for r, _ in R.not_applicable("CRYPTO-PERP", perp, include_disabled=True)] == ["FLOW.XS_GLSR_Z.L7"]
    macro = _without(lane_panel("MACRO"), meta_drop=("asset_class_of",))
    assert {r.id for r, _ in R.not_applicable("MACRO", macro, include_disabled=True)} == {
        "SEASON.TOM.EQUITY", "SEASON.SELL_IN_MAY.EQUITY"}
    with pytest.raises(ValueError):
        R.rules("EQUITY")
    with pytest.raises(ValueError):
        R.missing_requirements(dataclasses.replace(R.get("TREND.SMA_SIGN.200"), requires=("magic:beans",)), fx)


def test_a_rule_called_without_its_input_raises_instead_of_inventing_zeros():
    fx = lane_panel("FX")
    for rule_id, panel in (("VALUE.XS_REAL.L756", _without(fx, "cpi")), ("XASSET.OIL_FX.L63", _without(fx, "oil")),
                           ("CARRY.TS.S20", _without(fx, "rates", carry=False)),
                           ("CARRY.XS_CHANGE.L63", _without(fx, "rates", carry=False)),
                           ("FLOW.XS_GLSR_Z.L7", _without(lane_panel("CRYPTO-PERP"), "glsr"))):
        with pytest.raises(C.NotApplicable):
            R.get(rule_id).signal(panel)


# --------------------------------------------------------------------------------------------------
# universes
# --------------------------------------------------------------------------------------------------
def test_fx_universes_g10_and_g10em():
    fx = lane_panel("FX")
    u = R.fx_universes(fx)
    assert list(u) == ["G10", "G10EM"] and u["G10"] == G10 and u["G10EM"] == G10 + EM
    assert len(u["G10"]) == 9 and len(u["G10EM"]) == 16
    sub = fx.subset(u["G10"])
    assert list(sub.prices.columns) == G10 and list(sub.carry.columns) == G10
    assert "USD" in sub.aux["rates"].columns and "USD" in sub.aux["cpi"].columns     # passed through untouched
    assert R.universes(fx) == u
    fred = lane_panel("FX-FRED")
    assert list(R.fx_universes(fred)) == ["G10"] and len(R.fx_universes(fred)["G10"]) == 9
    assert R.LANE_UNIVERSES["FX"] == ("G10", "G10EM") and R.LANE_UNIVERSES["FX-FRED"] == ("G10",)
    macro = lane_panel("MACRO")
    assert R.universes(macro) == {"ALL": list(macro.prices.columns)}
    with pytest.raises(C.NotApplicable):
        R.fx_universes(macro)
    broken = mini_panel({"EUR": [1.0, 1.1], "GBP": [1.0, 1.1]}, meta={"universe_groups": {"G10": ["EUR", "GBP", "JPY"]}})
    with pytest.raises(ValueError, match="JPY"):
        R.fx_universes(broken)


def test_sigma_targets():
    assert R.SIGMA_TARGET == {"FX": 0.10, "FX-FRED": 0.10, "MACRO": 0.10, "CRYPTO-PERP": 0.20, "CRYPTO-SPOT": 0.20}
    assert R.sigma_target("MACRO") == 0.10 and R.sigma_target("CRYPTO-SPOT") == 0.20
    with pytest.raises(ValueError):
        R.sigma_target("EQUITY")


# --------------------------------------------------------------------------------------------------
# primaries (§6)
# --------------------------------------------------------------------------------------------------
def test_sixteen_primaries_exactly_as_declared():
    specs = R.primaries()
    assert [f.name for f in dataclasses.fields(R.PrimarySpec)] == ["id", "lane", "universe", "families", "transforms"]
    std_fx = {"vol_target": 0.10, "buffer": 0.10}
    std_crypto = {"vol_target": 0.20, "buffer": 0.10}
    four, two = ("TREND", "CARRY", "VALUE", "XSMOM"), ("TREND", "XSMOM")
    expected = [
        ("P.FX.G10.TREND", "FX", "G10", ("TREND",), std_fx, 20),
        ("P.FX.G10.CARRY", "FX", "G10", ("CARRY",), std_fx, 8),
        ("P.FX.G10.VALUE", "FX", "G10", ("VALUE",), std_fx, 7),
        ("P.FX.G10.XSMOM", "FX", "G10", ("XSMOM",), std_fx, 7),
        ("P.FX.G10.ALL", "FX", "G10", four, std_fx, 42),
        ("P.FX.G10EM.CARRY", "FX", "G10EM", ("CARRY",), std_fx, 8),
        ("P.FX.G10EM.ALL", "FX", "G10EM", four, std_fx, 42),
        ("P.MACRO.TREND", "MACRO", "ALL", ("TREND",), std_fx, 20),
        ("P.MACRO.XSMOM", "MACRO", "ALL", ("XSMOM",), std_fx, 7),
        ("P.MACRO.ALL", "MACRO", "ALL", two, std_fx, 27),
        ("P.MACRO.LO_TREND", "MACRO", "ALL", ("TREND",),
         {"long_only": True, "vol_target": 0.10, "max_gross": 1.0, "rebalance": "monthly"}, 20),
        ("P.CRYPTO.TREND", "CRYPTO-PERP", "ALL", ("TREND",), std_crypto, 20),
        ("P.CRYPTO.XSMOM", "CRYPTO-PERP", "ALL", ("XSMOM",), std_crypto, 7),
        ("P.CRYPTO.ALL", "CRYPTO-PERP", "ALL", two, std_crypto, 27),
        ("P.CRYPTO.LO_TREND", "CRYPTO-SPOT", "ALL", ("TREND",),
         {"long_only": True, "vol_target": 0.20, "max_gross": 1.0, "rebalance": "weekly"}, 20),
        ("P.GLOBAL", "GLOBAL", None, (),
         {"equal_risk_of": ("P.FX.G10.ALL", "P.MACRO.ALL", "P.CRYPTO.ALL"), "vol_target": 0.10}, 0),
    ]
    assert len(specs) == 16 == len({s.id for s in specs})
    for spec, (pid, lane, universe, families, transforms, n_members) in zip(specs, expected):
        assert (spec.id, spec.lane, spec.universe, spec.families) == (pid, lane, universe, families)
        assert spec.transforms == transforms and list(spec.transforms) == list(transforms), pid   # and their ORDER
        members = R.primary_members(spec)
        assert len(members) == n_members, pid
        assert all(m.tier == "CORE" and m.enabled and m.family in families and lane in m.lanes for m in members)
        assert R.primary_members(pid) == members
        if universe in ("G10", "G10EM"):
            assert universe in R.LANE_UNIVERSES[lane]
    ids = {s.id for s in specs}
    assert set(specs[-1].transforms["equal_risk_of"]) <= ids
    # two calls return independent objects (a caller may not corrupt the declaration)
    R.primaries()[0].transforms["vol_target"] = 99.0
    assert R.primaries()[0].transforms["vol_target"] == 0.10


def test_core_members_are_the_core_rows_of_the_table():
    core = {(f, lane): n for lane in ALL for (f, t), n in table_counts(lane).items() if t == CORE}
    assert core == {(f, lane): n for lane in ALL for (f, t), n in table_counts(lane, enabled=None).items() if t == CORE}
    assert core[("TREND", "FX")] == 20 and core[("CARRY", "FX")] == 8 and core[("VALUE", "FX")] == 7
    assert core[("XSMOM", "MACRO")] == 7 and ("CARRY", "MACRO") not in core and ("VALUE", "CRYPTO-PERP") not in core
    for spec in R.primaries():
        if spec.families:
            assert len(R.primary_members(spec)) == sum(core[(f, spec.lane)] for f in spec.families)


def test_a_primary_with_a_member_that_cannot_run_fails_visibly():
    fx = lane_panel("FX")
    g10 = fx.subset(R.fx_universes(fx)["G10"])
    assert len(R.primary_members("P.FX.G10.VALUE", g10)) == 7
    assert len(R.primary_members("P.FX.G10.ALL", g10)) == 42
    no_cpi = _without(g10, "cpi")
    with pytest.raises(C.NotApplicable, match="VALUE.XS_REAL.L756"):
        R.primary_members("P.FX.G10.VALUE", no_cpi)
    with pytest.raises(C.NotApplicable, match="P.FX.G10.ALL"):
        R.primary_members("P.FX.G10.ALL", no_cpi)
    assert len(R.primary_members("P.FX.G10.TREND", no_cpi)) == 20           # trend does not need CPI
    assert R.primary_members("P.GLOBAL", g10) == ()


# --------------------------------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------------------------------
def test_grid_manifest_is_json_and_its_hash_pins_declaration_and_sources(monkeypatch):
    import json

    man = R.grid_manifest()
    blob = json.dumps(man, sort_keys=True)
    assert json.loads(blob) == man                                           # plain JSON types only
    assert [r["id"] for r in man["rules"]] == EXPECTED_IDS
    assert len(man["primaries"]) == 16 and man["xs_ties"] == "split"
    assert man["declared_counts"]["formulas_total"] == 329
    assert set(man["lane_exclusions"]) == set(LANES_REMOVED) and "N_eligible" in man["sizing"]
    assert [r["id"] for r in man["rules"] if not r["enabled"]] == [r.id for r in R.disabled_rules()]
    assert man["rules"][EXPECTED_IDS.index("ML.RIDGE.A1")]["lanes"] == ["FX"]
    first = man["rules"][0]
    assert first["fn"] == "scripts.factory.strategies.rules_trend.ewmac" and first["params"] == {
        "fast": 2, "slow": 8, "scalar": 10.6}
    assert man["rules"][EXPECTED_IDS.index("XASSET.OIL_FX.L63")]["params"]["instruments"] == ["CAD", "NOK", "MXN"]
    assert sorted(man["source_sha256"]) == ["__init__.py", "common.py", "registry.py", "rules_carry.py",
                                            "rules_misc.py", "rules_ml.py", "rules_reversal.py", "rules_trend.py",
                                            "rules_value.py", "rules_xs.py"]
    assert all(len(h) == 64 for h in man["source_sha256"].values())
    h = R.grid_sha256()
    assert h == R.grid_sha256() and len(h) == 64
    assert R.grid_sha256(include_sources=False) != h
    # the declaration hash moves when the declaration moves
    declared = R.grid_sha256(include_sources=False)
    monkeypatch.setitem(R.SIGMA_TARGET, "FX", 0.12)
    assert R.grid_sha256(include_sources=False) != declared
    monkeypatch.undo()
    monkeypatch.setattr(C, "DEFAULT_TIES", "order")
    assert R.grid_sha256(include_sources=False) != declared
    monkeypatch.undo()
    assert R.grid_sha256(include_sources=False) == declared


# --------------------------------------------------------------------------------------------------
# isolation
# --------------------------------------------------------------------------------------------------
def test_importing_the_registry_pulls_in_nothing_but_the_panel():
    code = ("import sys; import scripts.factory.strategies.registry as R; "
            "mods = sorted(m for m in sys.modules if m.startswith('scripts.factory.')); "
            "bad = [m for m in mods if not (m.startswith('scripts.factory.strategies') or m == 'scripts.factory.panel')]; "
            "assert not bad, bad; assert 'sklearn' not in sys.modules; print(len(R.ALL_RULES))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "78"
