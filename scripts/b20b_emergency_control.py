"""B20b — the operator control surface for emergency state. The other half of slice E.

B19a requires "a separate authenticated local operator mechanism" that owns emergency state, kept
apart from the read-only browser and from strategy code. `b20a` is the owner of the state; this is
the mechanism a human reaches it through, and it is a SEPARATE FILE on purpose.

WHY SEPARATE, WHICH IS THE ONLY INTERESTING DESIGN DECISION HERE. `b20a` contains no `argparse`,
and one of its tests asserts that, because the operator secret must never be reachable through
argv — argv is visible in `ps` to every user on the machine, ends up in shell history, and is
captured by process accounting. Putting a CLI inside `b20a` would delete that guarantee by making
the module's own test unenforceable. So the argument parsing lives here, the secret still comes
only from the environment, and NO SUBCOMMAND ACCEPTS IT.

WHAT THIS ADDS TO THE SYSTEM: nothing. It holds no state, decides nothing, and computes no value.
Every operation is a thin pass-through to `b20a`, which owns every rule. If this file disappeared,
the switch would still be engaged-by-default and every guard would still hold; only the human's
route to it would be gone. That is deliberate — a control surface that carried its own policy would
be a second implementation of the thing it controls, and the two would eventually disagree.

    python scripts/b20b_emergency_control.py status
    python scripts/b20b_emergency_control.py engage --reason "watcher died" --operator anont
    python scripts/b20b_emergency_control.py clear --reason "cause understood" --operator anont \
        --expect-generation 3
    python scripts/b20b_emergency_control.py heartbeat --loop --interval-seconds 15

`status` is the only subcommand that is safe to run without thinking, and it is the default.

ENGAGING IS EASY AND CLEARING IS NOT. `engage` needs a reason and an operator. `clear` needs those
plus the generation the operator believes is current, so an operator who has not looked at the state
since somebody else moved it is refused instead of quietly overriding them. That asymmetry is the
point: the cost of engaging wrongly is a halt, and the cost of clearing wrongly is everything the
halt was protecting against.

No network, no wallet, no key, no transaction. This process reads a clock, reads and writes one
local JSON file through `b20a`, and prints.
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B20A = _load("b20a_emergency_state", "b20a_emergency_state.py")

# Exit codes are part of the interface: a shell or supervisor should be able to branch on
# "is it engaged" without parsing prose.
EXIT_CLEAR = 0
EXIT_ENGAGED = 2
EXIT_REFUSED = 3


def now_nanos(clock=time.time):
    """The one place a wall clock is read. b20a takes the time as an argument precisely so that
    every rule in it is testable at its boundaries; the clock belongs at the edge, here."""
    return int(clock() * 1_000_000_000)


def do_status(args, out, now):
    verdict = B20A.read_verdict(now, state_path=args.state, receipt_path=args.receipts)
    snapshot = B20A.snapshot(verdict)
    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True), file=out)
    else:
        state = "ENGAGED" if verdict["kill_switch_engaged"] else "clear"
        print(f"emergency state : {state}", file=out)
        print(f"reason code     : {verdict['reason_code']}", file=out)
        print(f"generation      : {verdict['generation']}", file=out)
        if verdict["detail"]:
            print(f"detail          : {verdict['detail']}", file=out)
        if verdict["kill_switch_engaged"] and verdict["reason_code"] != B20A.E09_EXPLICITLY_ENGAGED:
            print("\nNOTE: this is engaged by a FAIL-CLOSED DEFAULT, not by an operator action.",
                  file=out)
            print("Nothing is unsafe. Something could not be verified, and the safe reading of an "
                  "unverifiable state is engaged.", file=out)
    return EXIT_ENGAGED if verdict["kill_switch_engaged"] else EXIT_CLEAR


def do_engage(args, out, now):
    record = B20A.engage(args.reason, args.operator, now,
                         state_path=args.state, receipt_path=args.receipts)
    print(f"ENGAGED at generation {record['generation']}: {record['reason']}", file=out)
    return EXIT_ENGAGED


def do_clear(args, out, now):
    record = B20A.clear(args.reason, args.operator, args.expect_generation, now,
                        state_path=args.state, receipt_path=args.receipts)
    print(f"cleared at generation {record['generation']}: {record['reason']}", file=out)
    # Re-read rather than trusting the write. The verifiers may still disagree, in which case the
    # switch is engaged despite a successful clear, and an operator who walked away believing
    # otherwise would be wrong in the worst available direction.
    verdict = B20A.read_verdict(now, state_path=args.state, receipt_path=args.receipts)
    if verdict["kill_switch_engaged"]:
        print(f"BUT IT READS AS ENGAGED: {verdict['reason_code']} — {verdict['detail']}", file=out)
        return EXIT_ENGAGED
    return EXIT_CLEAR


def do_heartbeat(args, out, now, clock=time.time, sleeper=time.sleep):
    """Liveness only. A heartbeat can never clear — b20a refuses to let it — so this loop cannot
    turn into an accidental un-halt no matter how long it runs."""
    if not args.loop:
        B20A.heartbeat(now, state_path=args.state, receipt_path=args.receipts)
        print("heartbeat written", file=out)
        return EXIT_CLEAR
    count = 0
    while args.max_beats is None or count < args.max_beats:
        B20A.heartbeat(now_nanos(clock), state_path=args.state, receipt_path=args.receipts)
        count += 1
        print(f"heartbeat {count}", file=out, flush=True)
        if args.max_beats is not None and count >= args.max_beats:
            break
        sleeper(args.interval_seconds)
    return EXIT_CLEAR


def build_parser():
    parser = argparse.ArgumentParser(
        description="Operator control for emergency state. The secret is read from "
                    f"${B20A.OPERATOR_SECRET_ENV} and is NEVER accepted as an argument.")
    parser.add_argument("--state", type=pathlib.Path, default=B20A.STATE_PATH)
    parser.add_argument("--receipts", type=pathlib.Path, default=B20A.RECEIPT_PATH)
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="read the state; safe to run without thinking")
    status.add_argument("--json", action="store_true")

    engage = sub.add_parser("engage", help="halt. Needs no strategy, RPC or signer.")
    engage.add_argument("--reason", required=True)
    engage.add_argument("--operator", required=True)

    clear = sub.add_parser("clear", help="the only route to a not-engaged state")
    clear.add_argument("--reason", required=True)
    clear.add_argument("--operator", required=True)
    clear.add_argument("--expect-generation", required=True, type=int,
                       help="the generation you believe is current; refuses if someone moved it")

    beat = sub.add_parser("heartbeat", help="liveness only; can never clear")
    beat.add_argument("--loop", action="store_true")
    beat.add_argument("--interval-seconds", type=int, default=15)
    beat.add_argument("--max-beats", type=int, default=None)
    return parser


def main(argv=None, out=None, now=None):
    out = out or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    args.command = args.command or "status"
    if args.command == "status":
        args.json = getattr(args, "json", False)
    now = now if now is not None else now_nanos()

    handlers = {"status": do_status, "engage": do_engage, "clear": do_clear,
                "heartbeat": do_heartbeat}
    try:
        return handlers[args.command](args, out, now)
    except B20A.EmergencyRefused as refusal:
        # A refusal is an answer, printed plainly. It is never silently downgraded to a warning:
        # the operator asked for something and did not get it, and needs to know that.
        print(f"REFUSED: {refusal}", file=out)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
