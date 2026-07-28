"""The network guard must be installed and must have power.

A guard that cannot fail is worse than no guard, because it converts an unchecked assumption into
a false assurance. Today produced two vacuous checks already - an identity-prompt ordering test
that passed against the mutant it was written to catch (Seq 100), and a hermeticity harness whose
own breakage would have reported a passing suite (Seq 109). So the guard is tested for teeth, not
merely for presence.

These tests open no sockets at all: the blocking decision is a pure function, and the patched entry
points raise before dialling. Where an address is needed it is 192.0.2.1 - RFC 5737 TEST-NET-1,
guaranteed unroutable - so that if the guard ever regressed, this file still could not reach
anything real.
"""
import pathlib
import socket
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _netguard                                       # noqa: E402

UNROUTABLE = ("192.0.2.1", 443)                        # RFC 5737 TEST-NET-1

_self_installed = None


def setUpModule():
    """Install the guard if the runner did not.

    `conftest.py` is a pytest hook, so `python -m unittest` loads none of it and the whole suite
    would run unguarded - the exact hole this work exists to close. Installing here covers that
    runner too. It does **not** weaken the canary below: whether conftest did the installing is
    asserted separately, so a conftest regression is still caught under pytest.
    """
    global _self_installed
    if getattr(socket.create_connection, "__module__", None) != "_netguard":
        _self_installed = _netguard.install()


def tearDownModule():
    if _self_installed is not None:
        _self_installed()


class LoopbackPredicateTests(unittest.TestCase):
    def test_loopback_forms_are_permitted(self):
        for address in (("127.0.0.1", 80), ("::1", 80), ("localhost", 80),
                        ("127.0.0.53", 53), ("", 80)):
            self.assertTrue(_netguard._is_loopback(address), repr(address))

    def test_unix_socket_paths_are_local(self):
        self.assertTrue(_netguard._is_loopback("/run/some.sock"))
        self.assertTrue(_netguard._is_loopback(b"/run/some.sock"))

    def test_public_destinations_are_refused(self):
        for address in (("api.mainnet-beta.solana.com", 443), ("8.8.8.8", 53),
                        ("192.0.2.1", 443), ("2606:4700::1111", 443)):
            self.assertFalse(_netguard._is_loopback(address), repr(address))

    def test_unparseable_addresses_fail_closed(self):
        """A guard that waves through what it does not understand is not a guard."""
        for address in (None, 42, object(), ()):
            self.assertFalse(_netguard._is_loopback(address), repr(address))

    def test_a_hostname_merely_containing_localhost_is_not_loopback(self):
        self.assertFalse(_netguard._is_loopback(("localhost.evil.example", 443)))
        self.assertFalse(_netguard._is_loopback(("not-127.0.0.1.example", 443)))


class GuardIsInstalledTests(unittest.TestCase):
    """If conftest stops installing the guard, this fails rather than the suite going quiet."""

    def test_socket_entry_points_are_patched_for_this_session(self):
        for name, function in (("create_connection", socket.create_connection),
                               ("connect", socket.socket.connect),
                               ("connect_ex", socket.socket.connect_ex)):
            self.assertEqual(getattr(function, "__module__", None), "_netguard",
                             f"socket.{name} is not the guarded version; the suite is not hermetic")

    def test_the_installed_guard_blocks_an_outbound_destination(self):
        with self.assertRaises(_netguard.OutboundConnectionBlocked):
            socket.create_connection(UNROUTABLE, timeout=1)

    def test_the_block_names_the_destination_and_says_what_to_do(self):
        with self.assertRaises(AssertionError) as ctx:
            socket.create_connection(UNROUTABLE, timeout=1)
        message = str(ctx.exception)
        self.assertIn("192.0.2.1", message, "must name the destination it refused")
        self.assertIn("127.0.0.1", message, "must say what to do instead")

    def test_blocking_is_an_assertionerror_so_it_reads_as_a_test_failure(self):
        self.assertTrue(issubclass(_netguard.OutboundConnectionBlocked, AssertionError))

    def test_under_pytest_the_guard_comes_from_conftest_not_from_this_file(self):
        """Keeps the canary sharp.

        `setUpModule` installs the guard as a fallback for `python -m unittest`, which loads no
        conftest. Without this assertion that fallback would mask a conftest regression: the guard
        would look installed while every *other* test file in the suite ran unprotected, because
        only this module self-installs.
        """
        if "pytest" not in sys.modules:
            self.skipTest("not running under pytest; conftest hooks do not apply")
        self.assertIsNone(_self_installed,
                          "conftest.py did not install the network guard, so the rest of the "
                          "suite is running unguarded; this file installed it only for itself")


class InstallAndRestoreTests(unittest.TestCase):
    """install() must be reversible, or it leaks into whatever runs after the suite."""

    def test_restore_puts_the_original_functions_back(self):
        before = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
        restore = _netguard.install()
        self.assertIsNot(socket.create_connection, before[2], "install() must patch")
        restore()
        self.assertEqual(
            (socket.socket.connect, socket.socket.connect_ex, socket.create_connection), before,
            "restore() must return the exact objects it replaced")

    def test_loopback_still_works_while_the_guard_is_installed(self):
        """The recorder credential-leak test serves canned RPC over 127.0.0.1 and must keep working.

        Hermetic means nothing leaves the machine, not that no socket may be opened.
        """
        server = socket.socket()
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            client = socket.create_connection(server.getsockname(), timeout=5)
            client.close()
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
