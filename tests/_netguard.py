"""Block outbound network access for the whole test session.

Why this exists, concretely rather than as hygiene:

`tests/test_recorder.py::CredentialLeakTests` called `recorder.run()` against the **public mainnet
endpoint** for six seconds on every suite run, pulling real blocks off the chain
(`agent_discussion.md` Seq 109). That went unnoticed for weeks while both agents wrote handoff
entries asserting "read-only, zero RPC" and "N tests pass repo-wide" in the same breath. The two
claims were contradictory every time.

The specific test was fixed. This guard exists because *that* fix only covers the test that was
caught: without an enforced invariant, the next test to reach the network is discovered the same
way, by someone happening to notice a stray log line. AGENTS.md already forbids live network work
in this project; a guard does not create that policy, it stops the suite silently breaking one that
already exists.

**Loopback is deliberately allowed.** The recorder credential-leak test serves canned JSON-RPC from
a `127.0.0.1` `http.server` on purpose: stubbing the transport instead would stop exercising the
segment writer, frame index, slot-observation index and session meta — the paths where a credential
could actually leak. Hermetic means "nothing leaves the machine", not "no sockets".
"""
import socket

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "", None})


class OutboundConnectionBlocked(AssertionError):
    """A test tried to reach the network. Raised as AssertionError so it reads as a test failure."""


def _is_loopback(address):
    """True for loopback destinations. Unrecognised address shapes are NOT waved through.

    AF_UNIX sockets pass a string path rather than a (host, port) tuple; those are local by
    definition and allowed. Anything else that cannot be parsed is refused, because failing closed
    is the whole point - a guard that allows what it does not understand is not a guard.
    """
    if isinstance(address, (str, bytes)):
        return True                                   # AF_UNIX path: local
    try:
        host = address[0]
    except (TypeError, IndexError, KeyError):
        return False
    if host in LOOPBACK:
        return True
    if isinstance(host, str) and host.startswith("127."):
        return True
    return False


def _blocked(address, call):
    return OutboundConnectionBlocked(
        f"test attempted an outbound connection to {address!r} via {call}. "
        f"The suite must be hermetic: AGENTS.md permits no live network work, and a test that "
        f"reaches the chain makes every 'zero RPC' claim in agent_discussion.md false. "
        f"Serve canned responses over 127.0.0.1, or stub the transport.")


def install():
    """Patch socket entry points. Returns a callable that restores them."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create = socket.create_connection

    def connect(self, address):
        if not _is_loopback(address):
            raise _blocked(address, "socket.connect")
        return real_connect(self, address)

    def connect_ex(self, address):
        if not _is_loopback(address):
            raise _blocked(address, "socket.connect_ex")
        return real_connect_ex(self, address)

    def create_connection(address, *args, **kwargs):
        if not _is_loopback(address):
            raise _blocked(address, "socket.create_connection")
        return real_create(address, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.create_connection = create_connection

    def restore():
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex
        socket.create_connection = real_create

    return restore
