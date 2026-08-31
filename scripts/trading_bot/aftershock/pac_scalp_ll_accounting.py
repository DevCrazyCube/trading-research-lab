#!/usr/bin/env python3
"""Exact all-cost liquidation equity for the low-latency PAC scalp experiment.

This is deliberately separate from the sealed PAC_SCALP baseline.  A clean full sale can reclaim
the entry-created ATA rent, but doing so costs one close-account transaction.  Failed exit attempts
are capital already spent.  The number used by the stop, peak, trail, marks, and terminal return is
therefore one and the same exact integer.
"""
from __future__ import annotations

from dataclasses import dataclass

from .execution import RefusedExecution


@dataclass(frozen=True)
class LiquidationEquity:
    wallet_proceeds_lamports: int
    ata_rent_reclaim_lamports: int
    ata_close_cost_lamports: int
    failed_attempt_cost_lamports: int
    equity_lamports: int


def settled_equity(*, wallet_proceeds_lamports: int, ata_rent_lamports: int,
                   ata_close_cost_lamports: int, failed_attempt_cost_lamports: int,
                   ata_close_succeeded: bool) -> LiquidationEquity:
    """Settle a completed full-token sale without inventing an ATA reclaim.

    The entry-created ATA rent is returned only after separate close-account evidence.  A failed
    close still spends its attempt cost and leaves the rent locked.  This is the terminal convention;
    :func:`liquidation_equity` remains the executable-quote convention for a hypothetical clean
    sell+close and delegates here with ``ata_close_succeeded=True``.
    """
    values = {
        "wallet_proceeds_lamports": wallet_proceeds_lamports,
        "ata_rent_lamports": ata_rent_lamports,
        "ata_close_cost_lamports": ata_close_cost_lamports,
        "failed_attempt_cost_lamports": failed_attempt_cost_lamports,
    }
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise RefusedExecution("settled-equity inputs must be exact non-negative integers")
    if type(ata_close_succeeded) is not bool:
        raise RefusedExecution("ATA close outcome must be a boolean")
    if wallet_proceeds_lamports <= 0:
        raise RefusedExecution("a settled full-token sale requires positive wallet proceeds")
    if ata_close_succeeded and ata_close_cost_lamports > ata_rent_lamports:
        raise RefusedExecution("ATA close cost exceeds the reclaimable rent")
    reclaim = ata_rent_lamports if ata_close_succeeded else 0
    equity = (wallet_proceeds_lamports + reclaim
              - ata_close_cost_lamports - failed_attempt_cost_lamports)
    if equity <= 0:
        raise RefusedExecution("settled equity is net-nonpositive")
    return LiquidationEquity(
        wallet_proceeds_lamports=wallet_proceeds_lamports,
        ata_rent_reclaim_lamports=reclaim,
        ata_close_cost_lamports=ata_close_cost_lamports,
        failed_attempt_cost_lamports=failed_attempt_cost_lamports,
        equity_lamports=equity,
    )


def liquidation_equity(*, wallet_proceeds_lamports: int, ata_rent_lamports: int,
                       ata_close_cost_lamports: int,
                       failed_attempt_cost_lamports: int) -> LiquidationEquity:
    return settled_equity(
        wallet_proceeds_lamports=wallet_proceeds_lamports,
        ata_rent_lamports=ata_rent_lamports,
        ata_close_cost_lamports=ata_close_cost_lamports,
        failed_attempt_cost_lamports=failed_attempt_cost_lamports,
        ata_close_succeeded=True)


def return_fraction(*, equity_lamports: int, entry_all_in_lamports: int) -> tuple[int, int]:
    if (type(equity_lamports) is not int or equity_lamports < 0
            or type(entry_all_in_lamports) is not int or entry_all_in_lamports <= 0):
        raise RefusedExecution("return fraction inputs are invalid")
    return equity_lamports - entry_all_in_lamports, entry_all_in_lamports
