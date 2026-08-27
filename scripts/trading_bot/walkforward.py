#!/usr/bin/env python3
"""Walk-forward splits with a purge gap and an embargo. The gaps are mandatory, not options.

WHY THE GAPS EXIST
==================
A train/test boundary looks clean on a calendar and is not. Two things cross it:

**The warm-up.** A test fold that begins at bar k and uses an ATR(14) reads bars k-14..k --
which are TRAIN bars. That is not leakage in the harmful direction (the strategy is allowed
to know the past), but it means the test fold is not independent of the train fold, and a
significance test that treats folds as independent will overstate. So the splitter charges
`warmup_bars` explicitly and reports the overlap rather than hiding it.

**The label horizon.** Any strategy whose signal depends on an outcome realised over the
following h bars has, at the last h bars of the train fold, an outcome that lives inside the
test fold. Lopez de Prado's purge removes those train bars. `purge_bars` does that.

**The embargo** removes the first `embargo_bars` of the test fold instead, guarding the other
direction: serial correlation that lets the end of train predict the start of test for
reasons that have nothing to do with the signal.

Both default to a value derived from the strategy rather than to zero, and setting either to
zero requires saying so.

WHAT THIS MODULE DOES NOT DO
============================
It does not fit anything. This programme has no fitted model in equities and this rig is
being built before one exists, deliberately. The splitter produces index ranges; a strategy
that wants to fit gets `fit(train_view)` called on the train range only, and the engine then
runs it forward on the test range with the fitted state frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .frozen import Refused


@dataclass(frozen=True)
class Fold:
    index: int
    train_start: int
    train_end: int      # inclusive, AFTER purging
    test_start: int     # inclusive, AFTER embargo
    test_end: int       # inclusive
    purged_bars: int
    embargoed_bars: int
    warmup_bars: int

    @property
    def train_length(self) -> int:
        return self.train_end - self.train_start + 1

    @property
    def test_length(self) -> int:
        return self.test_end - self.test_start + 1

    def train_slice(self, series) -> tuple:
        return tuple(series[self.train_start:self.train_end + 1])

    def test_slice(self, series) -> tuple:
        """The test bars PLUS the warm-up bars immediately before them.

        The warm-up bars are handed over so the strategy's first test decision is computed
        from a full window rather than a truncated one, and the engine's `warmup_bars` then
        suppresses decisions over exactly those bars. The alternative -- letting the fold
        start cold -- produces a decision from a short window, which is the warm-up error
        B22B refuses at the ATR and which biases the first trades of every fold.
        """
        start = self.test_start - self.warmup_bars
        if start < 0:
            raise Refused(
                f"fold {self.index}: test start {self.test_start} has only {self.test_start} "
                f"bars of history but the strategy needs {self.warmup_bars}. A fold that "
                "cannot warm up is refused, not started cold."
            )
        return tuple(series[start:self.test_end + 1])

    def to_report(self) -> dict:
        return {
            "fold": self.index,
            "train": [self.train_start, self.train_end],
            "train_bars": self.train_length,
            "test": [self.test_start, self.test_end],
            "test_bars": self.test_length,
            "purged_bars": self.purged_bars,
            "embargoed_bars": self.embargoed_bars,
            "warmup_bars_prepended_to_test": self.warmup_bars,
        }


def walk_forward_folds(
    n_bars: int,
    *,
    n_folds: int,
    warmup_bars: int,
    purge_bars: int,
    embargo_bars: int,
    anchored: bool = True,
    min_train_bars: int | None = None,
) -> list:
    """Sequential, non-overlapping test folds, each strictly after its own train window.

    `anchored=True` grows the train window from bar 0 (expanding); `False` rolls a fixed
    window. Anchored is the default because a rolling window silently makes the effective
    sample size a tuning parameter.

    Every returned fold satisfies, by construction and by assertion:
        train_end + purge_bars < test_start  and  test_start <= test_end < next test_start
    """
    if n_folds < 1:
        raise Refused(f"n_folds must be >= 1; got {n_folds}")
    for name, value in (("warmup_bars", warmup_bars), ("purge_bars", purge_bars),
                        ("embargo_bars", embargo_bars)):
        if value is None:
            raise Refused(f"{name} must be stated explicitly; None is not zero")
        if value < 0:
            raise Refused(f"{name} must be >= 0; got {value}")

    min_train = min_train_bars if min_train_bars is not None else max(warmup_bars * 2, 30)
    usable = n_bars - min_train
    if usable < n_folds:
        raise Refused(
            f"{n_bars} bars cannot make {n_folds} folds with a {min_train}-bar minimum train "
            "window. Refusing rather than emitting folds too small to mean anything."
        )

    block = usable // n_folds
    folds = []
    for k in range(n_folds):
        raw_test_start = min_train + k * block
        test_end = min_train + (k + 1) * block - 1 if k < n_folds - 1 else n_bars - 1

        train_start = 0 if anchored else max(0, raw_test_start - min_train - purge_bars)
        train_end = raw_test_start - 1 - purge_bars
        test_start = raw_test_start + embargo_bars

        if train_end < train_start:
            raise Refused(
                f"fold {k}: purging {purge_bars} bars leaves no train window "
                f"({train_start}..{train_end}). Reduce purge_bars or lengthen the sample."
            )
        if test_start > test_end:
            raise Refused(
                f"fold {k}: embargoing {embargo_bars} bars leaves no test window. "
                "Reduce embargo_bars or lengthen the sample."
            )
        if train_end + purge_bars >= test_start:
            raise Refused(
                f"fold {k}: train ends at {train_end} and test starts at {test_start} with a "
                f"purge of {purge_bars} -- the windows touch. This is the leak the purge exists "
                "to prevent, so it is a refusal rather than a warning."
            )
        folds.append(Fold(
            index=k, train_start=train_start, train_end=train_end,
            test_start=test_start, test_end=test_end,
            purged_bars=purge_bars, embargoed_bars=embargo_bars, warmup_bars=warmup_bars,
        ))

    for prev, cur in zip(folds, folds[1:]):
        if cur.test_start <= prev.test_end:
            raise Refused(
                f"test folds {prev.index} and {cur.index} overlap "
                f"({prev.test_end} >= {cur.test_start}); out-of-sample results would be "
                "double-counted."
            )
    return folds


def assert_no_leakage(folds) -> dict:
    """Independent re-check of the invariants, run against the folds as returned.

    FINDINGS 8: 'Verify the diagnostic, not just the system.' Twice in this programme a
    checking tool was wrong rather than the thing checked, so the fold invariants are
    asserted a second time by code that does not share the construction logic.
    """
    if not folds:
        raise Refused("no folds to check")
    seen = set()
    for fold in folds:
        if fold.test_start > fold.test_end:
            raise Refused(f"fold {fold.index}: empty test window")
        if fold.train_end >= fold.test_start:
            raise Refused(
                f"fold {fold.index}: train ({fold.train_end}) reaches into test "
                f"({fold.test_start})"
            )
        if fold.train_end + fold.purged_bars >= fold.test_start:
            raise Refused(f"fold {fold.index}: purge gap not honoured")
        window = set(range(fold.test_start, fold.test_end + 1))
        if window & seen:
            raise Refused(f"fold {fold.index}: test bars already used by an earlier fold")
        seen |= window
    return {
        "verdict": "PASS",
        "folds": len(folds),
        "out_of_sample_bars": len(seen),
        "checks": [
            "every test window is non-empty",
            "no train window reaches into its own test window",
            "the purge gap is honoured on every fold",
            "no test bar is counted twice across folds",
        ],
        "note": (
            "Checked by code that does not share the construction logic, because in this "
            "programme the checking tool has twice been the thing that was wrong."
        ),
    }


__all__ = ["Fold", "walk_forward_folds", "assert_no_leakage"]
