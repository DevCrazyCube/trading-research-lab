"""NEWSDESK -- the agent-driven, world-reading forward paper LOGGER.

A SIBLING of BASKET1 (`scripts/trading_bot/basket_forward.py`), not a new bot. It adds exactly one
thing the basket does not have: **part 5 of a discretionary trader's edge -- a contextual read of the
world** -- supplied by an agent reading free live news/event feeds, and executes that read through the
same asymmetry + risk + discipline machinery (parts 2/3/4) the programme already enforces.

It places **NO orders, holds NO position, touches NO account or real money**, and reads only a fixed
allowlist of free, keyless public data hosts. Every number it logs is a hypothetical R-multiple. The
instrument is lookahead-proof by construction: the agent commits a falsifiable trade (sha256 + UTC
timestamp) BEFORE the move, and resolution reads only the strictly-later price path.

See `research/trading_bot/newsdesk/NEWSDESK_PREREGISTRATION.md` for the frozen rules and the honest
prior (news is priced in within seconds; the expectancy may be zero).
"""

from __future__ import annotations


class Refused(RuntimeError):
    """Absence is a refusal, never a silent zero.

    Locally defined (not imported from the b22b pin) so the Newsdesk never refuses to START because an
    unrelated frozen harness moved -- but it carries the identical house meaning: a missing datum, a
    lookahead, or a broken rule REFUSES rather than fabricating a number that looks like evidence.
    """


__all__ = ["Refused"]
