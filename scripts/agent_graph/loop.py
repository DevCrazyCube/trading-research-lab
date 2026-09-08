#!/usr/bin/env python3
"""Deterministic bookkeeping for the research agent graph.

The "graph" is scripts/agent_graph/graph.js (a Workflow: execute -> adversarial-verify per task).
The "loop" is a driver that, each iteration:
    1. `loop.py next`   -> selects the top pending tasks (JSON on stdout) to feed the graph
    2. runs the Workflow graph on those tasks (done by the Claude session / cron-fired session)
    3. `loop.py merge`  -> folds the graph's structured results back into agenda.json

State lives entirely in agenda.json on disk, so a crash resumes instead of restarting. This helper
never calls a model and never edits research files -- it only moves tasks through their lifecycle.

Verdict -> status mapping on merge:
    CONFIRMED  + executor status done      -> verified
    REFUTED                                -> pending  (re-queued; the claim did not hold)
    NEEDS_OWNER / PLAUSIBLE                -> blocked  (needs owner sign-off or more evidence)
    executor status blocked/killed         -> that status verbatim
"""
import importlib.util
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
AGENDA = HERE / "agenda.json"
CONTROL = HERE / "control.json"
DEFAULT_BATCH = 3
CONTROL_DEFAULT = {"paused": False, "batch": DEFAULT_BATCH, "run_requested": False, "updated_at": None}


def notify(text):
    """Best-effort Telegram push via the hardened scripts/operator_notify.py (its assert_no_secret
    guard makes a leaked credential fatal, not sent). Silently no-ops if Telegram is unconfigured or
    the module refuses -- notifications must never break the loop."""
    try:
        p = HERE.parent / "operator_notify.py"
        spec = importlib.util.spec_from_file_location("operator_notify", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.load_env()
        return bool(m.send(text))
    except Exception as e:
        print(f"(telegram notify skipped: {str(e)[:80]})", file=sys.stderr)
        return False


def load_control():
    c = dict(CONTROL_DEFAULT)
    if CONTROL.exists():
        try:
            c.update(json.loads(CONTROL.read_text()))
        except Exception:
            pass
    return c


def save_control(c):
    c["updated_at"] = int(time.time())
    tmp = CONTROL.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(c, indent=2) + "\n")
    tmp.replace(CONTROL)


def load():
    return json.loads(AGENDA.read_text())


def save(a):
    a["updated_at"] = int(time.time())
    AGENDA.write_text(json.dumps(a, indent=2) + "\n")


def pending(a):
    return sorted([t for t in a["tasks"] if t["status"] == "pending"],
                  key=lambda t: t.get("priority", 999))


def ready(a):
    """Pending tasks whose declared deps are all satisfied -- verified by the graph OR approved by
    the owner. Those are the ones safe to dispatch now."""
    done = {t["id"] for t in a["tasks"] if t["status"] in ("verified", "approved")}
    return [t for t in pending(a) if all(d in done for d in t.get("deps", []))]


def cmd_next(batch=None):
    ctrl = load_control()
    if batch is None:
        batch = ctrl.get("batch", DEFAULT_BATCH)
    if ctrl.get("paused"):
        print(json.dumps({"tasks": [], "paused": True}, indent=2))
        return
    a = load()
    picks = ready(a)[:batch]
    # Mark them running so a concurrent/duplicate driver does not double-dispatch. Stamp when, so
    # reclaim can tell a legitimately in-flight task from a crash-orphaned one.
    ids = {t["id"] for t in picks}
    nowts = int(time.time())
    for t in a["tasks"]:
        if t["id"] in ids:
            t["status"] = "running"
            t["started_at"] = nowts
    save(a)
    # A dispatch consumes any pending run request.
    if ctrl.get("run_requested"):
        ctrl["run_requested"] = False
        save_control(ctrl)
    # Emit exactly what graph.js expects as its `args`.
    print(json.dumps({"tasks": picks}, indent=2))


def cmd_control(args):
    """Read or mutate the loop control flags. Usage:
       control                       -> print current control
       control pause | resume
       control batch <N>
       control request-run           -> queue an iteration for the next tick"""
    ctrl = load_control()
    if not args:
        print(json.dumps(ctrl, indent=2))
        return
    op = args[0]
    if op == "pause":
        ctrl["paused"] = True
    elif op == "resume":
        ctrl["paused"] = False
    elif op == "batch" and len(args) > 1:
        ctrl["batch"] = max(1, int(args[1]))
    elif op == "request-run":
        ctrl["run_requested"] = True
    else:
        print(f"unknown control op {args!r}", file=sys.stderr)
        sys.exit(2)
    save_control(ctrl)
    print(json.dumps(ctrl, indent=2))


def cmd_merge(results_path):
    a = load()
    by_id = {t["id"]: t for t in a["tasks"]}
    payload = json.loads(pathlib.Path(results_path).read_text())
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    merged = 0
    for row in rows:
        t = by_id.get(row.get("id"))
        if not t:
            continue
        v = (row.get("verdict") or {}).get("verdict")
        exec_status = row.get("status")
        t["result"] = row.get("result")
        t["verdict"] = row.get("verdict")
        if exec_status in ("blocked", "killed"):
            t["status"] = exec_status
        elif v == "CONFIRMED" and exec_status == "done":
            t["status"] = "verified"
        elif v == "REFUTED":
            t["status"] = "pending"      # claim failed verification -> re-queue
        else:
            t["status"] = "blocked"      # NEEDS_OWNER / PLAUSIBLE / partial
        merged += 1
    save(a)
    print(f"merged {merged} result(s)")
    # Telegram summary of this iteration (best-effort; no-op if unconfigured).
    icon = {"verified": "✅", "blocked": "⛔", "pending": "♻️", "killed": "❌", "running": "▶️"}
    lines = []
    for row in rows:
        t = by_id.get(row.get("id"))
        if not t:
            continue
        v = (row.get("verdict") or {}).get("verdict", "")
        head = ((t.get("result") or {}).get("headline") or "")[:160]
        lines.append(f"{icon.get(t['status'], '•')} {t['id']} → {t['status']}"
                     + (f" ({v})" if v else "") + (f"\n   {head}" if head else ""))
    counts = {}
    for t in a["tasks"]:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    tally = ", ".join(f"{k} {counts[k]}" for k in sorted(counts))
    if lines:
        notify("Agent graph — iteration merged\n\n" + "\n".join(lines) + f"\n\nAgenda: {tally}")
    cmd_status()


def cmd_status():
    a = load()
    counts = {}
    for t in a["tasks"]:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    print("agenda:", json.dumps(counts))
    for t in sorted(a["tasks"], key=lambda t: t.get("priority", 999)):
        head = ""
        if t.get("result"):
            head = " :: " + (t["result"].get("headline") or "")[:80]
        vt = (t.get("verdict") or {}).get("verdict", "")
        print(f"  [{t['status']:8}] {t['id']:26} p{t.get('priority')} {vt:10}{head}")


STALE_SECS = 10800  # 3 h: these tasks run genuinely long data pipelines (multi-year bar fetches,
                    # 30-day slippage sweeps) that can exceed an hour. Only reclaim a running task
                    # after 3 h with no result — a real crash still auto-recovers, and the dashboard
                    # "Reset stuck tasks" (reclaim --force) covers the impatient case.


def cmd_reclaim(force=False):
    """Crash recovery. A task left 'running' is EITHER genuinely in flight (a workflow is still
    working it) OR orphaned (the graph died mid-iteration). We only re-queue the orphaned ones --
    those whose started_at is older than STALE_SECS (or missing). `--force` re-queues all running.
    This is what stops a scheduled tick from clobbering a batch that is still running."""
    a = load()
    now = int(time.time())
    reclaimed = inflight = 0
    for t in a["tasks"]:
        if t["status"] != "running":
            continue
        age = now - t.get("started_at", 0)
        if force or age > STALE_SECS:
            t["status"] = "pending"
            t.pop("started_at", None)
            reclaimed += 1
        else:
            inflight += 1
    save(a)
    print(f"reclaimed {reclaimed} orphaned task(s); left {inflight} in flight (running < {STALE_SECS}s)")
    cmd_status()


def cmd_add(title, kind, priority):
    a = load()
    n = len([t for t in a["tasks"]]) + 1
    a["tasks"].append({
        "id": f"T{n}_new", "title": title, "kind": kind, "priority": int(priority),
        "status": "pending", "why": "", "acceptance": "", "guardrails": [],
        "artifacts": [], "result": None, "verdict": None,
    })
    save(a)
    print(f"added task T{n}_new")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "next":
        batch = int(sys.argv[2]) if len(sys.argv) > 2 else None
        cmd_next(batch)
    elif cmd == "control":
        cmd_control(sys.argv[2:])
    elif cmd == "merge":
        cmd_merge(sys.argv[2])
    elif cmd == "status":
        cmd_status()
    elif cmd == "reclaim":
        cmd_reclaim(force=("--force" in sys.argv))
    elif cmd == "add":
        cmd_add(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(f"unknown command {cmd!r}; use next|merge|status|add", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
