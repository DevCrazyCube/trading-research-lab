"""Tests for scripts/factory/audit.py — clean strategies PASS; strategies that peek through prices,
carry, an AUX frame, tbill, the universe mask, the NaN pattern or the panel length FAIL; the
regenerated future really is regenerated; the PRINT-PROXIMITY flag on hand-computed Sharpes.

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_audit.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from scripts.factory import audit
from scripts.factory.audit import AuditResult, future_scramble_audit, lag_sensitivity, scramble_after
from scripts.factory.engine import Refused
from scripts.factory.panel import PanelBundle

T, N = 160, 4
COLS = ["AAA", "BBB", "CCC", "DDD"]
PROBES = [60, 100, 140]


def make_panel(seed: int = 0, with_gaps: bool = True) -> PanelBundle:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-04 13:15", periods=T, freq="D", tz="UTC")
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, (T, N)), axis=0))
    if with_gaps:
        px[:25, 3] = np.nan                                             # DDD lists late
        px[150:, 1] = np.nan                                            # BBB delists near the end
    mask = pd.DataFrame(True, index=idx, columns=COLS)
    mask.iloc[:40, 2] = False                                           # CCC enters the universe at row 40
    mask.iloc[120:, 0] = False                                          # AAA leaves it at row 120
    aux = {
        "rates": pd.DataFrame(0.02 + np.cumsum(rng.normal(0, 2e-4, (T, 2)), axis=0), index=idx, columns=["USD", "EUR"]),
        "universe_mask": mask,
        "volume_quote": pd.DataFrame(np.exp(rng.normal(15, 0.5, (T, N))), index=idx, columns=COLS),
        "flags": pd.DataFrame(rng.integers(0, 2, (T, 2)), index=idx, columns=["f1", "f2"]),
        "counts": pd.DataFrame(rng.integers(5, 50, (T, 1)), index=idx, columns=["n"]),
        "regime": pd.DataFrame({"label": rng.choice(["calm", "wild", "crash"], T)}, index=idx),
        "oil": pd.DataFrame({"WTI": 60 * np.exp(np.cumsum(rng.normal(0, 0.02, T)))}, index=idx),
    }
    return PanelBundle(
        "AUDIT", pd.DataFrame(px, index=idx, columns=COLS),
        carry=pd.DataFrame(rng.normal(0, 2e-4, (T, N)), index=idx, columns=COLS),
        aux=aux, tbill=pd.Series(1e-4 + np.abs(rng.normal(0, 2e-5, T)), index=idx, name="tbill"),
        meta={"periods_per_year": 252},
    )


# ---- strategies -------------------------------------------------------------------------------
def clean_momentum(panel, lookback=5):
    return np.sign(panel.prices.pct_change(lookback, fill_method=None))


def clean_uses_every_field(panel, lookback=10):
    """Legal use of prices, carry, tbill, three aux frames and the universe mask: rows <= t only."""
    mom = panel.prices.pct_change(lookback, fill_method=None).sub(panel.tbill.rolling(lookback).sum(), axis=0)
    carry = panel.carry.rolling(lookback, min_periods=3).mean()
    usd = panel.aux["rates"]["USD"].diff(lookback)
    vol = np.log(panel.aux["volume_quote"]).diff()
    calm = (panel.aux["regime"]["label"] != "crash").astype(float)
    busy = panel.aux["counts"]["n"].rolling(5).mean() / 50.0
    sig = np.sign(mom) * 0.5 + np.sign(carry) * 0.3 - np.sign(vol) * 0.1
    sig = sig.mul(calm, axis=0).mul(1 - 0.2 * np.sign(usd).fillna(0.0), axis=0).mul(busy.fillna(0.0), axis=0)
    return sig.where(panel.eligible(), 0.0)


def peek_next_price(panel):
    return np.sign(panel.prices.shift(-1) / panel.prices - 1.0)         # tomorrow's return


def peek_full_sample_std(panel, lookback=5):
    r = panel.prices.pct_change(fill_method=None)
    return (r.rolling(lookback).mean() / r.std()).clip(-1, 1)            # normalised by the FULL-sample std


def peek_through_aux_only(panel):
    """Prices are used legally; the leak is one row of an aux frame."""
    lead = np.sign(panel.aux["rates"]["USD"].shift(-1) - panel.aux["rates"]["USD"])
    return np.sign(panel.prices.pct_change(5, fill_method=None)).mul(lead, axis=0)


def peek_through_carry(panel):
    return np.sign(panel.carry.shift(-2))


def peek_through_tbill(panel):
    up = np.sign(panel.tbill.shift(-1) - panel.tbill)
    return pd.DataFrame(np.outer(up.fillna(0.0), np.ones(len(panel.prices.columns))), index=panel.prices.index,
                        columns=panel.prices.columns)


def peek_final_universe(panel):
    """Survivorship: trade only what is still in the universe on the LAST row."""
    alive = panel.aux["universe_mask"].iloc[-1]
    return clean_momentum(panel).mul(alive.astype(float), axis=1)


def peek_nan_pattern(panel):
    """Keep only the instruments that never have a missing price in the whole sample."""
    complete = panel.prices.notna().all(axis=0)
    return clean_momentum(panel).mul(complete.astype(float), axis=1)


def peek_integer_aux(panel):
    return clean_momentum(panel).mul(panel.aux["flags"]["f1"].shift(-1).fillna(0), axis=0)


def peek_text_aux(panel):
    crash_ahead = (panel.aux["regime"]["label"].shift(-1) == "crash").astype(float)
    return clean_momentum(panel).mul(1 - crash_ahead, axis=0)


def peek_slow_threshold(panel):
    """One shared series, one row ahead, through a SLOW threshold: is oil's 30-print return (ending tomorrow)
    positive? A plausible one-print continuation almost never flips that sign; fillna hides the truncation."""
    oil = panel.aux["oil"]["WTI"]
    lead = np.sign(oil.shift(-1) / oil.shift(29) - 1.0).fillna(1.0)
    return pd.DataFrame(np.outer(lead, np.ones(len(panel.prices.columns))), index=panel.prices.index,
                        columns=panel.prices.columns)


def depends_on_panel_length(panel):
    return clean_momentum(panel) * (100.0 / len(panel.prices))          # same decisions, scaled by T


def raises_when_future_changes(panel):
    if "scrambled_after_row" not in panel.meta and len(panel.prices) == T:
        return clean_momentum(panel)
    raise RuntimeError("cannot compute without the original future")


class Flaky:
    def __init__(self):
        self.calls = 0

    def __call__(self, panel):
        self.calls += 1
        return clean_momentum(panel) * (1.0 + 1e-9 * self.calls)


def mutating(panel):
    panel.prices.iloc[0, 0] = 12345.0                                    # writes into its input
    return clean_momentum(panel)


def rng(seed=7):
    return np.random.default_rng(seed)


# ---- PASS ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("fn,params", [(clean_momentum, {}), (clean_momentum, {"lookback": 20}),
                                       (clean_uses_every_field, {}), (clean_uses_every_field, {"lookback": 4})])
def test_clean_strategies_pass(fn, params):
    res = future_scramble_audit(fn, make_panel(), params, PROBES, rng())
    assert isinstance(res, AuditResult) and res.passed is True and res.verdict == "PASS"
    assert res.detail.startswith("PASS") and res.first_divergence is None
    assert res.probe_rows == (60, 100, 140)
    assert res.rows_compared == 3 * (61 + 101 + 141)                    # scramble + mirrored scramble + truncation


def test_audit_result_contract():
    res = future_scramble_audit(clean_momentum, make_panel(), None, [50], rng(), truncation_probe=False)
    assert res.passed and isinstance(res.detail, str) and res.rows_compared == 2 * 51 and res.truncation_probe is False
    lean = future_scramble_audit(clean_momentum, make_panel(), None, [50], rng(), truncation_probe=False,
                                 antithetic=False, determinism_check=False)
    assert lean.passed and lean.rows_compared == 51
    with pytest.raises(Exception):
        res.verdict = "LEAKY"                                            # frozen


# ---- FAIL ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("fn", [peek_next_price, peek_full_sample_std, peek_through_aux_only, peek_through_carry,
                                peek_through_tbill, peek_final_universe, peek_nan_pattern, peek_integer_aux,
                                peek_text_aux, peek_slow_threshold])
@pytest.mark.parametrize("truncation", [True, False])
def test_peeking_strategies_fail(fn, truncation):
    """Every peeker fails — and fails on the SCRAMBLE probes alone (truncation off), field by field."""
    res = future_scramble_audit(fn, make_panel(), {}, PROBES, rng(), truncation_probe=truncation)
    assert res.passed is False and res.verdict == "LEAKY", fn.__name__
    assert res.detail.startswith("LEAKY")
    assert res.first_divergence["probe_kind"] in ("scramble", "scramble_mirrored", "truncation")
    assert truncation or res.first_divergence["probe_kind"] != "truncation"
    assert res.first_divergence["row"] <= res.first_divergence["probe_row"]
    assert res.first_divergence["column"] in COLS


@pytest.mark.parametrize("fn", [peek_through_aux_only, peek_slow_threshold, peek_through_tbill])
def test_one_row_ahead_leaks_through_a_single_shared_series_are_caught_for_every_seed(fn):
    """The antithetic pair sends each column far above its history in one run and far below in the other, so a
    decision that reads ONE future cell through sign() or a threshold changes in exactly one of the two runs —
    whatever the generator's seed. A single random scramble has no such guarantee."""
    panel = make_panel()
    for seed in range(40):
        res = future_scramble_audit(fn, panel, {}, [100], np.random.default_rng(seed), truncation_probe=False)
        assert res.verdict == "LEAKY", (fn.__name__, seed)
    misses = sum(
        future_scramble_audit(fn, panel, {}, [100], np.random.default_rng(seed), truncation_probe=False,
                              antithetic=False).passed
        for seed in range(40)
    )
    print(f"\n[measured] {fn.__name__}: a single (un-mirrored) scramble at one probe row misses the leak in "
          f"{misses}/40 seeds; the antithetic pair misses 0/40")
    assert 5 <= misses <= 35                                             # ~ half: the direction is a coin flip


def test_a_leak_through_an_aux_frame_alone_is_caught_by_the_scramble_probe():
    """The aux-only peeker reads prices legally, so only the regenerated AUX future can expose it: with the
    truncation probe off the verdict must still be LEAKY, and scrambling ONLY prices must not catch it."""
    panel = make_panel()
    res = future_scramble_audit(peek_through_aux_only, panel, {}, PROBES, rng(), truncation_probe=False)
    assert res.verdict == "LEAKY" and res.first_divergence["probe_kind"].startswith("scramble")
    k = 100
    only_prices = PanelBundle("AUDIT", scramble_after(panel, k, rng()).prices, carry=panel.carry, aux=panel.aux,
                              tbill=panel.tbill, meta=dict(panel.meta))
    a = peek_through_aux_only(panel).to_numpy()[: k + 1]
    b = peek_through_aux_only(only_prices).to_numpy()[: k + 1]
    assert np.array_equal(a, b, equal_nan=True)                         # a prices-only scramble is blind to it


def test_full_sample_normalisation_survives_a_permutation_but_not_a_regeneration():
    """Why the future is regenerated: permuting future rows keeps the full-sample std, so the leak is invisible."""
    panel = make_panel(with_gaps=False)
    k = 100
    perm = np.concatenate([np.arange(k + 1), k + 1 + rng().permutation(T - k - 1)])
    r = panel.prices.pct_change(fill_method=None)
    r_perm = pd.DataFrame(r.to_numpy()[perm], index=r.index, columns=r.columns)
    base = (r.rolling(5).mean() / r.std()).to_numpy()[: k + 1]
    permuted = (r_perm.rolling(5).mean() / r_perm.std()).to_numpy()[: k + 1]
    np.testing.assert_allclose(base, permuted, rtol=1e-12, equal_nan=True)   # the permutation probe sees nothing
    assert future_scramble_audit(peek_full_sample_std, panel, {}, [k], rng()).verdict == "LEAKY"


def test_dependence_on_the_panel_length_needs_the_truncation_probe():
    panel = make_panel()
    without = future_scramble_audit(depends_on_panel_length, panel, {}, PROBES, rng(), truncation_probe=False)
    assert without.passed                                                # same T, same decisions: scramble is blind
    with_trunc = future_scramble_audit(depends_on_panel_length, panel, {}, PROBES, rng())
    assert with_trunc.verdict == "LEAKY" and with_trunc.first_divergence["probe_kind"] == "truncation"


def test_a_strategy_that_raises_without_its_future_is_leaky():
    res = future_scramble_audit(raises_when_future_changes, make_panel(), {}, PROBES, rng())
    assert res.verdict == "LEAKY" and "RuntimeError" in res.detail and res.first_divergence["probe_kind"] == "scramble"
    assert res.passed is False


def test_non_deterministic_strategy_is_not_auditable():
    res = future_scramble_audit(Flaky(), make_panel(), {}, PROBES, rng())
    assert res.passed is False and res.verdict == "NON_DETERMINISTIC" and "seed the rule" in res.detail
    # with the determinism check off the same rule is (rightly) reported as diverging
    assert future_scramble_audit(Flaky(), make_panel(), {}, PROBES, rng(), determinism_check=False).verdict == "LEAKY"


def test_a_strategy_that_mutates_its_input_fails_and_the_callers_panel_is_unharmed():
    panel = make_panel()
    before = panel.prices.copy()
    res = future_scramble_audit(mutating, panel, {}, PROBES, rng())
    assert res.passed is False and res.verdict == "MUTATES_INPUT" and res.first_divergence == {"field": "prices"}
    pd.testing.assert_frame_equal(panel.prices, before)


def test_contract_violations_are_refused_not_called_leaks():
    panel = make_panel()
    with pytest.raises(Refused, match="no probe rows"):
        future_scramble_audit(clean_momentum, panel, {}, [], rng())
    for bad in ([T - 1], [-1], [3.0], [True]):
        with pytest.raises(Refused, match="probe row"):
            future_scramble_audit(clean_momentum, panel, {}, bad, rng())
    with pytest.raises(Refused, match="Generator"):
        future_scramble_audit(clean_momentum, panel, {}, PROBES, 42)
    with pytest.raises(Refused, match="DataFrame"):
        future_scramble_audit(lambda p: p.prices.to_numpy(), panel, {}, PROBES, rng())
    with pytest.raises(Refused, match="columns"):
        future_scramble_audit(lambda p: p.prices[["AAA", "BBB"]], panel, {}, PROBES, rng())
    with pytest.raises(Refused, match="index"):
        future_scramble_audit(lambda p: p.prices.iloc[:-1], panel, {}, PROBES, rng())
    with pytest.raises(ZeroDivisionError):                               # a broken strategy is not a leak
        future_scramble_audit(lambda p: p.prices * (1 / 0), panel, {}, PROBES, rng())


def test_audit_is_reproducible_from_the_generator_state():
    panel = make_panel()
    a = future_scramble_audit(peek_next_price, panel, {}, PROBES, rng(3))
    b = future_scramble_audit(peek_next_price, panel, {}, PROBES, rng(3))
    assert a == b
    assert future_scramble_audit(clean_momentum, panel, {}, [140, 60, 60, 100], rng()).probe_rows == (60, 100, 140)


# ---- the scramble itself ------------------------------------------------------------------------
def _fields(panel):
    out = [("prices", panel.prices), ("carry", panel.carry)]
    out += [(f"aux[{n}]", panel.aux[n]) for n in panel.aux]
    out.append(("tbill", panel.tbill.to_frame()))
    return out


def test_scramble_after_regenerates_every_field_after_k_and_nothing_before():
    panel = make_panel()
    k = 90
    out = scramble_after(panel, k, rng())
    assert out.meta["scrambled_after_row"] == k and out.meta["scramble_mirror"] is False
    assert "scrambled_after_row" not in panel.meta and list(out.aux) == list(panel.aux)
    for (name, old), (_, new) in zip(_fields(panel), _fields(out)):
        assert new.index.equals(old.index) and list(new.columns) == list(old.columns), name
        assert list(new.dtypes) == list(old.dtypes), name                # dtypes preserved (bool, int, object, float)
        pd.testing.assert_frame_equal(new.iloc[: k + 1], old.iloc[: k + 1], check_exact=True, obj=name)
        assert not new.iloc[k + 1:].isna().any().any(), name            # no NaN survives after k
        changed = (new.iloc[k + 1:].to_numpy() != old.iloc[k + 1:].to_numpy())
        if name in ("aux[universe_mask]", "aux[flags]", "aux[regime]"):
            assert changed.mean() > 0.2, name                            # constant blocks / permutations
        elif name == "aux[counts]":
            assert changed.mean() > 0.8, name                            # small integers can coincide by chance
        else:
            assert changed.all(), name                                  # continuous fields: EVERY cell differs
    assert (out.prices.iloc[k + 1:] > 0).all().all() and (out.aux["volume_quote"].iloc[k + 1:] > 0).all().all()
    assert (out.tbill.iloc[k + 1:] > 0).all() and (out.aux["counts"].iloc[k + 1:] >= 1).all().all()
    assert set(np.unique(out.aux["flags"].to_numpy())) <= {0, 1}
    # the delisted instrument has prices after k: the future NaN pattern is not preserved
    assert out.prices["BBB"].iloc[150:].notna().all()
    # each price is thrown at least ~3x away from its last honest value (x J or / J, J in [3, 5])
    ratio = (out.prices.iloc[k + 1] / panel.prices.iloc[k]).to_numpy()
    assert (np.abs(np.log(ratio)) > math.log(2.5)).all() and (np.abs(np.log(ratio)) < math.log(8)).all()


def test_the_mirrored_scramble_is_the_antithetic_twin():
    """Same generator state, mirror=False / True: every column goes the other way."""
    panel = make_panel()
    k = 90
    a = scramble_after(panel, k, rng(5))
    b = scramble_after(panel, k, rng(5), mirror=True)
    assert b.meta["scramble_mirror"] is True
    # positive columns: one run jumps above the last honest value, the other below
    for name in ("prices", "aux[volume_quote]", "aux[oil]", "aux[rates]", "tbill", "aux[counts]"):
        old = dict(_fields(panel))[name]
        fa, fb = dict(_fields(a))[name], dict(_fields(b))[name]
        last = old.iloc[: k + 1].ffill().iloc[-1].to_numpy(dtype=float)
        up_a = fa.iloc[k + 1].to_numpy(dtype=float) > last
        up_b = fb.iloc[k + 1].to_numpy(dtype=float) > last
        assert (up_a != up_b).all(), name
    # real columns (carry): opposite sides of the honest mean, 8 sd away
    mean = panel.carry.iloc[: k + 1].mean().to_numpy()
    sd = panel.carry.iloc[: k + 1].std(ddof=0).to_numpy()
    za = (a.carry.iloc[k + 1:].to_numpy() - mean) / sd
    zb = (b.carry.iloc[k + 1:].to_numpy() - mean) / sd
    assert (np.sign(za.mean(axis=0)) == -np.sign(zb.mean(axis=0))).all()
    assert (np.abs(za.mean(axis=0)) > 3.5).all() and (np.abs(zb.mean(axis=0)) > 3.5).all()
    # boolean / binary columns: all ones in one run, all zeros in the other -> every cell differs in exactly one
    for name in ("universe_mask", "flags"):
        va = a.aux[name].iloc[k + 1:].to_numpy().astype(int)
        vb = b.aux[name].iloc[k + 1:].to_numpy().astype(int)
        orig = panel.aux[name].iloc[k + 1:].to_numpy().astype(int)
        assert (va + vb == 1).all() and ((va != orig) ^ (vb != orig)).all(), name
    # text: both are permutations of the original block, in different orders
    ta, tb = a.aux["regime"]["label"].iloc[k + 1:], b.aux["regime"]["label"].iloc[k + 1:]
    assert sorted(ta) == sorted(tb) == sorted(panel.aux["regime"]["label"].iloc[k + 1:]) and list(ta) == list(tb)[::-1]


def test_scramble_does_not_modify_its_input_and_differs_by_seed():
    panel = make_panel()
    snapshot = (panel.prices.copy(), panel.carry.copy(), panel.tbill.copy(), {n: d.copy() for n, d in panel.aux.items()})
    a = scramble_after(panel, 50, rng(1))
    b = scramble_after(panel, 50, rng(1))
    c = scramble_after(panel, 50, rng(2))
    pd.testing.assert_frame_equal(panel.prices, snapshot[0])
    pd.testing.assert_frame_equal(panel.carry, snapshot[1])
    pd.testing.assert_series_equal(panel.tbill, snapshot[2])
    for n in panel.aux:
        pd.testing.assert_frame_equal(panel.aux[n], snapshot[3][n])
    pd.testing.assert_frame_equal(a.prices, b.prices)
    assert not a.prices.equals(c.prices)
    for bad in (-1, T - 1, 2.0, True):
        with pytest.raises(Refused):
            scramble_after(panel, bad, rng())


def test_scramble_handles_a_panel_without_carry_or_aux_and_a_zero_tbill():
    idx = pd.date_range("2022-01-01", periods=30, freq="D", tz="UTC")
    bare = PanelBundle("BARE", pd.DataFrame({"X": np.linspace(10, 12, 30)}, index=idx))
    out = scramble_after(bare, 10, rng())
    assert out.carry is None and out.aux == {} and (out.tbill.iloc[:11] == 0).all()
    assert (out.tbill.iloc[11:] != bare.tbill.iloc[11:]).any()           # even a zero tbill is regenerated
    assert future_scramble_audit(lambda p: np.sign(p.prices.diff(3)), bare, {}, [10, 20], rng()).passed
    assert not future_scramble_audit(lambda p: np.sign(p.prices.diff(-1)), bare, {}, [10, 20], rng()).passed


# ---- lag sensitivity ----------------------------------------------------------------------------
def alternating(mean: float, half_range: float, n: int = 100) -> np.ndarray:
    """mean + half_range, mean - half_range, ... : mean `mean`, std(ddof=1) = half_range * sqrt(n/(n-1))."""
    return mean + half_range * np.where(np.arange(n) % 2 == 0, 1.0, -1.0)


def test_lag_sensitivity_known_answers():
    # n = 100, ppy = 100 -> sqrt(ppy) = 10 ; std = 0.01 * sqrt(100/99) = 0.01005038
    #   a: mean 0.002 -> Sharpe = 0.002/0.01005038*10 = 1.98997 ; b: mean 0.0005 -> 0.49749 ; 1.98997 > 2*0.49749 -> FLAG
    a, b = alternating(0.002, 0.01), alternating(0.0005, 0.01)
    out = lag_sensitivity(a, b, 100)
    assert out["sharpe_a"] == pytest.approx(0.002 / (0.01 * math.sqrt(100 / 99)) * 10, rel=1e-12)
    assert out["sharpe_a"] == pytest.approx(1.98997, abs=1e-5) and out["sharpe_b"] == pytest.approx(0.49749, abs=1e-5)
    assert out["flag"] is True and out["label"] == "PRINT-PROXIMITY" == audit.PRINT_PROXIMITY
    assert out["ratio"] == pytest.approx(4.0, rel=1e-9)
    assert list(out) == ["flag", "label", "sharpe_a", "sharpe_b", "ratio", "reason"]
    # b keeps 60 % of the edge: 1.98997 <= 2 * 1.19398 -> no flag
    keep = lag_sensitivity(a, alternating(0.0012, 0.01), 100)
    assert keep["flag"] is False and keep["label"] is None
    # exactly half (ratio 2.0) is NOT flagged: the rule is a strict inequality (numbers exact in binary)
    half = lag_sensitivity(alternating(0.5, 1.0), alternating(0.25, 1.0), 100)
    assert half["ratio"] == 2.0 and half["flag"] is False
    # a losing rule has no edge to lose; a delayed run that LOSES money flags a winning base
    assert lag_sensitivity(alternating(-0.002, 0.01), alternating(-0.01, 0.01), 100)["flag"] is False
    assert lag_sensitivity(a, alternating(-0.0005, 0.01), 100)["flag"] is True
    # an unreadable delayed run (zero variance -> NaN Sharpe) is flagged when the base is positive
    nan_b = lag_sensitivity(a, np.zeros(100), 100)
    assert nan_b["flag"] is True and math.isnan(nan_b["sharpe_b"]) and math.isnan(nan_b["ratio"])
    assert lag_sensitivity(np.zeros(100), b, 100)["flag"] is False


def test_lag_sensitivity_scores_the_window_only():
    idx = pd.date_range("2020-01-01", periods=300, freq="D", tz="UTC")
    a = pd.Series(np.concatenate([np.zeros(200), alternating(0.002, 0.01)]), index=idx)
    b = pd.Series(np.concatenate([np.zeros(200), alternating(0.0005, 0.01)]), index=idx)
    win = lag_sensitivity(a, b, 100, window=(idx[200], None))
    assert win["sharpe_a"] == pytest.approx(1.98997, abs=1e-5) and win["flag"] is True
    full = lag_sensitivity(a, b, 100)
    assert full["sharpe_a"] < win["sharpe_a"]                            # warm-up zeros dilute the Sharpe
    with pytest.raises(ValueError):
        lag_sensitivity(a.to_numpy(), b.to_numpy(), 100, window=(idx[200], None))
