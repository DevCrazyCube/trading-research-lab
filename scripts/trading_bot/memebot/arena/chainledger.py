#!/usr/bin/env python3
"""MEME ARENA — hash-chained append-only ledger, one per arm. Lifts virality_tracker's prev_hash/
record_hash chain into a class and binds the GENESIS to the arm's code + prereg + spec hashes, so a
resolve refuses if the code or the pre-registration drifted after the chain opened. The hash chain is
tamper-EVIDENCE only; git is the real append-only anchor (commit the ledger at the decision read).
Pure stdlib + filesystem; no network.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

GENESIS = "0" * 64


def _sha(v) -> str:
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_sha(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


class ChainLedger:
    def __init__(self, path, arm: str, code_sha: str, prereg_sha: str, spec_sha: str):
        self.path = pathlib.Path(path)
        self.arm = arm
        self.code_sha, self.prereg_sha, self.spec_sha = code_sha, prereg_sha, spec_sha

    # --- chain primitives ---
    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def _head(self) -> str:
        rows = self._rows()
        return rows[-1].get("record_hash", GENESIS) if rows else GENESIS

    def _write(self, row: dict) -> dict:
        body = {**row, "prev_hash": self._head()}
        rec = {**body, "record_hash": _sha(body)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        return rec

    # --- lifecycle ---
    def ensure_genesis(self) -> None:
        """Open the chain (once) by binding it to this arm's code + prereg + spec."""
        if self._rows():
            return
        self._write({"kind": "genesis", "arm": self.arm, "code_sha256": self.code_sha,
                     "prereg_sha256": self.prereg_sha, "spec_sha256": self.spec_sha})

    def bindings_match(self) -> bool:
        """True iff the genesis binding still matches the current code/prereg/spec (refuse-on-drift)."""
        rows = self._rows()
        if not rows or rows[0].get("kind") != "genesis":
            return False
        g = rows[0]
        return (g.get("code_sha256") == self.code_sha and g.get("prereg_sha256") == self.prereg_sha
                and g.get("spec_sha256") == self.spec_sha)

    def append_resolved(self, row: dict) -> dict:
        """Append a resolved trade — REFUSES if the code/prereg drifted since genesis (a resolve under
        changed rules measures nothing)."""
        self.ensure_genesis()
        if not self.bindings_match():
            raise RuntimeError(f"{self.arm}: ledger genesis binding drifted (code/prereg/spec changed) "
                               "— refusing to resolve. Freeze a new instrument instead.")
        return self._write({"kind": "resolved", **row})

    def verify(self) -> bool:
        """Recompute the whole chain: contiguous prev/record hashes + intact genesis binding."""
        rows = self._rows()
        if not rows:
            return True
        prev = GENESIS
        for r in rows:
            body = {k: v for k, v in r.items() if k != "record_hash"}
            if body.get("prev_hash") != prev or _sha(body) != r.get("record_hash"):
                return False
            prev = r["record_hash"]
        return rows[0].get("kind") == "genesis"

    def resolved(self) -> list[dict]:
        return [r for r in self._rows() if r.get("kind") == "resolved"]


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "ledger.jsonl"
        L = ChainLedger(p, "test", "codeA", "preA", "specA")
        L.append_resolved({"mint": "m1", "net_return": 0.1})
        L.append_resolved({"mint": "m2", "net_return": -0.2})
        assert L.verify() and len(L.resolved()) == 2
        # tamper: flip a byte -> verify must fail
        txt = p.read_text().splitlines()
        row = json.loads(txt[1]); row["net_return"] = 9.9
        txt[1] = json.dumps(row, separators=(",", ":"))
        p.write_text("\n".join(txt) + "\n")
        assert not ChainLedger(p, "test", "codeA", "preA", "specA").verify(), "tamper must break chain"
        # drift: a different code sha must refuse to resolve on the existing chain
        L2 = ChainLedger(pathlib.Path(d) / "l2.jsonl", "test", "codeA", "preA", "specA")
        L2.append_resolved({"mint": "x", "net_return": 0.0})
        drifted = ChainLedger(L2.path, "test", "codeB", "preA", "specA")   # code changed
        try:
            drifted.append_resolved({"mint": "y", "net_return": 0.0})
            raise AssertionError("drift should have refused")
        except RuntimeError:
            pass
        print("chainledger.py self-check OK: chain verifies, tamper breaks it, drift refuses to resolve")
