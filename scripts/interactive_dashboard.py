#!/usr/bin/env python3
"""Manage a tmux dashboard containing one Codex CLI and one Claude CLI."""
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
AGENTS = ("codex", "claude")
AGENT_COMMANDS = {
    "claude": "claude --permission-mode auto --effort max --name claude",
}
AGENT_IDENTITIES = {
    "codex": "You are Codex",
    "claude": "You are Claude",
}


def tmux(*args, capture=False, check=True):
    result = subprocess.run(["tmux", *args], text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or f"tmux {' '.join(args)} failed")
    return result.stdout.strip() if capture else result.returncode


def has_session():
    return tmux("has-session", "-t", SESSION, check=False) == 0


AGENT_TAG = "@agent"     # per-pane tmux user option: the one identity the TUI cannot overwrite


def tag_pane(pane, name):
    """Bind an agent name to a pane durably.

    `pane_title` cannot carry this. The dashboard used to set it with `select-pane -T`, but the
    Claude Code TUI *owns* that field and overwrites it with the agent's current activity — the
    live panes read `Read all markdown files`, not `claude1`/`claude2`. A tmux **user option** is
    per-pane, survives the application writing anything it likes, and dies with the pane.
    """
    tmux("set-option", "-p", "-t", pane, AGENT_TAG, name)


def pane_agent(pane):
    """The agent name bound to `pane`, or "" if it carries no tag."""
    return tmux("show-options", "-p", "-t", pane, "-v", AGENT_TAG,
                capture=True, check=False) or ""


def live_panes():
    """Pane ids in the dashboard session, or [] if they cannot be listed."""
    rows = tmux("list-panes", "-t", SESSION, "-F", "#{pane_id}", capture=True, check=False)
    return rows.split() if rows else []


def tagged_panes():
    """{agent name: pane id} for every pane carrying a tag.

    Fail-soft: an unreadable pane list yields {} and resolution falls through to the stored map,
    which is then validated. Raising here would make a transient tmux hiccup look like a missing
    dashboard. It cannot reintroduce the Seq-171 defect, because the stored-map path still refuses
    a pane whose tag names a different agent.
    """
    found = {}
    for pane in live_panes():
        name = pane_agent(pane)
        if name:
            if name not in (*AGENTS, "control"):
                raise RuntimeError(
                    f"pane {pane} carries unknown {AGENT_TAG} identity {name!r}; refusing to "
                    "route by an identity the dashboard does not recognise")
            if name in found:
                raise RuntimeError(
                    f"duplicate {AGENT_TAG} identity {name!r} on panes {found[name]} and "
                    f"{pane}; refusing to guess which occupant is authoritative")
            found[name] = pane
    return found


def pane_id(title):
    """Resolve an agent name to its pane, refusing rather than guessing.

    This function returned the wrong pane for hours and nothing noticed. It preferred a **stored**
    map and never revalidated it, and its fallback matched on `pane_title`, which the TUI
    overwrites. When the dashboard restarted and panes were recreated (%19/%20 -> %25/%26 ->
    %28/%29) the stored map bound `claude1` to Claude 2's own pane, so **every handoff one agent
    sent the other was typed into its own terminal.** Both panes run `claude` and both look alive,
    so every downstream check passed. See `agent_discussion.md` Seq 171.

    Order matters: the live tag wins over stored state, because the tag is a property of the pane
    that exists now and the stored map is a memory of one that may not. A stored id that disagrees
    with the tag is a **conflict, not a preference** - AGENTS.md forbids silently selecting the more
    convenient claim, and here the convenient claim is the stale one.
    """
    live = tagged_panes()
    if title in live:
        return live[title]

    stored = read_state().get("panes", {}).get(title)
    if stored:
        # Untagged (a dashboard from before tagging existed). Accept it only if the pane is real
        # and no *other* agent has claimed it, so a transposed map cannot survive contact.
        panes = live_panes()
        if panes and stored not in panes:
            raise RuntimeError(
                f"stored pane {stored} for {title!r} no longer exists. The map is stale; run "
                f"`upgrade` to re-tag the panes rather than trusting it.")
        owner = pane_agent(stored)
        if owner and owner != title:
            raise RuntimeError(
                f"stored map says {title!r} is pane {stored}, but that pane is tagged {owner!r}. "
                f"Refusing to send {title}'s handoff into {owner}'s terminal - this is the defect "
                f"that made both agents hand off to themselves. Run `upgrade` to re-tag.")
        return stored
    raise RuntimeError(
        f"dashboard pane {title!r} not found: no pane carries the {AGENT_TAG} tag and no stored "
        f"map entry exists. Run `upgrade` to tag the panes.")


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
SHELL_COMMAND = ("zsh", "-i")


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


def wait_for_app(pane, expected=None, timeout=90.0, poll=0.25):
    """Wait until a pane is running the expected agent application.

    Used after typing a launch command: the application has replaced the shell only once
    `pane_current_command` stops naming a shell. Until then, anything typed lands in the shell.
    """
    expected = expected.lower() if expected else None
    command = wait_for_pane(
        pane,
        lambda command, text: (command.lower() == expected if expected
                               else command.lower() not in SHELLS),
        f"the {expected or 'agent'} application to replace the shell",
        timeout=timeout, poll=poll)
    # Seeing the executable once only proves it started, not that it survived initialisation.
    # Codex can briefly replace the shell and then exit on a state-DB error; the old start path
    # sent its identity prompt into the returned shell and still reported success.
    time.sleep(0.5)
    current = pane_command(pane)
    if expected and current.lower() != expected:
        raise RuntimeError(
            f"{expected} started in pane {pane} but exited during initialisation "
            f"(current command {current!r}); refusing to report a working dashboard")
    return current or command


def agent_command(name):
    if name == "codex":
        return (f"codex --no-alt-screen -C {ROOT} "
                "-a never -s workspace-write "
                "-c sandbox_workspace_write.network_access=true "
                "-c check_for_update_on_startup=false")
    return AGENT_COMMANDS[name]


def send_line(pane, text):
    """Type one line into a pane. Callers must have established readiness first."""
    tmux("send-keys", "-t", pane, "-l", text)
    tmux("send-keys", "-t", pane, "Enter")


BUSY_MARKER = "esc to interrupt"
SUBMIT_POLL = 0.2          # TUI acceptance/redraw is asynchronous
SUBMIT_POLLS = 25          # five-second bounded post-condition window
PENDING_MATCH = 24         # prefix long enough to be ours, short enough to survive wrapping
INTERRUPT_TIMEOUT = 20.0
COMPOSER_PROMPTS = ("❯", "›")   # Claude Code, Codex — different applications, different glyphs
NBSP = " "                           # both TUIs pad the prompt with it


def agent_busy(pane):
    """True while the agent is mid-turn.

    Anchored on Claude Code's own status-line hint, which is present exactly while a turn is in
    flight and absent when the agent is waiting for input. Deliberately NOT the elapsed-timer
    pattern `(51s ...)`: that can appear in ordinary transcript text, and a check that matches
    something merely adjacent to the claim is the error this project has hit eight times.
    """
    return BUSY_MARKER in pane_text(pane)


def composer_text(pane):
    """Whatever is sitting unsent in the agent's input box, or "" when it is empty.

    Scanned from the BOTTOM. Both TUIs also echo *delivered* user messages into the transcript
    behind the same glyph, so the first match from the top is an old message, not the live
    composer. That inverted `send()`'s post-condition: a handoff that had actually landed read
    back as "still in the composer", `send()` raised, the supervisor left the Seq unconsumed and
    retried forever, pressing bare Enter into the pane each time. `supervisor.log` holds eleven
    identical "typed into pane %1 but NOT submitted" lines for one delivered message. The composer
    is the last such line by construction: the input box is at the bottom, the transcript above it.

    Both prompt glyphs are recognised because the two panes are no longer the same application.
    Claude Code draws `\u276f` and Codex draws `\u203a`. Matching only Claude's meant this returned
    "" for every Codex pane, so the post-condition there was not merely wrong, it was inert, and
    every send into Codex was recorded as delivered whether or not it was. A verification that
    cannot fail is the exact failure this function exists to detect.

    An empty Codex composer holds greyed placeholder text rather than nothing. That is harmless
    for the only caller, which asks whether a prefix of what sits here appears in the message it
    is trying to deliver; a placeholder never does.
    """
    return composer_text_from_text(pane_text(pane))


def wait_for_idle(pane, timeout=180.0, poll=0.5):
    """Block until the agent finishes its turn, so we never type into a busy composer.

    Returns True if the pane went idle, False on timeout. It does not raise: `send()` verifies
    delivery afterwards regardless, and that post-condition is what actually guarantees the
    handoff landed. This only avoids the failure; it is not what detects it.
    """
    deadline = time.monotonic() + timeout
    while agent_busy(pane):
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)
    return True


def wait_for_submission(pane, message, trust_busy_marker):
    """Wait for the draft to clear or the TUI to begin the submitted turn.

    Claude Code may leave submitted text visible in the composer for longer than one redraw. A
    one-shot 0.6 s read therefore reported accepted handoffs as pending.

    `trust_busy_marker` is the caller's observation that the pane was **idle immediately before
    submission**, and it is load-bearing. The busy marker only proves acceptance if it appeared
    *because of* our Enter; a marker that was already there proves nothing. Read level-triggered, it
    let a handoff typed into a still-busy pane — where `wait_for_idle` timed out and returned False
    without raising — return "accepted" on the first poll without ever reading the composer, and
    `send()` then recorded a delivery that had not happened. See Seq 214/216. After an idle-wait
    timeout, composer clearance is therefore the sole acceptance proof.
    """
    pending = ""
    for attempt in range(SUBMIT_POLLS):
        text = pane_text(pane)
        if trust_busy_marker and BUSY_MARKER in text:
            return True, ""
        pending = composer_text_from_text(text)
        if not pending or pending[:PENDING_MATCH] not in message:
            return True, pending
        if attempt + 1 < SUBMIT_POLLS:
            time.sleep(SUBMIT_POLL)
    return False, pending


def composer_text_from_text(text):
    """Parse composer content from one captured pane snapshot."""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        for prompt in COMPOSER_PROMPTS:
            if stripped.startswith(prompt):
                return stripped[len(prompt):].replace(NBSP, " ").strip()
    return ""


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
    # Assert the recipient, not merely that something was delivered. The old post-condition checked
    # that the composer emptied - which it did, because the text went somewhere real - and could not
    # tell whose terminal it went into. A delivery check that cannot identify the recipient is why
    # "Claude 1 is unresponsive" was diagnosed for hours while the messages were arriving here.
    bound = pane_agent(target)
    if bound and bound != agent:
        raise RuntimeError(
            f"refusing to send {agent!r}'s handoff into pane {target}, which is tagged {bound!r}")
    command = pane_command(target)
    if not command:
        raise RuntimeError(f"pane {target} for {agent!r} is gone; refusing to send")
    if command.lower() in SHELLS:
        raise RuntimeError(
            f"pane {target} for {agent!r} is at a {command!r} prompt, not running an agent; "
            f"refusing to send a handoff into a shell")
    # The other half of the Seq-27 guard. That one caught a pane running a *shell*; this catches a
    # pane running an *agent that is mid-turn*, where `pane_current_command` is `claude` either way.
    # Text typed then lands in the composer and the Enter is eaten by the running turn, so the
    # handoff sits as draft text until a human presses Enter. That is why the owner spent a day
    # relaying our messages by hand.
    idle = wait_for_idle(target)
    pending_before = composer_text(target)
    if not idle and not (pending_before and pending_before[:PENDING_MATCH] in message):
        raise RuntimeError(
            f"{agent!r} is still working in pane {target}; automatic routing will wait rather "
            "than interrupt the turn or type a draft into its active composer")
    if pending_before and pending_before[:PENDING_MATCH] in message:
        # A previous attempt reached the composer but the agent was still busy. Do not append a
        # duplicate; submit the existing draft once the pane is idle.
        if not idle:
            raise RuntimeError(
                f"handoff to {agent!r} is pending in pane {target}; waiting for the agent to go idle")
        tmux("send-keys", "-t", target, "Enter")
    else:
        tmux("send-keys", "-t", target, "-l", message)
        tmux("send-keys", "-t", target, "Enter")

    # Verify rather than assume. Acceptance and TUI redraw are asynchronous, so poll for either
    # composer clearance or the busy marker instead of declaring failure after one fixed sleep.
    submitted, pending = wait_for_submission(target, message, trust_busy_marker=idle)
    if not submitted:
        raise RuntimeError(
            f"handoff to {agent!r} was typed into pane {target} but NOT submitted — it is still "
            f"sitting in the composer ({pending[:60]!r}...). The agent was "
            f"{'busy past the wait timeout' if not idle else 'not consuming input'}. Not recording "
            f"a delivery that did not happen; retry when the pane is idle.")
    write_state(last_target=agent, last_message_at=int(time.time()),
                last_send_pane_command=command, last_send_waited_for_idle=idle)


def send_handoff(agent, message, interrupt_busy=True):
    """Interrupt stale UI work, then deliver a handoff into a clean turn.

    The interrupt is only issued when the agent is actually busy — C-c into an idle pane clears a
    composer the operator may be using. The flat `time.sleep(0.25)` that used to follow it was a
    fixed sleep against an unbounded wait, the same defect as the `start()` race: if the interrupt
    had not settled in 250 ms, the text went into a still-busy composer and was lost.

    `interrupt_busy=False` for an agent holding an open ownership claim. "Busy" cannot distinguish
    stale UI work from claimed work in flight, and the two deserve opposite treatment: destroying a
    colleague's in-flight measurement to deliver a message a few minutes sooner is the worse trade,
    and waiting costs nothing because an undelivered handoff already leaves the Seq unconsumed and
    retries. See `open_claim_holders`.
    """
    target = pane_id(agent)
    if interrupt_busy and agent_busy(target):
        tmux("send-keys", "-t", target, "C-c")
        wait_for_idle(target, timeout=INTERRUPT_TIMEOUT)
    send(agent, message)


def interrupt(agent):
    tmux("send-keys", "-t", pane_id(agent), "C-c")
    print(f"interrupt sent to {agent}")


def enable_auto():
    """Enable dispatch only when both tagged agent panes are genuinely running."""
    if not has_session():
        raise RuntimeError(f"tmux session {SESSION!r} does not exist")
    stopped = {agent: pane_command(pane_id(agent)) for agent in AGENTS}
    stopped = {agent: command for agent, command in stopped.items()
               if command.lower() != agent}
    if stopped:
        details = ", ".join(f"{agent}={command or 'gone'}" for agent, command in stopped.items())
        raise RuntimeError(
            f"automatic handoffs require both agents alive ({details}); launch the missing "
            "agent before enabling auto mode")
    write_state(mode="auto", owner="supervisor")
    print("automatic handoffs enabled: codex <-> claude")


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


def entry_status(entry):
    """The lowercased '- **Status:**' line of an entry, or "" when it has none."""
    return next((line.lower() for line in entry.splitlines()
                 if line.startswith("- **Status:**")), "")


RELEASE_WORDS = ("handoff", "released", "complete")
NO_ACTIONS = ("none", "no action", "nothing requested")


def entry_requested_action(entry):
    """A real requested action, or "" for audit-only/no-action entries."""
    line = next((line for line in entry.splitlines()
                 if line.startswith("- **Requested action:**")), "")
    action = line.split(":**", 1)[1].strip() if ":**" in line else ""
    if not action or any(action.lower().startswith(value) for value in NO_ACTIONS):
        return ""
    return action


def handoff_target(entry, active_agent=None):
    status_line = entry_status(entry)
    # Terminal releases and explicit cross-agent requests both need immediate pane delivery.
    # A claim/in-progress entry is audit state, not a task for the other agent, even if its prose
    # contains a future requested action.
    terminal = any(word in status_line for word in RELEASE_WORDS)
    explicit_request = (bool(entry_requested_action(entry))
                        and "claiming" not in status_line
                        and "in progress" not in status_line
                        and "implementation ownership" not in status_line)
    if not (terminal or explicit_request):
        return None
    author = entry_author(entry)
    if "codex" in author:
        return "claude"
    if "claude" in author:
        return "codex"
    return None


def handoff_message(entry, target):
    """Frame the released entry itself as the next agent's input.

    The log remains the audit record, but the receiver should not have to translate a generic
    "read the latest" instruction back into the actual work. Supplying the immutable entry also
    avoids a race where another entry is appended between detection and the receiver reading it.
    """
    sender = entry_author(entry) or "the other agent"
    return (
        f"Direct handoff from {sender} to {target}. The complete released handoff follows. "
        "Treat it as the task brief, verify its claims independently, follow AGENTS.md, claim "
        "ownership before editing, and append your own release when finished. Do not ask routine "
        "questions; make safe in-scope assumptions.\n\n"
        f"--- BEGIN HANDOFF ---\n{entry.rstrip()}\n--- END HANDOFF ---"
    )


def entry_blocks(text):
    """Every '## ' entry in the log, in file order."""
    starts = [m.start() for m in re.finditer(r"^## ", text, re.MULTILINE)]
    return [text[start:end] for start, end in zip(starts, starts[1:] + [len(text)])]


def open_claim_holders(text=None):
    """Agents whose most recent log entry claims ownership and has not released it.

    AGENTS.md makes an ownership claim binding until its author appends a release, but the
    supervisor only ever looked at the *latest* entry, so an open claim was invisible to it. That
    is what made the interrupt below destructive: routing is by author, so the moment either agent
    appends a release the other is handed work — and if that other agent is mid-run on something it
    claimed, `send_handoff` read "busy" as stale UI work and sent C-c into it. Seq 182 records the
    supervisor doing exactly this to a Claude pane; the rebuild changed the topology and kept the
    interrupt, so the same edge was live against a Codex pane holding an open B9b claim.

    Only each agent's own most recent entry counts, so a claim released later does not linger.
    "released" rather than "release" is deliberate: a claim reading "do not edit ... until I
    release" is an open claim describing its own future, not a closed one.
    """
    if text is None:
        text = DISCUSSION.read_text()
    holders, seen = set(), set()
    for block in reversed(entry_blocks(text)):
        author = entry_author(block)
        name = next((agent for agent in AGENTS if agent in author), None)
        if not name or name in seen:
            continue
        seen.add(name)
        status = entry_status(block)
        if "claim" in status and not any(word in status for word in RELEASE_WORDS):
            holders.add(name)
        if len(seen) == len(AGENTS):
            break
    return holders


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
    # A supervisor running in manual mode forwards nothing while reporting `status: running`.
    # Say so rather than leave it to whoever thinks to read the state file.
    if read_state().get("mode") != "auto":
        print("WARNING supervisor is running with automatic handoffs DISABLED (mode is not "
              "'auto'); no released entry will be dispatched until you run: "
              "python scripts/interactive_dashboard.py auto", flush=True)
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
                    message = handoff_message(entry, target)
                    # Automatic handoffs never interrupt either conversation. A bounded turn
                    # ends naturally; if the receiver is still working, leave the sequence
                    # unconsumed and retry after it becomes idle.
                    try:
                        send_handoff(target, message, interrupt_busy=False)
                    except RuntimeError as exc:
                        # A busy CLI is transient. Keep the sequence unconsumed so the next loop
                        # retries; never let one undeliverable handoff kill the supervisor.
                        print(f"handoff pending for {target}: {exc}", flush=True)
                    else:
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
         *SHELL_COMMAND)
    codex = tmux("display-message", "-p", "-t", f"{SESSION}:agents",
                   "#{pane_id}", capture=True)
    tmux("select-pane", "-t", codex, "-T", "codex")
    tag_pane(codex, "codex")
    claude = tmux("split-window", "-d", "-h", "-p", "50", "-P", "-F", "#{pane_id}",
                  "-t", f"{SESSION}:agents", "-c", str(ROOT), *SHELL_COMMAND, capture=True)
    tmux("select-pane", "-t", claude, "-T", "claude")
    tag_pane(claude, "claude")
    control = tmux("split-window", "-d", "-v", "-f", "-p", "22", "-P", "-F", "#{pane_id}",
                   "-t", f"{SESSION}:agents", "-c", str(ROOT), *SHELL_COMMAND, capture=True)
    tmux("select-pane", "-t", control, "-T", "control")
    tag_pane(control, "control")
    tmux("set-option", "-t", SESSION, "mouse", "on")
    tmux("set-option", "-t", SESSION, "pane-border-status", "top")
    tmux("set-option", "-t", SESSION, "pane-border-format",
         " #[bold]#{pane_title}#[default] ")
    tmux("set-option", "-t", SESSION, "status-left",
         "#[bold] meme-agents #[default]")
    write_state(mode="manual", owner="none", status="starting", observed_sequence=latest_entry()[0],
                panes={"codex": codex, "claude": claude, "control": control},
                active_agent=None)
    supervisor = (f"{sys.executable} {Path(__file__).resolve()} run "
                  f">>{LOG} 2>&1 &")
    # Wait for the prompt before typing. Sending immediately after `new-session` is what put the
    # mangled `d/usr/bin/python` line in supervisor.log.
    wait_for_shell(control)
    send_line(control, supervisor)
    for pane, name in ((codex, "codex"), (claude, "claude")):
        wait_for_shell(pane)
        send_line(pane, agent_command(name))
        # The identity prompt used to be typed immediately after the launch command, while
        # Claude was still booting, so it landed in the shell or was partly swallowed.
        wait_for_app(pane, name)
        send_line(
            pane,
            f"{AGENT_IDENTITIES[name]}. Work sequentially: edit only when explicitly handed "
            "ownership, follow AGENTS.md, and record a handoff in agent_discussion.md when done.")
    tmux("select-pane", "-t", control)
    if first:
        # Previously a fixed 1s sleep, then `send()` - whose Seq-73 guard refuses a pane still at
        # a shell prompt. Claude takes far longer than 1s to boot, so this path reliably raised
        # "refusing to send a handoff into a shell": the guard was right and the caller was wrong.
        wait_for_app(pane_id(first), first)
        send(first, "Read AGENTS.md and agent_discussion.md, then continue the latest active handoff."
                    " Preserve ownership rules and stop for genuine user gates.")
    print(f"started interactive dashboard: tmux attach -t {SESSION}")


def upgrade_existing():
    """Repair an explicitly identified Codex/Claude dashboard in place."""
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

    # A live per-pane tag is authoritative.  Titles are accepted only for a legacy, untagged
    # dashboard whose old names are still explicit.  Never assign two anonymous Claude panes by
    # pane id/order: that was the last remaining path by which an uncertain guess could be turned
    # into an authoritative tag and make both agents hand work back to themselves.
    tagged = {}
    for pane in rows_by_pane:
        name = pane_agent(pane)
        if not name:
            continue
        if name not in (*AGENTS, "control"):
            raise RuntimeError(
                f"pane {pane} carries unknown {AGENT_TAG} identity {name!r}; refusing upgrade")
        if name in tagged:
            raise RuntimeError(
                f"duplicate {AGENT_TAG} identity {name!r} on panes {tagged[name]} and {pane}; "
                "refusing upgrade")
        tagged[name] = pane

    codex = tagged.get("codex") or panes.get("codex")
    claude = tagged.get("claude") or panes.get("claude")
    control = tagged.get("control") or panes.get("control")
    if not all((codex, claude, control)):
        raise RuntimeError(
            "cannot identify codex/claude/control without guessing. Existing tags or explicit "
            "titles are required; restart the dashboard instead of assigning panes by order")
    if len({codex, claude, control}) != 3:
        raise RuntimeError("conflicting dashboard identities resolve more than one role to a pane")
    for name, pane in (("codex", codex), ("claude", claude),
                       ("control", control)):
        owner = pane_agent(pane)
        if owner and owner != name:
            raise RuntimeError(
                f"upgrade resolved {name!r} to pane {pane}, but that pane is tagged {owner!r}; "
                "refusing to overwrite a conflicting live identity")
    # Titles are cosmetic only: the TUI overwrites them. The tag is the identity.
    tmux("select-pane", "-t", codex, "-T", "codex")
    tmux("select-pane", "-t", claude, "-T", "claude")
    tag_pane(codex, "codex")
    tag_pane(claude, "claude")
    tag_pane(control, "control")
    for name, pane in (("codex", codex), ("claude", claude)):
        if rows_by_pane.get(pane, ("", ""))[1] != name:
            tmux("respawn-pane", "-k", "-t", pane, "-c", str(ROOT), *SHELL_COMMAND)
            wait_for_shell(pane)
            send_line(pane, agent_command(name))
            wait_for_app(pane, name)
            send_line(pane, f"{AGENT_IDENTITIES[name]}. Follow AGENTS.md and the sequential "
                            "ownership protocol in agent_discussion.md.")
    STOP.touch()
    time.sleep(0.3)
    write_state(mode="manual", owner="none", active_agent=None, status="starting",
                observed_sequence=latest_entry()[0],
                panes={"codex": codex, "claude": claude, "control": control})
    supervisor = f"{sys.executable} {Path(__file__).resolve()} run >>{LOG} 2>&1 &"
    tmux("send-keys", "-t", control, "-l", supervisor)
    tmux("send-keys", "-t", control, "Enter")
    tmux("select-pane", "-t", control)
    print("upgraded existing dashboard to codex + claude")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    start_parser = sub.add_parser("start")
    start_parser.add_argument("--first", choices=AGENTS, default="claude")
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
    elif args.command == "auto": enable_auto()
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
        # `STOP` is a lifecycle signal; `mode` is a policy. Conflating them meant a restart
        # silently disabled automatic handoffs - the dispatcher looked healthy and forwarded
        # nothing (Seq 165). `pause` already exists for the policy; this only stops the process.
        STOP.touch(); print("interactive supervisor stop requested (mode unchanged; use `pause` "
                            "to disable automatic handoffs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
