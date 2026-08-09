#!/usr/bin/env python3
"""Push B11a collection events to Telegram, so a five-day run does not need an SSH session.

NOT part of the frozen pipeline and deliberately not manifest-pinned: it observes, it never
participates. It opens the supervisor's state file READ-ONLY, sends outbound HTTPS, and touches no
artifact, no receipt and no lock. If this process dies, the collection does not notice.

THE HAZARD THIS MODULE IS MOSTLY ABOUT. The state file, the logs and the receipts all reference the
paid RPC endpoint, and that URL carries a credential in its path. A notifier that forwarded log
lines would publish that key to a third-party server, permanently, in a chat history. This project
has already had one credential-in-artifact incident. So every outbound message goes through
`assert_no_secret` FIRST, a match is fatal rather than redacted, and the fields sent are named
individually -- never "here is the state file" or "here is the last log line".

The bot token is itself a credential and is read from the environment. It is added to the secret
set, so a message that would echo the token back cannot be sent either.
"""
import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "research" / "b11a" / "supervisor_state.json"
RECEIPT_DIR = ROOT / "research" / "b11a" / "receipts"
TOKEN_VAR = "TELEGRAM_BOT_TOKEN"
CHAT_VAR = "TELEGRAM_CHAT_ID"
RPC_ENV_VAR = "SOLANA_RPC_URL"
API = "https://api.telegram.org"


class NotifyRefused(RuntimeError):
    """Raised instead of sending. Never caught internally: a refusal must not become a redaction."""


def load_env(path=ROOT / ".env"):
    """Read .env into the environment without printing it. Existing values win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def secret_values():
    """Everything that must never appear in an outbound message.

    The RPC URL whole, its query values and any long path segment -- Chainstack puts the key in the
    path, which is exactly the shape a naive `netloc`-only sanitiser misses. Plus the bot token,
    because a notifier that can leak its own credential is not better than one that leaks the other.
    """
    values = set()
    for name, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        if any(marker in name.upper() for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")):
            values.add(value)
        if name == RPC_ENV_VAR:
            parts = urllib.parse.urlsplit(value)
            values.add(value)
            for _, candidate in urllib.parse.parse_qsl(parts.query):
                if len(candidate) >= 8:
                    values.add(candidate)
            for segment in parts.path.split("/"):
                if len(segment) >= 16:
                    values.add(segment)
    return values


def assert_no_secret(text, secrets=None):
    """A match is FATAL. Redacting would mean the caller keeps building messages from raw sources
    and trusting this to catch them; refusing means the caller has to name safe fields instead.

    AN EMPTY SECRET SET IS ALSO FATAL, and that is the half a first draft of this got wrong. With
    no credentials in the environment -- nobody sourced .env -- `secret_values()` returns nothing,
    every message matches nothing, and the guard passes EVERYTHING while looking like it is
    working. A check that cannot fire is worse than no check, because the absent check is at least
    visible. So an unverifiable message is refused rather than sent unverified.
    """
    known = secret_values() if secrets is None else set(secrets)
    if not known:
        raise NotifyRefused(
            "REFUSING to send: no credentials are visible in the environment, so this cannot "
            "verify the message does not contain one. Source .env first. Sending anyway would "
            "mean the guard passed because it knew nothing, not because the message was clean")
    for secret in known:
        if secret and secret in text:
            raise NotifyRefused(
                "REFUSING to send: the message contains a credential. It is not redacted here on "
                "purpose -- a notifier that quietly strips secrets teaches its callers to pass raw "
                "log text, and the next value it does not recognise goes out intact")


def send(text, token=None, chat_id=None, opener=None):
    """One message. Refuses before any network call if the text carries a credential."""
    token = token or os.environ.get(TOKEN_VAR)
    chat_id = chat_id or os.environ.get(CHAT_VAR)
    if not token:
        raise NotifyRefused(f"{TOKEN_VAR} is not set; source .env or export it")
    if not chat_id:
        raise NotifyRefused(f"{CHAT_VAR} is not set; run `operator_notify.py chat-id` first")
    assert_no_secret(text)
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    request = urllib.request.Request(f"{API}/bot{token}/sendMessage", data=body, method="POST")
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=20) as response:
        return json.loads(response.read()).get("ok", False)


def discover_chat_id(token=None, opener=None):
    """The chat id of whoever last messaged the bot. Run after saying anything to it."""
    token = token or os.environ.get(TOKEN_VAR)
    if not token:
        raise NotifyRefused(f"{TOKEN_VAR} is not set")
    open_url = opener or urllib.request.urlopen
    with open_url(f"{API}/bot{token}/getUpdates", timeout=20) as response:
        payload = json.loads(response.read())
    for update in reversed(payload.get("result", [])):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is not None:
            return chat["id"]
    return None


# ------------------------------------------------------------------------------------------------
# What is worth waking somebody for
# ------------------------------------------------------------------------------------------------

def watcher_is_running():
    """Whether a supervisor process actually exists. /proc, so no dependency and no shell."""
    import pathlib as _p
    for entry in _p.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().decode(errors="replace")
        except (OSError, FileNotFoundError):
            continue                       # a process may exit between listing and reading
        if "b11c_maturity_watcher" in command and "zsh" not in command:
            return True
    return False


def describe(state, receipts):
    """The safe projection of the supervisor's state. Named fields ONLY.

    Deliberately not `json.dumps(state)`: the state carries `endpoint`, and a whole-object dump is
    how a sanitiser gets bypassed by a field somebody adds later. Adding a field here is a choice;
    inheriting one is not.
    """
    quarantine = state.get("quarantine") or {}
    heartbeat = state.get("stage_heartbeat_at")
    return {
        "state": state.get("state"),
        # THE BLIND SPOT THIS CLOSES. Everything else here is a state CHANGE, and a watcher that
        # died stops changing state -- so silence read exactly like a healthy run. A collection sat
        # quarantined for ninety-five minutes with nothing to report because nothing had changed.
        # Liveness is not a change; it has to be sampled.
        "watcher_running": watcher_is_running(),
        "stalled_seconds": int(time.time() - heartbeat) if heartbeat else None,
        "stage_in_flight": state.get("stage_in_flight"),
        "stages_completed": list(state.get("stages_completed") or []),
        "receipts": sorted(receipts),
        "quarantine_reason": quarantine.get("reason_code"),
        "quarantine_stage": quarantine.get("stage"),
        "polls": state.get("polls"),
        "last_tip_slot": state.get("last_tip_slot"),
    }


def render(previous, current):
    """A message for a change worth reading, or None. Quiet by default: a notifier that pings on
    every heartbeat is one whose alerts get muted, and the muted alert is the quarantine."""
    if previous is None:
        return (f"B11a watcher observed\nstate: {current['state']}\n"
                f"stages done: {len(current['stages_completed'])}/9")
    lines = []
    # A stall is reported ONCE, on the edge, not every interval -- an alert that repeats every
    # minute is one that gets muted, and this is the alert that matters overnight.
    stalled = (current.get("stalled_seconds") or 0) > 900 and not current["watcher_running"]
    was_stalled = (previous.get("stalled_seconds") or 0) > 900 and not previous["watcher_running"]
    if stalled and not was_stalled:
        lines.append(f"STALLED: no watcher process and no heartbeat for "
                     f"{current['stalled_seconds'] // 60} minutes. The collection is not running "
                     f"and nothing will report it, because a dead watcher changes no state.")
    if previous["watcher_running"] and not current["watcher_running"] and not stalled:
        lines.append("the watcher process is gone")
    if current["quarantine_reason"] and current["quarantine_reason"] != previous["quarantine_reason"]:
        lines.append(f"QUARANTINED: {current['quarantine_reason']}"
                     + (f" at {current['quarantine_stage']}" if current["quarantine_stage"] else ""))
    if current["stages_completed"] != previous["stages_completed"]:
        done = current["stages_completed"]
        lines.append(f"stage complete: {done[-1] if done else '(none)'}  [{len(done)}/9]")
    if current["stage_in_flight"] != previous["stage_in_flight"] and current["stage_in_flight"]:
        lines.append(f"stage started: {current['stage_in_flight']}")
    if current["state"] != previous["state"]:
        lines.append(f"state: {previous['state']} -> {current['state']}")
    return "\n".join(lines) if lines else None


def read_once(state_path=STATE_PATH, receipt_dir=RECEIPT_DIR):
    if not pathlib.Path(state_path).exists():
        return None
    state = json.loads(pathlib.Path(state_path).read_text())
    receipts = [p.stem for p in pathlib.Path(receipt_dir).iterdir()] \
        if pathlib.Path(receipt_dir).exists() else []
    return describe(state, receipts)


def watch(interval=60, state_path=STATE_PATH, receipt_dir=RECEIPT_DIR, sender=None, once=False):
    """Poll the state file and send on meaningful change. Never raises into the caller for a
    transport failure: a phone that cannot be reached is not a reason to stop watching."""
    sender = sender or send
    previous = None
    while True:
        current = read_once(state_path, receipt_dir)
        if current is not None:
            message = render(previous, current)
            if message:
                try:
                    sender(message)
                except NotifyRefused:
                    raise
                except Exception as error:                      # transport only
                    print(f"notify failed ({type(error).__name__}); continuing", file=sys.stderr)
            previous = current
        if once:
            return previous
        time.sleep(interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("chat-id", help="print the chat id of whoever last messaged the bot")
    test = sub.add_parser("test", help="send one message")
    test.add_argument("--text", default="B11a notifier online.")
    say = sub.add_parser("say", help="send an arbitrary message; refuses if it carries a credential")
    say.add_argument("--text", required=True)
    say.add_argument("--from", dest="seat", default=None,
                     help="which seat is speaking, prefixed to the message")
    commit = sub.add_parser("commit", help="announce a git commit by subject line only")
    commit.add_argument("--sha", required=True)
    commit.add_argument("--subject", required=True)
    commit.add_argument("--seat", default=None)
    watcher = sub.add_parser("watch", help="poll the supervisor state and push on change")
    watcher.add_argument("--interval", type=int, default=60)
    sub.add_parser("status", help="print the safe projection without sending anything")
    args = parser.parse_args(argv)
    load_env()

    if args.command == "chat-id":
        found = discover_chat_id()
        print(found if found is not None
              else "no messages yet -- say anything to the bot, then re-run")
        return 0
    if args.command == "status":
        print(json.dumps(read_once(), indent=2))
        return 0
    if args.command == "test":
        print("sent" if send(args.text) else "telegram rejected the message")
        return 0
    if args.command == "say":
        text = f"[{args.seat}] {args.text}" if args.seat else args.text
        print("sent" if send(text) else "telegram rejected the message")
        return 0
    if args.command == "commit":
        # Subject line ONLY, never the body. Commit bodies here quote log lines, argv and error
        # text -- exactly the places a credential travels -- and a hook that forwarded them would
        # publish one the first time somebody pasted a failing command into a message.
        who = f"[{args.seat}] " if args.seat else ""
        print("sent" if send(f"{who}commit {args.sha[:8]}\n{args.subject}")
              else "telegram rejected the message")
        return 0
    watch(interval=args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
