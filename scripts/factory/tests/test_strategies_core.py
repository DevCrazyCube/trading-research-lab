"""Every rule of the grid, on every lane it is declared for (builder B2, DESIGN_v2 §7).

For each (lane, rule) pair of `registry.rules(lane, include_disabled=True)` — the rules the conductor
disabled (SEASON, FLOW, LINREG_T, REVERSAL.TS_Z.L20, VALUE.XS_RET) stay in the library and are tested
like the others:
  * CONTRACT   — runs on the lane's synthetic panel; DataFrame with the panel's index and columns;
                 every value in [-1, 1] or NaN; the panel has what the rule requires; the signal can be
                 sized (`common.size_positions`) into a complete, bounded target.
  * TRUNCATION — the signal on the full panel and on the panel truncated at row k (50 %, 75 %, 90 % of
                 the rows) are BIT-IDENTICAL for rows <= k (`np.array_equal`, NaN == NaN — no tolerance).
  * SCRAMBLE   — the same with rows > k regenerated instead of removed (hostile values, no NaN).
Two deliberately leaky control rules must FAIL the same checks, so a pass means something.

The ML rules have their own (slower, smaller-panel) file: test_strategies_ml.py.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from scripts.factory.strategies import common as C
from scripts.factory.strategies import registry as R
from scripts.factory.strategies import rules_reversal, rules_trend
from scripts.factory.tests.test_strategies_synth import G10, LANES, lane_panel, scramble_future, truncate

FRACTIONS = (0.50, 0.75, 0.90)
PAIRS = [(lane, r.id) for lane in LANES for r in R.rules(lane, include_disabled=True) if r.family != "ML"]
PAIR_IDS = [f"{lane}:{rid}" for lane, rid in PAIRS]


@lru_cache(maxsize=None)
def truncated(lane: str, k: int):
    return truncate(lane_panel(lane), k)


@lru_cache(maxsize=None)
def scrambled(lane: str, k: int):
    return scramble_future(lane_panel(lane), k, seed=k)


def assert_signal_contract(sig: pd.DataFrame, panel) -> np.ndarray:
    assert isinstance(sig, pd.DataFrame)
    assert sig.index.equals(panel.prices.index), "signal index must be the panel index"
    assert list(sig.columns) == list(panel.prices.columns), "signal columns must be the panel columns"
    values = sig.to_numpy(dtype=float)
    assert not np.isinf(values).any(), "a signal is never infinite"
    finite = np.isfinite(values)
    assert (np.abs(values[finite]) <= 1.0).all(), "signal outside [-1, 1]"
    return values


def identical_prefix(full: pd.DataFrame, part: pd.DataFrame, k: int) -> bool:
    """Bit-identity of rows <= k (index, columns and every value; NaN equals NaN)."""
    a = part.iloc[:k + 1]
    b = full.iloc[:k + 1]
    return (a.index.equals(b.index) and list(a.columns) == list(b.columns)
            and np.array_equal(a.to_numpy(dtype=float), b.to_numpy(dtype=float), equal_nan=True))


# --------------------------------------------------------------------------------------------------
# contract
# --------------------------------------------------------------------------------------------------
def test_the_parametrisation_covers_every_non_ml_rule_of_every_lane():
    assert len(PAIRS) == sum(len(R.rules(lane, include_disabled=True)) for lane in LANES) - 3
    # enabled and disabled alike; ML is declared on FX only, VOL.XS_LOWVOL is not declared on MACRO
    assert len(PAIRS) == (73 - 3) + 62 + 52 + 52 + 51 == 287
    assert {rid for _, rid in PAIRS} == {r.id for r in R.ALL_RULES if r.family != "ML"}


@pytest.mark.parametrize("lane", LANES)
def test_synthetic_panel_can_run_every_rule_of_its_lane(lane):
    panel = lane_panel(lane)
    assert R.not_applicable(lane, panel, include_disabled=True) == []
    assert [r.id for r in R.rules(lane, panel)] == [r.id for r in R.rules(lane)]
    every = R.rules(lane, include_disabled=True)
    assert [r.id for r in R.rules(lane, panel, include_disabled=True)] == [r.id for r in every]
    assert all(r.enabled for r in R.rules(lane)) and len(every) >= len(R.rules(lane))


@pytest.mark.parametrize("lane,rule_id", PAIRS, ids=PAIR_IDS)
def test_rule_contract(lane, rule_id):
    panel, rule = lane_panel(lane), R.get(rule_id)
    sig = rule.fn(panel, **rule.params)
    values = assert_signal_contract(sig, panel)
    finite = np.isfinite(values)
    assert finite.any(), "the rule never takes a view on this panel — the test would be vacuous"
    assert (values[finite] != 0).any(), "the rule is identically zero on this panel"
    pd.testing.assert_frame_equal(sig, rule.signal(panel))                    # pure: same input, same output
    # sizing: a complete, bounded target that is flat wherever the instrument may not be held
    w = C.size_positions(sig, panel, R.sigma_target(lane))
    wv = w.to_numpy()
    assert not np.isnan(wv).any() and (np.abs(wv) <= 1.0).all()
    assert (wv[~panel.eligible().to_numpy()] == 0.0).all()
    assert (wv != 0).any()
    if rule.kind == "XS":
        # a cross-sectional rule is balanced in signal space and has no view outside the eligible set
        assert np.nanmax(np.abs(np.nansum(values, axis=1))) < 1e-9
        assert not finite[~panel.eligible().to_numpy()].any()


@pytest.mark.parametrize("rule_id", [r.id for r in R.rules("FX", include_disabled=True) if r.family != "ML"])
def test_fx_rule_on_the_g10_subset(rule_id):
    full = lane_panel("FX")
    universes = R.fx_universes(full)
    assert universes["G10"] == G10 and len(universes["G10EM"]) == 16
    panel, rule = full.subset(universes["G10"]), R.get(rule_id)
    assert not R.missing_requirements(rule, panel)
    values = assert_signal_contract(rule.fn(panel, **rule.params), panel)
    assert np.isfinite(values).any()
    if rule.kind == "XS" and rule.id.startswith(("XSMOM.TERCILE", "VALUE.XS", "REVERSAL.XS", "SKEW")):
        last = values[-1]                                           # nine currencies -> three long, three short
        assert (last == 1.0).sum() == 3 and (last == -1.0).sum() == 3 and (last == 0.0).sum() == 3


# --------------------------------------------------------------------------------------------------
# no lookahead
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lane,rule_id", PAIRS, ids=PAIR_IDS)
def test_rule_truncation_is_bit_identical(lane, rule_id):
    panel, rule = lane_panel(lane), R.get(rule_id)
    full = rule.fn(panel, **rule.params)
    n = len(panel.prices)
    saw_a_view = False
    for frac in FRACTIONS:
        k = int(n * frac)
        part = rule.fn(truncated(lane, k), **rule.params)
        assert len(part) == k + 1
        assert identical_prefix(full, part, k), f"{rule_id} on {lane}: rows <= {k} changed when the future was removed"
        saw_a_view |= bool(np.isfinite(part.to_numpy(dtype=float)).any())
    assert saw_a_view, "no truncation point reached a row with a view — the test would be vacuous"


@pytest.mark.parametrize("lane,rule_id", PAIRS, ids=PAIR_IDS)
def test_rule_future_scramble_is_bit_identical(lane, rule_id):
    panel, rule = lane_panel(lane), R.get(rule_id)
    full = rule.fn(panel, **rule.params)
    k = int(len(panel.prices) * 0.80)
    other = rule.fn(scrambled(lane, k), **rule.params)             # must not raise on a hostile future
    assert_signal_contract(other, panel)
    assert identical_prefix(full, other, k), f"{rule_id} on {lane}: rows <= {k} changed when the future changed"
    assert np.isfinite(full.iloc[:k + 1].to_numpy(dtype=float)).any()


# --------------------------------------------------------------------------------------------------
# the probes do catch a leak
# --------------------------------------------------------------------------------------------------
def leaky_full_sample_z(panel):
    """Normalises by the FULL-SAMPLE mean and std — a classic leak."""
    x = C.safe_log(C.excess_index(panel))
    return ((x - x.mean()) / x.std()).clip(-2, 2) / 2


def leaky_peek(panel):
    """Sign of TOMORROW's return."""
    return np.sign(C.excess_returns(panel).shift(-1))


@pytest.mark.parametrize("leaky", [leaky_full_sample_z, leaky_peek])
def test_the_probes_reject_a_leaky_rule(leaky):
    panel = lane_panel("FX")
    full = leaky(panel)
    k = int(len(panel.prices) * 0.75)
    assert not identical_prefix(full, leaky(truncated("FX", k)), k)
    assert not identical_prefix(full, leaky(scrambled("FX", k)), k)


def test_the_truncation_probe_is_not_vacuous_for_a_causal_rule():
    panel = lane_panel("FX")
    full = rules_trend.tsmom_z(panel, 21)
    k = int(len(panel.prices) * 0.75)
    part = rules_trend.tsmom_z(truncated("FX", k), 21)
    assert identical_prefix(full, part, k)
    assert np.isfinite(part.to_numpy()).mean() > 0.9
    # ... and the scrambled future really is different after k
    other = rules_trend.tsmom_z(scrambled("FX", k), 21)
    assert not np.array_equal(other.to_numpy()[k + 30:], full.to_numpy()[k + 30:], equal_nan=True)


# --------------------------------------------------------------------------------------------------
# degenerate panels: a rule may have no view, it may never raise
# --------------------------------------------------------------------------------------------------
def _with(panel, prices=None, aux=None):
    from scripts.factory.panel import PanelBundle
    return PanelBundle(lane=panel.lane, prices=panel.prices if prices is None else prices, carry=panel.carry,
                       aux=panel.aux if aux is None else aux, tbill=panel.tbill, meta=dict(panel.meta))


@pytest.mark.parametrize("lane", LANES)
def test_every_rule_survives_tiny_and_empty_panels(lane):
    """Zero, one, two, three and ten rows — including the ML rules (too short to fit: no view)."""
    panel = lane_panel(lane)
    shorts = [panel.window(end="1900-01-01")] + [truncated(lane, k) for k in (0, 1, 2, 9)]
    assert [len(s.prices) for s in shorts] == [0, 1, 2, 3, 10]
    for short in shorts:
        for rule in R.rules(lane, include_disabled=True):
            sig = rule.fn(short, **rule.params)
            assert_signal_contract(sig, short)
            w = C.size_positions(sig, short, R.sigma_target(lane))
            assert w.shape == short.prices.shape and not w.isna().any().any()


@pytest.mark.parametrize("lane", LANES)
def test_an_instrument_that_never_trades_gets_no_view_and_no_weight(lane):
    panel = lane_panel(lane)
    prices = panel.prices.copy()
    dead = prices.columns[1]
    prices[dead] = np.nan
    ghost = _with(panel, prices=prices)
    for rule in R.rules(lane, include_disabled=True):
        if rule.family == "ML":
            continue
        sig = rule.fn(ghost, **rule.params)
        assert sig[dead].isna().all(), rule.id
        assert (C.size_positions(sig, ghost, R.sigma_target(lane))[dead] == 0.0).all(), rule.id


@pytest.mark.parametrize("lane", ["CRYPTO-PERP", "CRYPTO-SPOT"])
def test_nothing_is_held_when_nothing_is_eligible(lane):
    panel = lane_panel(lane)
    aux = dict(panel.aux)
    aux["universe_mask"] = panel.aux["universe_mask"] & False
    closed = _with(panel, aux=aux)
    for rule in R.rules(lane, include_disabled=True):
        if rule.family == "ML":
            continue
        sig = rule.fn(closed, **rule.params)
        assert (C.size_positions(sig, closed, R.sigma_target(lane)) == 0.0).all().all(), rule.id
        if rule.kind == "XS":
            assert sig.isna().all().all(), rule.id                 # nothing to rank


# --------------------------------------------------------------------------------------------------
# purity
# --------------------------------------------------------------------------------------------------
def _fingerprint(panel) -> dict:
    frames = {"prices": panel.prices, "carry": panel.carry, "tbill": panel.tbill.to_frame()}
    frames.update({f"aux:{k}": v for k, v in panel.aux.items()})
    out = {k: int(pd.util.hash_pandas_object(v, index=True).sum()) for k, v in frames.items() if v is not None}
    out["meta"] = repr(sorted((k, repr(v)) for k, v in panel.meta.items()))
    return out


@pytest.mark.parametrize("lane", LANES)
def test_rules_do_not_mutate_the_panel(lane):
    panel = lane_panel(lane)
    before = _fingerprint(panel)
    for rule in R.rules(lane, include_disabled=True):
        if rule.family != "ML":
            sig = rule.fn(panel, **rule.params)
            C.size_positions(sig, panel, R.sigma_target(lane))
    assert _fingerprint(panel) == before


# --------------------------------------------------------------------------------------------------
# structural identities between rules of the grid
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lane", ["FX", "CRYPTO-PERP"])
def test_reversal_ts_z_is_the_exact_mirror_of_tsmom_z(lane):
    panel = lane_panel(lane)
    for lb in (5, 10, 20):
        pd.testing.assert_frame_equal(rules_reversal.reversal_ts_z(panel, lb), -rules_trend.tsmom_z(panel, lb))


def test_fx_turn_of_month_rules_are_exact_negations():
    panel = lane_panel("FX")
    long_usd = R.get("SEASON.TOM.LONG_USD").signal(panel)
    short_usd = R.get("SEASON.TOM.SHORT_USD").signal(panel)
    pd.testing.assert_frame_equal(long_usd, -short_usd)
    assert (long_usd.fillna(0.0) <= 0).all().all() and (long_usd == -1.0).any().any()


@pytest.mark.parametrize("lane", LANES)
def test_trend_rules_ignore_instruments_without_history(lane):
    """A TS rule's view on one instrument depends on that instrument alone (no cross-instrument leak)."""
    panel = lane_panel(lane)
    keep = list(panel.prices.columns[:3])
    alone = panel.subset(keep)
    for rid in ("TREND.EWMAC.16_64", "TREND.TSMOM_Z.L63", "TREND.BREAKOUT.L80", "TREND.DONCHIAN.L55",
                "TREND.LINREG_T.L63", "REVERSAL.RSI.14_30_70", "REVERSAL.BOLLINGER.20_2", "VOL.BREAKOUT.5_60"):
        rule = R.get(rid)
        both = rule.fn(panel, **rule.params)[keep]
        assert np.array_equal(both.to_numpy(), rule.fn(alone, **rule.params).to_numpy(), equal_nan=True), rid
