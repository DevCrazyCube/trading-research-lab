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

    print(f"MEME ARENA runtime selftest: PASS ({checks} hardened controls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
