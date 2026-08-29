#!/usr/bin/env python3
"""Hostile controls for the preregistered PAC V2.1 detector."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect

from .execution import ReserveState
from . import pac_v21_detector as detector
from .pac_v2_feed import ClockedEvent


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def state(real_quote: int) -> ReserveState:
    return ReserveState(
        virtual_quote=30_000_000_000 + real_quote,
        virtual_token=1_000_000_000_000_000,
        real_quote=real_quote,
        real_token=720_100_000_000_000,
        complete=False,
    )


def event(index: int, pre_quote: int, post_quote: int, *, base: int,
          side: str, trader: str, mint: str = "mint", epoch: str = "epoch") -> ClockedEvent:
    source = base + index * 500_000_000
    return ClockedEvent(
        event_id=hashlib.sha256(
            f"{mint}|{epoch}|{index}|{pre_quote}|{post_quote}|{side}|{trader}".encode()).hexdigest(),
        collector_epoch=epoch, mint=mint, trader=trader, signature=f"sig-{index}",
        slot=index + 1, side=side, source_received_unix_nanos=source,
        materialized_unix_nanos=source + 1, runner_seen_unix_nanos=source + 2,
        pre_state=state(pre_quote), post_state=state(post_quote),
    )


def passing(base: int = 1_000_000_000_000) -> tuple[ClockedEvent, ...]:
    # 0.15-SOL shock covers a 0.10-SOL probe. Recovery first reaches the 1.20-SOL floor at event 2;
    # event 4 supplies a 1-second dwell, the third distinct non-seller buyer, and >6x shock cover.
    return (
        event(0, 1_200_000_000, 1_050_000_000, base=base, side="sell", trader="seller"),
        event(1, 1_050_000_000, 1_120_000_000, base=base, side="buy", trader="buyer-1"),
        event(2, 1_120_000_000, 1_200_000_000, base=base, side="buy", trader="buyer-2"),
        event(3, 1_200_000_000, 1_240_000_000, base=base, side="buy", trader="buyer-3"),
        event(4, 1_240_000_000, 1_260_000_000, base=base, side="buy", trader="buyer-3"),
    )


def main() -> int:
    events = passing()
    result = detector.qualify(
        events, processed_p90_nanos=1_000_000_000,
        quote_input_lamports=100_000_000)
    check(result is not None, "one payable shock + full recovery + processed dwell qualifies")
    assert result is not None
    check(result.shock_index == 0 and result.recovery_index == 2,
          "first full recovery and shock coordinates are exact")
    check(result.shock_lamports == 150_000_000
          and result.pre_shock_reserve_lamports == 1_200_000_000
          and result.reserve_cover_lamports == 900_000_000,
          "shock, economic floor and 6x reserve cover are exact integers")
    check(result.buyer_breadth_ex_seller == 3,
          "buyer breadth counts distinct post-shock addresses excluding seller")
    check(result.evidence_indices == tuple(range(len(events)))
          and result.evidence_event_ids[-1] == events[-1].event_id,
          "evidence binds the complete shock-to-decision chain and newest event")

    too_small = (replace(events[0], pre_state=state(1_140_000_000)), *events[1:])
    check(detector.qualify(too_small, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "shock smaller than the planned probe refuses")

    partial = events[:2]
    check(detector.qualify(partial, processed_p90_nanos=1,
                           quote_input_lamports=100_000_000) is None,
          "partial recovery refuses")

    short_dwell = events[:4]
    check(detector.qualify(short_dwell, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "sub-p90 processed dwell refuses")

    eroded = (
        *events[:3],
        event(3, 1_200_000_000, 1_190_000_000, base=1_000_000_000_000,
              side="sell", trader="later-seller"),
        event(4, 1_190_000_000, 1_260_000_000, base=1_000_000_000_000,
              side="buy", trader="buyer-3"),
    )
    check(detector.qualify(eroded, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "any post-recovery erosion below the pre-shock floor refuses")

    two_buyers = tuple(replace(item, trader="buyer-2") if item.trader == "buyer-3" else item
                       for item in events)
    check(detector.qualify(two_buyers, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "fewer than three distinct buyers refuses")

    seller_rebuy = tuple(replace(item, trader="seller") if item.trader == "buyer-3" else item
                         for item in events)
    check(detector.qualify(seller_rebuy, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "shock seller rebuy cannot satisfy buyer breadth")

    low_cover = (
        event(0, 500_000_000, 400_000_000, base=2_000_000_000_000,
              side="sell", trader="seller"),
        event(1, 400_000_000, 460_000_000, base=2_000_000_000_000,
              side="buy", trader="buyer-1"),
        event(2, 460_000_000, 500_000_000, base=2_000_000_000_000,
              side="buy", trader="buyer-2"),
        event(3, 500_000_000, 520_000_000, base=2_000_000_000_000,
              side="buy", trader="buyer-3"),
        event(4, 520_000_000, 530_000_000, base=2_000_000_000_000,
              side="buy", trader="buyer-3"),
    )
    check(detector.qualify(low_cover, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "full recovery without 6x current reserve cover refuses")

    cross_mint = (*events[:-1], replace(events[-1], mint="other"))
    cross_epoch = (*events[:-1], replace(events[-1], collector_epoch="other"))
    backward = (*events[:-1], replace(
        events[-1], source_received_unix_nanos=events[-2].source_received_unix_nanos))
    broken = (*events[:-1], replace(events[-1], pre_state=state(999_000_000)))
    for stream, label in ((cross_mint, "cross-mint"), (cross_epoch, "cross-epoch"),
                          (backward, "backward-clock"), (broken, "broken-reserve-chain")):
        check(detector.qualify(stream, processed_p90_nanos=1_000_000_000,
                               quote_input_lamports=100_000_000) is None,
              f"{label} stream refuses")

    check(detector.qualify(events, processed_p90_nanos=True,
                           quote_input_lamports=100_000_000) is None
          and detector.qualify(events, processed_p90_nanos=1_000_000_000,
                               quote_input_lamports=100_000_000.0) is None,
          "bool/float calibration or sizing refuses")
    signature = inspect.signature(detector.qualify)
    check(signature.parameters["processed_p90_nanos"].default is inspect.Parameter.empty,
          "processed p90 is mandatory and has no finalized/default fallback")

    print(f"PAC V2.1 DETECTOR SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
