#!/usr/bin/env python3
"""Integrity selftest for the Launch-Window Sentinel Scalper (PAC_LWS / PAC_LWS_NULL).

Grows with the build. Coverage: the deadness/insider screen (pac_lws_screen) — byte-identical to the
validated b20b.score, no-lookahead, cross-check coverage loss, shadow footprint signals — PLUS the
multi-position runner: reserve reconstruction equals the create-event state at t0, the veto reads only
[t0,t0+60] and the entry is strictly after (no lookahead), the veto arm admits only SURVIVED while the
null arm admits regardless, the produced ledger rows hash-chain through the audited core, the two arms
carry distinct sealed closures, and no execution surface is imported.
"""
from __future__ import annotations

import importlib
import random

from . import pac_lws_screen as screen
from . import pac_lws_runner as runner
from . import pac_lws_common as common
from . import pac_lws_manifest as veto_manifest
from . import pac_lws_null_manifest as null_manifest


def _b20b_flag(window):
    """b20b.score's exact net-holding flag, re-implemented locally as the oracle."""
    held = {}
    for _slot, user, is_buy, amount in window:
        held[user] = held.get(user, 0) + (amount if is_buy else -amount)
    total = sum(v for v in held.values() if v > 0)
    if total <= 0:
        return None
    return max(held.values()) * 100 >= total * screen.CONCENTRATION_THRESHOLD


def _checks():
    yield "frozen rule pinned 60/95/2", (
        screen.K_SLOTS == 60 and screen.CONCENTRATION_THRESHOLD == 95
        and screen.MIN_BUYERS_TO_SCORE == 2)

    # byte-identical agreement with the validated b20b flag over random windows
    rng = random.Random(1234)
    scored = mism = 0
    for _ in range(500):
        t0 = rng.randint(1000, 2000)
        window = [(t0 + rng.randint(0, 60), f"w{rng.randint(0, 6)}",
                   rng.random() < 0.75, rng.randint(1, 10_000_000))
                  for _ in range(rng.randint(2, 14))]
        v = screen.evaluate([screen.WindowTrade(slot=s, trader=u, is_buy=b, token_amount=a)
                             for s, u, b, a in window], t0_slot=t0)
        ref = _b20b_flag(window)
        buyers = len({u for s, u, b, a in window if b})
        if buyers < 2 or ref is None:
            if v.status in (screen.SURVIVED, screen.VETO_CONCENTRATION):
                mism += 1
            continue
        scored += 1
        if v.flagged != ref:
            mism += 1
    yield f"screen matches b20b on {scored} scored windows", mism == 0

    veto = [screen.WindowTrade(100, "whale", True, 96), screen.WindowTrade(101, "b", True, 4)]
    yield "veto fires at >=95% concentration", screen.evaluate(veto, t0_slot=100).status == screen.VETO_CONCENTRATION
    surv = [screen.WindowTrade(100, "a", True, 60), screen.WindowTrade(101, "b", True, 40)]
    sv = screen.evaluate(surv, t0_slot=100)
    yield "screen survives 60/40 split", sv.status == screen.SURVIVED and sv.enter_allowed and sv.top_share_bps == 6000
    yield "single buyer is unreadable (refuse)", (
        screen.evaluate([screen.WindowTrade(100, "a", True, 99)], t0_slot=100).status == screen.UNREADABLE)
    la = surv + [screen.WindowTrade(200, "whale", True, 100000)]   # after t0+60
    yield "no lookahead: post-window whale ignored", screen.evaluate(la, t0_slot=100).status == screen.SURVIVED
    cc = [screen.WindowTrade(100, "a", True, 60, reserve_delta_tokens=60),
          screen.WindowTrade(101, "b", True, 40, reserve_delta_tokens=999)]
    cv = screen.evaluate(cc, t0_slot=100)
    yield "cross-check drops a mismatched trade", cv.dropped_crosscheck == 1
    bund = [screen.WindowTrade(100, "j1", True, 30), screen.WindowTrade(100, "j2", True, 30),
            screen.WindowTrade(105, "r", True, 40)]
    yield "shadow same-slot bundle is detected (non-decisional)", (
        screen.evaluate(bund, t0_slot=100).shadow.get("same_slot_wallets") == 2)
    yield "no execution surface imported", not any(
        m in screen.__dict__ for m in ("sendTransaction", "load_fee_payer", "build_signed_memo"))


_T0 = 443_270_000
_Q = 50_000_000                 # 0.05 SOL replay probe -> coverage floor 0.30 SOL
_BASE_NS = 1_788_217_000_000_000_000


def _ev(slot, trader, is_buy, token_amount, post_real_token, recv, *, reconciled=True, anchored=True):
    return {"mint": "M", "slot": slot, "trader": trader, "is_buy": is_buy,
            "token_amount": token_amount, "post_real_token": post_real_token,
            "pre_real_token": None, "reserve_delta_tokens": None,
            "reconciled": reconciled, "anchored": anchored, "t0_slot": _T0,
            "received_unix_nanos": recv}


def _state(veto_enabled, buffer):
    return {
        "schema": 1, "instrument_id": runner.INSTRUMENT, "seal_sha256": "a" * 64,
        "activation_unix_nanos": _BASE_NS - 10**9, "calibration_sha256": "b" * 64,
        "reaction_p90_nanos": 3_788_307_712, "veto_enabled": veto_enabled,
        "cursor": {"event_offset": 0}, "buffers": {"M": list(buffer)},
        "creation": {"M": {"t0_slot": _T0, "dev_wallet": "DEV", "bonding_curve": "CURVE",
                           "seedable": True}},
        "open_positions": {}, "pending_orders": {}, "cooldowns": {}, "recent_stops": [],
        "halt_new_entries_until": 0, "decided_mints": [], "pending_ledger_rows": [], "last_status": None,
    }


def _admit(veto_enabled, buffer):
    st = _state(veto_enabled, buffer)
    with runner._configured_core():
        rows = runner._admit_candidates(st, now=_BASE_NS, quote_input_lamports=_Q)
    return st, rows


def _runner_checks():
    pilot = importlib.import_module("scripts.b15a_shadow_pilot")

    # --- reconstruct-state-equals-create-state at t0 ---
    fields = {"virtual_sol_reserves": 30_000_000_000, "virtual_token_reserves": 1_073_000_000_000_000,
              "real_token_reserves": 793_100_000_000_000}
    create_state, _missing = pilot.state_from_create_event(fields, _T0)
    rs = runner.reconstruct_reserve_state(create_state["real_token"])
    yield "reconstruct==create-state at t0", (
        rs.virtual_quote == create_state["virtual_quote"]
        and rs.virtual_token == create_state["virtual_token"]
        and rs.real_token == create_state["real_token"]
        and rs.real_quote == 0)
    # a mid-life reconstruction stays a valid ReserveState (real<=virtual, non-negative)
    mid = runner.reconstruct_reserve_state(650_000_000_000_000)
    yield "reconstruct mid-life is a valid ReserveState with a live bid", (
        0 < mid.real_quote <= mid.virtual_quote and 0 < mid.real_token <= mid.virtual_token)

    # A post-window decision event whose reconstructed real_quote clears the coverage floor.
    post_rt = 700_000_000_000_000
    yield "coverage-floor precondition", (
        runner.reconstruct_reserve_state(post_rt).real_quote >= runner.COVERAGE_MULTIPLE * _Q)

    # --- no lookahead: the veto reads only [t0,t0+60]; a post-window whale is ignored ---
    survived_window = [_ev(_T0 + 1, "a", True, 60, 790_000_000_000_000, _BASE_NS + 1),
                       _ev(_T0 + 5, "b", True, 40, 788_000_000_000_000, _BASE_NS + 2)]
    whale_post = _ev(_T0 + 100, "whale", True, 10_000_000, post_rt, _BASE_NS + 3)  # slot > t0+60
    buffer = survived_window + [whale_post]
    wt = runner._window_trades(buffer, _T0)
    yield "window trades are confined to [t0,t0+60]", all(_T0 <= t.slot <= _T0 + 60 for t in wt) and len(wt) == 2
    verdict_full = screen.evaluate(
        [screen.WindowTrade(slot=e["slot"], trader=e["trader"], is_buy=e["is_buy"],
                            token_amount=e["token_amount"]) for e in buffer if _T0 <= e["slot"] <= _T0 + 60],
        t0_slot=_T0)
    yield "post-window whale cannot reach the veto", verdict_full.status == screen.SURVIVED

    # entry is strictly after the window: admission fires and the pending order's evidence slot > t0+60
    st, rows = _admit(True, buffer)
    entry = [r for r in rows if r["kind"] == "entry_decision"]
    yield "entry admitted strictly after t0+60", (
        len(entry) == 1 and entry[0]["minimum_context_slot"] > _T0 + 60
        and entry[0]["t0_slot"] == _T0 and len(st["pending_orders"]) == 1)

    # a mint whose window has NOT closed (no post-window event) is not entered (no lookahead into t0+60)
    open_window = [_ev(_T0 + 1, "a", True, 60, 790_000_000_000_000, _BASE_NS + 1),
                   _ev(_T0 + 30, "b", True, 40, post_rt, _BASE_NS + 2)]   # max slot t0+30 < t0+60
    _st2, rows2 = _admit(True, open_window)
    yield "no entry before the window closes", not any(
        r["kind"] in ("entry_decision", "entry_vetoed") for r in rows2)

    # --- veto arm admits only SURVIVED; null arm admits regardless ---
    veto_window = [_ev(_T0 + 1, "whale", True, 96, 790_000_000_000_000, _BASE_NS + 1),
                   _ev(_T0 + 5, "b", True, 4, 788_000_000_000_000, _BASE_NS + 2)]
    veto_buffer = veto_window + [_ev(_T0 + 100, "whale", True, 1, post_rt, _BASE_NS + 3)]
    st_v, rows_v = _admit(True, veto_buffer)
    yield "veto arm refuses a concentrated (VETO) window", (
        any(r["kind"] == "entry_vetoed" and r["filter"] == screen.VETO_CONCENTRATION for r in rows_v)
        and not any(r["kind"] == "entry_decision" for r in rows_v)
        and not st_v["pending_orders"])
    st_n, rows_n = _admit(False, veto_buffer)
    yield "null arm admits the same VETO window (shadow only)", (
        any(r["kind"] == "entry_decision" for r in rows_n)
        and any(r.get("filter") == screen.VETO_CONCENTRATION for r in rows_n)   # verdict still logged
        and len(st_n["pending_orders"]) == 1)
    st_vs, rows_vs = _admit(True, buffer)
    yield "veto arm admits a SURVIVED window", any(r["kind"] == "entry_decision" for r in rows_vs)

    # --- every produced ledger row hash-chains through the audited core ---
    ok = True
    with runner._configured_core():
        for r in (rows + rows_v + rows_n + rows_vs):
            try:
                runner.core._validate_ledger(r)
            except runner.RefusedExecution:
                ok = False
    yield "produced ledger rows validate through core hash chain", ok

    # --- the two arms are distinct sealed instruments over resolvable closures ---
    yield "veto/null closures differ only by the manifest file", (
        set(veto_manifest.dependency_paths()) ^ set(null_manifest.dependency_paths())
        == {veto_manifest.MANIFEST_PATH, null_manifest.MANIFEST_PATH})
    yield "both closures resolve to file digests", (
        len(common.dependency_digest(manifest_path=veto_manifest.MANIFEST_PATH))
        == len(veto_manifest.dependency_paths())
        and len(common.dependency_digest(manifest_path=null_manifest.MANIFEST_PATH))
        == len(null_manifest.dependency_paths()))
    yield "manifests carry opposite veto flags", (
        veto_manifest.VETO_ENABLED is True and null_manifest.VETO_ENABLED is False)

    # --- no execution/wallet surface in the runner ---
    body = "".join(str(v) for v in (runner.__doc__ or "",))
    surface = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key", "private_key",
               "sign_message", "requestAirdrop", "simulateTransaction")
    src = importlib.import_module("scripts.trading_bot.aftershock.pac_lws_runner")
    import inspect
    runner_source = inspect.getsource(src)
    yield "no execution surface in the runner", not any(tok in runner_source for tok in surface)


def run() -> int:
    failed = [name for name, ok in list(_checks()) + list(_runner_checks()) if not ok]
    if failed:
        print("PAC_LWS SELFTEST FAILED: " + "; ".join(failed))
        return 1
    print("PAC_LWS SELFTEST OK")
    return 0


def main(argv=None) -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
