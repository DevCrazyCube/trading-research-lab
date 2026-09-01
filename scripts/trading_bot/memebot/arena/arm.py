#!/usr/bin/env python3
"""MEME ARENA — the arm plug-in interface. Every arm (virality_arrival, bundle_momentum, graduation)
implements this ABC. The runtime owns the shared feed, gate, exit engine, ledger and scorer; an arm only
supplies its NAME, its frozen spec/pre-registration hashes, its ENTRY predicate (from data observable
strictly at/before the decision), and its fill basis. It never prices a fill itself and never writes the
ledger directly — those go through the shared honest modules, which is what keeps every arm honest.
"""
from __future__ import annotations

import abc


class Arm(abc.ABC):
    #: instrument id, e.g. "VIRALITY_ARRIVAL_V2_1"
    instrument: str = "UNSET"
    #: "snapshot" (tier-1 optimistic bound) | "causal_cp" (tier-2 executable)
    fill_basis: str = "snapshot"
    #: pre-registered decision sample and (optional) one-time extension cap
    target_n: int = 120
    extended_cap: int | None = 200

    @abc.abstractmethod
    def code_sha256(self) -> str:
        """sha256 of this arm's own source file, for the ledger genesis binding."""

    @abc.abstractmethod
    def prereg_sha256(self) -> str:
        """sha256 of this arm's frozen PREREGISTRATION file."""

    @abc.abstractmethod
    def spec_sha256(self) -> str:
        """sha256 of the frozen numeric spec (thresholds/constants)."""

    @abc.abstractmethod
    def candidates(self, feed) -> list[dict]:
        """Given the shared feed snapshot, return candidate coins to consider THIS cycle. Each candidate
        must carry the fields the entry predicate + gate + fill need (mint, price/reserves, age, flow…)."""

    @abc.abstractmethod
    def entry_ok(self, candidate: dict, history: list[dict]) -> bool:
        """The frozen entry predicate, using ONLY features observable at/before the decision instant. No
        lookahead. `history` is this mint's prior observations kept by the runtime."""

    def cluster_key(self, resolved_row: dict) -> tuple:
        """The bootstrap cluster for a resolved trade — default (mint, entry-day). Override if needed."""
        day = int(resolved_row.get("held_s", 0))  # placeholder; runtime injects entry-day
        return (resolved_row.get("mint"), resolved_row.get("entry_day", day))


if __name__ == "__main__":
    # the ABC must refuse instantiation until every hook is implemented (keeps arms honest-by-contract)
    class Incomplete(Arm):
        pass
    try:
        Incomplete()
        raise AssertionError("abstract arm should not instantiate")
    except TypeError:
        pass

    class Toy(Arm):
        instrument = "TOY"
        def code_sha256(self): return "c"
        def prereg_sha256(self): return "p"
        def spec_sha256(self): return "s"
        def candidates(self, feed): return feed
        def entry_ok(self, c, h): return c.get("go", False)
    t = Toy()
    assert t.entry_ok({"go": True}, []) and not t.entry_ok({}, [])
    assert t.cluster_key({"mint": "m", "entry_day": "d"}) == ("m", "d")
    print("arm.py self-check OK: ABC enforced, toy arm plugs in")
