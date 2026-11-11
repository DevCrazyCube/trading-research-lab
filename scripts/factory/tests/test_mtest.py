"""Tests for scripts/factory/mtest.py — hand-computed answers for BH / BY / Holm, the arch sign
convention PROVEN on planted-winner / planted-loser / pure-noise toys (with measured size and power
printed), PBO on hand cases and toys, and the windowed circular-shift null against a slow reference.

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_mtest.py -q -s
      (-s shows the "[measured]" lines: the size / power figures quoted in the builder's report)
"""
from __future__ import annotations

import itertools
import math
import warnings

import numpy as np
import pandas as pd
import pytest
from arch.bootstrap import SPA, StepM
from statsmodels.stats.multitest import multipletests

from scripts.factory import mtest as M
from scripts.factory import stats as S
from scripts.factory.engine import Refused, backtest
from scripts.factory.panel import PanelBundle


# --------------------------------------------------------------------------------------------------
# BH / BY / Holm
# --------------------------------------------------------------------------------------------------
P5 = [0.012, 0.039, 0.028, 0.004, 0.5]          # sorted: 0.004, 0.012, 0.028, 0.039, 0.5


def test_bh_known_answer():
    # q = 0.05, m = 5: lines i*q/m = 0.01, 0.02, 0.03, 0.04, 0.05
    #   0.004 <= 0.01 ; 0.012 <= 0.02 ; 0.028 <= 0.03 ; 0.039 <= 0.04 ; 0.5 > 0.05  -> k = 4
    # adjusted (sorted) = m*p/i = 0.02, 0.03, 0.046667, 0.04875, 0.5 (already monotone)
    out = M.bh_fdr(P5, q=0.05)
    assert out["reject"].tolist() == [True, True, True, True, False] and out["n_reject"] == 4
    assert out["threshold"] == pytest.approx(0.04) and out["m"] == 5 and out["method"] == "benjamini-hochberg"
    np.testing.assert_allclose(out["p_adjusted"], [0.03, 0.04875, 0.14 / 3, 0.02, 0.5], rtol=1e-12)


def test_bh_is_a_step_up_and_holm_a_step_down():
    # p = [0.001, 0.035, 0.036, 0.9], q = alpha = 0.05, m = 4
    # BH lines 0.0125, 0.025, 0.0375, 0.05: 0.035 FAILS its own line (0.025) but 0.036 <= 0.0375 -> k = 3:
    #   the step-UP rejects all three, including 0.035.
    # Holm thresholds 0.0125, 0.016667, 0.025, 0.05: 0.001 passes, 0.035 > 0.016667 -> stop -> 1 rejection.
    # BY: c(4) = 1 + 1/2 + 1/3 + 1/4 = 2.083333 ; lines i*0.05/(4*2.083333) = 0.006, 0.012, 0.018, 0.024 -> 1 rejection.
    p = [0.001, 0.035, 0.036, 0.9]
    assert M.bh_fdr(p, q=0.05)["reject"].tolist() == [True, True, True, False]
    assert M.holm(p, alpha=0.05)["reject"].tolist() == [True, False, False, False]
    by = M.by_fdr(p, q=0.05)
    assert by["reject"].tolist() == [True, False, False, False] and by["threshold"] == pytest.approx(0.006)
    # BY adjusted of the smallest: 0.001 * 4 * 2.083333 / 1 = 0.0083333
    assert by["p_adjusted"][0] == pytest.approx(0.001 * 4 * (25 / 12), rel=1e-12)


def test_holm_known_answer():
    # alpha = 0.05, m = 5: thresholds alpha/(m-i+1) = 0.01, 0.0125, 0.016667, 0.025, 0.05
    #   0.004 <= 0.01 ; 0.012 <= 0.0125 ; 0.028 > 0.016667 -> stop -> 2 rejections
    # adjusted (sorted): 5*0.004, 4*0.012, 3*0.028, 2*0.039, 1*0.5 = 0.02, 0.048, 0.084, 0.078, 0.5 -> cummax
    #   = 0.02, 0.048, 0.084, 0.084, 0.5
    out = M.holm(P5, alpha=0.05)
    assert out["reject"].tolist() == [True, False, False, True, False] and out["n_reject"] == 2
    np.testing.assert_allclose(out["p_adjusted"], [0.048, 0.084, 0.084, 0.02, 0.5], rtol=1e-12)


def test_nothing_rejected_and_everything_rejected():
    none = M.bh_fdr([0.5, 0.6, 0.9], q=0.10)
    assert none["n_reject"] == 0 and none["threshold"] == 0.0
    every = M.bh_fdr([0.001, 0.002, 0.003], q=0.10)
    assert every["n_reject"] == 3 and M.holm([0.001, 0.002, 0.003], alpha=0.05)["n_reject"] == 3


def test_nan_p_values_count_in_m_and_are_never_rejected():
    # m = 4 (the NaN counts). BH lines at q = 0.10: 0.025, 0.05, 0.075 for the three valid p-values.
    #   0.02 <= 0.025 ; 0.04 <= 0.05 ; 0.5 fails -> 2 rejections. Without the NaN (m = 3) the lines would be
    #   0.0333, 0.0667, 0.1 — same rejections here but different adjusted p: 0.02*4/1 = 0.08, not 0.06.
    out = M.bh_fdr([0.02, np.nan, 0.04, 0.5], q=0.10)
    assert out["reject"].tolist() == [True, False, True, False] and out["m"] == 4
    assert out["p_adjusted"][0] == pytest.approx(0.08) and math.isnan(out["p_adjusted"][1])
    h = M.holm([0.02, np.nan, 0.004], alpha=0.05)      # thresholds 0.05/3, 0.05/2: 0.004 passes, 0.02 passes
    assert h["reject"].tolist() == [True, False, True] and h["p_adjusted"][2] == pytest.approx(0.012)


def test_series_in_series_out_and_validation():
    p = pd.Series({"r1": 0.012, "r2": 0.039, "r3": 0.028, "r4": 0.004, "r5": 0.5})
    out = M.bh_fdr(p, q=0.05)
    assert isinstance(out["reject"], pd.Series) and list(out["reject"].index) == list(p.index)
    assert out["reject"]["r5"] is np.False_ or out["reject"]["r5"] == False  # noqa: E712
    assert list(out["reject"][out["reject"]].index) == ["r1", "r2", "r3", "r4"]
    for bad in ([], [1.2], [-0.1]):
        with pytest.raises(ValueError):
            M.bh_fdr(bad, q=0.1)
    with pytest.raises(ValueError):
        M.holm([0.1], alpha=0.0)
    with pytest.raises(ValueError):
        M.by_fdr([0.1], q=1.0)


@pytest.mark.parametrize("seed", range(20))
def test_adjustments_equal_statsmodels(seed):
    rng = np.random.default_rng(seed)
    m = int(rng.integers(1, 60))
    p = np.concatenate([rng.uniform(0, 1, m), rng.uniform(0, 0.01, int(rng.integers(0, 6)))])
    level = float(rng.choice([0.05, 0.10, 0.20]))
    for mine, method in ((M.bh_fdr(p, level), "fdr_bh"), (M.by_fdr(p, level), "fdr_by"), (M.holm(p, level), "holm")):
        rej, adj, _, _ = multipletests(p, alpha=level, method=method)
        assert mine["reject"].tolist() == rej.tolist(), method
        np.testing.assert_allclose(mine["p_adjusted"], adj, rtol=1e-12, atol=0, err_msg=method)


def test_bh_and_holm_error_rates_on_planted_and_noise_p_values():
    """Measured: under the global null BH(q) and Holm(alpha) make ANY rejection with probability ~ q / <= alpha;
    with planted signals the realised FDR of BH stays below q."""
    rng = np.random.default_rng(0)
    sims, m, q = 3000, 50, 0.10
    any_bh = any_by = any_holm = 0
    for _ in range(sims):
        p = rng.uniform(0, 1, m)
        any_bh += M.bh_fdr(p, q)["n_reject"] > 0
        any_by += M.by_fdr(p, q)["n_reject"] > 0
        any_holm += M.holm(p, 0.05)["n_reject"] > 0
    fdp, power, fdp_by, power_by, holm_false, holm_power = [], [], [], [], [], []
    for _ in range(1000):
        z = rng.standard_normal(m)
        z[:10] += 3.5                                                    # 10 true signals of 50
        p = 1 - 0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))
        rej = M.bh_fdr(p, q)["reject"]
        fdp.append(rej[10:].sum() / max(rej.sum(), 1))
        power.append(rej[:10].mean())
        rej_by = M.by_fdr(p, q)["reject"]
        fdp_by.append(rej_by[10:].sum() / max(rej_by.sum(), 1))
        power_by.append(rej_by[:10].mean())
        rej_h = M.holm(p, 0.05)["reject"]
        holm_false.append(rej_h[10:].any())
        holm_power.append(rej_h[:10].mean())
    c_m = sum(1 / i for i in range(1, m + 1))                            # 4.499 for m = 50
    print(f"\n[measured] global null (50 uniform p-values, 3000 sims): P(any rejection) BH q=10% = {any_bh / sims:.3f}, "
          f"BY q=10% = {any_by / sims:.3f} (bound q/c(m) = {q / c_m:.3f}), Holm 5% = {any_holm / sims:.3f} ; "
          f"10 planted of 50 (z = 3.5, 1000 sims): BH FDR = {np.mean(fdp):.3f} power = {np.mean(power):.3f} ; "
          f"BY FDR = {np.mean(fdp_by):.3f} power = {np.mean(power_by):.3f} ; "
          f"Holm P(any false rejection) = {np.mean(holm_false):.3f} power = {np.mean(holm_power):.3f}")
    assert 0.07 <= any_bh / sims <= 0.13 and any_holm / sims <= 0.07 and any_by / sims <= 0.04
    assert np.mean(fdp) <= 0.10 and np.mean(power) > 0.8
    assert np.mean(fdp_by) <= np.mean(fdp) and 0.5 < np.mean(power_by) < np.mean(power)     # BY: safer, weaker
    assert np.mean(holm_false) <= 0.07 and np.mean(holm_power) > 0.5


def test_white_reality_check_on_noise_and_on_a_planted_winner():
    """Reality check (un-studentized, full recentring): rarely rejects on noise, rejects a loud real winner."""
    seeds = 60
    false_rej = sum(M.white_reality_check(toy(60_000 + s, K=30, hetero=False), block=10, reps=300, seed=s)["p_value"] < 0.05
                    for s in range(seeds))
    hits = sum(M.white_reality_check(toy(61_000 + s, K=30, hetero=False, planted={s % 30: 0.25}), block=10, reps=300,
                                     seed=s)["p_value"] < 0.05 for s in range(seeds))
    print(f"\n[measured] White reality check, 30 homoskedastic strategies x 500 prints: rejected on noise {false_rej}/{seeds}, "
          f"on a planted +0.25/print winner {hits}/{seeds}")
    assert false_rej <= 7 and hits >= 50
    # its known weakness: un-studentized, so a quiet real edge among loud noise is invisible (the SPA finds it)
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.05, (500, 20))
    r[:, 0] = rng.normal(0.0005, 0.001, 500)
    assert M.white_reality_check(r, block=10, reps=300, seed=3)["p_value"] > 0.2
    assert M.spa(r, block=10, reps=300, seed=3)["p_consistent"] < 0.01


# --------------------------------------------------------------------------------------------------
# Long-run variance
# --------------------------------------------------------------------------------------------------
def test_stationary_long_run_variance_hand_example():
    # d = [1, 2, 6], block = 2 (q = 1/2): mean 3, dm = [-2, -1, 3]
    #   g0 = (4 + 1 + 9)/3 = 14/3 ; g1 = ((-2)(-1) + (-1)(3))/3 = -1/3 ; g2 = (-2)(3)/3 = -2
    #   kappa(3,1) = (2/3)(1/2) + (1/3)(1/4) = 5/12 ; kappa(3,2) = (1/3)(1/4) + (2/3)(1/2) = 5/12
    #   omega^2 = 14/3 + 2*(5/12)*(-1/3) + 2*(5/12)*(-2) = 4.666667 - 0.277778 - 1.666667 = 2.722222
    out = M.stationary_long_run_variance(np.array([[1.0], [2.0], [6.0]]), 2)
    assert out[0] == pytest.approx(14 / 3 - 10 / 36 - 20 / 12, rel=1e-12)
    assert out[0] == pytest.approx(2.722222, abs=1e-6)
    # block = 1 (iid bootstrap): kappa(T, i) = 0 for 0 < i < T, so omega^2 is the population variance
    x = np.random.default_rng(0).normal(0, 1, (200, 3))
    np.testing.assert_allclose(M.stationary_long_run_variance(x, 1), x.var(axis=0), rtol=1e-10)


@pytest.mark.parametrize("seed,block", [(0, 10), (1, 5), (2, 25)])
def test_long_run_variance_equals_archs_internal_estimate(seed, block):
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 0.01, (300, 6))
    d = e.copy()
    d[1:] += 0.5 * e[:-1]                                               # MA(1): autocovariances matter
    ref = SPA(np.zeros(300), -d, block_size=block, reps=100, seed=1)
    ref._compute_variance()                                             # private, used ONLY here as a reference
    np.testing.assert_allclose(M.stationary_long_run_variance(d, block), ref._loss_diff_var, rtol=1e-10)


# --------------------------------------------------------------------------------------------------
# SPA / StepM: the sign convention, proven
# --------------------------------------------------------------------------------------------------
def toy(seed: int, T: int = 500, K: int = 50, planted=None, sharpe_pp: float = 0.25, hetero: bool = True,
        ar: float = 0.0) -> pd.DataFrame:
    """K strategies of pure noise (per-print sd between 0.3 % and 3 % when `hetero`), optionally AR(1),
    with `planted` = {column index: per-print Sharpe} added as a real mean."""
    rng = np.random.default_rng(seed)
    e = rng.standard_normal((T, K))
    if ar:
        for t in range(1, T):
            e[t] += ar * e[t - 1]
        e *= math.sqrt(1 - ar * ar)
    sd = rng.uniform(0.003, 0.03, K) if hetero else np.full(K, 0.01)
    r = e * sd
    for col, sr in (planted or {}).items():
        r[:, col] += sr * sd[col]
    return pd.DataFrame(r, columns=[f"s{i:02d}" for i in range(K)])


def test_sign_convention_planted_winner_and_planted_loser():
    """One real winner (s07, +0.30 Sharpe per print) and one real loser (s21, -0.30) among 48 noise strategies.
    The wrapper must return the WINNER and never the loser. Feeding -returns (the mistake the arch API
    invites: losses where returns are expected) returns the loser instead — which is why this test exists."""
    r = toy(123, planted={7: 0.30, 21: -0.30})
    out = M.stepm(r, alpha=0.05, block=10, reps=500, seed=1)
    assert out["superior"] == ["s07"]
    assert out["t_stat"]["s07"] > 4 and out["t_stat"]["s21"] < -4
    assert out["steps"][0]["rejected"] == ["s07"] and out["steps"][-1]["rejected"] == []
    assert out["t_stat"]["s07"] > out["steps"][0]["critical_value"] > 2.5        # ~3.1 for the max of 50
    wrong = M.stepm(-r, alpha=0.05, block=10, reps=500, seed=1)
    assert wrong["superior"] == ["s21"]
    sp = M.spa(r, block=10, reps=500, seed=1)
    assert sp["best"] == "s07" and sp["p_consistent"] < 0.01 and sp["p_lower"] <= sp["p_consistent"] <= sp["p_upper"]
    loser_only = M.spa(toy(123, planted={21: -0.30}), block=10, reps=500, seed=1)
    assert loser_only["p_consistent"] > 0.05 and loser_only["best"] != "s21"
    rc = M.white_reality_check(toy(123, planted={7: 0.30}, hetero=False), block=10, reps=500, seed=1)
    assert rc["p_value"] < 0.01 and rc["best"] == "s07"


def test_what_arch_is_actually_fed():
    """Direct statement of the convention: our stepm == arch StepM on losses = -(returns - benchmark) / sd."""
    r = toy(5, T=400, K=20, planted={3: 0.25})
    omega = r.to_numpy().std(axis=0, ddof=1)
    ref = StepM(np.zeros(400), pd.DataFrame(-r.to_numpy() / omega, columns=r.columns), size=0.05, block_size=10,
                reps=400, bootstrap="stationary", studentize=False, seed=11)
    ref.compute()
    mine = M.stepm(r, alpha=0.05, block=10, reps=400, seed=11, bias_correction=False)
    assert mine["superior"] == list(ref.superior_models) == ["s03"]
    ref_spa = SPA(np.zeros(400), -r.to_numpy() / omega, block_size=10, reps=400, studentize=False, seed=11)
    ref_spa.compute()
    sp = M.spa(r, block=10, reps=400, seed=11, bias_correction=False)
    assert (sp["p_lower"], sp["p_consistent"], sp["p_upper"]) == tuple(float(v) for v in ref_spa.pvalues)
    assert sp["critical_value_inflation"] == 1.0 and sp["bias_correction"] is False


@pytest.mark.parametrize("seed", range(6))
def test_stepm_equals_arch_stepm_on_prescaled_data(seed):
    r = toy(700 + seed, T=300, K=15, planted={0: 0.3, 4: 0.25} if seed % 2 else None)
    omega = r.to_numpy().std(axis=0, ddof=1)
    ref = StepM(np.zeros(300), pd.DataFrame(-r.to_numpy() / omega, columns=r.columns), size=0.10, block_size=8,
                reps=300, studentize=False, seed=seed)
    ref.compute()
    raw = M.stepm(r, alpha=0.10, block=8, reps=300, seed=seed, bias_correction=False)
    assert raw["superior"] == list(ref.superior_models)
    # the default (bias-corrected) procedure can only reject a subset of what the raw one rejects
    assert set(M.stepm(r, alpha=0.10, block=8, reps=300, seed=seed)["superior"]) <= set(raw["superior"])


def test_bias_correction_inflates_the_critical_value_by_a_known_factor():
    # T = 500, block = 10: c = sqrt(500 / (500 - 20 + 1)) = sqrt(500/481) = sqrt(1.0395010) = 1.019559
    assert M.variance_bias_factor(500, 10) == pytest.approx(math.sqrt(500 / 481), rel=1e-15)
    assert M.variance_bias_factor(500, 10) == pytest.approx(1.019559, abs=1e-6)
    assert M.variance_bias_factor(1250, 10) == pytest.approx(1.007688, abs=1e-6)     # sqrt(1250/1231)
    with pytest.raises(ValueError):
        M.variance_bias_factor(20, 10)
    r = toy(77, planted={3: 0.25})
    raw = M.stepm(r, block=10, reps=400, seed=5, bias_correction=False)
    cor = M.stepm(r, block=10, reps=400, seed=5)
    # same bootstrap draws, same statistic; only the bar moves, by exactly c
    assert cor["steps"][0]["critical_value"] == pytest.approx(raw["steps"][0]["critical_value"] * math.sqrt(500 / 481), rel=1e-9)
    assert cor["critical_value_inflation"] == pytest.approx(math.sqrt(500 / 481)) and cor["bias_correction"] is True
    pd.testing.assert_series_equal(cor["t_stat"], raw["t_stat"])
    assert cor["superior"] == raw["superior"] == ["s03"]
    for step in cor["steps"]:                                            # rejected <=> statistic above the reported bar
        assert all(cor["t_stat"][i] > step["critical_value"] for i in step["rejected"])
    assert M.spa(r, block=10, reps=400, seed=5)["p_consistent"] >= M.spa(r, block=10, reps=400, seed=5,
                                                                        bias_correction=False)["p_consistent"]


def test_stationary_bootstrap_understates_the_variance_of_a_mean_by_the_stated_amount():
    """The reason for the correction, measured: E[omega-hat^2 / s^2] = 1 - (2*block - 1)/T on white noise."""
    rng = np.random.default_rng(0)
    for T, block in ((500, 10), (500, 25), (1250, 10)):
        d = rng.standard_normal((T, 3000))
        ratio = float((M.stationary_long_run_variance(d, block) / d.var(axis=0, ddof=1)).mean())
        assert ratio == pytest.approx(1 - (2 * block - 1) / T, abs=0.012), (T, block, ratio)


def test_arch_studentize_flag_is_a_no_op_and_ours_is_not():
    """arch 8.0.0: studentize=True and =False give identical p-values (the flag never touches the statistic).
    Consequence: a real low-volatility edge is invisible next to loud noise. Our pre-scaling fixes that."""
    rng = np.random.default_rng(0)
    T = 500
    r = rng.normal(0, 0.05, (T, 20))                                    # 19 loud noise strategies (5 % per print)
    r[:, 0] = rng.normal(0.0005, 0.001, T)                              # a quiet real edge: Sharpe 0.5 per print
    a = SPA(np.zeros(T), -r, block_size=10, reps=300, studentize=True, seed=3)
    b = SPA(np.zeros(T), -r, block_size=10, reps=300, studentize=False, seed=3)
    a.compute()
    b.compute()
    assert a.pvalues.tolist() == b.pvalues.tolist()
    assert a.critical_values(0.05).tolist() == b.critical_values(0.05).tolist()
    assert M.stepm(r, block=10, reps=300, seed=3, studentize=False)["superior"] == []
    assert M.stepm(r, block=10, reps=300, seed=3, studentize=True)["superior"] == [0]
    assert M.spa(r, block=10, reps=300, seed=3)["p_consistent"] < 0.01 < M.spa(r, block=10, reps=300, seed=3,
                                                                                 studentize=False)["p_consistent"]


def test_all_models_superior_over_two_steps_does_not_crash():
    """arch's StepM.compute() raises 'zero-size array to reduction operation maximum' on this input; ours returns."""
    rng = np.random.default_rng(0)
    T = 500
    r = np.column_stack([rng.normal(0.01, 0.05, T), rng.normal(0.0005, 0.001, T)])
    ref = StepM(np.zeros(T), -r, size=0.05, block_size=10, reps=300, seed=1)
    with pytest.raises(ValueError, match="zero-size array"):
        ref.compute()
    out = M.stepm(r, alpha=0.05, block=10, reps=300, seed=1, studentize=False)
    assert out["superior"] == [0, 1] and [s["rejected"] for s in out["steps"]] == [[0], [1]]
    assert M.stepm(r, alpha=0.05, block=10, reps=300, seed=1)["superior"] == [0, 1]


def test_benchmark_is_subtracted_and_degenerate_columns_are_reported():
    rng = np.random.default_rng(8)
    T = 400
    bench = pd.Series(rng.normal(0.002, 0.01, T))
    r = pd.DataFrame({
        "tracks": bench + rng.normal(0, 0.002, T),                      # the benchmark plus noise: not superior
        "beats": bench + rng.normal(0.0008, 0.002, T),                  # +0.4 Sharpe per print over the benchmark
        "is_bench": bench,                                              # identical to the benchmark: degenerate
    })
    out = M.stepm(r, benchmark=bench, alpha=0.05, block=10, reps=400, seed=2)
    assert out["superior"] == ["beats"] and out["degenerate"] == ["is_bench"] and math.isnan(out["t_stat"]["is_bench"])
    # against a zero benchmark all three have a clearly positive mean (0.2 Sharpe per print, t ~ 4)
    assert set(M.stepm(r, alpha=0.05, block=10, reps=400, seed=2)["superior"]) == {"tracks", "beats", "is_bench"}
    with pytest.raises(ValueError, match="one value per row"):
        M.stepm(r, benchmark=bench.iloc[:-1].to_numpy(), block=10, reps=400, seed=2)
    with pytest.raises(ValueError, match="index"):
        M.stepm(r, benchmark=bench.rename(lambda i: i + 1), block=10, reps=400, seed=2)


def test_results_are_labels_and_the_default_block_is_the_cube_root_rule():
    """arch's better_models() returns integer POSITIONS; this module returns the caller's LABELS. Integer labels
    that are not positions make the difference visible."""
    rng = np.random.default_rng(2)
    T = 500
    r = pd.DataFrame(rng.normal(0, 0.01, (T, 4)), columns=[40, 30, 20, 10])     # labels are NOT 0..3
    r[20] += 0.003                                                       # the planted winner sits at POSITION 2
    out = M.stepm(r, alpha=0.05, reps=400, seed=1)
    assert out["superior"] == [20] and out["steps"][0]["rejected"] == [20]
    assert list(out["t_stat"].index) == [40, 30, 20, 10] and out["t_stat"].idxmax() == 20
    sp = M.spa(r, reps=400, seed=1)
    assert sp["best"] == 20 and list(sp["mean"].index) == [40, 30, 20, 10]
    assert M.white_reality_check(r, reps=400, seed=1)["best"] == 20
    # string labels, a degenerate column named, a tuple label
    s = r.rename(columns={40: "alpha", 30: ("FX", "carry"), 20: "winner", 10: "flat"})
    s["flat"] = 0.0
    out = M.stepm(s, reps=400, seed=1)
    assert out["superior"] == ["winner"] and out["degenerate"] == ["flat"]
    assert list(out["t_stat"].index) == ["alpha", ("FX", "carry"), "winner", "flat"]
    # a bare array has no labels: positions ARE the labels, and that is stated by returning ints
    assert M.stepm(r.to_numpy(), reps=400, seed=1)["superior"] == [2]
    # block: None -> ceil(2 T^(1/3)) = 16 at T = 500 (arch's own fallback would be int(sqrt(500)) = 22)
    assert out["block"] == 16 and out["block_source"] == "default ceil(2*T^(1/3))" and sp["block"] == 16
    given = M.stepm(r, block=5, reps=400, seed=1)
    assert given["block"] == 5 and given["block_source"] == "given"
    same = M.stepm(r, block=16, reps=400, seed=1)
    assert same["steps"] == M.stepm(r, reps=400, seed=1)["steps"]         # the default is exactly block=16 here
    with pytest.raises(ValueError, match="duplicate"):
        M.stepm(pd.DataFrame(r.to_numpy(), columns=["a", "a", "b", "c"]), reps=400, seed=1)


def test_columns_without_variation_are_never_superior_and_an_all_flat_panel_has_no_p_value():
    """arch computes p = mean(bootstrap max > observed max); on an all-zero panel that is mean(0 > 0) = 0 —
    a 'significant' result out of nothing. Flat strategies are routine in a sweep (a rule with no signal yet)."""
    rng = np.random.default_rng(4)
    T = 300
    flat = pd.DataFrame(0.0, index=range(T), columns=["a", "b", "c"])
    raw = SPA(np.zeros(T), -flat.to_numpy(), block_size=10, reps=200, seed=1)
    raw.compute()
    assert float(raw.pvalues["consistent"]) == 0.0                       # what arch says about nothing
    sp = M.spa(flat, reps=200, seed=1)
    assert math.isnan(sp["p_consistent"]) and sp["best"] is None and sp["degenerate"] == ["a", "b", "c"]
    assert not (sp["p_consistent"] < 0.05)                               # a NaN p-value can never pass a threshold
    out = M.stepm(flat, reps=200, seed=1)
    assert out["superior"] == [] and out["steps"] == []
    assert math.isnan(M.white_reality_check(flat, reps=200, seed=1)["p_value"])
    # a CONSTANT positive return has no variance either: reported, not "infinitely significant"
    mixed = pd.DataFrame({"const": 0.001, "weak": rng.normal(-0.001, 0.01, T), "real": rng.normal(0.004, 0.01, T)})
    out = M.stepm(mixed, reps=300, seed=2)
    assert out["degenerate"] == ["const"] and out["superior"] == ["real"] and math.isnan(out["t_stat"]["const"])
    assert out["steps"][0]["n_tested"] == 2                              # the constant column is not in the family tested
    assert M.spa(mixed, reps=300, seed=2)["best"] == "real"
    # a flat strategy next to a LOSING one: left in the bootstrap, the flat column would make arch report p = 0
    loser = rng.normal(-0.004, 0.01, T)
    only_losers = pd.DataFrame({"flat": 0.0, "loser": loser})
    naive = SPA(np.zeros(T), -only_losers.to_numpy(), block_size=10, reps=300, seed=2)
    naive.compute()
    assert float(naive.pvalues["consistent"]) == 0.0                     # arch on the raw panel: "significant"
    sp = M.spa(only_losers, reps=300, seed=2)
    assert sp["p_consistent"] > 0.3 and sp["best"] == "loser" and sp["degenerate"] == ["flat"]
    assert M.stepm(only_losers, reps=300, seed=2)["superior"] == []


def test_spa_stepm_validation():
    r = toy(1, T=100, K=5)
    bad = r.copy()
    bad.iloc[3, 2] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        M.stepm(bad, block=10, reps=200, seed=1)
    for kwargs in (dict(block=0), dict(block=2.5), dict(reps=10), dict(seed=1.5), dict(seed=None)):
        call = dict(block=10, reps=200, seed=1)
        call.update(kwargs)
        with pytest.raises(ValueError):
            M.spa(r, **call)
    with pytest.raises(ValueError, match="alpha"):
        M.stepm(r, alpha=1.5, block=10, reps=200, seed=1)
    with pytest.raises(ValueError):
        M.spa(r.iloc[:5], block=2, reps=200, seed=1)
    with pytest.raises(TypeError):
        M.stepm(r)                                                       # seed is required
    with pytest.raises(TypeError):
        M.spa(r, block=10)
    same_a = M.stepm(r, block=10, reps=200, seed=4)
    same_b = M.stepm(r, block=10, reps=200, seed=4)
    assert same_a["superior"] == same_b["superior"] and same_a["steps"] == same_b["steps"]


N_NOISE_SEEDS = 200
N_PLANTED_SEEDS = 100


def test_stepm_size_and_power_measured():
    """The SHIPPED defaults (block = ceil(2 T^(1/3)) = 16, sd-studentized, bias-corrected).
    SIZE: an all-noise panel (50 strategies, 500 prints, heteroskedastic) must give the EMPTY set about 95 %
    of the time at alpha = 5 %. POWER: with one planted strategy (+0.25 Sharpe per print, t ~ 5.6) StepM must
    return exactly that one in most seeds."""
    empty = 0
    for seed in range(N_NOISE_SEEDS):
        out = M.stepm(toy(10_000 + seed), alpha=0.05, reps=400, seed=seed)
        empty += out["superior"] == []
    assert out["block"] == 16 and out["bias_correction"] is True and out["studentized"] is True
    exact = contains = 0
    for seed in range(N_PLANTED_SEEDS):
        col = seed % 50
        sup = M.stepm(toy(20_000 + seed, planted={col: 0.25}), alpha=0.05, reps=400, seed=seed)["superior"]
        exact += sup == [f"s{col:02d}"]
        contains += f"s{col:02d}" in sup
    rate = empty / N_NOISE_SEEDS
    print(f"\n[measured] StepM alpha=5% (default block 16, bias-corrected), 50 noise strategies x 500 prints: empty set in "
          f"{empty}/{N_NOISE_SEEDS} = {rate:.3f} (FWER {1 - rate:.3f}) ; planted +0.25/print: exactly the planted one in "
          f"{exact}/{N_PLANTED_SEEDS} = {exact / N_PLANTED_SEEDS:.2f}, planted included in {contains}/{N_PLANTED_SEEDS}")
    assert N_NOISE_SEEDS >= 200
    assert 0.91 <= rate <= 0.995                                        # 0.95 +/- ~3 binomial SE (SE = 0.015)
    assert exact / N_PLANTED_SEEDS >= 0.80 and contains / N_PLANTED_SEEDS >= 0.90


def test_spa_size_and_power_measured():
    rejections = 0
    for seed in range(N_NOISE_SEEDS):
        rejections += M.spa(toy(30_000 + seed), reps=400, seed=seed)["p_consistent"] < 0.05
    power = 0
    for seed in range(N_PLANTED_SEEDS):
        power += M.spa(toy(40_000 + seed, planted={seed % 50: 0.25}), reps=400, seed=seed)["p_consistent"] < 0.05
    size = rejections / N_NOISE_SEEDS
    print(f"\n[measured] SPA (consistent p < 5%, default block 16, bias-corrected), 50 noise strategies x 500 prints: "
          f"rejected in {rejections}/{N_NOISE_SEEDS} = {size:.3f} ; planted +0.25/print: rejected in "
          f"{power}/{N_PLANTED_SEEDS} = {power / N_PLANTED_SEEDS:.2f}")
    assert size <= 0.095 and power / N_PLANTED_SEEDS >= 0.90


def test_stepm_size_on_autocorrelated_noise_measured():
    """AR(1) noise with coefficient 0.3 — far more persistent than daily book returns. The stationary bootstrap
    with the default block and the bias correction should keep the family-wise error near alpha; the raw
    procedure with a short block does not (see mtest.py for the 1,000-seed figures)."""
    seeds = 100
    empty = sum(M.stepm(toy(50_000 + s, K=30, ar=0.3), alpha=0.05, reps=400, seed=s)["superior"] == []
                for s in range(seeds))
    raw_short = sum(M.stepm(toy(50_000 + s, K=30, ar=0.3), alpha=0.05, block=4, reps=400, seed=s,
                            bias_correction=False)["superior"] == [] for s in range(seeds))
    print(f"\n[measured] StepM alpha=5% on AR(1)=0.3 noise (30 x 500): empty set in {empty}/{seeds} = {empty / seeds:.2f} "
          f"with the defaults ; {raw_short}/{seeds} = {raw_short / seeds:.2f} raw with block 4")
    assert empty / seeds >= 0.88 and empty >= raw_short


# --------------------------------------------------------------------------------------------------
# PBO (CSCV)
# --------------------------------------------------------------------------------------------------
def test_pbo_hand_case_no_overfit():
    # S = 2 -> two combinations (IS = block 1 / IS = block 2), rows per block = 2, N = 2.
    #   A = [0.01, 0.03 | 0.02, 0.04]   Sharpe: block 1 = 0.02/0.0141421 = 1.4142 ; block 2 = 0.03/0.0141421 = 2.1213
    #   B = [0.05, 0.01 | -0.01, -0.03] Sharpe: block 1 = 0.03/0.0282843 = 1.0607 ; block 2 = -0.02/0.0141421 = -1.4142
    # IS = block 1: A is IS-best; OOS A (2.1213) beats B -> rank 2 of 2 -> w = 2/3 -> logit = ln 2
    # IS = block 2: A is IS-best; OOS A (1.4142) beats B (1.0607) -> rank 2 -> logit = ln 2
    # PBO = 0. Degradation line through (1.4142, 2.1213) and (2.1213, 1.4142): slope -1, intercept 3.5355.
    r = pd.DataFrame({"A": [0.01, 0.03, 0.02, 0.04], "B": [0.05, 0.01, -0.01, -0.03]})
    out = M.pbo_cscv(r, S=2)
    assert out["pbo"] == 0.0 and out["n_combinations"] == 2 and out["rows_per_block"] == 2 and out["n_rows_dropped"] == 0
    np.testing.assert_allclose(out["logits"], [math.log(2), math.log(2)], rtol=1e-12)
    assert out["slope"] == pytest.approx(-1.0, rel=1e-9) and out["intercept"] == pytest.approx(5 / math.sqrt(2), rel=1e-9)
    assert out["is_best_counts"] == {"A": 2} and out["prob_oos_loss"] == 0.0


def test_pbo_hand_case_total_overfit():
    # A = [0.03, 0.05 | -0.03, -0.05]: Sharpe +2.8284 in block 1, -2.8284 in block 2 ; B is the mirror image.
    # Whichever block is IS, its best configuration is the WORST out of sample: rank 1 of 2 -> w = 1/3 -> logit = -ln 2.
    # PBO = 1 ; the IS-best always loses OOS ; both points share the same IS Sharpe, so the slope is undefined.
    r = pd.DataFrame({"A": [0.03, 0.05, -0.03, -0.05], "B": [-0.03, -0.05, 0.03, 0.05]})
    out = M.pbo_cscv(r, S=2)
    assert out["pbo"] == 1.0 and out["prob_oos_loss"] == 1.0
    np.testing.assert_allclose(out["logits"], [-math.log(2), -math.log(2)], rtol=1e-12)
    assert math.isnan(out["slope"]) and out["is_best_counts"] == {"A": 1, "B": 1}


def _pbo_reference(m: np.ndarray, S: int):
    """Slow, literal CSCV: explicit loops, np.std on the concatenated rows."""
    t, n = m.shape
    rows = t // S
    m = m[t - rows * S:]
    blocks = [m[i * rows:(i + 1) * rows] for i in range(S)]
    logits = []
    for combo in itertools.combinations(range(S), S // 2):
        is_rows = np.vstack([blocks[i] for i in combo])
        oos_rows = np.vstack([blocks[i] for i in range(S) if i not in combo])
        sr_is = is_rows.mean(axis=0) / is_rows.std(axis=0, ddof=1)
        sr_oos = oos_rows.mean(axis=0) / oos_rows.std(axis=0, ddof=1)
        star = int(np.argmax(sr_is))
        rank = 1 + int((sr_oos < sr_oos[star]).sum())
        w = rank / (n + 1)
        logits.append(math.log(w / (1 - w)))
    return np.array(logits)


@pytest.mark.parametrize("seed,S,T,N", [(0, 6, 60, 5), (1, 4, 103, 7), (2, 8, 200, 3), (3, 6, 61, 12)])
def test_pbo_equals_a_literal_reference_implementation(seed, S, T, N):
    m = np.random.default_rng(seed).normal(0.0005, 0.01, (T, N))
    out = M.pbo_cscv(m, S=S)
    ref = _pbo_reference(m, S)
    np.testing.assert_allclose(out["logits"], ref, rtol=1e-9, atol=1e-12)
    assert out["pbo"] == pytest.approx(float((ref <= 0).mean())) and out["n_combinations"] == math.comb(S, S // 2)
    assert out["n_rows_dropped"] == T % S


def test_pbo_pure_noise_is_about_one_half_and_a_real_winner_is_near_zero():
    """Measured over 30 independent noise panels (40 configurations x 1,600 prints, S = 16 -> 12,870 splits each)."""
    pbos = [M.pbo_cscv(np.random.default_rng(900 + s).normal(0, 0.01, (1600, 40)), S=16)["pbo"] for s in range(30)]
    planted = []
    for s in range(5):
        m = np.random.default_rng(950 + s).normal(0, 0.01, (1600, 40))
        m[:, 17] += 0.003                                               # +0.3 Sharpe per print: t ~ 8.5 on 800 IS prints
        planted.append(M.pbo_cscv(m, S=16))
    print(f"\n[measured] PBO (S=16) on pure noise: mean {np.mean(pbos):.3f}, min {np.min(pbos):.3f}, max {np.max(pbos):.3f} "
          f"over 30 panels ; with one real winner: max PBO {max(p['pbo'] for p in planted):.4f}")
    assert 0.42 <= np.mean(pbos) <= 0.58
    assert min(pbos) < 0.45 and max(pbos) > 0.55                         # a single PBO is a noisy number
    for p in planted:
        assert p["pbo"] < 0.01 and p["is_best_counts"] == {17: 12870} and p["n_combinations"] == 12870
        assert p["prob_oos_loss"] == 0.0


def test_pbo_validation_and_degenerate_configurations():
    m = np.random.default_rng(0).normal(0, 0.01, (64, 4))
    for bad_s in (3, 0, 1, 2.0, True):
        with pytest.raises(ValueError):
            M.pbo_cscv(m, S=bad_s)
    with pytest.raises(ValueError, match="two strategy"):
        M.pbo_cscv(m[:, :1], S=4)
    with pytest.raises(ValueError, match="row"):
        M.pbo_cscv(m[:7], S=4)
    nan = m.copy()
    nan[0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        M.pbo_cscv(nan, S=4)
    # a configuration that is constant (always flat, or a constant positive return) has no Sharpe: never the IS-best
    flat = m.copy()
    flat[:, 2] = 0.0
    flat[:, 3] = 0.01
    out = M.pbo_cscv(flat, S=4)
    assert 2 not in out["is_best_counts"] and 3 not in out["is_best_counts"]


# --------------------------------------------------------------------------------------------------
# Circular-shift null
# --------------------------------------------------------------------------------------------------
def null_panel(seed: int, T: int = 420, N: int = 4, carry: bool = True, gaps: bool = False) -> PanelBundle:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01 13:15", periods=T, freq="D", tz="UTC")
    cols = [f"c{j}" for j in range(N)]
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (T, N)), axis=0))
    if gaps:
        px[:150, 0] = np.nan                                            # a late listing inside the window
    return PanelBundle(
        "NULL", pd.DataFrame(px, index=idx, columns=cols),
        carry=pd.DataFrame(rng.normal(0, 1e-4, (T, N)), index=idx, columns=cols) if carry else None,
        meta={"periods_per_year": 100},
    )


def random_books(panel: PanelBundle, seed: int, F: int = 5):
    rng = np.random.default_rng(seed)
    T, N = panel.prices.shape
    books = {}
    for f in range(F):
        raw = rng.normal(0, 1, (T // 5 + 1, N))
        w = np.repeat(raw, 5, axis=0)[:T] * 0.3                         # persistent, unrelated to returns
        w[:20] = np.nan                                                 # warm-up
        books[f"f{f}"] = pd.DataFrame(w, index=panel.prices.index, columns=panel.prices.columns)
    return books


def test_circular_shift_observed_statistics_are_the_engines_on_the_window():
    panel = null_panel(1)
    books = random_books(panel, 2)
    idx = panel.prices.index
    win = (idx[100], idx[399])
    out = M.circular_shift_null(panel, books, window=win, cost_bp_side=5.0, seed=3, n_rep=20, min_shift=100)
    for name, w in books.items():
        res = backtest(panel, w, cost_bp_side=5.0)
        st = S.summarize(res.net, periods_per_year=100, window=win)
        assert out["observed_hac_t"][name] == pytest.approx(st["hac_t"], rel=1e-12)
        assert out["observed_sharpe"][name] == pytest.approx(st["sharpe"], rel=1e-12)
    assert out["turnover_model"] == "drift"                               # the engine's default: the ledger's numbers
    tgt = M.circular_shift_null(panel, books, window=win, cost_bp_side=5.0, seed=3, n_rep=20, min_shift=100,
                                turnover_model="target")
    for name, w in books.items():
        st = S.summarize(backtest(panel, w, cost_bp_side=5.0, turnover_model="target").net, periods_per_year=100, window=win)
        assert tgt["observed_hac_t"][name] == pytest.approx(st["hac_t"], rel=1e-12)
        assert tgt["observed_hac_t"][name] > out["observed_hac_t"][name]  # free re-balancing flatters every book
    assert tgt["turnover_model"] == "target" and not np.array_equal(tgt["max_hac_t"], out["max_hac_t"])
    assert out["n_window_rows"] == 300 and out["window"] == (idx[100].isoformat(), idx[399].isoformat())
    assert out["observed_max_hac_t"] == max(out["observed_hac_t"].values())
    assert out["offset_range"] == (100, 200) and ((out["offsets"] >= 100) & (out["offsets"] <= 200)).all()


@pytest.mark.parametrize("exec_mode", [False, True])
def test_circular_shift_replicates_equal_a_slow_reference(exec_mode):
    """One formula, so the per-replicate maximum IS that formula's statistic: recompute it with explicit loops."""
    panel = null_panel(4, gaps=True)
    books = random_books(panel, 5, F=1)
    idx = panel.prices.index
    win = (idx[60], idx[359])
    kw = dict(cost_bp_side=pd.Series({"c0": 3.0, "c1": 6.0, "c2": 0.0, "c3": 12.0}),
              hold_cost_long_bp_year=40.0, hold_cost_short_bp_year=90.0)
    if exec_mode:
        panel.meta["exec_prices_strictly_after_decision"] = True
        kw.update(exec_prices=panel.prices * np.exp(np.random.default_rng(6).normal(0, 0.003, panel.prices.shape)),
                  extra_lag=1)
    else:
        kw.update(lag=2)
    out = M.circular_shift_null(panel, books, window=win, seed=9, n_rep=8, min_shift=50, hac_lags=3, **kw)
    res = backtest(panel, books["f0"], missing_return="zero", **kw)
    mask = S.window_mask(idx, win)
    H = res.held.to_numpy()[mask]
    C = (res.cost + res.hold_cost).to_numpy()[mask]
    px = (kw["exec_prices"] if exec_mode else panel.prices).to_numpy()
    r = np.full(px.shape, np.nan)
    r[1:] = px[1:] / px[:-1] - 1
    x = np.nan_to_num(r[mask]) + np.nan_to_num(panel.carry.to_numpy()[mask])
    tw, n = H.shape
    for j, u in enumerate(out["offsets"]):
        net = np.zeros(tw)
        for t in range(tw):
            s = (t - int(u)) % tw
            net[t] = sum(H[s, i] * x[t, i] for i in range(n)) - C[s]
        assert out["max_hac_t"][j] == pytest.approx(S.newey_west_t(net, 3), rel=1e-9)
        assert out["max_sharpe"][j] == pytest.approx(S.sharpe_ratio(net, 100), rel=1e-9)
        assert out["argmax_hac_t_ids"][j] == "f0" and out["argmax_sharpe_ids"][j] == "f0"
    assert out["n_nan_return_cells_in_window"] > 0 and 0 < out["mean_frac_exposure_on_missing"] < 1
    assert out["shift"] == (2 if exec_mode else 3) and out["priced_on"] == ("exec_prices" if exec_mode else "prices")


def test_one_shared_offset_per_replicate_and_every_replicate_pays_the_real_costs():
    panel = null_panel(7)
    books = random_books(panel, 8, F=3)
    books["twin"] = books["f0"].copy()                                  # same book twice
    idx = panel.prices.index
    win = (idx[100], None)
    out = M.circular_shift_null(panel, books, window=win, cost_bp_side=20.0, seed=5, n_rep=30, min_shift=100)
    assert out["observed_hac_t"]["twin"] == out["observed_hac_t"]["f0"] and out["adjusted_p"]["twin"] == out["adjusted_p"]["f0"]
    # zero-return, zero-carry world: net' is the rolled cost series, so every replicate has the real mean and std
    flat = PanelBundle("NULL", pd.DataFrame(100.0, index=idx, columns=panel.prices.columns), meta={"periods_per_year": 100})
    one = {"f0": books["f0"]}
    z = M.circular_shift_null(flat, one, window=win, cost_bp_side=20.0, seed=5, n_rep=30, min_shift=100)
    assert z["observed_sharpe"]["f0"] < 0
    np.testing.assert_allclose(z["max_sharpe"], z["observed_sharpe"]["f0"], rtol=1e-9)


def test_statistics_use_only_the_window():
    """Prices after the window's end, and targets that only take effect after it, cannot change the null."""
    panel = null_panel(10)
    books = random_books(panel, 11, F=3)
    idx = panel.prices.index
    win = (idx[80], idx[329])
    base = M.circular_shift_null(panel, books, window=win, cost_bp_side=4.0, seed=1, n_rep=15, min_shift=80)
    px2 = panel.prices.copy()
    px2.iloc[330:] = px2.iloc[330:] * 3.0
    carry2 = panel.carry.copy()
    carry2.iloc[330:] = 0.5
    books2 = {k: v.copy() for k, v in books.items()}
    for v in books2.values():
        v.iloc[328:] = 9.9                                              # decided at row 328, first held at row 330
    alt = M.circular_shift_null(PanelBundle("NULL", px2, carry=carry2, meta=dict(panel.meta)), books2, window=win,
                                cost_bp_side=4.0, seed=1, n_rep=15, min_shift=80)
    np.testing.assert_array_equal(base["max_hac_t"], alt["max_hac_t"])
    np.testing.assert_array_equal(base["max_sharpe"], alt["max_sharpe"])
    assert base["observed_hac_t"] == alt["observed_hac_t"]
    # ...whereas a change INSIDE the window does move it
    px3 = panel.prices.copy()
    px3.iloc[200:] = px3.iloc[200:] * 1.2
    moved = M.circular_shift_null(PanelBundle("NULL", px3, carry=panel.carry, meta=dict(panel.meta)), books, window=win,
                                  cost_bp_side=4.0, seed=1, n_rep=15, min_shift=80)
    assert not np.array_equal(base["max_hac_t"], moved["max_hac_t"])


def test_a_static_position_is_inside_the_null_by_construction():
    """Stated limit: shifting a constant exposure changes nothing, so its p-value is 1 whatever it earned."""
    panel = null_panel(12, carry=False)
    drift = panel.prices * np.exp(0.002 * np.arange(len(panel.prices)))[:, None]      # a strong positive drift
    panel = PanelBundle("NULL", drift, meta={"periods_per_year": 100})
    w = pd.DataFrame(0.25, index=panel.prices.index, columns=panel.prices.columns)
    win = (panel.prices.index[50], None)
    out = M.circular_shift_null(panel, {"hold": w}, window=win, cost_bp_side=2.0, seed=1, n_rep=40, min_shift=100,
                                turnover_model="target")
    assert out["observed_hac_t"]["hold"] > 3                             # genuinely profitable...
    np.testing.assert_allclose(out["max_hac_t"], out["observed_hac_t"]["hold"], rtol=1e-9)
    assert out["p_value_max_hac_t"] == 1.0                               # ...and not distinguishable by THIS null
    # Under the default drift model the constant book pays a little on every print to stay at 25 % each; a shift
    # moves those costs to other prints, so the replicates differ from the observed statistic — in the fifth digit.
    # The conclusion is the same: nowhere near a small p-value.
    drift = M.circular_shift_null(panel, {"hold": w}, window=win, cost_bp_side=2.0, seed=1, n_rep=40, min_shift=100)
    assert drift["turnover_model"] == "drift" and drift["observed_hac_t"]["hold"] < out["observed_hac_t"]["hold"]
    np.testing.assert_allclose(drift["max_hac_t"], drift["observed_hac_t"]["hold"], rtol=1e-4)
    assert not np.allclose(drift["max_hac_t"], drift["observed_hac_t"]["hold"], rtol=1e-9)
    assert drift["p_value_max_hac_t"] > 0.2


def test_planted_timing_skill_clears_the_null_and_noise_does_not():
    panel = null_panel(13, T=520)
    books = random_books(panel, 14, F=6)
    r = panel.returns()
    # a (deliberately illegal) clairvoyant: the target at s is the sign of r at s+2, so held_t = sign(r_t)
    books["oracle"] = np.sign(r.shift(-2)).fillna(0.0) * 0.2
    win = (panel.prices.index[100], panel.prices.index[499])
    out = M.circular_shift_null(panel, books, window=win, cost_bp_side=1.0, seed=2, n_rep=199, min_shift=100)
    assert out["observed_argmax_id"] == "oracle" and out["observed_max_hac_t"] > 15
    assert out["p_value_max_hac_t"] == pytest.approx(1 / 200)             # (1 + 0) / (1 + 199)
    assert out["adjusted_p"]["oracle"] == pytest.approx(1 / 200)
    assert out["observed_max_hac_t"] > 3 * out["p95_max_hac_t"] > 0
    assert out["p50_max_hac_t"] < out["p95_max_hac_t"] and out["p50_max_sharpe"] < out["p95_max_sharpe"]
    assert len(out["max_hac_t"]) == 199 and len(out["argmax_hac_t_ids"]) == 199 and out["n_rep_finite"] == 199
    assert all(a in books for a in out["argmax_hac_t_ids"])
    for name in books:
        if name != "oracle":
            assert out["adjusted_p"][name] > 0.02                        # the noise books do not clear the bar
    again = M.circular_shift_null(panel, books, window=win, cost_bp_side=1.0, seed=2, n_rep=199, min_shift=100)
    np.testing.assert_array_equal(out["max_hac_t"], again["max_hac_t"])   # seeded, deterministic


def test_circular_shift_null_size_on_noise_measured():
    """Books unrelated to returns: the observed maximum should fall above the null's p90 about 10 % of the time."""
    trials, hits = 60, 0
    for s in range(trials):
        panel = null_panel(1000 + s, T=360, N=3, carry=False)
        books = random_books(panel, 2000 + s, F=6)
        out = M.circular_shift_null(panel, books, window=(panel.prices.index[40], None), cost_bp_side=0.0, seed=s,
                                    n_rep=99, min_shift=60)
        hits += out["p_value_max_hac_t"] <= 0.10
    print(f"\n[measured] circular-shift null on noise books: P(p <= 0.10) = {hits / trials:.3f} ({hits}/{trials})")
    assert hits / trials <= 0.25


def test_circular_shift_null_refusals():
    panel = null_panel(15)
    books = random_books(panel, 16, F=2)
    idx = panel.prices.index
    ok = dict(window=(idx[100], None), cost_bp_side=5.0, seed=1, n_rep=5, min_shift=100)
    with pytest.raises(Refused, match="at least one formula"):
        M.circular_shift_null(panel, {}, **ok)
    with pytest.raises(Refused, match="offset range"):
        M.circular_shift_null(panel, books, **dict(ok, min_shift=200))
    with pytest.raises(Refused, match="window is required"):
        M.circular_shift_null(panel, books, **dict(ok, window=None))
    with pytest.raises(Refused, match="seed"):
        M.circular_shift_null(panel, books, **dict(ok, seed=1.5))
    with pytest.raises(Refused, match="n_rep"):
        M.circular_shift_null(panel, books, **dict(ok, n_rep=0))
    with pytest.raises(Refused, match="max_bytes"):
        M.circular_shift_null(panel, books, max_bytes=1000, **ok)
    with pytest.raises(Refused, match="cost_bp_side"):
        M.circular_shift_null(panel, books, **dict(ok, cost_bp_side=None))
    with pytest.raises(Refused, match="lag"):
        M.circular_shift_null(panel, books, lag=0, **ok)
    with pytest.raises(TypeError):
        M.circular_shift_null(panel, books, window=(idx[100], None), cost_bp_side=5.0)      # seed is required
    # default min_shift = one year of prints (periods_per_year = 100 here); (None, None) scores every row
    out = M.circular_shift_null(panel, books, window=(None, None), cost_bp_side=5.0, seed=1, n_rep=3)
    assert out["min_shift"] == 100 and out["n_window_rows"] == len(idx)


def test_nulls_shim_points_at_mtest():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from scripts.factory import nulls
    assert nulls.circular_shift_null is M.circular_shift_null
    assert M.sharpe_ci_bootstrap is S.sharpe_ci_bootstrap
