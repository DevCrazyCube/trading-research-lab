#!/usr/bin/env python3
"""B9l — fail-closed decoder for the pinned SPL Token instruction ABI.

Offline, read-only, no network. Provenance in `research/B9L_SPL_TOKEN_ABI_PIN.md`.

This exists for one movement the System ABI cannot see. Wallet-cost reconciliation attributes
50.29% of transactions exactly; the unattributed half is dominated by residuals of exactly
-2,039,280 lamports, which is SPL token-account rent flowing BACK to the payer. `CloseAccount` is
performed by the Token program on an account it owns, so no System instruction records it.

`CloseAccount` is the only variant in the pinned ABI that moves lamports, and it sends the closed
account's entire balance to `accounts[1]`. That single fact is what closes the gap.

Token-2022 shares this base ABI for variants 0..24 and adds extension instructions above it. Those
extensions are NOT covered by this pin, so they are refused by name rather than assumed inert: an
extension that moved lamports would otherwise be silently missed, which is the failure this whole
line of work exists to prevent.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_PROGRAMS = (TOKEN_PROGRAM, TOKEN_2022_PROGRAM)

TOKEN_ABI_SOURCE = "research/spl_token_interface_2.0.0_instruction.rs"
TOKEN_ABI_SOURCE_SHA256 = "7f6f247b549e11d07c83059bad918bb2d0a78824867f961a10b239a9880a1a15"
TOKEN_2022_ABI_SOURCE = "research/spl_token_2022_11.0.0_pod_instruction.rs"
TOKEN_2022_CRATE_SHA256 = "2f0e045d23300c8c9f57e52fa7a1103a20a707cc02080db929c2ff09044aa06a"
TOKEN_CRATE_SHA256 = "8c564ac05a7c8d8b12e988a37d82695b5ba4db376d07ea98bc4882c81f96c7f3"

# Declaration order is the wire discriminator, a single u8 -- unlike the System program's u32.
# Confirmed against the vendored source's own unpack table, which maps `9 => CloseAccount`.
TOKEN_INSTRUCTIONS = {
    0: "InitializeMint", 1: "InitializeAccount", 2: "InitializeMultisig", 3: "Transfer",
    4: "Approve", 5: "Revoke", 6: "SetAuthority", 7: "MintTo", 8: "Burn", 9: "CloseAccount",
    10: "FreezeAccount", 11: "ThawAccount", 12: "TransferChecked", 13: "ApproveChecked",
    14: "MintToChecked", 15: "BurnChecked", 16: "InitializeAccount2", 17: "SyncNative",
    18: "InitializeAccount3", 19: "InitializeMultisig2", 20: "InitializeMint2",
    21: "GetAccountDataSize", 22: "InitializeImmutableOwner", 23: "AmountToUiAmount",
    24: "UiAmountToAmount",
}

# Token-2022 extension instructions, tags 25..44, from the pinned spl-token-2022 11.0.0
# `PodTokenInstruction` enum. Token-2022 shares tags 0..24 with SPL Token and adds these above.
TOKEN_2022_EXTENSIONS = {
    25: "InitializeMintCloseAuthority", 26: "TransferFeeExtension",
    27: "ConfidentialTransferExtension", 28: "DefaultAccountStateExtension", 29: "Reallocate",
    30: "MemoTransferExtension", 31: "CreateNativeMint", 32: "InitializeNonTransferableMint",
    33: "InterestBearingMintExtension", 34: "CpiGuardExtension", 35: "InitializePermanentDelegate",
    36: "TransferHookExtension", 37: "ConfidentialTransferFeeExtension",
    38: "WithdrawExcessLamports", 39: "MetadataPointerExtension", 40: "GroupPointerExtension",
    41: "GroupMemberPointerExtension", 42: "ConfidentialMintBurnExtension",
    43: "ScaledUiAmountExtension", 44: "PausableExtension",
}

# Instructions routed through Token-2022 by an 8-byte interface discriminator rather than a
# one-byte enum tag. Their leading byte falls outside 0..44, which is how they are told apart.
# `update_the_authority` was confirmed by computing sha256("spl_token_metadata_interface:
# update_the_authority")[:8] locally -- it reproduces d7e4a6e45464567b exactly. The initialize
# discriminator is identified from its own payload, which carries a u32-prefixed name, symbol and
# URI in that order, observed as "sol has nuggies" / "nuggies" / an https URI.
TOKEN_METADATA_INTERFACE = {
    "d2e11ea258b84d8d": "TokenMetadataInitialize",
    "d7e4a6e45464567b": "TokenMetadataUpdateAuthority",
}

# WithdrawExcessLamports is the ONLY extension that moves lamports, established from the pinned
# source: `processor.rs` mutates source and destination lamports for it, while the token_metadata
# and metadata_pointer processors contain no reference to lamports at all. It does NOT appear in
# the frozen artifact -- so it is pinned, refused loudly if it ever shows up, and never silently
# treated as inert.
TOKEN_2022_LAMPORT_MOVING = frozenset({38})

# The only pinned variant that moves lamports, and where it sends them. `CloseAccount` transfers
# the closed account's ENTIRE balance, so the amount is not in the instruction data -- it is the
# closed account's pre-balance, which the caller supplies from the balance vector.
CLOSE_ACCOUNT = 9
CLOSE_ACCOUNT_SOURCE = 0        # accounts[0] is the account being closed
CLOSE_ACCOUNT_DESTINATION = 1   # accounts[1] receives its lamports


def _load_b9d():
    spec = importlib.util.spec_from_file_location(
        "b9d_transaction_bodies", ROOT / "scripts" / "b9d_transaction_bodies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load_b9d()
FreezeViolation = B9D.FreezeViolation


def assert_abi_source_pinned():
    """The vendored ABI must still hash to its pin, or the table below is not evidence."""
    actual = B9D.sha256_file(ROOT / TOKEN_ABI_SOURCE)
    if actual != TOKEN_ABI_SOURCE_SHA256:
        raise FreezeViolation(
            f"{TOKEN_ABI_SOURCE} hashes {actual}, pinned {TOKEN_ABI_SOURCE_SHA256}; the Token "
            "instruction table is stated against the pinned revision")
    return True


def decode_token_instruction(data):
    """Identify one Token instruction, or raise.

    Only the discriminator is decoded. The payloads are not, deliberately: nothing in this work
    needs them, and decoding fields nobody reads is surface area that can drift silently. What is
    needed is which variant it is, so a lamport-moving one can never be mistaken for an inert one.
    """
    if not data:
        raise FreezeViolation("Token instruction has no discriminator byte")
    tag = data[0]
    if tag in TOKEN_INSTRUCTIONS:
        return {"tag": tag, "name": TOKEN_INSTRUCTIONS[tag],
                "moves_lamports": tag == CLOSE_ACCOUNT}
    if tag in TOKEN_2022_EXTENSIONS:
        if tag in TOKEN_2022_LAMPORT_MOVING:
            raise FreezeViolation(
                f"{TOKEN_2022_EXTENSIONS[tag]} moves lamports and has never been observed in this "
                "artifact; its amount is the account balance above rent exemption, which is not in "
                "the instruction data. Refusing to attribute it without establishing that first")
        return {"tag": tag, "name": TOKEN_2022_EXTENSIONS[tag], "moves_lamports": False}
    discriminator = data[:8].hex()
    if discriminator in TOKEN_METADATA_INTERFACE:
        # Routed by 8-byte interface discriminator. The token_metadata processor in the pinned
        # source contains no lamport handling, so these are established as non-moving rather than
        # assumed so.
        return {"tag": tag, "name": TOKEN_METADATA_INTERFACE[discriminator],
                "moves_lamports": False, "discriminator": discriminator}
    raise FreezeViolation(
        f"Token instruction discriminator {tag} (first eight bytes {discriminator}) matches no "
        "pinned SPL Token tag, Token-2022 extension tag, or metadata-interface discriminator; "
        "refusing to assume it moves no lamports")


def close_account_movement(envelope, keys, pre_balances):
    """The lamports a CloseAccount moves, and where, from the balance vector.

    `CloseAccount` sends the closed account's entire balance, so the amount is its PRE-balance.
    Returns `(source, destination, lamports)`, or raises if the accounts cannot be resolved
    unambiguously -- an ambiguous attribution is worse than none.
    """
    accounts = envelope["accounts"]
    if len(accounts) <= CLOSE_ACCOUNT_DESTINATION:
        raise FreezeViolation(
            f"CloseAccount carries {len(accounts)} account(s); the pinned ABI gives it a closed "
            "account and a destination")
    source, destination = accounts[CLOSE_ACCOUNT_SOURCE], accounts[CLOSE_ACCOUNT_DESTINATION]
    indexes = [index for index, key in enumerate(keys) if key == source]
    if len(indexes) != 1:
        raise FreezeViolation(
            f"closed account {source} resolves to {len(indexes)} keys; its balance is ambiguous")
    return source, destination, pre_balances[indexes[0]]


def survey(database, limit=None, progress=None, strict=True):
    """Decode every Token instruction in the artifact, or enumerate what will not decode."""
    assert_abi_source_pinned()
    query = "SELECT signature FROM transaction_coordinate ORDER BY signature"
    if limit:
        query += f" LIMIT {int(limit)}"
    report = {"transactions": 0, "token_instructions": 0, "by_program": {}, "by_variant": {},
              "undecodable": [], "undecodable_count": 0}
    for (signature,) in database.execute(query):
        raw = database.execute(
            "SELECT raw_zlib FROM raw_transaction WHERE signature=?", (signature,)).fetchone()[0]
        result = B9D.raw_result(raw)
        report["transactions"] += 1
        for envelope in B9D.envelope_instructions(result):
            program = envelope["program_id"]
            if program not in TOKEN_PROGRAMS:
                continue
            report["token_instructions"] += 1
            label = "token" if program == TOKEN_PROGRAM else "token_2022"
            report["by_program"][label] = report["by_program"].get(label, 0) + 1
            try:
                decoded = decode_token_instruction(envelope["data"])
            except FreezeViolation as error:
                if strict:
                    raise FreezeViolation(f"{signature}: {error}") from error
                report["undecodable_count"] += 1
                if len(report["undecodable"]) < 20:
                    report["undecodable"].append({
                        "signature": signature, "program": label,
                        "discriminator": envelope["data"][0] if envelope["data"] else None,
                        "data_length": len(envelope["data"])})
                continue
            key = f"{label}:{decoded['name']}"
            report["by_variant"][key] = report["by_variant"].get(key, 0) + 1
        if progress and report["transactions"] % progress == 0:
            print(f"  {report['transactions']:,} transactions", file=sys.stderr, flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress", type=int, default=None)
    parser.add_argument("--enumerate-undecodable", action="store_true")
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
