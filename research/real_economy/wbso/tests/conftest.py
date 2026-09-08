"""Make the package importable and keep the suite hermetic.

The tests here touch no network: the arithmetic is pure, the ethics linter is pure, and the scanner
tests run against recorded fixture payloads. That is enforced rather than assumed — `_no_network`
replaces `socket.socket` for the session, mirroring `tests/_netguard.py` at the repository root.
"""
from __future__ import annotations

import pathlib
import socket
import sys

import pytest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


@pytest.fixture(autouse=True, scope="session")
def _no_network():
    real = socket.socket

    class Blocked(socket.socket):
        def connect(self, address):  # type: ignore[override]
            host = address[0] if isinstance(address, tuple) else address
            if host not in ("127.0.0.1", "::1", "localhost"):
                raise AssertionError(f"test tried to reach the network: {address!r}")
            return super().connect(address)

    socket.socket = Blocked  # type: ignore[misc]
    yield
    socket.socket = real  # type: ignore[misc]
