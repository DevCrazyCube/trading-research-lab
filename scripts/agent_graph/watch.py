#!/usr/bin/env python3
"""Watch what the research-graph agents are thinking and doing, in plain text.

The Workflow subagents write their full transcript (reasoning + tool calls) as JSONL under
subagents/workflows/wf_*/agent-*.jsonl. Those files are unreadable raw. This pretty-prints them.

    python scripts/agent_graph/watch.py            # follow the NEWEST workflow's agents live
    python scripts/agent_graph/watch.py --once      # print what's there so far and exit
    python scripts/agent_graph/watch.py <wf_dir>    # a specific workflow dir

Shows, per agent: thinking (dim), assistant text, and each tool call (name + short input).
"""
import glob
import json
import os
import pathlib
import sys
import time

BASE = pathlib.Path(os.path.expanduser("~/.claude/projects/-home-anont-meme"))
# The transcript root is under the active session dir; discover it rather than hardcode the session.
ROOTS = glob.glob(str(BASE / "*" / "subagents" / "workflows"))

DIM, RESET, CYAN, YELLOW, GREEN = "\033[2m", "\033[0m", "\033[36m", "\033[33m", "\033[32m"


def newest_wf():
    dirs = []
    for r in ROOTS:
        dirs += glob.glob(os.path.join(r, "wf_*"))
    if not dirs:
        sys.exit("no workflow transcripts found yet -- run an iteration first")
    return max(dirs, key=os.path.getmtime)


def short(v, n=220):
    s = json.dumps(v) if not isinstance(v, str) else v
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "..."


def render_line(agent_short, obj):
    role = obj.get("type") or obj.get("role")
    msg = obj.get("message", obj)
    content = msg.get("content") if isinstance(msg, dict) else None
    tag = f"{CYAN}[{agent_short}]{RESET}"
    if isinstance(content, str):
        print(f"{tag} {content}")
        return
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        t = block.get("type")
        if t == "thinking":
            th = short(block.get("thinking", "")).strip()
            if th:
                print(f"{tag} {DIM}think: {th}{RESET}")
        elif t == "text":
            print(f"{tag} {block.get('text','').strip()}")
        elif t == "tool_use":
            print(f"{tag} {YELLOW}-> {block.get('name')}{RESET} {DIM}{short(block.get('input',{}),160)}{RESET}")
        elif t == "tool_result":
            c = block.get("content")
            if isinstance(c, list):
                c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
            print(f"{tag} {GREEN}<- {short(c,160)}{RESET}")


def follow(wf):
    wf = pathlib.Path(wf)
    print(f"watching {wf.name}  (Ctrl-C to stop)\n")
    offsets = {}
    once = "--once" in sys.argv
    while True:
        for f in sorted(glob.glob(str(wf / "agent-*.jsonl"))):
            if f.endswith(".meta.json"):
                continue
            a = pathlib.Path(f).stem.replace("agent-", "")[:8]
            with open(f) as fh:
                fh.seek(offsets.get(f, 0))
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        render_line(a, json.loads(line))
                    except Exception:
                        pass
                offsets[f] = fh.tell()
        if once:
            return
        time.sleep(1.0)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    follow(args[0] if args else newest_wf())
