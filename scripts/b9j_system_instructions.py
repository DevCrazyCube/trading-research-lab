#!/usr/bin/env python3
"""B9j — fail-closed decoder for the pinned System program instruction ABI.

Offline, read-only, no network. The pin, its provenance and its corroboration against the frozen
artifact are recorded in `research/B9J_SYSTEM_ABI_PIN.md`.

This exists because wallet-cost reconciliation cannot be done from balance vectors. Attributing the
fee payer's delta to `meta.fee`, protocol quote flows and zero-based account lifecycle reconciles
272 of 1,200 transactions. The unattributed movements are System-program instructions, and a
movement's purpose is stated by the instruction that made it, never by the delta it leaves behind.

Everything here refuses rather than guesses:

- an unknown variant tag raises, including the eight pinned-but-unobserved ones. Absence from the
  artifact is not impossibility, and a decoder that silently skipped a variant would under-count
  exactly the lamports it was written to find.
- trailing bytes raise. A payload that decodes and leaves data over is not the payload this ABI
  describes, and treating the remainder as padding is how a layout change becomes a silent
  mis-attribution.
- truncated data raises, including a seed length that overruns the buffer.

No amount, purpose or account role is inferred from a value's shape. A transfer of 1,000,000
lamports is a transfer of 1,000,000 lamports, not a tip.
"""
import argparse
import importlib.util
import json
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Pinned: research/B9J_SYSTEM_ABI_PIN.md. Vendored source is
# research/solana_system_interface_3.2.0_instruction.rs, sha256
# 1126faa2ab8c7a1ecc73dca70de34713ad25bd0e090e2bb8595fb3d767801876, from crate
# solana-system-interface 3.2.0, sha256
# 55b54965bf0b76fa8e2b35376583efddd4d916618cfe595bf48c7d7b55a9e628.
SYSTEM_PROGRAM = "11111111111111111111111111111111"
SYSTEM_ABI_SOURCE = "research/solana_system_interface_3.2.0_instruction.rs"
SYSTEM_ABI_SOURCE_SHA256 = "1126faa2ab8c7a1ecc73dca70de34713ad25bd0e090e2bb8595fb3d767801876"
SYSTEM_CRATE_SHA256 = "55b54965bf0b76fa8e2b35376583efddd4d916618cfe595bf48c7d7b55a9e628"

# Declaration order IS the wire tag. Payload fields in order; `pubkey` is 32 bytes, `u64` is 8
# little-endian bytes, `string` is an 8-byte little-endian length followed by that many bytes.
SYSTEM_INSTRUCTIONS = {
    0: ("CreateAccount", ("lamports:u64", "space:u64", "owner:pubkey")),
    1: ("Assign", ("owner:pubkey",)),
    2: ("Transfer", ("lamports:u64",)),
    3: ("CreateAccountWithSeed",
        ("base:pubkey", "seed:string", "lamports:u64", "space:u64", "owner:pubkey")),
    4: ("AdvanceNonceAccount", ()),
    5: ("WithdrawNonceAccount", ("lamports:u64",)),
    6: ("InitializeNonceAccount", ("authority:pubkey",)),
    7: ("AuthorizeNonceAccount", ("authority:pubkey",)),
    8: ("Allocate", ("space:u64",)),
    9: ("AllocateWithSeed", ("base:pubkey", "seed:string", "space:u64", "owner:pubkey")),
    10: ("AssignWithSeed", ("base:pubkey", "seed:string", "owner:pubkey")),
    11: ("TransferWithSeed", ("lamports:u64", "from_seed:string", "from_owner:pubkey")),
    12: ("UpgradeNonceAccount", ()),
    13: ("CreateAccountAllowPrefund", ("lamports:u64", "space:u64", "owner:pubkey")),
}

# Variants that move lamports, and the field naming the amount. Used by cost reconciliation so it
# never has to pattern-match on a variant name at the call site.
LAMPORT_MOVING = {"CreateAccount": "lamports", "CreateAccountWithSeed": "lamports",
                  "CreateAccountAllowPrefund": "lamports", "Transfer": "lamports",
                  "TransferWithSeed": "lamports", "WithdrawNonceAccount": "lamports"}


def _load_b9d():
    spec = importlib.util.spec_from_file_location(
        "b9d_transaction_bodies", ROOT / "scripts" / "b9d_transaction_bodies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load_b9d()
FreezeViolation = B9D.FreezeViolation


def assert_abi_source_pinned():
    """The vendored ABI must still hash to what was pinned, or the layout below is not evidence."""
    actual = B9D.sha256_file(ROOT / SYSTEM_ABI_SOURCE)
    if actual != SYSTEM_ABI_SOURCE_SHA256:
        raise FreezeViolation(
            f"{SYSTEM_ABI_SOURCE} hashes {actual}, pinned {SYSTEM_ABI_SOURCE_SHA256}; the System "
            "instruction layout in this module is stated against the pinned revision and must not "
            "be applied to another")
    return True


def decode_system_instruction(data):
    """Decode one System instruction, or raise. Never returns a partial or best-effort result."""
    if len(data) < 4:
        raise FreezeViolation(
            f"System instruction data is {len(data)} bytes; the variant tag alone is 4")
    tag = struct.unpack_from("<I", data, 0)[0]
    if tag not in SYSTEM_INSTRUCTIONS:
        raise FreezeViolation(
            f"System instruction tag {tag} is outside the pinned ABI (0..13); refusing to guess "
            "its layout")
    name, fields = SYSTEM_INSTRUCTIONS[tag]

    offset = 4
    decoded = {}
    for field in fields:
        label, kind = field.split(":")
        if kind == "u64":
            if offset + 8 > len(data):
                raise FreezeViolation(f"{name}.{label} is truncated")
            decoded[label] = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
        elif kind == "pubkey":
            if offset + 32 > len(data):
                raise FreezeViolation(f"{name}.{label} is truncated")
            decoded[label] = B9D.base58(data[offset:offset + 32])
            offset += 32
        elif kind == "string":
            if offset + 8 > len(data):
                raise FreezeViolation(f"{name}.{label} length prefix is truncated")
            length = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
            if offset + length > len(data):
                raise FreezeViolation(
                    f"{name}.{label} declares {length} bytes with {len(data) - offset} remaining")
            decoded[label] = data[offset:offset + length].decode("utf-8", errors="strict")
            offset += length
        else:                                              # pragma: no cover - table is closed
            raise FreezeViolation(f"unhandled pinned field kind {kind!r}")

    if offset != len(data):
        raise FreezeViolation(
            f"{name} decoded {offset} of {len(data)} bytes; {len(data) - offset} trailing byte(s) "
            "are not part of this pinned layout and must not be treated as padding")
    return {"tag": tag, "name": name, "fields": decoded}


def system_lamports_moved(decoded):
    """The lamports this instruction moves, or None when the variant moves none.

    None and 0 are different answers and are kept different: a variant that cannot move lamports is
    not the same as one that moved zero.
    """
    field = LAMPORT_MOVING.get(decoded["name"])
    return None if field is None else decoded["fields"][field]


def survey(database, limit=None, progress=None, strict=True):
    """Decode every System instruction in the artifact.

    `strict` raises on the first instruction that will not decode, which is what a gate wants.
    With `strict=False` the refusal is ENUMERATED instead: the instruction is recorded with its
    signature, coordinates and reason, and counted separately. That is not a tolerance -- nothing
    is decoded leniently and no trailing byte is accepted. It exists so the population can be
    measured, and so a reconciliation can mark the containing transaction unreconcilable by name
    rather than crashing on it or, worse, silently skipping it.

    Measured over the full artifact: 412,028 System instructions, 2 undecodable.
    """
    assert_abi_source_pinned()
    query = "SELECT signature FROM transaction_coordinate ORDER BY signature"
    if limit:
        query += f" LIMIT {int(limit)}"
    report = {"transactions": 0, "system_instructions": 0, "by_variant": {},
              "lamports_by_variant": {}, "undecodable": []}
    for (signature,) in database.execute(query):
        raw = database.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()[0]
        result = B9D.raw_result(raw)
        report["transactions"] += 1
        for envelope in B9D.envelope_instructions(result):
            if envelope["program_id"] != SYSTEM_PROGRAM:
                continue
            try:
                decoded = decode_system_instruction(envelope["data"])
            except FreezeViolation as error:
                if strict:
                    raise FreezeViolation(f"{signature}: {error}") from error
                report["undecodable"].append({
                    "signature": signature, "outer_index": envelope["outer_index"],
                    "inner_index": envelope["inner_index"],
                    "data_length": len(envelope["data"]), "reason": str(error)})
                report["system_instructions"] += 1
                continue
            report["system_instructions"] += 1
            report["by_variant"][decoded["name"]] = report["by_variant"].get(decoded["name"], 0) + 1
            moved = system_lamports_moved(decoded)
            if moved is not None:
                report["lamports_by_variant"][decoded["name"]] = (
                    report["lamports_by_variant"].get(decoded["name"], 0) + moved)
        if progress and report["transactions"] % progress == 0:
            print(f"  {report['transactions']:,} transactions", file=sys.stderr, flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--enumerate-undecodable", action="store_true",
                        help="record instructions that will not decode instead of raising; the "
                             "decoder stays strict, only the survey continues")
    args = parser.parse_args(argv)
    database = B9D.connect(args.artifact, readonly=True)
    try:
        report = survey(database, args.limit, args.progress,
                        strict=not args.enumerate_undecodable)
    finally:
        database.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
