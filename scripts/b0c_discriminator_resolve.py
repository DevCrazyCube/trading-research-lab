#!/usr/bin/env python3
"""B0c - resolve observed Anchor discriminators to instruction/event names.

Offline and deterministic. Anchor derives:
    instruction discriminator = sha256("global:" + snake_case_name)[:8]
    event discriminator       = sha256("event:" + CamelCaseName)[:8]

A match is a derivation, not a guess: the name is confirmed iff its hash equals the
observed bytes. Unmatched discriminators stay explicitly unknown.
"""
import hashlib
import sys

OBSERVED_OUTER = {
    "66063d1201daebea": 24,
    "f945a4da9667548a": 15,
    "33e685a4017f83ad": 5,
    "b817ee6167c5d33d": 2,
    "253a237ebe35e4c5": 1,
    "d6904cec5f8b31b4": 1,
}
OBSERVED_INNER = {
    "e445a52e51cb9a1d": 51,
    "66063d1201daebea": 7,
    "33e685a4017f83ad": 5,
    "5df6823ce7e940b2": 4,
    "c2ab1c46684d5b2f": 1,
    "b817ee6167c5d33d": 1,
}

IX_NAMES = [
    "buy", "sell", "create", "initialize", "set_params", "withdraw", "migrate",
    "buy_v2", "sell_v2", "buy_exact_quote_in_v2", "sell_exact_quote_out_v2",
    "collect_creator_fee", "set_creator", "set_metaplex_creator",
    "extend_account", "update_global_authority", "set_coin_creator",
    "sync_user_volume_accumulator", "close_user_volume_accumulator",
    "init_user_volume_accumulator", "claim_token_incentives",
    "admin_set_creator", "admin_update_token_incentives", "admin_set_idl_authority",
    "create_and_buy", "close", "collect_coin_creator_fee",
    "claim_cashback", "create_v2",
]
EVENT_NAMES = [
    "TradeEvent", "CreateEvent", "CompleteEvent", "SetParamsEvent",
    "CompletePumpAmmMigrationEvent", "ExtendAccountEvent", "CollectCreatorFeeEvent",
    "SetCreatorEvent", "UpdateGlobalAuthorityEvent", "SyncUserVolumeAccumulatorEvent",
    "ClaimTokenIncentivesEvent", "SetMetaplexCreatorEvent", "AdminSetCreatorEvent",
]
SPECIAL_DISCRIMINATORS = {
    "e445a52e51cb9a1d": "Anchor emit_cpi! event-instruction tag (EVENT_IX_TAG_LE)"
}


def disc(prefix, name):
    return hashlib.sha256(f"{prefix}{name}".encode()).digest()[:8].hex()


def build():
    table = {}
    for n in IX_NAMES:
        table[disc("global:", n)] = f"instruction `{n}`"
    for n in EVENT_NAMES:
        table[disc("event:", n)] = f"event `{n}`"
    table.update(SPECIAL_DISCRIMINATORS)
    return table


def report(title, observed, table):
    print(f"\n{title}")
    print("-" * len(title))
    for d, count in sorted(observed.items(), key=lambda kv: -kv[1]):
        name = table.get(d)
        mark = "RESOLVED" if name else "UNKNOWN "
        print(f"  {mark}  {d}  n={count:<4} {name or '(no candidate name hashes to this)'}")


if __name__ == "__main__":
    t = build()
    print(f"candidate names hashed: {len(IX_NAMES)} instructions, {len(EVENT_NAMES)} events")
    report("Outer instruction discriminators", OBSERVED_OUTER, t)
    report("Inner (self-CPI) discriminators", OBSERVED_INNER, t)
    if "--dump" in sys.argv:
        print("\nfull candidate table:")
        for d, n in sorted(t.items(), key=lambda kv: kv[1]):
            print(f"  {d}  {n}")
