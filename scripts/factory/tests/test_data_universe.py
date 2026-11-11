"""Point-in-time universe mask: known answers and the truncation (no-lookahead) property.
Synthetic frames only — no files, no network."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.factory.data.universe import mask_summary, pit_universe_mask, trailing_mean_volume


def _frame(rows: int, cols: int, seed: int = 0, *, holes: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=rows, freq="D", tz="UTC")
    scale = np.exp(rng.normal(0, 2.0, size=cols))
    v = np.exp(rng.normal(0, 1.0, size=(rows, cols)).cumsum(axis=0) * 0.05) * scale * 1e6
    df = pd.DataFrame(v, index=idx, columns=[f"S{i:02d}" for i in range(cols)])
    if holes:
        for j in range(cols):                       # staggered listings, a few delistings, a few halts
            start = int(rng.integers(0, rows // 2)) if j % 3 else 0
            df.iloc[:start, j] = np.nan
            if j % 7 == 3:
                df.iloc[int(rows * 0.8):, j] = np.nan
            if j % 5 == 1:
                h = int(rng.integers(start + 5, rows - 5))
                df.iloc[h:h + 2, j] = np.nan
    return df


def test_truncation_mask_row_t_ignores_everything_after_t():
    qv = _frame(400, 45, seed=1)
    full = pit_universe_mask(qv, top_n=10, min_history=60, vol_window=30)
    rng = np.random.default_rng(99)
    for t in (61, 95, 150, 233, 398):
        alt = qv.copy()
        # scramble every row after t: new values, new NaN pattern, even permuted columns of data
        tail = alt.iloc[t + 1:].to_numpy(copy=True)
        tail = rng.permutation(tail.T).T * rng.uniform(0.01, 100.0, size=tail.shape)
        tail[rng.random(tail.shape) < 0.3] = np.nan
        alt.iloc[t + 1:] = tail
        m2 = pit_universe_mask(alt, top_n=10, min_history=60, vol_window=30)
        pd.testing.assert_frame_equal(full.iloc[: t + 1], m2.iloc[: t + 1])
        # and on a frame physically cut at t
        m3 = pit_universe_mask(qv.iloc[: t + 1], top_n=10, min_history=60, vol_window=30)
        pd.testing.assert_frame_equal(full.iloc[: t + 1], m3)


def test_mask_changes_when_the_past_changes():
    """The truncation test must be able to fail: altering rows <= t does move the mask."""
    qv = _frame(300, 30, seed=3, holes=False)
    full = pit_universe_mask(qv, top_n=5, min_history=60, vol_window=30)
    alt = qv.copy()
    loser = full.columns[~full.iloc[200].to_numpy()][0]
    alt.loc[alt.index[171:201], loser] = alt.to_numpy().max() * 1e3
    m2 = pit_universe_mask(alt, top_n=5, min_history=60, vol_window=30)
    assert m2.iloc[200][loser] and not full.iloc[200][loser]


def test_known_answer_small():
    idx = pd.date_range("2022-01-01", periods=8, freq="D", tz="UTC")
    qv = pd.DataFrame({"A": [10, 10, 10, 10, 10, 10, 10, 10],
                       "B": [np.nan, np.nan, 50, 50, 50, 50, 50, 50],
                       "C": [5, 5, 5, 5, np.nan, 5, 5, 5],
                       "D": [1, 1, 1, 1, 1, 1, 100, 100]}, index=idx, dtype="float64")
    m = pit_universe_mask(qv, top_n=2, min_history=3, vol_window=2)
    # row 3 (4th row): A has 3 prior candles -> eligible, rank by 2-candle mean: B 50 (only 1 prior -> too young), A 10, C 5, D 1
    assert m.iloc[3].to_dict() == {"A": True, "B": False, "C": False, "D": False}
    # row 5: B now has 3 prior candles (rows 2,3,4); C's window (rows 4,5) is incomplete -> unranked
    assert m.iloc[5].to_dict() == {"A": True, "B": True, "C": False, "D": False}
    # row 7: means A 10, B 50, C 5, D 100 -> top-2 = D, B
    assert m.iloc[7].to_dict() == {"A": False, "B": True, "C": False, "D": True}
    # nothing can be in the mask before `min_history` prior candles exist
    assert not m.iloc[:3].to_numpy().any()


def test_young_instrument_keeps_its_rank_slot():
    """Literal reading: rank among ALL instruments with a complete window, then require the history."""
    idx = pd.date_range("2022-01-01", periods=70, freq="D", tz="UTC")
    qv = pd.DataFrame({"OLD1": 10.0, "OLD2": 9.0, "OLD3": 8.0}, index=idx)
    qv["NEW"] = np.nan
    qv.loc[idx[30:], "NEW"] = 1000.0                 # listed on row 30, by far the largest volume
    m = pit_universe_mask(qv, top_n=2, min_history=60, vol_window=30)
    row = m.iloc[65]                                  # NEW: 35 prior candles (< 60) but a complete 30-window
    assert not row["NEW"] and row["OLD1"] and not row["OLD2"] and not row["OLD3"]
    assert int(m.iloc[65].sum()) == 1                 # the young name occupies a slot -> fewer than top_n members


def test_requires_trade_at_t_and_complete_window():
    idx = pd.date_range("2022-01-01", periods=160, freq="D", tz="UTC")
    qv = pd.DataFrame({"A": 5.0, "B": 3.0}, index=idx)
    qv.loc[idx[100], "A"] = np.nan                    # one missing candle
    m = pit_universe_mask(qv, top_n=1, min_history=60, vol_window=30)
    assert m["A"].iloc[99] and not m["A"].iloc[100]
    assert not m["A"].iloc[101:130].any()             # the 30-candle window is incomplete for the next 29 rows
    assert m["B"].iloc[100:130].all()                 # B takes the slot meanwhile
    assert m["A"].iloc[130:].all() and not m["B"].iloc[130:].any()
    tm = trailing_mean_volume(qv, 30)
    assert np.isnan(tm["A"].iloc[100]) and np.isnan(tm["A"].iloc[129]) and tm["A"].iloc[130] == 5.0


def test_dead_instrument_leaves_the_mask_and_summary():
    idx = pd.date_range("2022-01-01", periods=200, freq="D", tz="UTC")
    qv = pd.DataFrame({"A": 5.0, "B": 3.0, "C": 1.0}, index=idx)
    qv.loc[idx[150:], "A"] = np.nan                   # delisted: phantom candles are NaN in this layer
    m = pit_universe_mask(qv, top_n=2, min_history=60, vol_window=30)
    assert m["A"].iloc[60:150].all() and not m["A"].iloc[150:].any()
    s = mask_summary(m)
    assert s["ever_in_mask"] == 3 and s["members_per_row_max"] == 2
    assert s["first_row_with_member"].startswith("2022-03-02")


def test_bad_inputs_refused():
    idx = pd.date_range("2022-01-01", periods=5, freq="D", tz="UTC")
    qv = pd.DataFrame({"A": 1.0}, index=idx)
    with pytest.raises(ValueError):
        pit_universe_mask(qv.iloc[::-1], top_n=1)
    with pytest.raises(ValueError):
        pit_universe_mask(qv, top_n=0)


# ------------------------------------------------------------------------------- trading-break segments
from scripts.factory.data.crypto_build import SEG, base_symbol, split_segments  # noqa: E402


def _seg_frame():
    idx = pd.date_range("2022-01-01", periods=40, freq="D", tz="UTC")
    px = pd.DataFrame({"AAA": 1.0, "BBB": 2.0, "CCC": 3.0}, index=idx)
    px.loc[idx[10:13], "AAA"] = np.nan          # 3 missing days  -> split
    px.loc[idx[20:22], "BBB"] = np.nan          # 2 missing days  -> stays one instrument
    px.loc[idx[5:9], "CCC"] = np.nan            # 4 missing days  -> split
    px.loc[idx[25:30], "CCC"] = np.nan          # 5 missing days  -> split again
    px.loc[idx[:3], "BBB"] = np.nan             # not listed yet: no effect
    return px, px * 1000.0


def test_split_segments_names_and_content():
    px, qv = _seg_frame()
    spx, sqv, info = split_segments(px, qv, gap_days=3)
    assert sorted(spx.columns) == sorted(["AAA", "AAA@20220110", "BBB", "CCC", "CCC@20220105", "CCC@20220125"])
    assert spx["AAA@20220110"].notna().sum() == 10 and spx["AAA@20220110"].last_valid_index() == px.index[9]
    assert spx["AAA"].first_valid_index() == px.index[13] and spx["AAA"].notna().sum() == 27
    assert spx["BBB"].notna().sum() == 35                       # the 2-day hole stays inside one instrument
    assert info["CCC"]["segment"] == 3 and info["CCC"]["of"] == 3 and info["CCC@20220105"]["segment"] == 1
    assert base_symbol("CCC@20220105") == "CCC" and base_symbol("BBB") == "BBB" and SEG == "@"
    # nothing is created or lost: per symbol the union of the segments is the original series
    for b in ("AAA", "BBB", "CCC"):
        cols = [c for c in spx.columns if base_symbol(c) == b]
        merged = spx[cols].bfill(axis=1).iloc[:, 0]
        pd.testing.assert_series_equal(merged.rename(b), px[b])
        assert (spx[cols].notna().sum(axis=1) <= 1).all()       # segments never overlap
        pd.testing.assert_frame_equal(sqv[cols], spx[cols] * 1000.0)
    # no instrument keeps a break of >= 3 days inside itself
    for c in spx.columns:
        v = spx[c].notna().to_numpy()
        pos = np.flatnonzero(v)
        assert (np.diff(pos) <= 3).all()


def test_split_segments_is_causal():
    """Cutting the frame at row t never changes the CONTENT of what was known by t (only the name of the
    segment that is still open, which carries the plain symbol until a later break closes it)."""
    px, qv = _seg_frame()
    full, _, info = split_segments(px, qv, gap_days=3)
    key = lambda inf: (inf["base"], inf["first_row"])
    by_key = {key(info[c]): full[c] for c in full.columns}
    for t in (4, 9, 12, 13, 24, 27, 31, 39):
        cut, _, inf_t = split_segments(px.iloc[: t + 1], qv.iloc[: t + 1], gap_days=3)
        for c in cut.columns:
            want = by_key[key(inf_t[c])].iloc[: t + 1]
            got = cut[c]
            assert np.array_equal(want.to_numpy(), got.to_numpy(), equal_nan=True), (t, c)
