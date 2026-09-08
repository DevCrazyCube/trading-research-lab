#!/usr/bin/env python3
"""Hermetic wiring check -- no network, no ledger written. Proves the enforcement and the R-math.

Verifies, on synthetic data only:
  * the frozen spec loads and its pre-registration hash matches;
  * the proposer REJECTS a missing stop, R:R < 2, a wrong-direction stop/target, an over-1% risk, a
    6th concurrent setup, and an unknown instrument -- and ACCEPTS a clean 2:1 setup;
  * the freeze produces a stable, re-verifiable sha256;
  * the resolver's R-math is correct (target -> +R:R, stop -> -1, adverse tie -> stop, horizon mark);
  * the forward-only assertion DISCARDS a pre-freeze bar;
  * the kill switch HALTS a significantly-negative stream past N_min and spares a noisy positive.
"""

from __future__ import annotations

import json
import sys

from . import Refused
from .frozen import frozen_spec
from . import proposer, resolve as resolver, scoring


def _expect_refused(fn, label):
    try:
        fn()
    except Refused:
        return
    raise Refused(f"selftest FAILED: expected a Refused for {label}, got none")


def run_selftest() -> int:
    spec = frozen_spec()
    out = {"framing": "hermetic wiring check; no network, no ledger, no orders"}

    base = {"instrument": "SPY", "asset_class": "equity", "direction": "long",
            "entry_ref": 100.0, "stop": 99.0, "target": 103.0, "horizon_hours": 24,
            "thesis": "synthetic clean setup for the wiring test with a >=2:1 reward to risk ratio.",
            "confidence": 0.5, "event_ids": ["deadbeef"]}

    # ACCEPT a clean 2:1 (reward 3, risk 1 -> R:R 3.0).
    good = proposer.validate_setup(base, spec, n_open=0)
    assert abs(good["reward_to_risk"] - 3.0) < 1e-9, "R:R computed wrong"
    frozen = proposer.freeze_setup(good, proposed_utc="2026-08-23T12:00:00+00:00")
    assert proposer.freeze_setup(dict(good), proposed_utc="2026-08-23T12:00:00+00:00")["setup_sha256"] \
        == frozen["setup_sha256"], "freeze hash not stable"
    out["accepts_clean_2to1"] = True
    out["freeze_hash_stable"] = True

    # REJECTIONS.
    _expect_refused(lambda: proposer.validate_setup(dict(base, stop=None), spec), "missing stop")
    _expect_refused(lambda: proposer.validate_setup(dict(base, target=101.0), spec), "R:R < 2 (=1.0)")
    _expect_refused(lambda: proposer.validate_setup(dict(base, stop=101.0), spec),
                    "long with stop above entry")
    _expect_refused(lambda: proposer.validate_setup(dict(base, account_risk_pct=2.0), spec),
                    "risk > 1%")
    _expect_refused(lambda: proposer.validate_setup(base, spec, n_open=5), "6th concurrent setup")
    _expect_refused(lambda: proposer.validate_setup(dict(base, instrument="ENRON"), spec),
                    "unknown instrument")
    _expect_refused(lambda: proposer.validate_setup(dict(base, horizon_hours=999), spec),
                    "horizon out of bounds")
    out["rejects_all_rule_violations"] = True

    # RESOLVER R-math on synthetic bars. entry 100, stop 99, target 103, risk 1, R:R 3.
    fe = 1_000_000  # freeze epoch
    # Drive the private walker directly on synthetic bars (long, entry 100, stop 99, target 103).
    def _run(bars):
        return resolver._walk("long", 100.0, 99.0, 103.0, 1.0, bars,
                              spec["rules"]["adverse_tie_break"])

    hit_target = _run([(fe + 10, 103.5, 100.0, 103.0)])
    assert hit_target[1] == "target" and abs(hit_target[0] - 3.0) < 1e-9, f"target R wrong: {hit_target}"
    hit_stop = _run([(fe + 10, 100.2, 98.5, 99.0)])
    assert hit_stop[1] == "stop" and abs(hit_stop[0] + 1.0) < 1e-9, f"stop R wrong: {hit_stop}"
    tie = _run([(fe + 10, 103.5, 98.5, 100.0)])
    assert tie[1] == "stop_adverse_tie" and abs(tie[0] + 1.0) < 1e-9, f"adverse tie wrong: {tie}"
    horizon = _run([(fe + 10, 101.0, 99.5, 101.0)])  # neither touched -> mark at 101 -> +1R
    assert horizon[1] == "horizon_mark" and abs(horizon[0] - 1.0) < 1e-9, f"horizon mark wrong: {horizon}"
    out["resolver_r_math_correct"] = True

    # Forward-only assertion discards a pre-freeze bar.
    pre = [(fe - 5, 200.0, 0.1, 103.0), (fe + 5, 101.0, 100.0, 101.0)]
    kept = resolver._assert_forward(pre, fe, "SPY")
    assert kept == [(fe + 5, 101.0, 100.0, 101.0)], "forward-only assertion did not drop pre-freeze bar"
    out["forward_only_drops_pre_freeze_bar"] = True

    # Kill switch: a steady loser past N_min HALTS; a noisy positive does not.
    losers = [-1.0 if i % 3 else -0.5 for i in range(35)]  # all negative, n>=N_min
    winners = [3.0 if i % 2 else -1.0 for i in range(35)]  # noisy but positive mean
    kL = scoring.kill_check(losers, spec)
    kW = scoring.kill_check(winners, spec)
    assert kL["verdict"].startswith("HALTED"), f"kill did not halt a steady loser: {kL['verdict']}"
    assert not kW["verdict"].startswith("HALTED"), f"kill wrongly halted a noisy winner: {kW['verdict']}"
    out["kill_halts_loser_spares_winner"] = True

    # Expectancy arithmetic.
    exp = scoring._expectancy([3.0, 3.0, -1.0, -1.0])  # winrate .5, avgWin 3, avgLoss 1 -> +1.0
    assert abs(exp["expectancy_R"] - 1.0) < 1e-9, f"expectancy wrong: {exp}"
    out["expectancy_arithmetic_correct"] = True

    # Ticker attribution (FAULT FIX 2026-09-03): a per-ticker feed item that does not name the
    # ticker must NOT be tagged with it; provenance survives in feed_ticker.
    from . import world_reader as _wr
    _false = _wr._mk_event("YAHOO_RSS", "Why Goldgroup Mining Stock Soared on Wednesday", None,
                           "http://x/1", "Precious metals had a good day.", tickers=["NVDA"],
                           feed_ticker="NVDA", verify_mentions=True)
    assert _false["tickers"] == [], f"false ticker attribution survived: {_false}"
    assert _false["feed_ticker"] == "NVDA", "feed provenance lost"
    _sym = _wr._mk_event("YAHOO_RSS", "NVDA guides higher", None, "http://x/2", "", tickers=["NVDA"],
                         feed_ticker="NVDA", verify_mentions=True)
    _name = _wr._mk_event("YAHOO_RSS", "Broadcom outlook weighs on stock", None, "http://x/3", "",
                          tickers=["AVGO"], feed_ticker="AVGO", verify_mentions=True)
    assert _sym["tickers"] == ["NVDA"] and _name["tickers"] == ["AVGO"], "true mention dropped"
    out["ticker_attribution_verified"] = True

    # Data-path fault #1 (FIXED 2026-09-03): the read digest truncated a globally recency-sorted
    # stream, so a high-volume feed crowded the window and a low-volume feed could be 0% visible to
    # the agent proposing off it. Measured live: SEC_8K 7/40, GOOGLE_NEWS 0/15. The digest must now
    # represent EVERY feed present in the stream.
    from .__main__ import _stratified
    synth = ([{"source": "LOUD", "id": f"l{i}"} for i in range(500)]
             + [{"source": "QUIET", "id": f"q{i}"} for i in range(3)]
             + [{"source": "RARE", "id": "r0"}])
    picked = _stratified(synth, 60)
    seen = {e["source"] for e in picked}
    assert seen == {"LOUD", "QUIET", "RARE"}, f"digest hid a whole feed: {seen}"
    assert len(picked) == 60, f"digest lost its budget: {len(picked)}"
    assert sum(1 for e in picked if e["source"] == "QUIET") == 3, "low-volume feed under-shown"
    out["datapath_digest_represents_every_feed"] = True

    # Data-path fault #2 (FIXED 2026-09-03): read_google_news caught each query's failure and
    # `continue`d, so ALL queries could fail and the feed reported 0 items with feed_errors == {} --
    # a blind eye indistinguishable from "no news". Partial failure must surface; total failure raises.
    from . import world_reader as _w
    _calls = {"n": 0}

    def _flaky(url):
        _calls["n"] += 1
        if _calls["n"] % 2:
            raise Refused("simulated 429")
        return ("<rss><channel><item><title>ok</title><link>http://x</link>"
                "<description>d</description></item></channel></rss>")

    _real = _w.http_get_text
    try:
        _w.http_get_text = _flaky
        got = _w.read_google_news(spec, ["a", "b", "c", "d"])
        assert getattr(got, "partial_errors", None), "partial feed failure went silent"
        # A well-formed 200 with zero items is a throttle, not "no news" -- it must not go silent.
        _w.http_get_text = lambda url: "<rss><channel></channel></rss>"
        blank = _w.read_google_news(spec, ["a", "b"])
        raise AssertionError(f"blank-but-valid feed did not raise: {blank}")
    except Refused:
        pass
    finally:
        _w.http_get_text = _real
    try:
        _w.http_get_text = lambda url: (_ for _ in ()).throw(Refused("simulated 429"))
        try:
            _w.read_google_news(spec, ["a", "b"])
            raise AssertionError("total feed failure did not raise past its boundary")
        except Refused:
            pass
    finally:
        _w.http_get_text = _real
    out["datapath_feed_failure_never_silent"] = True

    out["ALL_PASSED"] = True
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0
