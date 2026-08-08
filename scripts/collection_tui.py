#!/usr/bin/env python3
"""A live terminal dashboard for the B11a collection. Read-only, and pure stdlib.

OBSERVES, NEVER PARTICIPATES -- the same rule as the notifier. It opens the supervisor state, the
receipts and the artifacts READ-ONLY, runs git for log lines, and writes nothing anywhere. If this
process dies the collection does not notice, and a test asserts the module names no write.

Truecolor ANSI rather than curses: the terminal reports COLORTERM=truecolor, so the palette can be
exact instead of approximated to 256, and the alternate screen buffer keeps the scrollback intact.

The credential rule from operator_notify applies here too and is easier to get wrong, because a TUI
is tempting to feed raw log tails. The endpoint is NEVER rendered: `describe`-style named fields
only, and the feed shows commit SUBJECTS and stage names, never argv or log text.
"""
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import termios
import threading
import time
import tty

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORK = ROOT / "research" / "b11a"
STATE = WORK / "supervisor_state.json"
RECEIPTS = WORK / "receipts"
BODIES = WORK / "b11a_bodies.sqlite"
SIGNATURES = WORK / "b11a_signatures.sqlite"
TRANSCRIPTS = pathlib.Path.home() / ".claude" / "projects" / "-home-anont-meme"

def _b11c():
    """The supervisor, loaded for its RUN_ORDER only.

    DERIVED, not restated. A hardcoded copy of the stage list here would drift the first time a
    stage is added -- which is exactly what happened twice tonight: the manifest missed b11f, and
    b18c's staging list missed it again one layer down. A dashboard showing 9 stages while the
    pipeline runs 10 would be a display that lies confidently.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "b11c_for_run_order", ROOT / "scripts" / "b11c_maturity_watcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUN_ORDER = _b11c().RUN_ORDER

# Claude's palette, exact.
CORAL = (217, 119, 87)
CREAM = (240, 238, 230)
MUTED = (138, 135, 128)
DIM = (94, 92, 87)
GREEN = (122, 158, 126)
AMBER = (214, 168, 92)
RED = (196, 94, 84)
INK = (38, 38, 36)


def fg(rgb):
    return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def bg(rgb):
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


RESET = "\033[0m"
BOLD = "\033[1m"


# Eighths, so one cell carries eight visible states instead of one. Over 153,473 blocks a
# whole-cell bar advances once every 29 minutes, which reads as broken -- and a progress bar that
# never moves is worse than no progress bar, because it says the run is stuck.
PARTIALS = " ▏▎▍▌▋▊▉"


def bar(done, total, width=34, filled_colour=CORAL, empty_colour=DIM):
    """A proportional bar with sub-cell resolution. `total` of zero renders empty."""
    fraction = (done / total) if total else 0.0
    fraction = max(0.0, min(1.0, fraction))
    exact = fraction * width
    cells = int(exact)
    remainder = exact - cells
    tip = PARTIALS[int(remainder * 8)] if cells < width else ""
    empty = width - cells - (1 if tip else 0)
    return (fg(filled_colour) + "█" * cells + tip + fg(empty_colour) + "░" * max(0, empty) + RESET,
            fraction)


def human_time(seconds):
    if seconds is None or seconds < 0:
        return "--"
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds/60:.0f}m"
    if seconds < 86400 * 2:
        return f"{seconds/3600:.1f}h"
    return f"{seconds/86400:.1f}d"


def thousands(value):
    return f"{value:,}" if isinstance(value, int) else str(value)


# ------------------------------------------------------------------------------------------------
# Readers. Every one of these is read-only and tolerant of a file that is mid-write.
# ------------------------------------------------------------------------------------------------

def read_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def read_receipts():
    out = {}
    if not RECEIPTS.exists():
        return out
    for path in RECEIPTS.iterdir():
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        out[record.get("stage", path.stem)] = record
    return out


def sqlite_counts(path, queries):
    """Counts from a live database. A busy artifact returns None rather than blocking the frame."""
    if not path.exists():
        return {name: None for name in queries}
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro&immutable=0", uri=True, timeout=0.4)
        db.execute("PRAGMA busy_timeout=400")
        out = {}
        for name, sql in queries.items():
            try:
                out[name] = db.execute(sql).fetchone()[0]
            except sqlite3.Error:
                out[name] = None
        db.close()
        return out
    except sqlite3.Error:
        return {name: None for name in queries}


def git_feed(limit=6):
    try:
        result = subprocess.run(
            ["git", "log", f"-{limit}", "--format=%h\x1f%ar\x1f%an\x1f%s"],
            cwd=ROOT, capture_output=True, text=True, timeout=4)
        rows = []
        for line in result.stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                rows.append(parts)
        return rows
    except (OSError, subprocess.SubprocessError):
        return []


# The phase targets come from COUNT(DISTINCT signature) over a multi-gigabyte inventory, which
# takes the better part of a minute. Computing it inline made the FIRST FRAME take 54 seconds and
# the dashboard look dead -- a progress display whose own progress you cannot see. It is loaded
# once, on a daemon thread, and the frame renders without it until it arrives.
_TARGETS = {"value": None, "state": "idle"}


def _load_targets():
    counts = sqlite_counts(SIGNATURES, {
        "ok": "SELECT COUNT(DISTINCT signature) FROM signature_observation "
              "WHERE time_class='in_window' AND err_json='null'",
        "slots": "SELECT COUNT(DISTINCT slot) FROM signature_observation "
                 "WHERE time_class='in_window' AND err_json='null'"})
    if counts.get("ok"):
        _TARGETS["value"] = {"txns": counts["ok"], "blocks": counts["slots"]}
        _TARGETS["state"] = "ready"
    else:
        _TARGETS["state"] = "unavailable"


def start_target_load():
    """Kick the one slow query onto a daemon thread. Idempotent; never blocks a frame."""
    if _TARGETS["state"] == "idle" and SIGNATURES.exists():
        _TARGETS["state"] = "loading"
        threading.Thread(target=_load_targets, daemon=True).start()
    return _TARGETS


def agent_usage(cache={}, every=45.0):
    """Token usage per seat, from the session transcripts. Cached: these files are tens of MiB."""
    now = time.time()
    if cache.get("at", 0) + every > now:
        return cache.get("value", {})
    totals = {}
    if TRANSCRIPTS.exists():
        for path in TRANSCRIPTS.glob("*.jsonl"):
            if now - path.stat().st_mtime > 86400:
                continue
            seat = path.stem[:8]
            out = cached = created = 0
            try:
                with path.open() as handle:
                    for line in handle:
                        if '"usage"' not in line:
                            continue
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        usage = (record.get("message") or {}).get("usage") or {}
                        out += usage.get("output_tokens", 0) or 0
                        cached += usage.get("cache_read_input_tokens", 0) or 0
                        created += usage.get("cache_creation_input_tokens", 0) or 0
            except OSError:
                continue
            if out:
                totals[seat] = {"output": out, "cache_read": cached, "cache_write": created,
                                "mtime": path.stat().st_mtime}
    cache["at"], cache["value"] = now, totals
    return totals


# ------------------------------------------------------------------------------------------------
# Frame
# ------------------------------------------------------------------------------------------------

def render(previous):
    state = read_state()
    receipts = read_receipts()
    now = time.time()
    lines = []
    add = lines.append

    running = state.get("state", "not started")
    quarantine = state.get("quarantine")
    done_stages = list(state.get("stages_completed") or [])
    in_flight = state.get("stage_in_flight")

    if quarantine:
        dot, colour, label = "●", RED, f"QUARANTINED  {quarantine.get('reason_code','')}"
    elif in_flight:
        dot, colour, label = "◐", CORAL, running
    elif running == "all_stages_complete":
        dot, colour, label = "●", GREEN, "COMPLETE"
    else:
        dot, colour, label = "○", MUTED, running

    add(f"{fg(CORAL)}{BOLD}  B11A COLLECTION{RESET}"
        f"{fg(DIM)}   pump.fun research pipeline{RESET}")
    heartbeat = state.get("stage_heartbeat_at")
    beat = f"{fg(DIM)}heartbeat {human_time(now - heartbeat)} ago{RESET}" if heartbeat else ""
    add(f"  {fg(colour)}{dot} {label}{RESET}   {beat}")
    add("")

    # ---- pipeline -----------------------------------------------------------------------------
    filled, fraction = bar(len(done_stages), len(RUN_ORDER), 34)
    add(f"  {fg(CREAM)}PIPELINE{RESET}   {filled}  {fg(CREAM)}{len(done_stages)}/{len(RUN_ORDER)}{RESET}")
    add("")
    for stage in RUN_ORDER:
        receipt = receipts.get(stage)
        if stage in done_stages:
            took = (receipt or {}).get("finished_at", 0) - (receipt or {}).get("started_at", 0)
            add(f"    {fg(GREEN)}✓{RESET} {fg(MUTED)}{stage:<24}{RESET}{fg(DIM)}{human_time(took)}{RESET}")
        elif stage == in_flight:
            elapsed = now - (state.get("stage_progress_at") or now)
            add(f"    {fg(CORAL)}◐{RESET} {fg(CREAM)}{BOLD}{stage:<24}{RESET}"
                f"{fg(CORAL)}running {human_time(elapsed)}{RESET}")
        else:
            add(f"    {fg(DIM)}·  {stage}{RESET}")
    add("")

    # ---- collection ---------------------------------------------------------------------------
    counts = sqlite_counts(BODIES, {
        "blocks": "SELECT COUNT(*) FROM raw_block_signatures",
        "txns": "SELECT COUNT(*) FROM raw_transaction"})
    loader = start_target_load()
    targets = loader["value"]

    if counts["blocks"] is not None and targets:
        for key, label in (("blocks", "BLOCKS"), ("txns", "TRANSACTIONS")):
            done, total = counts[key] or 0, targets[key]
            drawn, fraction = bar(done, total, 34)
            add(f"  {fg(CREAM)}{label:<13}{RESET}{drawn}  "
                f"{fg(CREAM)}{thousands(done)}{fg(DIM)}/{thousands(total)}  "
                f"{fg(MUTED)}{fraction*100:5.1f}%{RESET}")
        # live rate from the previous frame
        total_done = (counts["blocks"] or 0) + (counts["txns"] or 0)
        last = previous.get("sample")
        rate = previous.get("rate")
        if last and now - last[0] >= 8:
            delta = total_done - last[1]
            if delta >= 0:
                measured = delta / (now - last[0])
                rate = measured if rate is None else rate * 0.7 + measured * 0.3
            previous["sample"] = (now, total_done)
            previous["rate"] = rate
        elif not last:
            previous["sample"] = (now, total_done)
        # Phase-aware. getBlock returns a whole block and is far slower per call than
        # getTransaction; a single blended rate would quote a number true of neither phase.
        blocks_left = max(0, targets["blocks"] - (counts["blocks"] or 0))
        txns_left = max(0, targets["txns"] - (counts["txns"] or 0))
        add("")
        history = previous.setdefault("history", [])
        history.append((now, total_done))
        while history and now - history[0][0] > 300:
            history.pop(0)
        per_minute = None
        if len(history) > 1 and history[-1][0] - history[0][0] > 20:
            span = history[-1][0] - history[0][0]
            per_minute = (history[-1][1] - history[0][1]) / span * 60
        if rate:
            in_blocks = blocks_left > 0
            phase_eta = (blocks_left / rate) if in_blocks else (txns_left / rate)
            phase = "blocks" if in_blocks else "transactions"
            add(f"  {fg(DIM)}rate{RESET} {fg(CORAL)}{rate:.2f}/s{RESET}   "
                f"{fg(DIM)}{phase} left{RESET} {fg(CREAM)}"
                f"{thousands(blocks_left if in_blocks else txns_left)}{RESET}   "
                f"{fg(DIM)}this phase{RESET} {fg(CORAL)}{human_time(phase_eta)}{RESET}")
            if per_minute is not None:
                finish = time.localtime(now + phase_eta)
                add(f"  {fg(DIM)}last 5 min{RESET} {fg(CREAM)}{per_minute:,.0f}/min{RESET}   "
                    f"{fg(DIM)}done around{RESET} {fg(CORAL)}"
                    f"{time.strftime('%a %H:%M', finish)}{RESET}")
            if in_blocks and txns_left:
                add(f"  {fg(DIM)}then {thousands(txns_left)} transactions, which fetch faster "
                    f"per call{RESET}")
        else:
            add(f"  {fg(DIM)}measuring rate...{RESET}")
    elif counts["blocks"] is None:
        add(f"  {fg(DIM)}collection artifact not open yet{RESET}")
    if counts["blocks"] is not None and not targets:
        drawn, _ = bar(0, 1, 34)
        add(f"  {fg(CREAM)}BLOCKS       {RESET}{drawn}  "
            f"{fg(CREAM)}{thousands(counts['blocks'] or 0)}{fg(DIM)}/…{RESET}")
        note = "counting the inventory (one slow pass, ~1 min)" \
            if loader["state"] == "loading" else "targets unavailable"
        add(f"  {fg(DIM)}{note}{RESET}")
    add("")

    # ---- agents -------------------------------------------------------------------------------
    usage = agent_usage()
    if usage:
        add(f"  {fg(CREAM)}AGENT USAGE{RESET} {fg(DIM)}(this project, last 24h){RESET}")
        biggest = max((v["output"] for v in usage.values()), default=1)
        for seat, value in sorted(usage.items(), key=lambda kv: -kv[1]["output"])[:4]:
            drawn, _ = bar(value["output"], biggest, 20)
            live = "●" if time.time() - value["mtime"] < 300 else " "
            add(f"    {fg(CORAL)}{live}{RESET} {fg(MUTED)}{seat}{RESET}  {drawn}  "
                f"{fg(CREAM)}{value['output']/1000:,.0f}k{fg(DIM)} out  "
                f"{value['cache_read']/1_000_000:,.1f}M cached{RESET}")
        add("")

    # ---- feed ---------------------------------------------------------------------------------
    add(f"  {fg(CREAM)}RECENT{RESET}")
    for sha, when, who, subject in git_feed(6):
        subject = subject[:60] + ("…" if len(subject) > 62 else "")
        add(f"    {fg(CORAL)}{sha}{RESET} {fg(DIM)}{when:<15}{RESET}{fg(MUTED)}{subject}{RESET}")

    add("")
    add(f"  {fg(DIM)}q quit   ·   read-only, nothing here writes{RESET}")
    return lines


def main():
    interval = 2.0
    previous = {}
    old = None
    try:
        old = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
    except (termios.error, ValueError, OSError):
        old = None
    sys.stdout.write("\033[?1049h\033[?25l")            # alternate screen, hide cursor
    try:
        while True:
            frame = render(previous)
            sys.stdout.write("\033[H\033[2J" + "\n".join(frame) + "\n")
            sys.stdout.flush()
            if old:
                import select
                if select.select([sys.stdin], [], [], interval)[0]:
                    if sys.stdin.read(1).lower() == "q":
                        break
            else:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\033[?1049l")        # restore cursor and screen
        sys.stdout.flush()
        if old:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
    return 0


if __name__ == "__main__":
    sys.exit(main())
