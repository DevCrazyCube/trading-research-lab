"""Session-wide test configuration.

The network guard is installed for the entire session rather than per test, so hermeticity is a
property of the suite by construction instead of something each author has to remember. See
`tests/_netguard.py` for why (`agent_discussion.md` Seq 109/110).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _netguard                                       # noqa: E402

_restore = None


def pytest_configure(config):
    global _restore
    _restore = _netguard.install()


def pytest_unconfigure(config):
    if _restore is not None:
        _restore()
