"""Causal creation-name observer. Development diagnostics only; always NO_TRADE.

Run: python -m scripts.birth_origin --out <new-directory>
Reads the existing canonical CreateEvent corpus; never reads prices or returns.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
import hashlib
from itertools import groupby
import json
from pathlib import Path
import random
import re
import sqlite3
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
LOOKBACK = 6 * 3600
GROUPS = 4
STOP = frozenset("the and for with this that token coin meme pump fun official sol solana crypto".split())
IDL_SHA = "b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49"
NATIVE = "1" * 32


class Refused(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def words(name, symbol):
    if not isinstance(name, str) or not isinstance(symbol, str):
        raise Refused("text absent or not a string")
    text = unicodedata.normalize("NFKC", name + " " + symbol).casefold()
    return frozenset(w for w in re.findall(r"[^\W\d_]+", text) if len(w) >= 3 and w not in STOP)


@dataclass(frozen=True)
class Birth:
    coord: tuple[int, int, int, int]
    timestamp: int
    mint: str
    creator: str | None
    user: str | None
    terms: frozenset[str]
    source_sha256: str
    in_scope: bool = True

    @property
    def actors(self):
        return frozenset((self.creator, self.user)) if self.creator and self.user else frozenset()


class Identities:
    """Incremental exact creator/user equality; never estimates economic ownership."""
    def __init__(self):
        self.parent = {}

    def root(self, actor):
        self.parent.setdefault(actor, actor)
        while self.parent[actor] != actor:
            self.parent[actor] = self.parent[self.parent[actor]]
            actor = self.parent[actor]
        return actor

    def add(self, births):
        for b in births:
            if b.actors:
                self.parent[self.root(b.user)] = self.root(b.creator)


def components(births):
    """Exact role equality only. No common-funder or ownership inference."""
    identities = Identities()
    identities.add(births)
    return {a: identities.root(a) for a in identities.parent}


def observe(births, *, history_start):
    """Replay in canonical order. Transaction siblings become visible together."""
    history = defaultdict(deque)
    emitted = set()
    seen = set()
    counters = Counter()
    output = []
    previous_coord = None
    previous_time = history_start
    identities = Identities()
    # Materialize each whole transaction before examining any of its events.
    for _, iterator in groupby(births, key=lambda b: b.coord[:2]):
        batch = list(iterator)
        timestamps = {b.timestamp for b in batch}
        if len(timestamps) != 1:
            raise Refused("conflicting transaction timestamps")
        now = batch[0].timestamp
        if now < previous_time:
            raise Refused("backward block timestamp")
        previous_time = now
        for b in batch:
            if (len(b.coord) != 4 or any(type(x) is not int for x in b.coord)
                    or (previous_coord is not None and b.coord <= previous_coord)):
                raise Refused("duplicate or unordered canonical coordinate")
            if b.mint in seen:
                raise Refused("duplicate mint")
            if not b.mint or type(b.timestamp) is not int or b.timestamp < history_start:
                raise Refused("invalid mint or clock")
            if not re.fullmatch(r"[0-9a-f]{64}", b.source_sha256):
                raise Refused("invalid source evidence hash")
            previous_coord = b.coord
            seen.add(b.mint)
            counters["births"] += 1
        scoped = [b for b in batch if b.in_scope]
        counters["scope_excluded"] += len(batch) - len(scoped)
        current = [b for b in scoped if b.actors]
        counters["missing_actor"] += len(scoped) - len(current)
        if now - history_start < LOOKBACK:
            counters["warmup_births"] += len(current)
        terms = sorted(set().union(*(b.terms for b in current)))
        proposals = []
        pending = []
        for term in terms:
            h = history[term]
            while h and h[0].timestamp < now - LOOKBACK:
                h.popleft()
            # t is excluded even when another transaction has the same second.
            prior = [b for b in h if b.timestamp < now]
            arriving = [b for b in current if term in b.terms]
            n_before = len({identities.root(b.creator) for b in prior})
            if n_before < GROUPS:
                pending.append((term, prior, arriving, n_before))
        # A bridge on ANY earlier word, including one outside the rolling window,
        # is known identity context. Later bridges never revise earlier outputs.
        # Other quote regimes can supply exact-identity context but no word counts.
        identities.add(batch)
        for term, prior, arriving, n_before in pending:
            n_after = len({identities.root(b.creator) for b in prior + arriving})
            if now - history_start >= LOOKBACK and n_before < GROUPS <= n_after:
                counters["word_crossings"] += 1
                if not prior:
                    counters["no_prior_origin"] += 1
                    continue
                origin = prior[0]
                root = identities.root(origin.creator)
                if any(identities.root(b.creator) == root for b in arriving):
                    counters["origin_linked_to_arrival"] += 1
                    continue
                evidence = prior + arriving
                proposals.append((origin.coord, term, origin, evidence, n_before, n_after))
        for _, term, origin, evidence, n_before, n_after in sorted(proposals):
            if origin.mint in emitted:
                counters["duplicate_origin_suppressed"] += 1
                continue
            emitted.add(origin.mint)
            output.append({
                "schema": "birth-origin-v1", "status": "NO_TRADE",
                "provenance": "historical_oracle", "observed_at_unix_nanos": None,
                "decision_boundary": "after_whole_transaction",
                "trigger_coordinate": list(batch[-1].coord), "chain_time": now,
                "candidate_mint": origin.mint, "first_in_window_coordinate": list(origin.coord),
                "word": term, "groups_before": n_before, "groups_after": n_after,
                "birth_evidence_sha256": [b.source_sha256 for b in evidence],
                "funding_independence": "UNVERIFIED",
            })
        for b in current:
            for term in b.terms:
                history[term].append(b)
    counters["observations"] = len(output)
    return output, dict(sorted(counters.items()))


def read_births(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("BEGIN")
    meta = dict(connection.execute("SELECT key,value FROM metadata"))
    if meta.get("idl_sha256") != IDL_SHA:
        raise Refused("creation corpus IDL is not the inspected pinned version")
    if connection.execute("SELECT count(*) FROM decode_error").fetchone()[0]:
        raise Refused("creation corpus has unresolved decode errors")
    coverage = connection.execute("SELECT count(*), min(slot),max(slot),"
                                  "sum(status NOT IN ('retrieved','skipped')) FROM slot_scan").fetchone()
    start, end = int(meta["start_slot"]), int(meta["end_slot_exclusive"])
    if tuple(coverage) != (end - start, start, end - 1, 0):
        raise Refused("creation enumeration does not cover its declared slot range")
    history_start = connection.execute("SELECT min(block_time) FROM slot_scan WHERE block_time IS NOT NULL").fetchone()[0]
    evidence = hashlib.sha256()
    births = []
    query = "SELECT * FROM create_event ORDER BY slot,transaction_index,outer_instruction_index,inner_instruction_index"
    for raw in connection.execute(query):
        row = dict(raw)
        encoded = canonical(row)
        evidence.update(encoded + b"\n")
        fields = json.loads(row["fields_json"])
        if row["block_time"] is None or not start <= row["slot"] < end:
            raise Refused("creation clock or declared slot boundary missing")
        if row["is_mayhem_mode"] not in (0, 1) or not row["quote_mint"]:
            raise Refused("unknown launch regime")
        births.append(Birth(
            (row["slot"], row["transaction_index"], row["outer_instruction_index"], row["inner_instruction_index"]),
            row["block_time"], row["mint"], row["creator"], row["user"],
            words(fields.get("name"), fields.get("symbol")), hashlib.sha256(encoded).hexdigest(),
            row["is_mayhem_mode"] == 0 and row["quote_mint"] == NATIVE))
    connection.close()
    return births, {"source": str(path.relative_to(ROOT)), "create_rows_sha256": evidence.hexdigest(),
                    "idl_sha256": IDL_SHA, "start_slot": start, "end_slot_exclusive": end,
                    "history_start": history_start, "create_count": len(births)}


def placebo(births, seed):
    """Within-exact-identity text permutation; structural diagnostic, not a PnL null.

    Full-window grouping here is deliberate for null generation ONLY. The observer
    recomputes its groups causally, including on the permuted input.
    """
    groups = components(births)
    indexes = defaultdict(list)
    for i, b in enumerate(births):
        if b.actors:
            indexes[groups[b.creator]].append(i)
    result = list(births)
    rng = random.Random(seed)
    changed = 0
    for indexes_in_group in indexes.values():
        names = [births[i].terms for i in indexes_in_group]
        rng.shuffle(names)
        for i, terms in zip(indexes_in_group, names):
            changed += terms != births[i].terms
            result[i] = replace(births[i], terms=terms,
                                source_sha256=digest(["PLACEBO", seed, births[i].source_sha256, sorted(terms)]))
    return result, changed


def write_new(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="new output directory; never overwrite")
    args = ap.parse_args()
    if args.out.exists():
        raise Refused("output path already exists")
    births, source = read_births(ROOT / "research/b11a/b11a_creates.sqlite")
    output, counts = observe(births, history_start=source["history_start"])
    nulls = []
    for seed in range(20260908, 20260928):
        shuffled, changed = placebo(births, seed)
        _, metrics = observe(shuffled, history_start=source["history_start"])
        nulls.append({"seed": seed, "changed_text_rows": changed, **metrics})
        print(json.dumps({"placebo_seed_complete": seed}), flush=True)
    span = max(b.timestamp for b in births) - min(b.timestamp for b in births)
    report = {"status": "NO_TRADE_DEVELOPMENT_ONLY", "source": source, "counts": counts,
              "launch_span_seconds": span, "performance_evaluated": False,
              "observations_sha256": digest(output), "placebos": nulls,
              "placebo_scope": "within-actor text timing only; NOT a profitability test",
              "profitability_survivors_real": None, "profitability_survivors_noise": None,
              "required_pair_check": "UNAVAILABLE_IDENTIFIERS_AND_ENTRY_TIMES",
              "three_disjoint_days_available": span >= 3 * 86400,
              "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "spec_sha256": hashlib.sha256((ROOT / "research/midcap/BIRTH_ORIGIN_V1_SPEC.md").read_bytes()).hexdigest()}
    args.out.mkdir(parents=True)
    write_new(args.out / "observations.json", output)
    write_new(args.out / "result.json", report)
    print(json.dumps({"output": str(args.out), "status": report["status"], "counts": counts,
                      "null_observation_counts": [r["observations"] for r in nulls],
                      "performance_evaluated": False}, sort_keys=True))


if __name__ == "__main__":
    main()
