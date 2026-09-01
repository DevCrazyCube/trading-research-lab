#!/usr/bin/env python3
"""Immutable activation authority for MEME ARENA paper instruments.

An arm may collect only after its executable closure and preregistration have been committed, and
after a separate activation record has itself been committed unchanged.  Tape arms also pin the exact
byte/chain cursor at activation, preventing retrospective consumption after a restart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import time

from .. import ws_data

ROOT = pathlib.Path(__file__).resolve().parents[4]
ACTIVATION_DIR = ROOT / "research" / "trading_bot" / "memebot" / "arena" / "activations"
SCHEMA = 1


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def activation_path(arm) -> pathlib.Path:
    return ACTIVATION_DIR / f"{arm.instrument}.json"


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError(f"activation git check refuses: {' '.join(args)}")
    return proc.stdout.strip()


def _atomic_create(path: pathlib.Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"activation is set-once: {path}")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".activation_", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_activation(arm) -> dict:
    """Write once, after code/prereg commit and before evidence. Caller commits the record separately."""
    if getattr(arm, "requires_trade_data", False) and not ws_data.trade_data_authorized():
        raise RuntimeError(f"{arm.instrument} requires PUMPPORTAL_DATA_API_KEY; paid trade data is not "
                           "authorized in this process")
    head = _git("rev-parse", "HEAD")
    sequence, tape_head = ws_data._trade_head()
    record = {
        "schema": SCHEMA,
        "instrument": arm.instrument,
        "service_kind": arm.service_kind,
        "activated_unix_nanos": time.time_ns(),
        "code_sha256": arm.code_sha256(),
        "prereg_sha256": arm.prereg_sha256(),
        "spec_sha256": arm.spec_sha256(),
        "code_commit": head,
        "tape_sequence": sequence,
        "tape_head_sha256": tape_head,
        "tape_offset": (ws_data.TRADE_BUFFER_PATH.stat().st_size
                        if ws_data.TRADE_BUFFER_PATH.exists() else 0),
        "boundary": "PAPER_ONLY_NO_WALLET_NO_ORDERS",
    }
    body = _canonical(record)
    sealed = {**record, "activation_sha256": hashlib.sha256(body).hexdigest()}
    _atomic_create(activation_path(arm), _canonical(sealed) + b"\n")
    return sealed


def require_activation(arm, *, require_git_anchor: bool = True) -> dict:
    path = activation_path(arm)
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{arm.instrument}: missing/malformed activation authority") from exc
    observed = value.pop("activation_sha256", None)
    if (set(value) != {"schema", "instrument", "service_kind", "activated_unix_nanos",
                       "code_sha256", "prereg_sha256", "spec_sha256", "code_commit",
                       "tape_sequence", "tape_head_sha256", "tape_offset", "boundary"}
            or value["schema"] != SCHEMA or value["instrument"] != arm.instrument
            or value["service_kind"] != arm.service_kind
            or type(value["activated_unix_nanos"]) is not int
            or value["activated_unix_nanos"] <= 0
            or type(value["tape_sequence"]) is not int or value["tape_sequence"] < 0
            or type(value["tape_offset"]) is not int or value["tape_offset"] < 0
            or value["boundary"] != "PAPER_ONLY_NO_WALLET_NO_ORDERS"
            or observed != hashlib.sha256(_canonical(value)).hexdigest()):
        raise RuntimeError(f"{arm.instrument}: activation authority refuses")
    if (value["code_sha256"] != arm.code_sha256()
            or value["prereg_sha256"] != arm.prereg_sha256()
            or value["spec_sha256"] != arm.spec_sha256()):
        raise RuntimeError(f"{arm.instrument}: activated closure drifted")
    if require_git_anchor:
        relative = path.relative_to(ROOT).as_posix()
        _git("ls-files", "--error-unmatch", relative)
        if _git("status", "--porcelain", "--", relative):
            raise RuntimeError(f"{arm.instrument}: activation is not clean at HEAD")
        if subprocess.run(["git", "merge-base", "--is-ancestor", value["code_commit"], "HEAD"],
                          cwd=ROOT, capture_output=True).returncode:
            raise RuntimeError(f"{arm.instrument}: code commit is not an ancestor of HEAD")
    return {**value, "activation_sha256": observed}


def _arm_by_name(name: str):
    from .runtime import _registered_arms
    matches = [arm for arm in _registered_arms() if arm.instrument == name]
    if len(matches) != 1:
        raise RuntimeError(f"unknown Arena instrument: {name}")
    return matches[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("write", "verify"))
    parser.add_argument("instrument")
    args = parser.parse_args(argv)
    arm = _arm_by_name(args.instrument)
    result = write_activation(arm) if args.command == "write" else require_activation(arm)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
