"""Tests for scripts/factory/forward_crypto.py — the forward paper logger.

Synthetic only: no network, no real ledger, nothing written outside pytest's tmp directories.

  * ledger: hash chain, tamper detection, torn last line;
  * the forward-start row from PIN.json;
  * A0 / C252 scaling and the 2x cap against hand-computed answers, and all five arms against v2's own calls;
  * replay on the synthetic CRYPTO-PERP lane (the conductor's `v2.Ctx(synthetic=True)` panel): rows, fields,
    idempotency, immutability refusal, the truncation property, the stop rule, the 60-row reading;
  * the forward store: first observation wins, raw responses re-hash and re-parse to the parsed tables;
  * A FABRICATED EXCHANGE served through a fake transport: the v2 data layer's own `_assemble` builds the
    "frozen" lane from a raw tree, the logger extends it day by day through `cmd_run`, and the extension is
    compared cell by cell with what `_assemble` gives once it has seen the later days — equal everywhere
    except the stated causal differences (settlement row, a non-traded row inside a halt).

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_forward_crypto.py -q
"""
from __future__ import annotations

import email.utils
import json
import urllib.parse
import zipfile

import numpy as np
import pandas as pd
import pytest

from scripts.factory import forward_crypto as fc
from scripts.factory import portfolio, realism, v2, v2_extras
from scripts.factory.data import crypto as C
from scripts.factory.data import crypto_build as CB
from scripts.factory.panel import PanelBundle
from scripts.factory.strategies import registry
from scripts.factory.strategies.common import size_positions

H, D = fc.HOUR, fc.DAY
PIN = {"sha256": "ab" * 32, "frozen_utc": "2023-07-01T12:00:00Z", "preregistration": "synthetic"}
QUIET = lambda *a, **k: None  # noqa: E731


# ==================================================================================================
# ledger
# ==================================================================================================
def _rows(n=4):
    return [{"date": f"2026-11-{11 + k // 2:02d}", "arm": "A60", "account": "IDEAL" if k % 2 == 0 else "KRAKEN-5K",
             "equity": 5597.0 + 0.1 * k, "net_return": 1e-3 * k, "top_positions": [["BTCUSDT", 0.1]]} for k in range(n)]


def test_hash_chain_round_trip_and_tamper_detection(tmp_path):
    g = fc.genesis_hash(PIN)
    p = tmp_path / "ledger.jsonl"
    first = fc.chain(_rows(4), g)
    fc.append_ledger(p, first[:2])
    fc.append_ledger(p, first[2:])
    rows = fc.read_ledger(p)
    assert rows == first and fc.verify_chain(rows, g) == first[-1]["row_hash"]
    assert rows[0]["prev_hash"] == g and rows[1]["prev_hash"] == rows[0]["row_hash"]
    assert fc.genesis_hash(PIN, "replay:2026-01-01") != g                      # a replay ledger cannot be spliced into the real one

    lines = p.read_text().splitlines()
    # (1) a value edited in place: the row no longer hashes to its row_hash
    bad = tmp_path / "edited.jsonl"
    bad.write_text("\n".join([lines[0], lines[1].replace('"equity":5597.1', '"equity":5598.1')] + lines[2:]) + "\n")
    with pytest.raises(fc.Incident) as e:
        fc.verify_chain(fc.read_ledger(bad), g)
    assert e.value.kind == "LEDGER_CHAIN" and "row 2" in str(e.value)
    # (2) a row removed, (3) two rows swapped: prev_hash no longer continues the chain
    for name, sel in (("removed", [0, 2, 3]), ("swapped", [0, 2, 1, 3])):
        q = tmp_path / f"{name}.jsonl"
        q.write_text("\n".join(lines[i] for i in sel) + "\n")
        with pytest.raises(fc.Incident) as e:
            fc.verify_chain(fc.read_ledger(q), g)
        assert e.value.kind == "LEDGER_CHAIN"
    # (4) a row rewritten with a freshly computed row_hash: the NEXT row's prev_hash gives it away
    forged = dict(rows[1], equity=9999.0)
    forged["row_hash"] = fc.row_hash(forged)
    q = tmp_path / "forged.jsonl"
    q.write_text("\n".join([lines[0], fc.canonical(forged)] + lines[2:]) + "\n")
    with pytest.raises(fc.Incident) as e:
        fc.verify_chain(fc.read_ledger(q), g)
    assert "row 3" in str(e.value)
    # (5) a torn last line, (6) a line that is not canonical JSON, (7) another genesis
    q = tmp_path / "torn.jsonl"
    q.write_text("\n".join(lines) + "\n" + lines[0][:40])
    with pytest.raises(fc.Incident) as e:
        fc.read_ledger(q)
    assert e.value.kind == "LEDGER_TORN"
    q = tmp_path / "spaced.jsonl"
    q.write_text(lines[0].replace('":', '": ', 1) + "\n")
    with pytest.raises(fc.Incident):
        fc.read_ledger(q)
    with pytest.raises(fc.Incident):
        fc.verify_chain(rows, fc.genesis_hash(dict(PIN, sha256="cd" * 32)))


def test_canonical_json_refuses_nothing_silently():
    assert fc.canonical({"b": 1, "a": [1.5, None, "é"]}) == '{"a":[1.5,null,"\\u00e9"],"b":1}'
    assert fc.canonical({"x": float("nan")}) == '{"x":null}'                    # v2.jsonable: an unknown number is null, never NaN
    r = fc.chain([{"x": np.float64(0.1), "n": np.int64(3)}], "g")[0]
    assert json.loads(fc.canonical(r)) == r and r["row_hash"] == fc.row_hash(r)


# ==================================================================================================
# forward start
# ==================================================================================================
def test_forward_start_row_is_the_first_midnight_after_the_freeze_in_the_real_pin():
    pin = fc.load_pin()
    assert pin["frozen_utc"] == "2026-11-10T18:13:17Z"
    idx = pd.date_range("2026-11-01", "2026-11-20", freq="D", tz="UTC")
    start = fc.forward_start_row(idx, pin["frozen_utc"])
    assert start == pd.Timestamp("2026-11-11", tz="UTC") == fc.forward_start_label(pin["frozen_utc"])
    assert fc.forward_start_row(idx[:10], pin["frozen_utc"]) is None            # the panel ends 2026-11-10: no forward row yet
    # a freeze exactly at midnight: that row closed AT the freeze, not after it
    assert fc.forward_start_row(idx, "2026-11-10T00:00:00Z") == pd.Timestamp("2026-11-11", tz="UTC")
    assert fc.forward_start_label("2026-11-10T00:00:00Z") == pd.Timestamp("2026-11-11", tz="UTC")
    assert fc.forward_start_row(idx, "2026-11-09T23:59:59Z") == pd.Timestamp("2026-11-10", tz="UTC")


def test_a_row_is_appendable_only_ten_minutes_after_its_0100_print():
    t = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731
    assert fc.last_appendable_row(t("2026-11-11 01:09:59")) == t("2026-11-10")
    assert fc.last_appendable_row(t("2026-11-11 01:10:00")) == t("2026-11-11")
    assert fc.last_appendable_row(t("2026-11-11 23:59:00")) == t("2026-11-11")
    assert fc.last_final_hour(t("2026-11-11 01:10:00")) == t("2026-11-11 00:00")   # the candle that closed at 01:00
    assert fc.last_final_hour(t("2026-11-11 02:09:00")) == t("2026-11-11 00:00")   # the 02:00 print is not final yet


# ==================================================================================================
# arms
# ==================================================================================================
def test_cap_and_static_mean_known_answers():
    idx = pd.date_range("2026-01-01", periods=3, freq="D", tz="UTC")
    b1 = pd.DataFrame([[0.1, -0.1], [0.4, 0.4], [0.0, 0.0]], index=idx, columns=["X", "Y"])
    b2 = pd.DataFrame([[0.3, 0.1], [0.4, 0.2], [0.0, 0.0]], index=idx, columns=["X", "Y"])
    mean = fc.static_mean({"r1": b1, "r2": b2})
    np.testing.assert_allclose(mean.to_numpy(), [[0.2, 0.0], [0.4, 0.3], [0.0, 0.0]], rtol=0, atol=1e-15)
    a0 = fc.cap_gross(mean * fc.A0_FACTOR, fc.GROSS_CAP)                         # x 4.0: rows 0.8 | 1.6 + 1.2 = 2.8 | 0
    np.testing.assert_allclose(a0.to_numpy(), [[0.8, 0.0], [1.6 * 2 / 2.8, 1.2 * 2 / 2.8], [0.0, 0.0]], rtol=0, atol=1e-15)
    assert a0.abs().sum(axis=1).tolist() == pytest.approx([0.8, 2.0, 0.0], abs=1e-12)
    w = pd.DataFrame([[0.1, -0.05], [0.2, -0.2], [0.25, 0.0]], index=idx, columns=["X", "Y"])
    c = fc.cap_gross(w * fc.C252_FACTOR, fc.GROSS_CAP)                           # x 8.0: 0.8, -0.4 | 1.6, -1.6 -> 1, -1 | 2.0 (at the cap, untouched)
    np.testing.assert_allclose(c.to_numpy(), [[0.8, -0.4], [1.0, -1.0], [2.0, 0.0]], rtol=0, atol=1e-15)
    assert (fc.A0_FACTOR, fc.C252_FACTOR, fc.GROSS_CAP) == (4.0, 8.0, 2.0) == (4.0, 8.0, v2.LANES["CRYPTO-PERP"].max_gross)


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    """The conductor's synthetic CRYPTO-PERP lane (with its fabricated 01:00 prints) and Kraken payloads."""
    ctx = v2.Ctx(True, str(tmp_path_factory.mktemp("v2ctx")))
    panel, cfg = ctx.panel("CRYPTO-PERP"), ctx.cfg("CRYPTO-PERP")
    ev = v2_extras.synthetic_evidence(ctx, 1.1)
    arms, info = fc.build_arms(panel, cfg, enforce_members=False)
    return {"ctx": ctx, "panel": panel, "cfg": cfg, "kraken": fc.KrakenInput(ev, {"note": "synthetic"}, panel), "arms": arms,
            "arm_info": info}


def test_the_five_arms_are_v2s_own_calls(synth):
    panel, cfg, arms = synth["panel"], synth["cfg"], synth["arms"]
    spec = next(s for s in registry.primaries() if s.id == "P.CRYPTO.TREND")
    b = v2.build_primary(synth["ctx"], spec)
    kept = [m["rule_id"] for m in b["members"] if m["kept"]]
    assert len(kept) >= 2 and list(arms) == list(fc.ARMS)
    assert np.array_equal(arms["A60"].to_numpy(), b["w"].to_numpy())             # A60 IS the primary's frame
    books = {rid: size_positions(registry.get(rid).signal(panel), panel, cfg.sigma) for rid in kept}
    fam = {rid: registry.get(rid).family for rid in kept}
    for name, win in (("A30", 30), ("A120", 120)):
        ref = portfolio.vol_target(portfolio.ensemble(books, fam, panel, vol_window=win, target=cfg.sigma), panel, 0.20,
                                   vol_window=win, max_gross=2.0)
        assert np.array_equal(arms[name].to_numpy(), ref.to_numpy())
        assert not np.array_equal(arms[name].to_numpy(), arms["A60"].to_numpy())
    mean = sum(b_.to_numpy() for b_ in books.values()) / len(books)
    np.testing.assert_allclose(arms["A0"].to_numpy(), fc.cap_gross(pd.DataFrame(mean * 4.0), 2.0).to_numpy(), rtol=0, atol=1e-15)
    hp = size_positions(registry.get("XSMOM.HIGH_PROXIMITY.L252").signal(panel), panel, cfg.sigma)
    assert np.array_equal(arms["C252"].to_numpy(), fc.cap_gross(hp * 8.0, 2.0).to_numpy())
    for name in fc.ARMS:
        assert float(arms[name].abs().sum(axis=1).max()) <= 2.0 + 1e-12 and not arms[name].isna().any().any()
    # where the cap does not bind, C252 is exactly eight times the v2 rule book
    free = (hp.abs().sum(axis=1) * 8.0 <= 2.0).to_numpy()
    assert free.sum() > 100 and np.array_equal(arms["C252"].to_numpy()[free], (hp * 8.0).to_numpy()[free])


def test_a_dropped_member_refuses_the_registered_book(synth):
    """On the synthetic lane the speed limit drops members: with enforcement on (the real setting) that is an
    incident, because the registered book has all 20."""
    info = synth["arm_info"]
    assert info["declared_members"] == 20
    if info["kept_members"] == 20:
        pytest.skip("the synthetic lane happens to keep all 20 members")
    with pytest.raises(fc.Incident) as e:
        fc.build_arms(synth["panel"], synth["cfg"], enforce_members=True)
    assert e.value.kind == "SPEED_LIMIT" and e.value.detail["dropped_by_speed_limit"]


# ==================================================================================================
# replay on the synthetic lane
# ==================================================================================================
def _replay(synth, tmp, start_i, asof_i, **kw):
    idx = synth["panel"].prices.index
    return fc.replay_step(fc.Paths(tmp), synth["panel"], cfg=synth["cfg"], start=idx[start_i], asof=idx[asof_i], pin=PIN,
                          kraken=synth["kraken"], base_id="synthetic", enforce_members=False, say=QUIET, **kw)


def _content(row):
    return {k: v for k, v in row.items() if k not in ("backfilled", "run_utc", "prev_hash", "row_hash")}


S0 = 1400                                                                       # forward-start row of the synthetic replays


def test_replay_appends_one_row_per_account_per_day_and_is_idempotent(synth, tmp_path):
    idx = synth["panel"].prices.index
    run = _replay(synth, tmp_path, S0, S0 + 10)
    assert run["status"] == "APPENDED" and run["exit_code"] == 0 and run["advance"]["rows_appended"] == 11 * 10
    paths = fc.Paths(tmp_path)
    rows = fc.read_ledger(paths.ledger)
    fc.verify_chain(rows, fc.genesis_hash(PIN, f"replay:{fc.day(idx[S0])}"))
    assert len(rows) == 110 and {(r["arm"], r["account"]) for r in rows} == {(a, b) for a in fc.ARMS for b in fc.ACCOUNTS}
    need = {"date", "arm", "account", "equity", "net_return", "gross_return", "gross_exposure", "net_exposure", "n_positions",
            "turnover", "fees", "funding", "top_positions", "data_sha256", "backfilled", "run_utc", "prev_hash", "row_hash"}
    assert all(need <= set(r) for r in rows)
    first = [r for r in rows if r["date"] == fc.day(idx[S0])]
    for r in first:                                                              # flat until the 01:00 fill of the start row
        assert r["n"] == 1 and r["net_return"] == 0.0 and r["gross_return"] == 0.0 and r["funding"] == 0.0
        assert r["equity"] == pytest.approx(fc.EQUITY0 - r["fees"] - r["spread"], abs=1e-9) and r["equity"] < fc.EQUITY0
        assert r["exec_utc"] == fc.iso(idx[S0] + pd.Timedelta(hours=1))
    ideal = [r for r in rows if r["account"] == "IDEAL"]
    kr = [r for r in rows if r["account"] == "KRAKEN-5K"]
    assert all(r["spread"] == 0.0 and r["unheld_share"] in (0.0, None) and r["venue_sha256"] is None for r in ideal)
    assert all(len(r["top_positions"]) <= 10 for r in rows)
    # 7 bp on the ideal venue, 5 + 2 bp at Kraken: fees / turnover
    r0 = next(r for r in first if r["arm"] == "A60" and r["account"] == "IDEAL")
    assert r0["fees"] / (r0["turnover"] * fc.EQUITY0) == pytest.approx(7e-4, rel=1e-9)
    k0 = next(r for r in first if r["arm"] == "A60" and r["account"] == "KRAKEN-5K")
    assert k0["fees"] / (k0["turnover"] * fc.EQUITY0) == pytest.approx(5e-4, rel=1e-9)
    assert k0["spread"] / (k0["turnover"] * fc.EQUITY0) == pytest.approx(2e-4, rel=1e-9)
    # the synthetic Kraken lists 7 in 10 instruments: something is not held, and the row says how much
    assert any((r["unheld_share"] or 0) > 0 for r in kr) and all(0.0 <= (r["unheld_share"] or 0.0) <= 1.0 for r in kr)
    book = fc.TermsBook(paths.terms)
    assert {r["venue_sha256"] for r in kr} == set(book.by_sha) and len(book.by_sha) == 1
    assert all(r["backfilled"] == (r["date"] != fc.day(idx[S0 + 10])) for r in rows)   # only the last day was logged on its own day
    assert (tmp_path / "STATUS.md").read_text().count("n < 60: no performance statement") == 5
    assert "REPLAY" in (tmp_path / "STATUS.md").read_text()

    before = paths.ledger.read_bytes()
    again = _replay(synth, tmp_path, S0, S0 + 10)                                # the same day again: nothing
    assert again["status"] == "NOTHING_TO_APPEND" and again["advance"]["rows_appended"] == 0
    assert again["advance"]["ledger_rows_checked"] == 110 and paths.ledger.read_bytes() == before
    nxt = _replay(synth, tmp_path, S0, S0 + 11)                                  # the next day: exactly one day
    assert nxt["status"] == "APPENDED" and nxt["advance"]["rows_appended"] == 10 and nxt["advance"]["ledger_rows_checked"] == 110
    after = paths.ledger.read_bytes()
    assert after.startswith(before) and after.count(b"\n") == 120                # appended, never rewritten
    assert not list(tmp_path.glob("INCIDENT_*.json"))


def test_truncation_property_rows_do_not_depend_on_later_data(synth, tmp_path):
    """The ledger rows of days <= N are the same whether the panel ends at N or at N + 5."""
    a, b = tmp_path / "ends_at_n", tmp_path / "ends_at_n_plus_5"
    _replay(synth, a, S0, S0 + 12)
    _replay(synth, b, S0, S0 + 17)
    ra, rb = fc.read_ledger(fc.Paths(a).ledger), fc.read_ledger(fc.Paths(b).ledger)
    assert len(ra) == 130 and len(rb) == 180
    assert [_content(r) for r in rb[:130]] == [_content(r) for r in ra]          # bit for bit, data fingerprint included
    assert [r["date"] for r in rb[130:]] == sorted(r["date"] for r in rb[130:]) and rb[130]["date"] > ra[-1]["date"]
    # and N, then N + 5 into the same ledger: five days appended, the 130 earlier rows reproduced
    run = _replay(synth, a, S0, S0 + 17)
    assert run["status"] == "APPENDED" and run["advance"]["rows_appended"] == 50 and run["advance"]["ledger_rows_checked"] == 130
    assert run["advance"]["data_sha256_not_reproduced"] == 0
    assert [_content(r) for r in fc.read_ledger(fc.Paths(a).ledger)] == [_content(r) for r in rb]


def test_immutability_refuses_when_a_ledgered_row_was_altered(synth, tmp_path):
    idx = synth["panel"].prices.index
    _replay(synth, tmp_path, S0, S0 + 5)
    paths = fc.Paths(tmp_path)
    g = fc.genesis_hash(PIN, f"replay:{fc.day(idx[S0])}")
    rows = fc.read_ledger(paths.ledger)
    # a careful forger: alters one equity by 1e-9 relative and re-chains the WHOLE file, so the hash chain verifies
    k = 23
    rows[k] = dict(rows[k], equity=rows[k]["equity"] * (1.0 + 1e-9))
    forged = fc.chain(rows, g)
    paths.ledger.write_text("".join(fc.canonical(r) + "\n" for r in forged))
    fc.verify_chain(fc.read_ledger(paths.ledger), g)
    before = paths.ledger.read_bytes()
    run = _replay(synth, tmp_path, S0, S0 + 6)                                   # a new day is due — and must NOT be appended
    assert run["status"] == "INCIDENT:IMMUTABILITY" and run["exit_code"] == fc.EXIT_INCIDENT
    assert paths.ledger.read_bytes() == before
    inc = json.loads(next(tmp_path.glob("INCIDENT_*.json")).read_text())
    assert inc["kind"] == "IMMUTABILITY" and inc["detail"]["n_rows_differ"] == 1
    assert (inc["detail"]["first"]["date"], inc["detail"]["first"]["arm"], inc["detail"]["first"]["account"]) == \
        (forged[k]["date"], forged[k]["arm"], forged[k]["account"])
    assert inc["detail"]["first"]["data_sha256_reproduced"] is True              # the data did not change: the ledger did
    assert "INCIDENT:IMMUTABILITY" in paths.status.read_text() and "Incidents: 1" in paths.status.read_text()
    # a clumsy forger (no re-chaining) is caught one step earlier, by the chain
    paths.ledger.write_text(before.decode().replace('"n_positions":', '"n_positions" :', 1))
    assert _replay(synth, tmp_path, S0, S0 + 6)["status"] == "INCIDENT:LEDGER_CHAIN"


def test_a_tolerance_of_1e_12_is_what_passes(synth, tmp_path):
    idx = synth["panel"].prices.index
    _replay(synth, tmp_path, S0, S0 + 3)
    paths = fc.Paths(tmp_path)
    g = fc.genesis_hash(PIN, f"replay:{fc.day(idx[S0])}")
    rows = fc.read_ledger(paths.ledger)
    rows[7] = dict(rows[7], equity=rows[7]["equity"] * (1.0 + 2e-13))            # inside the tolerance: float noise, not an incident
    paths.ledger.write_text("".join(fc.canonical(r) + "\n" for r in fc.chain(rows, g)))
    assert _replay(synth, tmp_path, S0, S0 + 4)["status"] == "APPENDED"


def test_windowed_simulation_is_the_full_panel_with_targets_zeroed_before_the_start(synth):
    """`simulate` runs on the rows from the forward start. That is, bit for bit, the account on the WHOLE panel
    whose targets are zero before the start row: flat until then, trading into the book at that row's print."""
    panel, cfg = synth["panel"], synth["cfg"]
    idx = panel.prices.index
    w = synth["arms"]["A60"]
    cols = [c for c in w.columns if (w[c].iloc[S0:] != 0).any()]
    venue = fc.ideal_venue(cols)
    p = fc.simulate(panel.window(idx[S0], None), w.iloc[S0:], venue, cfg)
    assert p.cols == cols
    zeroed = w[cols].copy()
    zeroed.iloc[:S0] = 0.0
    sub = panel.subset(cols)
    full = realism.simulate_account(sub, zeroed, equity0=fc.EQUITY0, venue=venue, no_trade_band=0.10, exec_prices=sub.aux["exec_prices"],
                                    extra_lag=0, missing_return="zero", ideal_net=pd.Series(0.0, index=idx))
    assert np.array_equal(full.equity.to_numpy()[S0:], p.equity) and np.array_equal(full.net.to_numpy()[S0:], p.net)
    assert (full.equity.to_numpy()[:S0] == fc.EQUITY0).all() and (full.net.to_numpy()[:S0] == 0.0).all()
    assert p.net[0] == 0.0 and p.equity[0] < fc.EQUITY0 and (p.notional[0] != 0).any()


def test_stop_rule_freezes_the_arm_from_the_row_after_the_breach(synth, tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "STOP_LOSS", 0.004)                                  # 0.4 % instead of 30 %: it triggers within days
    run = _replay(synth, tmp_path, S0, S0 + 40)
    stops = {a: d for a, d in run["advance"]["stops"].items() if d}
    assert stops, "no arm lost 0.4 % in 41 synthetic days"
    rows = fc.read_ledger(fc.Paths(tmp_path).ledger)
    for arm, stop_day in stops.items():
        ideal = [r for r in rows if r["arm"] == arm and r["account"] == "IDEAL"]
        k = next(i for i, r in enumerate(ideal) if r["date"] == stop_day)
        assert ideal[k]["equity"] <= (1 - 0.004) * fc.EQUITY0 and all(r["equity"] > (1 - 0.004) * fc.EQUITY0 for r in ideal[:k])
        assert all(r["state"] == "LIVE" for r in ideal[: k + 1]) and all(r["state"] == "FROZEN" for r in ideal[k + 1:])
        for acc in fc.ACCOUNTS:
            path = [r for r in rows if r["arm"] == arm and r["account"] == acc]
            if k + 2 < len(path):                                                # flat one row after the stop took effect
                assert all(r["n_positions"] == 0 and r["gross_exposure"] == 0.0 for r in path[k + 2:])
                assert len({r["equity"] for r in path[k + 2:]}) == 1
    assert "FAILED on" in (tmp_path / "STATUS.md").read_text()
    nxt = _replay(synth, tmp_path, S0, S0 + 41)                                  # the frozen path is itself reproducible
    assert nxt["status"] == "APPENDED" and nxt["advance"]["stops"] == run["advance"]["stops"]


def test_no_performance_statement_before_60_rows_then_a_reading(synth, tmp_path):
    assert [fc.read_point(n) for n in (0, 59, 60, 89, 90, 119, 180, 209, 210)] == [None, None, 60, 60, 90, 90, 180, 180, 210]
    np.testing.assert_allclose(fc.n_day_outcomes(np.array([0.1, -0.5, 1.0, 0.0]), 2), [1.1 * 0.5 - 1, 0.5 * 2 - 1, 2 * 1 - 1], atol=1e-15)
    assert len(fc.n_day_outcomes(np.zeros(5), 6)) == 0
    run = _replay(synth, tmp_path, S0 - 10, S0 + 48)                             # 59 rows
    status = (tmp_path / "STATUS.md").read_text()
    assert status.count("n < 60: no performance statement") == 5 and "Sharpe" not in status.split("## Performance")[1]
    assert all(v["reading"] is None for v in run["advance"]["performance"]["arms"].values())
    run = _replay(synth, tmp_path, S0 - 10, S0 + 49)                             # the 60th row
    perf = run["advance"]["performance"]["arms"]
    status = (tmp_path / "STATUS.md").read_text()
    assert "no performance statement" not in status and status.count("first 60 rows") == 5
    for arm in fc.ARMS:
        p = perf[arm]
        assert p["reading"] == 60 and p["rows"] == 60 and p["sharpe_ci90"][0] < p["sharpe_ci90"][1] and np.isfinite(p["sharpe"])
        assert p["backtest_outcomes"]["n_windows"] > 100 and p["backtest_outcomes"]["p05"] <= p["backtest_outcomes"]["p95"]
        assert "reading_180" not in p
    rows = [r for r in fc.read_ledger(fc.Paths(tmp_path).ledger) if r["arm"] == "A60" and r["account"] == "IDEAL"]
    total = float(np.prod([1 + r["net_return"] for r in rows]) - 1)
    assert perf["A60"]["total_return"] == pytest.approx(total, abs=1e-12)


def test_the_180_row_readings_follow_the_preregistered_wording():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2021-01-01", periods=1500, freq="D", tz="UTC")
    bt = {a: pd.Series(rng.normal(0.0004, 0.012, 1500), index=idx) for a in fc.ARMS}
    up = np.full(200, 0.004)
    up[::2] = -0.002                                                             # +0.1 % a day on average: far above the backtest's 25th percentile
    down = -2.0 * up                                                             # -0.2 % a day: far below the backtest's 5th percentile
    nets = {"A60": up, "A30": up * 0.5, "A120": up * 1.5, "A0": up * 0.9, "C252": down}
    out = fc.performance(nets, bt)
    assert out["arms"]["A60"]["reading"] == 180 and out["arms"]["A60"]["reading_180"]["verdict"] == "consistent with a positive edge"
    assert out["arms"]["C252"]["reading_180"]["verdict"] == "contradicted"
    assert "reading_180" not in out["arms"]["A0"] and "reading_180" not in out["arms"]["A30"]       # shadows are read only comparatively
    v = out["verdicts"]
    t = {a: float(np.prod(1 + nets[a][:180]) - 1) for a in fc.ARMS}
    assert v["a60_minus_a0"] == pytest.approx(t["A60"] - t["A0"]) and v["spread_a30_a60_a120"] == pytest.approx(t["A120"] - t["A30"])
    assert v["volatility_scaling"] == "declared noise"                           # A60 beats A0 by less than the spread among the windows
    flat = dict(nets, A30=up, A120=up, A0=up * 0.2)
    assert fc.performance(flat, bt)["verdicts"]["volatility_scaling"] == "not declared noise"
    mid = dict(nets, A60=np.r_[np.full(90, -0.0005), np.full(110, 0.0006)])        # small positive: neither above p25 nor below p05?
    verdict = fc.performance(mid, bt)["arms"]["A60"]["reading_180"]
    assert verdict["verdict"] in ("undecided", "consistent with a positive edge", "contradicted")
    assert (verdict["verdict"] == "undecided") == (not (verdict["sharpe"] > 0 and verdict["total_return"] > verdict["backtest_p25"])
                                                    and not verdict["total_return"] < verdict["backtest_p05"])
    assert fc.performance({a: up[:59] for a in fc.ARMS}, bt)["arms"]["A60"]["statement"] == "n < 60: no performance statement"


# ==================================================================================================
# the store
# ==================================================================================================
def _resp(body, url="https://x/y?z=1"):
    return fc.Resp(200, body, {}, url, "2026-11-11T01:10:00Z")


def test_store_keeps_the_first_observation_and_reports_a_later_different_one(tmp_path):
    paths = fc.Paths(tmp_path)
    tabs = fc.Tables()
    k1 = json.dumps([[D * 10, "1", "1", "1", "100.5", "9", D * 11 - 1, "5000.25", 7, "0", "0", "0"],
                     [D * 11, "1", "1", "1", "101.5", "9", D * 12 - 1, "6000.5", 0, "0", "0", "0"]]).encode()
    f1 = json.dumps([{"symbol": "AUSDT", "fundingTime": 8 * H + 3, "fundingRate": "0.00010000"},
                     {"symbol": "AUSDT", "fundingTime": 8 * H + 4, "fundingRate": "0.5"}]).encode()
    w = fc.RunWriter(paths, "20261111T011000Z", tabs)
    w.record("1d", "AUSDT", D * 10, D * 11, _resp(k1))
    w.add_rows("1d", "AUSDT", fc.parse_klines(k1))
    w.coverage("1d", "AUSDT", D * 10, D * 11)
    w.record("fund", "AUSDT", 0, 9 * H, _resp(f1))
    w.add_rows("fund", "AUSDT", fc.parse_funding(f1))
    w.complete(pd.Timestamp("2026-11-11", tz="UTC"))
    rep = w.close()
    assert rep["requests"] == 2 and rep["rows_added"] == {"1d": 2, "1h": 0, "fund": 2} and rep["conflicts"] == 0
    with zipfile.ZipFile(paths.binance / rep["zip"]) as z:                       # the raw bodies, byte for byte, with URL, time and sha256
        assert z.read("r/000001.json") == k1 and z.read("r/000002.json") == f1
        idx = [json.loads(x) for x in z.read("index.jsonl").decode().splitlines()]
    req = [r for r in idx if r["type"] == "request"]
    assert req[0]["sha256"] == fc.sha256_hex(k1) and req[0]["url"].startswith("https://") and req[0]["fetched_utc"].endswith("Z")
    again = fc.Tables.load(paths)
    assert again.cov[("1d", "AUSDT")] == (D * 10, D * 11) and again.complete_through == pd.Timestamp("2026-11-11", tz="UTC")
    df = again.klines("AUSDT", "1d")
    assert df.index.tolist() == [D * 10, D * 11] and df["close"].tolist() == [100.5, 101.5] and df["count"].tolist() == [7.0, 0.0]
    assert again.last_traded_day_open("AUSDT") == D * 10                         # the zero-trade candle is not a print
    assert len(again.funding("AUSDT")) == 1                                      # two stamps in one minute are one event (data layer rule)
    assert fc.verify_store(paths)["ok"]

    # a second run: one candle again and unchanged, one changed (an upstream revision), one new
    k2 = json.dumps([[D * 10, "1", "1", "1", "100.5", "9", D * 11 - 1, "5000.25", 7, "0", "0", "0"],
                     [D * 11, "1", "1", "1", "999.0", "9", D * 12 - 1, "6000.5", 0, "0", "0", "0"],
                     [D * 12, "1", "1", "1", "102.5", "9", D * 13 - 1, "7000.5", 3, "0", "0", "0"]]).encode()
    w2 = fc.RunWriter(paths, "20261112T011000Z", again)
    w2.record("1d", "AUSDT", D * 10, D * 12, _resp(k2))
    w2.add_rows("1d", "AUSDT", fc.parse_klines(k2))
    rep2 = w2.close()
    assert rep2["rows_added"]["1d"] == 1 and rep2["conflicts"] == 1 and w2.conflicts[0]["t_ms"] == D * 11
    assert w2.conflicts[0]["first_seen"][1] == 101.5 and w2.conflicts[0]["now"][1] == 999.0
    final = fc.Tables.load(paths)
    assert final.klines("AUSDT", "1d")["close"].tolist() == [100.5, 101.5, 102.5]   # the first observation stays
    assert fc.verify_store(paths)["ok"]
    # a raw body altered on disk no longer hashes to its index entry
    zp = paths.binance / rep2["zip"]
    with zipfile.ZipFile(zp) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    entries["r/000001.json"] = entries["r/000001.json"].replace(b"102.5", b"102.6")
    with zipfile.ZipFile(zp, "w") as z:
        for n, b in entries.items():
            z.writestr(n, b)
    v = fc.verify_store(paths)
    assert not v["ok"] and "sha256" in v["problems"][0]["why"]


def test_causal_funding_keeps_a_stamp_only_if_the_instrument_had_traded_up_to_it():
    ev = pd.DataFrame({"rate": [1.0, 2.0, 4.0, 8.0]}, index=pd.Index([8 * H + 3, 16 * H + 1, 24 * H + 5, 32 * H], name="ms"))
    always = np.arange(0, 40) * H
    assert fc._causal_funding(ev, always)["rate"].tolist() == [1.0, 2.0, 4.0, 8.0]
    # trading stopped after the hour that opened at 09:00 (it closed at 10:00): the 16:00 and later stamps are phantom
    assert fc._causal_funding(ev, np.arange(0, 10) * H)["rate"].tolist() == [1.0]
    # no trade in the 00:00 hour of day 1, but the 23:00 hour traded (closed 24:00): the 00:00 stamp (+5 ms) still counts
    assert fc._causal_funding(ev, np.arange(0, 24) * H)["rate"].tolist() == [1.0, 2.0, 4.0]
    assert len(fc._causal_funding(ev, np.empty(0, dtype="int64"))) == 0
    tot, cnt = C.funding_to_rows(fc._causal_funding(ev, always), pd.DatetimeIndex([pd.Timestamp(D, unit="ms", tz="UTC"),
                                                                                    pd.Timestamp(2 * D, unit="ms", tz="UTC")]),
                                 cut_after_ms=None)
    assert tot.tolist() == [7.0, 8.0] and cnt.tolist() == [3, 1]                 # row D collects (D-1 01:00, D 01:00]


# ==================================================================================================
# a fabricated exchange: the data layer's own build is the truth the extension is held to
# ==================================================================================================
T0 = pd.Timestamp("2026-01-01", tz="UTC")
T0_MS = int(T0.value // 10 ** 6)
K = 130                                                                         # the "freeze": the frozen lane ends on day K


class FakeExchange:
    """Hourly candles per symbol (random walk; zero-trade hours are flat with count 0, as Binance serves them),
    daily candles aggregated from them, funding stamps with millisecond jitter, exchangeInfo, and a fake Kraken."""

    def __init__(self, n_days: int = K + 12, seed: int = 5):
        self.rng = np.random.default_rng(seed)
        self.n_h = n_days * 24
        self.sym: dict = {}
        self.now_ms = 0
        self.calls = 0
        self.fail_symbol = None
        add = self._add
        add("AAAUSDT", size=9.0)
        add("BBBUSDT", size=7.0)
        add("CCCUSDT", size=5.0, fund_h=4)
        add("DDDUSDT", size=3.0)
        add("EEEUSDT", size=0.4)
        add("龙虾USDT", size=6.0)                                                 # a non-ASCII ticker, as on the real venue
        add("GGGUSDT", size=8.0, list_day=5, delist_h=100 * 24 + 9)              # delisted inside the continuity window
        add("HHHUSDT", size=10.0, delist_h=(K + 2) * 24 + 9)                     # delisted after the freeze
        add("IIIUSDT", size=0.01, list_day=K - 70, boost=((K + 1) * 24, 30000.0))  # enters the mask only after the freeze
        add("JJJUSDT", size=2.0, list_day=K + 1)                                 # listed after the freeze
        add("KKKUSDT", size=6.5, halts=[((K + 3) * 24, (K + 4) * 24)])           # one whole day without a trade, after the freeze
        add("LLLUSDT", size=0.2)
        add("USDCUSDT", size=50.0)                                               # stablecoin: excluded
        add("PAXGUSDT", size=50.0)                                               # gold token: excluded
        add("BTCDOMUSDT", size=50.0)                                             # synthetic index: excluded
        add("AAPLUSDT", size=50.0, contract="TRADIFI_PERPETUAL", underlying="EQUITY")

    def _add(self, name, size=1.0, list_day=0, delist_h=None, halts=(), fund_h=8, boost=None, contract="PERPETUAL", underlying="COIN"):
        n, rng = self.n_h, self.rng
        close = rng.uniform(0.5, 500.0) * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
        traded = np.ones(n, dtype=bool)
        traded[: list_day * 24] = False
        if delist_h is not None:
            traded[delist_h:] = False
        for a, b in halts:
            traded[a:b] = False
        qv = size * 1e6 * np.exp(rng.normal(0.0, 0.5, n))
        if boost:
            qv[boost[0]:] *= boost[1]
        count = rng.integers(20, 400, n).astype(float)
        last = np.nan
        for h in range(n):                                                       # a zero-trade hour is flat at the last traded price
            if traded[h]:
                last = close[h]
            else:
                close[h], qv[h], count[h] = last, 0.0, 0.0
        base = name[:-4]
        self.sym[name] = {"close": close, "qv": qv, "count": count, "list_h": list_day * 24, "delist_h": delist_h, "fund_h": fund_h,
                          "contract": contract, "underlying": underlying, "base": base,
                          "rate": np.round(rng.normal(1e-4, 4e-4, n), 8)}

    # ---- what the venue would answer at self.now_ms
    def _klines(self, name, interval, start, end, limit, now_ms):
        s = self.sym[name]
        step = D if interval == "1d" else H
        per = 24 if interval == "1d" else 1
        k0 = max(-(-(max(start, T0_MS + s["list_h"] * H) - T0_MS) // step), 0)
        out = []
        k = k0
        while len(out) < limit:
            open_ms = T0_MS + k * step
            if open_ms > end or open_ms > now_ms or (k + 1) * per > self.n_h:
                break
            h0 = k * per
            if h0 >= s["list_h"]:
                sl = slice(h0, h0 + per)
                out.append([open_ms, "0", "0", "0", repr(float(s["close"][sl][-1])), "0", open_ms + step - 1,
                            repr(float(s["qv"][sl].sum())), int(s["count"][sl].sum()), "0", "0", "0"])
            k += 1
        return out

    def _funding(self, name, start, end, limit, now_ms):
        s = self.sym[name]
        out = []
        h = s["list_h"] - (s["list_h"] % s["fund_h"]) + s["fund_h"]
        while h < self.n_h and len(out) < limit:
            t = T0_MS + h * H + (h * 7 + 3) % 6                                  # 0 .. 5 ms of jitter, as on the real venue
            if t > end or t > now_ms:
                break
            if t >= start:
                out.append({"symbol": name, "fundingTime": t, "fundingRate": f"{s['rate'][h]:.8f}", "markPrice": "1"})
            h += s["fund_h"]
        return out

    def _listed(self, now_ms):
        return [n for n, s in self.sym.items() if T0_MS + s["list_h"] * H <= now_ms]

    def exchange_info(self, now_ms):
        syms = []
        for n in self._listed(now_ms):
            s = self.sym[n]
            dead = s["delist_h"] is not None and now_ms >= T0_MS + s["delist_h"] * H
            syms.append({"symbol": n, "status": "SETTLING" if dead else "TRADING", "contractType": s["contract"],
                         "underlyingType": s["underlying"], "baseAsset": s["base"], "quoteAsset": "USDT",
                         "onboardDate": T0_MS + s["list_h"] * H, "deliveryDate": 4133404800000})
        return {"serverTime": now_ms, "rateLimits": [{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1,
                                                      "limit": 2400}], "symbols": syms}

    def kraken(self, now_ms):
        h = min((now_ms - T0_MS) // H, self.n_h - 1)
        ins, tick = [], []
        for n in self._listed(now_ms):
            s = self.sym[n]
            if n in ("DDDUSDT", "JJJUSDT") or s["contract"] != "PERPETUAL" or not s["base"].isascii():
                continue                                                         # Kraken does not list these
            px = float(s["close"][h])
            ins.append({"symbol": f"PF_{s['base']}USD", "type": "flexible_futures", "base": s["base"], "quote": "USD", "contractSize": 1,
                        "contractValueTradePrecision": int(np.clip(round(np.log10(px)), -3, 4)), "tradeable": True, "suspended": False,
                        "postOnly": False, "isExpired": False, "tradfi": False, "platformsPermitted": ["europa"], "countriesBanned": [],
                        "category": "Layer 1", "openingDate": "2025-01-01T00:00:00Z"})
            tick.append({"symbol": f"PF_{s['base']}USD", "markPrice": px * 1.001, "last": px * 1.002, "lastTime": fc.iso(fc.from_ms(now_ms))})
        t = fc.iso(fc.from_ms(now_ms))
        return ({"result": "success", "instruments": ins, "serverTime": t}, {"result": "success", "tickers": tick, "serverTime": t})

    def transport(self, url, params):
        self.calls += 1
        now_ms = self.now_ms
        head = {"date": email.utils.formatdate(now_ms / 1000.0, usegmt=True), "x-mbx-used-weight-1m": "7"}
        full = url + ("?" + urllib.parse.urlencode(params) if params else "")
        sym = params.get("symbol")
        if self.fail_symbol is not None and sym == self.fail_symbol:
            raise ConnectionError("fabricated network failure")
        if url.endswith("/exchangeInfo"):
            body = self.exchange_info(now_ms)
        elif url.endswith("/klines") or url.endswith("/fundingRate"):
            if sym not in self.sym or T0_MS + self.sym[sym]["list_h"] * H > now_ms:
                return 400, json.dumps({"code": -1121, "msg": "Invalid symbol."}).encode(), head, full
            if url.endswith("/klines"):
                body = self._klines(sym, params["interval"], int(params["startTime"]), int(params["endTime"]), int(params["limit"]), now_ms)
            else:
                body = self._funding(sym, int(params["startTime"]), int(params["endTime"]), int(params["limit"]), now_ms)
        elif url == fc.KRAKEN_INSTRUMENTS_URL:
            body = self.kraken(now_ms)[0]
        elif url == fc.KRAKEN_TICKERS_URL:
            body = self.kraken(now_ms)[1]
        else:
            raise AssertionError(f"the logger asked for an endpoint it was not given: {url}")
        return 200, json.dumps(body, ensure_ascii=False).encode("utf-8"), head, full

    # ---- the raw tree the v2 data layer reads: what its downloader would have saved at `cutoff`
    def write_raw_tree(self, root, cutoff: pd.Timestamp):
        now_ms = int(cutoff.value // 10 ** 6)
        src = root / C.SRC["perp"]
        info = self.exchange_info(now_ms)
        (src / "exchangeInfo").mkdir(parents=True, exist_ok=True)
        (src / "exchangeInfo" / "latest.json").write_text(json.dumps(info, ensure_ascii=False))
        (src / "listings").mkdir(parents=True, exist_ok=True)
        (src / "listings" / "daily_plan.json").write_text(json.dumps({"rest_symbols": sorted(s["symbol"] for s in info["symbols"]),
                                                                      "archive_only_symbols": []}, ensure_ascii=False))
        day0 = (now_ms // D) * D
        for n in self._listed(now_ms):
            for kind, name, rows in (("rest_klines_1d", "1d_0.json", self._klines(n, "1d", 0, day0 - 1, 10 ** 6, now_ms)),
                                     ("rest_klines_1h", "1h_0.json", self._klines(n, "1h", 0, (now_ms // H) * H - 1, 10 ** 6, now_ms)),
                                     ("rest_funding", "funding_all_0.json", self._funding(n, 0, now_ms, 10 ** 6, now_ms))):
                (src / kind / n).mkdir(parents=True, exist_ok=True)
                (src / kind / n / name).write_text(json.dumps(rows, ensure_ascii=False))


def _assemble(monkeypatch, root):
    """The v2 data layer's own lane build (`crypto_lanes._assemble`) on a raw tree."""
    from scripts.factory.data import crypto_lanes as CL

    for mod in (C, CB, CL):
        monkeypatch.setattr(mod, "RAW", root)
    CB.plan("perp")
    return CL._assemble("perp")


def _frozen_from(A) -> fc.Frozen:
    rows = fc._norm_index(A["rows"])

    def f(df):
        out = df.copy()
        out.index = rows
        return out

    inc = [str(c) for c in A["prices"].columns]
    aux = {"universe_mask": f(A["mask"]), "exec_prices": f(A["exec"]), "exec_prices_alt": f(A["alt"]), "volume_quote": f(A["volq"]),
           "live_at_print": f(A["live"]), "funding_obs": f(A["fund_n"]), "terminal_return": f(A["terminal"]), "settlement_row": f(A["settle"])}
    meta = {"periods_per_year": 365, "exec_prices_strictly_after_decision": True, "print_convention": "fabricated",
            "source_manifest": "fabricated", "universe_groups": {"EVER_IN_MASK": [c for c in inc if bool(A["mask"][c].any())], "ALL": inc}}
    panel = PanelBundle(lane="CRYPTO-PERP", prices=f(A["prices"]), carry=f(A["carry"]), aux=aux,
                        tbill=pd.Series(0.0, index=rows, name="tbill"), meta=meta)
    cls = A["cls"]
    return fc.Frozen(panel, "fabricated-manifest", [str(c) for c in A["ever"]], {str(n): str(cls.at[n, "reason"]) for n in cls.index[~cls["include"]]})


def _simple_arms(sub, cfg, *, enforce_members=True):
    """Five plain books on the eligible instruments (this test is about the data path and the ledger, not the rules)."""
    elig = sub.eligible().astype(float)
    base = elig.div(elig.sum(axis=1).replace(0.0, np.nan), axis=0).fillna(0.0)
    side = [1.0 if sum(map(ord, str(c))) % 2 == 0 else -1.0 for c in base.columns]      # by NAME: a book may not depend on which other columns exist
    sign = pd.DataFrame(np.tile(side, (len(base), 1)), index=base.index, columns=base.columns)
    arms = {"A60": base * 0.5, "A30": base * sign * 0.8, "A120": base * 0.3, "A0": base * sign * 0.4, "C252": base * 1.5}
    return arms, {"primary": "TEST", "declared_members": 0, "kept_members": 0, "dropped_by_speed_limit": [], "max_cost_sr": 0.0,
                  "speed_limit_sr": 0.13}


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setitem(CB.TOP_N, "perp", 6)                                     # twelve coins: a top-6 mask is a real selection
    ex = FakeExchange()
    freeze = T0 + pd.Timedelta(days=K, hours=15)                                 # the lane was built at 15:00 UTC on day K
    ex.write_raw_tree(tmp_path / "raw_freeze", freeze)
    fz = _frozen_from(_assemble(monkeypatch, tmp_path / "raw_freeze"))
    assert fz.last_row == T0 + pd.Timedelta(days=K)
    pin = {"sha256": "ef" * 32, "frozen_utc": fc.iso(T0 + pd.Timedelta(days=K, hours=18)), "preregistration": "fabricated"}
    monkeypatch.setattr(fc, "load_pin", lambda: pin)
    monkeypatch.setattr(fc, "build_arms", _simple_arms)
    paths = fc.Paths(tmp_path / "fwd")

    def run(day_offset: float, hours: float = 1.25):
        now = T0 + pd.Timedelta(days=K + day_offset, hours=hours)
        ex.now_ms = int(now.value // 10 ** 6)
        http = fc.Http(ex.transport, min_gap=0.0, slow_gap=0.0, sleep=lambda s: None, wall=lambda: now)
        code = fc.cmd_run(now=now, paths=paths, fz=fz, http=http, say=QUIET)
        runs = sorted(paths.runs.glob("*.json"))
        return code, json.loads(runs[-1].read_text())

    return {"ex": ex, "fz": fz, "paths": paths, "run": run, "pin": pin, "tmp": tmp_path, "mp": monkeypatch}


def test_the_fabricated_frozen_lane_is_a_real_data_layer_build(world):
    fz = world["fz"]
    cols = set(fz.panel.prices.columns)
    assert {"AAAUSDT", "龙虾USDT", "GGGUSDT", "HHHUSDT", "IIIUSDT", "KKKUSDT"} <= cols and "JJJUSDT" not in cols
    assert not cols & {"USDCUSDT", "PAXGUSDT", "BTCDOMUSDT", "AAPLUSDT"} and set(fz.excluded) == {"USDCUSDT", "PAXGUSDT", "BTCDOMUSDT", "AAPLUSDT"}
    mask = fz.panel.aux["universe_mask"]
    assert int(mask.sum(axis=1).max()) == 6 and "GGGUSDT" in fz.tracked and "IIIUSDT" not in fz.tracked
    st = fz.panel.aux["settlement_row"]
    assert bool(st["GGGUSDT"].any()) and st["GGGUSDT"].idxmax() == T0 + pd.Timedelta(days=101)   # the data layer's settlement print, on z


def test_daily_runs_on_a_fabricated_exchange(world):
    ex, fz, paths, run = world["ex"], world["fz"], world["paths"], world["run"]
    g = fc.genesis_hash(world["pin"])

    # ---- the day of the freeze, 18:30 UTC: no forward row exists; everything else is exercised
    code, r = run(0, hours=18.5)
    assert code == 0 and r["status"] == "NO_FORWARD_ROW_YET" and "0 forward rows" in r["message"]
    assert r["continuity"]["ok"] and r["continuity"]["mismatches"] == 0 and r["continuity"]["n_rows"] == 90
    assert r["continuity"]["frames"]["settlement_row"]["mismatches"] == 0 and r["continuity"]["instruments_rebuilt_from_hourly_and_funding"] >= 6
    assert not paths.ledger.exists() and "0** (0 ledger rows" in paths.status.read_text()
    assert r["binance"]["requests"] > 20 and r["binance"]["conflicts"] == 0 and r["advance"]["targets_now"]["A60"]["target_gross"] == pytest.approx(0.5)
    assert r["advance"]["kraken"]["mapped"] >= 5 and r["price_gap"] and abs(r["price_gap"][0]["mark_gap_bp"]) < 1500
    assert sorted(p.name for p in paths.kraken.glob("*.gz")) == [f"{r['run_id']}_instruments.json.gz", f"{r['run_id']}_tickers.json.gz"]
    meta = json.loads((paths.kraken / f"{r['run_id']}_instruments.meta.json").read_text())
    assert meta["url"] == fc.KRAKEN_INSTRUMENTS_URL and len(meta["sha256"]) == 64 and meta["fetched_utc"].endswith("Z")
    calls = ex.calls
    code, r = run(0, hours=19.0)                                                 # again the same evening: the store is complete
    assert code == 0 and r["status"] == "NO_FORWARD_ROW_YET" and r["binance"]["requests"] == 0
    assert ex.calls == calls + 2                                                 # only the two Kraken GETs (still no forward row: the preview)

    # ---- day K+1, 00:30: the 01:00 print does not exist yet
    code, r = run(1, hours=0.5)
    assert code == 0 and r["status"] == "NO_FORWARD_ROW_YET" and not paths.ledger.exists()
    # ---- day K+1, 01:15: the first forward row
    code, r = run(1)
    d1 = fc.day(T0 + pd.Timedelta(days=K + 1))
    assert code == 0 and r["status"] == "APPENDED" and r["advance"]["new_days"] == [d1] and r["advance"]["rows_appended"] == 10
    rows = fc.read_ledger(paths.ledger)
    fc.verify_chain(rows, g)
    assert len(rows) == 10 and all(r_["date"] == d1 and not r_["backfilled"] and r_["n"] == 1 and r_["net_return"] == 0.0 for r_ in rows)
    a60 = next(r_ for r_ in rows if r_["arm"] == "A60" and r_["account"] == "IDEAL")
    assert a60["gross_exposure"] == pytest.approx(0.5, rel=2e-3) and a60["n_positions"] == 6 and a60["unheld_share"] == 0.0
    k60 = next(r_ for r_ in rows if r_["arm"] == "A60" and r_["account"] == "KRAKEN-5K")
    assert 0.0 < k60["unheld_share"] < 1.0 and k60["n_positions"] < 6           # DDD and the non-ASCII ticker are not at Kraken
    assert (paths.root / "CODE_FINGERPRINT.json").exists()
    # ---- the same day, later: idempotent, and no network at all
    calls, before = ex.calls, paths.ledger.read_bytes()
    code, r = run(1, hours=5.0)
    assert code == 0 and r["status"] == "NOTHING_TO_APPEND" and paths.ledger.read_bytes() == before and ex.calls == calls
    assert r["advance"]["ledger_rows_checked"] == 10

    # ---- day K+2 is missed; day K+3 backfills it with the same prints
    code, r = run(3)
    d2, d3 = fc.day(T0 + pd.Timedelta(days=K + 2)), fc.day(T0 + pd.Timedelta(days=K + 3))
    assert code == 0 and r["advance"]["new_days"] == [d2, d3] and r["advance"]["rows_appended"] == 20
    rows = fc.read_ledger(paths.ledger)
    assert {r_["date"]: r_["backfilled"] for r_ in rows} == {d1: False, d2: True, d3: False}
    assert paths.ledger.read_bytes().startswith(before)

    # ---- a network failure: nothing appended, exit 3; the next run recovers
    ex.fail_symbol = "BBBUSDT"
    before = paths.ledger.read_bytes()
    code, r = run(4)
    assert code == fc.EXIT_FETCH and r["status"].startswith("FAILED:FetchFailed") and paths.ledger.read_bytes() == before
    ex.fail_symbol = None
    code, r = run(4, hours=3.0)
    assert code == 0, (r["status"], r.get("message"), [p_.read_text()[:1500] for p_ in paths.root.glob("INCIDENT_*.json")])
    assert r["advance"]["rows_appended"] == 10 and "failed or refused: 1" in paths.status.read_text()

    for k in (5, 6, 7):
        code, r = run(k)
        assert code == 0 and r["status"] == "APPENDED" and r["advance"]["rows_appended"] == 10, r.get("message")
    rows = fc.read_ledger(paths.ledger)
    fc.verify_chain(rows, g)
    assert len(rows) == 70 and len({r_["date"] for r_ in rows}) == 7
    assert r["continuity"]["ok"] and fc.verify_store(paths)["ok"]
    booked = r["panel"]["settlements_booked"]
    assert [(b["instrument"], b["last_traded_row"], b["booked_on"]) for b in booked] == \
        [("HHHUSDT", fc.day(T0 + pd.Timedelta(days=K + 3)), fc.day(T0 + pd.Timedelta(days=K + 6)))]
    # III (volume boost) and DDD (the next in rank once KKK's halt breaks its 30-candle window) entered the mask after the freeze
    assert r["panel"]["newly_tracked"] == ["DDDUSDT", "IIIUSDT"] and r["panel"]["new_instruments"] == ["JJJUSDT"]
    assert not list(paths.root.glob("INCIDENT_*.json"))

    # ---- an upstream revision of a candle the store already holds: incident, nothing appended, first observation kept
    ex.sym["AAAUSDT"]["close"][(K + 6) * 24 + 23] *= 1.01                        # the daily candle that ended on day K+7
    before = paths.ledger.read_bytes()
    code, r = run(8)
    assert code == fc.EXIT_INCIDENT and r["status"] == "INCIDENT:UPSTREAM_REVISION" and paths.ledger.read_bytes() == before
    inc = json.loads(sorted(paths.root.glob("INCIDENT_*.json"))[-1].read_text())
    assert inc["kind"] == "UPSTREAM_REVISION" and any(c["symbol"] == "AAAUSDT" for c in inc["detail"]["conflicts"])
    assert "INCIDENT:UPSTREAM_REVISION" in paths.status.read_text()


def test_the_extension_is_what_the_data_layer_builds_later_except_the_stated_causal_cells(world):
    """Extend the frozen lane to day K+7 with the logger; let the data layer build the same days after the fact
    (it has seen day K+11); compare every cell of the extension."""
    ex, fz, paths, run, tmp = world["ex"], world["fz"], world["paths"], world["run"], world["tmp"]
    for k in (0.75, 1, 2, 3, 4, 5, 6):
        assert run(k)[0] == 0
    code, r = run(7, hours=3.0)                                                  # 03:00: the 02:00 print of day K+7 is final too
    assert code == 0
    tabs = fc.Tables.load(paths)
    ext = fc.build_extended(fz, tabs, T0 + pd.Timedelta(days=K + 7))
    P = ext.panel
    late = T0 + pd.Timedelta(days=K + 11, hours=15)
    ex.write_raw_tree(tmp / "raw_late", late)
    A = _assemble(world["mp"], tmp / "raw_late")
    rows = P.prices.index[P.prices.index > fz.last_row]
    assert len(rows) == 7
    cols = [str(c) for c in P.prices.columns]
    assert cols == [str(c) for c in A["prices"].columns] and "JJJUSDT" in cols   # same instruments, the new listing included

    def cmp(mine, truth, allowed=()):
        m = mine.loc[rows, cols].to_numpy()
        t = truth.copy()
        t.index = fc._norm_index(t.index)
        t = t.loc[rows, cols].to_numpy()
        if m.dtype.kind == "f":
            bad = ~((m == t) | (np.isnan(m) & np.isnan(t)))
        else:
            bad = m != t
        cells = {(fc.day(rows[i]), cols[j]) for i, j in np.argwhere(bad)}
        assert cells <= set(allowed), sorted(cells - set(allowed))
        return cells

    d = lambda k: fc.day(T0 + pd.Timedelta(days=K + k))  # noqa: E731
    assert cmp(P.prices, A["prices"]) == set() and cmp(P.aux["volume_quote"], A["volq"]) == set()
    assert cmp(P.aux["live_at_print"], A["live"]) == set()
    # the settlement print of HHH: the data layer books it on its last traded row (K+3), the logger on K+6
    assert cmp(P.aux["settlement_row"], A["settle"], {(d(3), "HHHUSDT"), (d(6), "HHHUSDT")}) == {(d(3), "HHHUSDT"), (d(6), "HHHUSDT")}
    halt = (d(4), "KKKUSDT")                                                     # no daily candle traded on that row: no print, no carry (causal)
    diff = cmp(P.aux["exec_prices"], A["exec"], {(d(3), "HHHUSDT"), (d(6), "HHHUSDT"), halt})
    assert {(d(3), "HHHUSDT"), (d(6), "HHHUSDT")} <= diff
    assert P.aux["exec_prices"].at[rows[5], "HHHUSDT"] == A["exec"].loc[A["exec"].index == rows[2], "HHHUSDT"].iloc[0] == P.prices.at[rows[2], "HHHUSDT"]
    cmp(P.aux["exec_prices_alt"], A["alt"], {(d(3), "HHHUSDT"), (d(6), "HHHUSDT"), halt})
    cmp(P.carry, A["carry"], {halt})
    cmp(P.aux["funding_obs"], A["fund_n"], {halt})
    assert cmp(P.aux["universe_mask"], A["mask"]) == set()
    # III and DDD entered the mask after the freeze: their WHOLE history is filled, as the data layer has it
    late_in = ["DDDUSDT", "IIIUSDT"]
    assert ext.info["newly_tracked"] == late_in
    for c in late_in:
        assert bool(P.aux["universe_mask"][c].loc[rows].any()) and not bool(fz.panel.aux["universe_mask"][c].any())
        for mine, truth in ((P.carry, A["carry"]), (P.aux["exec_prices"], A["exec"]), (P.aux["live_at_print"], A["live"])):
            t = truth[c].copy()
            t.index = fc._norm_index(t.index)
            assert fc._same(mine[c].to_numpy(), t.reindex(P.prices.index).to_numpy()), c
        assert float(fz.panel.carry[c].abs().sum()) == 0.0 and float(P.carry[c].abs().sum()) > 0.0
    # every frozen row of every OTHER instrument is the frozen lane, untouched
    others = [c for c in fz.panel.prices.columns if c not in late_in]
    for name in ("exec_prices", "exec_prices_alt", "universe_mask", "live_at_print", "funding_obs", "settlement_row", "volume_quote"):
        assert fc._same(P.aux[name].loc[fz.panel.prices.index, others].to_numpy(), fz.panel.aux[name][others].to_numpy())
    assert fc._same(P.prices.loc[fz.panel.prices.index, list(fz.panel.prices.columns)].to_numpy(), fz.panel.prices.to_numpy())
    assert fc._same(P.carry.loc[fz.panel.prices.index, others].to_numpy(), fz.panel.carry[others].to_numpy())
    # the held position in HHH: carried at its last print through the three dead rows, closed on the settlement row
    led = fc.read_ledger(paths.ledger)
    c252 = [r_ for r_ in led if r_["arm"] == "C252" and r_["account"] == "IDEAL"]
    held = {r_["date"]: {p[0] for p in r_["top_positions"]} for r_ in c252}
    assert "HHHUSDT" in held[d(2)] and "HHHUSDT" in held[d(5)] and "HHHUSDT" not in held[d(6)]


def test_pseudo_forward_reproduces_the_frozen_rows_it_cut_off(world):
    """Cut the fabricated frozen lane 25 rows early and extend it by the forward rules: the 25 rows come out as the
    data layer built them. The two exceptions are the ones a build made AFTER THE FACT cannot avoid at its own
    last row K (they do not occur on the real lane, whose last funding stamps carry no jitter): the data layer cut
    the 00:00 funding stamp of row K (+3 ms here) because no later hour had traded yet when it was built."""
    ex, fz, paths, run = world["ex"], world["fz"], world["paths"], world["run"]
    assert run(0, hours=18.5)[0] == 0
    res = fc.pseudo_forward(fz, fc.Tables.load(paths), 25)
    last = fc.day(T0 + pd.Timedelta(days=K))
    assert res["n_rows"] == 25 and res["cut_at"] == fc.day(T0 + pd.Timedelta(days=K - 25))
    for name in ("prices", "volume_quote", "universe_mask", "exec_prices", "exec_prices_alt", "live_at_print", "settlement_row"):
        assert res["frames"][name]["differ"] == 0, name
    assert {(u["frame"], u["row"]) for u in res["unexplained"]} <= {("carry", last), ("funding_obs", last)}
    assert 0 < res["frames"]["funding_obs"]["differ"] <= 7                       # the tracked instruments alive on the last row
    with pytest.raises(ValueError):
        fc.pseudo_forward(fz, fc.Tables.load(paths), 90)


def test_continuity_break_is_an_incident_not_a_silent_difference(world):
    ex, paths, run = world["ex"], world["paths"], world["run"]
    ex.sym["CCCUSDT"]["close"][(K - 20) * 24] *= 1.0001                          # one 01:00 print, 20 days before the freeze, differs upstream
    code, r = run(0, hours=18.5)
    assert code == fc.EXIT_INCIDENT and r["status"] == "INCIDENT:CONTINUITY"
    f = r["continuity"]["frames"]
    assert f["exec_prices"]["mismatches"] == 1 and f["exec_prices"]["first"][0]["instrument"] == "CCCUSDT"
    assert f["exec_prices"]["first"][0]["row"] == fc.day(T0 + pd.Timedelta(days=K - 20)) and f["prices"]["mismatches"] == 0
    assert not paths.ledger.exists() and "BROKEN" in paths.status.read_text() and list(paths.root.glob("INCIDENT_*.json"))
