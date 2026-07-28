#!/usr/bin/env python3
"""Supervise bounded, sequential Codex↔Claude CLI handoffs in tmux."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".autonomy"
STATE = RUNTIME / "state.json"
STOP = RUNTIME / "STOP"
PAUSE = RUNTIME / "PAUSE"
LOCK = RUNTIME / "loop.lock"
LOG = RUNTIME / "autonomy.log"
ACTIVE_PID = RUNTIME / "active.pid"
INBOX = RUNTIME / "inbox"
ARCHIVE = RUNTIME / "inbox-archive"
SCHEMA = ROOT / "config" / "autonomy_result.schema.json"
SESSION = "meme-autonomy"
SEQ_RE = re.compile(r"^- \*\*Seq:\*\* (\d+)\s*$", re.MULTILINE)
STATUSES = {"handoff", "user_required", "blocked", "complete"}


def write_state(**values):
    RUNTIME.mkdir(exist_ok=True)
    current = {}
    if STATE.exists():
        try:
            current = json.loads(STATE.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    current.update(values, updated_at=int(time.time()))
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, STATE)


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if Path(f"/proc/{pid}/stat").exists():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # A managed caller may be unable to signal a process outside its sandbox namespace.
        return Path(f"/proc/{pid}").exists()
    return True


def status_payload():
    if not STATE.exists():
        return {"status": "never_started"}
    try:
        value = json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "invalid_state", "reason": str(error)}
    if value.get("status") in {"running", "paused"}:
        # Legacy state used `pid`, which may be stale and later reused by an unrelated process.
        # New supervisors always publish the explicit field below.
        pid = value.get("supervisor_pid")
        if not process_alive(pid):
            value["status"] = "stale"
            value["reason"] = f"recorded supervisor pid {pid!r} is not alive"
    return value


def latest_sequence():
    discussion = (ROOT / "agent_discussion.md").read_text()
    values = [int(value) for value in SEQ_RE.findall(discussion)]
    return max(values, default=0)


def pending_messages():
    INBOX.mkdir(parents=True, exist_ok=True)
    messages = []
    for path in sorted(INBOX.glob("*.json")):
        try:
            value = json.loads(path.read_text())
            messages.append((path, value["message"]))
        except (OSError, KeyError, json.JSONDecodeError):
            continue
    return messages


def archive_messages(messages):
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    for path, _ in messages:
        if path.exists():
            os.replace(path, ARCHIVE / path.name)


def prompt(agent, turn, sequence, owner_messages=()):
    other = "claude" if agent == "codex" else "codex"
    owner_block = ""
    if owner_messages:
        rendered = "\n".join(f"- {message}" for _, message in owner_messages)
        owner_block = f"""

The owner queued these instructions after the previous turn. Treat them as current user requests,
subject to AGENTS.md and the hard gates below:
{rendered}
"""
    return f"""You are the {agent} CLI in bounded autonomous collaboration with {other}.
Work in {ROOT}. This is autonomous turn {turn}; latest handoff sequence before your turn is {sequence}.
{owner_block}

Read AGENTS.md, PLAN.md, DOCUMENTATION.md, DECISIONS.md, and the latest relevant entries in
agent_discussion.md before acting. Check the working tree and existing code. Continue the concrete
requested action from the latest handoff. Prefer completing one bounded, testable task over planning.
Record ownership before editing and append a release/handoff entry after verification. Never edit or
rewrite prior agent_discussion.md entries.

Hard stop: return user_required before wallet creation/import, private keys, signing, transaction
submission, funding, spending, paid services, deployment, actions outside this repository,
live/devnet execution, destructive actions, or a material scope/architecture choice lacking recorded
authority. Do not expose or persist secrets. Existing ignored .env credentials may only support
already-authorized read-only RPC research and must never be printed or copied into prompts, logs,
commands, or artifacts. Obey all PLAN.md promotion gates.

If useful safe work remains, perform it and return status=handoff with next_agent={other}. If a real
owner decision is required, return user_required with one concise question. If no meaningful progress
is possible, return blocked. Return complete only when the entire recorded project objective is met.
Your final response must match the provided JSON schema exactly."""


def command_for(agent, prompt_text, output):
    if agent == "codex":
        return ["codex", "exec", "-C", str(ROOT), "-s", "workspace-write",
                "-c", "sandbox_workspace_write.network_access=true",
                "--output-schema", str(SCHEMA), "-o", str(output), prompt_text]
    return ["claude", "-p", "--permission-mode", "auto", "--output-format", "json",
            "--json-schema", SCHEMA.read_text(), prompt_text]


def run_agent(agent, command, live_log, timeout=3600):
    """Run one agent in its own process group and stream combined output to its live log."""
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, bufsize=1, start_new_session=True)
    ACTIVE_PID.write_text(str(process.pid) + "\n")
    chunks = []
    try:
        with live_log.open("a", encoding="utf-8", buffering=1) as handle:
            handle.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {agent} turn ===\n")
            while True:
                if time.monotonic() - started > timeout:
                    os.killpg(process.pid, signal.SIGINT)
                    raise TimeoutError(f"{agent} turn exceeded {timeout}s")
                line = process.stdout.readline()
                if line:
                    chunks.append(line)
                    handle.write(line)
                    continue
                if process.poll() is not None:
                    break
                time.sleep(0.1)
        return subprocess.CompletedProcess(command, process.wait(), "".join(chunks), None)
    finally:
        ACTIVE_PID.unlink(missing_ok=True)


def parse_result(agent, completed, output):
    if agent == "codex":
        raw = output.read_text() if output.exists() else completed.stdout
        return json.loads(raw)
    envelope = json.loads(completed.stdout)
    value = envelope.get("structured_output", envelope.get("result", envelope))
    if isinstance(value, str):
        value = json.loads(value)
    return value


def validate_result(value, agent):
    if not isinstance(value, dict) or value.get("status") not in STATUSES:
        raise ValueError("agent returned an invalid status payload")
    expected = "claude" if agent == "codex" else "codex"
    if value["status"] == "handoff" and value.get("next_agent") != expected:
        raise ValueError(f"handoff must target {expected}")
    return value


def run_loop(first, max_turns):
    RUNTIME.mkdir(exist_ok=True)
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another autonomy supervisor already holds the lock")
        STOP.unlink(missing_ok=True)
        agent, no_progress = first, 0
        write_state(status="running", active_agent=agent, turn=0, supervisor_pid=os.getpid(),
                    reason="")
        try:
            for turn in range(1, max_turns + 1):
                while PAUSE.exists() and not STOP.exists():
                    write_state(status="paused", active_agent=agent, turn=turn)
                    time.sleep(0.5)
                if STOP.exists():
                    write_state(status="stopped", reason="stop requested", turn=turn - 1)
                    return 0
                before = latest_sequence()
                output = RUNTIME / f"turn-{turn:04d}-{agent}.json"
                messages = pending_messages()
                live_log = RUNTIME / f"{agent}.live.log"
                write_state(status="running", active_agent=agent, turn=turn,
                            sequence_before=before, reason="")
                completed = run_agent(
                    agent, command_for(agent, prompt(agent, turn, before, messages), output), live_log)
                try:
                    result = validate_result(parse_result(agent, completed, output), agent)
                except Exception as error:  # noqa: BLE001
                    write_state(status="blocked", active_agent=agent, turn=turn,
                                reason=f"invalid agent result: {type(error).__name__}: {error}",
                                process_exit_code=completed.returncode)
                    return 2
                archive_messages(messages)
                after = latest_sequence()
                no_progress = no_progress + 1 if after <= before else 0
                write_state(status=result["status"], active_agent=agent, turn=turn,
                            sequence_before=before, sequence_after=after, result=result,
                            process_exit_code=completed.returncode)
                print(f"turn={turn} agent={agent} status={result['status']} seq={before}->{after}",
                      flush=True)
                if completed.returncode or result["status"] != "handoff":
                    return completed.returncode or 0
                if no_progress >= 2:
                    write_state(status="blocked", reason="two handoffs without a new discussion entry")
                    return 2
                agent = result["next_agent"]
            write_state(status="stopped", reason=f"max-turns circuit breaker ({max_turns})")
            return 0
        except KeyboardInterrupt:
            write_state(status="interrupted", reason="supervisor interrupted")
            return 130
        except Exception as error:  # noqa: BLE001
            write_state(status="blocked", reason=f"supervisor error: {type(error).__name__}: {error}")
            return 2
        finally:
            ACTIVE_PID.unlink(missing_ok=True)


def tmux_start(first, max_turns):
    RUNTIME.mkdir(exist_ok=True)
    for path in (RUNTIME / "codex.live.log", RUNTIME / "claude.live.log"):
        path.touch(exist_ok=True)
    exists = subprocess.run(["tmux", "has-session", "-t", SESSION],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode == 0
    if not exists:
        subprocess.run(["tmux", "new-session", "-d", "-s", SESSION, "-c", str(ROOT),
                        "-n", "control"], check=True)
    windows = subprocess.check_output(
        ["tmux", "list-windows", "-t", SESSION, "-F", "#{window_name}"], text=True).splitlines()
    if "control" not in windows:
        first_index = subprocess.check_output(
            ["tmux", "list-windows", "-t", SESSION, "-F", "#{window_index}"],
            text=True).splitlines()[0]
        subprocess.run(["tmux", "rename-window", "-t", f"{SESSION}:{first_index}",
                        "control"], check=True)
        windows[0] = "control"
    if "codex-log" not in windows:
        subprocess.run(["tmux", "new-window", "-d", "-t", SESSION, "-n", "codex-log",
                        "tail", "-n", "100", "-F", str(RUNTIME / "codex.live.log")], check=True)
    if "claude-log" not in windows:
        subprocess.run(["tmux", "new-window", "-d", "-t", SESSION, "-n", "claude-log",
                        "tail", "-n", "100", "-F", str(RUNTIME / "claude.live.log")], check=True)
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--first", first,
               "--max-turns", str(max_turns)]
    shell_command = " ".join(shlex.quote(part) for part in command) + \
        " >>" + shlex.quote(str(LOG)) + " 2>&1"
    if status_payload().get("status") not in {"running", "paused"}:
        pane = subprocess.check_output([
            "tmux", "split-window", "-d", "-P", "-F", "#{pane_id}",
            "-t", f"{SESSION}:control", "-l", "3", shell_command], text=True).strip()
        subprocess.run(["tmux", "select-pane", "-t", pane, "-T", "supervisor"], check=True)
        subprocess.run(["tmux", "set-option", "-p", "-t", pane, "remain-on-exit", "on"],
                       check=True)
    subprocess.run(["tmux", "select-window", "-t", f"{SESSION}:control"], check=True)
    print(f"started {SESSION}: windows control, codex-log, claude-log; log={LOG}")


def control_message(message):
    INBOX.mkdir(parents=True, exist_ok=True)
    destination = INBOX / f"{time.time_ns()}-{uuid.uuid4().hex}.json"
    destination.write_text(json.dumps({"created_at": int(time.time()), "message": message}) + "\n")
    print("message queued for the next agent turn")


def interrupt_active():
    if not ACTIVE_PID.exists():
        print("no active agent process")
        return 1
    pid = int(ACTIVE_PID.read_text().strip())
    try:
        os.killpg(pid, signal.SIGINT)
    except ProcessLookupError:
        ACTIVE_PID.unlink(missing_ok=True)
        print("active process had already exited")
        return 1
    print(f"interrupt sent to active agent process group {pid}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "run"):
        item = sub.add_parser(name)
        item.add_argument("--first", choices=("codex", "claude"), default="claude")
        item.add_argument("--max-turns", type=int, default=20)
    sub.add_parser("status")
    sub.add_parser("stop")
    sub.add_parser("pause")
    sub.add_parser("resume")
    message_parser = sub.add_parser("message")
    message_parser.add_argument("message", nargs="+", help="instruction for the next agent turn")
    sub.add_parser("interrupt")
    args = parser.parse_args()
    if args.command == "start":
        tmux_start(args.first, args.max_turns)
        return 0
    if args.command == "run":
        return run_loop(args.first, args.max_turns)
    if args.command == "status":
        print(json.dumps(status_payload(), indent=2, sort_keys=True))
        return 0
    if args.command == "pause":
        RUNTIME.mkdir(exist_ok=True); PAUSE.touch()
        print("pause requested; it takes effect between agent turns")
        return 0
    if args.command == "resume":
        PAUSE.unlink(missing_ok=True)
        print("supervisor resumed")
        return 0
    if args.command == "message":
        control_message(" ".join(args.message))
        return 0
    if args.command == "interrupt":
        return interrupt_active()
    RUNTIME.mkdir(exist_ok=True)
    STOP.touch()
    print("stop requested; supervisor will stop between agent turns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
