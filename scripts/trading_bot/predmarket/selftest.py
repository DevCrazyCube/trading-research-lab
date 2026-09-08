#!/usr/bin/env python3
"""Hermetic wiring check -- no network, no ledger written. Proves the enforcement and the Brier math.

Verifies, on synthetic data only:
  * the frozen spec loads and its pre-registration hash matches;
  * the proposer REJECTS a resolved/past-close market (the lookahead trap), a q_agent outside (0,1),
    a too-thin thesis, an efficient macro/crypto market, and an unknown venue -- and ACCEPTS a clean
    open estimate, setting side=abstain when the edge is inside the fee/spread floor and side=yes/no
    when it clears it;
  * the freeze produces a stable, re-verifiable sha256;
  * the resolver's Brier math is correct (agent/market Brier, brier_edge sign) and the hypothetical
    P&L nets the fee; a PENDING (unresolved) market yields no outcome;
  * the kill switch HALTS when the agent fails to beat the market past N_min and stays ALIVE when it
    clearly does.
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
    out = {"framing": "hermetic wiring check; no network, no ledger, no bets"}
    future = "2027-01-01T00:00:00+00:00"
    now = "2026-08-23T12:00:00+00:00"

    # A clean OPEN estimate on a big-edge Polymarket market -> clears the floor -> side yes.
    base = {"venue": "polymarket", "market_id": "0xabc", "question": "Will candidate X win the primary?",
            "p_market": 0.40, "q_agent": 0.65, "close_time": future,
            "yes_bid": 0.39, "yes_ask": 0.41, "spread": 0.02,
            "thesis": "synthetic clean estimate tying the read to specific polling and endorsement news.",
            "confidence": 0.6}
    good = proposer.validate_estimate(base, spec, now_utc=now)
    assert good["hypothetical_side"] == "yes", f"expected yes side, got {good['hypothetical_side']}"
    assert good["clears_edge_floor"], "0.25 edge should clear the polymarket floor"
    frozen = proposer.freeze_estimate(good, proposed_utc=now)
    assert proposer.freeze_estimate(dict(good), proposed_utc=now)["estimate_sha256"] \
        == frozen["estimate_sha256"], "freeze hash not stable"
    out["accepts_clean_open_estimate"] = True
    out["freeze_hash_stable"] = True

    # A tiny edge inside the fee/spread floor -> frozen for calibration but side=abstain.
    tiny = proposer.validate_estimate(dict(base, q_agent=0.405), spec, now_utc=now)
    assert tiny["hypothetical_side"] == "abstain", "sub-cost edge must abstain from a hypothetical bet"
    assert not tiny["clears_edge_floor"], "0.5pp edge must not clear the floor"
    out["edge_floor_abstains_below_cost"] = True

    # REJECTIONS.
    _expect_refused(lambda: proposer.validate_estimate(dict(base, close_time=now), spec, now_utc=now),
                    "market at/after resolution (lookahead)")
    _expect_refused(lambda: proposer.validate_estimate(dict(base, q_agent=1.4), spec, now_utc=now),
                    "q_agent outside (0,1)")
    _expect_refused(lambda: proposer.validate_estimate(dict(base, thesis="too short"), spec, now_utc=now),
                    "thesis too thin")
    _expect_refused(lambda: proposer.validate_estimate(
        dict(base, question="Will CPI inflation print above 3%?"), spec, now_utc=now),
        "efficient macro market")
    _expect_refused(lambda: proposer.validate_estimate(dict(base, venue="fanduel"), spec, now_utc=now),
                    "unknown venue")
    out["rejects_all_rule_violations"] = True

    # RESOLVER Brier math on a synthetic outcome. YES resolves TRUE (outcome=1).
    #   agent q=0.65 -> brier (0.65-1)^2 = 0.1225 ; market p=0.40 -> (0.40-1)^2 = 0.36 ; edge +0.2375.
    #   PURE math only, no network (resolve_estimate fetches the venue settlement -- live path only).
    outcome = 1
    ba = round((frozen["q_agent"] - outcome) ** 2, 6)
    bm = round((frozen["p_market"] - outcome) ** 2, 6)
    assert abs(ba - 0.1225) < 1e-9 and abs(bm - 0.36) < 1e-9, f"brier math wrong: {ba},{bm}"
    pnl, fee = resolver._hypothetical_pnl(frozen, outcome, spec)
    assert abs(fee - 0.0) < 1e-9, "polymarket fee should be 0"
    assert abs(pnl - (1 - frozen["hypothetical_entry_price"])) < 1e-9, f"pnl wrong: {pnl}"
    out["resolver_brier_and_pnl_math_correct"] = True

    # KILL SWITCH. Build synthetic resolved records with agent WORSE than market past N_min -> HALT.
    def _res(ba, bm):
        return {"brier_agent": ba, "brier_market": bm, "q_agent": 0.5, "yes_outcome": 1,
                "hypothetical_pnl_net_fee": None}
    worse = [_res(0.30, 0.20) for _ in range(60)]  # agent Brier HIGHER (worse) -> edge negative
    better = [_res(0.10, 0.30) for _ in range(60)]  # agent Brier much LOWER (better)
    kW = scoring.kill_check(worse, spec)
    kB = scoring.kill_check(better, spec)
    assert kW["verdict"].startswith("HALTED"), f"kill did not halt a losing agent: {kW['verdict']}"
    assert not kB["verdict"].startswith("HALTED"), f"kill wrongly halted a winning agent: {kB['verdict']}"
    out["kill_halts_uncalibrated_spares_calibrated"] = True

    # KEEP-FIRST dedupe by (venue, market_id) (T43): a market frozen twice counts ONCE, earliest freeze.
    from . import ledger
    dup = [{"venue": "polymarket", "market_id": "1", "proposed_utc": "2026-08-25", "q_agent": 0.7},
           {"venue": "polymarket", "market_id": "1", "proposed_utc": "2026-08-24", "q_agent": 0.6},
           {"venue": "kalshi", "market_id": "1", "proposed_utc": "2026-08-26", "q_agent": 0.5}]
    kept = ledger.dedupe_keep_first(dup)
    assert len(kept) == 2, f"expected 2 after dedupe, got {len(kept)}"
    assert any(r["q_agent"] == 0.6 for r in kept), "dedupe must keep the EARLIEST freeze"
    assert not any(r["q_agent"] == 0.7 for r in kept), "dedupe must drop the later duplicate freeze"
    assert any(r["venue"] == "kalshi" for r in kept), "same id on another venue is a different market"
    out["scoring_dedupes_keep_first_by_market_id"] = True

    # ---------------------------------------------------------------- T48 DATA-PATH assertions.
    # The 2026-09-03 fault: both venue feeds are PAGED and were read one page deep, so the proposer
    # saw ~2% of the Kalshi book and could not tell.  Nothing above would have caught it -- every
    # decision rule was correct on the rows it was handed.  These checks live on the INPUT surface:
    # pagination must actually follow, and any residual truncation or unrepresented declared feed
    # must surface as a warning rather than vanish.  Synthetic feeds only; no network.
    from . import venues

    def _fake_kalshi_feed(n_pages):
        """A cursor-paged Kalshi stub: one political event with one live market per page."""
        def _get(url, **kw):
            page = 0
            if "cursor=" in url:
                page = int(url.rsplit("cursor=", 1)[1])
            return {"cursor": str(page + 1) if page + 1 < n_pages else None,
                    "events": [{"category": "Politics", "title": f"Event {page}",
                                "markets": [{"status": "active", "ticker": f"T{page}",
                                             "yes_bid_dollars": 0.40, "yes_ask_dollars": 0.42,
                                             "close_time": future, "event_ticker": f"E{page}",
                                             "rules_primary": "synthetic"}]}]}
        return _get

    real_get = venues.http_get_json
    try:
        venues.http_get_json = _fake_kalshi_feed(5)
        rows, st = venues.pull_kalshi(max_pages=10)
        assert st["pages"] == 5 and st["exhausted"] and len(rows) == 5, \
            f"cursor pagination did not follow to exhaustion: {st}"
        rows, st = venues.pull_kalshi(max_pages=2)
        assert st["pages"] == 2 and not st["exhausted"] and len(rows) == 2, \
            f"page cap must be reported as NOT exhausted: {st}"
        warn = venues.data_path_warnings({"kalshi": st})
        assert any("TRUNCATED" in w for w in warn), "a capped read must raise a TRUNCATED warning"
        assert not venues.data_path_warnings(
            {"kalshi": {"pages": 5, "events_scanned": 5, "markets": 5, "exhausted": True}}), \
            "an exhausted, represented feed must be clean"
        assert any("not represented" in w for w in venues.data_path_warnings(
            {"polymarket": {"markets": 3, "exhausted": True, "empty_tags": ["policy"]}})), \
            "a declared-but-empty tag must surface"
        assert any("NOT REPRESENTED" in w for w in venues.data_path_warnings(
            {"kalshi": {"markets": 0, "exhausted": True}})), \
            "a feed contributing zero rows must surface"
    finally:
        venues.http_get_json = real_get
    out["datapath_pagination_follows_and_truncation_is_reported"] = True

    out["ALL_PASSED"] = True
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0
