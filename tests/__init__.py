"""Package init for the test suite — exists to install the network guard under **every** runner.

`tests/conftest.py` installs the guard via `pytest_configure`, which covers pytest and nothing else.
`python -m unittest discover -s tests` never loads a conftest, so under that runner the suite ran
**unguarded** — and that is the runner this project has actually been using in every handoff that
claimed "N tests pass" beside "zero RPC". Verified by probe: a connect to 192.0.2.1 under unittest
raised `TimeoutError` (a real outbound attempt that timed out) where pytest raised
`OutboundConnectionBlocked`. See `agent_discussion.md` Seq 111/112.

Making `tests/` a package means unittest discovery imports this module **before** any test module,
which is the only hook that runner offers. Two consequences handled here:

1. Discovery now puts the repository root on `sys.path` instead of `tests/`, so the sibling imports
   several test modules rely on (`from _isolation import ...`, `import _netguard`) would break.
   This module re-inserts its own directory first, exactly as `conftest.py` does.
2. Under pytest both this module and `conftest.py` would install. The check below skips the second
   install rather than double-wrapping, so `conftest.py`'s `pytest_unconfigure` restore still puts
   the real socket functions back. `_netguard.install()` itself is deliberately **not** modified —
   its install/restore round-trip is pinned by `test_netguard.py`, and making it globally
   idempotent breaks that contract.
"""
import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _netguard  # noqa: E402

# `install()` rebinds `socket.socket.connect` to a closure defined in `_netguard`, so the module of
# the currently-bound function tells us whether a guard is already active without probing the
# network to find out.
if getattr(socket.socket.connect, "__module__", None) != _netguard.__name__:
    _netguard.install()
