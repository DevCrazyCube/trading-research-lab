"""Makes the network guard active under **every** runner and invocation, and proves it blocks.

Seq 111 installed the guard two ways: `conftest.py` (pytest only) and `tests/__init__.py` (package
import). Neither covers the command this project actually uses. Measured, not assumed:

| invocation | `tests/__init__.py` imported | guard active before this file |
|---|---|---|
| `python -m unittest discover -s tests` | **no** | **no** — the suite ran unguarded |
| `python -m unittest discover -s tests -t .` | yes | yes |
| `python -m unittest discover` (from root) | yes | yes |
| `pytest tests` | no | yes, via `conftest.py` |

With `-s tests`, unittest sets `top_level_dir = start_dir`, so `tests/` is treated as the root
rather than as a package and its `__init__.py` is never imported. A probe connect to 192.0.2.1
under that invocation raised `TimeoutError` — a **real outbound attempt that timed out** — where
pytest raised `OutboundConnectionBlocked`.

Making hermeticity depend on remembering the right flag is the same class of error as the original
defect: a gate asserted rather than enforced. So the install happens at **module import** below.
unittest and pytest both import every matching test module during collection, before any test
executes, so importing this file is sufficient to guard the whole run however it was started.

The import-time side effect is deliberate and is the only universal hook unittest offers.
`_netguard.install()` is not modified — its install/restore round-trip is pinned by
`test_netguard.py`, and making it globally idempotent would break that contract.
"""
import pathlib
import socket
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _netguard  # noqa: E402

# Install at import, not in setUp: by the time any test runs, collection is already complete.
if getattr(socket.socket.connect, "__module__", None) != _netguard.__name__:
    _netguard.install()


class GuardIsActiveTests(unittest.TestCase):
    """`test_installed` alone would be vacuous — this module installs the guard, so of course it is
    installed. The blocking test is what carries the evidence."""

    # RFC 5737 TEST-NET-1: reserved for documentation and guaranteed unroutable, so even a total
    # guard failure reaches nothing real. A timeout here instead of the exception would mean a
    # genuine outbound attempt was made.
    UNROUTABLE = ("192.0.2.1", 443)

    def test_guard_is_installed_however_the_suite_was_invoked(self):
        self.assertEqual(getattr(socket.socket.connect, "__module__", None), _netguard.__name__,
                         "network guard is not installed - the suite is not hermetic")

    def test_outbound_connection_is_blocked_by_the_guard_not_by_a_timeout(self):
        s = socket.socket()
        s.settimeout(2)
        self.addCleanup(s.close)
        with self.assertRaises(_netguard.OutboundConnectionBlocked):
            s.connect(self.UNROUTABLE)

    def test_connect_ex_and_create_connection_are_covered_too(self):
        s = socket.socket()
        s.settimeout(2)
        self.addCleanup(s.close)
        with self.assertRaises(_netguard.OutboundConnectionBlocked):
            s.connect_ex(self.UNROUTABLE)
        with self.assertRaises(_netguard.OutboundConnectionBlocked):
            socket.create_connection(self.UNROUTABLE, timeout=2)

    def test_loopback_remains_permitted(self):
        """Loopback must stay open: `test_recorder.py` serves canned RPC over 127.0.0.1 precisely
        so the credential test can stay end-to-end instead of stubbing the transport."""
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        self.addCleanup(server.close)
        client = socket.socket()
        client.settimeout(2)
        self.addCleanup(client.close)
        client.connect(server.getsockname())      # must not raise


if __name__ == "__main__":
    unittest.main()
