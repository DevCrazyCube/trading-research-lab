#!/usr/bin/env python3
"""Manage a tmux dashboard containing two sequential Claude CLIs."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".autonomy" / "interactive"
STATE = RUNTIME / "state.json"
LOG = RUNTIME / "supervisor.log"
STOP = RUNTIME / "STOP"
SESSION = "meme-agents"
DISCUSSION = ROOT / "agent_discussion.md"
# A Seq line may carry a trailing note, and every collision fix in the log does:
#   - **Seq:** 94  _(collision fix: appended as a duplicate Seq 84 ...)_
# Requiring end-of-line straight after the digits made all six such entries invisible to the
# parser, so `all_sequences()` under-reported, `duplicate_sequences()` could not see a duplicated
# renumber, and the log half of `next_sequence()`'s `max(log, counter)` missed the log's true
# maximum. The note must be separated from the digits by whitespace, so `84x` still fails to
# match rather than silently parsing as 84.
SEQ_RE = re.compile(r"^- \*\*Seq:\*\* (\d+)(?:\s+.*)?$", re.MULTILINE)
AGENTS = ("claude1", "claude2")


def tmux(*args, capture=False, check=True):
    result = subprocess.run(["tmux", *args], text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or f"tmux {' '.join(args)} failed")
    return result.stdout.strip() if capture else result.returncode


def has_session():
    return tmux("has-session", "-t", SESSION, check=False) == 0


def pane_id(title):
    state = read_state()
    stored = state.get("panes", {}).get(title)
    if stored:
        return stored
    rows = tmux("list-panes", "-t", SESSION, "-F",
                "#{pane_id}\t#{pane_title}", capture=True)
    for row in rows.splitlines():
        pane, pane_title = row.split("\t", 1)
        if pane_title == title:
            return pane
    raise RuntimeError(f"dashboard pane {title!r} not found")


def read_state():
    if not STATE.exists():
        return {"mode": "manual", "owner": "none", "status": "not_started"}
    try:
        return json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"mode": "manual", "owner": "none", "status": "invalid_state"}


def write_state(**updates):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    state = read_state()
    state.update(updates, updated_at=int(time.time()))
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, STATE)


SHELLS = ("zsh", "bash", "sh", "dash", "fish")


def pane_command(pane):
    """Current foreground command in a pane, or "" if the pane is gone."""
    return tmux("display-message", "-p", "-t", pane, "#{pane_current_command}",
                capture=True, check=False) or ""


def pane_text(pane):
    """Visible pane contents, or "" if the pane is gone."""
    return tmux("capture-pane", "-p", "-t", pane, capture=True, check=False) or ""


def wait_for_pane(pane, ready, description, timeout=90.0, poll=0.25):
    """Block until `ready(command, text)` holds for a pane, or fail loudly.

    `tmux send-keys` is fire-and-forget: it exits 0 as soon as the pane exists and says nothing
    about whether anything was listening. Typing into a pane whose shell has not finished
    initialising its line editor loses the leading characters — `supervisor.log` holds exactly
    that, a `d/usr/bin/python` line whose head was eaten. Fixed sleeps only make the window
    smaller; they cannot close it, and a 1s sleep before a Claude process that takes many
    seconds to boot is not even close.

    On timeout this raises. Returning anyway would put us back to typing into a pane that is not
    listening, which is the failure being fixed.
    """
    deadline = time.monotonic() + timeout
    while True:
        command = pane_command(pane)
        if not command:
            raise RuntimeError(f"pane {pane} is gone while waiting for {description}")
        if ready(command, pane_text(pane)):
            return command
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"pane {pane} did not become ready for {description} within {timeout:.0f}s "
                f"(current command {command!r}); refusing to send keys into a pane that is "
                f"not listening")
        time.sleep(poll)


def wait_for_shell(pane, timeout=30.0, poll=0.25):
    """Wait until a pane holds a shell that has drawn a prompt.

    A shell appears in `pane_current_command` the moment it is forked, well before it can accept
    input, so the command alone is not evidence of readiness. Non-empty pane content means the
    prompt has actually been written.
    """
    return wait_for_pane(
        pane, lambda command, text: command.lower() in SHELLS and text.strip() != "",
        "a shell prompt", timeout=timeout, poll=poll)


def wait_for_app(pane, timeout=90.0, poll=0.25):
    """Wait until a pane is running something other than a shell.

    Used after typing a launch command: the application has replaced the shell only once
    `pane_current_command` stops naming a shell. Until then, anything typed lands in the shell.
    """
    return wait_for_pane(
        pane, lambda command, text: command.lower() not in SHELLS,
        "an application to replace the shell", timeout=timeout, poll=poll)


def send_line(pane, text):
    """Type one line into a pane. Callers must have established readiness first."""
    tmux("send-keys", "-t", pane, "-l", text)
    tmux("send-keys", "-t", pane, "Enter")


def send(agent, message):
    """Deliver a message to an agent pane, refusing to send into the wrong target.

    `tmux send-keys` exits 0 whenever the pane exists; it says nothing about whether the
    receiving application consumed the keystrokes. The previous version recorded
    `last_target`/`last_message_at` unconditionally, so a message typed into a bare shell — or
    into a pane whose agent had exited — was indistinguishable in state from a delivered handoff.
    `supervisor.log` contains evidence of exactly that class of failure: a mangled
    `d/usr/bin/python` line, i.e. shell text that arrived with its leading characters missing.

    A shell prompt in an agent pane means the agent is not running, so sending would type the
    handoff into a shell instead of delivering it. That fails closed here rather than being
    recorded as a successful dispatch.
    """
    if agent not in AGENTS:
        raise ValueError(agent)
    target = pane_id(agent)
    command = pane_command(target)
    if not command:
        raise RuntimeError(f"pane {target} for {agent!r} is gone; refusing to send")
    if command.lower() in SHELLS:
        raise RuntimeError(
            f"pane {target} for {agent!r} is at a {command!r} prompt, not running an agent; "
            f"refusing to send a handoff into a shell")
    tmux("send-keys", "-t", target, "-l", message)
    tmux("send-keys", "-t", target, "Enter")
    write_state(last_target=agent, last_message_at=int(time.time()),
                last_send_pane_command=command)


def send_handoff(agent, message):
    """Interrupt stale UI work, then deliver a handoff into a clean turn."""
    target = pane_id(agent)
    tmux("send-keys", "-t", target, "C-c")
    time.sleep(0.25)
    send(agent, message)


def interrupt(agent):
    tmux("send-keys", "-t", pane_id(agent), "C-c")
    print(f"interrupt sent to {agent}")


def latest_entry():
    text = DISCUSSION.read_text()
    matches = list(SEQ_RE.finditer(text))
    if not matches:
        return 0, ""
    match = matches[-1]
    # Slice from the "## ..." heading above this Seq line, not from the Seq line itself.
    # The author name lives only in the heading, and handoff routing needs it; slicing from
    # the Seq line excluded it, which made author detection structurally unreachable.
    start = text.rfind("\n## ", 0, match.start())
    start = 0 if start < 0 else start + 1
    return int(match.group(1)), text[start:]


SEQ_LOCK = RUNTIME / "seq.lock"
SEQ_COUNTER = RUNTIME / "seq.counter"


def all_sequences(text=None):
    """Every Seq value in the log, in file order (duplicates preserved)."""
    if text is None:
        text = DISCUSSION.read_text()
    return [int(m.group(1)) for m in SEQ_RE.finditer(text)]


def duplicate_sequences(text=None):
    """Seq values used more than once, ascending.

    Duplicates do not break dispatch — `latest_entry()` takes the last match in file order, not
    the maximum — which is exactly why four collisions accumulated in one session before anyone
    noticed. Detection has to be explicit or it does not happen.
    """
    seen, dupes = set(), set()
    for value in all_sequences(text):
        (dupes if value in seen else seen).add(value)
    return sorted(dupes)


def next_sequence(timeout=10.0, poll=0.05):
    """Reserve the next free Seq atomically and **durably**.

    Serialising the read alone is not enough, and this is the subtle part. Two agents can each
    acquire the lock in turn, both read the same log — because neither has appended yet — and
    both be handed the same number. Writing an entry is not instantaneous, and an agent may
    compose for minutes between allocating and appending.

    So the allocation is persisted to a counter the moment it is made. The reserved value is
    `max(highest in log, highest previously allocated) + 1`, which means a number handed out but
    not yet appended is still consumed. The counter never regresses; the log is still consulted
    so a hand-written entry cannot be overwritten.

    Returns the reserved Seq. The lock is always released, including on error.
    """
    RUNTIME.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(SEQ_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"could not acquire {SEQ_LOCK} within {timeout}s; another allocation is in "
                    f"flight or a stale lock needs removing") from None
            time.sleep(poll)
    try:
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        used = all_sequences()
        highest_logged = max(used) if used else 0
        try:
            highest_allocated = int(SEQ_COUNTER.read_text().strip())
        except (OSError, ValueError):
            highest_allocated = 0
        reserved = max(highest_logged, highest_allocated) + 1
        temporary = SEQ_COUNTER.with_suffix(".tmp")
        temporary.write_text(f"{reserved}\n")
        os.replace(temporary, SEQ_COUNTER)   # durable before the lock is released
        return reserved
    finally:
        try:
            os.unlink(SEQ_LOCK)
        except FileNotFoundError:
            pass


def entry_author(entry):
    """Author field from a '## <date> - <Author> - <subject>' heading, lowercased.

    Returns "" when there is no heading or the author field cannot be isolated. Failing closed
    matters: the previous implementation fell back to scanning the whole entry body for an agent
    name, so routing depended on whether the author happened to mention themselves in prose, and
    a heading whose *subject* named another agent could be misrouted.
    """
    heading = next((line for line in entry.splitlines() if line.startswith("## ")), "")
    parts = [part.strip() for part in heading[3:].split("—")]
    return parts[1].lower() if len(parts) >= 2 else ""


def handoff_target(entry, active_agent=None):
    status_line = next((line.lower() for line in entry.splitlines()
                        if line.startswith("- **Status:**")), "")
    if not any(word in status_line for word in ("handoff", "released", "complete")):
        return None
    if "claude" in entry_author(entry):
        # Claude 1 and Claude 2 are deliberately sequential. Route a released
        # entry to the other terminal, never to the terminal that just released.
        return "claude2" if active_agent == "claude1" else "claude1"
    return None


def supervisor_loop(interval=2.0):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    STOP.unlink(missing_ok=True)
    sequence, _ = latest_entry()
    # Preserve the persisted cursor across supervisor restarts. Initializing to the
    # current latest sequence would silently skip a handoff written while the
    # supervisor was down (the exact failure mode seen after Seq 71).
    persisted = read_state().get("observed_sequence")
    baseline = persisted if isinstance(persisted, int) else sequence
    write_state(status="running", supervisor_pid=os.getpid(), observed_sequence=baseline)
    try:
        while not STOP.exists():
            state = read_state()
            current, entry = latest_entry()
            # Surface Seq collisions loudly. They do not break dispatch, because latest_entry()
            # takes the last match in file order rather than the maximum — which is precisely why
            # four accumulated in one session unnoticed. Report on change only, so the log does
            # not fill with repeats of a known condition.
            dupes = duplicate_sequences()
            if dupes != state.get("duplicate_sequences"):
                write_state(duplicate_sequences=dupes)
                if dupes:
                    print(f"WARNING duplicate Seq values in agent_discussion.md: {dupes}",
                          flush=True)
            if state.get("mode") == "auto" and current > state.get("observed_sequence", 0):
                target = handoff_target(entry, state.get("active_agent"))
                if target:
                    message = ("Read the latest handoff in agent_discussion.md, follow AGENTS.md, "
                               "claim ownership, perform the requested bounded task, verify it, "
                               "then append a release/handoff entry. Stop for genuine user gates.")
                    source = state.get("active_agent")
                    if source in AGENTS and source != target:
                        tmux("send-keys", "-t", pane_id(source), "C-c")
                    send_handoff(target, message)
                    write_state(active_agent=target, owner=target, observed_sequence=current)
                else:
                    write_state(observed_sequence=current)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        write_state(status="stopped", supervisor_pid=None)


def start(first):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if has_session():
        raise RuntimeError(f"tmux session {SESSION!r} already exists")
    tmux("new-session", "-d", "-s", SESSION, "-c", str(ROOT), "-n", "agents",
         "zsh")
    claude1 = tmux("display-message", "-p", "-t", f"{SESSION}:agents",
                   "#{pane_id}", capture=True)
    tmux("select-pane", "-t", claude1, "-T", "claude1")
    claude2 = tmux("split-window", "-d", "-h", "-p", "50", "-P", "-F", "#{pane_id}",
                  "-t", f"{SESSION}:agents", "-c", str(ROOT), "zsh", capture=True)
    tmux("select-pane", "-t", claude2, "-T", "claude2")
    control = tmux("split-window", "-d", "-v", "-f", "-p", "22", "-P", "-F", "#{pane_id}",
                   "-t", f"{SESSION}:agents", "-c", str(ROOT), "zsh", capture=True)
    tmux("select-pane", "-t", control, "-T", "control")
    tmux("set-option", "-t", SESSION, "mouse", "on")
    tmux("set-option", "-t", SESSION, "pane-border-status", "top")
    tmux("set-option", "-t", SESSION, "pane-border-format",
         " #[bold]#{pane_title}#[default] ")
    tmux("set-option", "-t", SESSION, "status-left",
         "#[bold] meme-agents #[default]")
    write_state(mode="manual", owner="none", status="starting", observed_sequence=latest_entry()[0],
                panes={"claude1": claude1, "claude2": claude2, "control": control},
                active_agent=None)
    supervisor = (f"{sys.executable} {Path(__file__).resolve()} run "
                  f">>{LOG} 2>&1 &")
    # Wait for the prompt before typing. Sending immediately after `new-session` is what put the
    # mangled `d/usr/bin/python` line in supervisor.log.
    wait_for_shell(control)
    send_line(control, supervisor)
    claude_command = "claude -c --permission-mode auto"
    for pane, identity in ((claude1, "Claude 1"), (claude2, "Claude 2")):
        wait_for_shell(pane)
        send_line(pane, claude_command)
        # The identity prompt used to be typed immediately after the launch command, while
        # Claude was still booting, so it landed in the shell or was partly swallowed.
        wait_for_app(pane)
        send_line(
            pane,
            f"You are {identity}. Work sequentially: edit only when explicitly handed ownership, use maximum available effort, and record a handoff in agent_discussion.md when done.")
    tmux("select-pane", "-t", control)
    if first:
        # Previously a fixed 1s sleep, then `send()` - whose Seq-73 guard refuses a pane still at
        # a shell prompt. Claude takes far longer than 1s to boot, so this path reliably raised
        # "refusing to send a handoff into a shell": the guard was right and the caller was wrong.
        wait_for_app(pane_id(first))
        send(first, "Read AGENTS.md and agent_discussion.md, then continue the latest active handoff."
                    " Preserve ownership rules and stop for genuine user gates.")
    print(f"started interactive dashboard: tmux attach -t {SESSION}")


def upgrade_existing():
    """Convert an older codex/claude dashboard in place, preserving the session."""
    if not has_session():
        raise RuntimeError(f"tmux session {SESSION!r} does not exist; use start")
    rows = tmux("list-panes", "-t", SESSION,
                "-F", "#{pane_id}\t#{pane_title}\t#{pane_current_command}", capture=True)
    panes = {}
    rows_by_pane = {}
    for row in rows.splitlines():
        pane, title, command = row.split("\t", 2)
        panes[title] = pane
        rows_by_pane[pane] = (title, command)
    claude1 = panes.get("claude1") or panes.get("claude")
    claude2 = panes.get("claude2") or panes.get("codex")
    control = panes.get("control")
    if not (claude1 and claude2):
        live = [pane for pane, (title, command) in rows_by_pane.items()
                if pane != control and command == "claude"]
        if len(live) >= 2:
            claude1, claude2 = sorted(live)[:2]
    if not all((claude1, claude2, control)):
        raise RuntimeError("expected claude/codex/control panes in existing dashboard")
    tmux("select-pane", "-t", claude1, "-T", "claude1")
    tmux("select-pane", "-t", claude2, "-T", "claude2")
    if rows_by_pane.get(claude2, ("", ""))[1] != "claude":
        tmux("respawn-pane", "-k", "-t", claude2, "-c", str(ROOT), "zsh")
        # Same race as start(): a respawned pane's shell is not ready the instant tmux returns.
        wait_for_shell(claude2)
        send_line(claude2, "claude -c --permission-mode auto")
        wait_for_app(claude2)
        send_line(
            claude2,
            "You are Claude 2. Work sequentially: edit only when explicitly handed ownership, use maximum available effort, and record a handoff in agent_discussion.md when done.")
    STOP.touch()
    time.sleep(0.3)
    write_state(mode="manual", owner="none", active_agent=None, status="starting",
                observed_sequence=latest_entry()[0],
                panes={"claude1": claude1, "claude2": claude2, "control": control})
    supervisor = f"{sys.executable} {Path(__file__).resolve()} run >>{LOG} 2>&1 &"
    tmux("send-keys", "-t", control, "-l", supervisor)
    tmux("send-keys", "-t", control, "Enter")
    tmux("select-pane", "-t", control)
    print("upgraded existing dashboard to claude1 + claude2")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    start_parser = sub.add_parser("start")
    start_parser.add_argument("--first", choices=AGENTS, default="claude1")
    sub.add_parser("upgrade")
    sub.add_parser("run")
    sub.add_parser("status")
    take = sub.add_parser("take"); take.add_argument("agent", choices=AGENTS)
    sub.add_parser("release")
    sub.add_parser("auto")
    sub.add_parser("pause")
    message = sub.add_parser("send"); message.add_argument("agent", choices=AGENTS); message.add_argument("message", nargs="+")
    interrupt_parser = sub.add_parser("interrupt"); interrupt_parser.add_argument("agent", choices=AGENTS)
    sub.add_parser("stop")
    sub.add_parser("next-seq")    # atomic Seq allocation for agents appending entries
    sub.add_parser("check-seq")   # report duplicate Seq values; nonzero exit if any
    args = parser.parse_args()
    if args.command == "start": start(args.first)
    elif args.command == "upgrade": upgrade_existing()
    elif args.command == "run": supervisor_loop()
    elif args.command == "status": print(json.dumps(read_state(), indent=2, sort_keys=True))
    elif args.command == "take":
        write_state(mode="manual", owner=args.agent, active_agent=args.agent); tmux("select-pane", "-t", pane_id(args.agent)); print(f"manual control: {args.agent}")
    elif args.command == "release": write_state(mode="manual", owner="none", active_agent=None); print("manual control released")
    elif args.command == "auto": write_state(mode="auto", owner="supervisor"); print("automatic handoffs enabled")
    elif args.command == "pause": write_state(mode="manual", owner="none"); print("automatic handoffs paused")
    elif args.command == "send": send(args.agent, " ".join(args.message))
    elif args.command == "interrupt": interrupt(args.agent)
    elif args.command == "next-seq": print(next_sequence())
    elif args.command == "check-seq":
        dupes = duplicate_sequences()
        print(json.dumps({"duplicate_sequences": dupes,
                          "total_entries": len(all_sequences())}, sort_keys=True))
        return 1 if dupes else 0
    else:
        STOP.touch(); write_state(mode="manual", owner="none"); print("interactive supervisor stop requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
