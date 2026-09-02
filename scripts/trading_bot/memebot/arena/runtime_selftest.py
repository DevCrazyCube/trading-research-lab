#!/usr/bin/env python3
"""Hermetic negative-control battery for the Arena lifecycle and causal arms."""
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace
import tempfile

from . import fill as F
from . import manifest as MF
from . import runtime as RT
from . import bundle_runtime as BR
from .arms import bundle_momentum as BM
from .arms import graduation as G
from .chainledger import ChainLedger
from .. import ws_data
from ...aftershock.pac_v2_pumpswap import PumpSwapReserves, sell_quote


class DummyArm:
    instrument = "DUMMY_ARENA"
    service_kind = "snapshot"
    def code_sha256(self): return "1" * 64
    def prereg_sha256(self): return "2" * 64
    def spec_sha256(self): return "3" * 64


def main() -> int:
    checks = 0
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)

        # Activation is set-once and byte tampering refuses through the real parser/hash path.
        old_dir, old_tape, old_git = MF.ACTIVATION_DIR, ws_data.TRADE_BUFFER_PATH, MF._git
        MF.ACTIVATION_DIR = root / "activations"
        ws_data.TRADE_BUFFER_PATH = root / "tape.jsonl"
        MF._git = lambda *args: "a" * 40
        try:
            activation = MF.write_activation(DummyArm())
            assert MF.require_activation(DummyArm(), require_git_anchor=False)["activation_sha256"] \
                   == activation["activation_sha256"]
            try:
                MF.write_activation(DummyArm()); raise AssertionError("activation overwrite allowed")
            except RuntimeError:
                pass
            path = MF.activation_path(DummyArm())
            value = json.loads(path.read_text()); value["activated_unix_nanos"] -= 1
            path.write_text(json.dumps(value))
            try:
                MF.require_activation(DummyArm(), require_git_anchor=False)
                raise AssertionError("activation tamper accepted")
            except RuntimeError:
                pass
            checks += 2
        finally:
            MF.ACTIVATION_DIR, ws_data.TRADE_BUFFER_PATH, MF._git = old_dir, old_tape, old_git

        # State-first WAL can replay after a crash without duplicate ledger rows.
        ledger = ChainLedger(root / "ledger.jsonl", "X", "c", "p", "s", "a")
        state_path = root / "state.json"
        row = {"entry_id": "e1", "mint": "m", "net_return": 0.0}
        state = {"pending_events": [{"kind": "opened", "row": row, "finalize": {}}], "open": {}}
        RT._save(state_path, state); RT._drain_pending(state, ledger, state_path)
        state["pending_events"] = [{"kind": "opened", "row": row, "finalize": {}}]
        RT._drain_pending(state, ledger, state_path)
        assert sum(r.get("kind") == "opened" for r in ledger._rows()) == 1
        checks += 1

        # Phase-0 #4 PROOF — an API-outage MEASUREMENT_FAILURE drains as a VOID (NOT a -100% resolved),
        # pops the open (F1), and is excluded from primary N by the cohort split.
        from . import cohorts as CH
        L2 = ChainLedger(root / "l2.jsonl", "V", "c", "p", "s", "a")
        sp2 = root / "s2.json"
        st2 = {"pending_events": [{"kind": "void", "row": {"void_id": "v1", "mint": "mm",
               "reason": "MEASUREMENT_FAILURE", "cohort": "PRIMARY"},
               "finalize": {"remove_open_mint": "mm"}}], "open": {"mm": {"entry_id": "e"}}}
        RT._save(sp2, st2); RT._drain_pending(st2, L2, sp2)
        assert "mm" not in st2["open"]                                  # void terminated the position
        voids = [r for r in L2._rows() if r.get("kind") == "void"]
        assert len(voids) == 1 and voids[0]["reason"] == "MEASUREMENT_FAILURE" and not L2.resolved()
        coh = CH.split_cohorts(L2.resolved(), voids)
        assert coh["primary_n"] == 0 and coh["measurement_failure_n"] == 1
        checks += 1

        # PROOF — the arbiter never fabricates a rug: an alive coin (recent txns) -> MEASUREMENT_VOID; a
        # positively-dead one (no trades + drained balance) -> RUG_CONFIRMED.
        from . import helius_rug_arbiter as ARB
        NOW = 2_000_000_000 * 1_000_000_000
        sec = NOW // 1_000_000_000
        alive = ARB.classify_unpriced("m", None, now_ns=NOW, rpc=lambda meth, p: [{"blockTime": sec - 30}] * 5)
        assert alive["verdict"] == "MEASUREMENT_VOID", alive
        dead = ARB.classify_unpriced("m", "pool", now_ns=NOW,
               rpc=lambda meth, p: {"value": 0} if meth == "getBalance" else [{"blockTime": sec - 9 * 3600}])
        assert dead["verdict"] == "RUG_CONFIRMED", dead
        checks += 1

        # PROOF (handoff 460) — a stale process (boot closure != current on-disk closure) REFUSES, so an
        # old resolver can never run under a freshly-written activation.
        class _StaleArm:
            instrument = "BOOTX"
            def code_sha256(self): return "disk_after_commit"
        RT._BOOT_SHAS["BOOTX"] = "code_loaded_at_boot"       # process booted with the OLD code
        try:
            RT._boot_guard(_StaleArm()); raise AssertionError("stale process allowed to run old code")
        except RuntimeError as exc:
            assert "BOOT CLOSURE DRIFT" in str(exc)
        RT._BOOT_SHAS["BOOTX"] = "disk_after_commit"         # after a real restart boot==disk -> allowed
        RT._boot_guard(_StaleArm())                          # no raise
        del RT._BOOT_SHAS["BOOTX"]
        checks += 1

        # PumpPortal tape append is chained; changing a persisted byte is refused.
        old_tape, old_reserve = ws_data.TRADE_BUFFER_PATH, ws_data._RESERVE_BYTES
        ws_data.TRADE_BUFFER_PATH, ws_data._RESERVE_BYTES = root / "trade.jsonl", 0
        try:
            body = {"schema": 2, "mint": "m", "received_unix_nanos": 1}
            ws_data._append_trade(body, (0, "0" * 64)); assert ws_data._trade_head()[0] == 1
            value = json.loads(ws_data.TRADE_BUFFER_PATH.read_text()); value["mint"] = "x"
            ws_data.TRADE_BUFFER_PATH.write_text(json.dumps(value) + "\n")
            try:
                ws_data._trade_head(); raise AssertionError("trade-tape tamper accepted")
            except Exception:
                pass
            checks += 1
        finally:
            ws_data.TRADE_BUFFER_PATH, ws_data._RESERVE_BYTES = old_tape, old_reserve

    # The sixth-buy decision, actual-size entry, and fee-charged fill all execute exactly once.
    rows = [{"received_unix_nanos": 1_000_000_000 + i * 100_000_000, "sequence": i + 1,
             "tx_type": "buy", "trader": "a" if i < 3 else "b", "token_amount": "10",
             "record_sha256": f"{i + 1:064x}"} for i in range(6)]
    assert BM.first_six_signal(rows) and BR._entry_token_atoms((30.0, 1_000_000_000.0, 1.0)) > 0
    causal = F.causal_fill_cp((30.0, 1e9), (30.0, 1e9), BM.SIZE_SOL)
    assert causal.net_return < 0 and causal.decomposition["buy_toll"] > 0
    checks += 2

    # Migration routes through a typed PumpSwap quote and includes fixed costs.
    reserves = PumpSwapReserves(900_000_000_000_000, 80_000_000_000, 20, 5, 5)
    raw = {"mint": "11111111111111111111111111111111", "token_atoms": 1_000_000_000,
           "entry_price": 1e-7, "opened_unix_nanos": 1, "entry_id": "e"}
    observation = SimpleNamespace(reserves=reserves, response_received_unix_nanos=2_000_000_001,
                                  raw_response_sha256="f" * 64)
    migration = BR._migration_result(raw, "primary", observation)
    assert migration["basis"] == "pumpswap_exact_cp" and migration["reason"] == "MIGRATION_EXIT"
    checks += 1

    # Graduation math is exact-integer and the preregistered N=30 sign tripwire fires.
    buy = G.buy_quote(50_000_000, reserves); assert buy["base_out_atoms"] > 0
    assert sell_quote(buy["base_out_atoms"], reserves)["net_quote_lamports"] > 0
    negative = [{"mint": f"m{i}", "entry_day": "d", "net_return": -0.1,
                 "cohort": "PROXY_PASS"} for i in range(30)]
    decision = G.ARM.final_verdict({"verdict": "COLLECTING", "reason": ""}, negative, negative)
    assert decision["verdict"] == "KILL" and decision["negative_sign_p"] < 0.05
    checks += 2

    # ============================ FIVE causal PROOFS through the V2 money-book runtimes ===================
    # These drive the REAL bundle_v2_runtime + migration_acceptance_runtime code (WAL drain, arbiter routing,
    # the shared-sizer slot, the boot-closure guard) — not module unit tests. The git-anchored `_ledger()`
    # and the RT.DATA state/slot paths are the only non-hermetic seams, so each is redirected to a tmp dir.
    from . import bundle_v2_runtime as BV2
    from . import migration_acceptance_runtime as MR
    from .arms import bundle_momentum_v2 as BM2
    from .arms import migration_acceptance as MA
    from . import sizer as SZ
    from . import cohorts as CH2

    with tempfile.TemporaryDirectory() as d3:
        r3 = pathlib.Path(d3)
        port = r3 / "portfolio.json"
        saved = (RT.DATA, BV2.PORTFOLIO_PATH, MR.PORTFOLIO, BV2._ledger, MR._ledger, MR.classify_unpriced)
        RT.DATA = r3 / "arena_data"
        BV2.PORTFOLIO_PATH = MR.PORTFOLIO = port
        bl = ChainLedger(r3 / "bundle_v2.jsonl", BV2.INSTRUMENT, "c", "p", "s", "a")
        ml = ChainLedger(r3 / "migration.jsonl", MR.INSTRUMENT, "c", "p", "s", "a")
        BV2._ledger = lambda: bl
        MR._ledger = lambda: ml
        try:
            # PROOF (1): an API-outage / arbiter MEASUREMENT_VOID drains as a VOID (F1 right-censored), NEVER a
            # −100% resolved — driven through the REAL migration −100% site `_resolve_unpriced`. And a
            # positively-dead pool (RUG_CONFIRMED) DOES book a real −100%, so it is not a blanket void.
            raw_mv = {"mint": "mm", "entry_id": "e1", "cohort": "PROXY_PASS", "entry_day": "d",
                      "entry_unix_nanos": 1, "entry_all_in_lamports": 1_000, "quote_input_lamports": 1_000,
                      "last_gross_exit_lamports": 0, "pool": "poolmm", "holds_slot": True}
            st_mv = {"pending_ledger": [], "open": {"mm": raw_mv}, "census": {}}
            assert SZ.try_acquire_primary(MR.INSTRUMENT, "mm", port)          # the open holds a global slot
            MR.classify_unpriced = lambda mint, acct=None: {"verdict": "MEASUREMENT_VOID", "reason": "alive"}
            MR._resolve_unpriced(st_mv, raw_mv, {"trigger_evidence_sha256": "f" * 64})
            assert "mm" not in st_mv["open"]                                  # F1: the open popped
            assert not ml.resolved()                                         # NOT a −100% resolved
            mv = [r for r in ml._rows() if r.get("kind") == "void"]
            assert mv and mv[-1]["reason"] == "MEASUREMENT_FAILURE", mv
            assert json.loads(port.read_text()).get(f"{MR.INSTRUMENT}:mm") is None   # slot released on pop
            raw_rug = {"mint": "dd", "entry_id": "e2", "cohort": "PROXY_PASS", "entry_day": "d",
                       "entry_unix_nanos": 1, "entry_all_in_lamports": 1_000, "quote_input_lamports": 1_000,
                       "last_gross_exit_lamports": 0, "pool": "pooldd", "holds_slot": False}
            st_rug = {"pending_ledger": [], "open": {"dd": raw_rug}, "census": {}}
            MR.classify_unpriced = lambda mint, acct=None: {"verdict": "RUG_CONFIRMED", "reason": "drained"}
            MR._resolve_unpriced(st_rug, raw_rug, {"trigger_evidence_sha256": "e" * 64})
            res = ml.resolved()
            assert res and res[-1]["reason"] == "UNAVAILABLE_FULL_LOSS" and res[-1]["net_return"] <= -0.99
            checks += 1

            # PROOF (2): at most TWO concurrent PRIMARY opens ACROSS arms against ONE shared portfolio.json; a
            # 3rd is refused — the REAL bundle_v2 open-site emits a strategy VOID, never a 3rd open.
            port.unlink()
            assert SZ.try_acquire_primary(BM2.ARM.instrument, "m1", port)     # arm A takes slot 1
            assert SZ.try_acquire_primary(MA.ARM.instrument, "m2", port)      # arm B takes slot 2 (across arms)
            assert not SZ.try_acquire_primary(BM2.ARM.instrument, "m3", port)  # global cap hit, 3rd refused
            st_full = {"pending_ledger": [], "open": {}, "pending_entries": {}, "sampled_mints": {}, "voids": 0}
            BV2._emit_candidate_void(st_full, "m3", "e3", "PORTFOLIO_SLOTS_FULL", 123)
            vb = [r for r in bl._rows() if r.get("kind") == "void"]
            assert vb and vb[-1]["reason"] == "PORTFOLIO_SLOTS_FULL" and "m3" not in st_full["open"]
            assert len(json.loads(port.read_text())) == 2                    # still EXACTLY two primaries
            checks += 1

            # PROOF (3): a CONTROL_PROXY_FAIL never takes a slot (the runtime's open-site only acquires for
            # PROXY_PASS) and never enters primary_n (cohorts + include_resolution — the real primary gate).
            port.unlink()
            for cohort in ("PROXY_PASS", "CONTROL_PROXY_FAIL"):
                if cohort == "PROXY_PASS":                                    # mirrors _open_candidate's guard
                    SZ.try_acquire_primary(MA.ARM.instrument, "pp", port)
            slots = json.loads(port.read_text()) if port.exists() else {}
            assert f"{MA.ARM.instrument}:cm" not in slots                     # control never claimed a slot
            rows = [{"mint": "pp", "entry_day": "d", "net_return": 0.1, "cohort": "PROXY_PASS"},
                    {"mint": "cm", "entry_day": "d", "net_return": -0.5, "cohort": "CONTROL_PROXY_FAIL"}]
            coh = CH2.split_cohorts(rows, [])
            assert coh["primary_n"] == 1 and coh["control_n"] == 1
            assert MA.ARM.include_resolution(rows[0]) and not MA.ARM.include_resolution(rows[1])
            checks += 1

            # PROOF (4): a restart does not leak a slot — acquire, "crash" before the open is recorded (live
            # open set empty), then the runtime's cycle-start `reconcile_slots` frees THIS arm's orphan only.
            port.unlink()
            assert SZ.try_acquire_primary(BM2.ARM.instrument, "orphan", port)   # claimed, then crash
            assert SZ.reconcile_slots(BM2.ARM.instrument, [], port) == ["orphan"]   # cycle-start self-heal
            assert json.loads(port.read_text()) == {} and SZ.try_acquire_primary(MA.ARM.instrument, "x", port)
            checks += 1

            # PROOF (5): a stale process (boot closure != on-disk closure) REFUSES via BOTH runtimes' guards,
            # so an old resolver can never run under a freshly-written activation.
            for MOD, attr in ((BV2, "_BOOT_CLOSURE_SHA"), (MR, "_BOOT_SHA")):
                keep = getattr(MOD, attr)
                setattr(MOD, attr, "0" * 64)
                try:
                    MOD._boot_guard(); raise AssertionError("stale process allowed to run old code")
                except RuntimeError as exc:
                    assert "BOOT CLOSURE DRIFT" in str(exc)
                setattr(MOD, attr, keep)
                MOD._boot_guard()                                            # boot == disk after restart → ok
            checks += 1
        finally:
            (RT.DATA, BV2.PORTFOLIO_PATH, MR.PORTFOLIO, BV2._ledger, MR._ledger,
             MR.classify_unpriced) = saved

    print(f"MEME ARENA runtime selftest: PASS ({checks} hardened controls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
